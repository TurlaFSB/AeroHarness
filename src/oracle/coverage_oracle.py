"""
Line-coverage oracle for the self-repair loop.

The compile and smoke oracles say a harness *runs*; they do not say it *exercises* the code
under test. In the Oct 2026 triage run, ``pl011_irq_tx_enable`` was recorded as SUCCESS with
11 of 22 driver lines covered because its harness always set the interrupt callback to NULL,
so the target returned early on every execution (RESULTS.md, "Diagnosis of the two
triage-run anomalies"). This oracle measures which lines of the target's own ``.c`` files a
short fuzz campaign reaches, so the loop can feed the unreached lines back to the model.

It builds the same two translation units as the pipeline (harness + target ``.c``) with
``-fprofile-instr-generate -fcoverage-mapping`` and reads ``llvm-cov export -format=lcov``.
Native Linux/WSL-shell execution only: under ``use_wsl`` (Windows host driving WSL) it
reports an error result rather than guessing, and the caller skips the step.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from config.settings import get_settings


class CoverageResult(BaseModel):
    ok: bool
    error: Optional[str] = None
    covered: int = 0
    total: int = 0
    uncovered_lines: Dict[str, List[int]] = Field(default_factory=dict)  # file -> line numbers
    crashed: bool = False  # the measuring campaign aborted; figures are from a corpus replay

    @property
    def fraction(self) -> float:
        return (self.covered / self.total) if self.total else 1.0


def parse_lcov(text: str, wanted: List[Path]) -> tuple[int, int, Dict[str, List[int]]]:
    """Parses lcov ``SF:`` / ``DA:line,count`` records, keeping only files that denote one of
    ``wanted``. Returns (covered lines, instrumented lines, uncovered line numbers per file)."""
    want = [str(Path(w).resolve()) for w in wanted]
    cur: Optional[str] = None
    covered = total = 0
    unc: Dict[str, List[int]] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("SF:"):
            p = line[3:]
            try:
                rp = str(Path(p).resolve())
            except OSError:
                rp = p
            cur = p if rp in want else None
        elif line.startswith("DA:") and cur is not None:
            try:
                ln_s, cnt_s = line[3:].split(",")[:2]
                ln, cnt = int(ln_s), int(cnt_s)
            except ValueError:
                continue
            total += 1
            if cnt > 0:
                covered += 1
            else:
                unc.setdefault(cur, []).append(ln)
    return covered, total, {k: sorted(set(v)) for k, v in unc.items()}


class CoverageOracle:
    def __init__(self, use_wsl: Optional[bool] = None):
        self.settings = get_settings()
        self.use_wsl = self.settings.use_wsl if use_wsl is None else use_wsl

    def measure(
        self,
        harness_src_path: Path,
        target_c_files: List[Path],
        include_dirs: List[Path],
        work_dir: Path,
        runs: int = 20000,
        max_total_time: int = 30,
    ) -> CoverageResult:
        if self.use_wsl:
            return CoverageResult(ok=False, error="coverage measurement is not supported with use_wsl")
        for tool in ("clang++", "llvm-profdata", "llvm-cov"):
            if not shutil.which(tool):
                return CoverageResult(ok=False, error=f"{tool} not found on PATH")
        work_dir.mkdir(parents=True, exist_ok=True)
        binp = work_dir / "cov_bin"
        raw = work_dir / "cov.profraw"
        prof = work_dir / "cov.profdata"
        corpus = work_dir / "cov_corpus"
        art = work_dir / "cov_artifacts"
        corpus.mkdir(exist_ok=True)
        art.mkdir(exist_ok=True)
        for stale in (raw, prof):
            stale.unlink(missing_ok=True)

        cmd = (["clang++", "-std=c++17", "-fsanitize=fuzzer,address", "-fprofile-instr-generate",
                "-fcoverage-mapping", "-O1", "-fno-inline", "-g", "-w"]
               + [f"-I{Path(i).resolve()}" for i in include_dirs]
               + [str(Path(harness_src_path).resolve())]
               + [str(Path(c).resolve()) for c in target_c_files]
               + ["-o", str(binp)])
        try:
            cb = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except Exception as e:  # noqa: BLE001
            return CoverageResult(ok=False, error=f"coverage build failed to run: {e}")
        if cb.returncode != 0:
            return CoverageResult(ok=False, error="coverage build failed: " + cb.stderr.strip()[-300:])

        env = dict(os.environ, LLVM_PROFILE_FILE=str(raw))
        crashed = False
        try:
            fr = subprocess.run(
                [str(binp), str(corpus), f"-runs={runs}", f"-max_total_time={max_total_time}",
                 "-timeout=5", "-max_len=512", "-print_final_stats=0", f"-artifact_prefix={art}/"],
                capture_output=True, text=True, timeout=max_total_time + 60, env=env)
            crashed = fr.returncode != 0 or "ERROR: " in (fr.stderr or "")
        except subprocess.TimeoutExpired:
            pass  # a slow campaign still leaves a profile only if it exited; handled below
        if crashed or not raw.exists() or raw.stat().st_size == 0:
            # An aborted process writes no profile; replay the corpus saved before the abort.
            raw.unlink(missing_ok=True)
            try:
                subprocess.run([str(binp), str(corpus), "-runs=0", f"-artifact_prefix={art}/"],
                               capture_output=True, text=True, timeout=120, env=env)
            except subprocess.TimeoutExpired:
                pass
        if not raw.exists() or raw.stat().st_size == 0:
            return CoverageResult(ok=False, error="no coverage profile produced", crashed=crashed)
        pm = subprocess.run(["llvm-profdata", "merge", "-sparse", str(raw), "-o", str(prof)],
                            capture_output=True, text=True)
        if pm.returncode != 0:
            return CoverageResult(ok=False, error="llvm-profdata merge failed: " + pm.stderr[-200:])
        ex = subprocess.run(["llvm-cov", "export", "-format=lcov", str(binp),
                             f"-instr-profile={prof}"] + [str(Path(c).resolve()) for c in target_c_files],
                            capture_output=True, text=True)
        if ex.returncode != 0:
            return CoverageResult(ok=False, error="llvm-cov export failed: " + ex.stderr[-200:])
        covered, total, unc = parse_lcov(ex.stdout, target_c_files)
        if total == 0:
            return CoverageResult(ok=False, error="no instrumented lines found in the target sources",
                                  crashed=crashed)
        for p in (binp, raw, prof):
            p.unlink(missing_ok=True)
        shutil.rmtree(corpus, ignore_errors=True)
        shutil.rmtree(art, ignore_errors=True)
        return CoverageResult(ok=True, covered=covered, total=total, uncovered_lines=unc, crashed=crashed)
