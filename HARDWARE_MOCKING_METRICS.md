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

## Second-RTOS/Target Data Point: RIOT OS Kinetis ADC (`kinetis_adc_calibrate`, Oct 1 2026)

The table above is Zephyr/UART-only. Reporting the Kinetis ADC numbers as a separate row (rather than blending them into the table above) because the two datasets differ in scope and severity, and averaging them would hide that difference.

| Metric | Numerator | Denominator | Result | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Stub Synthesis Success Rate** | 1 (eventually compilable, non-hanging harness) | 1 (target function) | **100% eventual**, but via 5 total compile+fuzz sessions (4 failed, 1 succeeded) — see Runtime Fault Rate below | Matches the project's "100% eventual success" framing elsewhere, but the path there was materially harder than any Zephyr harness. |
| **Incorrect Mock Rate (Divergence)** | 2 (divergent register behaviors: `SC3`/CAL self-hazard, `SC1`/COCO busy-wait) | 16 (distinct register names modeled, counting each of `SC1`,`SC3`,`CLP0-4`,`CLPS`,`CLM0-4`,`CLMS`,`PG`,`MG` once) | **12.5%** | Lower *rate* than Zephyr's 33.3%, but **higher severity**: one of the two Kinetis divergences (`SC3`/CAL) is unconditionally unfuzzable under static mocking for every input, whereas all of Zephyr's documented divergences (and Kinetis's own `SC1`/COCO case) are only conditionally hit, i.e. some inputs avoid them. Rate and severity are different axes and this project's prior framing (rate only) would have under-weighted this case. |
| **Runtime Fault Rate (Mock-Caused)** | 4 (mock-caused hangs: per-call thread, busy-spin-starved thread, condvar-thread-handoff failure, one-shot-timer race) | 5 (independent compile+fuzz sessions across the self-repair history) | **80%** | Nearly double Zephyr/UART's 50% (2/4) — the self-set-and-spin hazard class is a harder mocking problem than anything in the original 3 Zephyr harnesses, consistent with `stage6_difficulty_metrics.md`'s planned new Kinetis row. |

**Aggregate across both datasets** (Zephyr/UART + Kinetis ADC, for anyone who wants one number): Incorrect Mock Rate = 4/22 distinct registers (18.2%); Runtime Fault Rate = 6/9 independent sessions (66.7%). These blended figures are provided for convenience only — the per-dataset rows above are the ones that should be cited, since the blend obscures the severity difference noted above.

---
*Note: This data represents the exact findings compiled from the `AeroHarness` project history, strictly tracing back to documented extraction bugs, LLM reasoning repairs, and libFuzzer timeout/crash logs.*
