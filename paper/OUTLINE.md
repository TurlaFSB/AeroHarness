# AeroHarness Paper Outline (v0, Oct 19 2026)

Working title (from README): **AeroHarness: Agentic, Oracle-Verified Synthesis of Fuzz Drivers for Memory-Safety Bug Hunting in Embedded Firmware**

Every number below is copied from the committed ledger (`RESULTS.md`, `EVALUATION_PROTOCOL.md`, `ABLATION_*.md`). Nothing here is new data. `[GAP]` marks something the paper needs that the repo does not yet have.

---

## 0. Decide first (these change the whole paper)

1. **Venue + page limit + template.** Not stated anywhere in the repo. Systems-security venue vs. an empirical/negative-results track changes how much weight sections 6 and 7 get.
2. **Contribution framing.** The evidence supports "a validated pipeline plus an honest empirical and methodological study of where semantic modeling helps and doesn't," not "a tool that finds bugs." Objective 4 (previously unknown vulnerabilities) currently stands at zero on unmodified targets (`RESULTS.md`, Item 6).
3. **FreeRTOS claim.** The old LaTeX template's abstract says "evaluated across real-world FreeRTOS." No FreeRTOS target has been run. Either run it (Crazyflie) or cut the claim everywhere.

---

## 1. Abstract (write last)
Problem (manual harness engineering blocks embedded fuzzing) → gap → approach → 3 headline results → honest scope statement.

