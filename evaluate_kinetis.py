import json
import csv
import re
import glob

# Load LLM proposals
with open("llm_proposals_kinetis.json", "r") as f:
    proposals = json.load(f)

csv_files = {
    "ADC": "p2im-unit_tests/RIOT/ADC/k64f.csv",
    "I2C": "p2im-unit_tests/RIOT/I2C/k64f.csv",
    "SPI": "p2im-unit_tests/RIOT/SPI/k64f.csv",
    "TIMER": "p2im-unit_tests/RIOT/TIMER/k64f.csv"
}

overall_evaluated = 0
overall_correct = 0

print("="*50)
print("KINETIS (K64F) PERIPHERAL EVALUATION")
print("="*50)

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
            # Handle some Kinetis specifics where multiple registers have same name suffix
            # Actually, let's just use the name from the regex.
            ground_truth[name] = {
                "gt_cat": row["Reg cat"],
                "raw": row["Reg name"]
            }

    evaluated_accesses = 0
    correct_accesses = 0
    
    # Filter proposals for this peripheral.
    # In Kinetis, drivers are in spi.c, i2c.c, adc.c, timer.c
    for key, p in proposals.items():
        if p["model"] == "not_applicable_write_only":
            continue
            
        reg = p["register"]
        
        # Check if register is in this peripheral's test case CSV
        # (This organically filters out unused drivers like i2c.c when evaluating SPI)    
        matched_gt_name = None
        for gt in ground_truth:
            if reg in gt:  # Simple substring match since Kinetis registers in AST are often short (e.g. 'C1', 'S', 'SC')
                # Be a bit careful: 'C1' is in 'SPI0_CTAR0_SLAVE' if we're not careful.
                # Actually, Kinetis CMSIS headers usually have struct fields like 'C1', 'C2', 'S1', 'D'.
                # The P2IM CSV has 'UART0_C1', 'UART0_D'.
                # If the AST parsed `dev->C1`, `reg` is `C1`.
                # We need to match `C1` precisely at the end of the GT name, like `UART0_C1`.
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
            
    print(f"--- {ptype} Test Case ---")
    if evaluated_accesses == 0:
        print("0 accesses evaluated (no matches found).")
    else:
        acc = (correct_accesses / evaluated_accesses) * 100
        print(f"Accuracy: {correct_accesses}/{evaluated_accesses} ({acc:.1f}%)")
        
    overall_evaluated += evaluated_accesses
    overall_correct += correct_accesses

print("="*50)
if overall_evaluated > 0:
    acc = (overall_correct / overall_evaluated) * 100
    print(f"COMBINED TOTAL ACCURACY: {overall_correct}/{overall_evaluated} ({acc:.1f}%)")
else:
    print("NO ACCESSES EVALUATED.")
