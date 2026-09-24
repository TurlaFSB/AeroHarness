import json
import httpx
import os
import sys
import time

api_key = None
try:
    with open(".env") as f:
        for line in f:
            if "GEMINI_API_KEY" in line and "=" in line:
                api_key = line.split("=")[1].strip().strip('"').strip("'")
except:
    pass
if not api_key:
    api_key = os.environ.get("GEMINI_API_KEY")

with open("ast_kinetis.json", "r") as f:
    data = json.load(f)

proposals = {}
if os.path.exists("llm_proposals_kinetis_v2.json"):
    with open("llm_proposals_kinetis_v2.json", "r") as f:
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
    resp = httpx.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code == 429:
        raise Exception("429 Rate limited")
    if resp.status_code == 503:
        raise Exception("503 Server overloaded")
    resp.raise_for_status()
    res_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(res_text)

def generate_ollama(prompt):
    full_prompt = prompt + '\n\nPlease respond ONLY with a valid JSON object containing exactly two string fields: "model" (the lowercase name of the model you chose) and "reasoning" (your detailed reasoning). Do not include any other text or markdown formatting.'
    resp = httpx.post(
        "http://localhost:11434/api/generate", 
        json={"model": "qwen2.5-coder:7b", "prompt": full_prompt, "stream": False, "format": "json"}, 
        timeout=60.0
    )
    resp.raise_for_status()
    text = resp.json()["response"].strip()
    if text.startswith("```json"): text = text[7:]
    if text.startswith("```"): text = text[3:]
    if text.endswith("```"): text = text[:-3]
    return json.loads(text.strip())

count = 0
gemini_success_count = 0
MAX_GEMINI_SPOT_CHECKS = 20

for func_key, f_data in data["functions"].items():
    source_file, func_name = func_key.split("::")
    
    for acc in f_data.get("mmio_accesses", []):
        count += 1
        reg = acc["register"]
        line = acc["line"]
        access_type = acc["access_type"]
        
        prop_key = f"{func_key}::{reg}::{line}"
        if prop_key in proposals and proposals[prop_key].get("model") not in ["unknown", "failed_api_error"]:
            # Count the existing gemini hits if restarting
            if proposals[prop_key].get("backend") == "gemini":
                gemini_success_count += 1
            continue
            
        if access_type == "write":
            proposals[prop_key] = {
                "source": source_file,
                "function": func_name,
                "register": reg,
                "model": "not_applicable_write_only",
                "reasoning": "Skipped because access is write-only",
                "backend": "none"
            }
            continue

        context = get_context(source_file, func_name, line)
        prompt = PROMPT_TEMPLATE.format(
            function_sig=f_data["signature"],
            register=reg,
            access_type=access_type,
            context=context
        )
        
        backend_used = "none"
        result = None
        
        active_backend = "ollama"
        if gemini_success_count < MAX_GEMINI_SPOT_CHECKS and api_key:
            active_backend = "gemini"
            
        if active_backend == "gemini":
            try:
                result = generate_gemini(prompt, api_key)
                backend_used = "gemini"
                gemini_success_count += 1
            except Exception as e:
                if "429" in str(e) or "503" in str(e):
                    print(f"[{count}/332] Gemini {e}. Failing over to Ollama.")
                    try:
                        result = generate_ollama(prompt)
                        backend_used = "ollama"
                    except Exception as ollama_e:
                        print(f"[{count}/332] Ollama fallback failed: {ollama_e}")
                else:
                    print(f"[{count}/332] Gemini Error: {e}")
                    
        if backend_used == "none":
            try:
                result = generate_ollama(prompt)
                backend_used = "ollama"
            except Exception as e:
                print(f"[{count}/332] Ollama Error: {e}")
                
        if result:
            pred_model = result.get("model", "").lower().strip()
            print(f"[{count}/332] {func_name}::{reg} -> {pred_model} ({backend_used})")
            proposals[prop_key] = {
                "source": source_file,
                "function": func_name,
                "register": reg,
                "model": pred_model,
                "reasoning": result.get("reasoning", ""),
                "backend": backend_used
            }
        else:
            proposals[prop_key] = {
                "source": source_file,
                "function": func_name,
                "register": reg,
                "model": "failed_api_error",
                "reasoning": "Failed both backends",
                "backend": "none"
            }
            
        if count % 10 == 0:
            with open("llm_proposals_kinetis_v2.json", "w") as out:
                json.dump(proposals, out, indent=2)

with open("llm_proposals_kinetis_v2.json", "w") as out:
    json.dump(proposals, out, indent=2)

print("Saved proposals to llm_proposals_kinetis_v2.json")
