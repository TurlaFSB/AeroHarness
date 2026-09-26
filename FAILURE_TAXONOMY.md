# Formal Taxonomy of Failures in AeroHarness

This document consolidates every real failure mode encountered and documented across all seven stages (plus repository hardening) of the AeroHarness project. It categorizes both technical execution failures and procedural/methodological failures.

## 1. Technical & Execution Failures

### Syntax failure
* **Observed:** Yes.
* **Instances:** During early Stage 6 harness synthesis, the LLM generated malformed C/C++ (e.g., missing semicolons, unclosed brackets) when attempting to inject Zephyr RTOS stubs directly into the libFuzzer harness file.

### Compilation failure
* **Observed:** Yes.
* **Instances:** Stage 6 compiler-repair loop. The LLM repeatedly generated code that failed to compile due to undeclared structs (e.g., trying to access `pl011_data` fields before they were fully defined) and missing type definitions (`uint32_t`) before the correct headers were `#include`d.

### Linking failure
* **Observed:** Not observed in this project's scope.
* **Context:** Because we injected driver source code directly into the C++ fuzzer harnesses or included them directly as headers, all symbols were resolved in a single translation unit, avoiding linking errors.

### Missing dependency
* **Observed:** Yes.
* **Instances:** Stage 1 and Stage 6. The original firmware sources heavily relied on Zephyr headers (`zephyr/device.h`, `zephyr/kernel.h`, `zephyr/sys/util.h`). Because we stripped the code from the RTOS tree, compilation failed until we built `harnesses/include/zephyr_stubs.h` and explicitly mocked macros like `BIT(n)` and `DEVICE_MMIO_RAM`.

### Incorrect API assumption
* **Observed:** Yes.
* **Instances:** In Stage 6, the LLM assumed `K_SPINLOCK(&data->irq_cb_lock)` was a standard function call. In reality, it is a complex Zephyr preprocessor macro that expands into a block loop. This mismatch severely complicated static analysis (Lizard reported CCN=4, missing the hidden complexity) and required dynamic fuzzing to fully explore.

### Incorrect type inference
* **Observed:** Yes.
* **Instances:** In Stage 6, the LLM generated code attempting to directly access fields on `dev->data` without casting it from `void*` to the underlying `struct pl011_data*`, triggering C++ strict-typing compilation errors.

### Initialization failure
* **Observed:** Yes.
* **Instances:** Early Stage 6 harnesses failed to properly initialize `struct pl011_data pl_data;` using `memset(&pl_data, 0, sizeof(pl_data));`. This resulted in uninitialized pointers and undefined behavior until the repair loop corrected it.

### Hardware-mock failure
* **Observed:** Yes.
* **Instances:** 
  1. **Write-1-to-Clear (W1C) Clobbering:** In `pl011_isr`, the real driver writes to `uart->icr` twice consecutively to clear different interrupts. On real hardware, this works. In our static C-struct mock, the second write silently clobbered the first write, forcing us to adjust the `assert()` logic to only check the final state.
  2. **Busy-Wait Timeout:** In `pl011_poll_in`, the loop `while (uart->fr & RXFE)` hung indefinitely because our static mock struct didn't natively toggle the RXFE flag over time as real hardware would.

### Runtime crash
* **Observed:** Yes.
* **Instances:** 
  * **Intentional:** We deliberately introduced a heap-buffer-overflow bug into a toy harness to verify our ASan/libFuzzer CI pipeline successfully caught memory corruption.
  * **Unintended:** In `pl011_isr`, the fuzzer initially generated inputs that caused `data->irq_cb` to evaluate to a garbage pointer, causing a segmentation fault when the ISR attempted to fire the callback, until it was correctly mapped to a `dummy_irq_cb`.

### Sanitizer failure
* **Observed:** Not observed in this project's scope.
* **Context:** AddressSanitizer (ASan) correctly caught the deliberate overflow during verification and performed reliably alongside libFuzzer.

### Infinite loop/hang
* **Observed:** Yes.
* **Instances:** (See Hardware-mock failure). The busy-wait TXFF/RXFE polling loops caused the fuzzer to spin endlessly, triggering libFuzzer's `-timeout=1` limit.

### Low-coverage harness
* **Observed:** Yes.
* **Instances:** Initial iterations of the `poll_in` harness failed to explore deeply because the fuzzer bytes were not effectively mapped to the MMIO mock registers, preventing the harness from passing basic `if` condition checks.

### False-positive vulnerability
* **Observed:** Not observed in this project's scope.
* **Context:** While we had classification inaccuracies, no false-positive memory vulnerabilities or exploits were flagged in the real Zephyr code by the fuzzer.

### Repair-loop failure
* **Observed:** Not observed in this project's scope.
* **Context:** We bounded the LLM compiler-repair loop to a strict 5 iterations. Our most difficult function (`pl011_isr`) required exactly 4 iterations to successfully mock and compile. We never exhausted the limit.

### Timeout
* **Observed:** Yes.
* **Instances:** 
  1. **LLM API Timeout:** Exhaustion of the Gemini API Free-Tier daily quota (~20 requests/day) resulting in `429 Too Many Requests`, necessitating the Ollama local fallback.
  2. **Fuzzer Timeout:** LibFuzzer triggered `-timeout=1` exceptions during busy-wait infinite loops (as noted above).

---

## 2. Methodology & Process Failures

*Note: These are non-code execution failures that represent genuine risks and pitfalls in agentic-AI-assisted research workflows.*

* **Fabricated/Lost Empirical Data:** `RESULTS.md` silently lost real empirical data during agentic edits (e.g., the actual theoretical vs empirical step counts for the Coupon Collector's Problem were overwritten with a vague summary), requiring a full reversion/restoration from cached system logs.
* **Silently Overwritten Scripts:** The Stage 4 evaluation script was accidentally reverted from strict scoring (rejecting passthrough) back to the lenient baseline during an agent refactor. This was only caught by rigorously auditing the evaluation logic against the reported 83.3% canonical metric.
* **Prompt Inconsistency (The Kinetis Flaw):** A massive methodological failure occurred in Stage 2 where the Zephyr evaluation used a highly structured zero-shot prompt, but the Kinetis evaluation used a flawed, unstructured prompt. This drastically inflated Kinetis accuracy to 56.0%. When discovered and re-evaluated consistently, the true Ollama accuracy dropped to 52.8%.
* **Copy-Paste Documentation Errors:** Stage 7's `Raw Output` and `Verification Status` lines in `RESULTS.md` were accidentally copy-pasted from Stage 5 (claiming "raw logs missing"), invalidating the chain of custody until manually caught and corrected to point to `stage7_rl_output.log`.
* **Exposed API Keys:** The Gemini API key was inadvertently exposed in `.env` and shell histories without proper Git isolation, necessitating a key rotation and strict `.gitignore` enforcement.
