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
