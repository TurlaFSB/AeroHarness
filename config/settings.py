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
