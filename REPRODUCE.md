# AeroHarness Independent Reproduction Guide

This guide provides the minimum steps required for an external evaluator (e.g. lab-mate, faculty) to independently verify the strongest claims of the AeroHarness paper. 

## Environment Prerequisites
1. **OS**: Windows 11 with WSL2 (Ubuntu 22.04 LTS or 24.04 LTS recommended). 
2. **Compilers**: Clang and Clang++ (Version 14+). 
   * Install via: `sudo apt-get install clang llvm lld`
3. **Python**: Python 3.10+
   * Dependencies: `pip install stable-baselines3 gymnasium scipy numpy pandas scikit-learn transformers torch xgboost==3.4.1`
   * Note on PyTorch: A CPU-only installation is entirely sufficient for reproducibility, but it must be natively installed inside WSL (to run Linux ELF libFuzzer executables alongside Python). 
4. **API Keys**: To re-run LLM harness generation, export `GEMINI_API_KEY`. (Alternatively, if using Ollama, ensure the Ollama daemon is running locally and swap the backend in script configurations).

---

## 1. Re-running the Oracle Uncertainty Ablation (Stage 7 Extension)
This test proves that mapping real LLM uncertainty to target rewards produces statistically robust scheduling compared to random target weighting. 

* **Expected Runtime:** ~2 minutes on a modern CPU. 
* **Exact Command:**
  ```bash
  python3 rl_strict_ablation.py
  ```
* **Expected Result:** The script outputs a paired t-test array showcasing UCB1 with the Real Uncertainty Multiplier achieving roughly `80.80 ± 4.53`, whilst the Random Multiplier falls to `73.20 ± 18.90` (F=17.42, p<0.01; these are `RESULTS.md`'s canonical figures — a documented re-run reproduced them within expected libFuzzer variance at `78.80`/`71.13`, and this section previously cited a third, non-matching pair, `78.20 ± 3.97` / `51.00 ± 22.27`, which did not match either run).

---

## 2. Re-running the P2IM Benchmark (Stage 4)
This test verifies the AST-guided LLM harnesses natively achieve state traversal metrics comparable to strict full-system emulators. 

* **Expected Runtime:** <10 seconds.
* **Exact Command:**
  ```bash
  python3 evaluate_accuracy_canonical.py
  ```
* **Expected Result:** The console will output `Total Accuracy: 83.33%`. This validates that our harnesses accurately triggered the correct peripheral state transitions in the RIOT USART firmware benchmark. 

---

## 3. Harness Compilation (Stage 6)
To verify that our synthesized fuzz drivers successfully link against the real firmware HAL and LibFuzzer.

**Note (corrected Oct 3 2026):** the `target_*.cpp` harness files are Stage 6 *output*, not checked into the repo (`.gitignore` excludes `target_*` deliberately — they're synthesized artifacts, regenerated per-run). This section previously named files that never exist in a fresh checkout (`./targets/fuzz_pl011_poll_in.cpp`, `./include/`, `./firmware/pl011.c`) and don't match the real build script below. If you haven't yet run Stage 6 synthesis for a target, do that first (see `run.py`/`ANTIGRAVITY_TASK_ITEM2.md`-style instructions elsewhere in this repo); this section assumes at least one `targets/target_*.cpp` file already exists.

* **Expected Runtime:** <10 seconds per target.
* **Exact Command:** run the actual, checked-in build script, which compiles every currently-present generated target against the real mocks/headers under `harnesses/include`:
  ```bash
  ./build_targets.sh
  ```
  Its commands look like (one line per target, e.g.):
  ```bash
  clang++ -g -fsanitize=fuzzer,address -Iharnesses/include targets/target_poll_in_sbsa.cpp -o targets/target_poll_in_sbsa
  ```
* **Expected Result:** A valid ELF executable per target (e.g. `./targets/target_poll_in_sbsa`) is produced next to its source. Run one via `./targets/target_poll_in_sbsa -runs=1` to observe the libFuzzer ASan initialization hook executing successfully.
