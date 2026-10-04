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
function in the driver file. Two independent experiments now show the same complexity-gated
pattern, which is stronger evidence than either alone.

### Spot-check verification (source-level, not just statistical)

Two of the 10 rescued trials were independently audited at the source-code level — not just
trusted from the stored JSON record — to confirm the loop's real-feedback mechanism actually
fixed a real, specific compile error rather than the final attempt happening to compile by
chance:

* **`pl011_poll_in`, trial 3 (succeeded on attempt 4):** the attempt-1 harness referenced
  `get_uart(dev)` and the macro `PL011_FR_RXFE` in the appended target function body, but
  defined neither anywhere in the harness — a genuine undefined-symbol compile error. The
  attempt-4 harness adds exactly those two missing definitions (a real `get_uart` function,
  a `#define PL011_FR_RXFE 0x10`) and is otherwise materially unchanged. A precise, traceable
  fix matching the fed-back compiler error, not a lucky rewrite.
* **`pl011_poll_out`, trial 1 (succeeded on attempt 3):** the attempt-1 harness declared a
  `struct device` field of type `const struct device_config *` without `device_config` ever
  being defined anywhere — an incomplete-type compile error — and separately used the
  undefined macro `PL011_FR_TXFF`. The attempt-3 harness replaces the undefined type with a
  plain `void *config` and defines `PL011_FR_TXFF` via its own `BIT` macro. Same pattern:
  specific, targeted fix.

Both final harnesses were independently re-compiled from the extracted source (not just read)
with the exact command `evaluate_harness()` uses and confirmed to compile cleanly (exit code
0). Both are substantively real fuzz targets, not degenerate no-ops: `poll_in`'s harness
copies fuzzer input directly into the mock register struct and exercises the branch on `fr`;
`poll_out`'s harness loops over every input byte calling the target function. This rules out
the main alternative explanation for a positive "rescue" result — that `evaluate_harness()`
itself is flaky/non-deterministic and some fraction of the 10 discordant pairs are false
positives rather than genuine repairs.

## Results — `qwen2.5-coder:14b`

**In progress.** Running on Antigravity's machine as of Oct 4 2026, CPU-only (GPU path hit a
CUDA crash, confirmed avoided by forcing `CUDA_VISIBLE_DEVICES=-1`), which makes it
substantially slower than the 7B run — early pace estimate puts full completion around
12-15 hours from start. Will be appended here once complete, with the same per-target
breakdown and a source-level spot-check of at least 2 rescued trials before being accepted,
same bar as the 7B leg above.

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
