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

    def _wsl_cmd(self, binary_path: Path, runs: int) -> list:
        wsl_bin = self._win_to_wsl_path(binary_path)
        return ["wsl", "bash", "-c", f"{wsl_bin} -runs={runs} -max_total_time=3"]

    def _run_with_wsl_fallback(self, cmd, binary_path: Path, runs: int, timeout_sec: int):
        """
        NOTE (Oct 2 2026): added after a real item-2 run on Windows+WSL hit
        `WinError 193: %1 is not a valid Win32 application` on EVERY target's smoke test,
        while the matching compile step (CompilerOracle) succeeded. Root cause:
        `CompilerOracle._compile_native` already has a silent fallback to WSL on
        `FileNotFoundError` (clang++ not on the native Windows PATH) -- so on a machine
        where `settings.use_wsl` was (mis)detected as False, compilation still quietly
        produced a real binary via WSL (a Linux ELF), but `SmokeTestOracle` had NO
        equivalent fallback: it strictly trusted the same (wrong) `use_wsl` flag and tried
        to exec that ELF binary directly as a native Windows process -- guaranteed to fail
        on every single target, every iteration, indistinguishable in the report from a
        genuine harness defect. The self-repair loop then burned real iterations "fixing"
        code that was never the problem, silently inflating/corrupting item 2's own core
        statistic (iteration counts). Fixed the same way CompilerOracle already handles
        this: try native execution first (if not already using WSL), and on the exact
        Windows exec-format failure (or a plain FileNotFoundError), retry once via WSL
        before giving up -- so a wrong upfront `use_wsl` guess no longer causes a 100%,
        unrecoverable, environment-level failure rate across an entire run.
        """
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
        except (FileNotFoundError, OSError) as e:
            is_exec_format_error = isinstance(e, FileNotFoundError) or getattr(e, "winerror", None) == 193
            if self.use_wsl or not is_exec_format_error:
                raise
            wsl_cmd = self._wsl_cmd(binary_path, runs)
            return subprocess.run(wsl_cmd, capture_output=True, text=True, timeout=timeout_sec)

    def run_smoke_test(self, binary_path: Path, runs: int = 100) -> SmokeTestResult:
        """Executes the fuzzer binary for N runs with zero/empty inputs."""
        timeout_sec = self.settings.smoke_test_timeout_sec

        if self.use_wsl:
            cmd = self._wsl_cmd(binary_path, runs)
        else:
            cmd = [str(binary_path.resolve()), f"-runs={runs}", "-max_total_time=3"]

        try:
            res = self._run_with_wsl_fallback(cmd, binary_path, runs, timeout_sec)

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
