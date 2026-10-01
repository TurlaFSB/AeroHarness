# AeroHarness — Stage 6 Enhancement: Call-Graph-Guided State-Machine Harness

### Task 1: Call-graph prerequisite discovery

- **Source of ordering:** Inferred from driver naming conventions, NOT from the AST call-graph.
- **Details:** The actual Stage 1 `ast_output.json` for these functions correctly resolved internal calls but contained zero ordering constraints or cross-API dependencies in its `calls` fields. 

**Exact JSON fragments used:**
```json
"pl011_init": {
  "calls": ["DEVICE_MMIO_MAP", "get_uart", "defined", "reset_line_toggle_dt", "clock_control_on", "clock_control_get_rate", "pinctrl_apply_state", "pwr_on_func", "pl011_disable", "pl011_disable_fifo", "clk_enable_func", "pl011_runtime_configure_internal", "FIELD_PREP", "pl011_enable_fifo", "barrier_isync_fence_full", "irq_config_func", "pl011_enable", "GENMASK", "BIT"]
}
"pl011_poll_out": {
  "calls": ["get_uart", "BIT"]
}
"pl011_poll_in": {
  "calls": ["get_uart", "pl011_is_readable"]
}
"pl011_isr": {
  "calls": ["get_uart", "K_SPINLOCK", "irq_cb", "BIT"]
}
```
Because the call graph contained no prerequisite checks, I fell back to standard RTOS knowledge: `pl011_init` must execute first to populate the `struct device` config fields and unmask hardware clocks, otherwise undefined behavior occurs. The dispatcher loops enforce `is_initialized = true` before allowing other commands.

### Task 2: State-machine dispatcher harness

The harness (`fuzz_state_machine.c`) builds an execution loop across the fuzzer's buffer, using `cmd = data[i] % 4` to branch between the four APIs while concurrently fuzzing MMIO registers (`dr`, `fr`, `mis`, `imsc`).

**Self-repair iteration log (Compiler-Oracle Feedback):**
1. **Iteration 1**: Failed with `fatal error: 'zephyr/device.h' file not found`.
   - *Fix*: Created a `fake_zephyr` directory with empty dummy headers to satisfy Zephyr's `#include` tree, mimicking Stage 6's stubbing approach.
2. **Iteration 2**: Failed with 20 errors, including `function-like macro 'DT_ANY_COMPAT_HAS_PROP_STATUS_OKAY' is not defined`, `use of undeclared identifier 'EINVAL'`, and `UART_CFG_PARITY_NONE`.
   - *Fix*: Mocked the device tree query macro to return `1` and defined the required POSIX error codes and `UART_CFG_*` macros in the harness preamble.
3. **Iteration 3**: Failed with `call to undeclared function 'pl011_isr'` and `variable has incomplete type 'struct uart'`.
   - *Fix*: Discovered that `pl011_isr` was stripped out by the C preprocessor because `#define CONFIG_UART_INTERRUPT_DRIVEN 1` was missing. Added it. Mocked `DEVICE_API` with a dummy struct (`struct uart_driver_api`) to satisfy Zephyr's API binding macro.
4. **Iteration 4**: Compiled successfully.

**Compile evidence:**
```
$ clang -O1 -g -fsanitize=fuzzer,address,undefined -Ifake_zephyr fuzz_state_machine.c -o fuzz_sm
(Success, exit code 0)
```

### Task 3: Struct-aware mocking

- **Applicable:** Yes.
- **Details:** The PL011 driver functions require `struct device *dev`, which points to `struct pl011_data` and `struct pl011_config`. The harness synthesizes these with boundary-valid types rather than zeroing them out:
  ```c
  struct pl011_data pl_data; memset(&pl_data, 0, sizeof(pl_data));
  struct pl011_config pl_config; memset(&pl_config, 0, sizeof(pl_config));
  
  pl_data.sbsa = 0;
  pl_data.clk_freq = 4000000;
  pl_config.fifo_disable = false;
  pl_data.irq_cb = dummy_irq_cb;
  ```

