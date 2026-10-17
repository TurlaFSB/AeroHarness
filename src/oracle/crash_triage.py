"""
Crash-location triage for the self-repair loop.

Why this exists (Oct 2026, work plan item 2). The repair loop treats every runtime
failure of a candidate harness as a defect of the *harness* and asks the model to fix it.
That is wrong when the sanitizer report points into the code under test: the model then
"repairs" the harness by constraining its input so the defect is no longer reached, and the
real bug is silently removed from the result. This happened for ``pl011_set_baudrate``
(see RESULTS.md, "Work Plan Item 2: llvm-cov Line Coverage"): iteration 2 failed on a
division by zero located in the driver, iteration 3 passed after the harness was changed to
replace ``baudrate == 0`` by 1, and a longer fuzz run then crashed the final harness on the
integer-overflow variant of the same defect within 64 executions.

This module decides *where* a sanitizer report points. It is deliberately a pure function of
the report text and a few file paths, so it can be tested offline with real sanitizer
output and has no dependency on the compiler, the model or the filesystem layout.

Verdicts
--------
HARNESS_SIDE   top informative location is the generated harness file
TARGET_SIDE    top informative location is the code under test (its .c file or its header)
SCAFFOLD_SIDE  top informative location is elsewhere in the project (mock headers, stubs)
UNKNOWN        the report contains no usable source location

A TARGET_SIDE verdict is a *candidate*, never a confirmed vulnerability: the harness may
have violated a precondition of the target (for example a NULL config pointer the real
caller never passes). Confirming reachability through the target's public API is a separate,
manual step.

How the deciding location is chosen
-----------------------------------
1. If the report contains an AddressSanitizer abort, the first stack frame that has a
   source location and is not sanitizer/fuzzer runtime or system code decides. (The ASan
   abort is what actually ended the process.)
2. Otherwise the first UBSan ``runtime error`` line decides. (This matches the line the
   legacy loop already shows to the model.)
Limitation: a source path containing a space cannot be parsed from an ASan frame and is
treated as having no location.
"""
from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Optional

from pydantic import BaseModel


class CrashVerdict(str, Enum):
    HARNESS_SIDE = "HARNESS_SIDE"
    TARGET_SIDE = "TARGET_SIDE"
    SCAFFOLD_SIDE = "SCAFFOLD_SIDE"
    UNKNOWN = "UNKNOWN"


class CrashSite(BaseModel):
    file: str
    line: int
    col: Optional[int] = None
    function: Optional[str] = None
    origin: str  # 'asan_frame' | 'ubsan_line'


class CrashTriage(BaseModel):
    verdict: CrashVerdict
    site: Optional[CrashSite] = None
    message: str = ""
    asan_abort: bool = False


class UbsanReport(BaseModel):
    file: str
    line: int
    col: Optional[int] = None
    message: str


class CrashFinding(BaseModel):
    """A target-side crash kept as evidence instead of being repaired away."""

    iteration: int
    stage: str
    verdict: CrashVerdict
    site_file: str
    site_line: int
    site_col: Optional[int] = None
    site_function: Optional[str] = None
    message: str = ""
    reproducer_path: Optional[str] = None
    evidence_excerpt: str = ""
    status: str = "CANDIDATE: requires reachability triage through the target's public API"
    # Set when the loop ends: True if a later iteration produced a passing harness, i.e.
    # the legacy behaviour would have removed this finding from the result.
    masked_by_repair: Optional[bool] = None


_UBSAN_RE = re.compile(
    r"^(?P<file>.+?):(?P<line>\d+):(?P<col>\d+): runtime error: (?P<msg>.*?)\s*$"
)
_FRAME_RE = re.compile(r"^\s*#(?P<n>\d+)\s+0x[0-9a-fA-F]+\s+in\s+(?P<rest>.+?)\s*$")
_LOC_TAIL_RE = re.compile(r"^(?P<path>\S+?):(?P<line>\d+)(?::(?P<col>\d+))?$")

# Frames from these functions are runtime plumbing, never the deciding location.
_RUNTIME_FUNC_PREFIXES = (
    "__asan_", "__sanitizer", "__interceptor_", "__ubsan", "__msan", "__tsan",
    "fuzzer::", "__libc_start", "_start", "main", "std::", "__gnu_cxx::",
)
# Source locations under these prefixes are system code, never the deciding location.
_SYSTEM_PATH_PREFIXES = ("/usr/", "/lib/", "/lib64/", "/proc/")


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def _is_system_path(path: str) -> bool:
    p = _norm(path)
    return p.startswith(_SYSTEM_PATH_PREFIXES) or "compiler-rt" in p or "/llvm-" in p


