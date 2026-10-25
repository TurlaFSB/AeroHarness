"""
OpenRouter Synthesizer Agent for Crazyflie radiolinkSyslinkDispatch.
Pinned strictly to CoreWeave (provider: {"order": ["CoreWeave"], "allow_fallbacks": false}),
using deepseek/deepseek-v4.1-flash-20260910 with 12-attempt exponential backoff.
Duck-type compatible with HarnessSynthesizerAgent for SelfRepairOrchestrator.
"""
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from src.analyzer.c_ast_extractor import ExtractedHeaderContext, FunctionSignature
from src.analyzer.call_graph import APIRiskScore
from src.synthesizer.agent import SynthesisCandidate
from src.synthesizer.prompts import PromptFactory

PINNED_PROVIDER = "CoreWeave"
REQUIRED_MODEL = "deepseek/deepseek-v4.1-flash-20260910"
SPEND_CAP_USD = 0.50
BACKOFF_DELAYS = [2, 4, 8, 16, 32, 60, 60, 60, 60, 60, 60]


def load_openrouter_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY")
    if key:
        return key

    key_file = Path("/home/pranav_verma/.openrouter_key")
    if key_file.exists():
        for line in key_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    env_file = Path("/mnt/d/aeroharness/.env")
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("OPENROUTER_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    raise RuntimeError("OPENROUTER_API_KEY not found in environment, /home/pranav_verma/.openrouter_key, or .env")


class OpenRouterHarnessSynthesizerAgent:
    """
    Duck-type compatible with HarnessSynthesizerAgent for SelfRepairOrchestrator.
    Routes all queries through OpenRouter pinned exclusively to CoreWeave.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = REQUIRED_MODEL,
        fallback_model: Optional[str] = None,
        ledger_path: Optional[Path] = None,
    ):
        self.api_key = api_key or load_openrouter_key()
        self.model_name = model_name or REQUIRED_MODEL
        self.fallback_model = fallback_model
        self.ledger_path = ledger_path

        self.total_cost_usd: float = 0.0
        self.total_calls: int = 0
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0
        self.calls: int = 0  # Compatibility counter for driver records

        self.url = "https://openrouter.ai/api/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/TurlaFSB/AeroHarness",
            "X-Title": "AeroHarness",
        }

    def _extract_code(self, response_text: str) -> str:
        """Extracts clean C++ code from markdown code blocks."""
        pattern = re.compile(r'```(?:cpp|c|c\+\+)?\s*(.*?)\s*```', re.DOTALL)
        match = pattern.search(response_text)
        if match:
            return match.group(1).strip()
        return response_text.strip()

    def _post_openrouter(
        self,
        messages: List[Dict[str, str]],
        context_label: str
    ) -> Tuple[str, str, float]:
        """
        Executes an HTTP POST to OpenRouter with CoreWeave pinned and fallbacks disabled.
        Implements 12-attempt backoff on HTTP 429 / transient errors.
        """
        if self.total_cost_usd >= SPEND_CAP_USD:
            raise RuntimeError(f"SPEND_CAP_EXCEEDED: ${self.total_cost_usd:.5f} >= ${SPEND_CAP_USD:.2f}")

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.0,
            "seed": 42,
            "max_tokens": 8192,
            "provider": {"order": [PINNED_PROVIDER], "allow_fallbacks": False},
            "usage": {"include": True},
        }

        last_error = None
        last_status = None

        for attempt in range(len(BACKOFF_DELAYS) + 1):
            t0 = time.perf_counter()
            call_time = time.strftime("%Y-%m-%dT%H:%M:%S")
            try:
                resp = httpx.post(self.url, headers=self.headers, json=payload, timeout=60.0)
                latency = time.perf_counter() - t0
                last_status = resp.status_code

                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if not choices:
                        raise ValueError(f"Empty choices in response: {resp.text}")

                    content = (choices[0]["message"].get("content") or "").strip()
                    finish_reason = choices[0].get("finish_reason")
                    usage = data.get("usage", {})
                    p_tokens = usage.get("prompt_tokens", 0)
                    c_tokens = usage.get("completion_tokens", 0)
                    t_tokens = usage.get("total_tokens", p_tokens + c_tokens)
                    cost = float(usage.get("cost", 0.0))

                    self.total_cost_usd += cost
                    self.total_calls += 1
                    self.calls += 1
                    self.total_prompt_tokens += p_tokens
                    self.total_completion_tokens += c_tokens

                    served_model = data.get("model", "")
                    provider = data.get("provider", "")

                    if provider and provider != PINNED_PROVIDER:
                        raise RuntimeError(f"Provider violation: expected {PINNED_PROVIDER}, got {provider}")

                    # Append to ledger if configured
                    if self.ledger_path:
                        entry = {
                            "time": call_time,
                            "context": context_label,
                            "requested_model": self.model_name,
                            "served_model": served_model,
                            "provider": provider,
                            "http_status": resp.status_code,
                            "retry_number": attempt,
                            "prompt_tokens": p_tokens,
                            "completion_tokens": c_tokens,
                            "total_tokens": t_tokens,
                            "finish_reason": finish_reason,
                            "cost_usd": cost,
                            "spent_total_usd": round(self.total_cost_usd, 6),
                            "latency_sec": round(latency, 3),
                        }
                        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(self.ledger_path, "a", encoding="utf-8") as lf:
                            lf.write(json.dumps(entry) + "\n")

                    return content, served_model, cost

                elif resp.status_code in (429, 500, 502, 503, 504):
                    if attempt < len(BACKOFF_DELAYS):
                        delay = BACKOFF_DELAYS[attempt]
                        print(f"[{context_label}] HTTP {resp.status_code} on attempt {attempt+1}. Backing off {delay}s...", flush=True)
                        time.sleep(delay)
                        continue
                    else:
                        last_error = f"HTTP {resp.status_code}: {resp.text}"
                else:
                    raise RuntimeError(f"OpenRouter returned unhandled HTTP {resp.status_code}: {resp.text}")

            except httpx.RequestError as e:
                last_error = str(e)
                if attempt < len(BACKOFF_DELAYS):
                    delay = BACKOFF_DELAYS[attempt]
                    print(f"[{context_label}] RequestError '{e}' on attempt {attempt+1}. Backing off {delay}s...", flush=True)
                    time.sleep(delay)
                    continue

        raise RuntimeError(f"OpenRouter call failed after 12 attempts: last_status={last_status}, last_error={last_error}")

    def synthesize_initial_harness(
        self,
        header_context: ExtractedHeaderContext,
        target_api: FunctionSignature,
        risk_score: Optional[APIRiskScore],
        header_filename: str,
        externally_linked: bool = False,
        mmio_convention_note: Optional[str] = None,
    ) -> SynthesisCandidate:
        """Synthesizes the initial libFuzzer harness via OpenRouter."""
        prompt = PromptFactory.build_synthesis_prompt(
            header_context=header_context,
            target_api=target_api,
            risk_score=risk_score,
            header_filename=header_filename,
            externally_linked=externally_linked,
            mmio_convention_note=mmio_convention_note,
        )
        system_prompt = PromptFactory.get_system_prompt()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        content, served_model, cost = self._post_openrouter(
            messages=messages,
            context_label=f"{target_api.name}::synthesize_initial",
        )
        code = self._extract_code(content)

        return SynthesisCandidate(
            target_api=target_api.name,
            code=code,
            iteration=0,
            model_used=served_model or self.model_name,
            history=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": code},
            ],
        )

    def repair_harness(
        self,
        candidate: SynthesisCandidate,
        error_type: str,
        error_message: str,
        diagnostics: List[Dict[str, str]],
    ) -> SynthesisCandidate:
        """Prompts DeepSeek via OpenRouter to repair an uncompilable or crashing harness."""
        candidate.iteration += 1
        repair_prompt = PromptFactory.build_repair_prompt(
            current_code=candidate.code,
            error_type=error_type,
            error_message=error_message,
            diagnostics=diagnostics,
        )
        system_prompt = PromptFactory.get_system_prompt()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": repair_prompt},
        ]

        content, served_model, cost = self._post_openrouter(
            messages=messages,
            context_label=f"{candidate.target_api}::repair_iter_{candidate.iteration}",
        )
        fixed_code = self._extract_code(content)
        candidate.code = fixed_code
        candidate.model_used = served_model or self.model_name
        candidate.history.append({"role": "user", "content": repair_prompt})
        candidate.history.append({"role": "assistant", "content": fixed_code})

        return candidate

    def _apply_deterministic_fix(self, code: str, error_message: str) -> str:
        """Applies targeted heuristics for offline auto-repair and pre-repair cost reduction."""
        fixed = code
        err_lower = error_message.lower()

        if "fuzzer/FuzzedDataProvider.h" not in fixed and ("fuzzeddataprovider" in err_lower or "fuzzed_data" in err_lower):
            fixed = "#include <fuzzer/FuzzedDataProvider.h>\n" + fixed
        if "string.h" not in fixed and ("memset" in err_lower or "memcpy" in err_lower or "memcmp" in err_lower or "strlen" in err_lower):
            fixed = "#include <string.h>\n" + fixed
        if "stdint.h" not in fixed and ("uint8_t" in err_lower or "uint32_t" in err_lower or "uint16_t" in err_lower or "uint64_t" in err_lower):
            fixed = "#include <stdint.h>\n" + fixed
        if "errno.h" not in fixed and ("enotsup" in err_lower or "einval" in err_lower or "errno" in err_lower):
            fixed = "#include <errno.h>\n" + fixed
        if "stdlib.h" not in fixed and ("malloc" in err_lower or "free" in err_lower or "abort" in err_lower or "exit" in err_lower):
            fixed = "#include <stdlib.h>\n" + fixed
        if "stddef.h" not in fixed and ("size_t" in err_lower or "null" in err_lower):
            fixed = "#include <stddef.h>\n" + fixed

        return fixed

    def improve_coverage(self, candidate: SynthesisCandidate, **kwargs) -> SynthesisCandidate:
        """No-op coverage refinement pass."""
        return candidate
