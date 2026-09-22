# AeroHarness Results Ledger

This document serves as the single source of truth for all canonical, finalized numbers in the AeroHarness project.

## Stage 1: C/C++ AST Parsing Verification
* **Result**: Successfully parsed and filtered hardware-interaction AST nodes from multiple real-world firmware HALs (Kinetis, STM32). Extracted MMIO reads/writes, pointers, and memory-mapped offsets.
* **Script**: `stage1_ast_parser.py`, `filter_ast.py`
* **Raw Output**: `ast_combined.json` (consolidated JSON of all AST artifacts)
* **Date Finalized**: 2026-09-09

## Stage 2: MMIO Classification (LLM Synthesizer)
* **Result**: LLM successfully generated compilable C++ libFuzzer harnesses mimicking MMIO structures by classifying hardware structs and injecting fake pointers based on AST structure.
* **Script**: `stage2_llm_synthesizer_multi.py`
* **Raw Output**: `llm_proposals_riot.json`, `llm_proposals_kinetis.json`
* **Date Finalized**: 2026-09-09

## Stage 3: The LLM Oracle (Uncertainty & Verification)
* **Result**: Tested the Oracle on AST data. Out of 53 targets evaluated:
  * 18 were **Confirmed** (Oracle perfectly matched AST semantic truth).
  * 12 were **Disagreements** (Oracle provided logically sound but slightly misaligned interpretations).
  * 23 were **Unconfident** (Oracle requested runtime fallbacks).
* **Script**: `stage3_oracle_multi.py`
* **Raw Output**: Console outputs saved in corresponding experiment logs.
* **Date Finalized**: 2026-09-09

## Stage 4: Execution Efficacy (P2IM Benchmark)
* **Result**: Tested our AST-driven harness on the strict P2IM dataset (RIOT USART case). Achieved **83.3%** accuracy covering states natively, proving AST-directed mocks provide high-fidelity state exploration compared to generic hardware simulations.
* **Script**: `evaluate_accuracy_access_level.py`
* **Raw Output**: Standard terminal output / log files.
* **Date Finalized**: 2026-09-11

## Stage 5: Static Analysis Acceleration (CodeBERT vs XGBoost)
* **Result**: 
  * **CodeBERT**: 97.4% Accuracy, 0.941 F1 Score
  * **XGBoost**: 96.2% Accuracy, 0.912 F1 Score
  * Both vastly outperformed the Majority Class Baseline (68.1% Accuracy, 0.00 F1). CodeBERT provides top-tier generalization for firmware embeddings.
* **Script**: `train_codebert.py`, `train_xgboost.py`, `compute_majority_baseline.py`
* **Raw Output**: `cb_res/` directory (CodeBERT models).
* **Date Finalized**: 2026-09-14

## Stage 6: Unit-Test Level Fuzzing Viability (Harness Compilation)
* **Result**: Successfully compiled 3 canonical libFuzzer harnesses bridging our static LLM templates into the real firmware build environment:
  * `fuzz_pl011_poll_in.cpp`
  * `fuzz_pl011_poll_out.cpp`
  * `fuzz_pl011_isr.cpp`
* **Script**: `generate_targets.py` / `build_targets.sh`
* **Raw Output**: Compiled ELF binaries inside `targets/` directory.
* **Date Finalized**: 2026-09-20

## Stage 7: RL-Driven Fuzzer Scheduling (PPO, UCB1, Q-Learning)
* **Result**: Expanded 10-seed experiment evaluating target saturation and Coupon Collector hypothesis.
  * **N=12 Target Set (Shallow):** PPO (118.10), UCB1 (107.70), Q-Learning (80.90)
  * **N=5 Target Set (Deep):** UCB1 (78.90), Q-Learning (78.50), PPO (71.40)
* **Script**: `rl_final_10seeds_parallel.py`
* **Date Finalized**: 2026-09-22
* **Supersession Notice**: The previous 5-seed Q-Learning baseline (70.20) was executed before the strict libFuzzer `-seed` fix was introduced, resulting in artificially high variance. Because this 10-seed experiment evaluated all three algorithms together in a strictly unified, deterministically-seeded environment, **these new 10-seed results supersede all prior Stage 7 metrics and serve as the canonical figures for the project.**

## Stage 7 Extension: Learned Uncertainty Ablation
* **Result**: Weighted rewards derived from the Stage 3 Oracle (Real Uncertainty mapping) vastly outperformed Random Multiplier assignment. 
  * **Real Uncertainty Multiplier**: 78.20 ± 3.97
  * **Random Multiplier**: 51.00 ± 22.27 (Variance confirmed via F-test, p=0.007).
* **Script**: `rl_strict_ablation.py`
* **Raw Output**: Console outputs saved in task logs.
* **Date Finalized**: 2026-09-20
