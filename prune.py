import json
import collections

with open('ast_output.json') as f:
    ast_data = json.load(f)

valid_keys = set()
for func_name, func_data in ast_data['functions'].items():
    for acc in func_data['mmio_accesses']:
        valid_keys.add(f"{func_name}::{acc['register']}::{acc['line']}")

with open('llm_proposals.json') as f:
    results = json.load(f)

new_results = {k: v for k, v in results.items() if k in valid_keys}

with open('llm_proposals.json', 'w') as f:
    json.dump(new_results, f, indent=2)

print(f'Pruned from {len(results)} to {len(new_results)}')

backend_counts = collections.Counter(v.get('backend', 'unknown') for v in new_results.values())
print('\nBackend counts:')
for k, v in backend_counts.items():
    print(f'  {k}: {v}')

model_counts = collections.Counter(v['model'] for v in new_results.values())
print('\nModel counts (all backends combined):')
for k, v in model_counts.items():
    print(f'  {k}: {v}')
