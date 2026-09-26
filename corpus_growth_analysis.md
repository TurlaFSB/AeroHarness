# Corpus Growth and Time-to-New-Path Analysis

Extracted from the `fuzz_pl011_isr` coverage fuzzing session (Task 2).

## Event Log
| Execution Count | Corpus Size | Coverage Features (ft) | Gap to Previous Event (Execs) |
| :--- | :--- | :--- | :--- |
| 2 | 1 | 2 | 2 |
| 32 | 2 | 9 | 30 |
| 44 | 3 | 12 | 12 |
| 59 | 4 | 13 | 15 |
| 95 | 5 | 17 | 36 |

## Time-to-New-Path Statistics
* **Average gap between discoveries:** 23.2 executions
* **Maximum gap (longest dry spell):** 36 executions

*Limitation Note: libFuzzer does not output precise wall-clock timestamps per NEW event in standard logs. Thus, time-to-new-path is fundamentally measured in execution units rather than wall-clock seconds. Given the execution rate of ~730,000 execs/sec in this run, the maximum gap of 36 executions translates to approximately 0.05 milliseconds of wall-clock time.*