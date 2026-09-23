import json
import csv
import re

ground_truth = {}
with open("p2im-unit_tests/RIOT/USART/f103.csv", "r") as f:
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

with open("llm_proposals_riot.json", "r") as f:
    proposals = json.load(f)

evaluated_accesses = 0
correct_accesses = 0

for key, p in proposals.items():
    if p["model"] == "not_applicable_write_only":
        continue
        
    reg = p["register"]
    matched_gt_name = None
    
    if p["source"].endswith("uart.c"):
        for gt in ground_truth:
            if gt.startswith("USART_") and reg in gt:
                matched_gt_name = gt
                break
    elif p["source"].endswith("gpio.c"):
        for gt in ground_truth:
            if gt.startswith("GPIOx_") and reg in gt:
                matched_gt_name = gt
                break
    elif "stmclk" in p["source"] or "cpu" in p["source"]:
        for gt in ground_truth:
            if (gt.startswith("RCC_") or gt.startswith("FLASH_")) and reg in gt:
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
    elif gt_cat == "C&SR" and llm_model in ["set", "bitextract"]: # STRICT RULE: passthrough rejected
        is_correct = True
        
    evaluated_accesses += 1
    if is_correct:
        correct_accesses += 1

print(f"Final Access-Level Accuracy: {correct_accesses}/{evaluated_accesses} ({(correct_accesses/max(1, evaluated_accesses))*100:.1f}%)")
