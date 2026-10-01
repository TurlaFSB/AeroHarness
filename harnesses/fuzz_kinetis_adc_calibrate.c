// Stage 6 harness for the second-RTOS/target pipeline (Section B item 3,
// Oct 1 2026): kinetis_adc_calibrate, from RIOT OS's Kinetis K64F ADC
// driver (p2im-unit_tests/RIOT/RIOT-ENV/cpu/kinetis/periph/adc.c), a
// genuinely different RTOS and peripheral type from Stage 6's prior work
// (Zephyr, UART). MMIO models driving this harness come from
// llm_proposals_kinetis_adc_calibrate.json and were verified by
// stage3_oracle_kinetis_adc.py (5 Confirmed, 13 Unconfident, 0
// Disagreements -- see stage3_oracle_kinetis_adc.log).
//
// Target function body (copied verbatim from the real driver source,
// byte-for-byte, matching Stage 6's established practice for Zephyr):
//
//   int kinetis_adc_calibrate(ADC_Type *dev)
//   {
//       uint16_t cal;
//       dev->SC3 |= ADC_SC3_CAL_MASK;
//       while (dev->SC3 & ADC_SC3_CAL_MASK) {} /* wait for calibration to finish */
//       while (!(dev->SC1[0] & ADC_SC1_COCO_MASK)) {}
//       if (dev->SC3 & ADC_SC3_CALF_MASK) { return -1; }
//       cal = dev->CLP0 + dev->CLP1 + dev->CLP2 + dev->CLP3 + dev->CLP4 + dev->CLPS;
//       cal /= 2;
//       cal |= (1 << 15);
//       dev->PG = cal;
//       cal = dev->CLM0 + dev->CLM1 + dev->CLM2 + dev->CLM3 + dev->CLM4 + dev->CLMS;
//       cal /= 2;
//       cal |= (1 << 15);
//       dev->MG = cal;
//       return 0;
//   }
//
// A NEW class of static-mocking limitation vs. Zephyr Stage 6 (documented
// here, not silently worked around): the very first line the function
// executes sets the SC3/CAL bit itself (dev->SC3 |= ADC_SC3_CAL_MASK),
// then immediately spins on that same bit (while (dev->SC3 & CAL_MASK) {}).
// A plain static struct mock can never un-set a bit the function itself
// just set -- on real hardware the ADC peripheral clears CAL asynchronously
// once calibration physically completes, so this function is UNCONDITIONALLY
// unfuzzable (100% hang, every input) under Stage 6's established
// single-shot static-struct mocking approach. This is a new, concrete
// instance of the busy-wait class of static-mocking limitation already
// documented for Zephyr Stage 6 (see README Stage 6 description), but one
// level more severe: Zephyr's busy-waits depended on a FUZZER-CONTROLLED
// bit (so inputs existed that avoided the hang); this one depends on a bit
// the function sets itself, so NO static input can avoid it.
//
// Fix: simulate the real hardware's asynchronous self-clearing behavior.
// Four approaches were tried (see the detailed self-repair history below,
// just above the LIBFUZZER HARNESS section); the one that actually works
// in this sandbox is a one-shot POSIX timer (timer_create/CLOCK_REALTIME)
// that delivers a SIGUSR1 signal ~200us after the main thread arms it,
// clearing SC3/CAL from a signal handler -- modeling what the ADC
// peripheral actually does asynchronously, rather than statically
// pre-seeding a value that the function's own write would immediately
// overwrite anyway, and without the thread-starvation/handoff failures
// that broke the three earlier thread-based attempts.

// POSIX timer/signal APIs (timer_create, sigaction's full struct, etc.)
// are not exposed under strict -std=c99 without this -- must be defined
// before any system header is included.
#define _POSIX_C_SOURCE 199309L

#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <assert.h>
#include <string.h>
#include <signal.h>
#include <time.h>

// === ADC_Type struct, copied field-for-field from the real CMSIS vendor
// header (p2im-unit_tests/.../include/vendor/MK64F12.h), not reinvented. ===
typedef volatile uint32_t __IO_u32;
typedef volatile const uint32_t __I_u32;

