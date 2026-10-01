import os
import glob
import subprocess
import json

files = glob.glob("p2im-unit_tests/RIOT/RIOT-ENV/cpu/kinetis/periph/*.c")
all_asts = []

for f in files:
    print("Parsing", f)
    # create a temporary output name
    out_name = "ast_temp.json"
    subprocess.run(["python3", "stage1_ast_parser.py", f])
    
    # ast_output.json is created
    with open("ast_output.json") as jf:
        data = json.load(jf)
        all_asts.append((f, data))

# Combine
combined = {
    "constants": [],
    "functions": {},
    "extraction_warnings": []
}

for f, data in all_asts:
    combined["constants"].extend(data.get("constants", []))
    for k, v in data.get("functions", {}).items():
        # prepend filename to function key to avoid collisions
        func_key = f"{f}::{k}"
        combined["functions"][func_key] = v

with open("ast_kinetis.json", "w") as out:
    json.dump(combined, out, indent=2)

print("Saved combined AST to ast_kinetis.json")