### Verification

**Fuzzing run (1,000,000 executions):**
- **Executions/sec**: ~125,000 exec/s
- **Coverage reached**: `cov: 76 ft: 566` (edges/feature counters)

**Coverage comparison vs. 3 isolated harnesses:**
The original harnesses (ran locally to pull exact metrics from `fuzz_bin` binaries) achieved:
- `poll_in`: 11 total PCs, reached exactly `cov: 8, ft: 9`
- `isr`: 23 total PCs, reached exactly `cov: 18, ft: 19`
- `poll_out`: 8 total PCs. I ran a true fuzzing session which hung due to a timeout on its very first mutation (input: `0xa9,0x3a,`). The last logged coverage before timeout was exactly `cov: 2, ft: 2`.
- **State-Machine Harness** reached exactly `cov: 76, ft: 566` (out of 199 total PCs loaded).

**Important context on compilation scope and the PC jump:**
The jump from 42 total PCs (across all 3 isolated harnesses) to 199 total PCs in the dispatcher reflects two conflated factors that must be separated for the paper:
1. **Scope Difference:** The 3 original isolated harnesses compiled a *narrower scope*. They physically copy-pasted only the target function (`pl011_poll_out`, `pl011_isr`, etc.) into the harness. The dispatcher harness, however, utilized `#include "uart_pl011.c"`, bringing in the *entire* driver file. Because `pl011_init` recursively calls `pl011_runtime_configure_internal` (which has four massive switch-statements) and `pl011_set_baudrate`, the denominator exploded to 199 PCs due to this vast initialization tree being compiled and inlined.
2. **Sequencing Advantage:** The `cov: 76` vs `cov: 18/9/2` comparison reflects *both* the expanded instrumented surface (due to compiling `init`'s helpers) AND the state-machine's ability to reach deeper states in `isr`/`poll_out` (e.g. bypassing the `irq_cb` NULL checks). Therefore, we cannot claim the 76 edges came entirely from stateful sequencing; a significant portion stems simply from compiling `pl011_init`.

**Crashes / Hangs Evaluation:**

1. **`pl011_poll_out` Busy-Wait Hang (Re-confirmed)**
   The fuzzer hit a 3-second timeout at `while (uart->fr & PL011_FR_TXFF) {;}` inside `pl011_poll_out`. 
   *Correction*: This is **NOT** a new finding. It is the exact same divergence class documented during the original Stage 6 work. The original isolated harness purposely routed around it by hardcoding `regs.fr = 0` in some instances, or hung at `cov: 2` in others if the fuzzer controlled the flag. The state-machine harness successfully reproduced/re-confirmed this hang organically under compound fuzzing.
   *(Note: To permit further state exploration, a static fix `regs.fr &= ~PL011_FR_TXFF` was permanently baked into the harness source code. The final `cov: 76` metric was recorded on a clean 1,000,000-execution run that had this fix in place from the very first execution, ensuring fully reproducible coverage).*

2. **`pl011_isr` Infinite Loop (Artificial Mock Artifact)**
   I scrutinized the potential for an infinite loop inside `pl011_isr` at `while (uart->imsc & PL011_IMSC_TXIM)`.
   Mechanistically, this is entirely different from the `poll_out` hang: it spins on the `IMSC` mask, not the hardware FIFO status, and it delegates loop termination to `data->irq_cb(dev, data->irq_cb_data)`. 
   If a trivial, no-op `dummy_irq_cb` is supplied that doesn't clear the interrupt mask, the CPU spins forever. However, I confirm this is an **artificial, missing-mock artifact, NOT a genuine RTOS bug**. A real Zephyr UART application callback (e.g., from the console subsystem) rightfully handles the interrupt and mutates the mask. If our harness supplies a dummy function that does nothing, the resulting hang is just a harness logic error. Therefore, I explicitly programmed `dummy_irq_cb` to clear `PL011_IMSC_TXIM` to prevent the artifact hang.
