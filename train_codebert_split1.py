import json, csv, re, torch, random
import pandas as pd
import numpy as np
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments

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
            dataset.append({
                "context": ctx,
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

tokenizer = AutoTokenizer.from_pretrained("microsoft/codebert-base")
def tokenize(batch):
    return tokenizer(batch["context"], padding="max_length", truncation=True, max_length=128)

def compute_metrics(eval_pred):
    preds = np.argmax(eval_pred.predictions, axis=-1)
    acc = (preds == eval_pred.label_ids).mean()
    return {"accuracy": float(acc)}


print("--- CodeBERT Split 1 (5-Fold Group) ---")
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
    
    tr_ds = Dataset.from_pandas(tr_df).map(tokenize, batched=True)
    te_ds = Dataset.from_pandas(te_df).map(tokenize, batched=True)
    
    m = AutoModelForSequenceClassification.from_pretrained("microsoft/codebert-base", num_labels=4)
    tr = Trainer(model=m, args=TrainingArguments(output_dir=f"./cb_f{i}", num_train_epochs=5, per_device_train_batch_size=8, report_to="none"), train_dataset=tr_ds, eval_dataset=te_ds, compute_metrics=compute_metrics)
    tr.train()
    met = tr.evaluate()
    print(f"Fold {i+1} Accuracy: {met['eval_accuracy']*100:.1f}%")
    accs.append(met['eval_accuracy'])

print(f"CodeBERT Split 1 (5-Fold): {np.mean(accs)*100:.1f}% +/- {np.std(accs)*100:.1f}%")
