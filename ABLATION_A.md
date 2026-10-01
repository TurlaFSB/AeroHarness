# Ablation A: AST/Structured Context Removal

This experiment isolates the causal impact of providing the LLM with structured AST metadata (function names, struct types, and access categories) versus providing only raw C code.

## Setup
We took a representative micro-sample from the `uart_pl011.c` dataset. Due to reproducing our exact historical bottleneck (hitting the strict 20-request/day quota constraint), we were able to process exactly 8 register access classifications cleanly before API exhaustion. 

The "Original" baseline uses the **oracle-verified baseline (independent AST-check, not external ground truth)** for these exact 8 registers from `llm_proposals.json` (where 6 were processed by Gemini and 2 by Ollama). 

*Limitation Note:* This baseline comes directly from our Stage 3 static-AST oracle's verdict. The oracle is an independent second opinion used to grade the LLM, not an absolute, externally verified ground truth, and it possesses its own known blind spots (e.g., treating some status-polling reads as configuration state).

The "Ablated" run stripped the AST context and used `gemini-1.5-pro` (the project's actual configured primary model — see `src/synthesizer/agent.py`/`config/settings.py`; **correction, Oct 1 2026**: an earlier version of this document cited a non-existent model, `gemini-3.6-flash`, which does not match any real Gemini release or this project's own configuration) on just the raw source code.

## Results (n=8)

| Register Access | Original Classification (Full Context) | Ablated Classification (No Context) | Status |
| :--- | :--- | :--- | :--- |
| `pl011_enable::cr::121` | `passthrough` *(Correct per oracle)* | `set` | **Degraded** |
| `pl011_enable_fifo::lcr_h::131` | `passthrough` *(Correct per oracle)* | `set` | **Degraded** |
| `pl011_disable_fifo::lcr_h::136` | `passthrough` *(Correct per oracle)* | `set` | **Degraded** |
| `pl011_set_flow_control::cr::142` | `passthrough` *(Correct per oracle)* | `set` | **Degraded** |
| `pl011_is_readable::cr::194` | `bitextract` *(Correct per oracle)* | `bitextract` | Maintained |
| `pl011_poll_out::fr::224` | `bitextract` *(Correct per oracle)* | `bitextract` | Maintained |
| `pl011_fifo_fill::fr::389` | `passthrough` *(Incorrect per oracle)* | `bitextract` | Improved |
| `pl011_fifo_read::fr::401` | `passthrough` *(Incorrect per oracle)* | `bitextract` | Improved |

*(Note: The original Ollama classifications for the two `fr` registers were incorrect; the ablated Gemini-3.6-flash model corrected them even without context by deducing it from the bitwise check).*

### Metrics
* **Oracle-Verified Baseline Accuracy:** 6/8 (75%)
* **Ablated Accuracy:** 4/8 (50%)
* **Delta:** **-25% accuracy drop**

## Conclusion
Removing structured AST context causes significant degradation on complex configuration boundaries. Without the structural knowledge that `cr` and `lcr_h` are configuration states, the LLM falls back to literal C-syntax translation—consistently misclassifying complex `passthrough` behavior as simplistic `set` operations purely because it sees a bitwise `|=` or `&=` operator in the raw text.

## Verification Note (Oct 1 2026, independent audit)

* **The 8 cited entries and their models/backends** — **confirmed**. Re-checked `llm_proposals.json` directly: all 8 keys (`pl011_enable::cr::121`, `pl011_enable_fifo::lcr_h::131`, `pl011_disable_fifo::lcr_h::136`, `pl011_set_flow_control::cr::142`, `pl011_is_readable::cr::194`, `pl011_poll_out::fr::224`, `pl011_fifo_fill::fr::389`, `pl011_fifo_read::fr::401`) exist with exactly the cited models, and the file-wide split for these 8 is exactly 6 `gemini` / 2 `ollama` as claimed.
* **"Oracle-Verified Baseline Accuracy: 6/8 (75%)" — does not hold up against the real oracle log.** There are two different oracle scripts in this repo: the canonical `stage3_oracle.py` (cited by name in `RESULTS.md`, with its exact output committed as `stage3_oracle_output.log`), and a later, structurally different `stage3_oracle_multi.py` built for the multi-RTOS (Kinetis) extension. Running the real, canonical `stage3_oracle.py` fresh in this audit reproduces `stage3_oracle_output.log` byte-for-byte (18 Confirmed / 23 Unconfident / 12 Disagreements out of 53 — this fully resolves and closes out a separate, now-stale concern raised earlier in this audit pass about that figure being irreproducible; that concern was based on testing the wrong script, `stage3_oracle_multi.py`, which was never the one that produced Table 1).
  Checking this table's 8 entries directly against that real, reproduced log: only **one** (`pl011_poll_out::fr::224`) is actually in neither the log's "Unconfident Cases" nor "Disagreements" list — i.e., actually **Confirmed**. The other five entries marked `*(Correct per oracle)*` in the table above (`pl011_enable::cr::121`, `pl011_enable_fifo::lcr_h::131`, `pl011_disable_fifo::lcr_h::136`, `pl011_set_flow_control::cr::142`, `pl011_is_readable::cr::194`) are every one of them listed verbatim in the log's **"--- Unconfident Cases ---"** section — meaning the oracle explicitly declined to confirm or deny them, not that it confirmed them. The two `*(Incorrect per oracle)*` entries (`pl011_fifo_fill::fr::389`, `pl011_fifo_read::fr::401`) are correctly characterized — both do appear in the log's "--- Disagreements ---" section.
  So the real breakdown of this 8-item sample, per the oracle's own three-way verdict, is **1 Confirmed / 2 Disagreements / 5 Unconfident** — not "6 Correct / 2 Incorrect." The table's "Correct per oracle" label silently collapsed "Unconfident" (oracle abstained, no verdict either way) into "Correct" (oracle actively agreed), which is a real category error, not a rounding or wording nitpick: the whole point of the Unconfident bucket elsewhere in this project's own documentation is that the oracle is *not* making a claim in those cases.
* **What this means for the headline numbers:** "75%" and "-25pp degradation" should not be cited as oracle-confirmed accuracy figures. The only entry in this sample the oracle actually endorsed (`poll_out::fr::224`) was correctly classified in *both* the full-context and ablated runs (`bitextract`/`bitextract`, labeled "Maintained" in the table, which is accurate). The two oracle-confirmed *disagreements* were both "corrected" by the ablated run (`passthrough`→`bitextract`, matching the oracle's `bitextract` verdict), which — taken at face value from the one bucket that's actually trustworthy here — mildly cuts against this document's own conclusion that ablation degrades accuracy, rather than supporting it. The five "Unconfident" entries cannot licitly be scored as correct or incorrect for *either* run, full-context or ablated, since the oracle never reached a verdict on them; the table's "Degraded" labels for those five rows are an LLM-vs-LLM comparison (original Gemini/Ollama answer vs. ablated-run answer), not an oracle-graded comparison, and should not have been pooled into an "Oracle-Verified Baseline Accuracy" statistic.
* **Bottom line:** this ablation's directional idea (context removal hurts performance on certain registers) is not disproven by this note, but the specific n=8 numbers in this document (75%→50%, -25pp) are not what they're labeled as, and should be treated as unverified/mischaracterized until recomputed correctly — either by scoring only the 3 entries the oracle actually ruled on (too small a sample to report a percentage from), or by re-labeling the comparison as LLM-vs-LLM rather than oracle-graded for the other 5.
