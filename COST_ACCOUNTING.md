# Project Cost & Compute Accounting

This document compiles the API usage, compute time, and binding constraints encountered across the 7-stage AeroHarness pipeline. 

Because we relied on free-tier and local infrastructure, the project never hit a monetary cost limit ($0 total spend). However, we did hit hard API quotas, which significantly dictated our architecture (e.g., the introduction of local Ollama failovers).

## 1. Total LLM API Calls (Estimate)
Exact per-call tallies were not strictly persisted across all crash/failover logs, so these numbers are **estimates** mathematically derived from our known dataset sizes and documented stage runs:

* **Total LLM Calls:** ~950-1000 calls
* **Gemini API Calls:** ~140 calls
  * *Breakdown:* Zephyr original run (53) + Zephyr corrected-prompt run (53) + Kinetis original run before hitting quota (~21) + Kinetis stratified spot-check (13).
* **Ollama (Local) Calls:** ~850 calls
  * *Breakdown:* Kinetis original run post-failover (~409) + Kinetis v2 corrected-prompt full run (430) + scattered retry/failovers on timeouts.

## 2. Approximate Token Consumption (Estimate)
Since exact token tracking was not logged per-request, we estimate based on representative prompt and response sizes:
* **Average Prompt:** ~800 tokens (contains C struct definitions, driver source excerpts, and classification instructions).
* **Average Response:** ~50 tokens (constrained JSON object).
* **Total per classification:** ~850 tokens.

* **Estimated Gemini Token Usage:** 140 calls * 850 tokens ~ **119,000 tokens**
* **Estimated Ollama Token Usage:** 850 calls * 850 tokens ~ **722,500 tokens**
* **Total Estimated Tokens processed:** ~841,500 tokens.

## 3. Wall-Clock Compute Time
Wall-clock time varied significantly by stage. Since some scripts did not emit precise wall-clock timers, the following are compiled from explicitly logged timing outputs and commit-history bounds:
* **Stage 2 (LLM Bulk Classification):** 
  * *Ollama runs:* ~10-15 minutes for 430 Kinetis registers locally.
  * *Gemini runs:* ~1-2 minutes for 53 Zephyr registers (network bound).
* **Stage 6 (libFuzzer Harnesses):** ~60 seconds of fuzzing time per target function (as manually capped by `-max_total_time=60`), achieving 100% saturation in <1 second.
* **Stage 7 (RL Optimization):** Explicitly logged in `stage7_rl_output.log` as completing episodes in durations of **~460 seconds** and **~12 minutes** depending on the N-size and hyperparameter configurations.

## 4. The True Binding Constraint: API Quotas
The most significant practical constraint we encountered was not monetary cost, model reasoning capability, or local compute power, but **API Quotas**.

* **Constraint Hit:** We repeatedly hit the Gemini Free-Tier Daily Quota (which enforces a strict limit of roughly **~20 requests/day** for the specific tier used).
* **Occurrences:** 
  1. Hit during the Stage 2 Kinetis bulk classification (after ~21 requests).
  2. Hit during subsequent Stage 2 re-classification attempts on later days.
* **Workarounds Implemented:**
  * **Ollama Fallback:** We explicitly engineered a local failover system to route requests to a local Ollama model (e.g., Llama 3) when Gemini rejected a request with a `429 Too Many Requests` or quota exhaustion error. This allowed the 430-register Kinetis dataset to actually complete.
  * **Waiting for Reset:** For tasks requiring Gemini's specific reasoning fidelity (such as the 13-register Kinetis Spot Check), we were forced to wait for the daily quota to reset before proceeding.

**Finding:** For automated firmware analysis pipelines operating at scale, the primary bottleneck on free-tier or budget-constrained infrastructure is raw request volume limits. Building robust local-LLM fallbacks (like our Ollama implementation) is absolutely critical to achieving high-throughput classification without incurring heavy API costs.

## 5. A Worse Failure Mode Than Quota: Network-Policy Denial With No Fallback Tier (Oct 1 2026, Kinetis ADC run)

The constraint above (Gemini's ~20 requests/day quota, worked around with Ollama) turned out not to be the worst case this project would hit. During the second-RTOS/target pipeline run on RIOT OS's Kinetis ADC driver, Gemini was unreachable for a **different and more severe reason**: `curl` to the Gemini endpoint returned `403` on the sandbox proxy's `CONNECT` tunnel, and the proxy's own status diagnostic (`/__agentproxy/status`) confirmed a policy-level relay denial for that host — not a rate limit that would reset on a schedule. On top of that, **no Ollama binary and no local model were available in that execution environment at all**, so the fallback tier this project's architecture depends on (Section 4 above) did not exist there either.

* **Cost of the workaround:** Zero additional infrastructure cost (no new API calls, no new compute), but a real **methodological** cost: Stage 2 (LLM register-classification proposals) for `kinetis_adc_calibrate`'s 18 MMIO access sites was performed directly, with the substitution explicitly disclosed (`"backend": "claude_fallback"` on every entry in `llm_proposals_kinetis_adc_calibrate.json`), rather than skipping Stage 2 or silently reusing a stale partial run.
* **Why this matters for cost/efficiency as a dimension, not just as a one-off incident:** the project's existing cost narrative (Section 4) implicitly assumes there is always *some* automated LLM tier available, with quota exhaustion as the worst case and Ollama as the universal safety net. This incident shows that assumption doesn't hold in every execution environment, and a pipeline that hardcodes "if Gemini fails, fall back to Ollama" with no further fallback has a real availability gap. A more robust design would treat "no LLM backend reachable at all" as its own first-class failure state (distinct from quota exhaustion) with an explicit, disclosed degraded mode, rather than assuming Ollama is always there to catch the fall.
* **Not counted in the token/cost estimates above:** this run consumed zero Gemini/Ollama tokens (neither was reachable), so it is invisible to Sections 1-2's accounting entirely. A future revision of this document's token estimates should note this as a run with $0 LLM cost but non-zero methodological substitution cost, rather than letting the absence of API tokens imply the stage was free or skipped.
