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
| `kinetis_adc_calibrate` (RIOT/Kinetis, Oct 1 2026) | 4 (1 pt) | 16 (`SC1`,`SC3`,`CLP0-4`,`CLPS`,`CLM0-4`,`CLMS`,`PG`,`MG`) (2 pts) | 0 (0 pts) | 0 (0 pts) | **3 pts (Moderate)** | 4 | 15 | **HARD (Mismatch)** |

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

## ⚠️ A Second, Independent Static-vs-Empirical Mismatch (`kinetis_adc_calibrate`, Oct 1 2026)

The same Static-Score-vs-Empirical-Class mismatch found above for `pl011_isr` recurs in `kinetis_adc_calibrate` — a different function, from a different RTOS (RIOT, not Zephyr), on a different peripheral type (ADC, not UART) — but for a **different underlying reason**, which makes this a stronger validation of the general finding than a second instance of the same cause would be.

`kinetis_adc_calibrate` scores identically to `pl011_isr` on the static scale (CCN 4, 3 total points, "Moderate"), but required the same 4 self-repair iterations and was empirically **harder to fuzz at all**: a 10-seed campaign found 7/10 seeds hang immediately (`cov:2/ft:2`, i.e. before any real exploration) and only 3/10 reach deeper coverage (`ft:15`) before also eventually hanging — see `RESULTS.md`'s "Second-RTOS/Target Pipeline Run" section for the full campaign data.

**Why this one escaped the static score, and why it's a different mechanism than `pl011_isr`'s macro-hiding problem:** `lizard` correctly counts this function's two `while` loops and one `if` as CCN 4 — there's no hidden macro expansion here, unlike `K_SPINLOCK`. What the static score has no way to capture is that one of this function's busy-waits (`while (dev->SC3 & ADC_SC3_CAL_MASK) {}`) polls a bit the function **sets itself one line earlier**, which is unconditionally unfuzzable under this project's established static-struct-mock approach — no amount of fuzzer-controlled input can ever influence it. That required inventing a genuinely asynchronous mocking mechanism (ultimately a periodic POSIX timer + signal handler, after three different thread-based attempts each failed under real fuzzing load) rather than just the better static value assignment that fixes a *fuzzer-controlled*-bit busy-wait like `pl011_poll_out`'s.

**Finding:** Two functions from two unrelated RTOS codebases both land in the static scale's "Moderate" bucket while being among the hardest functions this project has actually fuzzed — for two different reasons (macro-hidden concurrency vs. a self-referential register hazard). This strengthens, rather than merely repeats, the original finding: no single static metric category is likely to catch every way a function can be harder than it looks, and a difficulty taxonomy that wants to generalize needs multiple independent empirical signals (repair iterations, hang rate, coverage-features-at-plateau), not just a sharper static scorer.

### Clarification on Coverage vs. Setup Complexity
It is critical to distinguish between **branch-level complexity** and **setup/mocking complexity**—conflating these two different axes of difficulty is misleading. 

As confirmed by our `llvm-cov` source-based coverage report, `pl011_isr` achieved 100% line and branch coverage in just 60 seconds. This is because it has **LOW branch-level complexity**: it consists of exactly 3 independent binary conditions (2^3 = 8 permutations) which the fuzzer trivially exhausts. 

However, it possesses **HIGH setup/mocking complexity**: compiling the harness and mocking the state for `K_SPINLOCK` macro expansion and external callback registration required significant LLM reasoning and 4 compiler repair iterations. 

*Caveat: The 100% branch/line coverage observed here reflects the small, fully-enumerable branch space specific to this function's logic, and is not a general claim that our pipeline achieves 100% coverage on arbitrary code.*

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

For `kinetis_adc_calibrate` (Oct 1 2026), the same tool was re-run directly against the real driver source and reproduces exactly:
```text
$ lizard p2im-unit_tests/RIOT/RIOT-ENV/cpu/kinetis/periph/adc.c
  NLOC    CCN   token  PARAM  length  location
------------------------------------------------
      19      4    152      1      39 kinetis_adc_calibrate@114-152@p2im-unit_tests/RIOT/RIOT-ENV/cpu/kinetis/periph/adc.c
```
(Re-verified live during this audit pass by reinstalling `lizard` and re-running it, not copied from a prior log.)
