# AeroHarness

**Autonomous Embedded-Target Reasoning and Oracle-Guided Harness Synthesis**  
*Feedback-Driven Agentic Synthesis of Fuzz Drivers for Memory-Safety Bug Hunting in Embedded Firmware*

---

## Architecture Overview

AeroHarness is an autonomous, closed-loop Cyber Reasoning System (CRS) designed to automate the entire lifecycle of fuzz harness engineering for embedded C/C++ firmware (FreeRTOS, Zephyr, NuttX):

1. **Semantic AST & Call-Graph Mining**: Parses C ASTs, type definitions, struct packing, and call paths to identify security-critical APIs reaching dangerous memory sinks (`memcpy`, pointer arithmetic).
2. **Hardware MMIO & RTOS Virtualization**: Automatically stubs hardware peripheral registers (`sys_read32`, `hw_read_reg32`) and RTOS primitives (`vTaskDelay`, `xQueueReceive`) so firmware can execute on host $x86\_64$ servers without physical devices.
3. **Agentic Synthesis with Gemini Pro**: Generates `libFuzzer` / `AFL++` entrypoints (`LLVMFuzzerTestOneInput`) utilizing `FuzzedDataProvider` to partition structured inputs.
4. **Deterministic Multi-Turn Self-Repair Oracle**: Captures Clang compiler diagnostics and dynamic sanitizer (AddressSanitizer/UBSan) crash traces, iteratively guiding Gemini Pro to fix syntax and state initialization errors autonomously.
5. **Campaign Execution & PoV Triaging**: Runs high-throughput fuzzing campaigns, deduplicates crashes, minimizes faulting inputs, and synthesizes standalone, reproducible **Proof-of-Vulnerability (`PoV.c`)** artifacts.

---

## Directory Structure

```text
D:\aeroharness/
├── config/
│   ├── __init__.py
│   └── settings.py              # LLM models, compiler paths, timeouts, sanitizer flags
├── targets/                      # Embedded firmware target codebases
│   ├── toy_firmware/            # Embedded IoT target with MMIO and memory bug
│   │   ├── protocol_parser.h
│   │   └── protocol_parser.c
│   └── freertos_tcp/            # Real-world FreeRTOS targets
├── src/
│   ├── analyzer/
│   │   ├── c_ast_extractor.py   # AST parsing, type & struct extraction
│   │   └── call_graph.py        # Call-graph & risky sink ranking
│   ├── synthesizer/
│   │   ├── agent.py             # Gemini Pro integration via google-genai
│   │   ├── prompts.py           # Domain-specific prompt templates
│   │   └── mmio_stubber.py      # Hardware MMIO register & RTOS stubber
│   ├── oracle/
│   │   ├── compiler_oracle.py   # Clang invocation & diagnostic parser
│   │   ├── smoke_test.py        # Dynamic dry-run validator
│   │   └── repair_loop.py       # Closed-loop multi-turn self-repair engine
│   ├── fuzzer/
│   │   ├── runner.py            # libFuzzer execution manager
│   │   ├── coverage.py          # Branch coverage parser
│   │   └── triager.py           # ASan crash triage & PoV artifact generator
│   └── cli/
│       └── console.py           # Rich terminal dashboard
├── tests/                       # Automated test suite
├── output/                      # Synthesized harnesses, logs, and PoVs
├── requirements.txt             # Python dependencies
├── run.py                       # Main CLI entrypoint
└── README.md
```

---

## Quick Start Guide

### 1. Installation
Install the Python dependencies:
```bash
pip install -r requirements.txt
```

### 2. Configure Gemini Pro API Key
Set your Gemini API key:
```bash
# Windows PowerShell
$env:GEMINI_API_KEY="your_api_key_here"

# Linux / WSL
export GEMINI_API_KEY="your_api_key_here"
```

### 3. Run AST Analysis & API Risk Ranking
Scan a target C header and implementation to extract types, MMIO registers, and rank functions by vulnerability risk:
```bash
python run.py analyze --header targets/toy_firmware/protocol_parser.h --source targets/toy_firmware/protocol_parser.c
```

### 4. Synthesize & Autonomously Repair a Fuzz Harness
Generate a verified `libFuzzer` driver for a target API:
```bash
python run.py synthesize --header targets/toy_firmware/protocol_parser.h --source targets/toy_firmware/protocol_parser.c --api protocol_process_frame
```

### 5. Launch Full End-to-End Campaign
Run AST mining, agentic synthesis, self-repair oracle, fuzzing campaign, and reproducible PoV generation in one command:
```bash
python run.py run-all --header targets/toy_firmware/protocol_parser.h --source targets/toy_firmware/protocol_parser.c --api protocol_process_frame --duration 20
```

---

## Running the Automated Test Suite
```bash
python -m pytest tests/ -v
```
All 7 unit tests validate AST extraction, call-graph risk scoring, prompt generation, MMIO stubbing, harness generation, and ASan crash triage.

---

## Reproducible PoV Artifacts

When a memory corruption flaw (CWE-119, CWE-416, CWE-787) is detected, AeroHarness automatically creates a standalone reproducer in `output/`:

```bash
# Compiling and verifying an auto-generated PoV
clang -fsanitize=address,undefined -g -O1 -Itargets/toy_firmware output/PoV_protocol_process_frame_heap-buffer-overflow.c targets/toy_firmware/protocol_parser.c -o pov_bin
./pov_bin
```
