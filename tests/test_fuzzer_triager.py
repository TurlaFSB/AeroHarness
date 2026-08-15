"""
Unit tests for Crash Triager and PoV Generator
"""
from pathlib import Path
from src.fuzzer.triager import CrashTriager, CrashReport


def test_asan_crash_log_parsing():
    sample_asan_log = """
=================================================================
==12345==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x602000000050 at pc 0x0000004a1234 bp 0x7ffd123456 sp 0x7ffd123448
WRITE of size 32 at 0x602000000050 thread T0
    #0 0x4a1234 in protocol_process_frame /targets/toy_firmware/protocol_parser.c:85:21
    #1 0x4a2100 in LLVMFuzzerTestOneInput /output/fuzz_protocol_process_frame.cpp:35:5
=================================================================
"""
    triager = CrashTriager()
    report = triager.parse_asan_log(sample_asan_log)

    assert report is not None
    assert report.crash_type == "heap-buffer-overflow"
    assert "CWE-122" in report.cwe_id
    assert report.access_type == "WRITE"
    assert report.access_size == 32
    assert len(report.stack_trace) == 2
    assert report.stack_trace[0].function_name == "protocol_process_frame"


def test_reproducible_pov_generation(tmp_path):
    triager = CrashTriager()
    sample_report = CrashReport(
        crash_type="heap-buffer-overflow",
        cwe_id="CWE-122 (Heap-based Buffer Overflow)",
        access_type="WRITE",
        access_size=32,
        crash_payload_bytes=b"\xA5\x5A\x04\x00\x10\x00\xAA\x20" + b"\x41" * 32
    )

    pov = triager.generate_reproducible_pov(
        crash_report=sample_report,
        target_api_name="protocol_process_frame",
        header_filename="protocol_parser.h",
        output_dir=Path("D:/aeroharness/output")
    )

    assert pov.file_path is not None
    assert Path(pov.file_path).exists()
    assert "AeroHarness Proof-of-Vulnerability" in pov.c_source_code
    assert "g_crash_payload" in pov.c_source_code
