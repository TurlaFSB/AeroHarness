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
    # !! STALE AS OF Oct 2 2026 -- DO NOT TRUST WITHOUT A LIVE CHECK !!
    # Both model names below are confirmed deprecated/shut down by Google as of Oct 2026
    # (gemini-1.5-pro: all Gemini 1.5 models deprecated; gemini-2.0-flash: shutdown date
    # June 1 2026, already passed). This is the most likely root cause of Work Plan item
    # 2's second real run failing all 4 API keys on their very first call each (not a
    # quota-exhaustion shape -- see FAILURE_TAXONOMY.md). Candidate replacements found via
    # web research (ai.google.dev/gemini-api/docs/models, Oct 2 2026): Pro-tier has no
    # current stable option, only "gemini-3.1-pro-preview" (Preview); Flash-tier stable
    # is "gemini-3.8-flash". NEITHER has been confirmed against a real, working Gemini API
    # call -- this sandbox cannot reach generativelanguage.googleapis.com to verify them
    # itself, and a wrong guess burns real daily quota across all 4 configured keys again.
    # Do not change these two literals until a live diagnostic call (see
    # ANTIGRAVITY_TASK_ITEM2.md's revision note) confirms the exact correct string.
    gemini_api_key: Optional[str] = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    primary_model: str = "gemini-1.5-pro"
    fallback_model: str = "gemini-2.0-flash"
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
