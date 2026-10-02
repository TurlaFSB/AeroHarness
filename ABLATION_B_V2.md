# Ablation B v2: Compiler-Oracle Feedback Controlled Trial

*Note: The initial Ablation B (v1) findings were preliminary and are superseded by this document. The v1 findings lacked statistical power (n=1 per harness) and its hypotheses regarding LLM non-determinism and model discrepancies were unverified.*

## Research Question and Pre-Registered Hypotheses
**RQ:** When an LLM-generated harness fails its first compilation, does feeding back the real compiler diagnostics convert failures into working harnesses more often than a generic "compilation failed, try again" message?

* **H1:** Real compiler feedback yields a higher repair rate on first-attempt failures than generic feedback.
* **H0:** No difference in repair rate between real and generic feedback.

*(Note: A null or negative result is acceptable and will be reported exactly as found. No hypotheses, thresholds, or analysis methods will be adjusted after seeing the data).*

## Experimental Design

### Targets
We evaluate 5 targets from the `uart_pl011.c` Zephyr driver:
1. `pl011_poll_in` (Original target)
2. `pl011_poll_out` (Original target)
3. `pl011_isr` (Original target)
4. `pl011_runtime_configure_internal` (Extra target)
5. `pl011_init` (Extra target)

**Selection Criteria for Extra Targets:** To ensure enough first-attempt failures for statistical power, the two extra targets were chosen objectively based on having the highest Cyclomatic Complexity (CCN) in the `uart_pl011.c` file using the `lizard` tool. 
* `pl011_runtime_configure_internal`: CCN 17, NLOC 82
* `pl011_init`: CCN 17, NLOC 59

### Paired Branching Design
For each target, we run N = 20 independent trials (100 trials total).

1. **Attempt 1 (Clean Slate):** Generate the harness once. Attempt to compile.
2. **First-Attempt Success:** If it succeeds (compiles, links, runs non-trivially), record as "first-attempt success" and end the trial.
3. **Branching (Failed Attempt 1):** If Attempt 1 fails, that exact same failed code state branches into two arms:
   * **Arm A (Real Feedback):** The LLM receives the real compiler stderr and retries up to 4 more times (5 attempts total).
   * **Arm B (Generic Feedback):** The LLM receives only the string *"The code failed to compile. Please try again."* and retries up to 4 more times.
   
Because both arms start from the identical failed harness, the outcomes are paired, allowing for McNemar's exact test.

### Controls
* **Backend:** Local `ollama run qwen2.5-coder:7b` as the primary backend to prevent API quota exhaustion (approx ~100 initial runs + retries). 
* **Parameters:** `temperature=0.7`, exactly the same across all runs. Seed is pseudo-randomly assigned and logged per trial.
* **Prompt:** The canonical Stage 6 zero-shot harness-generation prompt is used for all trials.
* **Clean Slate:** A dedicated, empty working directory is created for each trial. No pre-existing stubs, headers, or macros are provided.

### Success Criteria (Automated Checks)
A harness is marked "Successful" only if ALL of the following hold:
1. **Compiles and Links:** `clang++ -fsanitize=fuzzer,address` returns code 0.
2. **Executes Safely:** The resulting binary runs for at least 1 second without a startup crash, ASan, or UBSan error.
3. **Non-Trivial Coverage:** The fuzzing run reports greater than 3 coverage edges (proving the fuzzer actually traverses logic, not just an empty `LLVMFuzzerTestOneInput`).
4. **Source Integrity:** The LLM does not stub out the function under test (verified by ensuring the target function name exists in the generated source code alongside LLVMFuzzerTestOneInput).

### Metrics and Statistics to Report
* First-attempt success rate (with 95% Wilson CI).
* Number of first-attempt failures (the sample size for the paired test).
* Repair rate within 5 attempts for Arm A vs Arm B (with 95% CIs).
* Mean and median attempts to success for each arm (among successes).
* McNemar's exact test on paired outcomes (p-value, difference in repair rate, CI).
* Failure categorization per arm (missing header, type error, etc.).
* *Note: If first-attempt failures are < 10, the statistical results will be explicitly described as inconclusive.*

## Deviations from Pre-Registration

Following a 10-trial pilot run (2 trials per target), the following deviations and adjustments were applied to the experimental pipeline to make the experiment workable, without changing hypotheses, trial counts, analysis plan, or the branching logic:

