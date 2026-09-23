# AeroHarness

**Autonomous Embedded-Target Reasoning and Oracle-Guided Harness Synthesis**  
*Feedback-Driven Agentic Synthesis of Fuzz Drivers for Memory-Safety Bug Hunting in Embedded Firmware*

## Overview

AeroHarness is a Cyber Reasoning System (CRS) designed to automate the lifecycle of fuzz harness engineering for embedded C/C++ firmware. 
Embedded firmware powering critical IoT infrastructure and RTOS is predominantly written in memory-unsafe C/C++, yet applying coverage-guided fuzzing (e.g., AFL++, libFuzzer) is severely bottlenecked by the manual effort required to reverse-engineer code and construct hardware-mocking entrypoint harnesses.

While tools like **Fuzzware** and **QuartetFuzz** have pushed the boundaries of MMIO modeling and firmware re-hosting, synthesizing the actual entrypoint harnesses that reliably exercise complex, stateful RTOS components (like interrupts and protocol parsers) remains a manual, error-prone task. AeroHarness bridges this gap by introducing an agentic, LLM-driven loop that synthesizes, validates, and refines fuzz drivers via compiler feedback and active reinforcement learning.

## Pipeline Stages (1-7)

This repository contains the complete implementation of the AeroHarness pipeline across 7 distinct research stages:

1. **Stage 1 (AST Mining & Context Extraction):** Scripts (`stage1_ast_parser.py`) to parse C ASTs, type definitions, and call-graphs to identify target APIs.
2. **Stage 2 (Agentic Synthesis):** Initial harness generation using LLMs (`stage2_llm_synthesizer_multi.py`, `stage2_kinetis_gemini.py`), creating libFuzzer entrypoints with stubbed MMIO and RTOS dependencies.
3. **Stage 3 (Deterministic Self-Repair & Oracle):** A compiler-in-the-loop repair oracle (`stage3_oracle_multi.py`) that captures Clang diagnostics to iteratively fix syntax and initialization errors autonomously, labeling targets with confidence/uncertainty.
4. **Stage 4 (AST-Guided Pruning):** Heuristic filtering (`filter_ast.py`, `prune.py`) to reduce the search space by eliminating trivial getters/setters.
5. **Stage 5 (Machine Learning Triage):** CodeBERT and XGBoost models (`train_codebert.py`, `train_xgboost.py`) trained on the AST features to predict API fuzzability.
6. **Stage 6 (Fuzzing Campaign Execution):** Deep target decomposition (`generate_deep_targets.py`) and parallel libFuzzer execution scripts.
7. **Stage 7 (Reinforcement Learning Scheduler):** The final RL scheduler (`rl_final_10seeds_parallel.py`, `rl_strict_ablation.py`) that leverages Stage 3 uncertainty signals to optimally allocate step budgets across shallow vs. deep embedded targets.

## Current Project Status

The pipeline has been fully implemented, validated, and evaluated on a series of embedded benchmarks (including `uart_pl011`). 
Key validated achievements:
- **Oracle-Guided Repair**: Demonstrated that the compiler-in-the-loop oracle repairs broken LLM harnesses with 100% success on the target set.
- **Deep Target Fuzzing**: Decomposed large peripheral components into discrete register-level fuzzing targets (e.g., `CTSMIM`, `w1c_clobber`).
- **RL-Guided Scheduling**: Validated that stateless UCB1 bandits, when weighted by the Oracle's uncertainty signals, completely avoid the catastrophic starvation traps that naive Q-learning falls into when facing shallow targets, safely securing deep-target coverage without suffering the variance of pure random search.

## Repository Structure

* **`/legacy_v1/`** - Historical reference only (contains the initial pre-audit aspirational mock architecture).
* **`/*_ast.py`, `*oracle*.py`, `rl_*.py`** - Core pipeline scripts for stages 1-7 in the root directory.
* **`/*.json`** - Extracted ASTs and LLM proposal datasets.
* **`deep_targets/`** - Separated fuzzing corpora and executable harness artifacts.
* **`cb_*/`** - Model checkpoints and embeddings for CodeBERT.

*(Note: The repository scripts are currently centralized in the root directory to preserve relative paths for dataset loading and shell compilation commands. A larger structural refactor into `src/` and `benchmarks/` is pending.)*

## Reproducing Results

To run the final Stage 7 strict ablation study (which pairs the UCB1 scheduler against random weightings on the deep target set):
```bash
python3 rl_strict_ablation.py
```
This script tightly controls the libFuzzer PRNG seeds to guarantee perfectly paired execution environments.

