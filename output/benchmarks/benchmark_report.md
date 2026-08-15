# AeroHarness Empirical Benchmark Evaluation Report

## 1. Summary Comparison
| Metric | AeroHarness (Closed-Loop) | Single-Shot LLM (Baseline) | Improvement |
| :--- | :---: | :---: | :---: |
| **Harness Success Rate (HSR)** | **0.0%** | 0.0% | +0.0% |
| **Avg. Iterations to Converge** | **0.0** | N/A (1-shot) | $\le 3.5$ Convergence |
| **Avg. Branch Coverage** | **0.0%** | 0.0% | +0.0% |
| **Vulnerabilities Discovered** | **0** | 0 | +0 |
| **Unique Crash Signatures** | **0** | 0 | - |

## 2. Detailed Target-by-Target Results
| Target Name | Target API | Compiled | Smoke Passed | Iterations | Branch Cov | Crash Detected |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| ToyFirmware-FrameParser | `protocol_process_frame` | FAIL | FAIL | 5 | 0.0% | No |
| ToyFirmware-Init | `protocol_init` | FAIL | FAIL | 5 | 0.0% | No |
| FreeRTOS-IP-PacketProcess | `prvProcessIPPacket` | FAIL | FAIL | 5 | 0.0% | No |
| FreeRTOS-UDP-Process | `xProcessReceivedUDPPacket` | FAIL | FAIL | 5 | 0.0% | No |
| FreeRTOS-DNS-ReplyParser | `prvParseDNSReply` | FAIL | FAIL | 5 | 0.0% | No |