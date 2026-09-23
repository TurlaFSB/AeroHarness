import os
with open("evaluate_accuracy_FINAL.py", "r") as f:
    code = f.read()

replacement = """
    evaluated_accesses += 1
    if is_correct:
        correct_accesses += 1
    
    print(f"{reg: <12} | {gt_cat: <6} | {llm_model: <12} | {'CORRECT' if is_correct else 'INCORRECT'}")
"""

code = code.replace("""
    evaluated_accesses += 1
    if is_correct:
        correct_accesses += 1
""", replacement)

with open("evaluate_accuracy_FINAL.py", "w") as f:
    f.write(code)
