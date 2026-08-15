"""
Unit tests for Benchmark Evaluation Metrics
"""
from benchmarks.eval_metrics import BenchmarkMetrics, TargetEvaluationResult


def test_benchmark_metrics_computation():
    sample_results = [
        TargetEvaluationResult(
            target_name="Target1",
            target_api="api1",
            mode="AeroHarness-ClosedLoop",
            compiled_successfully=True,
            smoke_test_passed=True,
            iterations_to_converge=2,
            branch_coverage_pct=75.0,
            line_coverage_pct=80.0,
            crashed=True,
            crash_type="heap-buffer-overflow"
        ),
        TargetEvaluationResult(
            target_name="Target2",
            target_api="api2",
            mode="AeroHarness-ClosedLoop",
            compiled_successfully=True,
            smoke_test_passed=True,
            iterations_to_converge=1,
            branch_coverage_pct=85.0,
            line_coverage_pct=90.0,
            crashed=False
        ),
        TargetEvaluationResult(
            target_name="Target3",
            target_api="api3",
            mode="AeroHarness-ClosedLoop",
            compiled_successfully=False,
            smoke_test_passed=False,
            iterations_to_converge=5,
            branch_coverage_pct=0.0,
            line_coverage_pct=0.0,
            crashed=False
        )
    ]

    summary = BenchmarkMetrics.compute_summary(sample_results)

    assert summary.total_targets == 3
    # 2 out of 3 compiled -> 66.67%
    assert summary.compilation_success_rate_pct == 66.67
    assert summary.vulnerabilities_discovered == 1
    assert summary.avg_iterations_to_converge == 1.5  # (2 + 1) / 2
