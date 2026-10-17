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
    def compile_harness(self, **kw): return SimpleNamespace(success=True, diagnostics=[], stderr="")


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
