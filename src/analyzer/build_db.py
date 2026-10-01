"""
Build Database and compile_commands.json Parser for AeroHarness
Extracts include directories, preprocessor defines, and compiler flags from build databases.
"""
import json
import shlex
from pathlib import Path
from typing import List, Dict, Set, Optional
from pydantic import BaseModel, Field


class BuildTargetInfo(BaseModel):
    source_file: str
    include_dirs: List[str] = Field(default_factory=list)
    defines: List[str] = Field(default_factory=list)
    compiler: str = "clang"
    raw_command: str = ""


class BuildDatabase:
    """Parses and manages compilation databases for complex embedded codebases."""

    def __init__(self):
        pass

    def parse_compile_commands(self, compile_commands_path: Path) -> Dict[str, BuildTargetInfo]:
        """Parses a compile_commands.json file."""
        if not compile_commands_path.exists():
            return {}

        data = json.loads(compile_commands_path.read_text(encoding="utf-8"))
        targets: Dict[str, BuildTargetInfo] = {}

        for entry in data:
            file_path = entry.get("file", "")
            cmd_str = entry.get("command")
            args = entry.get("arguments")

            tokens = args if args else shlex.split(cmd_str or "")
            incs = []
            defines = []
            compiler = tokens[0] if tokens else "clang"

            idx = 1
            while idx < len(tokens):
                tok = tokens[idx]
                if tok.startswith("-I"):
                    inc_path = tok[2:] if len(tok) > 2 else (tokens[idx + 1] if idx + 1 < len(tokens) else "")
                    if inc_path:
                        incs.append(inc_path)
                elif tok.startswith("-D"):
                    d_val = tok[2:] if len(tok) > 2 else (tokens[idx + 1] if idx + 1 < len(tokens) else "")
                    if d_val:
                        defines.append(d_val)
                idx += 1

            targets[file_path] = BuildTargetInfo(
                source_file=file_path,
                include_dirs=list(set(incs)),
                defines=list(set(defines)),
                compiler=compiler,
                raw_command=cmd_str or " ".join(tokens)
            )

        return targets

    def infer_project_includes(self, project_root: Path) -> List[Path]:
        """Automatically infers include directories from standard project structures."""
        include_dirs: Set[Path] = set()
        
        # Add root
        include_dirs.add(project_root)

        # Standard C include folders
        for inc_name in ["include", "inc", "includes", "src", "source", "headers"]:
            for d in project_root.rglob(inc_name):
                if d.is_dir():
                    include_dirs.add(d)

        return sorted(list(include_dirs))
