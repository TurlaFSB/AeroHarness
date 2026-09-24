import json, csv, re, os, random
import pandas as pd
import numpy as np
import xgboost as xgb
from scipy import stats
import torch
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments
import glob

def get_context(source, target_line):
    try:
        with open(source, "r") as src:
            lines = src.readlines()
        start = max(0, target_line - 5 - 1)
        end = min(len(lines), target_line + 5)
        return "".join(lines[start:end])
    except:
        return ""

def extract_features(context):
    return {
        "inside_while_loop": int(bool(re.search(r'\bwhile\s*\(', context))),
        "inside_if_stmt": int(bool(re.search(r'\bif\s*\(', context))),
        "has_bitwise_and": int('&' in context and '&&' not in context),
        "has_bitwise_or": int('|' in context and '||' not in context),
        "has_bitshift": int('<<' in context or '>>' in context),
        "is_rmw": int('|=' in context or '&=' in context)
    }

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
            dataset.append(features)

print("Loading dataset...")
process_file("ast_kinetis_filtered.json", "llm_proposals_kinetis.json", [
    "p2im-unit_tests/RIOT/ADC/k64f.csv", "p2im-unit_tests/RIOT/I2C/k64f.csv",
    "p2im-unit_tests/RIOT/SPI/k64f.csv", "p2im-unit_tests/RIOT/TIMER/k64f.csv"
])
process_file("ast_output.json", "llm_proposals_riot.json", ["p2im-unit_tests/RIOT/USART/f103.csv"])

df = pd.DataFrame(dataset)
label_map = {"SR": 0, "CR": 1, "DR": 2, "C&SR": 3}
df["label"] = df["label"].map(label_map)

# Split 1 (5-Fold Group by Register) exact reproduction
unique_groups = df["group"].unique()
random.seed(42)
np.random.seed(42)
random.shuffle(unique_groups)
folds = np.array_split(unique_groups, 5)

tokenizer = AutoTokenizer.from_pretrained("microsoft/codebert-base")
def tokenize(batch):
    return tokenizer(batch["context"], padding="max_length", truncation=True, max_length=128)

def compute_metrics(eval_pred):
    preds = np.argmax(eval_pred.predictions, axis=-1)
    acc = (preds == eval_pred.label_ids).mean()
    return {"accuracy": float(acc)}

accs_cb = []
accs_xgb = []
accs_maj = []

print("\nEvaluating models on 5-fold CV...")
for i in range(5):
    test_groups = folds[i]
    train_mask = ~df["group"].isin(test_groups)
    test_mask = df["group"].isin(test_groups)
    
    tr_df = df[train_mask]
    te_df = df[test_mask]
    if len(te_df) == 0:
        continue
    
    # 1. Majority Baseline
    maj_class = tr_df["label"].mode()[0]
    maj_acc = (te_df["label"] == maj_class).mean()
    accs_maj.append(maj_acc)
    
    # 2. XGBoost
    dtrain = xgb.DMatrix(tr_df.drop(columns=["label", "group", "context"]), label=tr_df["label"])
    dtest = xgb.DMatrix(te_df.drop(columns=["label", "group", "context"]), label=te_df["label"])
    params = {"objective": "multi:softmax", "num_class": 4, "eval_metric": "mlogloss"}
    # Use deterministic seed for XGBoost too, just in case
    params['seed'] = 42
    bst = xgb.train(params, dtrain, num_boost_round=10)
    xgb_preds = bst.predict(dtest)
    xgb_acc = np.mean(xgb_preds == te_df["label"].values)
    accs_xgb.append(xgb_acc)
    
    # 3. CodeBERT
    # Load model from checkpoint
    chk_dirs = glob.glob(f"./cb_f{i}/checkpoint-*")
    if not chk_dirs:
        print(f"ERROR: Could not find checkpoint for fold {i}")
        accs_cb.append(0.0)
        continue
    chk_dir = sorted(chk_dirs)[-1]  # Get the latest checkpoint
    
    te_ds = Dataset.from_pandas(te_df).map(tokenize, batched=True)
    m = AutoModelForSequenceClassification.from_pretrained(chk_dir, num_labels=4)
    tr = Trainer(model=m, eval_dataset=te_ds, compute_metrics=compute_metrics)
    met = tr.evaluate()
    accs_cb.append(met['eval_accuracy'])

    print(f"Fold {i+1}: Maj={maj_acc*100:.1f}%, XGB={xgb_acc*100:.1f}%, CB={met['eval_accuracy']*100:.1f}%")

print("\nSummary Statistics (Mean +/- Std):")
print(f"Majority: {np.mean(accs_maj)*100:.1f}% +/- {np.std(accs_maj)*100:.1f}%")
print(f"XGBoost:  {np.mean(accs_xgb)*100:.1f}% +/- {np.std(accs_xgb)*100:.1f}%")
print(f"CodeBERT: {np.mean(accs_cb)*100:.1f}% +/- {np.std(accs_cb)*100:.1f}%")

def cohen_d(x, y):
    n1, n2 = len(x), len(y)
    var_x, var_y = np.var(x, ddof=1), np.var(y, ddof=1)
    pooled_var = ((n1 - 1) * var_x + (n2 - 1) * var_y) / (n1 + n2 - 2)
    return (np.mean(x) - np.mean(y)) / np.sqrt(pooled_var)

print("\nStatistical Significance (Paired t-test):")
pairs = [
    ("CodeBERT vs XGBoost", accs_cb, accs_xgb),
    ("CodeBERT vs Majority", accs_cb, accs_maj),
    ("XGBoost vs Majority", accs_xgb, accs_maj)
]

for name, x, y in pairs:
    res = stats.ttest_rel(x, y)
    d = cohen_d(x, y)
    print(f"{name}:")
    print(f"  t-statistic: {res.statistic:.4f}")
    print(f"  p-value: {res.pvalue:.4f}")
    print(f"  Cohen's d: {d:.4f}")
