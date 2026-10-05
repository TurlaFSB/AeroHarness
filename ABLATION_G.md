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

Full 100-trial run completed on Antigravity's machine, CPU-only (a CUDA crash forced
`CUDA_VISIBLE_DEVICES=-1`; a partial-offload test was 3x slower than CPU, so CPU was kept),
about 14 hours. Run at commit `54eef536c` (the provenance-fix version), so every trial has
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
  harnesses had unbalanced braces; no API errors). Among them, 52 have
  `redefinition of 'pl011_regs'` as the first line of the error text; the other 44 begin with
  a warning or a different line, so first-line counting understates the real share and a full
  per-error tally is still needed.
* **Likely cause: contradictory prompt.** Each target prompt says "you must mock the MMIO
  registers using a static struct" while also pointing the model at real headers that already
  define `struct pl011_regs`, `struct device` and `get_uart`. A model that follows both
  instructions redefines symbols the header provides and fails to compile. This is the same
  class of scaffolding defect as the ones fixed in the B v2 audit (an empty `device.h`, a
  header-path mismatch), and would depress both models' floors independently of capability.
* **The retry prompt does not include the previous code.** Each retry is the original prompt
  plus the latest error text, so the model regenerates from scratch with a hint rather than
  patching its own code. The error text is passed in full (not truncated).
* The one verified rescue (`poll_in` trial 16) is a clean example of the loop working as
  intended: attempt 1 failed with three redefinition errors (`pl011_regs`, `device`,
  `get_uart`, each with the compiler's "previous definition is here" note); attempt 2 dropped
  the redefinitions and relied on the headers; the harness compiles (re-checked by hand, exit
  code 0) and reached `cov: 5` over about 1.4M executions.
* **Reproducibility note.** The 7B run used the GPU; the 14B run used a different backend
  (reported as Vulkan, CPU-only) on the same machine. Model digests and quantization are
  recorded: 7B `dae161e27b0e` and 14B `9ec8897f747e`, both Q4_K_M, 32768 context.

Pending before this leg is treated as final: a full per-error-type tally across all attempts
(not first lines only), whether failed trials repeat the same error across attempts 2-5, and a
decision on whether the contradictory prompt should be fixed and both models re-run.

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
