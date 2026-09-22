# AeroHarness Final Evaluation Protocol

This checklist dictates the definitive, final set of tables and experiments the AeroHarness paper will contain. No more ad hoc additions will be included unless a distinctively novel finding justifies extending the scope. 

- [x] **Table 1: Static Analysis Oracle Output**
  - Breakdown of the 53 targeted hardware interactions: 18 Confirmed, 12 Disagreements, 23 Unconfident.
  - Status: DONE (Stage 3). Referenced in RESULTS.md.

- [x] **Table 2: P2IM Baseline Comparison (Execution Efficacy)**
  - 83.3% accuracy achieved on the strict RIOT USART firmware benchmark.
  - Status: DONE (Stage 4). Referenced in RESULTS.md.

- [x] **Table 3: ML Model Classifier Accuracy (CodeBERT vs XGBoost)**
  - Comparison of static analysis accelerators: CodeBERT (97.4% Acc, 0.941 F1) vs XGBoost (96.2% Acc, 0.912 F1) vs Majority Baseline (68.1% Acc, 0.00 F1).
  - Status: DONE (Stage 5). Referenced in RESULTS.md.

- [x] **Table 4: RL Algorithm Performance (10-Seed Coupon Collector Evaluation)**
  - Final reward means and stddevs for Q-Learning, UCB1, and PPO on N=12 (Shallow) and N=5 (Deep) datasets. Proves algorithmic complexity (PPO) is bound by structural saturation speed (Coupon Collector).
  - Status: DONE (Stage 7). Referenced in RESULTS.md.

- [x] **Table 5: Oracle Ablation (Learned Uncertainty vs Random)**
  - UCB1 run with the genuine Oracle uncertainty multiplier (78.20 ± 3.97) vs randomly shuffled target multipliers (51.00 ± 22.27). Verifies our learned signal breaks uniformity.
  - Status: DONE (Stage 7 Extension). Referenced in RESULTS.md.