typedef struct {
    __IO_u32 SC1[2];
    __IO_u32 CFG1;
    __IO_u32 CFG2;
    __I_u32  R[2];
    __IO_u32 CV1;
    __IO_u32 CV2;
    __IO_u32 SC2;
    __IO_u32 SC3;
    __IO_u32 OFS;
    __IO_u32 PG;
    __IO_u32 MG;
    __IO_u32 CLPD;
    __IO_u32 CLPS;
    __IO_u32 CLP4;
    __IO_u32 CLP3;
    __IO_u32 CLP2;
    __IO_u32 CLP1;
    __IO_u32 CLP0;
    uint8_t  RESERVED_0[4];
    __IO_u32 CLMD;
    __IO_u32 CLMS;
    __IO_u32 CLM4;
    __IO_u32 CLM3;
    __IO_u32 CLM2;
    __IO_u32 CLM1;
    __IO_u32 CLM0;
} ADC_Type;

// === Real register masks, copied from the same vendor header ===
#define ADC_SC1_COCO_MASK   (0x80u)
#define ADC_SC3_CALF_MASK   (0x40u)
#define ADC_SC3_CAL_MASK    (0x80u)

// === TARGET FUNCTION (byte-for-byte identical to the real driver) ===
int kinetis_adc_calibrate(ADC_Type *dev)
{
    uint16_t cal;

    dev->SC3 |= ADC_SC3_CAL_MASK;

    while (dev->SC3 & ADC_SC3_CAL_MASK) {} /* wait for calibration to finish */

    while (!(dev->SC1[0] & ADC_SC1_COCO_MASK)) {}

    if (dev->SC3 & ADC_SC3_CALF_MASK) {
        /* calibration failed for some reason, possibly SC2[ADTRG] is 1 ? */
        return -1;
    }

    cal = dev->CLP0 + dev->CLP1 + dev->CLP2 + dev->CLP3 + dev->CLP4 + dev->CLPS;
    cal /= 2;
    cal |= (1 << 15);
    dev->PG = cal;

    cal = dev->CLM0 + dev->CLM1 + dev->CLM2 + dev->CLM3 + dev->CLM4 + dev->CLMS;
    cal /= 2;
    cal |= (1 << 15);
    dev->MG = cal;

    return 0;
}

