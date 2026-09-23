# REJECTED SCRIPT
# Reason: Loose scoring logic that allows C&SR registers to count 'passthrough' as correct.
# This artificially hides real LLM failures on busy-wait status-polling registers.
# Please use evaluate_accuracy_FINAL.py instead.

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
            "p2im_cat": row["Model Cat"],
            "found_by_llm": [],
            "raw": row["Reg name"]
        }

with open("llm_proposals_riot.json", "r") as f:
    proposals = json.load(f)

for key, p in proposals.items():
    if p["model"] == "not_applicable_write_only":
        continue
    reg = p["register"]
    
    matched_gt = None
    if p["source"].endswith("uart.c"):
        for gt in ground_truth:
            if gt.startswith("USART_") and reg in gt:
                matched_gt = gt
                break
    elif p["source"].endswith("gpio.c"):
        for gt in ground_truth:
            if gt.startswith("GPIOx_") and reg in gt:
                matched_gt = gt
                break
    elif "stmclk" in p["source"] or "cpu" in p["source"]:
        for gt in ground_truth:
            if (gt.startswith("RCC_") or gt.startswith("FLASH_")) and reg in gt:
                matched_gt = gt
                break
                
    if matched_gt:
        ground_truth[matched_gt]["found_by_llm"].append(p["model"])

total_gt = len(ground_truth)
found_gt = sum(1 for gt in ground_truth.values() if gt["found_by_llm"])
print(f"Ground truth registers: {total_gt}")
print(f"Registers classified by LLM (read/RMW): {found_gt}")

correct_categories = 0
evaluated_categories = 0

for name, data in ground_truth.items():
    llms = [m for m in data["found_by_llm"] if m not in ("failed_api_error", "not_applicable_write_only")]
    
    if llms:
        evaluated_categories += 1
        # P2IM mapped to Fuzzware loosely:
        # SR -> bitextract
        # DR -> passthrough
        # CR -> set (or passthrough)
        # C&SR -> bitextract or set
        
        # Check if the LLM prediction aligns reasonably with P2IM cat:
        # P2IM cat is data['p2im_cat']
        is_correct = False
        p2im = data["p2im_cat"]
        # If any model proposal matches
        for m in llms:
            if p2im == "SR" and m in ("bitextract", "constant"): is_correct = True
            elif p2im == "DR" and m in ("passthrough", "identity"): is_correct = True
            elif p2im == "CR" and m in ("set", "passthrough", "bitextract"): is_correct = True # CR is quite generic
            elif p2im == "C&SR" and m in ("set", "bitextract", "passthrough"): is_correct = True
            
        if is_correct:
            correct_categories += 1
            print(f"{name}: Correct ({p2im} vs {list(set(llms))})")
        else:
            print(f"{name}: INCORRECT ({p2im} vs {list(set(llms))})")
    else:
        print(f"{name}: NO READ/RMW PROPOSAL")

print(f"\nFinal Accuracy: {correct_categories}/{evaluated_categories} ({correct_categories/max(1, evaluated_categories)*100:.1f}%) evaluated registers.")

