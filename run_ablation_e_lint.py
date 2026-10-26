# Work Plan item 8 / Ablation G: Compiler-Oracle-PRESENCE Ablation
#
# Distinct research question from Ablation B/B v2 (which varies feedback
# *type*, real vs. generic, after a loop already exists): this ablation
# varies whether a compile-check+retry loop exists AT ALL versus true
# one-shot generation with zero verification.
#
# Design (deliberately a strict superset, not a separate second arm): the
# "oracle absent" condition is simply attempt 1's own outcome -- generate
# once, compile/run it to RECORD whether it would have worked, but never
# feed that back into anything. The "oracle present" condition is whether
# ANY of up to 5 attempts succeeds, using the real compiler diagnostic as
# feedback on each retry (the same mechanism Ablation B v2's Arm A uses,
# and the same one AeroHarness's actual Stage 6 self-repair loop uses).
# Because "oracle present" by construction already includes attempt 1 as
# its first attempt, this is an inherently paired design: oracle-present
# success implies either (a) attempt 1 already succeeded (both conditions
# agree), or (b) a later real-feedback retry succeeded where attempt 1
# didn't (a discordant pair in oracle-present's favor). It is structurally
# impossible for oracle-absent to succeed where oracle-present fails, so
# McNemar's test here is really asking: in how many trials did the loop
# convert an attempt-1 failure into an eventual success?
#
# Reuses Ablation B v2's TARGETS prompts, evaluate_harness() success
# criteria, and call_ollama() verbatim -- this scaffolding was already
# independently audited and fixed (5 real defects found and corrected,
# see ABLATION_B_V2.md's "Scaffolding Audit and Remediation" section)
# before any ablation result was trusted. Re-deriving it here from scratch
# would risk reintroducing one of those same five bugs.
#
# Unlike B v2, there is no Arm B (generic feedback) here at all -- it's
# not needed for this RQ, and dropping it means every API call this
# script makes goes toward the oracle-present-vs-absent question, letting
# the trial count be pushed higher per unit of compute than B v2 could
# afford while asking its own (different) question.
#
# Run from the repo root as:
#   python3 run_ablation_g.py --model qwen2.5-coder:7b
#   python3 run_ablation_g.py --model qwen2.5-coder:14b
# (run one model at a time, per the project's standing convention of
# reviewing each variant's results before the next one runs.)
# Default trial count is 20 per target (5 targets = 100 trials/model),
# matching B v2's own "Future Work" recommendation of n=20-30/target/model
# to accumulate enough discordant pairs for McNemar's test to actually
# carry statistical weight this time, instead of repeating the n=2/target
# floor-effect/inconclusive result.
# Resumable: like B v2, completed trials are skipped on re-run (progress
# is written to the results file after every trial), so an interrupted
# run can simply be re-invoked with the same --model to continue.

# Work Plan item 5: Static-Analysis-Lint Ablation ("Ablation E")
#
# Closes the literal "static analysis lints" gap in Objective 2 ("compiler
# diagnostics (GCC/Clang), static analysis lints, and dynamic sanitizer
# traces") -- the project's self-repair loop has only ever fed back
# compiler diagnostics; no clang-tidy/cppcheck-class static-analysis output
# has ever reached an LLM agent in any feedback loop, anywhere in the
# project, despite being named explicitly in the proposal text.
#
# RQ: when a generated harness fails to compile, does ALSO feeding back
# clang-tidy's static-analysis warnings (on top of the real compiler error,
# which Ablation B v2 already established is the right baseline -- see
# that document's Arm A) help the model converge to a working harness
# faster or more often than compiler feedback alone?
#
# Design: a direct two-arm paired branching trial, same shape as Ablation
# B v2's real-vs-generic-feedback design (not item 8/Ablation G's strict-
# superset design, since this genuinely needs two independent feedback
# conditions, not a nested one):
#   - Arm A (Lint + Compiler): on a failed attempt, the retry prompt
#     includes BOTH the real compiler error AND clang-tidy's warnings
#     against that same failed harness.cpp (when clang-tidy can produce
#     any -- a harness broken badly enough that clang-tidy itself can't
#     parse it falls back to compiler-only feedback for that round, noted
#     in the trial record rather than silently treated as "no lint arm
#     difference").
#   - Arm B (Compiler only): identical to Ablation B v2's Arm A / item 8's
#     oracle-present loop -- the existing, already-proven real-feedback
#     condition, unmodified. This is the control.
# Success criterion is unchanged in both arms (evaluate_harness()'s
# existing compile+run+coverage bar) -- the manipulation is only what text
# goes into the retry prompt, never what counts as success, so the two
# arms stay directly comparable via McNemar's test exactly like B v2.
#
# clang-tidy is invoked with its DEFAULT check set (no custom -checks=
# filter) -- deliberately not hand-picked to flatter the result, and
# mirrors the same -I include paths evaluate_harness() uses to compile,
# so it sees the same mocks/headers the real compile step does.
#
# Reuses Ablation B v2's/Ablation G's TARGETS prompts, evaluate_harness(),
# and call_ollama() verbatim -- this scaffolding was already independently
# audited and fixed (5 real defects found and corrected, see
# ABLATION_B_V2.md's "Scaffolding Audit and Remediation" section) before
# any ablation result built on it was trusted.
#
# Run from the repo root as:
#   python3 run_ablation_e_lint.py --model qwen2.5-coder:7b
#   python3 run_ablation_e_lint.py --model qwen2.5-coder:14b
# (run one model at a time, per the project's standing convention.)
# Default trial count is 20 per target (5 targets = 100 trials/model),
# same rationale as item 8: B v2's own n=20-combined data was underpowered
# (1 discordant pair, p=1.0); this aims to actually resolve the question.
# Resumable: completed trials are skipped on re-run.

import math

import os
import re, sys, time, json, subprocess, shutil, argparse, platform
from datetime import datetime

