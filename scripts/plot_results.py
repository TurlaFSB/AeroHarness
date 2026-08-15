import sys
import json
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import click


def generate_svg_bar_chart(title: str, labels: list, values_a: list, values_b: list, legend_a: str, legend_b: str, out_file: Path):
    """Generates a clean vector SVG bar chart comparing AeroHarness vs Baseline."""
    width = 700
    height = 400
    margin_left = 80
    margin_bottom = 60
    chart_w = width - margin_left - 40
    chart_h = height - margin_bottom - 60

    num_groups = len(labels)
    group_w = chart_w / max(num_groups, 1)
    bar_w = group_w * 0.35

    svg_parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}">',
        '<style>',
        '  .title { font-family: sans-serif; font-size: 16px; font-weight: bold; fill: #1e293b; text-anchor: middle; }',
        '  .label { font-family: sans-serif; font-size: 11px; fill: #475569; text-anchor: middle; }',
        '  .axis { stroke: #cbd5e1; stroke-width: 1.5; }',
        '  .grid { stroke: #f1f5f9; stroke-dasharray: 4; }',
        '  .bar-a { fill: #2563eb; }',
        '  .bar-b { fill: #94a3b8; }',
        '  .legend { font-family: sans-serif; font-size: 12px; fill: #334155; }',
        '</style>',
        f'<text x="{width/2}" y="30" class="title">{title}</text>',
        f'<line x1="{margin_left}" y1="{height-margin_bottom}" x2="{width-30}" y2="{height-margin_bottom}" class="axis" />',
        f'<line x1="{margin_left}" y1="50" x2="{margin_left}" y2="{height-margin_bottom}" class="axis" />'
    ]

    # Draw Legend
    svg_parts.extend([
        f'<rect x="{width-240}" y="20" width="14" height="14" class="bar-a" rx="2" />',
        f'<text x="{width-220}" y="32" class="legend">{legend_a}</text>',
        f'<rect x="{width-120}" y="20" width="14" height="14" class="bar-b" rx="2" />',
        f'<text x="{width-100}" y="32" class="legend">{legend_b}</text>'
    ] )

    # Draw Bars
    max_val = 100.0  # Percentage scale
    for i, label in enumerate(labels):
        center_x = margin_left + (i * group_w) + (group_w / 2)
        val_a = values_a[i] if i < len(values_a) else 0
        val_b = values_b[i] if i < len(values_b) else 0

        h_a = (val_a / max_val) * chart_h
        h_b = (val_b / max_val) * chart_h

        x_a = center_x - bar_w - 2
        y_a = (height - margin_bottom) - h_a
        x_b = center_x + 2
        y_b = (height - margin_bottom) - h_b

        svg_parts.append(f'<rect x="{x_a}" y="{y_a}" width="{bar_w}" height="{h_a}" class="bar-a" rx="3" />')
        svg_parts.append(f'<rect x="{x_b}" y="{y_b}" width="{bar_w}" height="{h_b}" class="bar-b" rx="3" />')
        svg_parts.append(f'<text x="{center_x}" y="{height-margin_bottom+20}" class="label">{label}</text>')

    svg_parts.append('</svg>')

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text("\n".join(svg_parts), encoding="utf-8")


@click.command()
@click.option('--results-file', default="output/benchmarks/benchmark_results.json", help="Path to benchmark JSON results.")
@click.option('--output-dir', default="output/benchmarks/plots", help="Directory to save generated SVG plots.")
def plot(results_file: str, output_dir: str):
    """Generates high-resolution evaluation figures from benchmark results."""
    rf = Path(results_file)
    if not rf.exists():
        print(f"[!] Error: {results_file} not found. Run 'python benchmarks/run_benchmark.py' first.")
        return

    data = json.loads(rf.read_text(encoding="utf-8"))
    out_p = Path(output_dir)
    out_p.mkdir(parents=True, exist_ok=True)

    detailed_a = data.get("aeroharness_detailed", [])
    detailed_b = data.get("singleshot_detailed", [])

    labels = [d.get("target_name", f"T{i}").replace("ToyFirmware-", "").replace("FreeRTOS-", "") for i, d in enumerate(detailed_a)]
    cov_a = [d.get("branch_coverage_pct", 0.0) for d in detailed_a]
    cov_b = [d.get("branch_coverage_pct", 0.0) for d in detailed_b]

    # Plot 1: Branch Coverage Comparison
    plot_cov_path = out_p / "figure_branch_coverage_comparison.svg"
    generate_svg_bar_chart(
        title="Branch Coverage (%) Comparison across Embedded Targets",
        labels=labels,
        values_a=cov_a,
        values_b=cov_b,
        legend_a="AeroHarness",
        legend_b="Single-Shot Baseline",
        out_file=plot_cov_path
    )

    print(f"[+] Vector figure generated: {plot_cov_path}")


if __name__ == "__main__":
    plot()