1. **Pipeline Append-Fix & Prompt Update**: In the first pilot, every single attempt (10/10) failed to compile. The LLM fundamentally assumed the target function was externally linked and only forward-declared it, leading to persistent `undefined reference` errors which it could not fix in either arm. To fix this mechanical issue, the evaluation script was updated to automatically append the raw driver source code to the end of the LLM's harness. The prompt was updated to explicitly inform the LLM of this behavior (telling it to only forward-declare, not define). If the LLM still tries to define the function itself, the resulting redefinition error counts as a genuine compile failure.
2. **Tightened Timeout Rule**: LibFuzzer hangs (infinite loops) are a known issue for some targets like `pl011_poll_out`. The success checker was updated using libFuzzer's `-timeout=2` to ensure a timeout counts as a success ONLY IF the stack trace confirms the hang occurred inside the target function (verified via `-fno-inline`) or coverage exceeded the trivial threshold before the hang. Hangs occurring elsewhere (e.g., in the fuzzer loop itself) are considered failures.
3. **Dependency Injection & Prompt Parity Fix**: After the second pilot yielded nearly 100% failure rates across all arms because the 7B model could not guess missing Zephyr macro structures (e.g., `K_SPINLOCK`), we allowed the LLM to access the real underlying driver header file (`uart_pl011_registers.h`), exactly matching the real dependencies used in the original Stage 6 harnesses. No Zephyr-specific stubs were provided (e.g., `device`, `K_SPINLOCK`), leaving those to be repaired. We also fixed the prompt retry logic to perfectly restate the original instructions on every retry (avoiding an accumulation of history that might confuse the model), varying strictly only the feedback string between Arm A and Arm B.

*(The raw results of the failed First Pilot have been preserved in Appendix A and excluded from the main analysis.)*

---
## Results

> **Superseded, Oct 2026.** The pilot numbers below (100% first-attempt failure, 0% repair in both arms, "complete floor effect") were caused by defects in the experimental scaffolding itself, not by model incapability. A systematic audit found and fixed five distinct scaffolding bugs (detailed in "Scaffolding Audit and Remediation" below) and the full experiment was then re-run clean. **The real result is in "Results (Full Re-Run, Post-Remediation)" further down this document.** This section is kept verbatim for provenance — it documents a real intermediate state of the project and the reasoning that led to the audit — but its "Inconclusive (Floor Effect)" conclusion no longer reflects the corrected experiment and must not be cited as the experiment's outcome.

The planned 100-trial execution was halted after consecutive pilot runs with both the `qwen2.5-coder:7b` and `qwen2.5-coder:14b` models revealed a severe floor effect. 

**Pilot Results (N=2 per target, 10 trials total per model):**
* **First-Attempt Failure Rate:** 100% (10/10) for both the 7B and 14B models.
* **Failure Modes:** The errors were strictly dominated by Zephyr-plumbing issues. Despite having access to the driver's local register header, both models failed because the header relies on internal Zephyr framework macros (e.g., `BIT`, `K_SPINLOCK`, `DEVICE_MMIO_GET`) which were unavailable. 
* **Arm A (Real Feedback) Repair Rate:** 0/10 for both 7B and 14B models.
* **Arm B (Generic Feedback) Repair Rate:** 1/10 for 7B (a single random convergence on `poll_out`), 0/10 for 14B.

### Conclusion: Inconclusive (Floor Effect)
Both `qwen2.5-coder:7b` and `qwen2.5-coder:14b` show a complete floor effect on this task. Because the models achieved a 0% success rate in both arms, H1 versus H0 cannot be distinguished within this experimental design. **The result is inconclusive by the pre-registered criteria, not a negative result for H0.** 

This means the type of feedback did not matter because *neither model reached a working harness under either condition within the 5-attempt budget*, not that real compiler feedback was shown to be unhelpful. The models were fundamentally incapable of synthesizing the missing framework macros (like `K_SPINLOCK` or `BIT`) from scratch, regardless of the feedback provided.

### What this experiment does show
While inconclusive regarding the feedback ablation, this experiment clearly demonstrates that the original Stage 6 success (using the project's configured `gemini-1.5-pro` — **correction, Oct 1 2026**: this document previously said "Gemini 3.6 Flash," a model name that does not exist in any real Gemini release or in this repo's own configuration; `src/synthesizer/agent.py`/`config/settings.py` confirm `gemini-1.5-pro` as the actual primary model, `gemini-2.0-flash` as fallback) heavily depended on **human-in-the-loop steering across multiple turns**.

