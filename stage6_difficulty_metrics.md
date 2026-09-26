# Stage 6 Functions: Objective Difficulty Indicators

To empirically classify the difficulty of the three synthesized libFuzzer harnesses (`pl011_poll_in`, `pl011_poll_out`, `pl011_isr`), we computed objective indicators across both static metrics and empirical fuzzing results. 

To ensure a balanced and reachable difficulty scale, we apply a consistent **Additive Point Score** based on these metrics.

## Additive Point System (Static Metrics)
Each static metric contributes to a difficulty score:
* **Cyclomatic Complexity (CCN)**: <=2 (0 pts) | 3-4 (1 pt) | 5+ (2 pts)
* **MMIO Register Dependencies**: <=2 (0 pts) | 3-4 (1 pt) | 5+ (2 pts)
* **Call-Graph Depth**: 0 (0 pts) | 1 (1 pt) | 2+ (2 pts)
* **Init Prerequisites**: 0 (0 pts) | 1 (1 pt) | 2+ (2 pts)

**Classification Thresholds:**
* **Easy:** 0-1 points
* **Moderate:** 2-3 points
* **Hard:** 4+ points

## Objective Metrics Table

| Function | Cyclomatic Complexity | MMIO Register Count | Call-Graph Depth | Init Prerequisites | Static Score & Class | Repair Iterations | Fuzzing Features | Empirical Class |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `pl011_poll_out` | 2 (0 pts) | 2 (`fr`, `dr`) (0 pts) | 0 (0 pts) | 0 (0 pts) | **0 pts (Easy)** | 1 | 6 | **Easy** |
| `pl011_poll_in` | 2 (0 pts) | 3 (`cr`, `fr`, `dr`) (1 pt) | 1 (`is_readable`) (1 pt) | 1 (`UARTEN`/`RXE`) (1 pt) | **3 pts (Moderate)** | 2 | 2 | **Moderate** |
| `pl011_isr` | 4 (1 pt) | 3 (`mis`, `icr`, `imsc`) (1 pt) | 0 (0 pts) | 1 (`irq_cb` setup) (1 pt)| **3 pts (Moderate)** | 4 | 17 | **HARD (Mismatch)** |

---

## ⚠️ The Static vs. Empirical Complexity Mismatch (pl011_isr)

While the additive static scale cleanly ranks `poll_out` (Easy) and `poll_in` (Moderate), there is a **severe mismatch** between the static classification of `pl011_isr` (Moderate) and its actual, empirically observed fuzzing difficulty (Hard). 

Despite a relatively low static Cyclomatic Complexity (CCN = 4), `pl011_isr` required **4 repair iterations** to successfully compile/mock, and the fuzzer ultimately discovered **17 distinct coverage features** within it—vastly outstripping the other functions. 

### Why did Lizard miss this?
`lizard` performs static lexical analysis without expanding C preprocessor macros. Here is the raw source code of `pl011_isr` exactly as `lizard` saw it:

```c
void pl011_isr(const struct device *dev)
{
	struct pl011_data *data = dev->data;
	volatile struct pl011_regs *uart = get_uart(dev);

	/* Clear CTS modem status interrupt and disable it */
	if (uart->mis & PL011_IMSC_CTSMIM) {
		uart->icr = PL011_IMSC_CTSMIM;
		uart->imsc &= ~PL011_IMSC_CTSMIM;
	}

	/* Clear error interrupts (OE, BE, PE, FE) so they don't
	 * re-fire endlessly.  The error status is still available
	 * via uart_err_check() which reads RSR.
	 */
	if (uart->mis & PL011_IMSC_ERROR_MASK) {
		uart->icr = uart->mis & PL011_IMSC_ERROR_MASK;
	}

	/* Verify if the callback has been registered */
	if (data->irq_cb) {
		K_SPINLOCK(&data->irq_cb_lock) {
			data->irq_cb(dev, data->irq_cb_data);
		}
	}
}
```

Lizard calculates a CCN of 4 by simply counting the function entry (+1) and the three `if` statements (+3). 

However, it completely glosses over `K_SPINLOCK(&data->irq_cb_lock) { ... }`. Because Lizard does not run a preprocessor, it treats `K_SPINLOCK` as a simple block or function call. In reality, in a Zephyr RTOS build, `K_SPINLOCK` expands into complex concurrency and locking loops. The fuzzer must explore all of these expanded branches dynamically (hence 17 coverage features), and the LLM must successfully mock the RTOS spinlock state (hence 4 repair iterations). 

**Finding:** Static complexity tools like `lizard` can dangerously underreport the difficulty of RTOS firmware functions by ignoring macro-expanded concurrency abstractions, making empirical metrics (repair iterations, coverage features) essential for a true difficulty classification.

---

## Tool Verification
Cyclomatic complexity was computed using `lizard` v1.24.0.
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
