"""
Key-rotating wrapper around the real HarnessSynthesizerAgent for Work Plan item 2.

Why this exists: `HarnessSynthesizerAgent.synthesize_initial_harness`/`repair_harness`
(src/synthesizer/agent.py, already real and working, NOT modified by this file) silently
catch *any* exception from the Gemini call -- including a 429 rate-limit/quota error --
and fall back to the deterministic offline template generator. That fallback behavior is
correct and deliberate for its original purpose (toy targets with no network), but for
item 2 it is actively dangerous: a quota-exhausted key would silently produce
deterministic-fallback harnesses labeled as if they were ordinary Gemini attempts, with
no error raised anywhere. Antigravity running unattended could burn through all 18
targets this way and hand back a report that LOOKS like real self-repair data but is not.

This wrapper never changes that fallback behavior inside agent.py. Instead, it inspects
the `model_used` field on every `SynthesisCandidate` a call returns -- the one place the
real/fallback distinction is already recorded -- and treats "it fell back" as this key's
failure: rotate to the next key's agent and retry the SAME call. Only if every key fails
the same call does it raise `AllKeysExhaustedError`, which the driver script must handle
explicitly (see run_item2_self_repair.py) rather than letting it propagate into
"ALL_KEYS_EXHAUSTED" being silently recorded as a normal compile/smoke-test failure.
"""
from typing import Dict, List, Optional

from src.synthesizer.agent import HarnessSynthesizerAgent, SynthesisCandidate

# The two real model names agent.py/config/settings.py actually configure. Anything else
# coming back in `model_used` (i.e. "deterministic-generator") means the live call failed.
_REAL_MODEL_NAMES = {"gemini-1.5-pro", "gemini-2.0-flash"}


class AllKeysExhaustedError(RuntimeError):
    """Raised when every configured API key failed the same call (e.g. all 4 hit their
    20-requests/day limit). The driver script must catch this per-target and record an
    honest ALL_KEYS_EXHAUSTED status -- never silently continue with fallback data."""


class RotatingHarnessSynthesizerAgent:
    """
    Duck-type-compatible with HarnessSynthesizerAgent (same two public methods,
    same signatures) so it can be passed directly as `agent=` to SelfRepairOrchestrator
    without any change to repair_loop.py. Internally holds one real
    HarnessSynthesizerAgent per API key and rotates on fallback detection.
    """

    def __init__(self, api_keys: List[str], model_name: str, fallback_model: str):
        if not api_keys:
            raise ValueError("RotatingHarnessSynthesizerAgent needs at least one API key")
        self._model_name = model_name
        self._fallback_model = fallback_model
        self._agents: List[HarnessSynthesizerAgent] = [
            HarnessSynthesizerAgent(api_key=k, model_name=model_name, fallback_model=fallback_model)
            for k in api_keys
        ]
        self._current = 0
        # Per-key call counters, for the structured report -- lets us see exactly how
        # much of each key's daily quota this run actually consumed.
        self.calls_per_key: Dict[int, int] = {i: 0 for i in range(len(self._agents))}

    def _rotate(self) -> bool:
        """Advances to the next key. Returns False if we've wrapped back to where we
        started (every key already tried and failed for this call)."""
        self._current = (self._current + 1) % len(self._agents)
        return self._current != 0

    def synthesize_initial_harness(self, **kwargs) -> SynthesisCandidate:
        return self._call_with_rotation("synthesize_initial_harness", **kwargs)

    def repair_harness(self, **kwargs) -> SynthesisCandidate:
        return self._call_with_rotation("repair_harness", **kwargs)

    def _call_with_rotation(self, method_name: str, **kwargs) -> SynthesisCandidate:
        attempts = 0
        tried_keys = []

        # repair_harness mutates its input `candidate` in place (increments
        # `.iteration`, and on the fallback path overwrites `.code`) BEFORE we can tell
        # whether this key's call actually reached Gemini. If we rotate to the next key
        # and retry without undoing that, the iteration count -- the exact statistic
        # item 2 exists to measure -- would be inflated by one per failed key, not just
        # by genuine repair rounds. Snapshot and restore across rotation attempts.
        snapshot_iteration: Optional[int] = None
        snapshot_code: Optional[str] = None
        if method_name == "repair_harness" and "candidate" in kwargs:
            snapshot_iteration = kwargs["candidate"].iteration
            snapshot_code = kwargs["candidate"].code

        while attempts < len(self._agents):
            if snapshot_iteration is not None:
                kwargs["candidate"].iteration = snapshot_iteration
                kwargs["candidate"].code = snapshot_code

            agent = self._agents[self._current]
            method = getattr(agent, method_name)
            self.calls_per_key[self._current] += 1
            tried_keys.append(self._current)
            candidate = method(**kwargs)
            if candidate.model_used in _REAL_MODEL_NAMES:
                return candidate
            # Fell back -- this key failed (quota, 429, or any other API error the real
            # agent swallowed). Try the next key for the SAME call.
            attempts += 1
            if attempts < len(self._agents):
                self._rotate()
        raise AllKeysExhaustedError(
            f"{method_name} fell back to the deterministic generator on every configured "
            f"key (tried key indices {tried_keys}); all keys are exhausted or failing."
        )
