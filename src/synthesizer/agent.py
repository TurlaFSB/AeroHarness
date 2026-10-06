"""
Gemini Pro Harness Synthesizer Agent for AeroHarness
Generates C++ libFuzzer harnesses and handles multi-turn self-repair conversations.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from src.analyzer.c_ast_extractor import ExtractedHeaderContext, FunctionSignature
from src.analyzer.call_graph import APIRiskScore
from .prompts import PromptFactory
from .mmio_stubber import MMIOStubber


class SynthesisCandidate(BaseModel):
    target_api: str
    code: str
    iteration: int = 0
    model_used: str = "gemini-1.5-pro"
    history: List[Dict[str, str]] = Field(default_factory=list)


class HarnessSynthesizerAgent:
    """Agent that calls Gemini to synthesize and repair fuzz harnesses."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-1.5-pro",
        fallback_model: str = "gemini-2.0-flash",
        enable_cache: bool = True,
        max_output_tokens: Optional[int] = 1500,
        cache_dir: Optional[Path] = None,
        openrouter_api_key: Optional[str] = None,
        openrouter_model: Optional[str] = None,
        openrouter_base_url: str = "https://openrouter.ai/api/v1",
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.openrouter_api_key = openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
        self.openrouter_model = openrouter_model or "deepseek/deepseek-chat"
        self.openrouter_base_url = openrouter_base_url
        self.model_name = model_name
        self.fallback_model = fallback_model
        self.enable_cache = enable_cache
        self.max_output_tokens = max_output_tokens
        self._cache_dir = cache_dir or (Path(__file__).resolve().parent.parent.parent / ".cache")
        self._cache_file = self._cache_dir / "llm_cache.json"
        self._cache: Dict[str, Any] = self._load_cache()
        self.client = None
        # NOTE (Oct 2 2026, Work Plan item 2): the except blocks below have always
        # silently discarded the real exception before falling back to the
        # deterministic generator -- there was no way for any caller to tell "quota
        # exhausted" apart from "model name retired" apart from "network unreachable"
        # apart from "malformed API key." This surfaced for real during item 2's
        # Antigravity run: all 4 keys fell back on their very first call each (1 call
        # per key, not ~20), which is NOT the quota-exhaustion shape at all, but with
        # no captured exception there was no way to tell what it actually was without
        # more guessing and more burned API calls. Root cause (confirmed via Google's
        # own current deprecation docs, not guessed): both `gemini-1.5-pro` and
        # `gemini-2.0-flash` are deprecated/shut down as of Oct 2026 -- a model-name
        # problem, not a key or quota problem. `last_error` now captures the real
        # exception text so this is diagnosable without external guesswork next time.
        self.last_error: Optional[str] = None
        self._init_client()

    # NOTE (Oct 2 2026): a real item-2 run stalled completely for 40+ minutes mid-target
    # with zero further log output and zero further API calls recorded, until it was
    # killed by hand. Root cause, confirmed by reading the google.genai SDK's own
    # HttpOptions.timeout field: it defaults to None -- no request timeout at all -- so a
    # stalled/hung network connection to the Gemini API blocks generate_content()
    # indefinitely, never raises an exception, and therefore never triggers any of the
    # retry/fallback/rotation logic this file and rotating_agent.py already have (all of
    # which only fire on an actual exception). A 2-minute cap is generous for a normal
    # response but far short of "indefinitely" -- a call that's really just stuck now
    # fails fast and flows into the existing retry/fallback path instead of freezing the
    # whole unattended run.
    _REQUEST_TIMEOUT_MS = 120_000

    def _init_client(self):
        """Initializes the Google GenAI client if an API key is present."""
        if self.api_key:
            try:
                from google import genai
                from google.genai import types
                self.client = genai.Client(
                    api_key=self.api_key,
                    http_options=types.HttpOptions(timeout=self._REQUEST_TIMEOUT_MS),
                )
            except Exception as e:
                self.client = None
                self.last_error = f"client init failed: {e!r}"

    # NOTE (Oct 2 2026): added after item 2's real run hit a 503 UNAVAILABLE ("high
    # demand ... usually temporary") on EVERY key for BOTH the primary and fallback
    # model, on the very first real attempt after this file's own fallback-model fix
    # landed. That report also surfaced that key rotation (RotatingHarnessSynthesizerAgent)
    # is structurally useless against this failure mode: a 503 is a model-wide backend
    # condition, not a per-key problem, so cycling through all 4 keys just burns one call
    # per key for the identical, guaranteed-to-repeat error. Retrying the SAME model a
    # couple of times with a short delay -- cheap, and explicitly licensed by Google's own
    # error text -- is a much better first response than immediately treating a transient
    # spike as a hard failure. Only retries on a real 503 (ServerError with .code == 503);
    # a 404 (bad model name) or 429 (quota) will not resolve by waiting a few seconds, so
    # those still fail fast onto the next model/key exactly as before.
    def _load_cache(self) -> Dict[str, Any]:
        """Loads cached responses from disk."""
        if not self.enable_cache:
            return {}
        try:
            if self._cache_file.exists():
                return json.loads(self._cache_file.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_cache(self) -> None:
        """Persists cached responses to disk."""
        if not self.enable_cache:
            return
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(json.dumps(self._cache, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _generate_openrouter(self, model: str, prompt: str, system_prompt: str, temperature: float) -> Optional[str]:
        """Dispatches an OpenAI-compatible request to OpenRouter (e.g. DeepSeek V3 / V4 Flash)."""
        if not self.openrouter_api_key:
            return None
        try:
            import httpx
            headers = {
                "Authorization": f"Bearer {self.openrouter_api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/TurlaFSB/AeroHarness",
                "X-Title": "AeroHarness",
            }
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": temperature,
            }
            if self.max_output_tokens:
                payload["max_tokens"] = self.max_output_tokens

            with httpx.Client(timeout=120.0) as http_client:
                resp = http_client.post(f"{self.openrouter_base_url}/chat/completions", headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            self.last_error = f"OpenRouter API call failed ({model}): {e!r}"
            return None

    def _generate_content(self, prompt: str, system_prompt: str, temperature: float, context: str):
        """Tries `self.model_name` first, then `self.fallback_model` (only if it's a
        different string), retrying a transient 503 in place a couple of times before
        moving on. Supports both Gemini and OpenRouter (e.g. DeepSeek V3/V4 Flash).
        Utilizes local disk caching and max_output_tokens to minimize API spend."""
        if self.enable_cache:
            cache_key = hashlib.sha256(f"{self.model_name}:{system_prompt}:{prompt}:{temperature}".encode("utf-8")).hexdigest()
            if cache_key in self._cache:
                cached_data = self._cache[cache_key]
                return cached_data["text"], f"{cached_data.get('model', self.model_name)} (cached)"

        models_to_try = [self.model_name]
        if self.fallback_model and self.fallback_model != self.model_name:
            models_to_try.append(self.fallback_model)

        attempt_errors: List[str] = []
        for model in models_to_try:
            # 1. OpenRouter Provider (DeepSeek / OpenRouter models)
            if model.startswith("deepseek/") or model.startswith("openrouter/") or (self.openrouter_api_key and not self.client):
                resp_text = self._generate_openrouter(model, prompt, system_prompt, temperature)
                if resp_text is not None:
                    if self.enable_cache:
                        self._cache[cache_key] = {"text": resp_text, "model": model}
                        self._save_cache()
                    return resp_text, model
                attempt_errors.append(f"{context} ({model}): {self.last_error}")
                continue

            # 2. Google Gemini Provider
            if not self.client:
                continue

            delays = [0] + self._SERVER_BUSY_RETRY_DELAYS_SEC
            for attempt_num, delay in enumerate(delays):
                if delay:
                    time.sleep(delay)
                try:
                    config_dict = {
                        "system_instruction": system_prompt,
                        "temperature": temperature
                    }
                    if self.max_output_tokens:
                        config_dict["max_output_tokens"] = self.max_output_tokens

                    response = self.client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=config_dict
                    )
                    if self.enable_cache and response.text:
                        self._cache[cache_key] = {"text": response.text, "model": model}
                        self._save_cache()
                    return response.text, model
                except Exception as e:
                    attempt_errors.append(f"{context} ({model}, attempt {attempt_num + 1}): {e!r}")
                    if getattr(e, "code", None) != 503:
                        break  # not a transient-busy error -- no point retrying this model
        self.last_error = " | ".join(attempt_errors)
        return None, None

    def synthesize_initial_harness(
        self,
        header_context: ExtractedHeaderContext,
        target_api: FunctionSignature,
        risk_score: Optional[APIRiskScore],
        header_filename: str,
        externally_linked: bool = False,
        mmio_convention_note: Optional[str] = None
    ) -> SynthesisCandidate:
        """Synthesizes the first candidate fuzz harness for a given API."""
        prompt = PromptFactory.build_synthesis_prompt(
            header_context=header_context,
            target_api=target_api,
            risk_score=risk_score,
            header_filename=header_filename,
            externally_linked=externally_linked,
            mmio_convention_note=mmio_convention_note
        )
        system_prompt = PromptFactory.get_system_prompt()

        if self.client:
            response_text, model_used = self._generate_content(
                prompt, system_prompt, temperature=0.2, context="synthesize_initial_harness"
            )
            if response_text is not None:
                raw_code = self._extract_code(response_text)
                return SynthesisCandidate(
                    target_api=target_api.name,
                    code=raw_code,
                    iteration=0,
                    model_used=model_used,
                    history=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": raw_code}
                    ]
                )

        # Offline / Deterministic Template Synthesizer Fallback
        fallback_code = self._generate_deterministic_harness(header_context, target_api, header_filename)
        return SynthesisCandidate(
            target_api=target_api.name,
            code=fallback_code,
            iteration=0,
            model_used="deterministic-generator",
            history=[]
        )

    def repair_harness(
        self,
        candidate: SynthesisCandidate,
        error_type: str,
        error_message: str,
        diagnostics: List[Dict[str, str]]
    ) -> SynthesisCandidate:
        """Prompts Gemini Pro to repair an uncompilable or crashing harness."""
        candidate.iteration += 1
        repair_prompt = PromptFactory.build_repair_prompt(
            current_code=candidate.code,
            error_type=error_type,
            error_message=error_message,
            diagnostics=diagnostics
        )

        if self.client:
            system_prompt = PromptFactory.get_system_prompt()
            response_text, model_used = self._generate_content(
                repair_prompt, system_prompt, temperature=0.1, context="repair_harness"
            )
            if response_text is not None:
                fixed_code = self._extract_code(response_text)
                candidate.code = fixed_code
                # NOTE (Oct 2 2026): candidate.model_used previously was never touched
                # here at all -- on a fallback it silently kept whatever value the
                # *initial* synthesis call had set, which would make
                # RotatingHarnessSynthesizerAgent's fallback-detection (it checks
                # candidate.model_used after every call) blind to a repair call that
                # actually fell back to the deterministic generator. Set explicitly on
                # every path now, success or fallback, so it always reflects the call
                # that just happened, not a stale earlier one.
                candidate.model_used = model_used
                candidate.history.append({"role": "user", "content": repair_prompt})
                candidate.history.append({"role": "assistant", "content": fixed_code})
                return candidate

        # Deterministic patch if offline
        candidate.code = self._apply_deterministic_fix(candidate.code, error_message)
        candidate.model_used = "deterministic-generator"
        return candidate

    def _extract_code(self, response_text: str) -> str:
        """Extracts clean C++ code from markdown code fences."""
        pattern = re.compile(r'```(?:cpp|c|c\+\+)?\s*(.*?)\s*```', re.DOTALL)
        match = pattern.search(response_text)
        if match:
            return match.group(1).strip()
        return response_text.strip()

    def _generate_deterministic_harness(
        self,
        header_context: ExtractedHeaderContext,
        target_api: FunctionSignature,
        header_filename: str
    ) -> str:
        """Generates a compilable, robust libFuzzer harness for the target."""
        stubber = MMIOStubber()
        mmio_code = stubber.generate_mmio_stubs(header_context.mmio_registers)

        lines = [
            "#include <stdint.h>",
            "#include <stddef.h>",
            "#include <string.h>",
            "#include <stdlib.h>",
            "#include <vector>",
            "#include <fuzzer/FuzzedDataProvider.h>",
            f'#include "{header_filename}"\n',
            mmio_code,
            'extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {',
            '    if (size < 4) {',
            '        return 0;',
            '    }\n'
        ]

        # NOTE (Oct 2 2026): this used to unconditionally declare one local named `ctx`
        # (only when context_struct was set) and then separately, in the arg-building
        # loop below, pass `&ctx` for EVERY struct-pointer parameter regardless of
        # whether context_struct was actually detected for that specific parameter --
        # for any target whose context-like parameter isn't literally named 'ctx',
        # 'context', 'handle', or 'self' (e.g. the extremely common embedded convention
        # `const struct device *dev`), context_struct stays None, the `ctx` declaration
        # above never executes, and the old code still emitted `&ctx`, producing a
        # guaranteed "undeclared identifier 'ctx'" compile error. It also hardcoded a
        # call to a function literally named `protocol_init`, which only exists for the
        # one toy_firmware example this fallback was originally written against -- not a
        # generic initializer for an arbitrary target. Confirmed broken directly while
        # preparing Work Plan item 2's uart_pl011.c targets (see FAILURE_TAXONOMY.md).
        # Fixed conservatively: declare `ctx` only when we can name a real match, and
        # never reference a function we have no evidence exists for this target.
        has_pl011 = any("pl011" in s.name for s in header_context.structs)
        has_device = any("device" in p.type_str for p in target_api.parameters)

        if has_device and has_pl011:
            lines.extend([
                '    struct pl011_data dev_data;',
                '    memset(&dev_data, 0, sizeof(dev_data));',
                '    struct pl011_regs dev_regs;',
                '    memset(&dev_regs, 0, sizeof(dev_regs));',
                '    mock_regs_ptr = &dev_regs;',
                '    struct device dev_obj;',
                '    memset(&dev_obj, 0, sizeof(dev_obj));',
                '    dev_obj.data = &dev_data;\n'
            ])
        elif target_api.context_struct:
            lines.extend([
                f'    {target_api.context_struct} ctx;',
                '    memset(&ctx, 0, sizeof(ctx));\n'
            ])

        # Prepare invocation
        args = []
        for param in target_api.parameters:
            if param.is_struct and param.is_pointer:
                if has_device and "device" in param.type_str and has_pl011:
                    args.append("&dev_obj")
                elif target_api.context_struct:
                    args.append("&ctx")
                else:
                    # No detected context parameter to point at -- a null pointer of
                    # the right type compiles cleanly. This will very likely crash or
                    # no-op rather than exercise real behavior; the deterministic
                    # fallback is a last-resort offline stand-in, never a substitute
                    # for a real synthesis call, and this keeps that limitation
                    # honest (a smoke-test crash) rather than masking it as a
                    # compile failure unrelated to the actual target.
                    args.append(f"({param.type_str.strip()})0")
            elif param.is_buffer_param or (param.is_pointer and "uint8" in param.type_str):
                args.append("data")
            elif param.is_size_param:
                args.append("size")
            else:
                args.append("0")

        args_str = ", ".join(args)
        lines.extend([
            f'    {target_api.name}({args_str});\n',
            '    return 0;',
            '}'
        ])

        return "\n".join(lines)

    def _apply_deterministic_fix(self, code: str, error_message: str) -> str:
        """Applies targeted heuristics for offline auto-repair and pre-repair cost reduction."""
        fixed = code
        err_lower = error_message.lower()

        # 1. Missing standard/fuzzing includes
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

        # 2. Fix redundant struct redefinitions (e.g. struct pl011_regs already provided by header)
        if "redefinition of" in err_lower and "pl011_regs" in err_lower:
            fixed = re.sub(r'struct\s+pl011_regs\s*\{[^}]*\}\s*;?', '', fixed)

        return fixed