TARGETS = {
    "pl011_poll_in": """Write a libFuzzer harness in C++ for the function 'pl011_poll_in' from Zephyr PL011.
You must mock the MMIO registers using a static struct and include an LLVMFuzzerTestOneInput function.

Here is the source of the driver target function:
```c
static int pl011_poll_in(const struct device *dev, unsigned char *c)
{
	volatile struct pl011_regs *uart = get_uart(dev);

	if (uart->fr & PL011_FR_RXFE) {
		return -1;
	}

	*c = (unsigned char)uart->dr;
	return 0;
}
```
The function definition will be appended by the build system, so do NOT include or rewrite it; forward-declare it ABOVE that point using the exact same `static` qualifier shown in the source above (a forward declaration using `extern` or `extern "C"` instead of `static` will fail to link against the appended definition), and provide every mock, type, struct and macro it needs. These functions are static, so they must be in the same translation unit, and appending is what makes a forward declaration plus a later definition work.
You can #include "zephyr-src/drivers/serial/uart_pl011_registers.h" (or, equivalently, #include <zephyr/drivers/serial/uart_pl011_registers.h> — both paths resolve to the identical real header) to get the hardware register structs — the build system already provides `struct device` (fields: `config`, `data`, `mmio_base`) and the `BIT`, `GENMASK`, and `DEVICE_MMIO_GET` macros that header needs, via <zephyr/device.h>. Do NOT redefine `struct device`, `BIT`, `GENMASK`, or `DEVICE_MMIO_GET` yourself — that causes a redefinition error. Before calling the target function, set `dev->mmio_base` to point at your mock `struct pl011_regs` instance (this is what `get_uart()`/`DEVICE_MMIO_GET` reads). Use `dev->data` for driver runtime state (e.g. `struct pl011_data`) and `dev->config` for driver config (e.g. `struct pl011_config`) only if the target function needs them.
Include all necessary standard headers. Do NOT use `FuzzedDataProvider.h` — it is not guaranteed to be available in this build; read bytes directly from `data`/`size` instead.""",

    "pl011_poll_out": """Write a libFuzzer harness in C++ for the function 'pl011_poll_out' from Zephyr PL011.
You must mock the MMIO registers using a static struct and include an LLVMFuzzerTestOneInput function.

Here is the source of the driver target function:
```c
static void pl011_poll_out(const struct device *dev, unsigned char c)
{
	volatile struct pl011_regs *uart = get_uart(dev);

	while (uart->fr & PL011_FR_TXFF) {
		; /* Wait */
	}

	uart->dr = (uint32_t)c;
}
```
The function definition will be appended by the build system, so do NOT include or rewrite it; forward-declare it ABOVE that point using the exact same `static` qualifier shown in the source above (a forward declaration using `extern` or `extern "C"` instead of `static` will fail to link against the appended definition), and provide every mock, type, struct and macro it needs. These functions are static, so they must be in the same translation unit, and appending is what makes a forward declaration plus a later definition work.
You can #include "zephyr-src/drivers/serial/uart_pl011_registers.h" (or, equivalently, #include <zephyr/drivers/serial/uart_pl011_registers.h> — both paths resolve to the identical real header) to get the hardware register structs — the build system already provides `struct device` (fields: `config`, `data`, `mmio_base`) and the `BIT`, `GENMASK`, and `DEVICE_MMIO_GET` macros that header needs, via <zephyr/device.h>. Do NOT redefine `struct device`, `BIT`, `GENMASK`, or `DEVICE_MMIO_GET` yourself — that causes a redefinition error. Before calling the target function, set `dev->mmio_base` to point at your mock `struct pl011_regs` instance (this is what `get_uart()`/`DEVICE_MMIO_GET` reads). Use `dev->data` for driver runtime state (e.g. `struct pl011_data`) and `dev->config` for driver config (e.g. `struct pl011_config`) only if the target function needs them.
Include all necessary standard headers. Do NOT use `FuzzedDataProvider.h` — it is not guaranteed to be available in this build; read bytes directly from `data`/`size` instead.""",

    "pl011_isr": """Write a libFuzzer harness in C++ for the function 'pl011_isr' from Zephyr PL011.
You must mock the MMIO registers using a static struct and include an LLVMFuzzerTestOneInput function.

Here is the source of the driver target function:
```c
static void pl011_isr(const struct device *dev)
{
	struct pl011_data *data = (struct pl011_data *)dev->data;
	volatile struct pl011_regs *uart = get_uart(dev);

	if (uart->mis & PL011_IMSC_CTSMIM) {
		uart->icr = PL011_IMSC_CTSMIM;
		uart->imsc &= ~PL011_IMSC_CTSMIM;
	}

	if (uart->mis & PL011_IMSC_ERROR_MASK) {
		uart->icr = uart->mis & PL011_IMSC_ERROR_MASK;
	}

	if (data->irq_cb) {
		K_SPINLOCK(&data->irq_cb_lock) {
			data->irq_cb(dev, data->irq_cb_data);
		}
	}
}
```
The function definition will be appended by the build system, so do NOT include or rewrite it; forward-declare it ABOVE that point using the exact same `static` qualifier shown in the source above (a forward declaration using `extern` or `extern "C"` instead of `static` will fail to link against the appended definition), and provide every mock, type, struct and macro it needs. These functions are static, so they must be in the same translation unit, and appending is what makes a forward declaration plus a later definition work.
You can #include "zephyr-src/drivers/serial/uart_pl011_registers.h" (or, equivalently, #include <zephyr/drivers/serial/uart_pl011_registers.h> — both paths resolve to the identical real header) to get the hardware register structs — the build system already provides `struct device` (fields: `config`, `data`, `mmio_base`) and the `BIT`, `GENMASK`, and `DEVICE_MMIO_GET` macros that header needs, via <zephyr/device.h>. Do NOT redefine `struct device`, `BIT`, `GENMASK`, or `DEVICE_MMIO_GET` yourself — that causes a redefinition error. Before calling the target function, set `dev->mmio_base` to point at your mock `struct pl011_regs` instance (this is what `get_uart()`/`DEVICE_MMIO_GET` reads). Use `dev->data` for driver runtime state (e.g. `struct pl011_data`) and `dev->config` for driver config (e.g. `struct pl011_config`) only if the target function needs them.
This target also uses `k_spinlock_t` (as the type of `irq_cb_lock` in your `struct pl011_data`) and the `K_SPINLOCK(&lock) { ... }` macro — both are provided via `#include <zephyr/kernel.h>`. Do NOT define `k_spinlock_t` or `K_SPINLOCK` yourself.
Include all necessary standard headers. Do NOT use `FuzzedDataProvider.h` — it is not guaranteed to be available in this build; read bytes directly from `data`/`size` instead.""",

    "pl011_runtime_configure_internal": """Write a libFuzzer harness in C++ for the function 'pl011_runtime_configure_internal' from Zephyr PL011.
You must mock the MMIO registers using a static struct and include an LLVMFuzzerTestOneInput function.

Here is the source of the driver target function:
```c
static int pl011_runtime_configure_internal(const struct device *dev,
					    const struct uart_config *cfg)
{
	volatile struct pl011_regs *uart = get_uart(dev);
	uint32_t lcrh;

	uart->cr &= ~(PL011_CR_UARTEN);

	lcrh = uart->lcr_h & ~(PL011_LCRH_FORMAT_MASK | PL011_LCRH_STP2);

	switch (cfg->parity) {
	case UART_CFG_PARITY_NONE:
		break;
	case UART_CFG_PARITY_ODD:
		lcrh |= PL011_LCRH_PEN;
		break;
	case UART_CFG_PARITY_EVEN:
		lcrh |= PL011_LCRH_PEN | PL011_LCRH_EPS;
		break;
	default:
		return -ENOTSUP;
	}

	if (cfg->stop_bits == UART_CFG_STOP_BITS_2) {
		lcrh |= PL011_LCRH_STP2;
	}

	switch (cfg->data_bits) {
	case UART_CFG_DATA_BITS_5:
		lcrh |= PL011_LCRH_WLEN_5;
		break;
	case UART_CFG_DATA_BITS_6:
		lcrh |= PL011_LCRH_WLEN_6;
		break;
	case UART_CFG_DATA_BITS_7:
		lcrh |= PL011_LCRH_WLEN_7;
		break;
	case UART_CFG_DATA_BITS_8:
		lcrh |= PL011_LCRH_WLEN_8;
		break;
	default:
		return -ENOTSUP;
	}

	if (cfg->flow_ctrl == UART_CFG_FLOW_CTRL_RTS_CTS) {
		pl011_set_flow_control(dev, true);
	} else if (cfg->flow_ctrl == UART_CFG_FLOW_CTRL_NONE) {
		pl011_set_flow_control(dev, false);
	} else {
		return -ENOTSUP;
	}

	uart->lcr_h = lcrh;

	pl011_set_baudrate(dev, cfg->baudrate);

	uart->cr |= PL011_CR_UARTEN;

	return 0;
}
```
The function definition will be appended by the build system, so do NOT include or rewrite it; forward-declare it ABOVE that point using the exact same `static` qualifier shown in the source above (a forward declaration using `extern` or `extern "C"` instead of `static` will fail to link against the appended definition), and provide every mock, type, struct and macro it needs. These functions are static, so they must be in the same translation unit, and appending is what makes a forward declaration plus a later definition work.
You can #include "zephyr-src/drivers/serial/uart_pl011_registers.h" (or, equivalently, #include <zephyr/drivers/serial/uart_pl011_registers.h> — both paths resolve to the identical real header) to get the hardware register structs — the build system already provides `struct device` (fields: `config`, `data`, `mmio_base`) and the `BIT`, `GENMASK`, and `DEVICE_MMIO_GET` macros that header needs, via <zephyr/device.h>. Do NOT redefine `struct device`, `BIT`, `GENMASK`, or `DEVICE_MMIO_GET` yourself — that causes a redefinition error. Before calling the target function, set `dev->mmio_base` to point at your mock `struct pl011_regs` instance (this is what `get_uart()`/`DEVICE_MMIO_GET` reads). Use `dev->data` for driver runtime state (e.g. `struct pl011_data`) and `dev->config` for driver config (e.g. `struct pl011_config`) only if the target function needs them.
This target also uses `struct uart_config` and the `UART_CFG_PARITY_*`/`UART_CFG_STOP_BITS_*`/`UART_CFG_DATA_BITS_*`/`UART_CFG_FLOW_CTRL_*` enum constants — all are provided via `#include <zephyr/drivers/uart.h>`. Do NOT redefine `struct uart_config` or any of those enum constants yourself. It also calls `pl011_set_baudrate(dev, baudrate)` and `pl011_set_flow_control(dev, bool)` — these are two internal driver functions NOT provided by any header; you must forward-declare and mock both yourself (matching exactly these two-argument signatures — a no-op body is fine for fuzzing purposes).
Include all necessary standard headers. Do NOT use `FuzzedDataProvider.h` — it is not guaranteed to be available in this build; read bytes directly from `data`/`size` instead.""",

    "pl011_init": """Write a libFuzzer harness in C++ for the function 'pl011_init' from Zephyr PL011.
You must mock the MMIO registers using a static struct and include an LLVMFuzzerTestOneInput function.

Here is the source of the driver target function:
```c
static int pl011_init(const struct device *dev)
{
	const struct pl011_config *config = (const struct pl011_config *)dev->config;
	struct pl011_data *data = (struct pl011_data *)dev->data;
	volatile struct pl011_regs *uart = get_uart(dev);
	int ret;
	uint32_t lcrh;

	if (!data->sbsa) {
		uart->dmacr = 0U;
		uart->cr &= ~PL011_CR_SIREN;
		uart->cr |= PL011_CR_RXE | PL011_CR_TXE;
	}

	lcrh = uart->lcr_h & ~(PL011_LCRH_FORMAT_MASK | PL011_LCRH_STP2);
	lcrh |= PL011_LCRH_WLEN_8;
	uart->lcr_h = lcrh;

	if (config->sys_clk != 0U) {
		pl011_set_baudrate(dev, data->baud_rate);
	}

	uart->cr |= PL011_CR_UARTEN;

	return 0;
}
```
The function definition will be appended by the build system, so do NOT include or rewrite it; forward-declare it ABOVE that point using the exact same `static` qualifier shown in the source above (a forward declaration using `extern` or `extern "C"` instead of `static` will fail to link against the appended definition), and provide every mock, type, struct and macro it needs. These functions are static, so they must be in the same translation unit, and appending is what makes a forward declaration plus a later definition work.
You can #include "zephyr-src/drivers/serial/uart_pl011_registers.h" (or, equivalently, #include <zephyr/drivers/serial/uart_pl011_registers.h> — both paths resolve to the identical real header) to get the hardware register structs — the build system already provides `struct device` (fields: `config`, `data`, `mmio_base`) and the `BIT`, `GENMASK`, and `DEVICE_MMIO_GET` macros that header needs, via <zephyr/device.h>. Do NOT redefine `struct device`, `BIT`, `GENMASK`, or `DEVICE_MMIO_GET` yourself — that causes a redefinition error. Before calling the target function, set `dev->mmio_base` to point at your mock `struct pl011_regs` instance (this is what `get_uart()`/`DEVICE_MMIO_GET` reads). Use `dev->data` for driver runtime state (e.g. `struct pl011_data`) and `dev->config` for driver config (e.g. `struct pl011_config`) only if the target function needs them.
This target also calls `pl011_set_baudrate(dev, baudrate)` — an internal driver function NOT provided by any header; you must forward-declare and mock it yourself (matching exactly this two-argument signature — a no-op body is fine for fuzzing purposes).
Include all necessary standard headers. Do NOT use `FuzzedDataProvider.h` — it is not guaranteed to be available in this build; read bytes directly from `data`/`size` instead."""
}

