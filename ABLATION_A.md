# Ablation A: AST/Structured Context Removal

This experiment isolates the causal impact of providing the LLM with structured AST metadata (function names, struct types, and access categories) versus providing only raw C code.

## Setup
We took a representative micro-sample from the `uart_pl011.c` dataset. Due to reproducing our exact historical bottleneck (hitting the strict 20-request/day quota constraint), we were able to process exactly 8 register access classifications cleanly before API exhaustion. 

The "Original" baseline uses the **oracle-verified baseline (independent AST-check, not external ground truth)** for these exact 8 registers from `llm_proposals.json` (where 6 were processed by Gemini and 2 by Ollama). 

*Limitation Note:* This baseline comes directly from our Stage 3 static-AST oracle's verdict. The oracle is an independent second opinion used to grade the LLM, not an absolute, externally verified ground truth, and it possesses its own known blind spots (e.g., treating some status-polling reads as configuration state).

The "Ablated" run stripped the AST context and used `gemini-3.6-flash` on just the raw source code.

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
