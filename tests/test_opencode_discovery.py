"""
Unit tests for cross-platform OpenCode auto-discovery.
"""
from pathlib import Path
from src.synthesizer.opencode_discovery import (
    discover_opencode,
    get_opencode_auth_candidates,
    get_opencode_bin_candidates,
)


def test_opencode_candidate_paths():
    auth_paths = get_opencode_auth_candidates()
    bin_paths = get_opencode_bin_candidates()

    assert len(auth_paths) > 0
    assert len(bin_paths) > 0

    # Ensure cross-platform paths are represented
    auth_str = [str(p) for p in auth_paths]
    assert any(".local/share/opencode" in s or "AppData" in s or "auth.json" in s for s in auth_str)


def test_opencode_discovery():
    disc = discover_opencode()
    assert isinstance(disc, dict)
    assert "available" in disc
    assert "base_url" in disc
    assert "model" in disc
    assert disc["base_url"].startswith("http")