# --- Portability fix (Oct 1 2026, independent audit) ---
# The original script hardcoded a `wsl` subprocess wrapper and Windows-style
# paths (D:/, /mnt/d/) into evaluate_harness(), meaning it could only ever
# run on the original author's specific Windows+WSL machine. That's why no
# raw trial log for this experiment survived in the repo: the script itself
# was never portable enough to re-run anywhere else. Fixed below to call
# clang++ directly with OS-native paths, with a clear error if clang++ with
# libFuzzer+ASan support isn't on PATH. Nothing about the experimental
# design (prompts, temperature, seed logic, N_TRIALS, success criteria, Arm
# A/B branching) was changed -- only the mechanics of invoking the compiler.
#
# Run from the repo root as:
#   python3 run_ablation_b_v2.py --model qwen2.5-coder:7b
#   python3 run_ablation_b_v2.py --model qwen2.5-coder:14b
# (run once per model; results are written to a model-specific file so a
# 7b run and a 14b run never silently overwrite or merge into each other --
# the original script's single hardcoded "ablation_b_v2_results.json" name
# didn't guard against that.)

# Oct 15 2026 changes (before any results existed for this ablation):
#  1. Cloud backend: --backend openrouter (+ --provider/--budget-usd/--max-tokens/--reasoning),
#     same mechanics as run_ablation_g.py (spend guard, JSONL call ledger, DSML cut, provider
#     pin; results/ledger/log files carry the provider in their names).
#  2. Retry-loop fix: the first retry used to receive the bare original prompt (the attempt-1
#     error was computed but never passed in), so both arms got a free blind resample and Arm A's
#     lint never saw the attempt-1 harness. Retry 2 now carries the attempt-1 feedback, as in
#     Ablation G's loop.
#  3. Lint filter: clang-tidy only runs its analyzers on code that compiles; on a harness with a
#     compile error it re-prints the compiler error and nothing else. Only warnings located in
#     harness.cpp are now passed as lint feedback, so Arm A differs from Arm B only when
#     clang-tidy has something the compiler error does not already say; otherwise Arm A falls
#     back to compiler-only for that round. `arm_a_lint_used_on_any_retry` therefore measures how
#     often lint had any effect at all, which bounds what this ablation can show.

