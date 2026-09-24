# AeroHarness

**Autonomous Embedded-Target Reasoning and Oracle-Guided Harness Synthesis Feedback-Driven Agentic Synthesis of Fuzz Drivers for Memory-Safety Bug Hunting in Embedded Firmware**

## Overview

AeroHarness is a research prototype exploring how LLM agents, combined with deterministic verification oracles, can automate fuzz-harness engineering for embedded C/C++ firmware. Coverage-guided fuzzing (AFL++, libFuzzer) is the standard for memory-safety bug discovery, but applying it to embedded firmware is bottlenecked by the manual effort needed to reverse-engineer hardware and build entrypoint harnesses.

The gap this project targets: existing work addresses one half of this problem each. Fuzzware (USENIX Security '22) automatically models hardware/MMIO register behavior via dynamic symbolic execution, but has no semantic understanding of code. QuartetFuzz uses an LLM agent to generate fuzz harnesses with source-level correctness checks, but has only ever been applied to regular software libraries — never to firmware requiring hardware mocking. AeroHarness combines both: an LLM agent proposes hardware register behavior using semantic code understanding, and that proposal is verified against real code-usage patterns before being trusted and used to synthesize working fuzz harnesses.

## Pipeline Stages (1-7)

* **Stage 1 — Semantic Analysis**: Real AST-based parsing (`stage1_ast_parser.py`, via libclang) extracts function signatures, call relationships, and MMIO/hardware register accesses from firmware source. Generalized across RTOS codebases (validated on Zephyr and RIOT OS).
* **Stage 2 — LLM-Proposed MMIO Models**: For each hardware register access, an LLM (Gemini and/or local Qwen2.5-Coder via Ollama) proposes a Fuzzware-style behavior model — Constant, Passthrough, Bitextract, Set, or Identity — with grounded reasoning (`stage2_llm_synthesizer_multi.py`, `stage2_kinetis_gemini.py`). Includes automatic Gemini-to-Ollama failover for free-tier quota limits.
* **Stage 3 — Static Verification Oracle**: A code-pattern-based checker (`stage3_oracle_multi.py`) cross-checks each LLM-proposed model against real AST usage patterns. Explicitly a simplified static approximation of Fuzzware's dynamic symbolic execution, documented as such (faculty-approved scope decision).
* **Stage 4 — Dataset Benchmarking**: Evaluated against P2IM, the standard benchmark used by Fuzzware and related work, across two microcontroller architectures (STM32, NXP Kinetis) and 5 peripheral types. Achieved 83.3% [95% CI: 69.4%–91.7%] access-level accuracy on the STM32/RIOT USART benchmark against P2IM's published ground truth (script: `evaluate_accuracy_canonical.py`).
* **Stage 5 — Deep Learning Classifier**: Fine-tuned CodeBERT and an XGBoost baseline trained on the Stage 4 dataset, evaluated against a majority-class baseline with formal significance testing. Honest finding: neither trained model (CodeBERT 54.0%±24.4%, XGBoost 45.7%±25.3%) significantly outperforms naive majority-class guessing (40.4%±33.9%, all p>0.10), while zero-shot LLM inference (83.3%) meaningfully outperforms both.
* **Stage 6 — Harness Synthesis & Self-Repair Loop**: Real libFuzzer harnesses generated for 3 functions (`pl011_poll_in`, `pl011_poll_out`, `pl011_isr`) spanning read, write, and interrupt paths. Compilation failures are fed to the LLM as real diagnostics, repeated until success (bounded retry). Surfaced two real static-mocking limitations: busy-wait timeouts and write-1-to-clear register clobbering.
* **Stage 7 — Uncertainty-Guided RL Scheduling**: Q-learning, UCB1, and PPO agents trained to prioritize fuzzing time using Stage 3's uncertainty data as an added reward signal. Characterized, via the Coupon Collector's Problem (empirically validated), the scale at which scheduling helps vs. random search. An ablation confirmed the real uncertainty signal provides a statistically significant robustness/variance-reduction benefit (F=17.42, p<0.01), not a mean-performance one. 10-seed final results across all 3 algorithms confirmed.

## Current Project Status

All 7 stages implemented and empirically evaluated with real execution evidence. See `RESULTS.md` for the canonical results ledger with links to raw logs. Key findings:

* Semantic parsing generalizes across RTOS codebases (Zephyr, RIOT).
* 83.3% MMIO-classification accuracy [95% CI: 69.4%–91.7%] against P2IM (STM32/RIOT).
* Zero-shot LLM reasoning outperforms trained deep learning, formally confirmed via significance testing.
* Real compiler-driven self-repair loop demonstrated on 3 functions.
* RL-guided scheduling characterized across 3 algorithms and 10 seeds: no mean-performance advantage at unit-test scale, but a significant robustness benefit.
* Ongoing verification: a prompt-methodology inconsistency was found between our Zephyr and Kinetis Stage 2 scripts and corrected; a Gemini spot-check on the corrected prompt (n=13, see `RESULTS.md`) tentatively supports consistent performance across architectures, though the sample's limited register diversity means this remains a preliminary finding.

## Datasets & Provenance

All datasets are real, publicly available, third-party sources.

* **Zephyr uart_pl011.c**: `drivers/serial/uart_pl011.c` from the official Zephyr RTOS repository, downloaded August 2026 (exact commit hash not preserved; pinning is noted as future work).
* **P2IM unit test benchmark**: `github.com/RiS3-Lab/p2im-unit_tests` (Feng et al., USENIX Security 2020), the standard benchmark also used by Fuzzware. Vendored directly into `/p2im-unit_tests/`. Test cases used: RIOT/USART/f103 (STM32F103), SPI/I2C/ADC/TIMER under Kinetis K64F. Ground-truth labels taken as-is from the original authors' CSVs.
* **RIOT OS driver sources**: from within the vendored P2IM repo's bundled RIOT environment.

## Repository Structure

* `/legacy_v1/` — Historical reference only; pre-audit implementation with fabricated/stubbed components, kept for transparency.
* **Root directory** — Core pipeline scripts for Stages 1–7 (flat layout; refactor into `src/`/`benchmarks/` planned but not executed, to preserve reproducibility of existing results).
* `/*.json` — Extracted ASTs and LLM MMIO proposal datasets.
* `/harnesses/`, `/targets/` — Generated fuzz harness sources, compiled binaries, deep-target decompositions.
* `/cb_*/` — CodeBERT checkpoints (Stage 5).
* `/p2im-unit_tests/`, `/zephyr-src/` — Vendored third-party datasets.
* `RESULTS.md` — Canonical results ledger.
* `EVALUATION_PROTOCOL.md` — Definitive list of paper tables/results.
* `REPRODUCE.md` — Independent reproduction guide.

## Reproducing Key Results

See `REPRODUCE.md` for full setup. Quick start:

```bash
python3 stage1_ast_parser.py <path_to_driver.c>
python3 evaluate_accuracy_canonical.py
python3 rl_strict_ablation.py
```

## Related Work

* **Fuzzware** (Scharnowski et al., USENIX Security 2022) — our Stage 2/3 taxonomy is adopted from this paper.
* **QuartetFuzz** — our Stage 6 self-repair loop design is informed by this paper's bounded-retry approach.
* **P2IM** (Feng et al., USENIX Security 2020) — the benchmark dataset used in Stage 4.
