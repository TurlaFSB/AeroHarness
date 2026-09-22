import json
import httpx
import os
import concurrent.futures

with open("ast_kinetis_filtered.json", "r") as f:
    data = json.load(f)

proposals = {}
if os.path.exists("llm_proposals_kinetis.json"):
    with open("llm_proposals_kinetis.json", "r") as f:
        proposals = json.load(f)

PROMPT_TEMPLATE = """
Analyze the following MMIO register access from a C firmware driver.

Source File: {source}
Function: {function_sig}
Register: {register}
Access Type: {access_type}

Code Context:
{context}

Target Register: {register}

Based on Fuzzware's modeling (passthrough, bitextract, set, constant, identity), propose the single most appropriate Fuzzer Model for reading this register.
Explain your reasoning, then end with 'Model: <model>'.
"""

def get_context(source, func_name, target_line):
    try:
        with open(source, "r") as src:
            lines = src.readlines()
        start = max(0, target_line - 5 - 1)
        end = min(len(lines), target_line + 5)
        return "".join(lines[start:end])
    except:
        return "<context unavailable>"

tasks = []
count = 0

for func_key, f_data in data["functions"].items():
    source_file, func_name = func_key.split("::")
    
    for acc in f_data.get("mmio_accesses", []):
        count += 1
        reg = acc["register"]
        line = acc["line"]
        access_type = acc["access_type"]
        
        prop_key = f"{func_key}::{reg}::{line}"
        
        # Skip pure writes immediately
        if access_type == "write":
            proposals[prop_key] = {
                "source": source_file,
                "function": func_name,
                "register": reg,
                "model": "not_applicable_write_only",
                "reasoning": "Skipped because access is write-only"
            }
            continue

        if prop_key in proposals and proposals[prop_key]["model"] != "unknown":
            continue

        context = get_context(source_file, func_name, line)
        prompt = PROMPT_TEMPLATE.format(
            source=source_file,
            function_sig=f_data["signature"],
            register=reg,
            access_type=access_type,
            context=context
        )
        
        tasks.append({
            "prop_key": prop_key,
            "source": source_file,
            "function": func_name,
            "register": reg,
            "prompt": prompt,
            "id": count
        })

print(f"Total tasks to run: {len(tasks)}")

def process_task(task):
    url = "http://localhost:11434/api/generate"
    try:
        resp = httpx.post(url, json={
            "model": "qwen2.5-coder:7b",
            "prompt": task["prompt"],
            "stream": False
        }, timeout=120)
        
        text = resp.json()["response"]
        model_match = [w.strip() for w in text.split() if w.strip().lower() in ["passthrough", "bitextract", "set", "constant", "identity"]]
        pred_model = model_match[-1].lower() if model_match else "unknown"
        if "model:" in text.lower():
            part = text.lower().split("model:")[-1].strip()
            import re
            m = re.match(r'^([a-z]+)', part)
            if m and m.group(1) in ["passthrough", "bitextract", "set", "constant", "identity"]:
                pred_model = m.group(1)
                
        print(f"[{task['id']}/332] {task['function']}::{task['register']} -> {pred_model}")
        return task["prop_key"], {
            "source": task["source"],
            "function": task["function"],
            "register": task["register"],
            "model": pred_model,
            "reasoning": text
        }
    except Exception as e:
        print(f"[{task['id']}/332] Error: {e}")
        return task["prop_key"], None

# Run with limited concurrency
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    future_to_task = {executor.submit(process_task, t): t for t in tasks}
    for i, future in enumerate(concurrent.futures.as_completed(future_to_task)):
        prop_key, res = future.result()
        if res:
            proposals[prop_key] = res
        # periodically save
        if i % 10 == 0:
            with open("llm_proposals_kinetis.json", "w") as out:
                json.dump(proposals, out, indent=2)

with open("llm_proposals_kinetis.json", "w") as out:
    json.dump(proposals, out, indent=2)

print("Done! Saved to llm_proposals_kinetis.json")