def _same_file(reported: str, known: Path) -> bool:
    """True if a path printed by the sanitizer denotes ``known``. Absolute paths must
    match exactly (after normalisation); a relative reported path matches on its tail."""
    r = _norm(reported)
    k = _norm(str(known))
    if r == k:
        return True
    try:
        if _norm(str(Path(reported).resolve())) == _norm(str(known.resolve())):
            return True
    except (OSError, RuntimeError):
        pass
    if not (r.startswith("/") or (len(r) > 1 and r[1] == ":")):
        return k.endswith("/" + r.lstrip("./")) or Path(r).name == known.name and "/" not in r
    return False


def parse_ubsan_reports(stderr: str) -> List[UbsanReport]:
    """Every UBSan ``runtime error`` line, in order, de-duplicated by location+message."""
    seen, out = set(), []
    for raw in (stderr or "").splitlines():
        m = _UBSAN_RE.match(raw.strip())
        if not m:
            continue
        key = (m["file"], m["line"], m["col"], m["msg"])
        if key in seen:
            continue
        seen.add(key)
        out.append(UbsanReport(file=m["file"], line=int(m["line"]), col=int(m["col"]), message=m["msg"]))
    return out


def _asan_frames(stderr: str) -> List[CrashSite]:
    frames: List[CrashSite] = []
    in_report = False
    for raw in (stderr or "").splitlines():
        if "ERROR: AddressSanitizer" in raw:
            in_report = True
            frames = []  # keep only the frames of the last report
            continue
        if not in_report:
            continue
        m = _FRAME_RE.match(raw)
        if not m:
            continue
        rest = m["rest"]
        tail = rest.rsplit(" ", 1)
        if len(tail) != 2:
            continue
        func, loc = tail
        lm = _LOC_TAIL_RE.match(loc)
        if not lm:
            continue  # binary+offset form, no source location
        frames.append(CrashSite(
            file=lm["path"], line=int(lm["line"]),
            col=int(lm["col"]) if lm["col"] else None,
            function=func.strip(), origin="asan_frame"))
    return frames


def _informative(site: CrashSite) -> bool:
    if site.function and site.function.startswith(_RUNTIME_FUNC_PREFIXES):
        return False
    return not _is_system_path(site.file)


def extract_crash_site(stderr: str) -> tuple[Optional[CrashSite], bool]:
    """Returns (deciding site or None, whether an AddressSanitizer abort was present)."""
    asan = "ERROR: AddressSanitizer" in (stderr or "")
    if asan:
        for fr in _asan_frames(stderr):
            if _informative(fr):
                return fr, True
    ub = parse_ubsan_reports(stderr)
    for u in ub:
        site = CrashSite(file=u.file, line=u.line, col=u.col, origin="ubsan_line")
        if not _is_system_path(u.file):
            return site, asan
    return None, asan


def classify_site(site: CrashSite, harness_path: Path, target_paths: Iterable[Path]) -> CrashVerdict:
    if _same_file(site.file, harness_path):
        return CrashVerdict.HARNESS_SIDE
    for tp in target_paths:
        if _same_file(site.file, tp):
            return CrashVerdict.TARGET_SIDE
    return CrashVerdict.SCAFFOLD_SIDE


def target_path_set(target_c_files: Iterable[Path], header_path: Optional[Path] = None) -> List[Path]:
    """The target's own sources: its .c files and its header (``header_path``)."""
    paths = [Path(p) for p in target_c_files]
    if header_path is not None:
        paths.append(Path(header_path))
    return paths


def triage_crash(stderr: str, harness_path: Path, target_paths: Iterable[Path]) -> CrashTriage:
    site, asan = extract_crash_site(stderr)
    if site is None:
        return CrashTriage(verdict=CrashVerdict.UNKNOWN, asan_abort=asan,
                           message="no source location in the sanitizer report")
    verdict = classify_site(site, Path(harness_path), list(target_paths))
    return CrashTriage(verdict=verdict, site=site, asan_abort=asan,
                       message=f"{site.file}:{site.line} ({site.origin})")


def target_side_ubsan(stderr: str, target_paths: Iterable[Path]) -> List[UbsanReport]:
    """UBSan reports located in the target's own sources. UBSan runs in recover mode, so
    these do not fail a run and are invisible to the legacy loop."""
    tps = list(target_paths)
    return [u for u in parse_ubsan_reports(stderr) if any(_same_file(u.file, tp) for tp in tps)]


def evidence_excerpt(stderr: str, max_lines: int = 40) -> str:
    """The part of the report that matters: from the first error line, bounded."""
    lines = (stderr or "").splitlines()
    start = 0
    for i, ln in enumerate(lines):
        if "runtime error:" in ln or "ERROR: AddressSanitizer" in ln:
            start = i
            break
    return "\n".join(lines[start:start + max_lines])
