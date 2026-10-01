"""
Unit tests for AeroHarness AST Extractor and Call Graph Builder
"""
from pathlib import Path
from src.analyzer.c_ast_extractor import CASTExtractor
from src.analyzer.call_graph import CallGraphBuilder


def test_header_extraction():
    target_header = Path("D:/aeroharness/targets/toy_firmware/protocol_parser.h")
    extractor = CASTExtractor()
    context = extractor.extract_from_header(target_header)

    assert len(context.functions) >= 3
    func_names = [f.name for f in context.functions]
    assert "protocol_init" in func_names
    assert "protocol_process_frame" in func_names

    # Verify MMIO register detection
    assert len(context.mmio_registers) >= 2
    mmio_names = [r.name for r in context.mmio_registers]
    assert "MMIO_HW_STATUS_REG" in mmio_names

    # Verify magic constants
    assert "PROTOCOL_MAGIC_BYTE_1" in context.magic_constants

    # Verify struct extraction
    struct_names = [s.name for s in context.structs]
    assert "protocol_context_t" in struct_names
    assert "protocol_header_t" in struct_names


def test_call_graph_and_risk_scoring():
    target_header = Path("D:/aeroharness/targets/toy_firmware/protocol_parser.h")
    target_c = Path("D:/aeroharness/targets/toy_firmware/protocol_parser.c")

    extractor = CASTExtractor()
    context = extractor.extract_from_header(target_header)
    known_apis = [f.name for f in context.functions]

    cg_builder = CallGraphBuilder()
    risk_scores = cg_builder.analyze_source_file(target_c, known_apis)

    assert "protocol_process_frame" in risk_scores
    proc_score = risk_scores["protocol_process_frame"]

    # protocol_process_frame has multiple memcpy operations and branching
    assert proc_score.risk_score > 5.0
    assert len(proc_score.memory_operations) >= 2
