import json
import csv
import re
import os

csv_files = [
    "p2im-unit_tests/RIOT/ADC/k64f.csv",
    "p2im-unit_tests/RIOT/I2C/k64f.csv",
    "p2im-unit_tests/RIOT/SPI/k64f.csv",
    "p2im-unit_tests/RIOT/TIMER/k64f.csv"
]

gt_names = set()
for csv_path in csv_files:
    if not os.path.exists(csv_path):
        continue
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            m = re.search(r'\(([A-Za-z0-9_x]+)\)', row["Reg name"])
            if m:
                gt_names.add(m.group(1))
            else:
                gt_names.add(row["Reg name"].strip())

with open("ast_kinetis.json", "r") as f:
    data = json.load(f)

filtered_data = {"functions": {}}
keep_count = 0

for f_key, f_data in data["functions"].items():
    new_accesses = []
    for acc in f_data.get("mmio_accesses", []):
        reg = acc["register"]
        
        # Check if it matches any GT name
        matched = False
        for gt in gt_names:
            if gt.endswith("_" + reg) or gt == reg:
                matched = True
                break
                
        if matched:
            new_accesses.append(acc)
            keep_count += 1
            
    if new_accesses:
        f_data["mmio_accesses"] = new_accesses
        filtered_data["functions"][f_key] = f_data

print(f"Filtered from 332 down to {keep_count} targeted accesses.")
with open("ast_kinetis_filtered.json", "w") as f:
    json.dump(filtered_data, f, indent=2)
