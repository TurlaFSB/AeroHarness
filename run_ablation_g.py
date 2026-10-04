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

import math

import os, sys, time, json, subprocess, shutil, argparse, platform
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

_parser = argparse.ArgumentParser()
_parser.add_argument("--model", default="qwen2.5-coder:14b", help="Exact ollama model tag, e.g. qwen2.5-coder:7b")
_parser.add_argument("--trials", type=int, default=20, help="Trials per target (default 20, matching B v2's own recommended n=20-30/target/model for real statistical power)")
_parser.add_argument("--target", default=None, choices=list(TARGETS.keys()), help="Run only this one target instead of all 5 (for smoke-testing a scaffolding change cheaply)")
_parser.add_argument("--analyze-only", action="store_true", help="Skip running trials; just (re)compute the McNemar analysis from the existing results file and print it")
_args, _ = _parser.parse_known_args()

OLLAMA_MODEL = _args.model
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
N_TRIALS = _args.trials
if _args.target:
    TARGETS = {_args.target: TARGETS[_args.target]}
_MODEL_SLUG = OLLAMA_MODEL.replace(":", "_").replace("/", "_")
if _args.target:
    _MODEL_SLUG += f"_smoketest_{_args.target}"
RESULTS_FILE = f"ablation_g_results_{_MODEL_SLUG}.json"

CLANG = shutil.which("clang++")
if not CLANG and not _args.analyze_only:
    sys.exit("clang++ not found on PATH. Install LLVM/clang (with libFuzzer + AddressSanitizer support) before running this script.")

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

def write_log(path, content):
    with open(path, 'w') as f:
        f.write(content)

def evaluate_harness(harness_code, dir_path, target_func, attempt=None):
    # Provenance fix (Oct 4 2026): every retry in the oracle-present loop used
    # to write to the same fixed "harness.cpp" path, so each new attempt
    # silently overwrote the previous one -- once a trial finished, only the
    # LAST attempt's code and error text survived on disk; every intermediate
    # failing attempt (and its real compiler/runtime error, which was never
    # printed to console either) was unrecoverable. This made any after-the-
    # fact audit of "did the loop really fix a real error" impossible for
    # already-completed trials. Fixed by writing each attempt to its own
    # numbered file when an attempt number is given (the retry loop below now
    # passes one), while still keeping a stable "harness.cpp"/"result.json" at
    # the trial dir's root pointing at the latest attempt, for any tooling
    # that expects the old fixed filename.
    suffix = f"_attempt{attempt}" if attempt is not None else ""
    cpp_file = os.path.join(dir_path, f"harness{suffix}.cpp")
    meta_file = os.path.join(dir_path, f"harness{suffix}_result.json")
    stable_cpp_file = os.path.join(dir_path, "harness.cpp")
    stable_meta_file = os.path.join(dir_path, "harness_result.json")

    def _finish(success, fail_type, err_text):
        meta = {
            "attempt": attempt,
            "success": success,
            "fail_type": fail_type,
            "error_text": err_text,
        }
        with open(meta_file, "w") as f:
            json.dump(meta, f, indent=2)
        with open(stable_meta_file, "w") as f:
            json.dump(meta, f, indent=2)
        return success, fail_type, err_text

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
    write_log(stable_cpp_file, full_code)

    # 4. Source Integrity (now we check if the LLM included its own copy BEFORE our append, by checking original harness_code)
    if target_func not in harness_code:
        return _finish(False, "Target function missing from generated code (Trivial)", "Target function missing")

    # 1. Compile (portable: plain clang++, OS-native absolute include paths, no wsl wrapper)
    repo_root = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))
    # cwd is dir_path below, so the source filename must be given relative to
    # dir_path (not dir_path-prefixed again) -- see the existing comment a few
    # lines down about the exact same double-prefixing bug in the run step.
    res_compile = subprocess.run(
        [CLANG, "-fsanitize=fuzzer,address", "-O1", "-fno-inline",
         "-I" + os.path.join(repo_root, "harnesses", "include"),
         "-I" + repo_root,
         f"harness{suffix}.cpp", "-o", "fuzz_bin"],
        cwd=dir_path, capture_output=True, text=True
    )
    if res_compile.returncode != 0:
        return _finish(False, "Compiler Error", res_compile.stdout + res_compile.stderr)

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
            return _finish(False, "Sanitizer Error", out_stderr)
        if not is_timeout and "Done" not in out_stderr:
            return _finish(False, "Runtime Crash", out_stderr)
            
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
            return _finish(False, "Timeout outside target func with Trivial Coverage", out_stderr)
        return _finish(True, "Success (Timeout in target / adequate coverage)", out_stderr)

    if edges <= 3:
        return _finish(False, "Trivial Coverage (<=3 edges)", out_stderr)

    return _finish(True, "Success", out_stderr)