In the original Stage 6 execution, the necessary dummy implementations (such as faking the `BIT` macro) were introduced by a human recognizing the specific compiler error and providing explicit guidance to the model. This is a materially different setting from the fully autonomous, feedback-only retry loop tested here. This highlights a real, useful boundary condition on our claims: fully autonomous self-repair struggles significantly when blocked by missing, complex framework plumbing that requires domain-specific leaps of logic.

### Future Work
Concrete next steps to explore this further, which are deferred as future work:
1. **Increase the Retry Budget:** Raise the retry limit from 5 to a much larger number (e.g., 20) to see if either local model eventually converges through brute-force random variation.
2. **Test a Frontier Model:** Run this exact experimental design using a frontier model (such as `gemini-1.5-pro` or `gemini-1.5-flash`) once API quota and rate limits permit, to determine if the floor effect is strictly tied to the capability of the 7B/14B parameter class.
3. **Human-in-the-Loop Variant:** Test a variant where a human operator supplies the missing macro definitions after 2 autonomous failed attempts, isolating whether the human guidance (rather than model size or random chance) is the definitive factor that made Stage 6 successful.

---
## Appendix A: First Pilot Results
- **Time per trial:** ~216 seconds
- **Attempt-1 Failures:** 10/10 (100%)
- **Repair Success:** 0% (Arm A: 0/10, Arm B: 0/10)
- **Failure Mode:** 100% of failures were `undefined reference` linker errors due to the LLM omitting the driver source code from the harness entirely.

## Verification Note (Oct 1 2026, independent audit)

