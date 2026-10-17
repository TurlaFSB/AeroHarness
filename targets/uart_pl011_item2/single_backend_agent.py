"""
Single-backend wrapper around the real HarnessSynthesizerAgent for Work Plan item 2,
used when the model is reached through OpenRouter (e.g. DeepSeek V4.1 Flash) instead of
a rotating pool of Gemini keys.

Same reason as rotating_agent.py: HarnessSynthesizerAgent silently falls back to its
deterministic template generator when an LLM call fails (HTTP error, budget guard, empty
reply). For item 2 that would produce harnesses that look like model output but are not.
This wrapper inspects `candidate.model_used` after every call -- the one place the
real/fallback distinction is recorded -- and raises BackendFailedError if the call did
not come from the requested model, so the driver records an honest BACKEND_FAILED status
instead of fabricated self-repair data.

Duck-type compatible with HarnessSynthesizerAgent (same public methods, plus the private
`_apply_deterministic_fix` that SelfRepairOrchestrator calls directly), so it can be
passed as `agent=` to SelfRepairOrchestrator unchanged.
"""
import os
from typing import Optional

from src.synthesizer.agent import HarnessSynthesizerAgent, SynthesisCandidate


class BackendFailedError(RuntimeError):
    """The LLM backend failed on a call (the real agent fell back to its deterministic
    generator). The driver must record BACKEND_FAILED and stop, never continue with
    fallback data."""


class SingleBackendHarnessSynthesizerAgent:
    def __init__(self, model_name: str, openrouter_api_key: str, max_output_tokens: int = 4096):
        if not openrouter_api_key:
            raise ValueError("SingleBackendHarnessSynthesizerAgent needs an OpenRouter API key")
        self.model_name = model_name
        self._agent = HarnessSynthesizerAgent(
            api_key=None,
            model_name=model_name,
            fallback_model=None,      # no second model: a failure must surface, not be masked
            enable_cache=False,       # every attempt is a real, fresh call
            max_output_tokens=max_output_tokens,
            openrouter_api_key=openrouter_api_key,
            openrouter_model=model_name,
            openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            enable_opencode=False,
        )
        # Never route through Gemini even if GEMINI_API_KEY happens to be in the env.
        self._agent.client = None
        self.calls = 0

    @property
    def last_error(self) -> Optional[str]:
        return self._agent.last_error

    def _checked(self, candidate: SynthesisCandidate, method_name: str) -> SynthesisCandidate:
        self.calls += 1
        if candidate.model_used != self.model_name:
            raise BackendFailedError(
                f"{method_name} did not come from {self.model_name} "
                f"(model_used={candidate.model_used!r}); last_error: {self._agent.last_error}"
            )
        return candidate

    def synthesize_initial_harness(self, **kwargs) -> SynthesisCandidate:
        return self._checked(self._agent.synthesize_initial_harness(**kwargs), "synthesize_initial_harness")

    def repair_harness(self, **kwargs) -> SynthesisCandidate:
        return self._checked(self._agent.repair_harness(**kwargs), "repair_harness")

    def improve_coverage(self, **kwargs) -> SynthesisCandidate:
        return self._checked(self._agent.improve_coverage(**kwargs), "improve_coverage")

    def _apply_deterministic_fix(self, code: str, error_message: str) -> str:
        return self._agent._apply_deterministic_fix(code, error_message)
