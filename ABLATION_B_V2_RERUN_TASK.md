# Agent Task: Re-run Ablation B v2 (Compiler-Oracle Feedback) on Local Qwen2.5-Coder Models

**Audience:** An autonomous coding agent (e.g. Antigravity) operating directly on Pranav's laptop, with no visibility into any prior conversation. Everything it needs is in this file.

**Status:** Not yet executed. Fill in the "Results" section at the bottom once this task completes, and hand this file back for review.

---

## 1. Why this task exists

`ABLATION_B_V2.md` (in this repo) documents a pre-registered experiment comparing two feedback strategies in an LLM self-repair loop for libFuzzer harness synthesis: **Arm A** (real compiler error fed back) vs. **Arm B** (generic "it failed, try again" message). A 10-trial pilot run previously reported a complete floor effect — both `qwen2.5-coder:7b` and `qwen2.5-coder:14b` failed 100% of first attempts, because neither model could synthesize missing Zephyr framework macros (`K_SPINLOCK`, `BIT`, `DEVICE_MMIO_GET`) from scratch.

An independent audit of this project (Oct 1 2026) found that **no raw log, JSON result file, or trial transcript for that pilot exists anywhere in the repo**, and that the script which produced it (`run_ablation_b_v2.py`) was hardcoded to a `wsl` subprocess wrapper and Windows-only paths — meaning it could only ever run on the original author's specific machine. That hardcoding has since been fixed (commit `89105492b`, "Make run_ablation_b_v2.py portable"). This task is the first real, reproducible re-run of that experiment, producing an artifact that can actually be checked.

**Standing project norm (apply throughout):** this is an industry-grade research project. Never report a claim without the artifact that backs it. If something fails, report the failure plainly — do not guess around it, do not silently skip a step, do not fabricate a plausible-looking result.

---

## 2. Prerequisites — verify before running anything

Run each check and **stop and report** if any fails, rather than attempting a workaround on your own judgment:

1. **Repository is up to date.**
   ```
   git pull origin main
   ```
   Confirm `run_ablation_b_v2.py` contains the string `Portability fix (Oct 1 2026, independent audit)` near the top. If that string is absent, the pull did not bring in the current commit — stop here and report it.

2. **Compiler toolchain.**
   ```
   clang++ --version
   clang++ -fsanitize=fuzzer,address --help
   ```
   Both must succeed (libFuzzer + AddressSanitizer support is required; plain clang without these sanitizers will not work).

3. **Local LLM backend.**
   ```
   ollama list
   ```
   Confirm both `qwen2.5-coder:7b` and `qwen2.5-coder:14b` are present. If either is missing:
   ```
   ollama pull qwen2.5-coder:7b
   ollama pull qwen2.5-coder:14b
   ```
   Confirm the Ollama server answers at `http://127.0.0.1:11434` (e.g. `curl http://127.0.0.1:11434`). Start it if it isn't running.

4. **Python dependencies.**
   ```
   python3 -c "import requests"
   ```
   If this errors, run `pip install requests` (add `--break-system-packages` if the system pip refuses, or use `pip3`).

---

## 3. Run the experiment

From the repository root, run both models **sequentially, not in parallel** (they share the same local Ollama server and GPU/CPU):

```
python3 run_ablation_b_v2.py --model qwen2.5-coder:7b
python3 run_ablation_b_v2.py --model qwen2.5-coder:14b
```

### What each run does (do not modify this logic — it is a pre-registered design)
For each of 5 target functions (`pl011_poll_in`, `pl011_poll_out`, `pl011_isr`, `pl011_runtime_configure_internal`, `pl011_init`), run 2 trials:
1. Generate a libFuzzer harness via the local Ollama model (temperature 0.7, per-trial seed).
2. Compile with `clang++ -fsanitize=fuzzer,address`; run it 1 second under the fuzzer.
3. **Success criteria (all must hold):** compiles and links; runs ≥1s with no ASan/UBSan crash; reports >3 coverage edges; the target function name appears in the generated source (not stubbed out).
4. On first-attempt failure, branch into two retry arms from the identical failed state:
   - **Arm A:** real compiler stderr fed back, up to 4 more attempts.
   - **Arm B:** generic `"The code failed to compile. Please try again."`, up to 4 more attempts.

### Outputs to expect
- `ablation_b_v2_results_qwen2.5-coder_7b.json`, `ablation_b_v2_results_qwen2.5-coder_14b.json` — structured trial outcomes.
- `ablation_b_v2_logs_qwen2.5-coder_7b/`, `ablation_b_v2_logs_qwen2.5-coder_14b/` — raw generated harness code per trial/arm/attempt.

**Expected runtime:** a few minutes to ~20-30 minutes per model, depending on hardware (up to 5 LLM calls × 1s fuzz run × 5 targets × 2 trials). Let each run finish; a logged failure is a valid experimental outcome, not a reason to stop early.

**Do not edit** `run_ablation_b_v2.py`, its `TARGETS` prompts, temperature, seed logic, or success-criteria code. If something about the script itself appears broken (not just "the LLM failed," but the script erroring), report the exact error — do not patch it silently.

---

## 4. Reporting requirements

After both runs complete, report back:
1. Full console output from both runs (at minimum, the per-target `First-Attempt Success/Failed` and `Arm A (Real): ... / Arm B (Generic): ...` lines).
2. The full contents of both result JSON files.
3. A directory listing of both log folders.
4. Any errors hit at any step, verbatim — including partial failures (e.g. one target errored but others completed).

---

## 5. Results

*(To be filled in after the agent runs this task — paste console output, JSON contents, and any errors here, or attach the files.)*

- **7B run:** _pending_
- **14B run:** _pending_

---

## 6. Next step after results land (for whoever picks this back up)

Once the raw results are in hand:
1. Check whether the documented floor effect (100% first-attempt failure, 0/10 repair rate) reproduces exactly on this hardware/model-tag combination, or whether anything clears.
2. If ≥10 paired first-attempt failures exist across both models combined, run McNemar's exact test on Arm A vs. Arm B as pre-registered in `ABLATION_B_V2.md`.
3. If it's still an inconclusive floor effect, consider `ABLATION_B_V2.md`'s own "Future Work #3": pre-supply the missing Zephyr macro stubs (`K_SPINLOCK`, `BIT`, `DEVICE_MMIO_GET`) and re-run, to get a real (non-floored) Arm A vs. Arm B comparison.
4. Write the real numbers into `ABLATION_B_V2.md`, replacing its "Verification Note" flag (no raw artifact existed) with a proper result section, and commit/push.
