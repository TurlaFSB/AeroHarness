"""
Target definitions for Work Plan item 2 (Dimension B self-repair statistical rigor).

Each entry's `body` is copied VERBATIM from zephyr-src/drivers/serial/uart_pl011.c
(confirmed line-for-line against that file during preparation, Oct 2 2026), with only
the `static` storage-class keyword stripped from the one function actually being
fuzzed in each target (so it gets external linkage and can be called from a
separately-compiled harness.cpp) -- any OTHER function it calls that isn't itself a
chosen target is embedded as a `static` helper in the same translation unit, kept
exactly as the real driver wrote it. No target function's logic is rewritten,
simplified, or reinterpreted; this is a copy-and-relink operation, not a
reimplementation. `helpers` lists those embedded dependency functions in the order
they must appear (callees before callers). `macros` lists the exact real PL011_*
bit-flag values (from uart_pl011_registers.h, independently re-read during
preparation) this target's body plus its helpers actually reference, pre-resolved
from BIT(n) to a hex literal -- fed to the LLM as ExtractedHeaderContext.magic_constants
so the prompt is not context-free (see FAILURE_TAXONOMY.md's entry on why the generic
CASTExtractor can't discover these on its own for real driver-style code).
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ItemTwoTarget:
    name: str
    signature: str  # one-line real declaration, semicolon-terminated, for the .h forward decl
    body: str        # real body of `name` itself (NOT including helpers), static keyword stripped
    helpers: List[str] = field(default_factory=list)  # real bodies of embedded static dependencies, in order
    macros: Dict[str, str] = field(default_factory=dict)  # name -> resolved hex value
    ccn: int = 0


TARGETS: List[ItemTwoTarget] = [

    # ---- CCN 1 band (8 of 14 available, chosen to avoid deep call chains so this
    # band is genuinely low-difficulty in practice, not just by the static metric) ----

    ItemTwoTarget(
        name="pwr_on_arm_pl011",
        signature="int pwr_on_arm_pl011(const struct device *dev);",
        body="""int pwr_on_arm_pl011(const struct device *dev)
{
    return 0;
}""",
        ccn=1,
    ),

    ItemTwoTarget(
        name="clk_enable_arm_pl011",
        signature="int clk_enable_arm_pl011(const struct device *dev, uint32_t clk);",
        body="""int clk_enable_arm_pl011(const struct device *dev, uint32_t clk)
{
    return 0;
}""",
        ccn=1,
    ),

    ItemTwoTarget(
        name="pl011_enable",
        signature="void pl011_enable(const struct device *dev);",
        body="""void pl011_enable(const struct device *dev)
{
    get_uart(dev)->cr |= PL011_CR_UARTEN;
}""",
        macros={"PL011_CR_UARTEN": "0x1"},
        ccn=1,
    ),

    ItemTwoTarget(
        name="pl011_disable",
        signature="void pl011_disable(const struct device *dev);",
        body="""void pl011_disable(const struct device *dev)
{
    get_uart(dev)->cr &= ~PL011_CR_UARTEN;
}""",
        macros={"PL011_CR_UARTEN": "0x1"},
        ccn=1,
    ),

    ItemTwoTarget(
        name="pl011_irq_tx_complete",
        signature="int pl011_irq_tx_complete(const struct device *dev);",
        body="""int pl011_irq_tx_complete(const struct device *dev)
{
    /* Check for UART is busy transmitting data. */
    return ((get_uart(dev)->fr & PL011_FR_BUSY) == 0);
}""",
        macros={"PL011_FR_BUSY": "0x8"},
        ccn=1,
    ),

    ItemTwoTarget(
        name="pl011_irq_rx_enable",
        signature="void pl011_irq_rx_enable(const struct device *dev);",
        body="""void pl011_irq_rx_enable(const struct device *dev)
{
    get_uart(dev)->imsc |= PL011_IMSC_RXIM | PL011_IMSC_RTIM;
}""",
        macros={"PL011_IMSC_RXIM": "0x10", "PL011_IMSC_RTIM": "0x40"},
        ccn=1,
    ),

    ItemTwoTarget(
        name="pl011_irq_err_disable",
        signature="void pl011_irq_err_disable(const struct device *dev);",
        body="""void pl011_irq_err_disable(const struct device *dev)
{
    get_uart(dev)->imsc &= ~PL011_IMSC_ERROR_MASK;
}""",
        macros={"PL011_IMSC_ERROR_MASK": "0x780"},
        ccn=1,
    ),

    ItemTwoTarget(
        name="pl011_irq_callback_set",
        signature=(
            "void pl011_irq_callback_set(const struct device *dev, "
            "uart_irq_callback_user_data_t cb, void *cb_data);"
        ),
        body="""void pl011_irq_callback_set(const struct device *dev,
                 uart_irq_callback_user_data_t cb,
                 void *cb_data)
{
    struct pl011_data *data = (struct pl011_data *)dev->data;

    data->irq_cb = cb;
    data->irq_cb_data = cb_data;
}""",
        ccn=1,
    ),

    # ---- CCN 3 band (all 5 available) ----

    ItemTwoTarget(
        name="pl011_set_flow_control",
        signature="void pl011_set_flow_control(const struct device *dev, bool rts, bool cts);",
        body="""void pl011_set_flow_control(const struct device *dev, bool rts, bool cts)
{
    volatile struct pl011_regs *uart = get_uart(dev);
    uint32_t cr = uart->cr;

    if (rts) {
        cr |= PL011_CR_RTSEn;
    } else {
        cr &= ~PL011_CR_RTSEn;
    }

    if (cts) {
        cr |= PL011_CR_CTSEn;
    } else {
        cr &= ~PL011_CR_CTSEn;
    }

    uart->cr = cr;
}""",
        macros={"PL011_CR_RTSEn": "0x4000", "PL011_CR_CTSEn": "0x8000"},
        ccn=3,
    ),

    ItemTwoTarget(
        name="pl011_set_baudrate",
        signature="int pl011_set_baudrate(const struct device *dev, uint32_t clk, uint32_t baudrate);",
        body="""int pl011_set_baudrate(const struct device *dev,
                   uint32_t clk, uint32_t baudrate)
{
    /* Avoiding float calculations, bauddiv is left shifted by 6 */
    uint64_t bauddiv = (((uint64_t)clk) << PL011_FBRD_WIDTH)
                / (baudrate * 16U);
    volatile struct pl011_regs *uart = get_uart(dev);

    if ((bauddiv < (1u << PL011_FBRD_WIDTH))
        || (bauddiv > (65535u << PL011_FBRD_WIDTH))) {
        return -EINVAL;
    }

    uart->ibrd = bauddiv >> PL011_FBRD_WIDTH;
    uart->fbrd = bauddiv & ((1u << PL011_FBRD_WIDTH) - 1u);

    barrier_dmem_fence_full();

    uart->lcr_h = uart->lcr_h;

    return 0;
}""",
        macros={"PL011_FBRD_WIDTH": "6"},
        ccn=3,
    ),

    ItemTwoTarget(
        name="pl011_fifo_fill",
        signature="int pl011_fifo_fill(const struct device *dev, const uint8_t *tx_data, int len);",
        body="""int pl011_fifo_fill(const struct device *dev,
                const uint8_t *tx_data, int len)
{
    volatile struct pl011_regs *uart = get_uart(dev);
    int num_tx = 0;

    while (!(uart->fr & PL011_FR_TXFF) && (len - num_tx > 0)) {
        uart->dr = tx_data[num_tx++];
    }
    return num_tx;
}""",
        macros={"PL011_FR_TXFF": "0x20"},
        ccn=3,
    ),

    ItemTwoTarget(
        name="pl011_fifo_read",
        signature="int pl011_fifo_read(const struct device *dev, uint8_t *rx_data, const int len);",
        body="""int pl011_fifo_read(const struct device *dev,
                uint8_t *rx_data, const int len)
{
    volatile struct pl011_regs *uart = get_uart(dev);
    int num_rx = 0;

    while ((len - num_rx > 0) && !(uart->fr & PL011_FR_RXFE)) {
        rx_data[num_rx++] = uart->dr;
    }

    return num_rx;
}""",
        macros={"PL011_FR_RXFE": "0x10"},
        ccn=3,
    ),

    ItemTwoTarget(
        name="pl011_irq_is_pending",
        signature="int pl011_irq_is_pending(const struct device *dev);",
        body="""int pl011_irq_is_pending(const struct device *dev)
{
    volatile struct pl011_regs *uart = get_uart(dev);

    return pl011_irq_rx_ready(dev) || pl011_irq_tx_ready(dev) ||
           (uart->mis & PL011_IMSC_ERROR_MASK);
}""",
        helpers=[
            """static int pl011_irq_rx_ready(const struct device *dev)
{
    volatile struct pl011_regs *uart = get_uart(dev);
    struct pl011_data *data = (struct pl011_data *)dev->data;

    if (!data->sbsa && !(uart->cr & PL011_CR_RXE)) {
        return false;
    }

    return ((uart->imsc & PL011_IMSC_RXIM) &&
        (!(uart->fr & PL011_FR_RXFE)));
}""",
            """static int pl011_irq_tx_ready(const struct device *dev)
{
    struct pl011_data *data = (struct pl011_data *)dev->data;
    volatile struct pl011_regs *uart = get_uart(dev);

    if (!data->sbsa && !(uart->cr & PL011_CR_TXE)) {
        return false;
    }

    return ((uart->imsc & PL011_IMSC_TXIM) &&
        (uart->ris & PL011_RIS_TXRIS || uart->fr & PL011_FR_TXFE));
}""",
        ],
        macros={
            "PL011_IMSC_ERROR_MASK": "0x780",
            "PL011_CR_RXE": "0x200",
            "PL011_IMSC_RXIM": "0x10",
            "PL011_FR_RXFE": "0x10",
            "PL011_CR_TXE": "0x100",
            "PL011_IMSC_TXIM": "0x20",
            "PL011_RIS_TXRIS": "0x20",
            "PL011_FR_TXFE": "0x80",
        },
        ccn=3,
    ),

    # ---- CCN 4 band (both available) ----

    ItemTwoTarget(
        name="pl011_is_readable",
        signature="bool pl011_is_readable(const struct device *dev);",
        body="""bool pl011_is_readable(const struct device *dev)
{
    struct pl011_data *data = (struct pl011_data *)dev->data;
    volatile struct pl011_regs *uart = get_uart(dev);
    uint32_t cr = uart->cr;

    if (!data->sbsa &&
        (!(cr & PL011_CR_UARTEN) || !(cr & PL011_CR_RXE))) {
        return false;
    }

    return (uart->fr & PL011_FR_RXFE) == 0U;
}""",
        macros={"PL011_CR_UARTEN": "0x1", "PL011_CR_RXE": "0x200", "PL011_FR_RXFE": "0x10"},
        ccn=4,
    ),

    ItemTwoTarget(
        name="pl011_irq_rx_ready",
        signature="int pl011_irq_rx_ready(const struct device *dev);",
        body="""int pl011_irq_rx_ready(const struct device *dev)
{
    volatile struct pl011_regs *uart = get_uart(dev);
    struct pl011_data *data = (struct pl011_data *)dev->data;

    if (!data->sbsa && !(uart->cr & PL011_CR_RXE)) {
        return false;
    }

    return ((uart->imsc & PL011_IMSC_RXIM) &&
        (!(uart->fr & PL011_FR_RXFE)));
}""",
        macros={"PL011_CR_RXE": "0x200", "PL011_IMSC_RXIM": "0x10", "PL011_FR_RXFE": "0x10"},
        ccn=4,
    ),

    # ---- CCN 5 band (both available) ----

    ItemTwoTarget(
        name="pl011_err_check",
        signature="int pl011_err_check(const struct device *dev);",
        body="""int pl011_err_check(const struct device *dev)
{
    int errors = 0;
    uint32_t rsr;

    rsr = get_uart(dev)->rsr;
    get_uart(dev)->rsr = 0;

    if (rsr & PL011_RSR_ECR_OE) {
        errors |= UART_ERROR_OVERRUN;
    }

    if (rsr & PL011_RSR_ECR_BE) {
        errors |= UART_BREAK;
    }

    if (rsr & PL011_RSR_ECR_PE) {
        errors |= UART_ERROR_PARITY;
    }

    if (rsr & PL011_RSR_ECR_FE) {
        errors |= UART_ERROR_FRAMING;
    }

    return errors;
}""",
        macros={
            "PL011_RSR_ECR_OE": "0x8",
            "PL011_RSR_ECR_BE": "0x4",
            "PL011_RSR_ECR_PE": "0x2",
            "PL011_RSR_ECR_FE": "0x1",
        },
        ccn=5,
    ),

    ItemTwoTarget(
        name="pl011_irq_tx_ready",
        signature="int pl011_irq_tx_ready(const struct device *dev);",
        body="""int pl011_irq_tx_ready(const struct device *dev)
{
    struct pl011_data *data = (struct pl011_data *)dev->data;
    volatile struct pl011_regs *uart = get_uart(dev);

    if (!data->sbsa && !(uart->cr & PL011_CR_TXE)) {
        return false;
    }

    return ((uart->imsc & PL011_IMSC_TXIM) &&
        (uart->ris & PL011_RIS_TXRIS || uart->fr & PL011_FR_TXFE));
}""",
        macros={
            "PL011_CR_TXE": "0x100",
            "PL011_IMSC_TXIM": "0x20",
            "PL011_RIS_TXRIS": "0x20",
            "PL011_FR_TXFE": "0x80",
        },
        ccn=5,
    ),

    # ---- CCN 6 band (the only one available) ----

    ItemTwoTarget(
        name="pl011_irq_tx_enable",
        signature="void pl011_irq_tx_enable(const struct device *dev);",
        body="""void pl011_irq_tx_enable(const struct device *dev)
{
    struct pl011_data *data = (struct pl011_data *)dev->data;
    volatile struct pl011_regs *uart = get_uart(dev);

    uart->imsc |= PL011_IMSC_TXIM;
    if (!data->sw_call_txdrdy) {
        return;
    }
    data->sw_call_txdrdy = false;

    if (!data->irq_cb) {
        return;
    }

    while (uart->imsc & PL011_IMSC_TXIM) {
        if ((uart->cr & PL011_CR_CTSEn) && !(uart->fr & PL011_FR_CTS)) {
            data->sw_call_txdrdy = true;
            uart->imsc |= PL011_IMSC_CTSMIM;
            break;
        }
        K_SPINLOCK(&data->irq_cb_lock) {
            data->irq_cb(dev, data->irq_cb_data);
        }
    }
}""",
        macros={
            "PL011_IMSC_TXIM": "0x20",
            "PL011_CR_CTSEn": "0x8000",
            "PL011_FR_CTS": "0x1",
            "PL011_IMSC_CTSMIM": "0x2",
        },
        ccn=6,
    ),
]

assert len(TARGETS) == 18, f"expected 18 targets, got {len(TARGETS)}"
assert len(TARGETS) == len({t.name for t in TARGETS}), "duplicate target name"