_parser = argparse.ArgumentParser()
_parser.add_argument("--model", default="qwen2.5-coder:14b", help="Exact ollama model tag, e.g. qwen2.5-coder:7b")
_parser.add_argument("--trials", type=int, default=20, help="Trials per target (default 20, matching B v2's own recommended n=20-30/target/model for real statistical power)")
_parser.add_argument("--target", default=None, choices=list(TARGETS.keys()), help="Run only this one target instead of all 5 (for smoke-testing a scaffolding change cheaply)")
_parser.add_argument("--analyze-only", action="store_true", help="Skip running trials; just (re)compute the McNemar analysis from the existing results file and print it")
_parser.add_argument("--backend", default="ollama", choices=["ollama", "openrouter"], help="ollama (default, local model, unchanged) or openrouter (cloud model; needs OPENROUTER_API_KEY in the environment)")
_parser.add_argument("--provider", default=None, help="openrouter only: pin ONE upstream provider by name and disable fallbacks")
_parser.add_argument("--budget-usd", type=float, default=1.0, help="openrouter only: hard spending ceiling in USD; the run stops cleanly (progress saved, resumable) before a call that would start past it")
_parser.add_argument("--price-in", type=float, default=0.30, help="openrouter only: USD per 1M input tokens, used only when a response carries no cost")
_parser.add_argument("--price-out", type=float, default=1.20, help="openrouter only: USD per 1M output tokens (see --price-in)")
_parser.add_argument("--max-tokens", type=int, default=4096, help="openrouter only: max output tokens per call")
_parser.add_argument("--reasoning", default="off", choices=["off", "default"], help="openrouter only: 'off' asks the provider to disable hidden reasoning")
_parser.add_argument("--mock-headers", default="v1", choices=["v1", "ext"], help="v1 = the frozen mock Zephyr headers in harnesses/include (original behavior). ext = harnesses/include_ext placed first on the include path, exactly as in run_ablation_g.py. A labeled variant: results go to separate _mockext files.")
_parser.add_argument("--repair-context", default="error", choices=["error", "code"], help="error = the retry prompt carries only the latest error (original behavior). code = it also carries the previous attempt's code, exactly as in run_ablation_g.py. A labeled variant: results go to separate _ctxcode files.")
_args, _ = _parser.parse_known_args()

OLLAMA_MODEL = _args.model
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
N_TRIALS = _args.trials
if _args.target:
    TARGETS = {_args.target: TARGETS[_args.target]}
_MODEL_SLUG = OLLAMA_MODEL.replace(":", "_").replace("/", "_")
if _args.mock_headers != "v1":
    _MODEL_SLUG += "_mock" + _args.mock_headers
if _args.repair_context != "error":
    _MODEL_SLUG += "_ctx" + _args.repair_context
if _args.backend == "openrouter" and _args.provider:
    _MODEL_SLUG += "_prov-" + "".join(c if c.isalnum() else "-" for c in _args.provider)
if _args.target:
    _MODEL_SLUG += f"_smoketest_{_args.target}"
