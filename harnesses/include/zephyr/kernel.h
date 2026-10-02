#ifndef ZEPHYR_KERNEL_H_
#define ZEPHYR_KERNEL_H_

/*
 * Minimal mock of the two Zephyr kernel symbols the pl011_isr target body
 * needs (real: zephyr-src/include/zephyr/spinlock.h). Added Oct 2026 —
 * pl011_isr's body guards its irq_cb call with `K_SPINLOCK(&lock) { ... }`,
 * and neither k_spinlock_t nor K_SPINLOCK existed anywhere in the harness
 * build, so every attempt failed with "undeclared identifier"/"unknown
 * type name" before any model-written code was evaluated. This mock has
 * no real locking semantics (a single-threaded fuzzing harness doesn't
 * need any) — K_SPINLOCK(&lock) just runs its body block exactly once,
 * same control-flow shape as the real for-loop-based macro.
 */

struct k_spinlock {
	int _unused;
};
typedef struct k_spinlock k_spinlock_t;

#define K_SPINLOCK(lck) \
	for (int _k_spinlock_once = ((void)(lck), 1); _k_spinlock_once; _k_spinlock_once = 0)

#endif /* ZEPHYR_KERNEL_H_ */
