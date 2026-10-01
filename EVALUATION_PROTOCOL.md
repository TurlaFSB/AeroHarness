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

---

**Audit note (Oct 1 2026):** Tables 8-15 below cover real, previously-completed work (`STAGE6_HARNESS_METRICS.md`, `stage6_difficulty_metrics.md`, `corpus_growth_analysis.md`, `COST_ACCOUNTING.md`, `FAILURE_TAXONOMY.md`, `HARDWARE_MOCKING_METRICS.md`, `ABLATION_A.md`, `ABLATION_B.md`/`ABLATION_B_V2.md`) that existed in the repo as standalone files but had **zero references** from this document, `RESULTS.md`, or `README.md` until this pass. They were found and verified during an independent audit against an external evaluation-dimensions checklist that had (reasonably) concluded several of these dimensions were "not yet performed," because it could only see what the canonical docs linked. Adding them here so that checklist-style audits stop missing real, already-done work.

- [x] **Table 8: Harness Synthesis Sub-Metrics**
  - Breaks the top-line "3/3 harnesses eventually compiled" claim into 6 lifecycle sub-metrics (synthesis/compilation/linking/executable-startup/sanitizer-clean-init/valid-input-handling) per harness, with repair-iteration counts split into compile-repair vs. post-compile behavioral-repair.
  - Status: DONE (Stage 6). See `STAGE6_HARNESS_METRICS.md`. Not yet extended to the Kinetis ADC harness (Table 7) — future work.

- [x] **Table 9: Formal Difficulty Stratification**
  - Additive-point static score (cyclomatic complexity, MMIO register count, call-graph depth, init prerequisites) vs. empirical class (repair iterations, fuzzing features at plateau) across 4 functions now spanning 2 RTOSes: `pl011_poll_in`/`poll_out`/`isr` (Zephyr) and `kinetis_adc_calibrate` (RIOT, added Oct 1 2026). Documents two independent static-vs-empirical mismatches (`isr`'s hidden `K_SPINLOCK` macro expansion; `kinetis_adc_calibrate`'s self-referential register hazard) — different root causes, same general lesson. `lizard` CCN numbers independently re-verified live during this audit, not just copied from a prior log.
  - Status: DONE. See `stage6_difficulty_metrics.md`.

- [x] **Table 10: Corpus Growth and Time-to-New-Path**
  - Execution-count gaps between new-coverage discovery events for `pl011_isr`'s fuzzing session (average/max gap, with an honest limitation note that libFuzzer doesn't log wall-clock timestamps per event).
  - Status: DONE but narrow (one harness, one run). See `corpus_growth_analysis.md`. Extending to the other harnesses and the Kinetis campaign is scoped future work, not yet done.

- [x] **Table 11: Cost & Compute Accounting**
  - LLM call/token estimates (explicitly labeled as estimates where exact logging wasn't kept), wall-clock time by stage, and the project's primary real binding constraint (Gemini free-tier quota, worked around with an Ollama fallback). Updated Oct 1 2026 with a second, more severe constraint found during the Kinetis ADC run: a sandbox-level network-policy denial (not quota) with no Ollama fallback available either, worked around by disclosed direct substitution.
  - Status: DONE. See `COST_ACCOUNTING.md`.

- [x] **Table 12: Formal Failure Taxonomy**
  - Two-part taxonomy (technical/execution failures; methodology/process failures) consolidating every real failure mode documented narratively across all 7 stages. Updated Oct 1 2026 with a new sub-category (concurrency-based hardware-mock failure: 3 independently-diagnosed thread-based mocking failures plus a timer-race near-miss) and two new methodology entries (a silent Stage 1 extraction bug, Stage 3 never having gated the Kinetis benchmark path).
  - Status: DONE. See `FAILURE_TAXONOMY.md`.

- [x] **Table 13: Hardware-Mocking Formal Metrics**
  - Precision/recall/stub-synthesis-rate/divergence-rate/runtime-fault-rate table tied to specific Stage 1/4/6/7 evidence. Updated Oct 1 2026 with a second, separately-reported row for the Kinetis ADC dataset (lower divergence *rate* but higher *severity*, and a near-doubled runtime-fault rate vs. Zephyr/UART) plus a combined aggregate figure, with an explicit note that the per-dataset rows — not the blended aggregate — are the ones that should be cited.
  - Status: DONE. See `HARDWARE_MOCKING_METRICS.md`.

- [x] **Table 14: Ablation — AST/Structured Context Removal**
  - n=8 micro-sample comparing oracle-verified classifications (full AST context) against context-stripped raw-source classifications: 75% vs. 50% accuracy, -25pp degradation, concentrated on configuration-boundary registers (`cr`, `lcr_h`). Honestly scoped as a small sample, not a large-n claim.
  - Status: DONE. See `ABLATION_A.md`. Model attribution corrected Oct 1 2026 (see note below).

- [x] **Table 15: Ablation — Compiler-Oracle Feedback (Real vs. Generic)**
  - v1 (`ABLATION_B.md`, n=1/harness): zero-shot convergence on all 3 original Zephyr targets made the repair-loop-necessity question untestable on this sample; now explicitly marked superseded. v2 (`ABLATION_B_V2.md`, pre-registered, n=100 planned, paired-branching McNemar design): halted after a 10-trial pilot revealed a complete floor effect on `qwen2.5-coder:7b`/`14b` (0% success both arms on both models) — correctly reported as **inconclusive by the pre-registered criteria**, not as a negative result for H0, with the honest finding that original Stage 6 success depended on human-in-the-loop steering the fully-autonomous retry loop tested here does not have.
  - Status: DONE but inconclusive (v2's central question). Referenced once in RESULTS.md (Stage 6 section); now also listed here. **Correction (Oct 1 2026):** both documents previously attributed the original Stage 6 harnesses and the v1 re-run to a model called "Gemini 3.6 Flash," which does not match any real Gemini release. Reading `src/synthesizer/agent.py`/`config/settings.py` directly confirms the actual configured model is `gemini-1.5-pro` (fallback `gemini-2.0-flash`). Corrected in both files; flagged here because it also removes v1's "generational model discrepancy" hypothesis as a candidate explanation (both runs used the same configured primary model).
