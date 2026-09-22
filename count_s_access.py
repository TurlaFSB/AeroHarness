import json

with open("ast_kinetis_filtered.json") as f:
    ast = json.load(f)

c_s_accesses = []
for f_key, f_data in ast["functions"].items():
    for acc in f_data.get("mmio_accesses", []):
        if acc["register"] == "S":
            c_s_accesses.append(f"{f_key}::{acc['line']}")

print(f"Number of accesses to S register in AST: {len(c_s_accesses)}")
for x in c_s_accesses[:5]:
    print(x)
