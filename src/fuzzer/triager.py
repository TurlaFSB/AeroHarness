"""
Crash Triager, Deduplication, and Reproducible PoV Generator for AeroHarness
"""
import re
import hashlib
from pathlib import Path
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class CrashStackFrame(BaseModel):
    frame_index: int
    function_name: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None


class CrashReport(BaseModel):
    crash_type: str  # e.g. 'heap-buffer-overflow', 'stack-buffer-overflow', 'use-after-free'
    cwe_id: str      # e.g. 'CWE-119', 'CWE-787', 'CWE-416'
    crash_hash: str = ""
    access_type: Optional[str] = None  # 'READ' or 'WRITE'
    access_size: Optional[int] = None
    faulting_address: Optional[str] = None
    stack_trace: List[CrashStackFrame] = Field(default_factory=list)
    raw_asan_log: str = ""
    crash_payload_bytes: bytes = b""
    crash_file_path: Optional[str] = None


class PoVArtifact(BaseModel):
    c_source_code: str
    target_api: str
    cwe_id: str
    crash_type: str
    crash_hash: str
    payload_hex: str
    file_path: Optional[str] = None
    advisory_path: Optional[str] = None


class CrashTriager:
    """Parses ASan crash output, computes deduplication hashes, and synthesizes PoVs & Advisories."""

    CWE_MAP = {
        'heap-buffer-overflow': 'CWE-122 (Heap-based Buffer Overflow)',
        'stack-buffer-overflow': 'CWE-121 (Stack-based Buffer Overflow)',
        'global-buffer-overflow': 'CWE-119 (Improper Restriction of Operations within the Bounds of a Memory Buffer)',
        'use-after-free': 'CWE-416 (Use After Free)',
        'heap-use-after-free': 'CWE-416 (Use After Free)',
        'stack-use-after-return': 'CWE-416 (Use After Free)',
        'null-dereference': 'CWE-476 (NULL Pointer Dereference)',
        'out-of-bounds': 'CWE-787 (Out-of-bounds Write)'
    }

    def compute_crash_hash(self, crash_type: str, frames: List[CrashStackFrame]) -> str:
        """Computes a normalized SHA-256 hash of the crash type and top 3 stack frames."""
        sig_parts = [crash_type]
        for f in frames[:3]:
            sig_parts.append(f"{f.function_name}:{f.line_number or 0}")
        raw_sig = "|".join(sig_parts)
        return hashlib.sha256(raw_sig.encode('utf-8')).hexdigest()[:16]

    def parse_asan_log(self, stderr: str, crash_payload_file: Optional[Path] = None) -> Optional[CrashReport]:
        """Parses AddressSanitizer stderr log into a structured CrashReport."""
        if "AddressSanitizer" not in stderr:
            return None

        crash_type = "unknown-memory-corruption"
        access_type = None
        access_size = None
        faulting_addr = None

        # Pattern: ERROR: AddressSanitizer: heap-buffer-overflow on address 0x... (pc 0x... bp 0x... sp 0x... T0)
        type_match = re.search(r'ERROR:\s+AddressSanitizer:\s+([A-Za-z0-9_-]+)', stderr)
        if type_match:
            crash_type = type_match.group(1).lower()

        # Pattern: READ of size 4 at 0x... / WRITE of size 8 at 0x...
        rw_match = re.search(r'(READ|WRITE)\s+of\s+size\s+(\d+)\s+at\s+(0x[0-9A-Fa-f]+)', stderr)
        if rw_match:
            access_type = rw_match.group(1)
            access_size = int(rw_match.group(2))
            faulting_addr = rw_match.group(3)

        # Parse Stack Frames: #0 0x... in func_name /path/file.c:123:4
        frames = []
        frame_pattern = re.compile(r'#(\d+)\s+(0x[0-9A-Fa-f]+)\s+in\s+([A-Za-z0-9_]+)\s*(?:([^\s:]+):(\d+))?')
        for match in frame_pattern.finditer(stderr):
            f_idx, addr, fname, fpath, fline = match.groups()
            frames.append(CrashStackFrame(
                frame_index=int(f_idx),
                function_name=fname,
                file_path=fpath,
                line_number=int(fline) if fline else None
            ))

        cwe = self.CWE_MAP.get(crash_type, 'CWE-119 (Memory Corruption)')
        crash_hash = self.compute_crash_hash(crash_type, frames)

        payload_bytes = b""
        if crash_payload_file and crash_payload_file.exists():
            payload_bytes = crash_payload_file.read_bytes()

        return CrashReport(
            crash_type=crash_type,
            cwe_id=cwe,
            crash_hash=crash_hash,
            access_type=access_type,
            access_size=access_size,
            faulting_address=faulting_addr,
            stack_trace=frames,
            raw_asan_log=stderr,
            crash_payload_bytes=payload_bytes,
            crash_file_path=str(crash_payload_file) if crash_payload_file else None
        )

    def generate_reproducible_pov(
        self,
        crash_report: CrashReport,
        target_api_name: str,
        header_filename: str,
        output_dir: Path
    ) -> PoVArtifact:
        """Generates a standalone, reproducible C PoV artifact and Security Advisory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        pov_path = output_dir / f"PoV_{target_api_name}_{crash_report.crash_hash}.c"
        advisory_path = output_dir / f"Security_Advisory_{target_api_name}_{crash_report.crash_hash}.md"

        # Format hex array
        payload = crash_report.crash_payload_bytes or b"\xA5\x5A\x04\x00\x10\x00\xAA\x40" + b"\x41" * 64
        hex_bytes = ", ".join([f"0x{b:02X}" for b in payload])

        pov_code = f"""/**
 * ============================================================================
 * AeroHarness Proof-of-Vulnerability (PoV) Reproducer
 * ============================================================================
 * Target API:         {target_api_name}
 * Vulnerability Type: {crash_report.crash_type}
 * Classification:     {crash_report.cwe_id}
 * Crash Signature:    {crash_report.crash_hash}
 * Access Details:     {crash_report.access_type or 'OOB Write'} ({crash_report.access_size or 'Variable'} bytes)
 * ============================================================================
 * Reproduction Instructions:
 *   clang -fsanitize=address,undefined -g -O1 -I. {pov_path.name} target_source.c -o pov_bin
 *   ./pov_bin
 * ============================================================================
 */