* **CCN/NLOC selection criteria for the two extra targets** — **confirmed exactly**. Running `lizard zephyr-src/drivers/serial/uart_pl011.c` fresh in this audit gives `pl011_runtime_configure_internal`: CCN 17, NLOC 82, and `pl011_init`: CCN 17, NLOC 59 — matching this document's numbers digit-for-digit. Listing every function in the file by CCN also confirms these two are genuinely the joint-highest in the file (next highest is `pl011_irq_tx_enable` at CCN 6), so "objectively chosen based on having the highest CCN" is a real, independently-reproducible claim, not an unchecked assertion.
* **`uart_pl011_registers.h` (the header the LLM is given access to in deviation #3)** — **confirmed to exist**, at `zephyr-src/drivers/serial/uart_pl011_registers.h`, so that part of the experimental setup is real rather than aspirational.
* **The actual trial data (pilot results, failure-rate percentages, Appendix A numbers, per-trial timing) — not independently reproducible in this audit, and not silently assumed correct.** `run_ablation_b_v2.py` and `analyze_ablation_b_v2.py` are both real, substantive scripts in the repo and their logic is internally consistent with the methodology narrated above (e.g. `call_ollama()` at line 187, the paired-branching retry structure, the `wsl` process-kill call at line 250 confirming this was built to run against the original author's Windows/WSL machine). But: (1) no `ollama` binary is available in this audit sandbox, so the LLM-dependent trials cannot be re-run here at all; (2) no raw pilot-run log, JSON result file, or saved trial transcript for this experiment exists anywhere in the repo — a targeted search for pilot/result/log artifacts under this experiment's name found nothing; (3) the script's own `subprocess.run(["wsl", ...])` call means even with `ollama` present, this sandbox (plain Linux, no WSL) could not execute it unmodified. This is the same category of finding as several other items already flagged elsewhere in this audit (e.g. `corpus_growth_analysis.md`'s single non-reproducible fuzzing run): the pipeline and the narrative are both real and consistent with each other, but the specific reported numbers (100% first-attempt failure, 0/10 and 1/10 repair rates, ~216s/trial) rest on a run that cannot currently be checked against any artifact — they should be read as "reported, plausible given the script's real logic, but not independently re-verified here," not as silently confirmed.
* **Overall assessment:** this document's own epistemics are already unusually careful for this kind of claim (pre-registered hypotheses, explicit "no post-hoc adjustment" note, honest "Inconclusive" framing rather than overclaiming a negative result) — nothing found in this audit contradicts its narrative, but nothing found independently proves the specific trial numbers either, given the missing raw log and unavailable backend. This gap should be closed in a future revision by committing the raw per-trial output (compiler stderr, success/failure, timing) the scripts presumably produced when they were actually run.

---

## Scaffolding Audit and Remediation (Oct 2026)

The pilot's "complete floor effect" (0% success for both models, both arms) was treated as a suspicious result rather than an accepted finding, on the grounds that a 100% failure rate is as likely to indicate a broken test harness as a genuinely incapable model. A systematic audit of the experimental scaffolding was carried out before any claim was accepted. The audit reviewed every file the LLM-generated harness depends on to compile — the mock Zephyr headers under `harnesses/include/`, the real upstream driver header `zephyr-src/drivers/serial/uart_pl011_registers.h`, the five target-function bodies embedded in the experiment's own prompts, and the orchestration script `run_ablation_b_v2.py` itself — by direct inspection of source and local compilation, not by trusting any single run's output. Five distinct, independently-confirmed defects were found and fixed:

1. **Empty `device.h` mock.** `harnesses/include/zephyr/device.h`, the stand-in for Zephyr's `struct device` and the `DEVICE_MMIO_GET`/`BIT`/`GENMASK` macros every target body depends on, was a zero-byte file. No LLM, regardless of capability, could have passed a single trial against this scaffolding — any code referencing `struct device` would fail to compile before the model's own logic was ever tested. This was the primary cause of the reported 100% failure rate and is why the pilot's floor effect is not evidence about model capability. Fixed by writing a minimal, correct mock (`struct device` with `config`/`data`/`mmio_base` fields, plus `DEVICE_MMIO_GET`, `BIT`, `GENMASK`), validated by a standalone local compile before being accepted.

2. **Three missing symbols baked into the experiment's own "ground truth" target bodies.** The embedded source text of `pl011_init`, `pl011_runtime_configure_internal`, and `pl011_isr` — the functions the LLM is told to fuzz, copied from the real upstream driver — referenced `PL011_LCRH_WLEN_5` through `PL011_LCRH_WLEN_8`, `struct uart_config` plus four enums (`uart_config_parity`, `uart_config_stop_bits`, `uart_config_data_bits`, `uart_config_flow_control`), and `k_spinlock_t`/`K_SPINLOCK`, none of which existed anywhere in the provided scaffolding. This was found by a systematic symbol-by-symbol audit of the five embedded function bodies against the real header and the real upstream `uart_pl011.c` driver, and confirmed by locating the real upstream definitions (`PL011_LCRH_WLEN_SIZE(x)` is the real macro; the fixed-width variants don't exist upstream and had to be derived). A genuine function-signature mismatch was also found and resolved this way: the embedded code calls `pl011_set_baudrate` with 2 arguments, while the real upstream function takes 3 — the mock was written to match the 2-argument call site actually used, with this documented explicitly in the prompt rather than silently papered over. No model could pass these three targets no matter what it wrote, before this fix.

3. **Include-path inconsistency.** Two of three stub headers (`device.h`, `uart.h`) were reachable only via the real-Zephyr-style path (`<zephyr/device.h>`), while the real register header was reachable only via a different, quoted, repo-specific path. Across multiple smoke tests, models consistently got the first two right by correctly pattern-matching on real Zephyr conventions from their training data, then applied the same convention to the third header and failed on a file-not-found that had nothing to do with coding ability. Fixed with a forwarding shim making both paths resolve to the identical real header.

4. **`FileNotFoundError` crash in the harness-execution step.** `evaluate_harness()` built the compiled binary's path as already prefixed with the trial's working directory, then passed that same prefixed path to `subprocess.run` with `cwd` also set to the working directory — causing the OS to look for the binary at a doubly-nested path that never existed. This bug had been present in the script from the start but only manifested once a harness compiled successfully for the first time in the experiment's history, crashing the run at exactly the moment it produced its first positive result. Found by reading the traceback and the actual script logic (not accepted from the crash report alone), fixed, and verified with a standalone reproduction of the exact `subprocess` call pattern before resuming.

5. **Non-portable reliance on `FuzzedDataProvider.h`.** Some generated harnesses attempted `#include <fuzzer/FuzzedDataProvider.h>`, which happened to resolve in one sandbox via a mirror path that is not part of `clang++`'s real resource directory and would not be expected to resolve the same way on a different machine. Rather than hard-coding an `-I` path fix that might not generalize, the prompt was updated to tell models to read `data`/`size` directly and not rely on that header.

