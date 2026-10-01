import json
import sys

combined = {"constants": [], "functions": {}, "extraction_warnings": []}

for file in sys.argv[1:]:
    with open(file, "r") as f:
        data = json.load(f)
        combined["constants"].extend(data.get("constants", []))
        for func_name, func_data in data.get("functions", {}).items():
            if func_name not in combined["functions"]:
                combined["functions"][func_name] = func_data
            else:
                combined["functions"][func_name]["mmio_accesses"].extend(func_data.get("mmio_accesses", []))

with open("ast_combined.json", "w") as f:
    json.dump(combined, f, indent=2)
