"""
Unit tests for AeroHarness Synthesizer and Prompt Factory
"""
from pathlib import Path
from src.analyzer.c_ast_extractor import CASTExtractor
from src.synthesizer.prompts import PromptFactory
from src.synthesizer.mmio_stubber import MMIOStubber
from src.synthesizer.agent import HarnessSynthesizerAgent


def test_prompt_generation():
    target_header = Path("D:/aeroharness/targets/toy_firmware/protocol_parser.h")
    extractor = CASTExtractor()
    context = extractor.extract_from_header(target_header)
    target_func = context.functions[1]

    prompt = PromptFactory.build_synthesis_prompt(
        header_context=context,
        target_api=target_func,
        risk_score=None,
        header_filename="protocol_parser.h"
    )

    assert "LLVMFuzzerTestOneInput" in PromptFactory.get_system_prompt()
    assert target_func.name in prompt
    assert "MMIO_HW_STATUS_REG" in prompt


def test_mmio_stub_generation():
    target_header = Path("D:/aeroharness/targets/toy_firmware/protocol_parser.h")
    extractor = CASTExtractor()
    context = extractor.extract_from_header(target_header)

    stubber = MMIOStubber()
    stubs = stubber.generate_mmio_stubs(context.mmio_registers)

    assert "hw_read_reg32" in stubs
    assert "MMIO_HW_STATUS_REG" in stubs


def test_harness_synthesis_deterministic():
    target_header = Path("D:/aeroharness/targets/toy_firmware/protocol_parser.h")
    extractor = CASTExtractor()
    context = extractor.extract_from_header(target_header)
    target_func = next(f for f in context.functions if f.name == "protocol_process_frame")

    agent = HarnessSynthesizerAgent(api_key=None)
    candidate = agent.synthesize_initial_harness(
        header_context=context,
        target_api=target_func,
        risk_score=None,
        header_filename="protocol_parser.h"
    )

    assert "LLVMFuzzerTestOneInput" in candidate.code
    assert "protocol_process_frame" in candidate.code
    assert "hw_read_reg32" in candidate.code