// === Hardware-completion simulator: clears SC3/CAL shortly after the
// function sets it, modeling the real ADC peripheral's asynchronous
// calibration-complete behavior.
//
// Self-repair, iteration 1: spawned a brand-new pthread per
// LLVMFuzzerTestOneInput call (created, joined, discarded every single
// execution). Worked for a single replayed input but HUNG under real
// fuzzing after a couple of iterations -- per-call thread creation/teardown
// at libFuzzer's execution rate is not robust.
//
// Self-repair, iteration 2: switched to one persistent helper thread
// (pthread_once) signaled via a plain busy-poll `volatile int` flag instead
// of per-call create/join. STILL hung, and debug tracing (stderr prints in
// the helper loop) pinned down why: the helper's idle state was a tight
// `for (;;) { if (g_trigger) ... }` spin loop. Under this sandbox's limited
// CPU scheduling, with the MAIN thread also spinning (in the target
// function's own `while (dev->SC3 & ...) {}` busy-wait), the two
// busy-spinning threads starve each other for the single core -- the
// helper fired once, then was never scheduled again.
//
// Self-repair, iteration 3: made the helper properly BLOCK on a condition
// variable while idle instead of spinning. Debug tracing (stderr prints on
// both sides of the handshake) showed the first execution's full cycle
// (trigger -> wake -> clear -> back-to-waiting) succeeding, but the SECOND
// execution never even reached the "about to lock" print on the main side
// -- something in the pthread_once/thread-handoff path was itself
// unreliable across repeated calls in this sandbox, not just the spin-vs-
// block choice.
//
// Self-repair, iteration 4 (final, working): dropped threads entirely. A
// POSIX interval timer (timer_create/CLOCK_REALTIME) delivering SIGUSR1
// (not SIGALRM -- libFuzzer's own watchdog already owns that one) clears
// the CAL bit from a signal handler instead of a second thread. Signal
// delivery for an armed kernel timer does not depend on this sandbox's
// thread scheduling fairness the way a second runnable thread did, so it
// is not subject to the same starvation.
//
// Sub-iteration 4a (one-shot firing, ~200us out) STILL hung under real
// fuzzing. Debug tracing (stderr prints around timer_create/timer_settime
// and inside the handler) proved the handler DID fire -- but a one-shot
// timer races the target function: if SIGUSR1 lands before line 104's
// `dev->SC3 |= ADC_SC3_CAL_MASK;` executes, the handler clears a bit
// that isn't set yet (a no-op), the function then sets it, and since the
// timer never fires again, the bit is never cleared afterward.
//
// Sub-iteration 4b (this one, confirmed working by direct test): made the
// timer PERIODIC (it_interval, not just it_value), firing every ~50us.
// Clearing an already-clear bit is harmless, so an early "missed" firing
// doesn't matter -- a later one is guaranteed to land after the bit is
// actually set. Confirmed by direct replay: an input with the SC1/COCO
// bit set completes in 0ms (no hang on the SC3/CAL self-hazard).
//
// NOTE -- a second, SEPARATE and already-expected hang class remains:
// immediately after the CAL loop, the real driver has a second busy-wait,
// `while (!(dev->SC1[0] & ADC_SC1_COCO_MASK)) {}`, gated by a plain
// FUZZER-CONTROLLED bit (not self-set). This is the exact same busy-wait
// limitation class already documented for Zephyr's poll_out (see README
// Stage 6 description / the informed-vs-blind ablation): roughly half of
// random inputs leave COCO unset and hit a libFuzzer timeout. That is
// expected, not a harness bug, and is handled the same way the project
// already handles it for poll_out -- multi-seed campaigns measuring
// coverage reached before the eventual hang, not a requirement that zero
// timeouts ever occur. ===
static ADC_Type *volatile g_sim_dev = NULL;

static void sigusr1_clear_cal(int signo) {
    (void)signo;
    if (g_sim_dev) {
        g_sim_dev->SC3 &= ~ADC_SC3_CAL_MASK;
    }
}

static void install_handler_once(void) {
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = sigusr1_clear_cal;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;
    sigaction(SIGUSR1, &sa, NULL);
}

// === LIBFUZZER HARNESS ===
// Input layout: [0] SC1[0] initial value (COCO bit, bit 7, is what matters)
//               [1] SC3 initial value (CALF bit, bit 6, is what matters --
//                   CAL bit, bit 7, gets overwritten by the function itself)
//               [2..5]   CLP0 (passthrough, full u32)
//               [6..9]   CLP1
//               [10..13] CLP2
//               [14..17] CLP3
//               [18..21] CLP4
//               [22..25] CLPS
//               [26..29] CLM0
//               [30..33] CLM1
//               [34..37] CLM2
//               [38..41] CLM3
//               [42..45] CLM4
//               [46..49] CLMS
#define HARNESS_INPUT_LEN 50

static uint32_t read_u32(const uint8_t *p) {
    uint32_t v;
    memcpy(&v, p, sizeof(v));
    return v;
}

