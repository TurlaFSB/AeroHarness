"""
Dynamic Smoke-Test Oracle for AeroHarness
Runs candidate binary against zero/dummy inputs to detect early crashes or infinite loops.
"""
import subprocess
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

from config.settings import get_settings


class SmokeTestResult(BaseModel):
    passed: bool
    crashed: bool
    timed_out: bool
    exit_code: int = 0
    crash_reason: Optional[str] = None
    stderr: str = ""
    stdout: str = ""


class SmokeTestOracle:
    """Performs dynamic dry-run execution to validate harness stability."""

    def __init__(self, use_wsl: Optional[bool] = None):
        self.settings = get_settings()
        self.use_wsl = self.settings.use_wsl if use_wsl is None else use_wsl

    def _win_to_wsl_path(self, path: Path) -> str:
        abs_path = path.resolve()
        drive = abs_path.drive.replace(":", "").lower()
        rest = str(abs_path.as_posix()).replace(f"{abs_path.drive}", "")
        return f"/mnt/{drive}{rest}"

    def run_smoke_test(self, binary_path: Path, runs: int = 100) -> SmokeTestResult:
        """Executes the fuzzer binary for N runs with zero/empty inputs."""
        timeout_sec = self.settings.smoke_test_timeout_sec

        if self.use_wsl:
            wsl_bin = self._win_to_wsl_path(binary_path)
            cmd = ["wsl", "bash", "-c", f"{wsl_bin} -runs={runs} -max_total_time=3"]
        else:
            cmd = [str(binary_path.resolve()), f"-runs={runs}", "-max_total_time=3"]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec
            )

            # Check if AddressSanitizer or crash occurred
            is_asan_crash = "AddressSanitizer" in res.stderr or "SEGV" in res.stderr or res.returncode != 0
            crash_reason = None
            if is_asan_crash:
                for line in res.stderr.splitlines():
                    if "ERROR: AddressSanitizer:" in line or "runtime error:" in line:
                        crash_reason = line.strip()
                        break
                if not crash_reason and res.returncode != 0:
                    crash_reason = f"Process exited with non-zero status code: {res.returncode}"

            return SmokeTestResult(
                passed=(res.returncode == 0 and not is_asan_crash),
                crashed=is_asan_crash,
                timed_out=False,
                exit_code=res.returncode,
                crash_reason=crash_reason,
                stderr=res.stderr,
                stdout=res.stdout
            )

        except subprocess.TimeoutExpired:
            return SmokeTestResult(
                passed=False,
                crashed=False,
                timed_out=True,
                exit_code=-1,
                crash_reason="Execution timed out (Possible infinite loop or hardware register polling lock)",
                stderr="Timeout expired during smoke test run."
            )
        except Exception as e:
            return SmokeTestResult(
                passed=False,
                crashed=True,
                timed_out=False,
                exit_code=-1,
                crash_reason=f"Failed to execute smoke test: {str(e)}",
                stderr=str(e)
            )
