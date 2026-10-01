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
## Verification Note (Oct 1 2026, independent audit)

This analysis is internally consistent and correctly derived: re-running `extract_corpus_growth.py` reproduces every row and both summary statistics (23.2 average, 36 maximum) exactly from its embedded log text, and the arithmetic checks out by hand. Two things worth flagging that affect how this document should be cited, though:

1. **The underlying log is embedded as a string literal in the script, not a standalone saved log file.** Unlike this project's other fuzzing evidence (e.g. `kinetis_fuzz_logs/seed_*.log`), there's no independently-inspectable raw artifact for this specific run — just the text pasted into `extract_corpus_growth.py` itself. The embedded log's file paths (`/mnt/d/aeroharness/...`) show it was captured on the original developer's machine, not reproduced in this audit.
2. **The specific execution counts are a single sample from a run with no fixed seed, not a reproducible property of the harness.** The embedded log's own `INFO: Seed: 3232748249` line is libFuzzer's auto-generated seed when none is passed explicitly — i.e. this was one random run. Re-running `fuzz_isr` fresh twice during this audit (no `-seed` flag, matching the original's apparent methodology) produced two more sets of NEW-event execution counts, both different from each other and from the documented run:
   * Fresh run A: NEW events at #10, #17, #27, #63 (plateau `ft:17` by #63)
   * Fresh run B: NEW events at #24, #29, #32 (plateau `ft:17` by #32)
   * Documented run: NEW events at #32, #44, #59, #95 (plateau `ft:17` by #95)

   All three runs reach the same final `ft:17` coverage ceiling (consistent with `stage6_difficulty_metrics.md`), but the *path* there — and therefore the specific average/max gap figures reported above — varies substantially run to run. **The 23.2/36 figures describe one random run, not a stable average-case number.** Reporting this as "the" time-to-new-path profile for `isr` without averaging across multiple seeds would overstate precision that a single sample doesn't have. A more defensible version of this analysis would run N≥5-10 seeds (matching this project's own established multi-seed convention elsewhere) and report a mean/range across them, the same way `stage6_difficulty_metrics.md`'s fuzzing-features column and the ablation studies do.
