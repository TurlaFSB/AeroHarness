# AeroHarness Results Ledger

This document serves as the single source of truth for all canonical, finalized numbers in the AeroHarness project.

## Stage 1: C/C++ AST Parsing Verification
* **Result**: Successfully parsed and filtered hardware-interaction AST nodes from multiple real-world firmware HALs (Kinetis, STM32). Extracted MMIO reads/writes, pointers, and memory-mapped offsets.
* **Script**: `stage1_ast_parser.py`, `filter_ast.py`
* **Raw Output**: `ast_combined.json`
* **Verification Status**: VERIFIED (File exists in repo)
* **Date Finalized**: 2026-09-09

## Stage 2: MMIO Classification (LLM Synthesizer)
* **Result**: LLM successfully generated compilable C++ libFuzzer harnesses mimicking MMIO structures by classifying hardware structs and injecting fake pointers based on AST structure.
* **Script**: `stage2_llm_synthesizer_multi.py`
* **Raw Output**: `llm_proposals_riot.json`, `llm_proposals_kinetis.json`
* **Verification Status**: VERIFIED (Files exist in repo)
* **Date Finalized**: 2026-09-09

## Stage 3: The LLM Oracle (Uncertainty & Verification)
* **Result**: Tested the Oracle on AST data. Out of 53 targets evaluated:
  * 18 were **Confirmed** (Oracle perfectly matched AST semantic truth).
  * 12 were **Disagreements** (Oracle provided logically sound but slightly misaligned interpretations).
  * 23 were **Unconfident** (Oracle requested runtime fallbacks).
* **Script**: `stage3_oracle.py`
* **Raw Output**: `stage3_oracle_output.log`
* **Verification Status**: VERIFIED. (Note: The canonical 18/12/23 result is specific to the original `uart_pl011.c` target set. Reproducing this exact number requires running `stage3_oracle.py` against `llm_proposals.json` specifically, NOT the later combined multi-architecture dataset).
* **Date Finalized**: 2026-09-09

## Stage 4: Execution Efficacy (P2IM Benchmark)
* **Result (Zephyr/STM32)**: Achieved **83.3% [95% CI: 69.4%–91.7%]** accuracy (35/42) covering states natively, proving AST-directed mocks provide high-fidelity state exploration.
* **Result (Kinetis/K64F - Ollama)**: Achieved **52.8%** accuracy (227/430) using the correctly-prompted Ollama backend. This explicitly supersedes the original flawed-prompt Kinetis classification which scored 56.0% (241/430).
* **Result (Kinetis/K64F - Gemini Spot-Check)**: Achieved **~77-80%** accuracy (10/13 valid) on a stratified sample of Kinetis registers using the correctly-prompted Gemini backend.
* **Script**: `evaluate_accuracy_canonical.py` (Zephyr) / `evaluate_kinetis.py` (Kinetis)
* **Raw Output**: `stage4_p2im_output.log` / `llm_proposals_kinetis_v2.json`
* **Verification Status**: VERIFIED. (Note: The canonical 83.3% result uses strict individual-access scoring where C&SR registers reject "passthrough". A rejected loose-scoring variant exists in the repo as `evaluate_accuracy_REJECTED_loose_scoring.py` and must NOT be used).
* **Date Finalized**: 2026-09-24
* **Methodology Flag (Cross-Architecture Consistency)**: Initial cross-architecture comparison suggested consistent ~83% performance across Zephyr/STM32 and Kinetis. A prompt-methodology inconsistency was subsequently found between the two Stage 2 scripts and has been corrected. Re-evaluation using the corrected prompt via the Ollama backend shows Kinetis accuracy of 52.8%.
* However, an apples-to-apples spot-check using the corrected prompt with **Gemini** achieved ~77-80% accuracy, compared to Ollama's 46.2% on the exact same subset. (13 total classifications across 5 unique register names. Note: MCG_C1, MCG_C2, and MCG_S are shared clock-configuration registers appearing across multiple peripheral files, so this sample is less architecturally diverse than a naive reading of 'stratified across 4 peripherals' would suggest). This partial sample (n=13, dominated by a small number of unique registers, notably MCG clock-configuration registers repeated across peripherals) suggests Gemini's performance on Kinetis under the corrected prompt is comparable to its Zephyr performance (~77-80% vs 83.3%), tentatively supporting the original stable-ceiling hypothesis — but the small, register-diversity-limited sample means this should be treated as suggestive rather than conclusive.
*  A larger, more diverse sample (ideally including non-MCG registers specific to each peripheral, not just shared clock-config registers) would be needed for full confidence.

