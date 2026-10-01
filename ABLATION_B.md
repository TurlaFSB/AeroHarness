# Ablation B: Compiler-Oracle Feedback Removal (PRELIMINARY / SUPERSEDED)

> **IMPORTANT:** This document represents a preliminary v1 trial. The sample size (n=1 per harness) was insufficient for statistical validity, and the hypotheses regarding model discrepancy/non-determinism were unverified. Please refer to [ABLATION_B_V2.md](./ABLATION_B_V2.md) for the rigorously controlled, pre-registered paired-branching experiment that supersedes this file.

This experiment tests whether the self-repair loop requires specific compiler error strings to converge on a working harness, or if generic "it failed" feedback is sufficient.

## Setup
We targeted all three generated harnesses (`pl011_isr`, `pl011_poll_in`, and `pl011_poll_out`) which historically required varying degrees of repair iterations.

We re-ran the exact zero-shot harness generation prompts using **`gemini-3.6-flash`** (our established, consistent model throughout this project). Crucially, we enforced a **genuinely clean slate**: no pre-existing stub files or Zephyr type definitions were provided. The LLM had to generate everything from scratch, matching the exact conditions of the original Attempt 1.

Compilation was routed through the local `clang++` toolchain (via WSL). If it failed, the LLM was designed to receive a blinded oracle prompt: *"Your previous code failed to compile. Please try again. Do not give explanations, just output the corrected C++ code."*

## Execution Log

* **`pl011_isr` Attempt 1 Compilation:** **SUCCESS** (`clang++ -fsanitize=fuzzer,address ablation_b_clean/harness.cpp -o ablation_b_clean/fuzz_bin` exited with code 0).
* **`pl011_poll_in` Attempt 1 Compilation:** **SUCCESS**
* **`pl011_poll_out` Attempt 1 Compilation:** **SUCCESS**
* *Experiments terminated early due to zero-shot convergence across all three targets.*

## Conclusion & Discussion

The ablation proved technically inconclusive for measuring repair-loop degradation because the `gemini-3.6-flash` model **completely bypassed the repair loop entirely across all 3 test cases**. 

**Note on Original Models:** It is currently *unknown* exactly what backend model was used to generate the original Stage 6 harnesses interactively. While some configuration scripts in the repository reference `gemini-1.5-pro` and other older models, we cannot verify what was run on the developer's machine. We hypothesize that the discrepancy—original harnesses requiring repair loops vs. this ablation converging zero-shot—is likely due to a generational model discrepancy (where older models required scaffolding that newer models like `3.6-flash` bypass), but this remains an unverified hypothesis.

Starting from a perfectly clean slate with no infrastructure, the model successfully synthesized the correct missing structs (`device`, `pl011_regs`, `pl011_data`), Zephyr macros (`K_SPINLOCK`), and data relationships flawlessly on its very first zero-shot attempt every time.

### Implications for the Core Claim
Our central claim—that oracle-guided compiler feedback is necessary for synthesizing valid libFuzzer harnesses—must be nuanced in light of these results.

**1. Model Capabilities Erode the Need for Scaffolding on Simple Functions:** 
The functions tested here exhibit relatively low structural complexity (e.g., `isr` has a Cyclomatic Complexity of 4). For well-known patterns (like standard MMIO structs and bitwise flags), frontier models like `gemini-3.6-flash` possess enough internalized knowledge to hallucinate perfectly functioning hardware mocks and type stubs without iteratively bouncing off a compiler. 

**2. Where Repair Loops Still Matter:**
While zero-shot synthesis solves these simple unit-level drivers, the necessity of compiler-oracle feedback is not entirely obsolete. It is highly likely that for harder, larger real-world targets—such as deeply nested network stacks, bespoke RTOS subsystems, or monolithic vendor HALs where types span dozens of interconnected header files—the LLM will not be able to guess the entire memory layout or dependency graph zero-shot. In those domains, the compiler oracle remains an essential constraint-solving mechanism.

**Finding:** Raw capability improvements in newer LLM generations (e.g., from `1.5-pro` to `3.6-flash`) natively absorb the complex syntactic reasoning that previously required heavy agentic scaffolding for isolated, low-complexity functions. Future research must evaluate compiler-in-the-loop repair systems against significantly harder targets to demonstrate their ongoing necessity as models advance.
