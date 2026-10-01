"""
Compiler Verification Oracle for AeroHarness
Compiles candidate harnesses with Clang, ASan, and UBSan, parsing diagnostics.
"""
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from pydantic import BaseModel, Field

from config.settings import get_settings


class Diagnostic(BaseModel):
    file: str
    line: Optional[int] = None
    column: Optional[int] = None
    level: str = "error"  # 'error', 'warning', 'note', 'fatal'
    message: str


class CompilationResult(BaseModel):
    success: bool
    binary_path: Optional[str] = None
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    diagnostics: List[Diagnostic] = Field(default_factory=list)
    is_linking_error: bool = False
    undefined_symbols: List[str] = Field(default_factory=list)


class CompilerOracle:
    """Executes Clang/LLVM compilation with address and fuzzing sanitizers."""

    def __init__(self, use_wsl: Optional[bool] = None):
        self.settings = get_settings()
        self.use_wsl = self.settings.use_wsl if use_wsl is None else use_wsl

    def _win_to_wsl_path(self, path: Path) -> str:
        """Converts Windows path like D:\\aeroharness to /mnt/d/aeroharness."""
        abs_path = path.resolve()
        drive = abs_path.drive.replace(":", "").lower()
        rest = str(abs_path.as_posix()).replace(f"{abs_path.drive}", "")
        return f"/mnt/{drive}{rest}"

    def compile_harness(
        self,
        harness_src_path: Path,
        target_c_files: List[Path],
        include_dirs: List[Path],
        output_binary_path: Path
    ) -> CompilationResult:
        """Compiles the candidate fuzz harness and target C files into an instrumented binary."""
        output_binary_path.parent.mkdir(parents=True, exist_ok=True)

        if self.use_wsl:
            return self._compile_via_wsl(harness_src_path, target_c_files, include_dirs, output_binary_path)
        else:
            return self._compile_native(harness_src_path, target_c_files, include_dirs, output_binary_path)

    def _compile_native(
        self,
        harness_path: Path,
        target_c_files: List[Path],
        include_dirs: List[Path],
        out_bin: Path
    ) -> CompilationResult:
        """Invokes native Clang on Windows."""
        cmd = ["clang++"] + self.settings.cxx_flags
        for inc in include_dirs:
            cmd.append(f"-I{inc.resolve()}")
        cmd.append(str(harness_path.resolve()))
        for c_file in target_c_files:
            cmd.append(str(c_file.resolve()))
        cmd.extend(["-o", str(out_bin.resolve())])

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return self._parse_compilation_output(res.returncode, res.stdout, res.stderr, out_bin)
        except FileNotFoundError:
            # Clang not found natively, try WSL fallback automatically
            return self._compile_via_wsl(harness_path, target_c_files, include_dirs, out_bin)
        except Exception as e:
            return CompilationResult(
                success=False,
                exit_code=-1,
                stderr=f"Compilation execution failed: {str(e)}",
                diagnostics=[Diagnostic(file=str(harness_path), message=str(e))]
            )

    def _compile_via_wsl(
        self,
        harness_path: Path,
        target_c_files: List[Path],
        include_dirs: List[Path],
        out_bin: Path
    ) -> CompilationResult:
        """Invokes Clang inside Ubuntu WSL2."""
        wsl_harness = self._win_to_wsl_path(harness_path)
        wsl_out = self._win_to_wsl_path(out_bin)
        wsl_c_files = [self._win_to_wsl_path(p) for p in target_c_files]
        wsl_incs = [f"-I{self._win_to_wsl_path(p)}" for p in include_dirs]

        cxx_flags_str = " ".join(self.settings.cxx_flags)
        inc_str = " ".join(wsl_incs)
        c_files_str = " ".join(wsl_c_files)

        wsl_cmd = f"clang++ {cxx_flags_str} {inc_str} {wsl_harness} {c_files_str} -o {wsl_out}"
        cmd = ["wsl", "bash", "-c", wsl_cmd]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            return self._parse_compilation_output(res.returncode, res.stdout, res.stderr, out_bin)
        except Exception as e:
            return CompilationResult(
                success=False,
                exit_code=-1,
                stderr=f"WSL compilation error: {str(e)}",
                diagnostics=[Diagnostic(file=str(harness_path), message=str(e))]
            )

    def _parse_compilation_output(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        out_bin: Path
    ) -> CompilationResult:
        """Parses Clang errors and linker outputs."""
        success = (exit_code == 0)
        diagnostics = []
        is_linking = False
        undefined_symbols = []

        # Parse Clang compiler diagnostics: filename:line:col: error/warning: message
        diag_pattern = re.compile(r'([^:\n]+):(\d+):(\d+):\s+(error|warning|fatal error|note):\s+(.*)')
        for match in diag_pattern.finditer(stderr):
            fpath, line, col, level, msg = match.groups()
            diagnostics.append(Diagnostic(
                file=fpath.strip(),
                line=int(line),
                column=int(col),
                level=level.strip(),
                message=msg.strip()
            ))

        # Detect linker errors: undefined reference to '...'
        undef_pattern = re.compile(r'undefined reference to [\'`]([^\'^\`]+)[\'|\`]')
        for match in undef_pattern.finditer(stderr):
            is_linking = True
            undefined_symbols.append(match.group(1).strip())

        if "undefined reference" in stderr or "ld returned 1 exit status" in stderr:
            is_linking = True

        return CompilationResult(
            success=success,
            binary_path=str(out_bin) if success else None,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            diagnostics=diagnostics,
            is_linking_error=is_linking,
            undefined_symbols=list(set(undefined_symbols))
        )
