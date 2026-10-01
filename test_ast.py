import json
with open("ast_output.json") as f:
    data = json.load(f)
total = sum(len(d["mmio_accesses"]) for d in data["functions"].values())
print(f"Total MMIO accesses found: {total}")
print(f"Total Extraction Warnings: {len(data.get('extraction_warnings', []))}")
if data.get('extraction_warnings'):
    print(data['extraction_warnings'][0])