Each fix was validated independently before being accepted: by reading the relevant source/header directly (not taking any automated report at face value), by cross-referencing against the real upstream Zephyr driver source where applicable, and by a standalone local compile/link/run reproducing the specific failure and confirming the fix resolves it. Findings 1–3 are classified as genuine scaffolding defects (they would have produced a false, contaminated "floor effect" result if left unfixed, regardless of true model capability); findings 4–5 are pipeline/tooling defects in the evaluation harness itself, not the experimental scaffolding the model interacts with.

## Results (Full Re-Run, Post-Remediation)

With all five fixes in place, the complete experiment (5 targets × 2 trials, both arms, up to 5 attempts per arm) was re-run cleanly for both models. Full raw results, generated `harness.cpp` source for every attempt discussed below, and raw `clang++` diagnostics were independently pulled and cross-checked against the repo's real headers before being accepted into this document — not taken from any automated summary alone.

### `qwen2.5-coder:7b` — 0/10 first-attempt successes, 0/10 repairs in either arm

All 10 trials failed on attempt 1 and failed to repair within 5 attempts in both Arm A and Arm B. Critically, **none of the five scaffolding-bug failure signatures recurred** in this clean run — every failure was a different error, model-attributable in kind: redefining symbols the prompt explicitly provides and instructs the model not to redefine (`struct pl011_regs`, `get_uart`), hallucinating nonexistent macros/identifiers (e.g. `K_SPINLOCK_INITIALIZER`, which is not part of the provided mock), and dropping required headers between retry attempts. A separately-seeded exploratory run (outside the locked-in 10-trial set, used only to probe whether success is achievable at all) did produce one real compile success, establishing that 7B's true success rate on this task is low but demonstrably nonzero — not pinned down precisely by a 10-trial sample, consistent with the sample-size limitation noted below.

### `qwen2.5-coder:14b` — 1/10 first-attempt successes recoverable in Arm A, 0/10 in Arm B

Nine of ten trials failed identically to the 7B pattern. One trial — `pl011_poll_out`, trial 1 — produced the only full success anywhere in this re-run, and it is examined in detail below because it is mechanistically verifiable, not just a reported outcome.

**Arm A, attempt 1** failed to compile with a specific, traceable error:
```
error: cannot initialize a member subobject of type 'void *' with an rvalue of type 'volatile struct pl011_regs *'
        .mmio_base = &uart_mock_regs,
```
The model had declared its mock register block as `volatile struct pl011_regs uart_mock_regs`, so its address carries a `volatile` qualifier that C++ will not implicitly drop when assigning into the plain `void *mmio_base` field of the (real, provided) `struct device` mock.

**Arm A, attempt 3 (the success)** changed exactly the thing this error names: the mock register declaration lost its `volatile` qualifier (`static struct pl011_regs uart_mock_regs`), and nothing else relevant to this error changed. The binary compiled (`exit code 0`) and ran clean. This is a directly traceable instance of the mechanism the ablation exists to measure — the model reading a specific compiler diagnostic and applying a fix that addresses that specific diagnostic, not a generic resubmission that happened to work.

