import json
import csv
import re
import random

random.seed(42)

with open("llm_proposals_kinetis_v2.json", "r") as f:
    proposals = json.load(f)

csv_files = {
    "ADC": "p2im-unit_tests/RIOT/ADC/k64f.csv",
    "I2C": "p2im-unit_tests/RIOT/I2C/k64f.csv",
    "SPI": "p2im-unit_tests/RIOT/SPI/k64f.csv",
    "TIMER": "p2im-unit_tests/RIOT/TIMER/k64f.csv"
}

selected_keys = []
selected_details = []

for ptype, csv_path in csv_files.items():
    ground_truth = {}
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            m = re.search(r'\(([A-Za-z0-9_x]+)\)', row["Reg name"])
            if m:
                name = m.group(1)
            else:
                name = row["Reg name"].strip()
            ground_truth[name] = {
                "gt_cat": row["Reg cat"],
                "raw": row["Reg name"]
            }
            
    # Find proposals that match this peripheral's ground truth
    valid_proposals = []
    for key, p in proposals.items():
        if p["model"] == "not_applicable_write_only":
            continue
        reg = p["register"]
        
        matched_gt_name = None
        for gt in ground_truth:
            if gt.endswith("_" + reg) or gt == reg:
                matched_gt_name = gt
                break
                
        if matched_gt_name:
            valid_proposals.append((key, reg, matched_gt_name, ground_truth[matched_gt_name]["gt_cat"]))
            
    # Sample 5
    if len(valid_proposals) > 5:
        sampled = random.sample(valid_proposals, 5)
    else:
        sampled = valid_proposals
        
    for item in sampled:
        key, reg, gt_name, gt_cat = item
        selected_keys.append(key)
        selected_details.append(f"{ptype} - {proposals[key]['function']}(): {reg} (GT: {gt_name}, {gt_cat})")

with open("selected_spotcheck.json", "w") as f:
    json.dump(selected_keys, f, indent=2)

print("Selected Registers for Spot-check:")
for d in selected_details:
    print(d)
