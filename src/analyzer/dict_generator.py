"""
Automated Fuzzing Dictionary Generator for AeroHarness
Extracts string literals, magic bytes, and protocol constants into libFuzzer/AFL++ .dict format.
"""
import re
from pathlib import Path
from typing import Set, List, Dict
from pydantic import BaseModel


class FuzzingDictionary(BaseModel):
    tokens: List[str]
    dict_content: str


class DictionaryGenerator:
    """Extracts tokens and magic constants from C source and header files into a fuzzer dictionary."""

    def __init__(self):
        pass

    def generate_dictionary_from_files(self, file_paths: List[Path], output_dict_path: Path) -> FuzzingDictionary:
        """Parses files and writes a dictionary file."""
        tokens: Set[str] = set()

        for fpath in file_paths:
            if not fpath.exists():
                continue
            content = fpath.read_text(encoding="utf-8", errors="ignore")
            
            # Extract string literals: "hello", "PING", etc.
            str_literals = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', content)
            for s in str_literals:
                if 1 <= len(s) <= 32 and not s.startswith('%') and s not in [',', ';', '\n']:
                    # Escape special characters
                    escaped = s.encode('unicode_escape').decode('utf-8')
                    tokens.add(f'"{escaped}"')

            # Extract Hex defines: #define ... 0x...
            hex_defines = re.findall(r'#define\s+[A-Za-z0-9_]+\s+(0x[0-9A-Fa-f]+)', content)
            for h in hex_defines:
                raw_hex = h.replace('0x', '').replace('U', '').replace('u', '').replace('L', '').replace('l', '')
                if len(raw_hex) % 2 != 0:
                    raw_hex = '0' + raw_hex
                try:
                    bytes_val = bytes.fromhex(raw_hex)
                    hex_str = "".join([f"\\x{b:02x}" for b in bytes_val])
                    tokens.add(f'"{hex_str}"')
                except ValueError:
                    pass

        lines = [
            "# ============================================================================",
            "# AeroHarness Auto-Generated Fuzzing Dictionary",
            "# ============================================================================"
        ]
        sorted_tokens = sorted(list(tokens))
        for idx, tok in enumerate(sorted_tokens):
            lines.append(f'tok_{idx} = {tok}')

        dict_str = "\n".join(lines) + "\n"
        output_dict_path.parent.mkdir(parents=True, exist_ok=True)
        output_dict_path.write_text(dict_str, encoding="utf-8")

        return FuzzingDictionary(
            tokens=sorted_tokens,
            dict_content=dict_str
        )
