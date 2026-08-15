"""
Unit tests for Dictionary Generator and Build Database Parser
"""
from pathlib import Path
from src.analyzer.dict_generator import DictionaryGenerator
from src.analyzer.build_db import BuildDatabase


def test_dictionary_generation(tmp_path):
    gen = DictionaryGenerator()
    header_file = Path("D:/aeroharness/targets/toy_firmware/protocol_parser.h")
    c_file = Path("D:/aeroharness/targets/toy_firmware/protocol_parser.c")
    out_dict = tmp_path / "target.dict"

    fuzz_dict = gen.generate_dictionary_from_files([header_file, c_file], out_dict)

    assert out_dict.exists()
    assert len(fuzz_dict.tokens) > 0
    # Verify string literals like "PING" were captured
    dict_text = out_dict.read_text(encoding="utf-8")
    assert "PING" in dict_text or "tok_" in dict_text


def test_build_db_inference():
    db = BuildDatabase()
    project_root = Path("D:/aeroharness/targets/freertos_tcp")
    incs = db.infer_project_includes(project_root)

    inc_names = [d.name for d in incs]
    assert "include" in inc_names or "source" in inc_names
