import json
import httpx
import os
import sys
import time
import random

try:
    with open(".env") as f:
        for line in f:
            if "GEMINI_API_KEY" in line and "=" in line:
                api_key = line.split("=")[1].strip().strip('"').strip("'")
except:
    api_key = os.environ.get("GEMINI_API_KEY")

with open("ast_kinetis.json", "r") as f:
    data = json.load(f)

with open("selected_spotcheck.json", "r") as f:
    selected_keys = json.load(f)

proposals = {}
if os.path.exists("llm_proposals_kinetis_gemini_spotcheck.json"):
    with open("llm_proposals_kinetis_gemini_spotcheck.json", "r") as f:
        proposals = json.load(f)

PROMPT_TEMPLATE = """You are an expert firmware vulnerability researcher building MMIO register models for the Fuzzware fuzzer.
Given the following C source code context around an MMIO register access in a device driver, propose the most appropriate Fuzzware-style model for this register.

The available Fuzzware models are:
- Constant: The register always returns a constant value when read (e.g., a hardware ID or unchanged status).
- Passthrough: Data written to the register is returned exactly as written on the next read (e.g., configuration registers).
- Bitextract: The fuzzer should supply a symbolic value, but only specific bits are used (e.g., status/flag registers like RX ready).
- Set: A specific bit pattern is written to trigger an action, or a state machine changes bits (e.g., command registers).
- Identity: The register always returns a specific identity value.

Register name: {register}
Function: {function_sig}
Access Type: {access_type}

Surrounding Code:
{context}

Analyze the code. Is the driver reading from or writing to the register? Is it checking a specific bit? Is it setting a configuration?
Propose the most appropriate model and provide explicit reasoning grounded ONLY in the provided code context.
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

def generate_gemini(prompt, api_key):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
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
    while retries < 4:
        try:
            resp = httpx.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 503:
                # Exponential backoff with jitter
                wait_time = (15 * (2 ** retries)) + random.uniform(-2, 2)
                print(f"  Got 503. Retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
                retries += 1
                continue
            elif resp.status_code == 429:
                print("  Got 429 Rate Limited. Sleeping 60s...")
                time.sleep(60)
                retries += 1
                continue
            
            resp.raise_for_status()
            res_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(res_text)
        except Exception as e:
            if retries < 3:
                wait_time = (15 * (2 ** retries)) + random.uniform(-2, 2)
                print(f"  Request failed: {e}. Retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
                retries += 1
            else:
                raise e
    raise Exception("Max retries exceeded (503/429)")

count = 0
successes = 0

for func_key, f_data in data["functions"].items():
    source_file, func_name = func_key.split("::")
    
    for acc in f_data.get("mmio_accesses", []):
        reg = acc["register"]
        line = acc["line"]
        access_type = acc["access_type"]
        
        prop_key = f"{func_key}::{reg}::{line}"
        if prop_key not in selected_keys:
            continue
            
        count += 1
        print(f"[{count}/{len(selected_keys)}] Processing {func_name}::{reg}...")
        
        if prop_key in proposals and proposals[prop_key].get("model") not in ["unknown", "failed_api_error"]:
            print(f"  Already processed: {proposals[prop_key]['model']}")
            successes += 1
            continue
            
        context = get_context(source_file, func_name, line)
        prompt = PROMPT_TEMPLATE.format(
            function_sig=f_data["signature"],
            register=reg,
            access_type=access_type,
            context=context
        )
        
        try:
            result = generate_gemini(prompt, api_key)
            pred_model = result.get("model", "").lower().strip()
            print(f"  -> {pred_model} (gemini)")
            proposals[prop_key] = {
                "source": source_file,
                "function": func_name,
                "register": reg,
                "model": pred_model,
                "reasoning": result.get("reasoning", ""),
                "backend": "gemini"
            }
            successes += 1
        except Exception as e:
            print(f"  -> FAILED: {e}")
            proposals[prop_key] = {
                "source": source_file,
                "function": func_name,
                "register": reg,
                "model": "failed_api_error",
                "reasoning": str(e),
                "backend": "none"
            }
            
        with open("llm_proposals_kinetis_gemini_spotcheck.json", "w") as out:
            json.dump(proposals, out, indent=2)

print(f"Finished. Successfully processed {successes}/{len(selected_keys)}.")
