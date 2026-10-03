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
* **Stage 7 (RL Optimization):** ~~Explicitly logged in `stage7_rl_output.log` as completing episodes in durations of **~460 seconds** and **~12 minutes** depending on the N-size and hyperparameter configurations.~~ **Correction (Oct 1 2026, independent audit): this claim is false, not just imprecise.** `stage7_rl_output.log` (91 lines, checked in full) contains zero occurrences of "460," "12 min," "seconds," "minutes," or any other timing/duration text — only the experiment configuration header and a sequence of `[PROOF] First libFuzzer invocation` lines showing the exact commands run (e.g. `./targets/target_poll_in_sbsa ... -seed=111`). There is no wall-clock timing information in this file at all. Wall-clock duration for Stage 7 is therefore genuinely unknown from the evidence in this repo, not "~460s/~12min" — that figure should be removed or re-sourced, not cited.

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

* **Cost of the workaround:** Zero additional infrastructure cost (no new API calls, no new compute), but a real **methodological** cost: Stage 2 (LLM register-classification proposals) for `kinetis_adc_calibrate`'s 18 MMIO access sites was performed by a substitute LLM pass instead of the project's configured Gemini backend, with the substitution explicitly disclosed (`"backend": "substitute_llm_manual"` on every entry in `llm_proposals_kinetis_adc_calibrate.json`), rather than skipping Stage 2 or silently reusing a stale partial run.
* **Why this matters for cost/efficiency as a dimension, not just as a one-off incident:** the project's existing cost narrative (Section 4) implicitly assumes there is always *some* automated LLM tier available, with quota exhaustion as the worst case and Ollama as the universal safety net. This incident shows that assumption doesn't hold in every execution environment, and a pipeline that hardcodes "if Gemini fails, fall back to Ollama" with no further fallback has a real availability gap. A more robust design would treat "no LLM backend reachable at all" as its own first-class failure state (distinct from quota exhaustion) with an explicit, disclosed degraded mode, rather than assuming Ollama is always there to catch the fall.
* **Not counted in the token/cost estimates above:** this run consumed zero Gemini/Ollama tokens (neither was reachable), so it is invisible to Sections 1-2's accounting entirely. A future revision of this document's token estimates should note this as a run with $0 LLM cost but non-zero methodological substitution cost, rather than letting the absence of API tokens imply the stage was free or skipped.

## 6. Verification Note (Oct 1 2026, independent audit): two call-count claims don't match the committed data files

Sections 1-2's call-count breakdown was checked against the actual proposal JSON files committed to the repo (each entry's `"backend"` field, where present, records which LLM actually produced it). Two of the cited sub-totals don't hold up; one does.

* **"Zephyr original run (53) + Zephyr corrected-prompt run (53)" = 106 Gemini calls — does not match.** Only one Zephyr proposals file exists in the repo (`llm_proposals.json`, 53 entries total — there is no second "corrected-prompt" Zephyr file). Its own `backend` field breaks down as **11 `gemini`, 28 `ollama`, 14 `none`** (skipped/not-applicable entries) — not 53 Gemini calls, and nowhere near 106. If a second corrected-prompt Zephyr run really happened, its output file isn't in this repo; if it didn't, Section 1's Gemini-call estimate for Zephyr is overstated by roughly 10x.
* **"Kinetis v2 corrected-prompt full run (430)" Ollama calls — does not match.** `llm_proposals_kinetis_v2.json` has **312 entries total**, of which **222 are `ollama`-backed** (90 are `none`/skipped) — not 430 of either.
* **"Kinetis stratified spot-check (13)" — matches.** `llm_proposals_kinetis_gemini_spotcheck.json` has 18 entries total, but exactly **13 carry `backend: "gemini"`** (the other 5 are `none`/skipped write-only registers) — so read as "13 real Gemini requests," this one is accurate.
* **"Kinetis original run post-failover (~409)" / "before hitting quota (~21)" — unverifiable either way.** `llm_proposals_kinetis.json` (223 entries) has no `backend` field on any entry at all, so there's no way to attribute these to Gemini vs. Ollama from the data itself. Not contradicted, but not confirmed either — this part of the estimate rests on nothing checkable.

**Why this matters beyond just two wrong numbers:** Section 1 already labels its totals "estimates... mathematically derived from our known dataset sizes," which is the right caveat *if* the dataset sizes themselves are right. Two of the four cited sub-totals turn out not to match the files they're supposedly derived from, which means the "known dataset sizes" input to that math wasn't actually checked against the data at the time this document was written. The corrected, file-verified picture (where a `backend` field exists to check): Zephyr — 11 Gemini + 28 Ollama (out of 53); Kinetis v2 — 222 Ollama (out of 312); Kinetis spot-check — 13 Gemini (out of 18). This doesn't change the document's qualitative conclusion (quota exhaustion was the binding constraint, Ollama fallback was necessary), but the specific totals in Sections 1-2 should be treated as unverified pending a recount from these real files, not cited as-is.
