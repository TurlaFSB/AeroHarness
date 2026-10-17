"""
Closed-Loop Self-Repair Orchestrator for AeroHarness.

Rebuilt from scratch, Oct 2026 (see FAILURE_TAXONOMY.md). `src/oracle/repair_loop.py` was
imported by `run.py` and re-exported from `src/oracle/__init__.py` and `src/cli/console.py`
(`display_repair_outcome(outcome: RepairOutcome)`), but did not exist anywhere in the
repository's git history -- confirmed via a direct `ModuleNotFoundError` on `run.py synthesize`
and via `git log --all --oneline -- src/oracle` showing only the repo's first commit (which
added `compiler_oracle.py`/`smoke_test.py`/`__init__.py`, never this file). This has been broken
since day one and was never previously disclosed in any project document.

This is a new, independent implementation of the exact class/field contract already fixed by
three real, working consumers (`run.py`'s `synthesize`/`run_all` commands,
`src/cli/console.py::display_repair_outcome`, and `src/oracle/__init__.py`'s re-export list),
written directly against the real `CompilerOracle`/`SmokeTestOracle`/`HarnessSynthesizerAgent`
classes already present and working in this repo -- not copied from `legacy_v1/repair_loop.py`,
which that directory's own README already flags as containing fabricated/stubbed components.
`legacy_v1/repair_loop.py` was read for interface shape only (confirming field names already
implied by `run.py` and `console.py`); its control flow was independently re-derived here, not
transcribed.

Verification status (Oct 2026): before being used for any work-plan item 2 data generation,
this module was exercised end-to-end against a known-good existing target
(`pl011_poll_in`/`pl011_poll_out`) to confirm it actually drives a real synthesis -> compile ->
smoke-test -> repair loop rather than merely importing cleanly. See RESULTS.md for that
verification run's outcome before trusting any subsequent data this module produces.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from config.settings import get_settings
from src.analyzer.c_ast_extractor import ExtractedHeaderContext, FunctionSignature
from src.analyzer.call_graph import APIRiskScore
from src.synthesizer.agent import HarnessSynthesizerAgent, SynthesisCandidate

from .compiler_oracle import CompilationResult, CompilerOracle
from .crash_triage import (
    CrashFinding,
    CrashVerdict,
    evidence_excerpt,
    target_path_set,
    target_side_ubsan,
    triage_crash,
)
from .smoke_test import SmokeTestOracle, SmokeTestResult

TRIAGE_POLICIES = ("off", "record", "halt")


class RepairIteration(BaseModel):
    """One round of the loop: which oracle ran, whether it passed, and why not."""

    iteration: int
    stage: str  # 'COMPILATION_ORACLE' | 'SMOKE_TEST_ORACLE' | 'STABILITY_GATE' | 'SUCCESS'
    passed: bool
    diagnostics: List[Dict[str, Any]] = Field(default_factory=list)
    raw_error: str = ""


class RepairOutcome(BaseModel):
    """
    Final result of a `run_synthesis_and_repair` call. Field names and semantics are fixed
    by existing callers: `run.py` checks `.success`/`.binary_path` before proceeding to
    fuzzing, and `src/cli/console.py::display_repair_outcome` reads `.target_api`,
    `.success`, `.total_iterations`, `.harness_file_path`, `.binary_path`, and
    `.failure_reason`.
    """

    success: bool
    target_api: str
    final_harness_code: str
    harness_file_path: Optional[str] = None
    binary_path: Optional[str] = None
    total_iterations: int = 0
    history: List[RepairIteration] = Field(default_factory=list)
    failure_reason: Optional[str] = None
    # Crash triage (optional; defaults reproduce the original protocol exactly).
    triage_policy: str = "off"
    stability_runs: int = 0
    wrap_probe_runs: int = 0
    candidate_findings: List[CrashFinding] = Field(default_factory=list)
    halted_on_finding: bool = False


class SelfRepairOrchestrator:
    """
    Drives the closed feedback loop: ask the synthesis agent for a candidate harness, run it
    through two independent, real, deterministic verification oracles (compile with
    Clang/ASan/UBSan, then execute a smoke-test campaign), and if either oracle fails, feed
    its concrete diagnostics back to the agent for a repair attempt -- up to
    `max_iterations` times.

    Neither oracle is mocked or simulated by this class: `CompilerOracle.compile_harness`
    actually invokes `clang++` as a subprocess, and `SmokeTestOracle.run_smoke_test` actually
    executes the resulting binary. A harness only counts as `success=True` if both real
    checks pass on the same iteration.
    """

    def __init__(
        self,
        agent: Optional[HarnessSynthesizerAgent] = None,
        compiler_oracle: Optional[CompilerOracle] = None,
        smoke_oracle: Optional[SmokeTestOracle] = None,
        max_iterations: Optional[int] = None,
        crash_triage: str = "off",
        stability_runs: int = 0,
        stability_max_time_sec: int = 60,
        wrap_probe_runs: int = 0,
    ):
        """
        ``crash_triage`` (default ``off`` = the protocol behind the reported 18/18 result):
          * ``off``    every runtime failure is a harness defect and is sent to the model.
          * ``record`` runtime failures whose deciding source location is in the code under
                       test are recorded as candidate findings (with the crashing input), the
                       loop is otherwise unchanged; each finding is later marked
                       ``masked_by_repair`` if the loop still ended in a passing harness.
          * ``halt``   as ``record`` but the loop stops at the first such failure
                       (``halted_on_finding``) instead of editing the harness around it.
        ``stability_runs`` > 0 adds a second, longer campaign after the smoke test passes
        (``stability_max_time_sec`` wall-clock cap). Its failures are repaired/triaged like
        smoke failures, so a harness only succeeds if it also survives that campaign.
        ``wrap_probe_runs`` > 0 adds a record-only probe on a final passing harness: a second
        build with ``-fsanitize=unsigned-integer-overflow`` is run for that many executions and
        wrap reports located in the code under test are kept as candidate findings. It never
        changes success or triggers repair (unsigned wrap is defined C behaviour and is
        sometimes intended).
        """
        if crash_triage not in TRIAGE_POLICIES:
            raise ValueError(f"crash_triage must be one of {TRIAGE_POLICIES}, got {crash_triage!r}")
        self.crash_triage = crash_triage
        self.stability_runs = max(0, int(stability_runs))
        self.stability_max_time_sec = stability_max_time_sec
        self.wrap_probe_runs = max(0, int(wrap_probe_runs))
        self.settings = get_settings()
        self.agent = agent or HarnessSynthesizerAgent()
        self.compiler = compiler_oracle or CompilerOracle()
        self.smoke_oracle = smoke_oracle or SmokeTestOracle()
        self.max_iterations = max_iterations or self.settings.max_repair_iterations

    def run_synthesis_and_repair(
        self,
        header_context: ExtractedHeaderContext,
        target_api: FunctionSignature,
        risk_score: Optional[APIRiskScore],
        header_path: Path,
        target_c_files: List[Path],
        include_dirs: List[Path],
        output_dir: Path,
        externally_linked: bool = False,
        mmio_convention_note: Optional[str] = None,
    ) -> RepairOutcome:
        """
        Runs the full closed-loop workflow for one target API and returns a `RepairOutcome`
        describing whether a harness that compiles, links, and survives the smoke-test
        oracle was ever produced, and the full per-iteration history either way (used by
        work-plan item 2's statistical analysis of iteration counts).

        `externally_linked` (added Oct 2 2026, item 2): pass True when `target_api` is a
        real function being supplied via `target_c_files` rather than something the model
        should define itself -- see `PromptFactory.build_synthesis_prompt`'s docstring for
        why this matters for real driver-style targets (e.g. the Zephyr `uart_pl011.c`
        functions) as opposed to the toy, header-declared, externally-linked
        `protocol_process_frame`-style targets this flag happens not to be needed for.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        harness_src_path = output_dir / f"fuzz_{target_api.name}.cpp"
        out_binary_path = output_dir / f"fuzz_{target_api.name}_bin"

        history: List[RepairIteration] = []

        candidate = self.agent.synthesize_initial_harness(
            header_context=header_context,
            target_api=target_api,
            risk_score=risk_score,
            header_filename=header_path.name,
            externally_linked=externally_linked,
            mmio_convention_note=mmio_convention_note,
        )

        last_comp_res: Optional[CompilationResult] = None
        last_smoke_res: Optional[SmokeTestResult] = None

        consecutive_timeouts = 0
        findings: List[CrashFinding] = []
        triage_on = self.crash_triage != "off"
        target_paths = target_path_set(target_c_files, header_path)
        crash_root = output_dir / "crashes"

        def _finish(outcome: RepairOutcome) -> RepairOutcome:
            for f in findings:
                if f.stage == "WRAP_PROBE":
                    continue  # observed on the final harness; nothing was repaired away
                f.masked_by_repair = bool(outcome.success) and not outcome.halted_on_finding
            outcome.triage_policy = self.crash_triage
            outcome.stability_runs = self.stability_runs
            outcome.wrap_probe_runs = self.wrap_probe_runs
            outcome.candidate_findings = findings
            return outcome

        for iteration in range(1, self.max_iterations + 1):
            harness_src_path.write_text(candidate.code, encoding="utf-8")

            comp_res = self.compiler.compile_harness(
                harness_src_path=harness_src_path,
                target_c_files=target_c_files,
                include_dirs=include_dirs,
                output_binary_path=out_binary_path,
            )
            last_comp_res = comp_res

            if not comp_res.success:
                diag_dicts = [d.model_dump() for d in comp_res.diagnostics]
                history.append(
                    RepairIteration(
                        iteration=iteration,
                        stage="COMPILATION_ORACLE",
                        passed=False,
                        diagnostics=diag_dicts,
                        raw_error=comp_res.stderr,
                    )
                )
                if iteration >= self.max_iterations:
                    break

                # Cost-reduction optimization: Attempt deterministic rule-based fix first to save LLM tokens
                deterministic_fixed = self.agent._apply_deterministic_fix(candidate.code, comp_res.stderr)
                if deterministic_fixed != candidate.code:
                    harness_src_path.write_text(deterministic_fixed, encoding="utf-8")
                    test_comp = self.compiler.compile_harness(
                        harness_src_path=harness_src_path,
                        target_c_files=target_c_files,
                        include_dirs=include_dirs,
                        output_binary_path=out_binary_path,
                    )
                    if test_comp.success:
                        candidate.code = deterministic_fixed
                        candidate.model_used = "deterministic-rule-fixer"
                        last_comp_res = test_comp
                        # Successfully patched compile error without spending LLM tokens!
                    else:
                        harness_src_path.write_text(candidate.code, encoding="utf-8")
                        candidate = self.agent.repair_harness(
                            candidate=candidate,
                            error_type="COMPILATION_ERROR",
                            error_message=comp_res.stderr,
                            diagnostics=diag_dicts,
                        )
                        continue
                else:
                    candidate = self.agent.repair_harness(
                        candidate=candidate,
                        error_type="COMPILATION_ERROR",
                        error_message=comp_res.stderr,
                        diagnostics=diag_dicts,
                    )
                    continue

            iter_crash_dir = crash_root / f"iter{iteration}"
            smoke_kwargs = {}
            if triage_on:
                iter_crash_dir.mkdir(parents=True, exist_ok=True)
                smoke_kwargs["artifact_prefix"] = iter_crash_dir
            smoke_res = self.smoke_oracle.run_smoke_test(
                out_binary_path, runs=self.settings.smoke_test_runs, **smoke_kwargs
            )
            stage = "SMOKE_TEST_ORACLE"
            if smoke_res.passed and self.stability_runs > 0:
                gate_res = self.smoke_oracle.run_smoke_test(
                    out_binary_path,
                    runs=self.stability_runs,
                    max_total_time=self.stability_max_time_sec,
                    timeout_sec=self.stability_max_time_sec + 60,
                    **smoke_kwargs,
                )
                if not gate_res.passed:
                    smoke_res, stage = gate_res, "STABILITY_GATE"
            last_smoke_res = smoke_res

            if smoke_res.passed and triage_on:
                # UBSan runs in recover mode: a target-side report on a *passing* run is
                # invisible to the legacy loop. Keep it as evidence, never as a failure.
                for u in target_side_ubsan(smoke_res.stderr, target_paths)[:3]:
                    findings.append(CrashFinding(
                        iteration=iteration, stage=stage, verdict=CrashVerdict.TARGET_SIDE,
                        site_file=u.file, site_line=u.line, site_col=u.col,
                        message=f"non-fatal UBSan report: {u.message}",
                        evidence_excerpt=evidence_excerpt(smoke_res.stderr, 12)))

            if not smoke_res.passed:
                crash_reason = smoke_res.crash_reason or smoke_res.stderr
                if triage_on and smoke_res.crashed:
                    tri = triage_crash(smoke_res.stderr, harness_src_path, target_paths)
                    if tri.verdict == CrashVerdict.TARGET_SIDE and tri.site is not None:
                        repro = sorted(iter_crash_dir.glob("crash-*"), key=lambda q: q.stat().st_mtime)
                        findings.append(CrashFinding(
                            iteration=iteration, stage=stage, verdict=tri.verdict,
                            site_file=tri.site.file, site_line=tri.site.line,
                            site_col=tri.site.col, site_function=tri.site.function,
                            message=crash_reason,
                            reproducer_path=str(repro[-1]) if repro else None,
                            evidence_excerpt=evidence_excerpt(smoke_res.stderr)))
                        if self.crash_triage == "halt":
                            history.append(RepairIteration(
                                iteration=iteration, stage=stage, passed=False,
                                diagnostics=[], raw_error=crash_reason))
                            return _finish(RepairOutcome(
                                success=False,
                                target_api=target_api.name,
                                final_harness_code=candidate.code,
                                harness_file_path=str(harness_src_path),
                                binary_path=None,
                                total_iterations=iteration,
                                history=history,
                                failure_reason=(
                                    "CANDIDATE_FINDING: crash located in the code under test "
                                    f"({tri.site.file}:{tri.site.line}); loop halted instead of "
                                    f"repairing the harness around it ({crash_reason})."),
                                halted_on_finding=True,
                            ))
                history.append(
                    RepairIteration(
                        iteration=iteration,
                        stage=stage,
                        passed=False,
                        diagnostics=[],
                        raw_error=crash_reason,
                    )
                )
                if "timed out" in crash_reason.lower() or "timeout" in crash_reason.lower():
                    consecutive_timeouts += 1
                    if consecutive_timeouts >= 2:
                        # Hardware spinlock / infinite loop hazard: fail fast instead of wasting LLM turns
                        break
                else:
                    consecutive_timeouts = 0

                if iteration >= self.max_iterations:
                    break
                candidate = self.agent.repair_harness(
                    candidate=candidate,
                    error_type="RUNTIME_SMOKE_CRASH",
                    error_message=crash_reason,
                    diagnostics=[],
                )
                continue

            if self.wrap_probe_runs > 0:
                self._wrap_probe(
                    harness_src_path, out_binary_path, target_c_files, include_dirs,
                    target_paths, iteration, findings,
                )
            history.append(
                RepairIteration(
                    iteration=iteration, stage="SUCCESS", passed=True, diagnostics=[], raw_error=""
                )
            )
            return _finish(RepairOutcome(
                success=True,
                target_api=target_api.name,
                final_harness_code=candidate.code,
                harness_file_path=str(harness_src_path),
                binary_path=str(out_binary_path),
                total_iterations=iteration,
                history=history,
                failure_reason=None,
            ))

        failure_reason = self._summarize_terminal_failure(last_comp_res, last_smoke_res)
        return _finish(RepairOutcome(
            success=False,
            target_api=target_api.name,
            final_harness_code=candidate.code,
            harness_file_path=str(harness_src_path),
            binary_path=None,
            total_iterations=self.max_iterations,
            history=history,
            failure_reason=failure_reason,
        ))

    def _wrap_probe(self, harness_src_path, out_binary_path, target_c_files, include_dirs,
                    target_paths, iteration, findings) -> None:
        """Record-only: see ``wrap_probe_runs``. Any problem here is swallowed on purpose,
        because the probe must not change the outcome of the loop."""
        probe_bin = out_binary_path.with_name(out_binary_path.name + "_wrap")
        try:
            comp = self.compiler.compile_harness(
                harness_src_path=harness_src_path, target_c_files=target_c_files,
                include_dirs=include_dirs, output_binary_path=probe_bin,
                extra_flags=["-fsanitize=unsigned-integer-overflow"],
            )
            if not comp.success:
                return
            res = self.smoke_oracle.run_smoke_test(
                probe_bin, runs=self.wrap_probe_runs,
                max_total_time=self.stability_max_time_sec,
                timeout_sec=self.stability_max_time_sec + 60,
            )
            for u in target_side_ubsan(res.stderr, target_paths)[:5]:
                findings.append(CrashFinding(
                    iteration=iteration, stage="WRAP_PROBE", verdict=CrashVerdict.TARGET_SIDE,
                    site_file=u.file, site_line=u.line, site_col=u.col,
                    message=f"UBSan (wrap probe): {u.message}",
                    evidence_excerpt=evidence_excerpt(res.stderr, 12),
                    status="CANDIDATE: unsigned wrap is defined behaviour; review whether it is intended"))
        except Exception:
            return

    @staticmethod
    def _summarize_terminal_failure(
        comp_res: Optional[CompilationResult], smoke_res: Optional[SmokeTestResult]
    ) -> str:
        """
        Produces a one-line, honest reason the loop gave up, distinguishing "never got a
        clean compile" from "compiled but kept crashing/timing out the smoke test" -- the
        two terminal-failure modes have different implications for item 2's analysis and
        must not be collapsed into one generic message.
        """
        if comp_res is not None and not comp_res.success:
            return (
                "Exceeded maximum repair iterations without producing a harness that "
                "compiles and links cleanly."
            )
        if smoke_res is not None and not smoke_res.passed:
            reason = smoke_res.crash_reason or "unspecified smoke-test failure"
            return (
                "Harness compiled on the final iteration but failed the smoke-test oracle "
                f"({reason})."
            )
        return "Exceeded maximum repair iterations without satisfying all verification oracles."