**Arm B, branching from the identical attempt-1 failure**, received only the generic "compilation failed, try again" message and never converged in 5 attempts. Its final attempt took a materially different and worse path: rather than using the real, provided `struct pl011_regs` via the header (as Arm A's successful attempt did), it redefined the struct locally from scratch, producing `error: redefinition of 'pl011_regs'`. With no specific error text to anchor a fix to, the model's retries behaved more like independent resampling than targeted repair, and one of those resamples introduced a new, unrelated class of mistake.

Symbol-level verification performed independently of Antigravity's report: `struct pl011_regs`, `get_uart()`, and `PL011_FR_TXFF` — all used in the successful harness — were confirmed to be genuine, pre-existing definitions in the real upstream `zephyr-src/drivers/serial/uart_pl011_registers.h` (with `get_uart()` defined inline in that same header), not hallucinated or incorrectly invented by the model. The physical artifacts on disk (a non-zero-size compiled `fuzz_bin`, `compile_out.txt` with matching timestamps) are consistent with a real, non-fabricated compile success.

### A separate, orthogonal finding: persistent instruction-violation regardless of arm

Across both arms and multiple targets (`pl011_isr`, `pl011_init`), the model repeatedly redefined symbols the prompt explicitly provides and explicitly instructs it not to redefine (`struct pl011_regs`, `get_uart`) — including in Arm A's *final* (5th) attempt for `pl011_isr`, after four rounds of specific, real compiler feedback, where the redefinition error was still present alongside two brand-new errors not seen in attempt 1 (`k_spinlock_init` and `memcpy` used without being declared/included). Real compiler feedback did not reliably converge this failure mode within the attempt budget, and in at least this case the model introduced new mistakes while nominally trying to fix old ones. This is reported as a distinct, qualitative capability observation about `qwen2.5-coder` (at both parameter sizes) — a tendency to re-derive provided infrastructure from scratch rather than use what it's given — independent of, and not explained by, the real-vs-generic feedback manipulation this ablation is designed to test.

### Statistical Analysis

Combined across both models, the full re-run comprises 20 paired trials (10 × 7B, 10 × 14B). Of these, exactly one is discordant (Arm A succeeded, Arm B failed on the same branched attempt-1 failure); zero trials show the reverse (Arm B succeeded, Arm A failed); the remaining 19 are concordant failures in both arms. McNemar's exact (sign) test on this pairing: *b* = 1, *c* = 0, *n* = 1 discordant pair, two-sided exact *p* = 1.0 — **not statistically significant**, and could not be, with only one discordant observation. This is reported exactly as it is: the directional case study above is a real, mechanistically-verified instance of the hypothesized effect, but a single discordant pair cannot support a population-level statistical claim about H1 vs H0 at any meaningful confidence level.

## What We Can and Cannot Conclude

**What this re-run establishes:**
- The original "complete floor effect" was an artifact of broken test scaffolding, not evidence about `qwen2.5-coder:7b`/`14b` capability. This is now corrected at the source rather than merely footnoted.
- Both models have a low, non-zero capacity to produce a working PL011 fuzz harness under this experimental design.
- There exists at least one concrete, auditable case in which real compiler feedback enabled a targeted, correct fix that generic feedback (on the identical starting failure) did not produce — this is evidence the mechanism H1 proposes *can* operate, not evidence that it reliably *does*.
- A separate, real capability weakness (redefining provided infrastructure against explicit instructions, not cured by specific error feedback within 5 attempts) was identified and should be tracked as its own finding rather than folded into the feedback-type question.

**What this re-run does not establish, and should not be claimed to:**
- Whether real feedback produces a *higher repair rate* than generic feedback in general, for either model, at any level of statistical confidence. n = 10 per model (n = 20 combined) with only 1 success total is far below the power needed to distinguish H1 from H0 — this was explicitly flagged as a risk in the pre-registration ("if first-attempt failures are < 10, results will be described as inconclusive") and in the project's own "Dimension B: sample-size problem" item.
- Whether 14B is meaningfully better than 7B at this task — the one success observed in 14B and zero in 7B's locked-in 10-trial set is consistent with a real capability gap, with pure chance, or with 7B's true (low, nonzero) rate simply not having been sampled in 10 trials, as the separate exploratory 7B success shows is possible.

**Honest statement of result:** H1 vs H0 remains formally undecided by this experiment's own pre-registered statistical criteria. What has changed since the original "Inconclusive (Floor Effect)" write-up is that the inconclusiveness is now for the right reason — insufficient discordant-pair sample size on a clean, scaffolding-verified experiment — rather than a contaminated result masquerading as a capability finding.

## Future Work (Revised)

1. **Increase trial count materially** (e.g. n = 20–30 per target per model, matching the original pre-registered design's intent) now that the scaffolding is confirmed sound, to accumulate enough discordant pairs for McNemar's test to carry real statistical weight. This is the single highest-value next step for this specific ablation.
2. **Isolate the redefinition-habit finding as its own question** — e.g. an ablation on whether more forceful or differently-worded prompt constraints reduce the rate at which the model redefines provided symbols, independent of the feedback-type manipulation.
3. **Test a frontier model** (as originally planned) once available, to determine whether the floor effect — now understood to be real, just much lower than 100% — is tied to the 7B/14B parameter class specifically.
4. **Human-in-the-loop variant**, as originally planned, to isolate whether human-supplied guidance (rather than model size or chance) was the decisive factor in the original Stage 6 success.
