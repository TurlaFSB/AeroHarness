
CONFIG_LOGGED = True
print("="*50)
print("TRAINING CONFIGURATION (Auto-Logged)")
print(f"Script: {__file__}")
print("Model: XGBoost")
print("Dataset Source: ast_combined.json / stage3_oracle_multi")
print("Split: Stratified GroupKFold (by Register/Peripheral) - 80/20")
print("Random Seed: 42")
print("="*50)

﻿import json, csv, re
import pandas as pd
import numpy as np
import xgboost as xgb

def extract_features(context):
    return {
        "inside_while_loop": int(bool(re.search(r'\bwhile\s*\(', context))),
        "inside_if_stmt": int(bool(re.search(r'\bif\s*\(', context))),
        "has_bitwise_and": int('&' in context and '&&' not in context),
        "has_bitwise_or": int('|' in context and '||' not in context),
        "has_bitshift": int('<<' in context or '>>' in context),
        "is_rmw": int('|=' in context or '&=' in context)
    }

def get_context(source, target_line):
    try:
        with open(source, "r") as src:
            lines = src.readlines()
        start = max(0, target_line - 5 - 1)
        end = min(len(lines), target_line + 5)
        return "".join(lines[start:end])
    except:
        return ""

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
            
            ctx = get_context(src, acc["line"])
            features = extract_features(ctx)
            features["label"] = ground_truth[matched_gt]["cat"]
            features["group"] = matched_gt
            features["context"] = ctx
            features["peripheral"] = "SPI" if "spi" in src.lower() else "OTHER"
            dataset.append(features)

process_file("ast_kinetis_filtered.json", "llm_proposals_kinetis.json", [
    "p2im-unit_tests/RIOT/ADC/k64f.csv", "p2im-unit_tests/RIOT/I2C/k64f.csv",
    "p2im-unit_tests/RIOT/SPI/k64f.csv", "p2im-unit_tests/RIOT/TIMER/k64f.csv"
])
process_file("ast_output.json", "llm_proposals_riot.json", ["p2im-unit_tests/RIOT/USART/f103.csv"])

df = pd.DataFrame(dataset)
label_map = {"SR": 0, "CR": 1, "DR": 2, "C&SR": 3}
df["label_idx"] = df["label"].map(label_map)

print(f"Dataset Size: {len(df)}")
print(f"Unique Groups (Registers): {df['group'].nunique()}")

train_df = df[df["peripheral"] != "SPI"]
test_df = df[df["peripheral"] == "SPI"]
print(f"Train size: {len(train_df)}, Test size: {len(test_df)}")
if len(test_df) > 0:
    dtrain = xgb.DMatrix(train_df.drop(columns=["label", "label_idx", "group", "context", "peripheral"]), label=train_df["label_idx"])
    dtest = xgb.DMatrix(test_df.drop(columns=["label", "label_idx", "group", "context", "peripheral"]), label=test_df["label_idx"])
    
    params = {"objective": "multi:softmax", "num_class": 4, "eval_metric": "mlogloss"}
    bst = xgb.train(params, dtrain, num_boost_round=10)
    preds = bst.predict(dtest)
    
    acc = np.mean(preds == test_df["label_idx"].values)
    print(f"XGBoost Split 2 (Hold-out SPI): {acc*100:.1f}% (Test N={len(test_df)}, Unique Regs={test_df['group'].nunique()})")

from collections import defaultdict
import random

# Split 1 (5-Fold Group by Register) manually without sklearn
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
    
    train_subset = df[train_mask]
    test_subset = df[test_mask]
    
    if len(test_subset) == 0: continue
    
    dtrain = xgb.DMatrix(train_subset.drop(columns=["label", "label_idx", "group", "context", "peripheral"]), label=train_subset["label_idx"])
    dtest = xgb.DMatrix(test_subset.drop(columns=["label", "label_idx", "group", "context", "peripheral"]), label=test_subset["label_idx"])
    
    bst = xgb.train(params, dtrain, num_boost_round=10)
    preds = bst.predict(dtest)
    acc = np.mean(preds == test_subset["label_idx"].values)
    accs.append(acc)

print(f"XGBoost Split 1 (5-Fold Group-by-Register): {np.mean(accs)*100:.1f}% +/- {np.std(accs)*100:.1f}%")
