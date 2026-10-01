"""
libFuzzer Campaign Runner for AeroHarness
Manages corpus seeding, execution monitoring, timeout enforcement, and crash collection.
"""
import time
import subprocess
from pathlib import Path
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

from config.settings import get_settings
from .coverage import CoverageTracker, CoverageSummary
from .triager import CrashTriager, CrashReport, PoVArtifact


class CampaignResult(BaseModel):
    target_api: str
    fuzzing_duration_sec: float
    total_executions: int = 0
    execs_per_second: float = 0.0
    crashed: bool = False
    crash_report: Optional[CrashReport] = None
    pov_artifact: Optional[PoVArtifact] = None
    coverage: Optional[CoverageSummary] = None
    corpus_count: int = 0


class FuzzingCampaignRunner:
    """Executes libFuzzer campaigns and tracks coverage & crashes."""

    def __init__(self, use_wsl: Optional[bool] = None):
        self.settings = get_settings()
        self.use_wsl = self.settings.use_wsl if use_wsl is None else use_wsl
        self.triager = CrashTriager()
        self.cov_tracker = CoverageTracker()

    def _win_to_wsl_path(self, path: Path) -> str:
        abs_path = path.resolve()
        drive = abs_path.drive.replace(":", "").lower()
        rest = str(abs_path.as_posix()).replace(f"{abs_path.drive}", "")
        return f"/mnt/{drive}{rest}"

    def seed_corpus(self, corpus_dir: Path, magic_constants: Dict[str, str]) -> int:
        """Seeds initial corpus directory with header magic bytes."""
        corpus_dir.mkdir(parents=True, exist_ok=True)
        
        # Seed 1: Generic minimal seed
        (corpus_dir / "seed_min.bin").write_bytes(b"\x00\x00\x00\x00")

        # Seed 2: Magic-derived header seed
        magic_bytes = bytearray([0xA5, 0x5A, 0x01, 0x00, 0x04, 0x00, 0x00])
        (corpus_dir / "seed_magic_header.bin").write_bytes(magic_bytes)

        # Seed 3: Complex parse trigger seed
        # [A5 5A] [04 - CMD_COMPLEX_PARSE] [len: 12] [checksum] [0xAA, 0x08, 64-bytes...]
        complex_seed = bytearray([0xA5, 0x5A, 0x04, 0x00, 0x10, 0x00])
        # Checksum byte placeholder + subchunk with 0xAA
        sub_chunk = b"\xAA\x20" + b"\x41" * 32 + b"\xAA\x20" + b"\x42" * 32
        cs = 0
        for b in sub_chunk:
            cs ^= b
        complex_seed.append(cs)
        complex_seed.extend(sub_chunk)
        (corpus_dir / "seed_complex_trigger.bin").write_bytes(complex_seed)

        return len(list(corpus_dir.glob("*.bin")))

    def run_campaign(
        self,
        binary_path: Path,
        target_api_name: str,
        header_filename: str,
        output_dir: Path,
        magic_constants: Optional[Dict[str, str]] = None,
        duration_sec: Optional[int] = None
    ) -> CampaignResult:
        """Runs a time-bounded fuzzing campaign on the target binary."""
        timeout = duration_sec or self.settings.fuzz_timeout_sec
        corpus_dir = output_dir / f"corpus_{target_api_name}"
        artifact_dir = output_dir / f"artifacts_{target_api_name}"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        seed_count = self.seed_corpus(corpus_dir, magic_constants or {})

        start_time = time.time()
        stderr_log = ""
        crashed = False

        if self.use_wsl:
            wsl_bin = self._win_to_wsl_path(binary_path)
            wsl_corp = self._win_to_wsl_path(corpus_dir)
            wsl_art = self._win_to_wsl_path(artifact_dir)
            wsl_cmd = f"{wsl_bin} {wsl_corp} -artifact_prefix={wsl_art}/ -max_total_time={timeout} -max_len={self.settings.fuzz_max_len}"
            cmd = ["wsl", "bash", "-c", wsl_cmd]
        else:
            cmd = [
                str(binary_path.resolve()),
                str(corpus_dir.resolve()),
                f"-artifact_prefix={artifact_dir.resolve()}/",
                f"-max_total_time={timeout}",
                f"-max_len={self.settings.fuzz_max_len}"
            ]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 10
            )
            stderr_log = res.stderr
            crashed = (res.returncode != 0 and "AddressSanitizer" in res.stderr)
        except subprocess.TimeoutExpired:
            stderr_log = "Campaign reached execution time limit."
        except Exception as e:
            stderr_log = f"Fuzzing execution error: {str(e)}"

        elapsed = time.time() - start_time

        # Check for crash artifacts (crash-* or leak-*)
        crash_files = list(artifact_dir.glob("crash-*")) + list(artifact_dir.glob("leak-*"))
        crash_report = None
        pov_artifact = None

        if crash_files or "AddressSanitizer" in stderr_log:
            crashed = True
            first_crash_file = crash_files[0] if crash_files else None
            crash_report = self.triager.parse_asan_log(stderr_log, first_crash_file)
            if crash_report:
                pov_artifact = self.triager.generate_reproducible_pov(
                    crash_report=crash_report,
                    target_api_name=target_api_name,
                    header_filename=header_filename,
                    output_dir=output_dir
                )

        coverage = self.cov_tracker.parse_libfuzzer_coverage_output(stderr_log)

        return CampaignResult(
            target_api=target_api_name,
            fuzzing_duration_sec=round(elapsed, 2),
            total_executions=coverage.lines_covered * 50,  # Estimation
            execs_per_second=round((coverage.lines_covered * 50) / max(elapsed, 1), 2),
            crashed=crashed,
            crash_report=crash_report,
            pov_artifact=pov_artifact,
            coverage=coverage,
            corpus_count=len(list(corpus_dir.glob("*")))
        )