RESULTS_FILE = f"ablation_e_lint_results_{_MODEL_SLUG}.json"

CLANG = shutil.which("clang++")
CLANG_TIDY = shutil.which("clang-tidy")
if not CLANG and not _args.analyze_only:
    sys.exit("clang++ not found on PATH. Install LLVM/clang (with libFuzzer + AddressSanitizer support) before running this script.")
if not CLANG_TIDY and not _args.analyze_only:
    sys.exit("clang-tidy not found on PATH. Install it (usually ships alongside clang/LLVM) before running this script -- it's the static-analysis tool this ablation is specifically about.")

def _include_flags(repo_root):
    """-I flags shared by the compile step and clang-tidy, so lint sees what the compiler sees.
    With --mock-headers ext, harnesses/include_ext comes first (same order as run_ablation_g.py)."""
    flags = []
    if _args.mock_headers == "ext":
        flags.append("-I" + os.path.join(repo_root, "harnesses", "include_ext"))
    flags += ["-I" + os.path.join(repo_root, "harnesses", "include"), "-I" + repo_root]
    return flags


def call_ollama(prompt, seed):
    data = {
        "model": OLLAMA_MODEL,
        "prompt": "You are a firmware fuzzing expert. Return ONLY valid C++ code for a libFuzzer harness. No markdown formatting.\n\n" + prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "seed": seed,
            "num_predict": 1024
        }
    }
    try:
        import requests
        resp = requests.post(OLLAMA_URL, json=data)
        if resp.status_code == 200:
            text = resp.json()["response"]
            return text.replace('```cpp', '').replace('```', '').strip()
    except Exception as e:
        print(f"Ollama API Error: {e}")
    return None

class BudgetExceeded(Exception):
    pass

_SPENT_USD = 0.0
_CALLS_MADE = 0
_API_FAILED = [0]  # calls that returned no usable code; counted separately, never as model failures


def call_openrouter(prompt, seed):
    """One chat-completion call through OpenRouter (same mechanics as run_ablation_g.py).
    The key is read from the environment and never printed or written. Every call is
    appended to a JSONL ledger (model, serving provider, tokens, cost)."""
    global _SPENT_USD, _CALLS_MADE
    if _SPENT_USD >= _args.budget_usd:
        raise BudgetExceeded(f"spent ${_SPENT_USD:.4f} of ${_args.budget_usd:.2f}")
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        sys.exit("OPENROUTER_API_KEY is not set in this terminal. Set it and re-run.")
    body = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": "You are a firmware fuzzing expert. Return ONLY valid C++ code for a libFuzzer harness. No markdown formatting."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "seed": seed,
        "max_tokens": _args.max_tokens,
        "usage": {"include": True},
    }
    if _args.reasoning == "off":
        body["reasoning"] = {"enabled": False}
    if _args.provider:
        body["provider"] = {"order": [_args.provider], "allow_fallbacks": False}
    base = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    try:
        import requests
        resp = requests.post(base + "/chat/completions",
                             headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                             json=body, timeout=180)
        if resp.status_code != 200:
            print(f"OpenRouter HTTP {resp.status_code}: {resp.text[:300]}")
            return None
        data = resp.json()
        usage = data.get("usage") or {}
        tin = usage.get("prompt_tokens") or 0
        tout = usage.get("completion_tokens") or 0
        cost = usage.get("cost")
        if cost is None:
            cost = tin * _args.price_in / 1e6 + tout * _args.price_out / 1e6
        _SPENT_USD += float(cost)
        _CALLS_MADE += 1
        choice = data["choices"][0]
        finish = choice.get("finish_reason")
        rtoks = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
        with open(f"ablation_e_lint_calls_{_MODEL_SLUG}.jsonl", "a") as f:
            f.write(json.dumps({
                "time": datetime.now().isoformat(),
                "requested_model": OLLAMA_MODEL,
                "served_model": data.get("model"),
                "provider": data.get("provider"),
                "prompt_tokens": tin, "completion_tokens": tout,
                "reasoning_tokens": rtoks, "finish_reason": finish,
                "reasoning_mode": _args.reasoning,
                "cost_usd": float(cost), "spent_total_usd": round(_SPENT_USD, 6),
            }) + "\n")
        text = choice["message"].get("content") or ""
        text = text.replace('```cpp', '').replace('```', '').strip()
        # Some providers leak DeepSeek tool-call control tokens after the code;
        # they are transport noise, not model-written C++. Cut at the first one.
        _dsml = text.find("<\uff5cDSML\uff5c")
        if _dsml == -1:
            _dsml = text.find("</\uff5cDSML\uff5c")
        if _dsml != -1:
            print(f"    (provider leaked DSML control tokens at char {_dsml}; truncated)")
            text = text[:_dsml].rstrip()
        if not text:
            print(f"    (empty reply from model; finish_reason={finish}, completion_tokens={tout}, reasoning_tokens={rtoks})")
            return None
        return text
    except BudgetExceeded:
        raise
    except Exception as e:
        print(f"OpenRouter API Error: {e}")
        return None


def call_model(prompt, seed):
    if _args.backend == "openrouter":
        return call_openrouter(prompt, seed)
    return call_ollama(prompt, seed)


def write_log(path, content):
    with open(path, 'w') as f:
        f.write(content)

