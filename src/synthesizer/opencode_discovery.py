"""
Cross-Platform OpenCode Discovery and Auto-Configuration Engine.
Automatically locates OpenCode credentials (auth.json) and binaries on Ubuntu/Linux and Windows.
"""
import os
import sys
import json
import shutil
import platform
from pathlib import Path
from typing import Optional, Dict, Any


def get_opencode_auth_candidates() -> list[Path]:
    """Returns candidate paths for auth.json across Linux and Windows."""
    home = Path.home()
    candidates = []

    # Custom override
    if os.environ.get("OPENCODE_AUTH_PATH"):
        candidates.append(Path(os.environ["OPENCODE_AUTH_PATH"]))

    # Linux / Unix / macOS standard paths
    candidates.append(home / ".local" / "share" / "opencode" / "auth.json")
    if os.environ.get("XDG_DATA_HOME"):
        candidates.append(Path(os.environ["XDG_DATA_HOME"]) / "opencode" / "auth.json")
    candidates.append(home / ".config" / "opencode" / "auth.json")

    # Windows standard paths
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"]) / "opencode" / "auth.json")
    if os.environ.get("APPDATA"):
        candidates.append(Path(os.environ["APPDATA"]) / "opencode" / "auth.json")
    if os.environ.get("USERPROFILE"):
        candidates.append(Path(os.environ["USERPROFILE"]) / ".local" / "share" / "opencode" / "auth.json")
    candidates.append(home / "AppData" / "Local" / "opencode" / "auth.json")
    candidates.append(home / "AppData" / "Roaming" / "opencode" / "auth.json")

    return candidates


def get_opencode_bin_candidates() -> list[Path]:
    """Returns candidate paths for opencode executable across Linux and Windows."""
    home = Path.home()
    candidates = []

    # Custom override
    if os.environ.get("OPENCODE_BIN"):
        candidates.append(Path(os.environ["OPENCODE_BIN"]))

    # PATH checks
    which_bin = shutil.which("opencode")
    if which_bin:
        candidates.append(Path(which_bin))
    which_exe = shutil.which("opencode.exe")
    if which_exe:
        candidates.append(Path(which_exe))

    # Linux / macOS standard paths
    candidates.append(home / ".opencode" / "bin" / "opencode")
    candidates.append(home / ".local" / "bin" / "opencode")
    candidates.append(Path("/usr/local/bin/opencode"))
    candidates.append(Path("/usr/bin/opencode"))

    # Windows standard paths
    candidates.append(home / ".opencode" / "bin" / "opencode.exe")
    candidates.append(home / "AppData" / "Local" / "opencode" / "bin" / "opencode.exe")
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(Path(os.environ["LOCALAPPDATA"]) / "opencode" / "bin" / "opencode.exe")
    if os.environ.get("APPDATA"):
        candidates.append(Path(os.environ["APPDATA"]) / "npm" / "opencode.cmd")
        candidates.append(Path(os.environ["APPDATA"]) / "npm" / "opencode")

    return candidates


def discover_opencode() -> Dict[str, Any]:
    """
    Auto-discovers OpenCode API credentials and binary path.
    Works seamlessly on Ubuntu (Linux) and Windows.
    """
    current_os = platform.system().lower()
    api_key: Optional[str] = os.environ.get("OPENCODE_API_KEY")
    auth_file_found: Optional[str] = None
    binary_found: Optional[str] = None

    # 1. Locate auth.json
    for path in get_opencode_auth_candidates():
        try:
            if path.is_file():
                auth_file_found = str(path)
                if not api_key:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        # Pattern 1: {"opencode": {"key": "sk-...", "type": "api"}}
                        if "opencode" in data and isinstance(data["opencode"], dict):
                            api_key = data["opencode"].get("key")
                        # Pattern 2: {"key": "sk-..."}
                        elif "key" in data and isinstance(data["key"], str):
                            api_key = data["key"]
                if auth_file_found and api_key:
                    break
        except Exception:
            continue

    # 2. Locate opencode executable binary
    for path in get_opencode_bin_candidates():
        try:
            if path.is_file() and os.access(str(path), os.X_OK):
                binary_found = str(path)
                break
        except Exception:
            continue

    base_url = os.environ.get("OPENCODE_BASE_URL", "https://opencode.ai/zen/v1")
    model = os.environ.get("OPENCODE_MODEL", "opencode/nemotron-3.5-lightning-free")

    return {
        "api_key": api_key,
        "binary_path": binary_found,
        "auth_file": auth_file_found,
        "base_url": base_url,
        "model": model,
        "os": current_os,
        "available": bool(api_key or binary_found),
    }
