# Stage 6 Harness Sub-Metrics

The top-line "3/3 success" metric for Stage 6 harness generation can be formally broken down into 6 distinct lifecycle sub-metrics, tracking exactly where the LLM succeeded or struggled across the pipeline.

## Evaluation Protocol Table

| Harness | Synthesis Success | Compilation Success | Linking Success | Executable Startup | Sanitizer-Clean Init | Valid-Input Handling |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `pl011_poll_out` | **Yes** (Syntactically complete) | **Yes** (0 repair iterations; clean compile on first try) | **Yes** (Compile+link is a single step in our clang toolchain) | **Yes** (Began fuzzing cleanly before hitting hardware busy-wait) | **Yes** (No ASan/UBSan violations on startup) | **Yes** (LLM included `if (size < 2) return 0;`) |
| `pl011_poll_in` | **Yes** (Syntactically complete) | **Yes** (Required 2 compile-repair iterations) | **Yes** (Compile+link is a single step in our clang toolchain) | **Yes** (Successfully initialized and fuzzed cleanly) | **Yes** (No ASan/UBSan violations on startup) | **Yes** (LLM included `if (size < 4) return 0;`) |
| `pl011_isr` | **Yes** (Syntactically complete) | **Yes** (1 compile-repair iteration, 1 post-compile behavioral-repair iteration) | **Yes** (Compile+link is a single step in our clang toolchain) | **Yes** (Began fuzzing cleanly before hitting W1C assertion) | **Yes** (No ASan/UBSan violations on startup) | **Yes** (LLM included `if (size < 3) return 0;`) |

**Discrepancy flagged, Oct 1 2026:** this table's repair-iteration counts (`poll_out`: 0, `isr`: 1 compile + 1 behavioral = 2) do not match `stage6_difficulty_metrics.md`'s "Repair Iterations" column (`poll_out`: 1, `isr`: 4). No raw synthesis/repair log exists in the repo to adjudicate which is correct. See `stage6_difficulty_metrics.md`'s correction section for the full comparison — unresolved, not silently picked a side on.

### Metric Definitions:
* **Synthesis Success:** The LLM successfully produced a complete, validly-formatted C++ harness file (no unclosed braces, truncated output, or fatal syntactic format violations).
* **Compilation Success:** The harness compiled using our strict target flags. (Note: Iterations are split into 'compile-repair' for syntax/header fixes and 'post-compile behavioral-repair' for assertion or mock logic fixes discovered during fuzzing).
* **Linking Success:** The final binary linked. In our pipeline, `clang++` performs compiling and linking in a single step via injected source files rather than statically linked libraries, so this natively mirrors Compilation Success.
* **Executable Startup:** The binary executed correctly without segfaulting or crashing prior to invoking the fuzzing logic. (While `poll_out` and `isr` eventually hit divergent-mock faults *during* execution, they successfully started up and engaged the fuzzer loop).
* **Sanitizer-Clean Init:** The ASan/UBSan sanitizers verified there were no global buffer overflows or memory corruption issues during the harness's initialization phase.
* **Valid-Input Handling:** The harness's `LLVMFuzzerTestOneInput` correctly guarded itself against trivial out-of-bounds array reads by enforcing strict `size` constraints on the fuzzer's arbitrary byte buffer before executing the driver logic.