def evaluate_harness(harness_code, dir_path, target_func):
    cpp_file = os.path.join(dir_path, "harness.cpp")
    
    # Extract source from TARGETS
    prompt = TARGETS[target_func]
    import re
    match = re.search(r'```c\n(.*?)```', prompt, re.DOTALL)
    if match:
        target_source = match.group(1)
    else:
        target_source = ""
        
    # Check for redefinition (if LLM defined it anyway)
    # A genuine compile error will occur because we append it anyway
    full_code = harness_code + "\n\n// === APPENDED TARGET FUNCTION ===\n" + target_source
    
    write_log(cpp_file, full_code)
    
    # 4. Source Integrity (now we check if the LLM included its own copy BEFORE our append, by checking original harness_code)
    if target_func not in harness_code:
        return False, "Target function missing from generated code (Trivial)", "Target function missing"
        
    # 1. Compile (portable: plain clang++, OS-native absolute include paths, no wsl wrapper)
    repo_root = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
    res_compile = subprocess.run(
        [CLANG, "-fsanitize=fuzzer,address", "-O1", "-fno-inline"]
        + _include_flags(repo_root)
        + ["harness.cpp", "-o", "fuzz_bin"],
        cwd=dir_path, capture_output=True, text=True
    )
    if res_compile.returncode != 0:
        return False, "Compiler Error", res_compile.stderr

    # Bug fix (Oct 2026, Ablation B v2 full-sweep crash): this used to be
    # os.path.join(dir_path, "fuzz_bin"), i.e. an already-dir_path-prefixed
    # path, passed to subprocess.run with cwd=dir_path ALSO set. Since the
    # path contains a slash, the OS resolves it relative to the new cwd,
    # not the original one -- so it looked for dir_path/dir_path/fuzz_bin,
    # which never existed, and crashed with FileNotFoundError. This had
    # been latent since before this experiment started; it only fired now
    # because nothing had ever compiled successfully before this run.
    # Fix: reference the binary relative to dir_path, since cwd already is
    # dir_path.
    fuzz_bin_name = "./fuzz_bin" + (".exe" if platform.system() == "Windows" else "")
    try:
        res_run = subprocess.run(
            [fuzz_bin_name, "-max_total_time=1", "-timeout=2"],
            cwd=dir_path, capture_output=True, text=True, timeout=5
        )
        out_stderr = res_run.stderr
        ret_code = res_run.returncode
    except subprocess.TimeoutExpired as e:
        try:
            subprocess.run(["pkill", "-9", "-f", "fuzz_bin"])
        except Exception:
            pass
        out_stderr = e.stderr if e.stderr else (e.output.decode('utf-8', errors='ignore') if e.output else "")
        ret_code = 77 # Libfuzzer timeout exit code is usually 77, we'll handle it below
        out_stderr += "\n== ALARM: libFuzzer timeout ==\n"
        
    is_timeout = ("ALARM: libFuzzer timeout" in out_stderr or "timeout after" in out_stderr.lower())
    
    if ret_code != 0 and ret_code != 77:
        if "AddressSanitizer" in out_stderr or "UndefinedBehaviorSanitizer" in out_stderr or "LeakSanitizer" in out_stderr:
            return False, "Sanitizer Error", out_stderr
        if not is_timeout and "Done" not in out_stderr:
            return False, "Runtime Crash", out_stderr
            
    # Check edges
    edges = 0
    for line in out_stderr.split('\n'):
        if "stat::edges:" in line or "cov: " in line:
            try:
                if "cov: " in line:
                    edges = max(edges, int(line.split("cov: ")[1].split()[0]))
                else:
                    edges = max(edges, int(line.split("stat::edges:")[1].strip()))
            except:
                pass
                
    if is_timeout:
        # A libFuzzer timeout counts as success only if the stack trace shows the hang inside the target function,
        # or coverage exceeded the 3-edge threshold before the hang.
        hang_in_target = target_func in out_stderr
        if not hang_in_target and edges <= 3:
            return False, "Timeout outside target func with Trivial Coverage", out_stderr
        return True, "Success (Timeout in target / adequate coverage)", out_stderr
        
    if edges <= 3:
        return False, "Trivial Coverage (<=3 edges)", out_stderr

    return True, "Success", out_stderr


