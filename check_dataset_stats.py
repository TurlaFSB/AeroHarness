import json
import csv
import re

# 1. Kinetis
kinetis_csv_files = {
    "ADC": "p2im-unit_tests/RIOT/ADC/k64f.csv",
    "I2C": "p2im-unit_tests/RIOT/I2C/k64f.csv",
    "SPI": "p2im-unit_tests/RIOT/SPI/k64f.csv",
    "TIMER": "p2im-unit_tests/RIOT/TIMER/k64f.csv"
}

with open("llm_proposals_kinetis.json", "r") as f:
    k_proposals = json.load(f)

unique_registers = set()
total_accesses = 0

for ptype, csv_path in kinetis_csv_files.items():
    ground_truth = {}
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            m = re.search(r'\(([A-Za-z0-9_x]+)\)', row["Reg name"])
            name = m.group(1) if m else row["Reg name"].strip()
            ground_truth[name] = True

    for key, p in k_proposals.items():
        if p["model"] == "not_applicable_write_only": continue
        reg = p["register"]
        matched_gt_name = None
        for gt in ground_truth:
            if gt.endswith("_" + reg) or gt == reg:
                matched_gt_name = gt
                break
        if matched_gt_name:
            # We want the unique physical register, so we could use matched_gt_name
            unique_registers.add(matched_gt_name)
            total_accesses += 1

# 2. UART
with open("llm_proposals.json", "r") as f:
    u_proposals = json.load(f)
    
ground_truth = {}
with open("p2im-unit_tests/Zephyr/UART/stm32f103.csv", "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        m = re.search(r'\(([A-Za-z0-9_x]+)\)', row["Reg name"])
        name = m.group(1) if m else row["Reg name"].strip()
        ground_truth[name] = True

for key, p in u_proposals.items():
    if p["model"] == "not_applicable_write_only": continue
    reg = p["register"]
    matched_gt_name = None
    for gt in ground_truth:
        if gt.endswith("_" + reg) or gt == reg:
            matched_gt_name = gt
            break
    if matched_gt_name:
        unique_registers.add(matched_gt_name)
        total_accesses += 1

print(f"Total Evaluated Accesses: {total_accesses}")
print(f"Total Unique Registers (GT names): {len(unique_registers)}")
test_set_size = int(len(unique_registers) * 0.2)
print(f"Test Set Unique Registers (20%): {test_set_size}")
