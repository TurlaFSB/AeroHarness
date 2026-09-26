# AeroHarness: Autonomous Embedded-Target Reasoning & Fuzz Harness Synthesis

This document presents the complete system architecture for **AeroHarness**, mapping the data flow, decision boundaries, and verification loops across all seven pipeline stages. This architecture is designed to be included in an international research paper or industry whitepaper.

## System Architecture Diagram

```mermaid
flowchart TD
    classDef input fill:#e1f5fe,stroke:#01579b,stroke-width:2px,color:#000;
    classDef process fill:#f3e5f5,stroke:#4a148c,stroke-width:2px,color:#000;
    classDef llm fill:#fff3e0,stroke:#e65100,stroke-width:2px,color:#000;
    classDef oracle fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px,color:#000;
    classDef fuzzer fill:#ffebee,stroke:#b71c1c,stroke-width:2px,color:#000;
    classDef rl fill:#e0f7fa,stroke:#006064,stroke-width:2px,color:#000;
    classDef output fill:#f5f5f5,stroke:#212121,stroke-width:2px,color:#000;
    classDef future fill:#fff9c4,stroke:#fbc02d,stroke-width:2px,stroke-dasharray: 5 5,color:#000;

    %% Stage 1
    subgraph S1 [Stage 1: Semantic Analysis]
        A1[Embedded Firmware Source\n Zephyr / RIOT OS]:::input --> A2(AST Parser\n libclang):::process
        A2 --> A3[Filtered AST Nodes\n MMIO accesses, call-graphs]:::output
    end

    %% Stage 2
    subgraph S2 [Stage 2: LLM Synthesizer]
        A3 --> B1{LLM Router / Failover}:::process
        B1 -- Primary --> B2(Gemini 3.6 Flash\n Zero-Shot):::llm
        B1 -- Fallback --> B3(Qwen2.5-Coder\n via Ollama):::llm
        B2 --> B4[LLM-Proposed MMIO Models\n Constant, Passthrough, Set, etc.]:::output
        B3 --> B4
    end

    %% Stage 3 & 4
    subgraph S34 [Stage 3 & 4: Oracle Verification & Benchmarking]
        B4 --> C1(Static Verification Oracle\n AST-pattern structural checker):::oracle
        A3 --> C1
        C1 -- Agreement --> C2[Confirmed Models]:::output
        C1 -- Minor mismatch --> C3[Disagreements]:::output
        C1 -- Complex pattern --> C4[Unconfident / Uncertainty Signal]:::output
        
        C2 -. 83.3% Accuracy .-> C5[(P2IM Ground Truth\n Benchmark)]:::input
    end

    %% Stage 5
    subgraph S5 [Stage 5: Deep Learning Acceleration]
        C2 -. Dataset .-> D1(Fine-tune CodeBERT):::process
        C2 -. Dataset .-> D2(Train XGBoost):::process
        D1 -. "Underperformed\n Zero-Shot LLM" .-> D3[Result: LLM > DL]:::output
        D2 -. "Underperformed\n Zero-Shot LLM" .-> D3
    end

    %% Stage 6
    subgraph S6 [Stage 6: Harness Synthesis & Self-Repair]
        C2 --> E1(Harness Generator):::process
        E1 --> E2[libFuzzer C++ Harness]:::output
        E2 --> E3(Compiler)
        E3 -- "Compilation Error\n (Max 5 Retries)" --> E4(Diagnostic Feedback):::process
        E4 --> E1
        E3 -- "Success" --> E5[Compiled Fuzz Target ELF]:::output
    end

    %% Stage 7
    subgraph S7 [Stage 7: Uncertainty-Guided RL]
        E5 --> F1(Coverage-Guided Fuzzing\n libFuzzer):::fuzzer
        C4 -- "Reward Multiplier" --> F2(RL Scheduler\n Q-Learning, UCB1, PPO):::rl
        F2 -- "Selects Target" --> F1
        F1 -- "Coverage Signal" --> F2
        F2 --> F3[Statistically Significant\n Variance Reduction]:::output
    end
    
    %% Future Work
    subgraph S8 [What's Next: Future Trajectory]
        FW1(Dynamic Symbolic Execution\n Fuzzware Integration):::future
        FW2(Deep System-Level Fuzzing):::future
        FW3(Expanded Hardware Models\n DMA, Interrupts):::future
    end
    
    C4 -. "Runtime verification" .-> FW1
    F1 -. "Scale up" .-> FW2
    E4 -. "Complex State" .-> FW3
```

---

## Component Breakdown: How Each Step Works

### Stage 1: Semantic Analysis (AST Extraction)
* **Mechanism**: Bypasses unstable regex parsing by employing a true C/C++ compiler frontend (`libclang`). It recursively traverses the Abstract Syntax Tree (AST) of RTOS firmware (e.g., Zephyr, RIOT OS).
* **Output**: Extracts function signatures, deterministic call-graph boundaries, and locates hardware interaction nodes—specifically identifying where code interacts with volatile memory-mapped I/O (MMIO) register structs.

