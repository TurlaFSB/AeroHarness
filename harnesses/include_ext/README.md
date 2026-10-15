# Extended mock Zephyr headers (labeled variant)

`run_ablation_g.py --mock-headers ext` puts this directory BEFORE `harnesses/include` on the
include path. The frozen v1 mock in `harnesses/include` is untouched and remains the headline
configuration. This variant only adds names that real Zephyr provides (`mm_reg_t`, `mem_addr_t`,
`mmio_addr_t`, `ARG_UNUSED`, `uart_irq_callback_user_data_t`, `k_spinlock_init`) and lets
`struct device.mmio_base` accept either a pointer or an integer address (C++ only). See the
comment at the top of `zephyr/device.h` for the evidence that motivated it.
