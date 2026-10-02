Minimal include path for the isolated/blind/blackbox pl011 harnesses
(`fuzz_pl011_*.cpp`, `fuzz_pl011_*_blind.cpp`, `blackbox/fuzz_pl011_*_blackbox.cpp`).

These harnesses define their own local `struct device` and `DEVICE_MMIO_GET`
macro *before* including the real `uart_pl011_registers.h`, which itself
does `#include <zephyr/device.h>`. An empty `zephyr/device.h` here is
sufficient (and required) to satisfy that include without fatally erroring
*and* without re-defining `struct device`/`DEVICE_MMIO_GET` a second time.

Found Oct 2 2026: the previously-documented build flag for these harnesses
(`-Iharnesses/include`, per stage6_difficulty_metrics.md's "Tool
Verification" section) actually resolves to the Ablation B v2 scaffolding's
own non-empty `harnesses/include/zephyr/device.h`, which DOES define
`struct device` -- causing a real, previously-undiscovered compile failure
("redefinition of 'device'") for every isolated/blind pl011 harness, not
just new ones. Confirmed by direct reproduction: `clang++ -Iharnesses/include
harnesses/fuzz_pl011_poll_in.cpp` fails on current main. Use
`-Iharnesses/include_isolated` instead for any of these harnesses going
forward. Flagged here rather than silently worked around, since it means
the documented rebuild command in stage6_difficulty_metrics.md's
"Tool Verification" section needs a correction.
