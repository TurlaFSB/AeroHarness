# Formal Hardware Mocking Metrics

This document compiles formal metrics regarding peripheral extraction, mock generation, and runtime hardware fidelity, drawn directly from our empirical data across Stages 1, 4, 6, and 7.

## Core Metrics Table

| Metric | Numerator | Denominator | Result | Source Stage / Evidence |
| :--- | :--- | :--- | :--- | :--- |
| **Peripheral Identification Precision** | 53 (Real hardware registers isolated) | 53 (Total structs/fields flagged) | **Pre-fix: 31.3% (53 real / 169 total flagged). Post-fix: 100% (53/53, 0 false positives).** | **Stage 1 (Zephyr/Kinetis):** Our initial heuristic suffered a heavy noise ratio (flagging 116 fake software variables alongside the 53 real ones). The MMIO-detection generalization fix completely eliminated this noise, achieving 100% precision. |
| **Register Identification Recall** | All Ground-Truth Registers | All Ground-Truth Registers | **100%** | **Stage 1 (RIOT):** After the generalization fix (moving from 0% recall), the extraction script achieved 100% recall of the true hardware register types for the RIOT USART driver across all 4 linked source files. |
| **Stub Synthesis Success Rate** | 3 (Compilable harnesses) | 3 (Target functions) | **100%** | **Stage 6:** The LLM successfully synthesized fully compilable mock environments for `pl011_poll_in`, `pl011_poll_out`, and `pl011_isr`, correctly stubbing out all identified MMIO dependencies. |
| **Incorrect Mock Rate (Divergence)** | 2 (Divergent behaviors) | 6 (Distinct registers modeled) | **33.3%** | **Stage 6:** Across the 3 harnesses, exactly 6 distinct register types were mocked (`cr`, `fr`, `dr`, `mis`, `icr`, `imsc`). We encountered precisely 2 real divergences from hardware semantics: the busy-wait timeout on `fr/TXFF` and the Write-1-to-Clear (W1C) clobbering on `icr`. |
| **Runtime Fault Rate (Mock-Caused)** | 2 (Mock-caused faults) | 4 (Distinct harness-level compile+fuzz sessions) | **50.0%** | **Stage 6/7:** Counting strictly by independent harness-level compile+fuzz evaluation sessions (`poll_in`, `poll_out`, `isr` v1, and `isr` v2 repaired), exactly 2 sessions suffered mock-caused faults: the `poll_out` busy-wait timeout and the `isr` v1 assertion crash prior to the W1C fix. |

---
*Note: This data represents the exact findings compiled from the `AeroHarness` project history, strictly tracing back to documented extraction bugs, LLM reasoning repairs, and libFuzzer timeout/crash logs.*
