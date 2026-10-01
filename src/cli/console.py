"""
Rich Terminal Console & Dashboard for AeroHarness
"""
from typing import List, Dict, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from src.analyzer.c_ast_extractor import ExtractedHeaderContext
from src.analyzer.call_graph import APIRiskScore
from src.oracle.repair_loop import RepairOutcome
from src.fuzzer.runner import CampaignResult


class AeroConsole:
    """Provides formatted visual output for AeroHarness execution."""

    def __init__(self):
        self.console = Console()

    def print_banner(self):
        banner_text = """
    ___                  _  _                                  
   / _ \\                | || |                                 
  / /_\\ \\ ___ _ __ ___  | || |_ __ _ _ __ _ __   ___  ___ ___  
  |  _  |/ _ \\ '__/ _ \\ | __   / _` | '__| '_ \\ / _ \\/ __/ __| 
  | | | |  __/ | | (_) || || || (_| | |  | | | |  __/\\__ \\__ \\ 
  \\_| |_/\\___|_|  \\___/ |_||_| \\__,_|_|  |_| |_|\\___||___/___/ 
        Autonomous Embedded Fuzz Harness Cyber Reasoning System
        """
        self.console.print(Panel(Text(banner_text, style="bold cyan"), border_style="cyan"))

    def display_extracted_apis(self, context: ExtractedHeaderContext, risk_scores: Dict[str, APIRiskScore]):
        """Displays table of extracted APIs, types, and risk scores."""
        table = Table(title="Extracted Embedded APIs & Vulnerability Risk Ranking", box=box.ROUNDED)
        table.add_column("Target API", style="bold green")
        table.add_column("Return Type", style="dim")
        table.add_column("Parameters", style="yellow")
        table.add_column("Risk Score", justify="right", style="bold red")
        table.add_column("Vulnerability Assessment", style="white")

        for func in context.functions:
            params_str = ", ".join([f"{p.type_str} {p.name}" for p in func.parameters])
            score_obj = risk_scores.get(func.name)
            score_val = str(score_obj.risk_score) if score_obj else "N/A"
            justification = score_obj.justification if score_obj else "Standard function"

            table.add_row(
                func.name,
                func.return_type,
                params_str,
                score_val,
                justification
            )

        self.console.print(table)

    def display_repair_outcome(self, outcome: RepairOutcome):
        """Displays summary of the closed-loop self-repair process."""
        status_style = "bold green" if outcome.success else "bold red"
        status_text = "VERIFIED & PASSED ALL ORACLES" if outcome.success else "FAILED TO CONVERGE"

        panel_content = [
            f"[bold]Target API:[/bold] {outcome.target_api}",
            f"[bold]Status:[/bold] [{status_style}]{status_text}[/{status_style}]",
            f"[bold]Iterations Required:[/bold] {outcome.total_iterations}",
            f"[bold]Generated Harness Path:[/bold] {outcome.harness_file_path or 'None'}",
            f"[bold]Binary Path:[/bold] {outcome.binary_path or 'None'}"
        ]

        if not outcome.success and outcome.failure_reason:
            panel_content.append(f"[bold red]Failure Reason:[/bold red] {outcome.failure_reason}")

        self.console.print(Panel("\n".join(panel_content), title="[bold cyan]Closed-Loop Self-Repair Summary[/bold cyan]", border_style="green" if outcome.success else "red"))

    def display_campaign_results(self, result: CampaignResult):
        """Displays live fuzzing campaign statistics and bug disclosures."""
        table = Table(title=f"Fuzzing Campaign Results for {result.target_api}", box=box.ROUNDED)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="bold yellow")

        table.add_row("Fuzzing Duration", f"{result.fuzzing_duration_sec}s")
        table.add_row("Total Executions", str(result.total_executions))
        table.add_row("Execs / Second", str(result.execs_per_second))
        table.add_row("Corpus Seeds", str(result.corpus_count))
        if result.coverage:
            table.add_row("Branch Coverage", f"{result.coverage.branch_coverage_pct}% ({result.coverage.branches_covered} features)")
            table.add_row("Line Coverage", f"{result.coverage.line_coverage_pct}% ({result.coverage.lines_covered} lines)")

        self.console.print(table)

        if result.crashed and result.crash_report:
            crash = result.crash_report
            crash_panel = [
                f"[bold red]CRASH DETECTED: AddressSanitizer Tripped![/bold red]",
                f"[bold]Vulnerability:[/bold] {crash.crash_type}",
                f"[bold]Classification:[/bold] {crash.cwe_id}",
                f"[bold]Access:[/bold] {crash.access_type or 'Unknown'} {crash.access_size or ''} bytes at {crash.faulting_address or 'unknown address'}",
                f"[bold]Reproducible PoV Artifact:[/bold] [bold yellow]{result.pov_artifact.file_path if result.pov_artifact else 'Generated'}[/bold yellow]"
            ]
            self.console.print(Panel("\n".join(crash_panel), title="[bold red]VULNERABILITY DISCLOSURE[/bold red]", border_style="red"))
