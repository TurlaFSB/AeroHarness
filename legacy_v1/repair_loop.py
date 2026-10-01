"""
Closed-Loop Self-Repair Orchestrator for AeroHarness
Coordinates the multi-turn repair loop between Agent, Compiler Oracle, and Smoke Test Oracle.
"""
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from src.analyzer.c_ast_extractor import ExtractedHeaderContext, FunctionSignature
from src.analyzer.call_graph import APIRiskScore
from src.synthesizer.agent import HarnessSynthesizerAgent, SynthesisCandidate
from .compiler_oracle import CompilerOracle, CompilationResult
from .smoke_test import SmokeTestOracle, SmokeTestResult
from config.settings import get_settings


class RepairIteration(BaseModel):
    iteration: int
    stage: str  # 'SYNTHESIS', 'COMPILATION', 'SMOKE_TEST', 'SUCCESS'
    passed: bool
    diagnostics: List[Dict[str, Any]] = Field(default_factory=list)
    raw_error: str = ""


class RepairOutcome(BaseModel):
    success: bool
    target_api: str
    final_harness_code: str
    harness_file_path: Optional[str] = None
    binary_path: Optional[str] = None
    total_iterations: int = 0
    history: List[RepairIteration] = Field(default_factory=list)
    failure_reason: Optional[str] = None


class SelfRepairOrchestrator:
    """Manages the iterative feedback and self-repair loop until a valid harness is produced."""

    def __init__(
        self,
        agent: Optional[HarnessSynthesizerAgent] = None,
        compiler_oracle: Optional[CompilerOracle] = None,
        smoke_oracle: Optional[SmokeTestOracle] = None,
        max_iterations: Optional[int] = None
    ):
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
        output_dir: Path
    ) -> RepairOutcome:
        """Runs the complete closed-loop synthesis, compilation, and smoke-testing workflow."""
        output_dir.mkdir(parents=True, exist_ok=True)
        harness_src_path = output_dir / f"fuzz_{target_api.name}.cpp"
        out_binary_path = output_dir / f"fuzz_{target_api.name}_bin"

        history: List[RepairIteration] = []

        # 1. Synthesize Initial Harness
        candidate = self.agent.synthesize_initial_harness(
            header_context=header_context,
            target_api=target_api,
            risk_score=risk_score,
            header_filename=header_path.name
        )

        for iteration in range(1, self.max_iterations + 1):
            harness_src_path.write_text(candidate.code, encoding="utf-8")

            # 2. Compiler & Linker Oracle Check
            comp_res = self.compiler.compile_harness(
                harness_src_path=harness_src_path,
                target_c_files=target_c_files,
                include_dirs=include_dirs,
                output_binary_path=out_binary_path
            )

            if not comp_res.success:
                diag_dicts = [d.model_dump() for d in comp_res.diagnostics]
                history.append(RepairIteration(
                    iteration=iteration,
                    stage="COMPILATION_ORACLE",
                    passed=False,
                    diagnostics=diag_dicts,
                    raw_error=comp_res.stderr
                ))

                if iteration >= self.max_iterations:
                    break

                # Self-Repair Feedback
                candidate = self.agent.repair_harness(
                    candidate=candidate,
                    error_type="COMPILATION_ERROR",
                    error_message=comp_res.stderr,
                    diagnostics=diag_dicts
                )
                continue

            # 3. Dynamic Smoke-Test Oracle Check
            smoke_res = self.smoke_oracle.run_smoke_test(out_binary_path, runs=self.settings.smoke_test_runs)

            if not smoke_res.passed:
                history.append(RepairIteration(
                    iteration=iteration,
                    stage="SMOKE_TEST_ORACLE",
                    passed=False,
                    diagnostics=[],
                    raw_error=smoke_res.crash_reason or smoke_res.stderr
                ))

                if iteration >= self.max_iterations:
                    break

                # Self-Repair Feedback on Runtime crash
                candidate = self.agent.repair_harness(
                    candidate=candidate,
                    error_type="RUNTIME_SMOKE_CRASH",
                    error_message=smoke_res.crash_reason or smoke_res.stderr,
                    diagnostics=[]
                )
                continue

            # Passed all oracles!
            history.append(RepairIteration(
                iteration=iteration,
                stage="SUCCESS",
                passed=True,
                diagnostics=[],
                raw_error=""
            ))

            return RepairOutcome(
                success=True,
                target_api=target_api.name,
                final_harness_code=candidate.code,
                harness_file_path=str(harness_src_path),
                binary_path=str(out_binary_path),
                total_iterations=iteration,
                history=history,
                failure_reason=None
            )

        # Reached max iterations without passing
        return RepairOutcome(
            success=False,
            target_api=target_api.name,
            final_harness_code=candidate.code,
            harness_file_path=str(harness_src_path),
            binary_path=None,
            total_iterations=self.max_iterations,
            history=history,
            failure_reason="Exceeded maximum repair iterations without satisfying all verification oracles."
        )
