import json
import csv
import re

with open("llm_proposals_kinetis.json", "r") as f:
    proposals = json.load(f)

csv_files = {
    "ADC": "p2im-unit_tests/RIOT/ADC/k64f.csv",
    "I2C": "p2im-unit_tests/RIOT/I2C/k64f.csv",
    "SPI": "p2im-unit_tests/RIOT/SPI/k64f.csv",
    "TIMER": "p2im-unit_tests/RIOT/TIMER/k64f.csv"
}

gemini_eval = 0
gemini_corr = 0
ollama_eval = 0
ollama_corr = 0

for ptype, csv_path in csv_files.items():
    ground_truth = {}
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            m = re.search(r'\(([A-Za-z0-9_x]+)\)', row["Reg name"])
            name = m.group(1) if m else row["Reg name"].strip()
            ground_truth[name] = {"gt_cat": row["Reg cat"], "raw": row["Reg name"]}

    for key, p in proposals.items():
        if p["model"] == "not_applicable_write_only": continue
        reg = p["register"]
        matched_gt_name = None
        for gt in ground_truth:
            if gt.endswith("_" + reg) or gt == reg:
                matched_gt_name = gt
                break
        if not matched_gt_name: continue
        
        gt_cat = ground_truth[matched_gt_name]["gt_cat"]
        llm_model = p["model"]
        
        is_correct = False
        if gt_cat == "SR" and llm_model == "bitextract": is_correct = True
        elif gt_cat == "DR" and llm_model == "passthrough": is_correct = True
        elif gt_cat == "CR" and llm_model in ["set", "passthrough"]: is_correct = True
        elif gt_cat == "C&SR" and llm_model in ["set", "bitextract"]: is_correct = True
            
        is_gemini = "Model:" not in p["reasoning"]
        if is_gemini:
            gemini_eval += 1
            if is_correct: gemini_corr += 1
        else:
            ollama_eval += 1
            if is_correct: ollama_corr += 1

print(f"Gemini Accuracy: {gemini_corr}/{gemini_eval} ({(gemini_corr/max(1, gemini_eval))*100:.1f}%)")
print(f"Ollama Accuracy: {ollama_corr}/{ollama_eval} ({(ollama_corr/max(1, ollama_eval))*100:.1f}%)")