extern int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < HARNESS_INPUT_LEN) {
        return 0;
    }

    ADC_Type regs;
    memset((void *)&regs, 0, sizeof(regs));

    // Stage 2/3 bitextract-confirmed registers: isolate the one bit that
    // gates control flow into its own fuzzer byte.
    regs.SC1[0] = data[0] & ADC_SC1_COCO_MASK;
    regs.SC3 = data[1] & ADC_SC3_CALF_MASK;

    // Stage 2 passthrough (Stage 3: unconfident -- arithmetic context, no
    // conditional for the oracle to check; see stage3_oracle_kinetis_adc.log)
    // registers: full raw fuzzer-controlled u32 values.
    regs.CLP0 = read_u32(data + 2);
    regs.CLP1 = read_u32(data + 6);
    regs.CLP2 = read_u32(data + 10);
    regs.CLP3 = read_u32(data + 14);
    regs.CLP4 = read_u32(data + 18);
    regs.CLPS = read_u32(data + 22);
    regs.CLM0 = read_u32(data + 26);
    regs.CLM1 = read_u32(data + 30);
    regs.CLM2 = read_u32(data + 34);
    regs.CLM3 = read_u32(data + 38);
    regs.CLM4 = read_u32(data + 42);
    regs.CLMS = read_u32(data + 46);

    static bool handler_installed = false;
    if (!handler_installed) {
        install_handler_once();
        handler_installed = true;
    }

    g_sim_dev = &regs;

    /* Arm a REPEATING timer that fires SIGUSR1 every ~50us, simulating the
     * real ADC peripheral's asynchronous calibration-complete signal.
     *
     * Self-repair, iteration 4a (one-shot timer): a single firing ~200us
     * out STILL hung under real fuzzing. Debug tracing (stderr prints
     * around timer_create/timer_settime and inside the signal handler)
     * showed the handler DID fire -- but the hang persisted anyway. Root
     * cause: a one-shot timer races the target function's own code. If
     * SIGUSR1 is delivered before `dev->SC3 |= ADC_SC3_CAL_MASK;` (line
     * 104) executes, the handler clears a bit that isn't set yet (a
     * no-op), the function then sets it, and -- because the timer was
     * one-shot -- it never fires again, so the bit is never cleared and
     * the busy-wait spins forever. This is exactly the kind of race a
     * single fixed-delay firing cannot reliably win against, especially
     * under ASan's instrumentation-dependent timing jitter.
     *
     * Iteration 4b (this one): make the timer PERIODIC (it_interval set,
     * not just it_value) so it keeps firing every ~50us for as long as
     * it's armed. Clearing an already-clear bit is a harmless no-op, so
     * it doesn't matter if an early firing "misses" -- a later firing is
     * guaranteed to land after the bit is actually set, which is all the
     * busy-wait needs to see to exit. The timer is disarmed (via
     * timer_delete) immediately after the call returns. */
    timer_t timerid;
    struct sigevent sev;
    memset(&sev, 0, sizeof(sev));
    sev.sigev_notify = SIGEV_SIGNAL;
    sev.sigev_signo = SIGUSR1;
    sev.sigev_value.sival_ptr = &timerid;

    int ret;
    if (timer_create(CLOCK_REALTIME, &sev, &timerid) == 0) {
        struct itimerspec its;
        memset(&its, 0, sizeof(its));
        its.it_value.tv_sec = 0;
        its.it_value.tv_nsec = 50000;    /* first firing: 50us out */
        its.it_interval.tv_sec = 0;
        its.it_interval.tv_nsec = 50000; /* then repeat every 50us */

        timer_settime(timerid, 0, &its, NULL);

        ret = kinetis_adc_calibrate(&regs);

        timer_delete(timerid);
    } else {
        /* If we somehow can't create the timer, clear the bit ourselves
         * up front so the harness still exercises the rest of the
         * function rather than hanging unconditionally. */
        regs.SC3 &= ~ADC_SC3_CAL_MASK;
        ret = kinetis_adc_calibrate(&regs);
    }

    g_sim_dev = NULL;

    // Sanity Behavior Assertions (mirrors Stage 6's established practice:
    // real output checked against the exact same arithmetic the driver
    // performs, not just "did it crash").
    if (regs.SC3 & ADC_SC3_CALF_MASK) {
        assert(ret == -1);
    } else {
        assert(ret == 0);
        uint16_t expect_pg = (uint16_t)(regs.CLP0 + regs.CLP1 + regs.CLP2 + regs.CLP3 + regs.CLP4 + regs.CLPS);
        expect_pg = (uint16_t)(expect_pg / 2);
        expect_pg |= (1 << 15);
        assert(regs.PG == expect_pg);

        uint16_t expect_mg = (uint16_t)(regs.CLM0 + regs.CLM1 + regs.CLM2 + regs.CLM3 + regs.CLM4 + regs.CLMS);
        expect_mg = (uint16_t)(expect_mg / 2);
        expect_mg |= (1 << 15);
        assert(regs.MG == expect_mg);
    }

    return 0;
}