## 2. Introduction
- Embedded firmware fuzzing bottleneck: MMIO hardware coupling + manual harness effort.
- The gap: Fuzzware (USENIX Sec '22) models MMIO dynamically but has no semantic code understanding; QuartetFuzz (Sheng et al., arXiv:2605.21824) uses an LLM agent for harness generation but only on software libraries, never hardware-dependent code. No prior work combines LLM semantic understanding with Fuzzware-style register modeling. `[GAP]` re-verify this novelty claim with a fresh literature search right before submission.
- Contributions (draft):
  - C1. Pipeline: AST/call-graph mining → LLM MMIO proposals (Fuzzware's 5 categories) → static verification oracle → harness synthesis with compiler-driven self-repair.
  - C2. Empirical study of when semantic MMIO modeling pays off (informed vs. blind vs. blackbox).
  - C3. Negative results: supervised DL, RL scheduling at unit-test scale, small local models for autonomous self-repair.
  - C4. Methodology: static-mocking failure taxonomy and a measurement-validity case study (reward hacking through raw coverage counters).
  - C5. Validation: CVE-2020-10062 positive control and a Fuzzware head-to-head on the same driver.
  - C6. `[CONTINGENT]` a responsibly disclosed finding, only if it is confirmed and documented in the repo (see 9).

## 3. Background and Related Work
Fuzzware, P2IM, µEMU/MULTIFUZZ, QuartetFuzz, LLM fuzz-driver generation, RL-guided fuzzing. `[GAP]` the repo's Related Work lists only 3 papers; a submission needs a real survey. Verify every citation (do not copy from the legacy template).

## 4. Problem Statement and Design Goals
Input: firmware driver source. Output: compilable, sanitizer-clean harness plus register model. Explicit scope: host-side harness fuzzing with static MMIO mocking, not full-system emulation. Stage 3 is deliberately a static approximation of Fuzzware's dynamic symbolic execution (faculty-approved scope decision), so state it upfront.

## 5. System Design
Use `architecture.svg` (shared front end forks into Validation Track and Case-Study Track).
- 5.1 Stage 1 semantic analysis (libclang, call graph, ordering edges)
- 5.2 Stage 2 LLM register modeling (Constant/Passthrough/Bitextract/Set/Identity)
- 5.3 Stage 3 static verification oracle (Confirmed/Disagreement/Unconfident)
- 5.4 Stage 6 harness synthesis, compiler-oracle self-repair, state-machine dispatcher
- 5.5 Stage 7 RL scheduling using Stage 3 uncertainty as a reward signal

## 6. Evaluation
### 6.1 Setup
Targets: Zephyr `uart_pl011.c` (+ MQTT), RIOT/Kinetis K64F ADC, P2IM unit-test benchmark (third-party ground truth). Models used per result (pin these; see Threats). Stats methods: Wilson CIs, paired t-tests, McNemar's exact, Holm-Bonferroni, Fisher's exact, multi-seed protocol.

### 6.2 Research questions → evidence

| RQ | Question | Result in repo | Source |
|---|---|---|---|
| RQ1 | Can an LLM model MMIO behavior accurately? | 83.3% (35/42), Wilson 95% CI [69.4, 91.7], STM32/RIOT USART. Kinetis: Ollama 52.8% (227/430); Gemini spot-check ~77–80% (10/13, only 5 unique registers) | Tables 2, RESULTS Stage 4 |
| RQ1b | Does the oracle add anything? | 53 accesses: 18 Confirmed, 12 Disagreement, 23 Unconfident. Kinetis ADC: 5/0/13 | Table 1 |
| RQ2 | Does supervised DL beat zero-shot? | No. CodeBERT 54.0±24.4, XGBoost 45.7±25.3, majority 40.4±33.9, all p>0.10; zero-shot 83.3 | Table 3 |
| RQ3 | Does agentic self-repair produce working harnesses? | 5/5 harnesses reached compiled+executing state (KPI ≥80%). Caveat: definition is compile+start, and local 7B/14B models hit a floor | RESULTS KPI section, Table 15 |
| RQ3b | Does the compile loop itself matter? | 7B: 4% vs 14%, McNemar p=0.0020, but all rescues on 2 of 5 targets. 14B: 4% vs 5%, p=1.0. Rescue rate 1/96 vs 10/96 (Fisher p=0.0096). Prompt-scaffold defect depresses both | Table 16, ABLATION_G |
| RQ3c | Do lint warnings help? | `[GAP]` Ablation E (Table 17) results not in | Table 17 |
| RQ4 | Does semantic modeling beat blind/blackbox fuzzing? | Not a blanket multiplier. `poll_in`, `isr`: identical ceilings. `poll_out`: informed reaches deeper pre-hang state 9/10 seeds vs blind 3/10. Blackbox hangs immediately 10/10 | Table 6, blackbox section |
| RQ5 | Does it find real bugs? | CVE-2020-10062 positive control detected (610/809/1445 execs, 3 seeds), explicitly not a discovery. Scale campaign: ~486M/492M/95M execs, zero new bug classes. Real unmodified-target findings: zero | RESULTS Items 6, MQTT |
| RQ5b | vs. the field reference tool? | Fuzzware vs. host dispatcher on same driver: both plateau, 0 crashes; Fuzzware ~20–22k vs ~1.0M exec/s (~45–50x) | Item 7 |
| RQ6 | Does RL scheduling help? | N=12: Q 80.90±22.20, UCB1 107.70±13.75, PPO 118.10±15.69 (UCB1>Q p=0.0031, Holm). N=5: no sig. diff. Uncertainty signal: variance reduction (F=17.42, p<0.01), 80.80±4.53 vs 73.20±18.90. Sequencing: flat 29 PCs across all policies | Tables 4–5 |

### 6.3 Dispatcher coverage reporting
Report llvm-cov, not raw sancov: dispatcher is 29.43% lines / 35.00% branches of the real driver. "76 PCs" must never appear as a coverage percentage.

## 7. Methodology Lessons (candidate distinctive section)
- Static-mocking limitation classes: fuzzer-controlled busy-wait, W1C clobbering, self-set-and-spin (unfuzzable under single-shot mocks; fixed with periodic POSIX timer after 3 failed thread-based attempts).
- The 8-point RL measurement failure chain (8-bit counter wraparound → … → `no_sanitize("coverage")` + llvm-cov).
- Reproducibility failures found by audit: `-O1` dead-code elimination hiding the CVE crash, include-path collision, UTF-16 `.gitignore`, fabricated RESULTS.md, silent script overwrite.

## 8. Discussion and Limitations
- Shallow targets are the binding constraint (Coupon Collector explanation for RL, 90% single-episode ceiling for sequencing).
- Self-repair claim depends on a frontier model plus human steering; autonomous local-model result is a floor effect.
- Single-peripheral accuracy benchmark; small n at several points.
- Stage 3 confirms only 18/53 (34%).

## 9. Ethics and Responsible Disclosure
`[GAP]` If the `pl011_set_baudrate` candidate is reported to Zephyr, it needs a repo-level write-up (root cause, reproducer, ASan/UBSan trace, disclosure timeline) before it can become C6. It is not documented in the committed files I read.

## 10. Conclusion and Future Work
FreeRTOS/drone-controller target, deeper stateful drivers for RL, DMA/interrupt semantics, human-effort study.

## Appendix
Reproduction guide (`REPRODUCE.md`), failure taxonomy (`FAILURE_TAXONOMY.md`), cost accounting, per-harness metrics, evaluation-dimension coverage table.

---

## Paper-readiness problems (fix before writing prose)

1. **`scripts/generate_latex_paper_template.py` is unusable as-is.** Its table claims 78.4% branch coverage, 40% single-shot baseline, ≤3.5 repair iterations, "Automated" PoVs, FreeRTOS evaluation, and a placeholder lab name and email. None of this is supported by the audited results. Replace it with a template built from section 6's real numbers.
2. **Abstract-level claims must shrink to the evidence.** "Synthesizes reproducible PoV artifacts" and "discovers memory-safety violations autonomously" are not backed by any unmodified-target finding.
3. **The ≥80% KPI is generous.** 5/5 counts compile+link+start, with n=5, from one model family, with documented human steering in the original Zephyr runs. Report it with the definition stated, next to the 50%/80% runtime-fault rates.
4. **Open reproducibility item:** Stage 1's MMIO access count (53 claimed) should be re-run fresh and reconciled before Table 1 is final.
5. **Model attribution churn.** Results were produced under different configured Gemini models over time. Each table needs the exact model and date pinned.
6. **Unpinned provenance:** Zephyr commit hash was not preserved. Pin it.
7. **Thin sections:** Table 10 (corpus growth) is one harness/one run; Table 14 is n=8; Kinetis Gemini check is n=13 over 5 unique registers; Ablation E pending; human-effort study not done.
8. **Stats hygiene:** state multiple-comparison correction wherever more than one test is reported (done for RL, not uniformly elsewhere).