def run_experiment():
    print(f"=== Ablation G (Work Plan item 8): Compiler-Oracle-Presence ===")
    print(f"Model: {OLLAMA_MODEL}")
    print(f"Temperature: 0.7")
    print(f"Trials per target: {N_TRIALS}")
    print(f"Time: {datetime.now().isoformat()}")

    results = {}
    base_dir = f"ablation_g_logs_{_MODEL_SLUG}"  # model-specific dir: a 7b and 14b run must never share/overwrite raw trial files
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

            # Attempt 1 -- this IS the "oracle absent" condition: generated
            # once, compiled/run only to RECORD the outcome, never fed back.
            code = call_ollama(prompt, seed)
            if not code:
                print("    API Failed.")
                continue

            oracle_absent_success, fail_type, err_out = evaluate_harness(code, trial_dir, target, attempt=1)

            if oracle_absent_success:
                # Oracle-present trivially agrees (attempt 1 is its first attempt
                # too) -- a concordant success pair, no retries needed.
                print("    -> Attempt 1 Success (oracle-absent AND oracle-present agree: SUCCESS)")
                results[target].append({
                    "trial": trial,
                    "oracle_absent_success": True,
                    "oracle_present_success": True,
                    "oracle_present_attempts": 1,
                    "fail_type_attempt1": None
                })
                # Write partial results
                with open(RESULTS_FILE, "w") as f:
                    json.dump(results, f, indent=2)
                continue

            print(f"    -> Attempt 1 Failed ({fail_type}). oracle-absent=FAIL. Continuing with real-feedback retries for oracle-present...")

            loop_dir = os.path.join(trial_dir, "oracle_present_loop")
            os.makedirs(loop_dir, exist_ok=True)

            # Oracle-present condition: up to 4 more attempts (5 total), each
            # with the real compiler diagnostic fed back -- identical
            # mechanism to Ablation B v2's Arm A / AeroHarness's real Stage 6
            # self-repair loop. There is no Arm B here; this ablation isn't
            # asking about feedback type, only whether a loop exists at all.
            oracle_present_success = False
            oracle_present_attempts = 1
            cur_prompt = prompt + f"\n\nYour previous code failed with the following error:\n```\n{err_out}\n```\nPlease try again. Output ONLY C++."

            for retry in range(2, 6):
                oracle_present_attempts = retry
                retry_code = call_ollama(cur_prompt, seed + retry)
                if not retry_code: continue
                s, ft, eo = evaluate_harness(retry_code, loop_dir, target, attempt=retry)
                if s:
                    oracle_present_success = True
                    break
                cur_prompt = prompt + f"\n\nYour previous code failed with the following error:\n```\n{eo}\n```\nPlease try again. Output ONLY C++."

            print(f"      Oracle-present (loop, real feedback): {'SUCCESS' if oracle_present_success else 'FAIL'} in {oracle_present_attempts} total attempts")

            results[target].append({
                "trial": trial,
                "oracle_absent_success": False,
                "oracle_present_success": oracle_present_success,
                "oracle_present_attempts": oracle_present_attempts,
                "fail_type_attempt1": fail_type
            })

            # Write partial results
            with open(RESULTS_FILE, "w") as f:
                json.dump(results, f, indent=2)

    print("\nExperiment Complete.")
    analyze_results(results)


def analyze_results(results=None):
    """McNemar's exact (sign) test on the oracle-absent-vs-oracle-present
    paired outcomes. Because oracle-present strictly contains attempt 1 as
    its own first attempt, the only possible discordant direction is
    (absent=FAIL, present=SUCCESS) -- "the loop converted a failure into a
    success". The reverse (absent=SUCCESS, present=FAIL) is structurally
    impossible by this design and is asserted as a sanity check, not just
    assumed."""
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

    both_success = sum(1 for t in all_trials if t["oracle_absent_success"] and t["oracle_present_success"])
    both_fail = sum(1 for t in all_trials if not t["oracle_absent_success"] and not t["oracle_present_success"])
    b_loop_rescued = sum(1 for t in all_trials if not t["oracle_absent_success"] and t["oracle_present_success"])
    c_impossible = sum(1 for t in all_trials if t["oracle_absent_success"] and not t["oracle_present_success"])

    oracle_absent_rate = (both_success + c_impossible) / n
    oracle_present_rate = (both_success + b_loop_rescued) / n

    print("\n=== Ablation G Analysis ===")
    print(f"Total trials: {n}")
    print(f"Both succeed (concordant success): {both_success}")
    print(f"Both fail (concordant failure):    {both_fail}")
    print(f"Loop rescued a failure (b):         {b_loop_rescued}")
    print(f"Oracle-absent succeeded but oracle-present failed (c, should be 0 by design): {c_impossible}")
    if c_impossible != 0:
        print("  !! WARNING: c != 0 means the paired-design assumption was violated somewhere "
              "-- check the raw trial data for a bug before trusting this analysis.")
    print(f"Oracle-absent (one-shot) success rate:  {oracle_absent_rate:.1%} ({both_success + c_impossible}/{n})")
    print(f"Oracle-present (loop) success rate:     {oracle_present_rate:.1%} ({both_success + b_loop_rescued}/{n})")

    # McNemar's exact (sign) test, two-sided, on the discordant pairs only
    b, c = b_loop_rescued, c_impossible
    discordant = b + c
    if discordant == 0:
        print("McNemar's exact test: 0 discordant pairs -- no basis to distinguish oracle-present from oracle-absent in this sample.")
    else:
        k = min(b, c)
        # Two-sided exact binomial p-value under H0: p=0.5 for each discordant pair's direction
        p_value = 0.0
        for i in range(0, k + 1):
            p_value += math.comb(discordant, i) * (0.5 ** discordant)
        p_value = min(1.0, 2 * p_value) if b != c else 1.0
        print(f"McNemar's exact test: b={b}, c={c}, n_discordant={discordant}, two-sided exact p={p_value:.4f}")
        if p_value < 0.05:
            print("  -> Statistically significant at alpha=0.05: the compile-check+retry loop measurably "
                  "increases the success rate over one-shot generation on this sample.")
        else:
            print("  -> Not statistically significant at alpha=0.05.")


if __name__ == "__main__":
    if _args.analyze_only:
        analyze_results()
        sys.exit(0)
    run_experiment()
