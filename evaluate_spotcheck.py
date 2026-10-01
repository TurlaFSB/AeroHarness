import json
import csv
import re

csv_files = {
    "ADC": "p2im-unit_tests/RIOT/ADC/k64f.csv",
    "I2C": "p2im-unit_tests/RIOT/I2C/k64f.csv",
    "SPI": "p2im-unit_tests/RIOT/SPI/k64f.csv",
    "TIMER": "p2im-unit_tests/RIOT/TIMER/k64f.csv"
}

ground_truth = {}
for ptype, csv_path in csv_files.items():
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
                "raw": row["Reg name"],
                "ptype": ptype
            }

def evaluate_subset(proposals_file):
    with open(proposals_file, "r") as f:
        proposals = json.load(f)
        
    with open("selected_spotcheck.json", "r") as f:
        selected_keys = json.load(f)
        
    correct_accesses = 0
    evaluated_accesses = 0
    
    for key in selected_keys:
        if key not in proposals or proposals[key]["model"] in ["unknown", "failed_api_error"]:
            continue
            
        p = proposals[key]
        if p["model"] == "not_applicable_write_only":
            continue
            
        reg = p["register"]
        matched_gt_name = None
        for gt in ground_truth:
            if gt.endswith("_" + reg) or gt == reg:
                matched_gt_name = gt
                break
                
        if not matched_gt_name:
            continue
            
        gt_cat = ground_truth[matched_gt_name]["gt_cat"]
        llm_model = p["model"]
        
        is_correct = False
        if gt_cat == "SR" and llm_model == "bitextract":
            is_correct = True
        elif gt_cat == "DR" and llm_model == "passthrough":
            is_correct = True
        elif gt_cat == "CR" and llm_model in ["set", "passthrough"]:
            is_correct = True
        elif gt_cat == "C&SR" and llm_model in ["set", "bitextract"]:
            is_correct = True
            
        evaluated_accesses += 1
        if is_correct:
            correct_accesses += 1
            
    if evaluated_accesses > 0:
        return correct_accesses, evaluated_accesses, (correct_accesses/evaluated_accesses)*100
    return 0, 0, 0.0

print("Evaluating Gemini Spot-Check (Corrected Prompt):")
c, t, acc = evaluate_subset("llm_proposals_kinetis_gemini_spotcheck.json")
print(f"  Gemini Accuracy: {c}/{t} ({acc:.1f}%)")

print("Evaluating Ollama on the SAME subset (Corrected Prompt):")
c2, t2, acc2 = evaluate_subset("llm_proposals_kinetis_v2.json")
print(f"  Ollama Accuracy: {c2}/{t2} ({acc2:.1f}%)")
