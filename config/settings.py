"""
AeroHarness Configuration and Global Settings
"""
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field


class Settings(BaseModel):
    # Paths
    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent)
    targets_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "targets")
    output_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent.parent / "output")
    
    # LLM Configuration
    # UPDATED Oct 2 2026, via real diagnostic API calls (targets/uart_pl011_item2/
    # diagnose_model.py), not a guess -- see FAILURE_TAXONOMY.md for the full finding.
    # gemini-1.5-pro and gemini-2.0-flash (the original values) both returned a live
    # 404 NOT_FOUND -- confirmed dead. gemini-3.1-pro-preview (the only candidate
    # Pro-tier model) returned 429 RESOURCE_EXHAUSTED with an explicit limit of 0 on the
    # free tier -- architecturally unusable on these keys, not just quota-exhausted for
    # today, so there is currently no usable Pro-tier model at all.
    # gemini-3.8-flash first returned a transient 503 (high demand) twice in a row, then
    # SUCCEEDED on a later retry, confirming the earlier 503s were genuinely temporary
    # rather than a name problem. A second, independent, equally capable-tier model,
    # gemini-3.7-flash, also returned a real SUCCESS in the same diagnostic run, giving
    # genuine model diversity -- primary_model is the newest/most capable confirmed-live
    # model (Google's own description: "most intelligent Flash model, engineered for
    # long-horizon software engineering" -- a good match for harness synthesis), and
    # fallback_model is a different, also-confirmed-live model, not a duplicate of
    # primary_model. HarnessSynthesizerAgent now genuinely retries fallback_model on a
    # primary_model failure (src/synthesizer/agent.py::_generate_content) instead of
    # silently storing an unused field.
    gemini_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    primary_model: str = "gemini-3.8-flash"
    fallback_model: str = "gemini-3.7-flash"
    temperature: float = 0.2
    
    # Compiler & Fuzzer Settings
    compiler_cmd: str = "clang++"
    c_compiler_cmd: str = "clang"
    use_wsl: bool = False
    
    # Compiler & Sanitizer Flags
    cxx_flags: List[str] = [
        "-std=c++17",
        "-fsanitize=fuzzer,address,undefined",
        "-fno-omit-frame-pointer",
        "-g",
        "-O1",
        "-Wall",
        "-Wextra"
    ]
    
    c_flags: List[str] = [
        "-std=c99",
        "-fsanitize=address,undefined",
        "-fno-omit-frame-pointer",
        "-g",
        "-O1"
    ]
    
    # Self-Repair Oracle Parameters
    max_repair_iterations: int = 5
    smoke_test_runs: int = 500
    smoke_test_timeout_sec: int = 5
    
    # Fuzzing Parameters
    fuzz_timeout_sec: int = 60
    fuzz_max_len: int = 4096
    
    def detect_compiler_environment(self) -> None:
        """Detect whether clang is available natively or via WSL."""
        # 1. Check native clang++
        if shutil.which("clang++") or shutil.which("clang"):
            self.use_wsl = False
            return
        
        # 2. Check WSL
        try:
            res = subprocess.run(
                ["wsl", "which", "clang++"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if res.returncode == 0 and res.stdout.strip():
                self.use_wsl = True
                return
        except Exception:
            pass
        
        # Fallback check
        self.use_wsl = False


_settings_instance: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings()
        _settings_instance.detect_compiler_environment()
        _settings_instance.output_dir.mkdir(parents=True, exist_ok=True)
    return _settings_instance
