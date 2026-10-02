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
    # UPDATED Oct 2 2026, via a real diagnostic API call (targets/uart_pl011_item2/
    # diagnose_model.py), not a guess -- see FAILURE_TAXONOMY.md for the full finding.
    # gemini-1.5-pro and gemini-2.0-flash (the previous values) both returned a live
    # 404 NOT_FOUND. Google's own 404 error body for gemini-2.0-flash explicitly named
    # the replacement: "Please update your code to use models/gemini-3.8-flash" -- a
    # first-party confirmation, not web-research inference. gemini-3.1-pro-preview (the
    # only candidate Pro-tier model) returned 429 RESOURCE_EXHAUSTED with an explicit
    # limit of 0 on the free tier ("Quota exceeded ... limit: 0, model: gemini-3.1-pro"),
    # i.e. it is not merely daily-quota-exhausted, it is architecturally unusable on this
    # project's free-tier keys -- so there is currently no usable Pro-tier model at all.
    # gemini-3.8-flash itself returned a transient 503 UNAVAILABLE ("high demand") on
    # this one diagnostic call -- that is a temporary availability issue, not a model-name
    # problem (it would 404 if the name were wrong, the way the two retired models did).
    # Both fields are set to gemini-3.8-flash because it is the only model this sandbox's
    # diagnostic confirmed actually exists and is reachable on the free tier; there is no
    # second distinct model currently known to work, so fallback_model cannot yet provide
    # real model diversity (see the note on HarnessSynthesizerAgent.fallback_model in
    # agent.py -- it is also currently never used as an actual retry target, a separate,
    # pre-existing gap, not fixed here since there is nothing else to fall back to yet).
    gemini_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    primary_model: str = "gemini-3.8-flash"
    fallback_model: str = "gemini-3.8-flash"
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
