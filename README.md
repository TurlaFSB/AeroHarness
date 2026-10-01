# AeroHarness

**AeroHarness: Agentic, Oracle-Verified Synthesis of Fuzz Drivers for Memory-Safety Bug Hunting in Embedded Firmware**

## Overview

AeroHarness is a research prototype exploring how LLM agents, combined with deterministic verification oracles, can automate fuzz-harness engineering for embedded C/C++ firmware. Coverage-guided fuzzing (AFL++, libFuzzer) is the standard for memory-safety bug discovery, but applying it to embedded firmware is bottlenecked by the manual effort needed to reverse-engineer hardware and build entrypoint harnesses.

The gap this project targets: existing work addresses one half of this problem each. Fuzzware (USENIX Security '22) automatically models hardware/MMIO register behavior via dynamic symbolic execution, but has no semantic understanding of code. QuartetFuzz uses an LLM agent to generate fuzz harnesses with source-level correctness checks, but has only ever been applied to regular software libraries — never to firmware requiring hardware mocking. AeroHarness combines both: an LLM agent proposes hardware register behavior using semantic code understanding, and that proposal is verified against real code-usage patterns before being trusted and used to synthesize working fuzz harnesses.

## Architecture

![AeroHarness Pipeline Architecture](architecture.svg)

Stages 1–3 form a shared front end (AST parsing, LLM register-model proposal, static verification) that then forks into two tracks: a **Validation Track** (Stages 4–5), which benchmarks the front end's accuracy against the third-party P2IM dataset and tests whether a trained classifier can match it, and a **Case-Study Track** (Stages 6–7), which applies the same verified models to synthesize working fuzz harnesses for a real Zephyr driver and uses RL to guide fuzzing time and input sequencing against them. Two dashed arrows show artifacts reused directly across tracks rather than passed down the main pipeline: Stage 1's call-graph data into Stage 6, and Stage 3's uncertainty signal into Stage 7.

## Pipeline Stages (1-7)

* **Stage 1 — Semantic Analysis**: Real AST-based parsing (`stage1_ast_parser.py`, via libclang) extracts function signatures, call relationships, and MMIO/hardware register accesses from firmware source. Generalized across RTOS codebases (validated on Zephyr and RIOT OS).
* **Stage 2 — LLM-Proposed MMIO Models**: For each hardware register access, an LLM (Gemini and/or local Qwen2.5-Coder via Ollama) proposes a Fuzzware-style behavior model — Constant, Passthrough, Bitextract, Set, or Identity — with grounded reasoning (`stage2_llm_synthesizer_multi.py`, `stage2_kinetis_gemini.py`). Includes automatic Gemini-to-Ollama failover for free-tier quota limits.
* **Stage 3 — Static Verification Oracle**: A code-pattern-based checker (`stage3_oracle_multi.py`) cross-checks each LLM-proposed model against real AST usage patterns. Explicitly a simplified static approximation of Fuzzware's dynamic symbolic execution, documented as such (faculty-approved scope decision).
* **Stage 4 — Dataset Benchmarking**: Evaluated against P2IM, the standard benchmark used by Fuzzware and related work, across two microcontroller architectures (STM32, NXP Kinetis) and 5 peripheral types. Achieved 83.3% [95% CI: 69.4%–91.7%] access-level accuracy on the STM32/RIOT USART benchmark against P2IM's published ground truth (script: `evaluate_accuracy_canonical.py`).
* **Stage 5 — Deep Learning Classifier**: Fine-tuned CodeBERT and an XGBoost baseline trained on the Stage 4 dataset, evaluated against a majority-class baseline with formal significance testing. Honest finding: neither trained model (CodeBERT 54.0%±24.4%, XGBoost 45.7%±25.3%) significantly outperforms naive majority-class guessing (40.4%±33.9%, all p>0.10), while zero-shot LLM inference (83.3%) meaningfully outperforms both.
* **Stage 6 — Harness Synthesis & Self-Repair Loop**: Real libFuzzer harnesses generated for 3 functions (`pl011_poll_in`, `pl011_poll_out`, `pl011_isr`) spanning read, write, and interrupt paths. Compilation failures are fed to the LLM as real diagnostics, repeated until success (bounded retry). Surfaced two real static-mocking limitations: busy-wait timeouts and write-1-to-clear register clobbering.
  * **Enhancement 1 (State-Machine Dispatcher)**: Built a unified harness bridging the 3 isolated functions using call-graph-inferred initialization sequences (Stage 1 data). Reaches more total coverage than any isolated harness, but only ~29% of the real driver's lines/~35% of its branches by independent `llvm-cov` measurement — the raw sancov PC count alone overstates this and should not be read as a coverage percentage (see `RESULTS.md` for the full isolated-vs-dispatcher comparison, independently re-verified and corrected Oct 1 2026).
  * **Enhancement 2 (MQTT UBSan)**: Triaged an initial UBSan violation on the Zephyr MQTT `properties_decode` function, definitively classifying and fixing it as a harness artifact (mock macro promotion bug), not a vulnerability. Independently reproduced (Oct 1 2026): the pre-fix macro reproduces the exact UBSan error, the patched version is clean.
  * **Enhancement 3 (Ground-Truth Methodology Validation)**: Validated pipeline capability against a known positive control (CVE-2020-10062: MQTT off-by-one). Proved that isolated harnesses are blind to this API contract violation, but a broad-scope, call-graph-aware harness modeling a naive application consumer detects the memory corruption within hundreds to low thousands of executions (<1 second). (Explicitly a positive-control validation, not a new discovery.) Independently re-verified and fixed (Oct 1 2026): the harness originally failed to reproduce this at the project's own documented `-O1` build flag — LLVM's optimizer was dead-code-eliminating the vulnerable code path — now fixed and reproducible (see `RESULTS.md`).
  * **Informed-vs-blind harness ablation (Oct 1 2026)**: Tested whether Stage 2/3's semantic MMIO modeling actually earns more coverage than an engineer with no hardware-semantic analysis would get from raw-fuzzing the whole register struct. Finding: it's **not a blanket coverage multiplier**. For shallow functions with few branches (`poll_in`, `isr`), a blind harness that raw-memcpy's fuzzer bytes onto the whole struct converges to the *identical* coverage ceiling as the informed harness, in well under 20,000 executions either way. The real, measurable benefit shows up specifically on `poll_out`, which has a single-bit hazard (`PL011_FR_TXFF`) that causes an immediate hang: the informed harness (which isolates that bit into a dedicated byte) reached the deeper pre-hang coverage state in 9/10 seeds, vs. only 3/10 for the blind harness, which has to find that same bit by chance inside a 76-byte raw blob. See `RESULTS.md` for the full methodology, multi-seed data, and `llvm-cov` cross-validation.
* **Stage 7 — Uncertainty-Guided RL Scheduling & State-Machine Sequencing**: 
  * **Ablation**: Q-learning, UCB1, and PPO agents trained to prioritize fuzzing time using Stage 3's uncertainty data as an added reward signal. Characterized, via the Coupon Collector's Problem (empirically validated), the scale at which scheduling helps vs. random search. An ablation confirmed the real uncertainty signal provides a statistically significant robustness/variance-reduction benefit (F=17.42, p<0.01), not a mean-performance one. 10-seed final results across all 3 algorithms confirmed.
  * **RL-Guided Sequencing (Methodology Case Study)**: Extended the RL framework to select API sequences for the Stage 6 state-machine dispatcher, completely decoupling sequence length from libFuzzer's mutational payload. Initial results appeared to show Q-learning outperforming Random (54 vs 41 PCs). However, an exhaustive 8-point measurement audit unmasked every apparent RL victory as a reward-hacking vulnerability or measurement artifact (e.g., unsigned underflows, debug `printf` self-rewards, and harness-router branch inflation). Applying a rigorous structural fix (`__attribute__((no_sanitize("coverage")))` + `-fno-inline`) strictly scoped coverage to the target driver. Independent `llvm-cov` source-profiling confirmed the true, artifact-free result: **all algorithms (Random, UCB1, Q-learning) converge to identically flat driver-level coverage (29 PCs).** This honest null result is a reflection of the benchmark's shallow state space (a single 10-step random sequence hits 90% of branches), not a general claim about RL. The real contribution is the rigorous methodology case study mapping the failure modes of raw coverage counters in RL-guided fuzzing (see `RESULTS.md`).

## Current Project Status

All 7 stages implemented and empirically evaluated with real execution evidence. See `RESULTS.md` for the canonical results ledger with links to raw logs. Key findings:

* Semantic parsing generalizes across RTOS codebases (Zephyr, RIOT).
* 83.3% MMIO-classification accuracy [95% CI: 69.4%–91.7%] against P2IM (STM32/RIOT).
* Zero-shot LLM reasoning outperforms trained deep learning, formally confirmed via significance testing.
* Real compiler-driven self-repair loop demonstrated on 3 functions.
* RL-guided scheduling characterized across 3 algorithms and 10 seeds: no mean-performance advantage at unit-test scale, but a significant robustness benefit.
* Informed-vs-blind harness ablation (Oct 1 2026): semantic MMIO modeling is not a blanket coverage multiplier — it makes no measurable difference on shallow functions, but meaningfully increases the odds of reaching deeper coverage before an unguided fuzzer stumbles into a single-bit hazard inside a much larger raw search space.
* Ongoing verification: a prompt-methodology inconsistency was found between our Zephyr and Kinetis Stage 2 scripts and corrected; a Gemini spot-check on the corrected prompt (n=13, see `RESULTS.md`) tentatively supports consistent performance across architectures, though the sample's limited register diversity means this remains a preliminary finding.
* Independent re-audit (Oct 1 2026): Stage 6's isolated-harness coverage numbers, the MQTT UBSan classification, the CVE-2020-10062 positive control, and the Stage 6 coverage measurement method were each re-verified from scratch against the actual repo (not just the prose claims). Two real defects were found and fixed in the process — stale/incorrect isolated-harness coverage numbers, and a build-flag-dependent false negative in the CVE positive control — and `llvm-cov` cross-validation (previously missing for Stage 6) was added for all four Stage 6 harnesses. See `RESULTS.md` for full detail.

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
python3 rl_strict_ablation.py       # Stage 7 scheduling ablation (F=17.42, p<0.01) — verified current (Oct 1 2026)
python3 run_llvm_cov.py             # Stage 7 sequencing case study: consolidated harness (fuzz_consolidated.c)
                                     # + independent llvm-cov cross-validation — reproduces the flat-29-PC null
                                     # result across all 6 conditions (verified Oct 1 2026)
```

## Related Work

* **Fuzzware** (Scharnowski et al., USENIX Security 2022) — our Stage 2/3 taxonomy is adopted from this paper.
* **QuartetFuzz** (Sheng et al., 2026) — our Stage 6 self-repair loop design is informed by this paper's bounded-retry approach.
* **P2IM** (Feng et al., USENIX Security 2020) — the benchmark dataset used in Stage 4.
