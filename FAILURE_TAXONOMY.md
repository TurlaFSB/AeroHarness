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
* **Instances:** Stage 1 and Stage 6. The original firmware sources heavily relied on Zephyr headers (`zephyr/device.h`, `zephyr/kernel.h`, `zephyr/sys/util.h`). Because we stripped the code from the RTOS tree, compilation failed until we mocked them. **Correction (Oct 1 2026, independent audit):** the file name cited here, `harnesses/include/zephyr_stubs.h`, does not exist in the repo. Checking the real mechanism directly: `harnesses/include/zephyr/device.h` is an empty stub file that exists only to satisfy the `#include <zephyr/device.h>` line so compilation doesn't fail on a missing header; the actual macro mocks (`#define DEVICE_MMIO_RAM`, `#define BIT(n) (1UL << (n))`, confirmed present verbatim in `harnesses/fuzz_pl011_isr.cpp` lines 8-9) are defined inline in each harness `.cpp` file itself, not in one shared stubs header. The general claim (these macros had to be mocked because the real Zephyr headers were stripped out) is true and verified; only the specific file name was wrong.

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
  * **Intentional:** We deliberately introduced a heap-buffer-overflow bug into a toy harness to verify our ASan/libFuzzer CI pipeline successfully caught memory corruption. **Verification caveat (Oct 1 2026, independent audit):** the closest matching artifact found, `legacy_v1/output/PoV_protocol_process_frame_heap-buffer-overflow.c`, targets an unrelated function (`protocol_process_frame`, not any `pl011_*` function) and lives in `legacy_v1/`, which this project's own `README.md` explicitly labels "pre-audit implementation with fabricated/stubbed components, kept for transparency." Its documented reproduction command also doesn't run as-is: it requires `protocol_parser.h` and `target_source.c`, neither of which exist anywhere in the repo. This claim should be treated as unverified (possibly describing fabricated legacy work, not a real current-pipeline check) until a genuine, runnable ASan-verification artifact is identified or re-created.
  * **Unintended:** In `pl011_isr`, the fuzzer initially generated inputs that caused `data->irq_cb` to evaluate to a garbage pointer, causing a segmentation fault when the ISR attempted to fire the callback, until it was correctly mapped to a `dummy_irq_cb`. **Verified** — `dummy_irq_cb` is present and wired in exactly as described, confirmed by reading `harnesses/fuzz_pl011_isr.cpp` directly (lines 82, 95, 114).

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

### Timeout / LLM backend unavailability
* **Observed:** Yes.
* **Instances:** 
  1. **LLM API Timeout:** Exhaustion of the Gemini API Free-Tier daily quota (~20 requests/day) resulting in `429 Too Many Requests`, necessitating the Ollama local fallback.
  2. **Fuzzer Timeout:** LibFuzzer triggered `-timeout=1` exceptions during busy-wait infinite loops (as noted above).
  3. **LLM API policy denial (new, Oct 1 2026, distinct mechanism from #1):** During the Kinetis ADC pipeline run, Gemini was unreachable for a different reason than quota exhaustion — `curl` to the Gemini endpoint returned `403` on the proxy's `CONNECT` tunnel, and the sandbox's own proxy-status diagnostic confirmed a policy-level relay denial for that host, not a rate limit. No Ollama binary or local model was available in that environment either, so there was no fallback tier left to failover to. Resolved by having the Stage 2 LLM role performed directly and disclosed (`"backend": "claude_fallback"` in `llm_proposals_kinetis_adc_calibrate.json`) rather than skipping Stage 2 or silently reusing stale data. This is a materially worse failure mode than quota exhaustion: quota resets on a schedule and Ollama is a known-working fallback; a sandbox-level network policy denial with no local model installed has no automatic recovery path at all.

### Concurrency-based hardware-mock failure (new category, Oct 1 2026, Kinetis ADC work)
* **Observed:** Yes — three distinct sub-failures, each independently diagnosed with debug-instrumented tracing rather than assumed, while repairing `kinetis_adc_calibrate`'s harness (`harnesses/fuzz_kinetis_adc_calibrate.c`; see `RESULTS.md`'s "Second-RTOS/Target Pipeline Run" section for full detail). This is a new sub-category of hardware-mock failure distinct from the W1C/busy-wait cases above, because the hazard here is a register bit the target function sets *and* spins on *itself* — no static single-shot struct value can pre-seed around it, forcing a genuinely asynchronous mocking mechanism (a second thread or a signal) rather than just a smarter static value.
* **Instances:**
  1. **Per-call thread create/join instability:** Spawning a fresh `pthread` per `LLVMFuzzerTestOneInput` call compiled clean and worked on a single replayed input, but hung under real fuzzing load after only a few mutations — per-call thread creation/teardown could not keep up with libFuzzer's execution rate in this environment.
  2. **Busy-spin thread starvation:** Replacing per-call threads with one persistent helper thread, signaled via a plain busy-poll flag, still hung. Debug tracing showed the helper fired exactly once, then was never scheduled again: the helper's idle busy-spin and the main thread's own busy-wait (inside the target function) starved each other under this sandbox's constrained CPU scheduling.
  3. **Thread-handoff/`pthread_once` unreliability:** The textbook fix for #2 — the helper blocking on a condition variable instead of spinning when idle — still hung. A second debug-instrumented run showed the *first* execution's full handshake tracing perfectly, but the *second* execution never even reached the "about to lock" print before the alarm fired, implicating `pthread_once`/thread-handoff reliability itself in this sandbox, not the spin-vs-block choice.
  4. **One-shot timer race (near-miss, not a full instance, but worth recording):** The working fix dropped threads for a POSIX interval timer delivering a signal. A first version used a *one-shot* timer and still hung — direct tracing proved the signal handler fired, but could fire *before* the target set the bit it was meant to clear, after which the one-shot timer could never fire again. Fixed by making the timer periodic (an already-clear bit is a harmless no-op to re-clear).