def run_clang_tidy(dir_path):
    """Runs clang-tidy against the harness.cpp already written into dir_path
    by evaluate_harness() (it writes the file whether or not the compile
    succeeded, so this can run on code that failed to compile too -- that's
    exactly the case Arm A's retry feedback needs it for).

    Uses clang-tidy's DEFAULT check set (no -checks= filter) and the same
    -I include paths evaluate_harness() compiles with, so it sees the same
    mocks/headers. Returns (warning_count, tidy_output_text, tidy_ran_ok).

    tidy_ran_ok=False means clang-tidy itself couldn't produce useful
    output (e.g. the code is malformed enough that even clang-tidy's more
    tolerant parser gives up) -- the caller falls back to compiler-only
    feedback for that retry round rather than silently feeding an empty
    or misleading "lint" section into the prompt.
    """
    cpp_file = os.path.join(dir_path, "harness.cpp")
    if not os.path.exists(cpp_file):
        return 0, "", False

    repo_root = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
    try:
        res = subprocess.run(
            [CLANG_TIDY, "harness.cpp", "--"] + _include_flags(repo_root),
            cwd=dir_path, capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        return 0, "", False
    except Exception as e:
        return 0, f"clang-tidy invocation failed: {e}", False

    output = res.stdout + res.stderr

    if "clang-tidy" in output.lower() and ("error reading" in output.lower() or "unable to handle compilation" in output.lower()):
        return 0, output, False

    # Oct 15 2026 fix: keep ONLY real static-analysis warnings located in the
    # harness itself. Previously every ": error:" line was counted and pasted
    # into the prompt too, but on a harness that fails to compile clang-tidy
    # simply re-prints the compiler's own errors, so Arm A's "lint" feedback
    # was mostly a second copy of Arm B's feedback plus warnings from repo
    # headers. Now the lint text is empty (and Arm A falls back to
    # compiler-only for that round, exactly like Arm B) unless clang-tidy found
    # something the compiler error does not already say.
    kept, warning_count = _filter_tidy_warnings(output)
    return warning_count, kept, True


_DIAG_RE = re.compile(r"^(\S+?):(\d+):(\d+): (warning|error|note): ")


def _filter_tidy_warnings(output):
    """Return (text, count): the clang-tidy diagnostic blocks of kind 'warning'
    whose location is harness.cpp (with their attached notes and code context),
    and how many such warnings there are. Error blocks, warnings in other files
    and summary lines ("N warnings generated.", "Suppressed ...") are dropped."""
    blocks, cur, cur_keep = [], [], False
    for line in output.split("\n"):
        m = _DIAG_RE.match(line)
        if m:
            kind = m.group(4)
            if kind == "note":
                if cur:
                    cur.append(line)      # attach the note to the current block
                continue
            if cur and cur_keep:
                blocks.append("\n".join(cur))
            cur = [line]
            cur_keep = (kind == "warning" and os.path.basename(m.group(1)) == "harness.cpp")
        elif cur:
            if re.match(r"^\d+ (warnings?|errors?) generated|^Suppressed |^Use -header-filter|^Error while processing", line):
                continue
            cur.append(line)
    if cur and cur_keep:
        blocks.append("\n".join(cur))
    return "\n".join(blocks), len(blocks)


def _feedback_text(err, lint_dir, use_lint, prev_code):
    """Prompt suffix for one retry round: the real compiler/runtime error, plus (Arm A
    only) clang-tidy warnings on the failed harness in lint_dir when it finds any.
    With --repair-context code the previous attempt's code is included first (same text
    as run_ablation_g.py), identically for both arms.
    Returns (suffix, lint_added, tidy_parsed): lint_added = a non-empty lint section went
    into the prompt; tidy_parsed = clang-tidy could analyze the harness at all."""
    if _args.repair_context == "code":
        fb = (f"\n\nYour previous code:\n```cpp\n{prev_code}\n```\n\n"
              f"It failed with the following error:\n```\n{err}\n```")
        tail = "\nFix it and output the complete corrected C++ only."
    else:
        fb = f"\n\nYour previous code failed with the following error:\n```\n{err}\n```"
        tail = "\nPlease try again. Output ONLY C++."
    lint_added = False
    tidy_parsed = False
    if use_lint:
        warn_count, tidy_output, tidy_ok = run_clang_tidy(lint_dir)
        tidy_parsed = tidy_ok
        if tidy_ok and warn_count > 0:
            lint_added = True
            fb += (
                f"\n\nAdditionally, static analysis (clang-tidy) reported "
                f"{warn_count} warning(s):\n```\n{tidy_output}\n```"
            )
        # tidy_ok=False (harness too broken to parse) or no warnings: falls back to
        # compiler-only feedback for this round, same as the other arm.
    return fb + tail, lint_added, tidy_parsed


def _retry_loop(prompt, seed, loop_dir, target, use_lint, first_err, first_dir, first_code):
    """Shared retry mechanics for both arms: up to 4 more attempts (5 total,
    attempt 1 already having failed), feeding back the real compiler error
    plus, when use_lint=True and clang-tidy can parse the failed harness,
    its static-analysis warnings too. Returns
    (success, total_attempts, lint_used_on_any_retry, rounds) where rounds counts the
    feedback rounds generated: {"total", "tidy_parsed", "with_lint"} (Arm A only; zeros for B)."""
    success = False
    attempts = 1
    rounds = {"total": 0, "tidy_parsed": 0, "with_lint": 0}

    def _round(err, d, code):
        fb, added, parsed = _feedback_text(err, d, use_lint, code)
        rounds["total"] += 1
        rounds["tidy_parsed"] += parsed
        rounds["with_lint"] += added
        return prompt + fb, added

    # Oct 15 2026 fix: the first retry used to be sent the bare original prompt (the
    # attempt-1 error was computed but never passed in), so both arms silently got a
    # free blind resample and Arm A's lint was never applied to the attempt-1 harness.
    # Now retry 2 carries the attempt-1 feedback, matching Ablation G's loop.
    cur_prompt, lint_used = _round(first_err, first_dir, first_code)

    for retry in range(2, 6):
        attempts = retry
        retry_code = call_model(cur_prompt, seed + retry)
        if not retry_code:
            _API_FAILED[0] += 1
            continue
        s, ft, eo = evaluate_harness(retry_code, loop_dir, target)
        if s:
            success = True
            break

        cur_prompt, added = _round(eo, loop_dir, retry_code)
        lint_used = lint_used or added

    return success, attempts, lint_used, rounds


def run_experiment():
    print(f"=== Ablation E (Work Plan item 5): Static-Analysis-Lint Feedback ===")
    print(f"Model: {OLLAMA_MODEL}")
    print(f"Temperature: 0.7")
    print(f"Trials per target: {N_TRIALS}")
    print(f"Time: {datetime.now().isoformat()}")

    results = {}
    base_dir = f"ablation_e_lint_logs_{_MODEL_SLUG}"  # model-specific dir: a 7b and 14b run must never share/overwrite raw trial files
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)

    results_file = RESULTS_FILE
    if os.path.exists(results_file):
        with open(results_file, "r") as f:
            results = json.load(f)

    for target, prompt in TARGETS.items():
        print(f"\n--- Target: {target} ---")
        if target not in results:
            results[target] = []

        target_dir = os.path.join(base_dir, target)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        completed_trials = {t["trial"] for t in results[target]}

        for trial in range(1, N_TRIALS + 1):
            if trial in completed_trials:
                print(f"  Trial {trial} already completed. Skipping.")
                continue
            seed = int(time.time() * 1000) % 10000 + trial
            print(f"  Trial {trial} (Seed {seed})...")

            trial_dir = os.path.join(target_dir, f"trial_{trial}")
            os.makedirs(trial_dir, exist_ok=True)

            # Attempt 1 is shared by both arms -- generated once; if it
            # already succeeds, both arms trivially agree (concordant
            # success) and no retries/branching are needed.
            code = call_model(prompt, seed)
            if not code:
                print("    API Failed.")
                _API_FAILED[0] += 1
                continue

            attempt1_success, fail_type, err_out = evaluate_harness(code, trial_dir, target)

            if attempt1_success:
                print("    -> Attempt 1 Success (both arms agree: SUCCESS)")
                results[target].append({
                    "trial": trial,
                    "arm_a_lint_success": True,
                    "arm_b_compiler_only_success": True,
                    "arm_a_attempts": 1,
                    "arm_b_attempts": 1,
                    "arm_a_lint_used_on_any_retry": False,
                    "fail_type_attempt1": None
                })
                with open(RESULTS_FILE, "w") as f:
                    json.dump(results, f, indent=2)
                continue

            print(f"    -> Attempt 1 Failed ({fail_type}). Branching into independent Arm A (lint+compiler) and Arm B (compiler-only) retry loops...")

            arm_a_dir = os.path.join(trial_dir, "arm_a_lint")
            arm_b_dir = os.path.join(trial_dir, "arm_b_compiler_only")
            os.makedirs(arm_a_dir, exist_ok=True)
            os.makedirs(arm_b_dir, exist_ok=True)

            # Arm A: lint + compiler feedback. Offset seed base so the two
            # arms' retry sequences don't draw identical generations off the
            # same seed stream.
            arm_a_success, arm_a_attempts, arm_a_lint_used, arm_a_rounds = _retry_loop(
                prompt, seed, arm_a_dir, target, use_lint=True,
                first_err=err_out, first_dir=trial_dir, first_code=code
            )
            # Arm B: compiler-only feedback -- the existing, already-proven
            # real-feedback condition (identical mechanism to Ablation B
            # v2's Arm A / item 8's oracle-present loop), unmodified. Offset
            # seed so it doesn't share Arm A's exact generations.
            arm_b_success, arm_b_attempts, _, _ = _retry_loop(
                prompt, seed + 100, arm_b_dir, target, use_lint=False,
                first_err=err_out, first_dir=trial_dir, first_code=code
            )

            print(f"      Arm A (lint+compiler): {'SUCCESS' if arm_a_success else 'FAIL'} in {arm_a_attempts} total attempts (lint used on a retry: {arm_a_lint_used})")
            print(f"      Arm B (compiler-only): {'SUCCESS' if arm_b_success else 'FAIL'} in {arm_b_attempts} total attempts")

            results[target].append({
                "trial": trial,
                "arm_a_lint_success": arm_a_success,
                "arm_b_compiler_only_success": arm_b_success,
                "arm_a_attempts": arm_a_attempts,
                "arm_b_attempts": arm_b_attempts,
                "arm_a_lint_used_on_any_retry": arm_a_lint_used,
                "arm_a_feedback_rounds": arm_a_rounds["total"],
                "arm_a_rounds_tidy_parsed": arm_a_rounds["tidy_parsed"],
                "arm_a_rounds_with_lint": arm_a_rounds["with_lint"],
                "fail_type_attempt1": fail_type
            })

            with open(RESULTS_FILE, "w") as f:
                json.dump(results, f, indent=2)

    print("\nExperiment Complete.")
    analyze_results(results)


