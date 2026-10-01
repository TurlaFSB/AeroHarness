import json
with open("llm_proposals_kinetis.json") as f:
    props = json.load(f)
gemini = 0
ollama = 0
for k, v in props.items():
    if v["model"] == "not_applicable_write_only":
        continue
    reasoning = v["reasoning"]
    if "Model:" in reasoning:
        ollama += 1
    else:
        gemini += 1
print(f"Gemini: {gemini}, Ollama: {ollama}")
