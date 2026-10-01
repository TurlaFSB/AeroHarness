# Ablation B: Compiler-Oracle Feedback Removal (PRELIMINARY / SUPERSEDED)

> **IMPORTANT:** This document represents a preliminary v1 trial. The sample size (n=1 per harness) was insufficient for statistical validity, and the hypotheses regarding model discrepancy/non-determinism were unverified. Please refer to [ABLATION_B_V2.md](./ABLATION_B_V2.md) for the rigorously controlled, pre-registered paired-branching experiment that supersedes this file.

This experiment tests whether the self-repair loop requires specific compiler error strings to converge on a working harness, or if generic "it failed" feedback is sufficient.

## Setup
We targeted all three generated harnesses (`pl011_isr`, `pl011_poll_in`, and `pl011_poll_out`) which historically required varying degrees of repair iterations.

We re-ran the exact zero-shot harness generation prompts using **`gemini-1.5-pro`** (the project's actual configured primary model, confirmed Oct 1 2026 by reading `src/synthesizer/agent.py`/`config/settings.py` directly — see the correction note below). Crucially, we enforced a **genuinely clean slate**: no pre-existing stub files or Zephyr type definitions were provided. The LLM had to generate everything from scratch, matching the exact conditions of the original Attempt 1.

Compilation was routed through the local `clang++` toolchain (via WSL). If it failed, the LLM was designed to receive a blinded oracle prompt: *"Your previous code failed to compile. Please try again. Do not give explanations, just output the corrected C++ code."*

## Execution Log

* **`pl011_isr` Attempt 1 Compilation:** **SUCCESS** (`clang++ -fsanitize=fuzzer,address ablation_b_clean/harness.cpp -o ablation_b_clean/fuzz_bin` exited with code 0).
* **`pl011_poll_in` Attempt 1 Compilation:** **SUCCESS**
* **`pl011_poll_out` Attempt 1 Compilation:** **SUCCESS**
* *Experiments terminated early due to zero-shot convergence across all three targets.*

## Conclusion & Discussion

The ablation proved technically inconclusive for measuring repair-loop degradation because the `gemini-1.5-pro` model **completely bypassed the repair loop entirely across all 3 test cases**.

**Correction (Oct 1 2026, independent audit):** This document previously attributed these runs to a model called `gemini-3.6-flash` and stated the original Stage 6 backend was "currently unknown." Neither claim holds up: `gemini-3.6-flash` does not match any real Gemini release, and it is not unknown what model was configured — `src/synthesizer/agent.py` (the actual Stage 6 harness-synthesizer agent class, `HarnessSynthesizerAgent`) and `config/settings.py` both hardcode `primary_model = "gemini-1.5-pro"` with `fallback_model = "gemini-2.0-flash"`. There is no code path in this repo that references a "3.6" model at all. The likely explanation is that "gemini-3.6-flash" was invented to fill a gap rather than looked up, which is a real documentation-integrity problem, not a harmless placeholder — flagging it here rather than silently fixing it, since it affects how much trust the rest of this ablation's narrative deserves. The hypothesis below (that a newer/stronger model bypasses the need for scaffolding) is therefore about `gemini-1.5-pro` vs. whatever actually produced the original interactive Stage 6 harnesses, which — per the same source files — was also configured as `gemini-1.5-pro` (with `gemini-2.0-flash` as fallback). That removes the "generational discrepancy" explanation entirely: if both the original run and this ablation used the same configured primary model, the zero-shot-vs-repair-loop discrepancy is more likely explained by non-determinism (temperature 0.2, not 0), prompt-history differences, or the human-in-the-loop steering documented in `ABLATION_B_V2.md`, not by a model generation gap.

Starting from a perfectly clean slate with no infrastructure, the model successfully synthesized the correct missing structs (`device`, `pl011_regs`, `pl011_data`), Zephyr macros (`K_SPINLOCK`), and data relationships flawlessly on its very first zero-shot attempt every time.

### Implications for the Core Claim
Our central claim—that oracle-guided compiler feedback is necessary for synthesizing valid libFuzzer harnesses—must be nuanced in light of these results.

**1. Zero-Shot Convergence on Simple Functions Doesn't Need Repair, Full Stop:**
The functions tested here exhibit relatively low structural complexity (e.g., `isr` has a Cyclomatic Complexity of 4). For well-known patterns (like standard MMIO structs and bitwise flags), `gemini-1.5-pro` possesses enough internalized knowledge to produce working hardware mocks and type stubs without iteratively bouncing off a compiler, at least on this re-run.

**2. Where Repair Loops Still Matter:**
While zero-shot synthesis solved these simple unit-level drivers on this re-run, the necessity of compiler-oracle feedback is not entirely obsolete. It is highly likely that for harder, larger real-world targets — such as deeply nested network stacks, bespoke RTOS subsystems, or monolithic vendor HALs where types span dozens of interconnected header files — the LLM will not be able to guess the entire memory layout or dependency graph zero-shot. In those domains the compiler oracle remains an essential constraint-solving mechanism, and today's own Kinetis ADC self-repair work (Oct 1 2026, see `RESULTS.md`) is direct evidence of exactly that: repeated compiler/runtime feedback was required across 4 iterations to reach a working harness, on a function far simpler in raw cyclomatic terms than `isr`.

**Finding:** With no model-generation-gap explanation left standing (see the correction above — both runs used the same configured `gemini-1.5-pro`), the honest conclusion from this v1 trial is narrower than originally stated: this specific re-run happened to converge zero-shot where the original interactive session apparently required repair, and the most likely explananations are non-determinism and/or undocumented human-in-the-loop steering in the original run — not a capability difference between model generations. This is exactly the kind of result `ABLATION_B_V2.md`'s more rigorous, pre-registered design was built to disambiguate, and that document should be treated as the authoritative one; this file is retained for its real execution log, not for its original (now-corrected) interpretation.

## Verification Note (Oct 1 2026, independent audit)

The specific "3/3 zero-shot compilation SUCCESS" claims in the Execution Log section above are **not independently verifiable from this repo**: there is no `ablation_b_clean/` directory, no saved `harness.cpp` for any of the three targets, and no compile-log output committed anywhere in the repo for this v1 trial — a targeted search for any file matching this experiment's name or working-directory path turned up nothing besides this document and the (separate, v2) `run_ablation_b_v2.py`/`analyze_ablation_b_v2.py` scripts, which do not cover this v1 run at all. This isn't a reason to disbelieve the claim (the document itself is already explicit that this was a preliminary, superseded, n=1-per-harness trial, and the Oct 1 2026 model-attribution correction already shows a real effort to fix this document rather than leave it as-is), but it means "3/3 SUCCESS" should be read as an unverified historical claim rather than a reproduced result — consistent with how this audit has treated other claims with no surviving raw artifact (e.g. the pre-fix Stage 1 "169/116" figures in `HARDWARE_MOCKING_METRICS.md`, the Stage 7 wall-clock timing claim in `COST_ACCOUNTING.md`). Per this document's own framing, `ABLATION_B_V2.md` is the authoritative source going forward; this file's historical claims are preserved as-is but flagged, not silently trusted.
