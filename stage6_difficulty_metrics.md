# Stage 6 Functions: Objective Difficulty Indicators

To empirically classify the difficulty of the three synthesized libFuzzer harnesses (`pl011_poll_in`, `pl011_poll_out`, `pl011_isr`), we computed objective indicators across four metrics:

1. **Cyclomatic Complexity**: Computed using the industry-standard `lizard` static analysis tool on the source code.
2. **MMIO Register Count**: The number of distinct hardware register fields the function (and its sub-functions) depends on, mapped from Stage 1/3 extraction data.
3. **Call-Graph Depth**: How many function calls deep the execution path extends from the entry point (excluding standard RTOS inline macros like `K_SPINLOCK` or pointer getters).
4. **Init Prerequisites**: Dependencies on prior state (e.g., whether the function requires a specific initialization function to have been called or specific enable bits to be set to reach its core payload).

## Objective Metrics Table

| Function | Cyclomatic Complexity | MMIO Register Count | Call-Graph Depth | Init Prerequisites | Classification |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `pl011_poll_out` | 2 | 2 (`fr`, `dr`) | 0 | 0 | **Easy** |
| `pl011_poll_in` | 2 | 3 (`cr`, `fr`, `dr`) | 1 (`pl011_is_readable`) | 1 (Requires UARTEN/RXE bits) | **Moderate** |
| `pl011_isr` | 4 | 3 (`mis`, `icr`, `imsc`) | 0 | 1 (Requires `irq_cb` setup) | **Moderate** |

## Classification Reasoning & Thresholds

The classification labels (Easy / Moderate / Hard) are strictly assigned based on the following objective thresholds:

* **Easy**: `Cyclomatic Complexity <= 2` AND `MMIO Register Count <= 2` AND `Call-Graph Depth == 0` AND `Init Prerequisites == 0`.
  * **Reasoning**: Requires minimal fuzzer effort. The fuzzer hits the target payload immediately by guessing a single return status on a single control register, without passing through other modeled states or sub-functions.
  * **Example (`pl011_poll_out`)**: Meets all Easy thresholds. It simply spins on the `fr` (Flag Register) until there is space in the FIFO, then writes to `dr` (Data Register).

* **Moderate**: `Cyclomatic Complexity 3-4` OR `MMIO Register Count 3-4` OR `Call-Graph Depth >= 1` OR `Init Prerequisites >= 1`.
  * **Reasoning**: Requires specific sequences of state bits, conditional branching through error/status registers, or calling into sub-functions to reach terminal payload states. The fuzzer must intelligently navigate multiple mocked hardware registers.
  * **Example (`pl011_poll_in`)**: Meets Moderate thresholds due to Depth (1) and MMIO count (3). It calls `pl011_is_readable`, which requires the fuzzer to accurately mock the `cr` (Control Register) to have both `UARTEN` and `RXE` bits set, plus the `fr` register to indicate data is present, before it can read `dr`.
  * **Example (`pl011_isr`)**: Meets Moderate thresholds due to Cyclomatic Complexity (4) and MMIO count (3). It evaluates multiple conditional branches against `mis` (Masked Interrupt Status), dynamically writes to `icr` and `imsc`, and ultimately requires the `irq_cb` to have been initialized to execute the callback path.

* **Hard**: `Cyclomatic Complexity >= 5` AND `MMIO Register Count >= 4` AND `Call-Graph Depth >= 2`.
  * **Reasoning**: Requires deep execution chains, navigating complex error handling, and coordinating many mocked hardware registers to proceed without crashing or returning early. (None of the three selected Stage 6 functions fall into this category, as they are localized unit-test targets).

---

## Tool Verification
Cyclomatic complexity was computed using `lizard` v1.24.0 (`pip install lizard`).
Command executed: `lizard uart_pl011.c > stage6_complexity.log`

Extract of the relevant tool output for these three functions:
```text
  NLOC    CCN   token  PARAM  length  location  
------------------------------------------------
       9      2     54      2      13 pl011_poll_in@204-216@uart_pl011.c
       9      2     45      2      13 pl011_poll_out@218-230@uart_pl011.c
      17      4    100      1      26 pl011_isr@717-742@uart_pl011.c
```
The full raw output is preserved in `stage6_complexity.log`.
