import json, csv, re
import pandas as pd
import numpy as np
import random

def get_context(source, target_line): return ""

dataset = []
def process_file(ast_file, proposals_file, csv_files):
    with open(ast_file) as f: ast = json.load(f)
    with open(proposals_file) as f: props = json.load(f)
    ground_truth = {}
    for csv_path in csv_files:
        try:
            with open(csv_path) as f:
                for row in csv.DictReader(f):
                    m = re.search(r'\(([A-Za-z0-9_x]+)\)', row["Reg name"])
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
label_map = {"SR": 0, "CR": 1, "DR": 2, "C&SR": 3}
df["label"] = df["label"].map(label_map)

# Split 2 Baseline (Hold-out SPI)
train_df = df[df["peripheral"] != "SPI"]
test_df = df[df["peripheral"] == "SPI"]
majority_class = train_df["label"].mode()[0]
split2_acc = (test_df["label"] == majority_class).mean()
print(f"Majority Baseline Split 2 (Hold-out SPI): {split2_acc*100:.1f}%")

# Split 1 Baseline (5-Fold Group)
unique_groups = df["group"].unique()
random.seed(42)
np.random.seed(42)
random.shuffle(unique_groups)
folds = np.array_split(unique_groups, 5)

accs = []
for i in range(5):
    test_groups = folds[i]
    train_mask = ~df["group"].isin(test_groups)
    test_mask = df["group"].isin(test_groups)
    
    tr_df = df[train_mask]
    te_df = df[test_mask]
    if len(te_df) == 0: continue
    
    maj = tr_df["label"].mode()[0]
    acc = (te_df["label"] == maj).mean()
    accs.append(acc)

print(f"Majority Baseline Split 1 (5-Fold): {np.mean(accs)*100:.1f}% +/- {np.std(accs)*100:.1f}%")