* **Implication:** All three thread-based mechanisms that are textbook-correct in ordinary multithreaded code failed specifically under this project's fuzzing load/sandbox combination. Teams building similar asynchronous hardware-completion mocks for static-mock fuzz harnesses should default to a signal/timer-based mechanism over threads, and should budget for at least this many repair iterations when the hazard is "self-set-and-spin" rather than "fuzzer-controlled-bit."

---

## 2. Methodology & Process Failures

*Note: These are non-code execution failures that represent genuine risks and pitfalls in agentic-AI-assisted research workflows.*

* **Fabricated/Lost Empirical Data:** `RESULTS.md` silently lost real empirical data during agentic edits (e.g., the actual theoretical vs empirical step counts for the Coupon Collector's Problem were overwritten with a vague summary), requiring a full reversion/restoration from cached system logs.
* **Silently Overwritten Scripts:** The Stage 4 evaluation script was accidentally reverted from strict scoring (rejecting passthrough) back to the lenient baseline during an agent refactor. This was only caught by rigorously auditing the evaluation logic against the reported 83.3% canonical metric.
* **Prompt Inconsistency (The Kinetis Flaw):** A massive methodological failure occurred in Stage 2 where the Zephyr evaluation used a highly structured zero-shot prompt, but the Kinetis evaluation used a flawed, unstructured prompt. This drastically inflated Kinetis accuracy to 56.0%. When discovered and re-evaluated consistently, the true Ollama accuracy dropped to 52.8%.
* **Copy-Paste Documentation Errors:** Stage 7's `Raw Output` and `Verification Status` lines in `RESULTS.md` were accidentally copy-pasted from Stage 5 (claiming "raw logs missing"), invalidating the chain of custody until manually caught and corrected to point to `stage7_rl_output.log`.
* **Exposed API Keys:** The Gemini API key was inadvertently exposed in `.env` and shell histories without proper Git isolation, necessitating a key rotation and strict `.gitignore` enforcement.
* **Verification note on the methodology-failure entries above (Oct 1 2026):** `git log` for `RESULTS.md` only goes back 7 commits in this repo, which doesn't reach far enough to directly confirm the "Fabricated/Lost Empirical Data," "Silently Overwritten Scripts," or "Copy-Paste Documentation Errors" incidents as described. What *is* independently checkable: the end states these entries claim to have fixed are real and present now — `RESULTS.md`'s Stage 7 section currently shows real empirical-vs-theoretical step counts (37.40 vs 37.24, 14.20 vs 11.42), not a vague summary; its "Raw Output" line correctly points to `stage7_rl_output.log` (not a Stage 5 file); and `evaluate_accuracy_canonical.py` currently contains the strict scoring rule described ("`C&SR` and llm_model in [set, bitextract] # STRICT RULE: passthrough rejected"). So the *fixes* are verified; the *original incidents* are plausible and consistent with those fixes but not independently provable from available git history.
* **Silent Stage 1 extraction failure, discovered late (Oct 1 2026):** `ast_kinetis_filtered.json` recorded `null` for `kinetis_adc_calibrate`'s AST entry — a real extraction bug, not a missing run, that went unnoticed until the second-RTOS pipeline work specifically needed that function's data. Root cause was a pip/system `libclang` version mismatch (`clang` 21.1.7's bindings against system `libclang-18`). This is the same general risk as the "Silently Overwritten Scripts" entry above — a pipeline stage can silently produce empty/null output without raising an error, and nothing downstream notices until someone actually needs that specific data point.
* **Stage 3 oracle never run against a dataset it was meant to gate (Oct 1 2026):** `evaluate_kinetis.py` benchmarks raw Stage 2 LLM proposals directly against P2IM ground truth, bypassing Stage 3's oracle verification step entirely — contradicting the pipeline's own documented design, which benchmarks "Confirmed" (oracle-verified) models, not raw proposals. This had never been caught because the Kinetis benchmark path and the oracle path were never cross-checked against each other until this audit.
