# Ablation G: Compiler-Oracle-Presence (Work Plan Item 8)

## Research Question

Distinct from Ablation B/B v2 (which varies feedback *type* — real compiler diagnostic vs.
generic — once a retry loop already exists): this ablation varies whether a compile-check
retry loop exists **at all**, versus true one-shot generation with zero verification.

## Design

A deliberately nested/strict-superset design, not a second independent arm. The
"oracle-absent" condition is simply attempt 1's own recorded outcome — generated once,
compiled/run only to record whether it would have worked, never fed back into anything. The
"oracle-present" condition is whether *any* of up to 5 attempts succeeds, using the real
compiler diagnostic as feedback on each retry (the same mechanism Ablation B v2's Arm A uses,
and the same one AeroHarness's actual Stage 6 self-repair loop uses). Because oracle-present
by construction already includes attempt 1 as its own first attempt, oracle-absent succeeding
while oracle-present fails is structurally impossible — the only possible discordant
direction is "the loop converted a failure into a success," which is what McNemar's exact
test measures here.

5 targets (`pl011_poll_in`, `pl011_poll_out`, `pl011_isr`, `pl011_runtime_configure_internal`,
`pl011_init`), n=20 trials/target/model = 100 trials/model, matching B v2's own "Future Work"
recommendation to accumulate enough discordant pairs for real statistical power instead of
repeating its n=20-combined inconclusive result. Reuses B v2's audited `TARGETS` prompts,
`evaluate_harness()` success criteria (compile + run + >3 edges of coverage, or a timeout
hang confirmed inside the target function), and `call_ollama()` verbatim — this scaffolding
was already independently audited and fixed (5 real defects found and corrected, see
`ABLATION_B_V2.md`'s "Scaffolding Audit and Remediation" section) before any result built on
it was trusted. Script: `run_ablation_g.py`.

## Results — `qwen2.5-coder:7b` (complete, verified)

Full 100-trial run completed on Antigravity's machine (Oct 2026). All of the following was
independently re-derived by Claude from the raw per-trial JSON, not accepted from the
run's own printed summary alone — the raw results file reproduces the exact same numbers
when run through the real, committed `analyze_results()` function.

**Aggregate:**

| | Oracle-absent (one-shot) | Oracle-present (loop) |
|---|---|---|
| Success rate | 4.0% (4/100) | 14.0% (14/100) |

Both succeed (concordant): 4. Both fail (concordant): 86. Loop rescued a failure (b): 10.
Oracle-absent succeeded but oracle-present failed (c): 0 (confirms the paired-design
assumption held — structurally required to be 0, and it was).

**McNemar's exact test:** b=10, c=0, n=10 discordant pairs, two-sided exact p=0.0020.
Statistically significant at alpha=0.05.

**Per-target breakdown — this is the result that actually matters, not the aggregate:**

| Target | Oracle-absent | Oracle-present | Rescued by loop |
|---|---|---|---|
| `pl011_poll_in` | 0/20 | 4/20 | 4 |
| `pl011_poll_out` | 4/20 | 10/20 | 6 |
| `pl011_isr` | 0/20 | 0/20 | 0 |
| `pl011_runtime_configure_internal` | 0/20 | 0/20 | 0 |
| `pl011_init` | 0/20 | 0/20 | 0 |

**All 10 discordant pairs come from exactly 2 of the 5 targets.** The other 3 — `isr`,
`runtime_configure_internal`, `init` — are a complete, clean 0/20 floor under *both*
conditions: not one success anywhere, loop or no loop, across 60 combined trials. This is
not noise scattered randomly across targets; it is a structural split by target.

**Honest interpretation:** the significant aggregate p-value does **not** support the claim
"the compile-check+retry loop measurably helps `qwen2.5-coder:7b` generate PL011 fuzz
harnesses" as a general statement. The accurate claim is narrower and more specific: **the
loop helps on the two lower-complexity targets in this sample and provides zero measurable
benefit on the three higher-complexity ones, which remain at a hard floor regardless of
feedback.** This is consistent with — not a new finding independent of — `ABLATION_B_V2.md`'s
own prior result: that experiment's one real success (14B, `poll_out`) also landed on the
same target, and `isr`/`runtime_configure_internal` were specifically selected in that
experiment's design for having the highest cyclomatic complexity (CCN 17 each) of any
function in the driver file. Two independent experiments now show the same pattern. That the split tracks
cyclomatic complexity is a hypothesis, not a result: it has not been separated from
prompt/scaffold effects (see the 14B section), and per-target error tallies are still needed.

### Spot-check verification (source-level) — corrected Oct 5 2026

Two of the 10 rescued 7B trials (`pl011_poll_in` trial 3, rescued on attempt 4;
`pl011_poll_out` trial 1, rescued on attempt 3) were audited at the source level. **What this
check does and does not establish:** the pre-fix script overwrote each attempt's files and never
saved the compiler error text, so for these 7B trials only the final (successful) harness
exists. The compiler error that attempt 1 actually failed with is unrecoverable.

An earlier version of this section stated specific attempt-1 errors ("undefined `get_uart` and
`PL011_FR_RXFE`", an "incomplete-type error"). Those were inferences from reading the code, not
observed compiler output, and the first one is wrong: the attempt-1 `poll_in` harness included
`<zephyr/drivers/serial/uart_pl011_registers.h>`, and that header already defines
`struct pl011_regs`, `get_uart`, `PL011_FR_RXFE` and `PL011_FR_TXFF`, so those symbols were not
undefined. The 14B run (below), which has real per-attempt error text, shows the dominant
failure is the model redefining structs the included headers already provide
(`error: redefinition of 'pl011_regs'`); the 7B attempt-1 `poll_in` harness has exactly that
pattern (it includes the header, then declares its own `struct pl011_regs`), so that is the
likely real error, but it remains an inference for 7B.

What was verified directly: both final harnesses were re-compiled from the extracted source with
the exact command `evaluate_harness()` uses and compile cleanly (exit code 0), and both are
non-degenerate fuzz targets (`poll_in`'s harness feeds fuzzer bytes into the mock register
struct; `poll_out`'s loops over every input byte calling the target function). That rules out
`evaluate_harness()` being flaky as the source of the 10 discordant pairs. It does not show
which compiler error each rescue fixed.

## Results — `qwen2.5-coder:14b` (statistics verified Oct 5 2026; interpretation pending)

Full 100-trial run completed on Antigravity's machine (backend: see the reproducibility note
below), about 14 hours. Run at commit `54eef536c` (the provenance-fix version), so every trial has
per-attempt files and real error text. The statistics below were re-derived by Claude from the
raw per-trial JSON, not taken from the run's summary.

| | Oracle-absent (one-shot) | Oracle-present (loop) |
|---|---|---|
| Success rate | 4.0% (4/100) | 5.0% (5/100) |

Concordant-success 4, concordant-fail 95, loop-rescued (b) 1, hurt by loop (c) 0. McNemar's
exact p = 1.0 (one discordant pair; not significant).

| Target | Oracle-absent | Oracle-present | Rescued |
|---|---|---|---|
| `pl011_poll_in` | 2/20 | 3/20 | 1 (trial 16, attempt 2) |
| `pl011_poll_out` | 2/20 | 2/20 | 0 |
| `pl011_isr` | 0/20 | 0/20 | 0 |
| `pl011_runtime_configure_internal` | 0/20 | 0/20 | 0 |
| `pl011_init` | 0/20 | 0/20 | 0 |

**Comparison with 7B.** One-shot success is identical (4/100 vs 4/100). The difference is
entirely in what the loop does: 7B rescued 10 of its 96 attempt-1 failures, 14B rescued 1 of 96
(Fisher's exact, two-sided, p = 0.0096). So the larger model is not worse at one-shot
generation here; the compile-error-feedback loop simply converts almost none of its failures.
This should not be reported as "bigger models repair worse" without the diagnostics below,
because the failure mode appears to be at least partly a scaffold artifact:

* **Dominant failure.** 96 of 96 attempt-1 failures are compile errors (no truncation: 0 of 100
  harnesses had unbalanced braces; no API errors). A full tally of every `error:` line (not
  just the first line) shows that **all 96 of 96 attempt-1 failures contain at least one
  `redefinition of` error**. Attempt-1 error-line counts: `redefinition of 'pl011_regs'` 168,
  `'get_uart'` 72, `'device'` 70; everything else is minor (`call to 'memcpy' is ambiguous` 8,
  `static declaration of 'pl011_poll_in' follows non-static declaration` 5, `no matching
  function for call to 'free'` 4, `unknown type name 'pl011_data'/'pl011_config'` 3 each, and
  a handful of one- and two-off messages). The pattern is the same on every target.
* **The loop does not escape it.** Across attempts 2-5 (96 trials x up to 4 retries) the same
  three redefinitions still dominate: `pl011_regs` 657, `get_uart` 284, `device` 261. Of the 95
  trials that never succeeded, 91 still contain `redefinition of 'pl011_regs'` at attempt 5,
  and in 53 the set of error types at attempt 5 is identical to attempt 1. Example
  (`pl011_isr` trial 1): the attempt-5 harness `#include`s `<zephyr/device.h>` and
  `<zephyr/drivers/serial/uart_pl011_registers.h>` and then redefines `struct pl011_regs`,
  `struct device` and `get_uart` itself, exactly as in attempt 1.
* **A second layer exists behind the first.** Where the redefinition does disappear, other
  scaffold-level errors surface: `use of undeclared identifier 'ENOTSUP'` (15 error lines, all
  `runtime_configure_internal`; the harness never includes `<errno.h>`), `out-of-line
  definition of 'pl011_set_baudrate' does not match any declaration`, `unknown type name
  'pl011_config'/'pl011_data'` and incomplete-type uses of `struct device` (`init`), and
  undeclared helpers such as `pl011_irq_rx_ready` in the `isr` target's source. So fixing the
  prompt may not by itself lift the three 0/20 targets; that needs a smoke test, not an
  assumption.
* **Likely cause: ambiguous, under-specified prompt (refined after reading it again).** The v1
  prompt says "mock the MMIO registers using a static struct", which models read as "define
  `struct pl011_regs`", although the included header already defines it. It never says that
  `get_uart()` is provided by the header, so models re-implement it. It does say, mid-paragraph,
  "Do NOT redefine `struct device`", and models redefined `device` anyway (70 error lines), so
  part of the failure is plain instruction-following, not only ambiguity. This is the same class
  of scaffolding defect as those fixed in the B v2 audit, and would depress both models' floors
  independently of capability. (An earlier version of this note called the prompt
  "contradictory"; that overstated it.)
* **The retry prompt does not include the previous code.** Each retry is the original prompt
  plus the latest error text, so the model regenerates from scratch with a hint rather than
  patching its own code. The error text is passed in full (not truncated).
* The one verified rescue (`poll_in` trial 16) is a clean example of the loop working as
  intended: attempt 1 failed with three redefinition errors (`pl011_regs`, `device`,
  `get_uart`, each with the compiler's "previous definition is here" note); attempt 2 dropped
  the redefinitions and relied on the headers; the harness compiles (re-checked by hand, exit
  code 0) and reached `cov: 5` over about 1.4M executions.
* **Reproducibility note (backend, corrected).** An earlier note here and in the run's own
  report described the 14B run as "CPU-only". The Ollama server log shows otherwise:
  `CUDA_VISIBLE_DEVICES=-1` disabled CUDA, but Ollama fell back to its Vulkan backend on the
  same discrete GPU (`library=Vulkan ... NVIDIA GeForce RTX 4050 Laptop GPU`, 5.8 GiB total).
  14B: `offloaded 20/49 layers to GPU`. 7B (same server log): `offloaded 26/29 layers to GPU`.
  So both runs used partial Vulkan offload, with different layer splits. Sampling is
  temperature 0.7, so neither run was bit-reproducible anyway; the offload split is recorded
  for completeness and is not believed to explain the result, which is dominated by compile
  errors present in 96/96 attempt-1 failures. Model digests and quantization: 7B
  `dae161e27b0e` and 14B `9ec8897f747e`, both Q4_K_M, 32768 context.

**Reading of the combined evidence.** The Ablation G v1 prompt is ambiguous about which symbols the
build already provides (`struct pl011_regs`, `get_uart`) and the models also ignore its explicit
rule about `struct device`; the compiler rejects the result. Both legs' absolute success rates, the 7B rescue count, and the 14B-vs-7B contrast
are therefore measurements of a scaffold with a known defect, not clean measurements of
repair capability. The Fisher comparison above is a fact about this scaffold only. Pending: a
decision on correcting the prompt and re-running both models (smoke test first), and keeping
the retry prompt design as is unless changed deliberately and reported as a separate change.

## Provenance fix (Oct 4 2026)

`evaluate_harness()`'s retry loop originally overwrote the same `harness.cpp`/`fuzz_bin`
files on every attempt, so only the *last* attempt of any trial survived on disk once a trial
finished — intermediate failing attempts and the actual compiler/runtime error text (only a
short label like `"Compiler Error"` was ever printed to console) were unrecoverable after the
fact. This meant the source-level spot-check above could only be performed on the final
successful attempt of each rescued trial, not the full attempt-by-attempt sequence, for the
7B run specifically. Fixed in `run_ablation_g.py` (committed `54eef536c`) to write each
attempt to its own numbered file (`harness_attempt<N>.cpp` + a `_result.json` sidecar with
the full error text) while keeping a stable `harness.cpp`/`harness_result.json` alias
pointing at the latest attempt. The 14B run (and any future re-run) will have full
attempt-by-attempt provenance; the 7B run's already-completed trials do not, and that gap is
not recoverable for them.

## Prompt v2 (Oct 5 2026)

`run_ablation_g.py --prompt-version v2` keeps v1 frozen (default) and applies exactly four
prompt changes, documented in the script (`PROMPT_V2_NOTE`): (1) "static struct" becomes "a
static INSTANCE of the existing `struct pl011_regs`"; (2) states that `get_uart()` is provided
by the header; (3) repeats the do-not-redefine rule for `struct pl011_regs`, `struct device`,
`get_uart` and the `PL011_*` macros in a final explicit block; (4) tells the model to include
`<errno.h>` if it uses errno constants. Target source, success criteria, temperature, retry
design (previous code still omitted) and trial counts are unchanged. v2 results and logs are
written to `*_promptv2*` files so v1 data is never overwritten. v2 results will be reported
as a separate experiment next to v1, not as a replacement for it.

### Prompt v2 smoke test (7B, 5 trials per target, Oct 5 2026) and prompt v3

Reported by the executing agent, not yet independently re-derived; the agent's own analysis
was labelled a "snapshot from the first 10 completed trials" while tabulating 25, so the
numbers below should be treated as provisional until the v3 smoke test is analysed with
explicit file counts. The agent also disclosed that code it pasted in an earlier report
(the tail of one 14B harness) had been reconstructed from memory after tool output was
truncated; error texts and tallies came from scripts and are unaffected, and no committed
statement here relies on the reconstructed code.

* v2 success: 0/25 at attempt 1 and 0/25 eventually. Redefinition errors at attempt 1: 0
  (v1 14B: 96/96), so the v2 text did what it was meant to.
* New failure: told not to define the types, the model stopped including the headers at all
  (the v1/v2 text only says it "can" include them) and forward-declared `struct device`,
  `struct pl011_regs`, `struct pl011_data`, giving `member access into incomplete type` errors.
  On retries it added definitions back, so 2 never-succeeding trials again showed
  `redefinition of` at attempt 5.
* Scaffold solvability: `verify_reference_harnesses.py` builds one hand-written harness per
  target under the exact build flags. All five compile, exit 0 and reach `cov` 6-19 in a
  1-second run, so the headers and build can support success.

`--prompt-version v3` (v2 plus a build contract): the file must begin with a stated list of
`#include` lines per target, the already-provided symbols are listed as must-not-define, and
the types no header provides (`pl011_data`, `pl011_config`) are named as must-define. This
tells the model more about the build than v1 did, so it measures repair and generation *given a
fully specified build contract*; it will be reported as such, alongside v1 as-run, never as a
replacement for v1.

### Prompt v3 smoke test (7B, 5 trials per target, Oct 5 2026) and decision

Executed on `qwen2.5-coder:7b` at commit `ac98ae6dd` (CUDA, 25/29 layers). Tallies were produced
by a script reading the 25 result JSONs; no reconstructed code in this report. Attempt-5 error
text was truncated by the executing agent, and the result JSONs of successes carry no coverage
or exec count, so the strength of the 3 successes was not measured.

| Prompt (7B) | Attempt 1 | Eventual (<=5 attempts) | n |
|---|---|---|---|
| v1 (as run) | 4/100 | 14/100 | 100 |
| v2 smoke | 0/25 | 0/25 | 25 |
| v3 smoke | 1/25 | 3/25 | 25 |

Per target (v3): `poll_out` 1/5, `runtime_configure_internal` 2/5 (rescued at attempts 3 and 5),
`poll_in`, `isr`, `init` 0/5. With n=25 and 3 successes these are anecdotes, not rates.

What v3 fixed: all 25 harnesses began with the required include block; attempt-1 failures with a
`redefinition of` error fell to 4/24 (all `get_uart`).

What it did not fix (dominant remaining failures):

* Target function used before declaration (28 attempt-1 lines, every target). The prompt already
  instructs "forward-declare it ABOVE that point", so this is an ignored explicit instruction,
  not an under-specified scaffold.
* `struct pl011_data` / `struct pl011_config` forward-declared or omitted despite the
  must-define rule (185 "incomplete type" lines over attempts 2-5, `isr` and `init`).
* Invented `K_SPINLOCK_INIT` / `K_SPINLOCK_INITIALIZER` (18 lines); the shim `kernel.h`
  provides `k_spinlock_t` and `K_SPINLOCK` only.
* `get_uart` still redefined in 6 never-succeeding trials at attempt 5, plus `void*`/qualifier
  mismatches in the model's own variants.
* In 7 never-succeeding trials the error buckets at attempt 5 equal those at attempt 1: the
  retry prompt carries only the latest error text, not the previous code.

Decision: no further prompt iteration and no full v3 run. Once the scaffold ambiguity was
removed and the build contract stated in full, the 7B model still reached 1/25 at attempt 1 and
3/25 eventually; its remaining failures are instruction-following and generation failures, which
is the capability the ablation measures. Repeating the smoke test with more scaffolding (a
filled-in skeleton) would change the task from "write a harness" to "fill in a fuzz body" and is
out of scope. Reporting plan: v1 (7B, 14B) is the headline result; v2/v3 smoke tests are reported
as a scaffold-sensitivity finding (Table 16 is hypersensitive to prompt scaffolding for small
models, and both models sit near the floor under every prompt tried). The 14B was not re-run
under v2/v3.
