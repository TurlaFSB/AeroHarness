# AeroHarness Final Evaluation Protocol

This checklist dictates the definitive, final set of tables and experiments the AeroHarness paper will contain. No more ad hoc additions will be included unless a distinctively novel finding justifies extending the scope. 

- [x] **Table 1: Static Analysis Oracle Output**
  - Breakdown of the 53 targeted hardware interactions: 18 Confirmed, 12 Disagreements, 23 Unconfident.
  - Status: DONE (Stage 3). Referenced in RESULTS.md.

- [x] **Table 2: P2IM Baseline Comparison (Execution Efficacy)**
  - 83.3% accuracy achieved on the strict RIOT USART firmware benchmark.
  - Status: DONE (Stage 4). Referenced in RESULTS.md.

- [x] **Table 3: ML Model Classifier Accuracy (CodeBERT vs XGBoost vs Zero-Shot)**
  - Comparison of static analysis accelerators: CodeBERT (54.0% � 24.4%) vs XGBoost (45.7% � 25.3%) vs Majority Baseline (40.4% � 33.9%). Zero-shot LLM outperformed all at 83.3%. 
  - Status: DONE (Stage 5). Referenced in RESULTS.md.

- [x] **Table 4: RL Algorithm Performance (10-Seed Coupon Collector Evaluation)**
  - Final reward means and stddevs for Q-Learning, UCB1, and PPO on N=12 (Shallow) and N=5 (Deep) datasets. Proves algorithmic complexity (PPO) is bound by structural saturation speed (Coupon Collector).
  - Status: DONE (Stage 7). Referenced in RESULTS.md.

- [x] **Table 5: Oracle Ablation (Learned Uncertainty vs Random)**
  - UCB1 run with the genuine Oracle uncertainty multiplier (80.80 � 4.53) vs randomly shuffled target multipliers (73.20 � 18.90). Verifies our learned signal breaks uniformity.
  - Status: DONE (Stage 7 Extension). Referenced in RESULTS.md.

- [x] **Table 6: Informed vs. Blind Harness Construction Ablation**
  - Distinctively novel finding justifying the exception to "no more ad hoc additions" above: tests whether Stage 2/3's semantic MMIO modeling is actually load-bearing for coverage, isolated as its own variable for the first time. Result: not a blanket multiplier -- no measurable difference on shallow functions (`poll_in`, `isr`: identical coverage ceiling, informed vs. blind), but a real, quantified benefit on functions with a single-bit hazard buried in a large raw search space (`poll_out`: informed reaches deeper pre-hang coverage in 9/10 seeds vs. 3/10 for blind). Cross-validated with `llvm-cov`.
  - Status: DONE (Stage 6 Ablation). Referenced in RESULTS.md.

- [x] **Table 7: Second-RTOS/Target Generalization (RIOT OS Kinetis ADC)**
  - Distinctively novel finding: the full Stage 1-6 pipeline run end-to-end on a genuinely different RTOS/peripheral (RIOT OS, Kinetis K64F ADC calibration, not Zephyr/UART), surfacing and fixing real pipeline gaps (a Stage 1 extraction bug, a sparse never-completed Stage 2 run, Stage 3 never having been run on this function at all) and a new, more severe static-mocking limitation class (a self-set-and-spin register bit, unconditionally unfuzzable under single-shot struct mocking, requiring a periodic-timer/signal-based fix after 3 failed thread-based attempts). 10-seed fuzzing campaign and `llvm-cov` cross-validation confirm the fix works and the real driver function reaches 100% line coverage once an input survives the function's two busy-waits.
  - Status: DONE (Second-RTOS/Target pipeline run). Referenced in RESULTS.md.
