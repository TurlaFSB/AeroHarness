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
        self.fallback_model = fallback_model
        self.client = None
        self._init_client()

    def _init_client(self):
        """Initializes the Google GenAI client if an API key is present."""
        if self.api_key:
            try:
                from google import genai
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                self.client = None

    def synthesize_initial_harness(
        self,
        header_context: ExtractedHeaderContext,
        target_api: FunctionSignature,
        risk_score: Optional[APIRiskScore],
        header_filename: str
    ) -> SynthesisCandidate:
        """Synthesizes the first candidate fuzz harness for a given API."""
        prompt = PromptFactory.build_synthesis_prompt(
            header_context=header_context,
            target_api=target_api,
            risk_score=risk_score,
            header_filename=header_filename
        )
        system_prompt = PromptFactory.get_system_prompt()

        if self.client:
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config={
                        "system_instruction": system_prompt,
                        "temperature": 0.2
                    }
                )
                raw_code = self._extract_code(response.text)
                return SynthesisCandidate(
                    target_api=target_api.name,
                    code=raw_code,
                    iteration=0,
                    model_used=self.model_name,
                    history=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                        {"role": "assistant", "content": raw_code}
                    ]
                )
            except Exception as e:
                # Fall back to template synthesizer if network/API error
                pass

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
            try:
                system_prompt = PromptFactory.get_system_prompt()
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=repair_prompt,
                    config={
                        "system_instruction": system_prompt,
                        "temperature": 0.1
                    }
                )
                fixed_code = self._extract_code(response.text)
                candidate.code = fixed_code
                candidate.history.append({"role": "user", "content": repair_prompt})
                candidate.history.append({"role": "assistant", "content": fixed_code})
                return candidate
            except Exception:
                pass

        # Deterministic patch if offline
        candidate.code = self._apply_deterministic_fix(candidate.code, error_message)
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

        if target_api.context_struct:
            lines.extend([
                f'    {target_api.context_struct} ctx;',
                '    memset(&ctx, 0, sizeof(ctx));',
                '    protocol_init(&ctx, 0x12345678);\n'
            ])

        # Prepare invocation
        args = []
        for param in target_api.parameters:
            if param.is_struct and param.is_pointer:
                args.append("&ctx")
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
