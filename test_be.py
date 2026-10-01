import json
with open('llm_proposals.json') as f: p = json.load(f)
for k,v in p.items():
  if v['model'] == 'bitextract': print(k, v['model'])