### Stage 2: Agentic MMIO Classification
* **Mechanism**: LLM agents are supplied with the extracted AST context and a formal taxonomy adopted from Fuzzware (Constant, Passthrough, Bitextract, Set, Identity). The agent reads the source code context to deduce how a hardware register *behaves* when read/written.
* **Engineering Standard**: Implements a high-availability fallback router. If the primary cloud endpoint (Gemini) encounters a quota or `503` error, the system automatically offloads generation to a local LLM backend (Ollama, running Qwen2.5-Coder).

### Stage 3: Static Verification Oracle
* **Mechanism**: Operates as a completely independent, deterministic checker. It uses hand-written, deterministic pattern-matching rules on the AST to independently classify the register behavior.
* **Role**: It cross-checks the LLM's proposal. If they match, the model is **Confirmed**. If the static rules cannot resolve the behavior, it outputs an **Unconfident** signal. This prevents hallucinated models from poisoning the fuzzing campaign and explicitly quantifies uncertainty.

### Stage 4: Dataset Benchmarking
* **Mechanism**: The end-to-end extraction and classification pipeline is benchmarked against the gold-standard P2IM unit-test suite.
* **Result**: Achieved an empirically verified 83.3% accuracy ceiling using Gemini, proving that LLM-based static reasoning is a highly viable alternative to expensive dynamic symbolic execution.

### Stage 5: Deep Learning Acceleration (Ablation)
* **Mechanism**: Attempted to distill the expensive LLM logic into faster, smaller models (CodeBERT and XGBoost) using the Stage 4 benchmark as training data.
* **Result**: Both models failed to significantly outperform a naive majority-class baseline due to the limited sample size (N=42). This solidified the finding that *Zero-Shot LLM inference* is currently irreplaceable for this task.

### Stage 6: Autonomous Self-Repair Loop
* **Mechanism**: The Confirmed models are injected into C++ `libFuzzer` harnesses. The system attempts to compile them natively. If compilation fails (e.g., due to missing headers or type mismatches), the `stderr` compiler diagnostic is fed *back* into the LLM context.
* **Engineering Standard**: Employs a strict "Bounded Retry" approach (max 5 retries, informed by the *QuartetFuzz* paper) to prevent infinite loops, successfully synthesizing fully operational ELF binaries.

### Stage 7: RL-Guided Fuzzer Scheduling
* **Mechanism**: Multi-target fuzzing traditionally spends equal CPU time on all entry points. AeroHarness deploys Reinforcement Learning (Q-learning, UCB1, PPO) to prioritize which harnesses to fuzz. 
* **Key Innovation**: The RL agent's reward is multiplied by the *Uncertainty Signal* generated in Stage 3. This directs the fuzzer to spend more time exploring code paths where the Oracle was unconfident, resulting in a statistically significant variance-reduction benefit (F=17.42, p<0.01) over random search.

---

## What's Next: Industry & Research Trajectory

To elevate AeroHarness from a unit-test-scale research prototype to an industry-grade, system-level vulnerability discovery framework, the following tracks define the immediate future work:

### 1. Dynamic Symbolic Execution (DSE) Handoff
* **The Gap**: Stage 3's static oracle is a lightweight approximation. It correctly identifies its own limitations (flagged as "Unconfident") but currently cannot dynamically resolve them.
* **The Solution**: Directly integrate the pipeline with Fuzzware's DSE engine. When the static Oracle flags a register as "Unconfident", the system will automatically spin up a dynamic QEMU emulator to trace the exact semantic behavior at runtime, achieving 100% ground-truth accuracy on complex states.

### 2. Deep System-Level Fuzzing Integration
* **The Gap**: Stages 6 and 7 proved viability on standalone HAL driver functions (e.g., `pl011_poll_in`). Real-world firmware bugs often require reaching deep state machines across the entire RTOS network stack or file system.
* **The Solution**: Expand the AST semantic extraction (Stage 1) to build whole-program dependency graphs, enabling the LLM to synthesize harnesses that initialize entire RTOS subsystems rather than isolated unit tests.

### 3. Continuous-State RL for Fuzzer Scheduling
* **The Gap**: The Stage 7 evaluation demonstrated that complex algorithms like PPO collapse under a strict fuzzing budget (Coupon Collector limit) when target states are discrete and shallow.
* **The Solution**: Transition the RL observation space from shallow target-selection to real-time, continuous metrics (e.g., branch-coverage velocity, memory-allocation density). This will allow advanced policies like PPO to learn deep, programmatic insights over a multi-day fuzzing campaign, breaking past the discrete mathematical limitations identified in this study.

### 4. Advanced Hardware Semantics (DMA & Interrupts)
* **The Gap**: The current taxonomy accurately models synchronous MMIO access. However, Direct Memory Access (DMA) and complex asynchronous hardware interrupts are not strictly modeled.
* **The Solution**: Extend the LLM prompting architecture and AST extraction to capture asynchronous data structures and DMA ring-buffers, allowing the fuzzer to accurately mock hardware race conditions and concurrency bugs.
