import json
import httpx
import os
import sys

# Load GEMINI_API_KEY from environment or from the script
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("WARNING: GEMINI_API_KEY not set. Checking run.py...")
    try:
        with open("run.py") as f:
            for line in f:
                if "GEMINI_API_KEY" in line and "=" in line:
                    api_key = line.split("=")[1].strip().strip('"').strip("'")
    except:
        pass
        
if not api_key:
    print("ERROR: No Gemini API Key found.")
    sys.exit(1)

with open("ast_kinetis.json", "r") as f:
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

count = 0
for func_key, f_data in data["functions"].items():
    source_file, func_name = func_key.split("::")
    
    for acc in f_data.get("mmio_accesses", []):
        count += 1
        reg = acc["register"]
        line = acc["line"]
        access_type = acc["access_type"]
        
        prop_key = f"{func_key}::{reg}::{line}"
        if prop_key in proposals and proposals[prop_key]["model"] != "unknown":
            continue
            
        if access_type == "write":
            proposals[prop_key] = {
                "source": source_file,
                "function": func_name,
                "register": reg,
                "model": "not_applicable_write_only",
                "reasoning": "Skipped because access is write-only"
            }
            continue

        context = get_context(source_file, func_name, line)
        prompt = PROMPT_TEMPLATE.format(
            source=source_file,
            function_sig=f_data["signature"],
            register=reg,
            access_type=access_type,
            context=context
        )
        
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key
        }
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "model": {"type": "STRING", "enum": ["passthrough", "bitextract", "set", "constant", "identity"]},
                        "reasoning": {"type": "STRING"}
                    },
                    "required": ["model", "reasoning"]
                },
                "temperature": 0.1
            }
        }
        
        retries = 0
        while retries < 5:
            try:
                resp = httpx.post(url, headers=headers, json=payload, timeout=30)
                if resp.status_code == 200:
                    result = json.loads(resp.json()["candidates"][0]["content"]["parts"][0]["text"])
                    pred_model = result["model"].lower()
                    print(f"[{count}/332] {func_name}::{reg} -> {pred_model} (Gemini)")
                    proposals[prop_key] = {
                        "source": source_file,
                        "function": func_name,
                        "register": reg,
                        "model": pred_model,
                        "reasoning": result["reasoning"]
                    }
                    break
                elif resp.status_code == 429:
                    print(f"[{count}/332] Rate limited (429). Sleeping 60s...")
                    import time
                    time.sleep(65)
                    retries += 1
                else:
                    print(f"[{count}/332] Gemini Error: {resp.status_code} {resp.text}")
                    break
            except Exception as e:
                print(f"[{count}/332] Failed to query Gemini for {reg}: {e}")
                import time
                time.sleep(10)
                retries += 1
            
        # periodically save
        if count % 10 == 0:
            with open("llm_proposals_kinetis.json", "w") as out:
                json.dump(proposals, out, indent=2)

with open("llm_proposals_kinetis.json", "w") as out:
    json.dump(proposals, out, indent=2)

print("Saved proposals to llm_proposals_kinetis.json")
