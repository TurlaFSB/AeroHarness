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
* **Expected Result:** The script outputs a paired t-test array showcasing UCB1 with the Real Uncertainty Multiplier achieving roughly `78.20 ± 3.97`, whilst the Random Multiplier falls to `51.00 ± 22.27`. 

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

* **Expected Runtime:** <10 seconds.
* **Exact Command:**
  ```bash
  clang++ -g -O1 -fsanitize=fuzzer,address -I./include -c ./targets/fuzz_pl011_poll_in.cpp -o fuzz_pl011_poll_in.o
  clang++ -g -O1 -fsanitize=fuzzer,address fuzz_pl011_poll_in.o ./firmware/pl011.c -o ./targets/fuzz_pl011_poll_in
  ```
  *(Note: A convenience script `./build_targets.sh` automatically wraps this logic for all generated drivers).*
* **Expected Result:** A valid ELF executable `./targets/fuzz_pl011_poll_in` is produced. Run it via `./targets/fuzz_pl011_poll_in -runs=1` to observe the libFuzzer ASan initialization hook executing successfully.
