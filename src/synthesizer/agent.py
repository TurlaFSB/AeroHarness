"""
Gemini Pro Harness Synthesizer Agent for AeroHarness
Generates C++ libFuzzer harnesses and handles multi-turn self-repair conversations.
"""
import os
import re
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
    """Agent that calls Gemini Pro to synthesize and repair fuzz harnesses."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gemini-1.5-pro",
        fallback_model: str = "gemini-2.0-flash"
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model_name
        # NOTE (Oct 2 2026): `fallback_model` used to be accepted and stored here but
        # never actually used anywhere else in the class -- the only "fallback" that
        # happened on any API exception was the deterministic offline generator, not a
        # second attempt against a different Gemini model. That was left unfixed at
        # first because there was no second distinct Gemini model confirmed to work (see
        # config/settings.py's history). Now there is: a live diagnostic
        # (targets/uart_pl011_item2/diagnose_model.py) confirmed gemini-3.8-flash AND
        # gemini-3.7-flash both return real SUCCESS responses. `_generate_content` below
        # now genuinely tries `model_name` first and `fallback_model` second (only when
        # they differ) before giving up to the deterministic generator -- real model
        # diversity, not dead config.
        self.fallback_model = fallback_model
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

    def _init_client(self):
        """Initializes the Google GenAI client if an API key is present."""
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                self.client = None
                self.last_error = f"client init failed: {e!r}"

    def _generate_content(self, prompt: str, system_prompt: str, temperature: float, context: str):
        """Tries `self.model_name` first, then `self.fallback_model` (only if it's a
        different string) on any exception from the primary. Returns (response_text,
        model_used) on success, or (None, None) if every attempt failed -- in which case
        self.last_error holds the LAST failure's text (the most recent attempt is the
        most informative one for a caller deciding what to report). Added Oct 2 2026 once
        a second real working model (gemini-3.7-flash, alongside gemini-3.8-flash) was
        confirmed live -- see the __init__ note on fallback_model."""
        models_to_try = [self.model_name]
        if self.fallback_model and self.fallback_model != self.model_name:
            models_to_try.append(self.fallback_model)

        for model in models_to_try:
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config={
                        "system_instruction": system_prompt,
                        "temperature": temperature
                    }
                )
                return response.text, model
            except Exception as e:
                self.last_error = f"{context} ({model}): {e!r}"
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
        if target_api.context_struct:
            lines.extend([
                f'    {target_api.context_struct} ctx;',
                '    memset(&ctx, 0, sizeof(ctx));\n'
            ])

        # Prepare invocation
        args = []
        for param in target_api.parameters:
            if param.is_struct and param.is_pointer:
                if target_api.context_struct:
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
        """Applies targeted heuristics for offline auto-repair."""
        fixed = code
        if "fuzzer/FuzzedDataProvider.h" not in fixed:
            fixed = "#include <fuzzer/FuzzedDataProvider.h>\n" + fixed
        if "string.h" not in fixed:
            fixed = "#include <string.h>\n" + fixed
        return fixed
