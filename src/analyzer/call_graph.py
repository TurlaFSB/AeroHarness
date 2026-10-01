"""
Call Graph and API Risk Ranking Module for AeroHarness
Identifies risky memory operations, hardware interaction points, and ranks target APIs.
"""
import re
from pathlib import Path
from typing import Dict, List, Set, Optional
from pydantic import BaseModel, Field


class MemoryOperation(BaseModel):
    op_type: str  # e.g., 'memcpy', 'strcpy', 'pointer_arithmetic', 'array_write'
    line_number: int
    raw_snippet: str


class APIRiskScore(BaseModel):
    api_name: str
    risk_score: float
    cyclomatic_complexity: int
    memory_operations: List[MemoryOperation] = Field(default_factory=list)
    calls_mmio: bool = False
    callees: List[str] = Field(default_factory=list)
    justification: str = ""


class CallGraphBuilder:
    """Builds call relationships and analyzes risk factors for embedded C code."""

    DANGEROUS_MEM_FUNCS = {
        'memcpy': 4.0,
        'memmove': 3.5,
        'strcpy': 5.0,
        'strncpy': 2.5,
        'strcat': 4.5,
        'sprintf': 4.0,
        'vsprintf': 4.0,
        'gets': 10.0
    }

    MMIO_PATTERNS = [
        r'hw_read_', r'hw_write_', r'readl', r'writel', r'sys_in', r'sys_out',
        r'sys_read', r'sys_write', r'MMIO_'
    ]

    def __init__(self):
        pass

    def analyze_source_file(self, c_source_path: Path, known_apis: List[str]) -> Dict[str, APIRiskScore]:
        """Analyzes a .c source file and calculates risk scores for known APIs."""
        content = c_source_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()

        # Simple function body segmentation
        func_bodies = self._extract_function_bodies(content, known_apis)
        scores: Dict[str, APIRiskScore] = {}

        for api_name, (start_line, body) in func_bodies.items():
            complexity = self._calculate_cyclomatic_complexity(body)
            mem_ops = self._find_memory_operations(body, start_line)
            has_mmio = self._check_mmio_interactions(body)
            callees = self._extract_callees(body, known_apis, api_name)

            # Calculate composite risk score
            # Score = (Complexity * 0.5) + sum(MemOpWeights) + (10 if MMIO else 0) + (5 if buffer param)
            mem_score = sum(self.DANGEROUS_MEM_FUNCS.get(op.op_type, 2.0) for op in mem_ops)
            raw_score = (complexity * 0.4) + mem_score + (3.0 if has_mmio else 0.0)

            justification_parts = []
            if mem_ops:
                justification_parts.append(f"{len(mem_ops)} memory operations ({', '.join(set(o.op_type for o in mem_ops))})")
            if has_mmio:
                justification_parts.append("Direct MMIO/hardware register interactions")
            if complexity > 5:
                justification_parts.append(f"High branching complexity ({complexity})")

            scores[api_name] = APIRiskScore(
                api_name=api_name,
                risk_score=round(raw_score, 2),
                cyclomatic_complexity=complexity,
                memory_operations=mem_ops,
                calls_mmio=has_mmio,
                callees=callees,
                justification="; ".join(justification_parts) if justification_parts else "Standard logic"
            )

        return scores

    def _extract_function_bodies(self, content: str, known_apis: List[str]) -> Dict[str, tuple]:
        """Extracts function boundaries and bodies."""
        bodies = {}
        lines = content.splitlines()
        
        for api in known_apis:
            pattern = re.compile(r'^[A-Za-z0-9_\s\*]+?\s+' + re.escape(api) + r'\s*\([^)]*\)\s*\{', re.MULTILINE)
            match = pattern.search(content)
            if match:
                start_pos = match.start()
                start_line = content[:start_pos].count('\n') + 1
                # Find matching closing brace
                open_brace_idx = content.find('{', start_pos)
                if open_brace_idx != -1:
                    depth = 1
                    idx = open_brace_idx + 1
                    while idx < len(content) and depth > 0:
                        if content[idx] == '{':
                            depth += 1
                        elif content[idx] == '}':
                            depth -= 1
                        idx += 1
                    body = content[open_brace_idx:idx]
                    bodies[api] = (start_line, body)
        return bodies

    def _calculate_cyclomatic_complexity(self, body: str) -> int:
        """Estimates cyclomatic complexity based on branching keywords."""
        branch_keywords = [r'\bif\b', r'\bwhile\b', r'\bfor\b', r'\bcase\b', r'\bcatch\b', r'\?', r'&&', r'\|\|']
        count = 1
        for kw in branch_keywords:
            count += len(re.findall(kw, body))
        return count

    def _find_memory_operations(self, body: str, start_line: int) -> List[MemoryOperation]:
        """Detects dangerous memory operations inside a function body."""
        ops = []
        body_lines = body.splitlines()
        for idx, line in enumerate(body_lines):
            line_no = start_line + idx
            for func_name in self.DANGEROUS_MEM_FUNCS:
                if re.search(r'\b' + func_name + r'\s*\(', line):
                    ops.append(MemoryOperation(
                        op_type=func_name,
                        line_number=line_no,
                        raw_snippet=line.strip()
                    ))
            # Detect raw pointer arithmetic or array offset indexing
            if re.search(r'\[[^\]]+\]\s*=', line):
                ops.append(MemoryOperation(
                    op_type='array_write',
                    line_number=line_no,
                    raw_snippet=line.strip()
                ))
        return ops

    def _check_mmio_interactions(self, body: str) -> bool:
        """Checks if function body touches hardware MMIO routines."""
        for pattern in self.MMIO_PATTERNS:
            if re.search(pattern, body):
                return True
        return False

    def _extract_callees(self, body: str, known_apis: List[str], current_api: str) -> List[str]:
        """Finds calls to other known functions."""
        callees = []
        for other in known_apis:
            if other != current_api and re.search(r'\b' + re.escape(other) + r'\s*\(', body):
                callees.append(other)
        return callees
