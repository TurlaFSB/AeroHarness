"""
AeroHarness Main CLI Entrypoint
Autonomous Embedded-Target Reasoning and Oracle-Guided Harness Synthesis
"""
import sys
from pathlib import Path
import click

from config.settings import get_settings
from src.analyzer.c_ast_extractor import CASTExtractor
from src.analyzer.call_graph import CallGraphBuilder
from src.synthesizer.agent import HarnessSynthesizerAgent
from src.oracle.repair_loop import SelfRepairOrchestrator
from src.fuzzer.runner import FuzzingCampaignRunner
from src.cli.console import AeroConsole


@click.group()
def cli():
    """AeroHarness: Feedback-Driven Agentic Synthesis of Fuzz Drivers for Embedded Firmware."""
    pass


@cli.command()
@click.option('--header', default="targets/toy_firmware/protocol_parser.h", help="Path to target header file.")
@click.option('--source', default="targets/toy_firmware/protocol_parser.c", help="Path to target source file.")
def analyze(header: str, source: str):
    """Parses C AST, extracts types, MMIO registers, and ranks API vulnerability risks."""
    console = AeroConsole()
    console.print_banner()

    header_path = Path(header)
    source_path = Path(source)

    if not header_path.exists() or not source_path.exists():
        console.console.print(f"[bold red]Error:[/bold red] Target files '{header}' or '{source}' not found.")
        sys.exit(1)

    extractor = CASTExtractor()
    context = extractor.extract_from_header(header_path)

    cg_builder = CallGraphBuilder()
    known_apis = [f.name for f in context.functions]
    risk_scores = cg_builder.analyze_source_file(source_path, known_apis)

    console.display_extracted_apis(context, risk_scores)


@cli.command()
@click.option('--header', default="targets/toy_firmware/protocol_parser.h", help="Path to target header file.")
@click.option('--source', default="targets/toy_firmware/protocol_parser.c", help="Path to target source file.")
@click.option('--api', default="protocol_process_frame", help="Target API function name.")
@click.option('--output', default="output", help="Output directory for generated harnesses.")
def synthesize(header: str, source: str, api: str, output: str):
    """Synthesizes and autonomously repairs a fuzz driver for the specified API."""
    console = AeroConsole()
    console.print_banner()

    settings = get_settings()
    header_path = Path(header)
    source_path = Path(source)
    output_dir = Path(output)

    extractor = CASTExtractor()
    context = extractor.extract_from_header(header_path)

    target_func = next((f for f in context.functions if f.name == api), None)
    if not target_func:
        console.console.print(f"[bold red]Error:[/bold red] Function '{api}' not found in header {header}.")
        sys.exit(1)

    cg_builder = CallGraphBuilder()
    risk_scores = cg_builder.analyze_source_file(source_path, [f.name for f in context.functions])
    target_risk = risk_scores.get(api)

    console.console.print(f"[bold cyan]Initiating Agentic Synthesis & Self-Repair for target:[/bold cyan] [bold yellow]{api}[/bold yellow]")
    
    agent = HarnessSynthesizerAgent(
        api_key=settings.gemini_api_key,
        model_name=settings.primary_model
    )
    orchestrator = SelfRepairOrchestrator(agent=agent)

    outcome = orchestrator.run_synthesis_and_repair(
        header_context=context,
        target_api=target_func,
        risk_score=target_risk,
        header_path=header_path,
        target_c_files=[source_path],
        include_dirs=[header_path.parent],
        output_dir=output_dir
    )

    console.display_repair_outcome(outcome)


@cli.command()
@click.option('--header', default="targets/toy_firmware/protocol_parser.h", help="Path to target header file.")
@click.option('--source', default="targets/toy_firmware/protocol_parser.c", help="Path to target source file.")
@click.option('--api', default="protocol_process_frame", help="Target API function name.")
@click.option('--duration', default=15, help="Fuzzing campaign duration in seconds.")
@click.option('--output', default="output", help="Output directory.")
def run_all(header: str, source: str, api: str, duration: int, output: str):
    """Full End-to-End Campaign: Ingestion -> Agentic Synthesis -> Self-Repair -> Fuzzing -> PoV."""
    console = AeroConsole()
    console.print_banner()

    settings = get_settings()
    header_path = Path(header)
    source_path = Path(source)
    output_dir = Path(output)

    # 1. AST Analysis
    console.console.print("[bold green][Phase 1/4][/bold green] Parsing AST, extracting structs & MMIO registers...")
    extractor = CASTExtractor()
    context = extractor.extract_from_header(header_path)

    target_func = next((f for f in context.functions if f.name == api), None)
    if not target_func:
        console.console.print(f"[bold red]Error:[/bold red] Function '{api}' not found.")
        sys.exit(1)

    cg_builder = CallGraphBuilder()
    risk_scores = cg_builder.analyze_source_file(source_path, [f.name for f in context.functions])
    target_risk = risk_scores.get(api)
    console.display_extracted_apis(context, risk_scores)

    # 2. Agentic Synthesis & Self-Repair
    console.console.print("\n[bold green][Phase 2/4][/bold green] Gemini Pro Agentic Synthesis & Hardware Mocking...")
    agent = HarnessSynthesizerAgent(
        api_key=settings.gemini_api_key,
        model_name=settings.primary_model
    )
    orchestrator = SelfRepairOrchestrator(agent=agent)

    console.console.print("[bold green][Phase 3/4][/bold green] Running Closed-Loop Verification Oracles (Clang + ASan)...")
    outcome = orchestrator.run_synthesis_and_repair(
        header_context=context,
        target_api=target_func,
        risk_score=target_risk,
        header_path=header_path,
        target_c_files=[source_path],
        include_dirs=[header_path.parent],
        output_dir=output_dir
    )

    console.display_repair_outcome(outcome)

    if not outcome.success or not outcome.binary_path:
        console.console.print("[bold red]Cannot proceed to fuzzing because harness verification failed.[/bold red]")
        sys.exit(1)

    # 4. Fuzzing Campaign & Triage
    console.console.print(f"\n[bold green][Phase 4/4][/bold green] Launching libFuzzer Campaign ({duration}s)...")
    runner = FuzzingCampaignRunner()
    campaign_res = runner.run_campaign(
        binary_path=Path(outcome.binary_path),
        target_api_name=api,
        header_filename=header_path.name,
        output_dir=output_dir,
        magic_constants=context.magic_constants,
        duration_sec=duration
    )

    console.display_campaign_results(campaign_res)


if __name__ == "__main__":
    cli()
