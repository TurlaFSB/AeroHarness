"""Offline tests for src/oracle/crash_triage.py. The sanitizer texts are copied from real
item-2 output (pl011_set_baudrate, convnote run); no compiler, model or network is used."""
from pathlib import Path

from src.oracle.crash_triage import (
    CrashVerdict, parse_ubsan_reports, target_side_ubsan, triage_crash,
)

D = "/mnt/d/aeroharness/targets/uart_pl011_item2"
RUN = D + "/output/openrouter_deepseek_deepseek-v4.1-flash-20260910_prov-CoreWeave_convnote/pl011_set_baudrate"
HARNESS = Path(RUN + "/fuzz_pl011_set_baudrate.cpp")
TARGETS = [Path(D + "/pl011_set_baudrate.c"), Path(D + "/pl011_set_baudrate.h")]

UBSAN_HARNESS = f"{HARNESS}:37:27: runtime error: null pointer passed as argument 2, which is declared to never be null\n"
UBSAN_TARGET = f"{D}/pl011_set_baudrate.c:28:17: runtime error: division by zero\n"
ASAN_FPE = f"""==409==ERROR: AddressSanitizer: FPE on unknown address 0x61c0da12a592 (pc 0x61c0da12a592 bp 0x7ffed6e04370 sp 0x7ffed6e04360 T0)
    #0 0x61c0da12a592 in pl011_set_baudrate(device const*, unsigned int, unsigned int) {D}/pl011_set_baudrate.c:28:17
    #1 0x61c0da127b49 in LLVMFuzzerTestOneInput {HARNESS}:83:11
    #2 0x61c0da032d34 in fuzzer::Fuzzer::ExecuteCallback(unsigned char const*, unsigned long) ({RUN}/cov_bin+0x4ed34) (BuildId: cff7bd0e)
    #3 0x61c0da04c0d6 in main ({RUN}/cov_bin+0x680d6) (BuildId: cff7bd0e)
    #4 0x79204862a1c9  (/lib/x86_64-linux-gnu/libc.so.6+0x2a1c9) (BuildId: a4a7992a)
"""


def test_ubsan_in_harness_is_harness_side():
    t = triage_crash(UBSAN_HARNESS, HARNESS, TARGETS)
    assert t.verdict == CrashVerdict.HARNESS_SIDE
    assert (t.site.line, t.site.col) == (37, 27)


def test_ubsan_in_driver_is_target_side():
    t = triage_crash(UBSAN_TARGET, HARNESS, TARGETS)
    assert t.verdict == CrashVerdict.TARGET_SIDE
    assert t.site.line == 28


def test_asan_fpe_top_frame_is_target_side_not_the_harness_caller():
    t = triage_crash(ASAN_FPE, HARNESS, TARGETS)
    assert t.verdict == CrashVerdict.TARGET_SIDE
    assert t.asan_abort and t.site.function.startswith("pl011_set_baudrate")


def test_asan_skips_runtime_frames_to_reach_harness():
    txt = f"""==1==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x1 at pc 0x2
    #0 0x1 in __asan_memcpy /build/llvm-toolchain/compiler-rt/lib/asan/asan_interceptors_memintrinsics.cpp:63:3
    #1 0x2 in LLVMFuzzerTestOneInput {HARNESS}:50:5
    #2 0x3 in main ({RUN}/b+0x1)
"""
    t = triage_crash(txt, HARNESS, TARGETS)
    assert t.verdict == CrashVerdict.HARNESS_SIDE and t.site.line == 50


def test_asan_decides_over_earlier_nonfatal_ubsan_line():
    txt = UBSAN_HARNESS + ASAN_FPE
    assert triage_crash(txt, HARNESS, TARGETS).verdict == CrashVerdict.TARGET_SIDE


def test_scaffold_side_for_mock_header():
    txt = f"{D}/common_stubs.h:12:5: runtime error: signed integer overflow\n"
    assert triage_crash(txt, HARNESS, TARGETS).verdict == CrashVerdict.SCAFFOLD_SIDE


def test_unknown_without_location():
    assert triage_crash("Segmentation fault\n", HARNESS, TARGETS).verdict == CrashVerdict.UNKNOWN
    assert triage_crash("", HARNESS, TARGETS).verdict == CrashVerdict.UNKNOWN


def test_system_header_ubsan_is_ignored():
    txt = "/usr/lib/llvm-18/lib/clang/18/include/fuzzer/FuzzedDataProvider.h:100:5: runtime error: x\n"
    assert triage_crash(txt, HARNESS, TARGETS).verdict == CrashVerdict.UNKNOWN


def test_relative_path_matches_target_tail():
    txt = "pl011_set_baudrate.c:28:17: runtime error: division by zero\n"
    assert triage_crash(txt, HARNESS, TARGETS).verdict == CrashVerdict.TARGET_SIDE


def test_same_basename_other_directory_is_not_target():
    txt = "/elsewhere/pl011_set_baudrate.c:28:17: runtime error: division by zero\n"
    assert triage_crash(txt, HARNESS, TARGETS).verdict == CrashVerdict.SCAFFOLD_SIDE


def test_parse_dedup_and_target_side_filter():
    txt = UBSAN_TARGET * 3 + UBSAN_HARNESS
    assert len(parse_ubsan_reports(txt)) == 2
    assert len(target_side_ubsan(txt, TARGETS)) == 1
