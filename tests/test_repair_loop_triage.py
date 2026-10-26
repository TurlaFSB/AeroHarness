"""Offline orchestrator tests with stub agent/oracles (no compiler, model or network)."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.oracle.repair_loop import SelfRepairOrchestrator
from src.oracle.smoke_test import SmokeTestResult

T = "/w/targets/pl011_set_baudrate.c"
TARGET_CRASH = SmokeTestResult(
    passed=False, crashed=True, timed_out=False, exit_code=77,
    crash_reason=f"{T}:28:17: runtime error: division by zero",
    stderr=f"{T}:28:17: runtime error: division by zero\n")


class Agent:
    def __init__(self): self.repairs = 0
    def synthesize_initial_harness(self, **kw): return SimpleNamespace(code="v0", model_used="m")
    def repair_harness(self, candidate, **kw):
        self.repairs += 1
        return SimpleNamespace(code=f"v{self.repairs}", model_used="m")
    def _apply_deterministic_fix(self, code, err): return code


class Comp:
    def compile_harness(self, **kw):
        kw["output_binary_path"].write_text("bin")
        return SimpleNamespace(success=True, diagnostics=[], stderr="")


class Smoke:
    """First `bad` calls (any kind) crash; afterwards pass. Records call kwargs."""
    def __init__(self, bad, gate_bad=0):
        self.bad, self.gate_bad, self.calls = bad, gate_bad, []
    def run_smoke_test(self, binary, runs=100, **kw):
        self.calls.append((runs, kw))
        if str(binary).endswith("_wrap"):
            return SmokeTestResult(passed=True, crashed=False, timed_out=False,
                                   stderr=f"{T}:28:29: runtime error: unsigned integer overflow: 5 * 16\n")
        is_gate = "max_total_time" in kw
        if is_gate and self.gate_bad > 0:
            self.gate_bad -= 1
            return TARGET_CRASH
        if not is_gate and self.bad > 0:
            self.bad -= 1
            return TARGET_CRASH
        return SmokeTestResult(passed=True, crashed=False, timed_out=False)


def run(tmp_path, smoke, **kw):
    agent = Agent()
    orch = SelfRepairOrchestrator(agent=agent, compiler_oracle=Comp(), smoke_oracle=smoke,
                                  max_iterations=5, **kw)
    out = orch.run_synthesis_and_repair(
        header_context=None, target_api=SimpleNamespace(name="pl011_set_baudrate"),
        risk_score=None, header_path=Path("/w/targets/pl011_set_baudrate.h"),
        target_c_files=[Path(T)], include_dirs=[], output_dir=tmp_path)
    return out, agent


def test_off_is_legacy_repairs_and_succeeds(tmp_path):
    out, agent = run(tmp_path, Smoke(bad=1))
    assert out.success and agent.repairs == 1
    assert out.candidate_findings == [] and out.triage_policy == "off"
    assert not (tmp_path / "crashes").exists()           # no side effects when off


def test_record_keeps_finding_and_marks_masked(tmp_path):
    smoke = Smoke(bad=1)
    out, agent = run(tmp_path, smoke, crash_triage="record")
    assert out.success and agent.repairs == 1            # loop unchanged
    assert len(out.candidate_findings) == 1
    f = out.candidate_findings[0]
    assert f.site_line == 28 and f.masked_by_repair is True
    assert "artifact_prefix" in smoke.calls[0][1]


def test_halt_stops_without_repair(tmp_path):
    out, agent = run(tmp_path, Smoke(bad=1), crash_triage="halt")
    assert not out.success and out.halted_on_finding and agent.repairs == 0
    assert out.failure_reason.startswith("CANDIDATE_FINDING")
    assert out.candidate_findings[0].masked_by_repair is False


def test_stability_gate_catches_failure_after_smoke_pass(tmp_path):
    smoke = Smoke(bad=0, gate_bad=1)
    out, agent = run(tmp_path, smoke, crash_triage="record", stability_runs=100000)
    assert out.success and agent.repairs == 1
    assert out.history[0].stage == "STABILITY_GATE"
    assert out.candidate_findings[0].stage == "STABILITY_GATE"
    assert out.candidate_findings[0].masked_by_repair is True
    assert any(k.get("max_total_time") == 60 and r == 100000 for r, k in smoke.calls)


def test_stability_without_triage_still_gates(tmp_path):
    out, agent = run(tmp_path, Smoke(bad=0, gate_bad=1), stability_runs=1000)
    assert out.success and agent.repairs == 1 and out.candidate_findings == []


def test_invalid_policy_rejected():
    with pytest.raises(ValueError):
        SelfRepairOrchestrator(agent=Agent(), compiler_oracle=Comp(), smoke_oracle=Smoke(0),
                               crash_triage="bogus")


def test_wrap_probe_is_record_only_and_not_masked(tmp_path):
    smoke = Smoke(bad=0)
    out, agent = run(tmp_path, smoke, wrap_probe_runs=20000)
    assert out.success and agent.repairs == 0
    assert [f.stage for f in out.candidate_findings] == ["WRAP_PROBE"]
    assert out.candidate_findings[0].masked_by_repair is None
    assert out.wrap_probe_runs == 20000


# ---- coverage feedback ------------------------------------------------------------------
from src.oracle.coverage_oracle import CoverageResult


class CovOracle:
    """Returns the queued results in order; records calls."""
    def __init__(self, *results): self.results, self.calls = list(results), 0
    def measure(self, *a, **k):
        self.calls += 1
        return self.results.pop(0)


def cov(covered, total=22, unc=None):
    return CoverageResult(ok=True, covered=covered, total=total,
                          uncovered_lines={T: unc if unc is not None else [38, 39]})


class CovAgent(Agent):
    def __init__(self, new_code="v_cov"): super().__init__(); self.new_code, self.cov_calls = new_code, 0
    def improve_coverage(self, candidate, **kw):
        self.cov_calls += 1
        return SimpleNamespace(code=self.new_code, model_used="m", iteration=getattr(candidate, "iteration", 0) + 1,
                               history=[])


def run_cov(tmp_path, cov_oracle, agent=None, smoke=None, **kw):
    agent = agent or CovAgent()
    # the real target source is read to mark lines; give it something
    Path(T).parent.mkdir(parents=True, exist_ok=True)
    Path(T).write_text("int x;\n" * 60)
    orch = SelfRepairOrchestrator(agent=agent, compiler_oracle=Comp(), smoke_oracle=smoke or Smoke(bad=0),
                                  max_iterations=5, coverage_oracle=cov_oracle, **kw)
    out = orch.run_synthesis_and_repair(
        header_context=None, target_api=SimpleNamespace(name="pl011_set_baudrate"),
        risk_score=None, header_path=Path("/w/targets/pl011_set_baudrate.h"),
        target_c_files=[Path(T)], include_dirs=[], output_dir=tmp_path)
    return out, agent


def test_coverage_feedback_off_by_default(tmp_path):
    co = CovOracle()
    out, agent = run_cov(tmp_path, co)
    assert out.coverage_feedback is None and co.calls == 0 and agent.cov_calls == 0


def test_coverage_above_threshold_makes_no_model_call(tmp_path):
    out, agent = run_cov(tmp_path, CovOracle(cov(21)), coverage_feedback_min=0.9)
    assert agent.cov_calls == 0 and out.coverage_feedback["skipped_reason"].startswith("coverage at or")


def test_coverage_improvement_is_accepted_and_replaces_files(tmp_path):
    (tmp_path).mkdir(exist_ok=True)
    out, agent = run_cov(tmp_path, CovOracle(cov(11), cov(20, unc=[40])), coverage_feedback_min=0.9)
    assert out.coverage_feedback["accepted"] and agent.cov_calls == 1
    assert out.final_harness_code == "v_cov"
    assert (tmp_path / "fuzz_pl011_set_baudrate.cpp").read_text() == "v_cov"


def test_coverage_not_better_is_rejected_and_original_kept(tmp_path):
    out, agent = run_cov(tmp_path, CovOracle(cov(11), cov(11)), coverage_feedback_min=0.9)
    assert not out.coverage_feedback["accepted"] and out.final_harness_code == "v0"
    assert "did not cover more" in out.coverage_feedback["reject_reason"]
    assert out.success


def test_coverage_round_failing_smoke_is_rejected(tmp_path):
    class S(Smoke):
        def run_smoke_test(self, binary, runs=100, **kw):
            if str(binary).endswith("_covfb"):
                return TARGET_CRASH
            return super().run_smoke_test(binary, runs, **kw)
    out, agent = run_cov(tmp_path, CovOracle(cov(11)), smoke=S(bad=0),
                         coverage_feedback_min=0.9, crash_triage="record")
    assert not out.coverage_feedback["accepted"] and out.final_harness_code == "v0"
    assert out.success
    assert [f.stage for f in out.candidate_findings] == ["COVERAGE_FEEDBACK"]


def test_coverage_measure_error_is_skipped_not_fatal(tmp_path):
    out, agent = run_cov(tmp_path, CovOracle(CoverageResult(ok=False, error="clang missing")),
                         coverage_feedback_min=0.9)
    assert out.success and agent.cov_calls == 0 and out.coverage_feedback["skipped_reason"] == "clang missing"


def test_escalate_after_two_same_site_crashes_halts_early(tmp_path):
    out, agent = run(tmp_path, Smoke(bad=99), crash_triage="record", escalate_after=2)
    assert out.halted_on_finding and not out.success
    assert out.total_iterations == 2 and agent.repairs == 1
    assert "same location crashed 2 times" in out.failure_reason
    assert all(f.masked_by_repair is False for f in out.candidate_findings)


def test_without_escalation_record_runs_all_iterations(tmp_path):
    out, agent = run(tmp_path, Smoke(bad=99), crash_triage="record")
    assert not out.success and not out.halted_on_finding and out.total_iterations == 5