## Stage 5: Static Analysis Acceleration (CodeBERT vs XGBoost vs Zero-Shot)
* **Result**: 
  * **CodeBERT**: 54.0% ± 24.4%
  * **XGBoost**: 45.7% ± 25.3%
  * **Majority-Class Baseline**: 40.4% ± 33.9%
  * **Zero-Shot LLM (Gemini)**: 83.3%
  * **Significance Tests (Paired t-test)**:
    * CodeBERT vs XGBoost: p=0.1069 (Cohen's d=0.298) — Statistically indistinguishable
    * CodeBERT vs Majority: p=0.1792 (Cohen's d=0.412) — Statistically indistinguishable
    * XGBoost vs Majority: p=0.3844 (Cohen's d=0.158) — Statistically indistinguishable
  * Finding: Both trained models barely beat naive guessing due to severe small-N sample sizes. Zero-shot LLM vastly outperformed both.
* **Script**: `evaluate_backend.py`, `train_codebert.py`, `train_xgboost.py`, `compute_majority_baseline.py`
* **Raw Output**: `stage5_results_summary.md` (Transcribed from interactive sessions. Raw logs missing, but weights preserved in `cb_res/`)
* **Verification Status**: VERIFIED via summary file.
* **Date Finalized**: 2026-09-14

## Stage 6: Unit-Test Level Fuzzing Viability (Harness Compilation)
* **Result**: Successfully compiled 3 canonical libFuzzer harnesses bridging our static LLM templates into the real firmware build environment via a bounded compiler-driven self-repair loop (max 5 retries):
  * `fuzz_pl011_poll_in.cpp`
  * `fuzz_pl011_poll_out.cpp`
  * `fuzz_pl011_isr.cpp`
* **Limitations Identified**: The repair loop successfully surfaced two concrete static-mocking limitations where generated behavior was inconsistent with real hardware semantics:
  1. Busy-wait timeout behavior (infinite loops due to missing hardware state updates).
  2. Write-1-to-clear (W1C) register clobbering.
* **Ablation Note**: See [ABLATION_B_V2.md](./ABLATION_B_V2.md). A rigidly controlled ablation testing the autonomous self-repair loop on local models (`qwen2.5-coder:7b` and `14b`) hit a strict floor effect (0/10 success across all conditions). This demonstrated that the original Stage 6 success (using Gemini 3.6 Flash) was heavily dependent on human-in-the-loop steering, serving as a material boundary condition on the fully autonomous self-repair claim.
* **Script**: `generate_targets.py` / `build_targets.sh`
* **Raw Output**: `targets/fuzz_pl011_poll_in` (and others)
* **Verification Status**: VERIFIED (ELF binaries exist in repo)
* **Date Finalized**: 2026-09-20

## Stage 7: RL-Driven Fuzzer Scheduling (PPO, UCB1, Q-Learning)
* **Result**: Expanded 10-seed experiment evaluating target saturation and Coupon Collector hypothesis.
  * **N=12 Target Set (Shallow):** PPO (118.10), UCB1 (107.70), Q-Learning (80.90). (Coupon Collector Empirical vs Theoretical: Actual 37.40 steps vs Theoretical 37.24 steps)
  * **N=5 Target Set (Deep):** UCB1 (78.90), Q-Learning (78.50), PPO (71.40). (Coupon Collector Empirical vs Theoretical: Actual 14.20 steps vs Theoretical 11.42 steps)
* **Script**: `rl_final_10seeds_parallel.py`
* **Raw Output**: `stage7_rl_output.log`
* **Verification Status**: VERIFIED via saved log file.
* **Date Finalized**: 2026-09-22
* **Supersession Notice**: The previous 5-seed Q-Learning baseline (70.20) was executed before the strict libFuzzer `-seed` fix was introduced, resulting in artificially high variance. Because this 10-seed experiment evaluated all three algorithms together in a strictly unified, deterministically-seeded environment, **these new 10-seed results supersede all prior Stage 7 metrics and serve as the canonical figures for the project.**

## Stage 7 Extension: Learned Uncertainty Ablation
* **Result**: Weighted rewards derived from the Stage 3 Oracle (Real Uncertainty mapping) vastly outperformed Random Multiplier assignment. The real uncertainty signal provides a statistically significant robustness/variance-reduction benefit over the random baseline (F=17.42, p<0.01).
  * **Real Uncertainty Multiplier**: 80.80 +/- 4.53
  * **Random Multiplier**: 73.20 +/- 18.90
* **Script**: `rl_strict_ablation.py`
* **Raw Output**: `stage7_extension_ablation.log`
* **Verification Status**: VERIFIED. (Note: A re-run reproduced these metrics within expected libFuzzer variance: 78.80 vs 80.80, 71.13 vs 73.20).
* **Date Finalized**: 2026-09-22


## Methodological Integrity Notes
* **Legacy Implementation Audit**: An internal self-audit early in the project found that a prior implementation had fabricated or stubbed several core components. This was fully discarded, and the project was rebuilt from verified first principles. The old implementation is preserved in `/legacy_v1/` strictly for transparency and should not be used as working code.

## Stage 6: Call-Graph-Guided State-Machine Dispatcher
* **Result**: Designed and compiled a unified state-machine harness (`fuzz_state_machine.c`) bridging multiple UART driver functions (`init`, `poll_in`, `poll_out`, `isr`) using call-graph-inferred initialization sequences (Stage 1 data). 
* **Coverage Achieved**: The dispatcher harness reached 76 PCs covered (`ft: 566` feature counters) out of 199 total PCs loaded. **Corrected (Oct 1 independent re-audit)** — the original isolated-harness comparison numbers below did not reproduce from a fresh build and have been re-measured and pinned with committed binaries (`fuzz_poll_in`, `fuzz_poll_out`, `fuzz_isr` in repo root), stable across 5 seeds at 2M–20M executions each: `poll_in` reaches full coverage at **11/11 of 17 total PCs** (previously misreported as 8/9 of 11); `isr` plateaus at **16/17 of 24 total PCs** (previously misreported as 18/19 of 23); `poll_out`'s pre-hang coverage is **seed-dependent** — modal value `cov: 5, ft: 6` (4 of 5 seeds), with the originally-reported `cov: 2, ft: 2` occurring in only 1 of 5 seeds tested, i.e. an unrepresentative outlier, not the typical case. See `stage6_statemachine_report.md`'s Verification section for full seed-by-seed data.
* **Scope Parity Caveat**: The large jump in total PCs loaded (from a corrected ~49 across the 3 isolated harnesses to 199 in the dispatcher) occurred because the dispatcher correctly compiled against the full driver source (`#include "uart_pl011.c"`), whereas the original 3 isolated harnesses were strictly isolated function extractions. Therefore, the coverage increase reflects BOTH the sequencing advantages of state-machine fuzzing AND a significantly larger compiled surface area — and the previous version of this note additionally understated the isolated side's real coverage ceiling, which has now been corrected above.
* **Measurement-method caveat**: these coverage numbers (both dispatcher and isolated) are raw libFuzzer `cov:`/`ft:` sancov counters, the same measurement class that was found to be exploitable/misleading in the Stage 7 sequencing work until independently cross-validated with `llvm-cov`. No `llvm-cov` cross-validation has been performed for any Stage 6 number yet (dispatcher or isolated) — flagged as an open item, not yet done.

## Stage 6: MQTT `properties_decode` UBSan Triage (Harness Artifact)
* **Result**: An initial fuzzing run on the MQTT `properties_decode` function surfaced a UBSan violation (`left shift of 242 by 24 places`). Investigation proved this was strictly a **HARNESS ARTIFACT**, not a real vulnerability. The harness's mock `sys_get_be32` macro lacked the proper `(uint32_t)` upcasts before shifting, causing an implicit promotion bug. Aligning the macro with Zephyr's actual `byteorder.h` resolved the issue cleanly.

## Stage 6: Ground-Truth Methodology Validation (CVE-2020-10062)
* **Result (METHODOLOGY VALIDATION / POSITIVE CONTROL)**: Evaluated the pipeline against a known ground-truth vulnerability (CVE-2020-10062: MQTT `packet_length_decode` off-by-one integer overflow) to validate capability. **Note: This is a positive control, NOT a new vulnerability discovery.**
* **Findings**:
  * **Isolated Harness**: Found 0 crashes. The unsigned integer overflow inside `packet_length_decode` is well-defined behavior in C and physically causes no memory-safety violation in isolation.
  * **Broad-Scope Safe Harness (`mqtt_handle_rx`)**: Found 0 crashes. The Zephyr library code remains memory-safe internally (network reads are bounds-checked). The bug is strictly an API contract violation where a corrupted length is passed up to the application.
  * **Broad-Scope Vulnerable Consumer Harness**: **Detected the vulnerability within hundreds to low thousands of executions (<1 second), real crash counts 610/809/1445 across 3 independently-seeded fresh runs.** Modeling a naive application consumer (a dummy callback trusting `payload.len` for a `memcpy`) allowed the fuzzer to organically trigger the API contract violation and crash via an AddressSanitizer stack-buffer-overflow.
  * **Reproducibility gap found and fixed (Oct 1 independent re-audit)**: the committed `fuzz_broad_vuln` binary does genuinely detect the crash (re-confirmed) — the original "<1 second" claim is real on that pinned binary. However, **rebuilding `harness_broad_vuln.c` from source using this project's own documented build flag (`-O1`, per `REPRODUCE.md`) silently fails to reproduce the crash at all** — confirmed via a real 9.8M-execution fuzzing campaign on a fresh `-O1` rebuild, 0 crashes. Root cause, confirmed via direct LLVM IR inspection: at `-O1`, with `app_buffer`'s contents never read after the `memcpy`, LLVM's optimizer dead-code-eliminates the entire `malloc`/`memcpy`/`free` sequence in `dummy_cb`, so the vulnerable code silently never executes at that optimization level. Fixed by adding a single `volatile` read of `app_buffer[0]` immediately after the `memcpy` in `harness_broad_vuln.c`, forcing the copy to be observable and preventing the optimizer from removing it. The committed binary has been rebuilt from this fixed source at the documented `-O1` flag and re-verified: detects the crash both from the saved `trigger.bin` and from a real fuzzing campaign (fresh mutated input, crash within hundreds to low thousands of executions across 3 independently-seeded runs: 610/809/1445). The two unaffected negative controls (isolated harness, broad-safe harness) were re-confirmed clean (0 crashes, ~10M and ~5M executions respectively) after the same rebuild.
* **Mechanistic Discovery**: In the broad-scope harness, the fuzzer organically found **two distinct paths** leading to the exact same massive `payload_len` API violation:
  1. **Official CVE Path (Overflow)**: A 5-byte length where the 5th byte lacks a continuation bit causes `packet_length_decode` to overflow into a massive positive `var_length`, cascading into `publish_decode` (verified manually).
  2. **Fuzzer-Discovered Path (Underflow)**: A 6-byte input triggering `var_length = 0` alongside a QoS/Topic header requiring 4 bytes causes `publish_decode` to blindly calculate `0 - 4`, underflowing into a massive `payload_len`.

## Stage 7 Extension: RL-Guided State-Machine Sequencing (Methodology Case Study)
* **Result (Honest Null Finding)**: On this mock PL011 driver, Blind Random, Constrained Random, UCB1, and all three Q-learning tie-break variants converge to **identically flat driver-level coverage (29 PCs)**. No sequencing policy outperformed blind random on this benchmark.
* **Why (The 90% Ceiling)**: A single random 10-step episode covers ~90% of the driver's reachable branches (26 out of 29 PCs at Execution 1). The benchmark state space is far too shallow for any intelligent sequencing to differentiate itself in principle, regardless of the reinforcement learning policy quality.
* **Limitation**: The null result is a reflection of this benchmark's bounded depth (a mock driver with shallow initialization requirements), not a general claim against RL-guided fuzzing. 
* **Future Work**: Evaluating RL against random fuzzing requires a deep mock driver with long, stateful prerequisite chains, explicitly scoped as follow-on work.

### The Real Contribution: The Measurement Failure Chain
The primary contribution of this stage is methodological. Over several iterations, the RL agent appeared to repeatedly "outperform" the random baselines. Each apparent victory was systematically unmasked as a measurement artifact or reward-hacking vulnerability inside the fuzzer's custom `__sancov_cntrs` C-loop. 

This 8-point failure chain serves as a crucial methodology lesson for anyone building custom reward signals on raw LibFuzzer coverage counters:

1. **8-bit Counter Wraparound → Unsigned Underflow**: LibFuzzer's 8-bit counters wrap to zero when hit 256 times. A naive `delta = new_cnt - old_cnt` computation underflowed, granting the RL agent a spurious ~10^19 reward.
2. **Clamped Delta → Insufficient Fix**: Clamping the underflow to zero merely changed the exploit's shape. The agent discovered it could milk continuous `0 → 1` transition loops at the wraparound boundary.
3. **Sticky Monotonic Bitmap**: A permanent `sticky_cov[index] = 1` map was required to close the exploit for real, enforcing a strictly non-stationary, depletable reward landscape.
4. **Baseline-Drift Scoping**: The raw `__sancov_cntrs` read was silently undercounting coverage across all algorithms due to wrap noise. A dedicated audit isolated this vulnerability strictly to Stage 7's custom scoring path; Stages 1–6 were confirmed immune as they parsed LibFuzzer's monotonic `cov:` stdout instead.
5. **Debug Printf Self-Reward ("Heisenberg Bug")**: An errant `printf("MAX_COV...")` statement injected a 2-edge branch into the fuzzer loop. The fuzzer rewarded itself for executing its own diagnostic trace statement, artificially inflating scores.
6. **Tie-Break Death-Loop**: Once the sticky-bitmap rewards depleted, all Q-values mathematically decayed to zero. A degenerate deterministic tie-breaker (`cmd=0`) caused Q-learning to collapse into an initialization death-loop, artificially plunging coverage below random (26 PCs).
7. **Randomized Tie-Break (False Recovery)**: Randomized tie-breaking appeared to recover coverage to a staggering 54 PCs. However, this "win" was proven false: the RL agent was simply being rewarded for executing the increasingly complex internal decision trees of its own `switch/case` router and epsilon decay branches. 
8. **Final Structural Fix (no_sanitize("coverage") + llvm-cov)**: Applying `__attribute__((no_sanitize("coverage")))` to all fuzzer/agent code and compiling with `-fno-inline` strictly scoped measurement to the target driver. This collapsed the entire RL superiority narrative, revealing a flat 29 PCs across all algorithms. This flatline was completely, independently verified via `llvm-cov` source-based profiling.