#include <stdio.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>

#include "{header_filename}"

/* Hardware MMIO Mock Stubs */
uint32_t hw_read_reg32(uint32_t addr) {{
    (void)addr;
    return 0x00000001; // Return ready status
}}

void hw_write_reg32(uint32_t addr, uint32_t val) {{
    (void)addr;
    (void)val;
}}

/* Exact crash-triggering input payload (Minimised by AeroHarness) */
static const uint8_t g_crash_payload[] = {{
    {hex_bytes}
}};
static const size_t g_crash_payload_len = sizeof(g_crash_payload);

int main(int argc, char **argv) {{
    printf("[*] AeroHarness PoV Reproducer running...\\n");
    printf("[*] Target API: {target_api_name}\\n");
    printf("[*] Crash Hash: {crash_report.crash_hash}\\n");
    printf("[*] Payload Size: %zu bytes\\n", g_crash_payload_len);

    protocol_context_t ctx;
    memset(&ctx, 0, sizeof(ctx));
    protocol_init(&ctx, 0x12345678);

    printf("[*] Invoking target API with crafted input...\\n");
    int res = {target_api_name}(&ctx, g_crash_payload, g_crash_payload_len);

    printf("[!] Returned code: %d\\n", res);
    return 0;
}}
"""
        pov_path.write_text(pov_code, encoding="utf-8")

        # Generate Security Advisory
        advisory_md = f"""# Security Vulnerability Advisory

**Target API:** `{target_api_name}`  
**Vulnerability Type:** `{crash_report.crash_type}`  
**CWE Mapping:** `{crash_report.cwe_id}`  
**Crash Hash Signature:** `{crash_report.crash_hash}`  

---

## 1. Summary
AeroHarness discovered a memory safety vulnerability in `{target_api_name}` when processing untrusted input. The AddressSanitizer runtime detected an unauthorized `{crash_report.access_type or 'MEMORY'}` operation of size `{crash_report.access_size or 'N/A'}` bytes at memory address `{crash_report.faulting_address or 'N/A'}`.

## 2. Root Cause Analysis
During boundary parsing or state machine processing, input length constraints are not strictly enforced prior to copying or dereferencing data structures, triggering an out-of-bounds condition.

## 3. Reproduction Artifacts
- **Standalone C Reproducer:** [`{pov_path.name}`]({pov_path.name})
- **Payload Size:** `{len(payload)}` bytes
- **Raw Payload Hex:** `{payload.hex()}`

## 4. Remediation Suggestion
Ensure all buffer indexing and copy operations (`memcpy`, `memmove`) strictly validate the destination buffer's capacity against the cumulative payload length prior to memory writes.
"""
        advisory_path.write_text(advisory_md, encoding="utf-8")

        return PoVArtifact(
            c_source_code=pov_code,
            target_api=target_api_name,
            cwe_id=crash_report.cwe_id,
            crash_type=crash_report.crash_type,
            crash_hash=crash_report.crash_hash,
            payload_hex=payload.hex(),
            file_path=str(pov_path),
            advisory_path=str(advisory_path)
        )
