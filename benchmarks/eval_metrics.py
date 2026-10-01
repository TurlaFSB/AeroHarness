"""
Research Evaluation Metrics Calculator for AeroHarness
Computes Harness Success Rate (HSR), Convergence Rate, Coverage Gains, and TTV.
"""
from typing import List, Dict, Optional
from pydantic import BaseModel, Field


class TargetEvaluationResult(BaseModel):
    target_name: str
    target_api: str
    mode: str  # 'AeroHarness-ClosedLoop', 'SingleShot-LLM', 'Deterministic'
    compiled_successfully: bool
    smoke_test_passed: bool
    iterations_to_converge: int
    branch_coverage_pct: float
    line_coverage_pct: float
    crashed: bool
    time_to_vulnerability_sec: Optional[float] = None
    crash_type: Optional[str] = None


class BenchmarkSummary(BaseModel):
    total_targets: int = 0
    compilation_success_rate_pct: float = 0.0  # Target: >= 80%
    smoke_pass_rate_pct: float = 0.0
    avg_iterations_to_converge: float = 0.0   # Target: <= 3.5
    avg_branch_coverage_pct: float = 0.0
    avg_line_coverage_pct: float = 0.0
    vulnerabilities_discovered: int = 0
    unique_crashes: int = 0


class BenchmarkMetrics:
    """Aggregates and computes statistical metrics across benchmark runs."""

    @staticmethod
    def compute_summary(results: List[TargetEvaluationResult]) -> BenchmarkSummary:
        if not results:
            return BenchmarkSummary()

        total = len(results)
        compiled_count = sum(1 for r in results if r.compiled_successfully)
        smoke_count = sum(1 for r in results if r.smoke_test_passed)
        
        # Only compute iteration average for converged targets
        converged = [r.iterations_to_converge for r in results if r.compiled_successfully]
        avg_iter = sum(converged) / len(converged) if converged else 0.0

        avg_branch_cov = sum(r.branch_coverage_pct for r in results) / total
        avg_line_cov = sum(r.line_coverage_pct for r in results) / total
        vuln_count = sum(1 for r in results if r.crashed)
        
        unique_crashes = len(set(r.crash_type for r in results if r.crashed and r.crash_type))

        return BenchmarkSummary(
            total_targets=total,
            compilation_success_rate_pct=round((compiled_count / total) * 100, 2),
            smoke_pass_rate_pct=round((smoke_count / total) * 100, 2),
            avg_iterations_to_converge=round(avg_iter, 2),
            avg_branch_coverage_pct=round(avg_branch_cov, 2),
            avg_line_coverage_pct=round(avg_line_cov, 2),
            vulnerabilities_discovered=vuln_count,
            unique_crashes=unique_crashes
        )