def analyze_results(results=None):
    """McNemar's exact (sign) test on the Arm A (lint+compiler) vs. Arm B
    (compiler-only) paired outcomes. Unlike item 8/Ablation G's nested
    design, both arms branch independently from the same attempt-1 failure
    (matching Ablation B v2's original real-vs-generic structure), so
    BOTH discordant directions (b: A succeeds, B fails; c: B succeeds, A
    fails) are structurally possible here -- neither is asserted to be
    zero."""
    if results is None:
        if not os.path.exists(RESULTS_FILE):
            print(f"No results file found at {RESULTS_FILE}; nothing to analyze.")
            return
        with open(RESULTS_FILE, "r") as f:
            results = json.load(f)

    all_trials = [t for trials in results.values() for t in trials]
    n = len(all_trials)
    if n == 0:
        print("No completed trials to analyze.")
        return

    both_success = sum(1 for t in all_trials if t["arm_a_lint_success"] and t["arm_b_compiler_only_success"])
    both_fail = sum(1 for t in all_trials if not t["arm_a_lint_success"] and not t["arm_b_compiler_only_success"])
    b_a_only = sum(1 for t in all_trials if t["arm_a_lint_success"] and not t["arm_b_compiler_only_success"])
    c_b_only = sum(1 for t in all_trials if not t["arm_a_lint_success"] and t["arm_b_compiler_only_success"])

    arm_a_rate = (both_success + b_a_only) / n
    arm_b_rate = (both_success + c_b_only) / n
    lint_actually_used = sum(1 for t in all_trials if t.get("arm_a_lint_used_on_any_retry"))

    print("\n=== Ablation E Analysis ===")
    print(f"Total trials: {n}")
    print(f"Both arms succeed (concordant success): {both_success}")
    print(f"Both arms fail (concordant failure):    {both_fail}")
    print(f"Arm A succeeded, Arm B failed (b):       {b_a_only}")
    print(f"Arm B succeeded, Arm A failed (c):       {c_b_only}")
    print(f"Trials where Arm A actually got a non-empty lint warning on a retry: {lint_actually_used}")
    rounds = sum(t.get("arm_a_feedback_rounds", 0) for t in all_trials)
    if rounds:
        parsed = sum(t.get("arm_a_rounds_tidy_parsed", 0) for t in all_trials)
        withl = sum(t.get("arm_a_rounds_with_lint", 0) for t in all_trials)
        print(f"Arm A feedback rounds: {rounds} | clang-tidy could analyze the harness in {parsed} ({parsed/rounds:.0%}) | "
              f"round carried a non-empty lint section in {withl} ({withl/rounds:.0%})")
    print(f"Arm A (lint+compiler) success rate:  {arm_a_rate:.1%} ({both_success + b_a_only}/{n})")
    print(f"Arm B (compiler-only) success rate:  {arm_b_rate:.1%} ({both_success + c_b_only}/{n})")

    # McNemar's exact (sign) test, two-sided, on the discordant pairs only
    b, c = b_a_only, c_b_only
    discordant = b + c
    if discordant == 0:
        print("McNemar's exact test: 0 discordant pairs -- no basis to distinguish Arm A from Arm B in this sample.")
    else:
        k = min(b, c)
        # Two-sided exact binomial p-value under H0: p=0.5 for each discordant pair's direction
        p_value = 0.0
        for i in range(0, k + 1):
            p_value += math.comb(discordant, i) * (0.5 ** discordant)
        p_value = min(1.0, 2 * p_value) if b != c else 1.0
        print(f"McNemar's exact test: b={b}, c={c}, n_discordant={discordant}, two-sided exact p={p_value:.4f}")
        if p_value < 0.05:
            winner = "Arm A (lint+compiler)" if b > c else "Arm B (compiler-only)"
            print(f"  -> Statistically significant at alpha=0.05: {winner} measurably outperforms the other arm on this sample.")
        else:
            print("  -> Not statistically significant at alpha=0.05.")


if __name__ == "__main__":
    if _args.analyze_only:
        analyze_results()
        sys.exit(0)
    try:
        run_experiment()
    except BudgetExceeded as e:
        print(f"\nSTOPPED: budget guard reached ({e}). Progress is saved; re-run the same command to resume with a higher --budget-usd if you want to continue.")
        analyze_results()
    if _args.backend == "openrouter":
        print(f"Spend this session: ${_SPENT_USD:.4f} over {_CALLS_MADE} calls (budget ${_args.budget_usd:.2f}); calls with no usable code (excluded from rates): {_API_FAILED[0]}")
