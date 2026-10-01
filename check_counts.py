import pandas as pd
import json
import re
import csv
dataset = []
def process_file(ast_file, proposals_file, csv_files):
    with open(ast_file) as f: ast = json.load(f)
    ground_truth = {}
    for csv_path in csv_files:
        try:
            with open(csv_path) as f:
                for row in csv.DictReader(f):
                    m = re.search(r"\(([A-Za-z0-9_x]+)\)", row["Reg name"])
                    name = m.group(1) if m else row["Reg name"].strip()
                    ground_truth[name] = {"cat": row["Reg cat"]}
        except: pass
    for f_key, f_data in ast["functions"].items():
        parts = f_key.split("::")
        src = parts[0] if len(parts) > 1 else "p2im-unit_tests/RIOT/RIOT-ENV/cpu/stm32f1/periph/uart.c"
        for acc in f_data.get("mmio_accesses", []):
            if acc["access_type"] == "write": continue
            reg = acc["register"]
            matched_gt = next((gt for gt in ground_truth if gt.endswith("_" + reg) or gt == reg), None)
            if not matched_gt: continue
            dataset.append({
                "label": ground_truth[matched_gt]["cat"],
                "group": matched_gt,
                "peripheral": "SPI" if "spi" in src.lower() else "OTHER"
            })
process_file("ast_kinetis_filtered.json", "llm_proposals_kinetis.json", [
    "p2im-unit_tests/RIOT/ADC/k64f.csv", "p2im-unit_tests/RIOT/I2C/k64f.csv",
    "p2im-unit_tests/RIOT/SPI/k64f.csv", "p2im-unit_tests/RIOT/TIMER/k64f.csv"
])
process_file("ast_output.json", "llm_proposals_riot.json", ["p2im-unit_tests/RIOT/USART/f103.csv"])
df = pd.DataFrame(dataset)
print(f"Total Unique Registers: {len(df['group'].unique())}")
print(f"Unique Registers in SPI: {len(df[df['peripheral']=='SPI']['group'].unique())}")
print(f"Unique Registers in OTHER: {len(df[df['peripheral']!='SPI']['group'].unique())}")
