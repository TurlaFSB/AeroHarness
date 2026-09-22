import os
import json
import time
import httpx

def generate_gemini(prompt, api_key):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }
    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "model": {"type": "STRING"},
                    "reasoning": {"type": "STRING"}
                },
                "required": ["model", "reasoning"]
            },
            "temperature": 0.1
        }
    }
    
    timeout = httpx.Timeout(30.0)
    
    retries = 0
    max_retries = 2
    while retries <= max_retries:
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
            if response.status_code == 429:
                raise Exception("Rate limited 429")
            if response.status_code == 503:
                time.sleep(65)
                retries += 1
                continue
            
            response.raise_for_status()
            res_data = response.json()
            return res_data["candidates"][0]["content"]["parts"][0]["text"]
            
        except Exception as e:
            if hasattr(e, 'response') and getattr(e, 'response') is not None:
                if e.response.status_code == 429:
                    raise Exception("Rate limited 429")
                if e.response.status_code == 503:
                    time.sleep(65)
                    retries += 1
                    continue
            raise e
    raise Exception("Max retries exceeded")

def generate_ollama(prompt, api_key=None):
    full_prompt = prompt + '\n\nPlease respond ONLY with a valid JSON object containing exactly two string fields: "model" (the lowercase name of the model you chose) and "reasoning" (your detailed reasoning). Do not include any other text or markdown formatting.'
    
    response = httpx.post(
        "http://localhost:11434/api/generate", 
        json={
            "model": "qwen2.5-coder:7b", 
            "prompt": full_prompt, 
            "stream": False,
            "format": "json"
        }, 
        timeout=60.0
    )
    response.raise_for_status()
    return response.json()["response"]

def parse_llm_json(text_response):
    text = text_response.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return json.loads(text.strip())

def main():
    with open("ast_output.json") as f:
        ast_data = json.load(f)
        
    with open("uart_pl011.c") as f:
        source_lines = f.readlines()
        
    try:
        with open("llm_proposals.json") as f:
            results = json.load(f)
    except FileNotFoundError:
        results = {}
        
    for key, res in results.items():
        if "backend" not in res:
            if res["model"] == "not_applicable_write_only":
                res["backend"] = "none"
            elif res["model"] != "failed_api_error":
                res["backend"] = "gemini"
            else:
                res["backend"] = "none"

    prompt_template = """
You are an expert firmware vulnerability researcher building MMIO register models for the Fuzzware fuzzer.
Given the following C source code context around an MMIO register access in a device driver, propose the most appropriate Fuzzware-style model for this register.

The available Fuzzware models are:
- Constant: The register always returns a constant value when read (e.g., a hardware ID or unchanged status).
- Passthrough: Data written to the register is returned exactly as written on the next read (e.g., configuration registers).
- Bitextract: The fuzzer should supply a symbolic value, but only specific bits are used (e.g., status/flag registers like RX ready).
- Set: A specific bit pattern is written to trigger an action, or a state machine changes bits (e.g., command registers).
- Identity: The register always returns a specific identity value.

Register name: {register}
Function: {func_name}

Surrounding Code:
{code_context}

Analyze the code. Is the driver reading from or writing to the register? Is it checking a specific bit? Is it setting a configuration?
Propose the most appropriate model and provide explicit reasoning grounded ONLY in the provided code context.
"""
    
    active_backend = "ollama"
    generate_func = generate_ollama if active_backend == "ollama" else generate_gemini
    api_key = os.environ.get("GEMINI_API_KEY") if active_backend == "gemini" else None

    for func_name, func_data in ast_data["functions"].items():
        for access in func_data["mmio_accesses"]:
            reg = access["register"]
            line = access["line"]
            access_type = access.get("access_type", "read")
            
            key = f"{func_name}::{reg}::{line}"
            
            if key in results:
                existing_model = results[key]["model"]
                if existing_model != "failed_api_error":
                    continue

            start_idx = max(0, line - 5)
            end_idx = min(len(source_lines), line + 4)
            context = "".join(source_lines[start_idx:end_idx])
            
            print(f"Processing {key} via {active_backend}...", flush=True)
            
            if access_type == "write":
                results[key] = {
                    "function": func_name,
                    "register": reg,
                    "line": line,
                    "model": "not_applicable_write_only",
                    "reasoning": "This access is a pure write operation, so a fuzzer-facing read model is not applicable.",
                    "context": context,
                    "backend": "none"
                }
                print(f"  -> Skipped: not_applicable_write_only", flush=True)
                continue
            
            prompt = prompt_template.format(
                register=reg,
                func_name=func_name,
                code_context=context
            )
            
            try:
                text_response = generate_func(prompt, api_key)
                res_json = parse_llm_json(text_response)
                
                results[key] = {
                    "function": func_name,
                    "register": reg,
                    "line": line,
                    "model": res_json["model"].strip().lower(),
                    "reasoning": res_json["reasoning"],
                    "context": context,
                    "backend": active_backend
                }
                print(f"  -> Success: {results[key]['model']}", flush=True)
                
            except Exception as e:
                print(f"  -> Error processing {key}: {e}", flush=True)
                results[key] = {
                    "function": func_name,
                    "register": reg,
                    "line": line,
                    "model": "failed_api_error",
                    "reasoning": f"Failed with {active_backend}: {e}",
                    "context": context,
                    "backend": "none"
                }

            with open("llm_proposals.json", "w") as f:
                json.dump(results, f, indent=2)
            
    print("Done! Results written to llm_proposals.json")

if __name__ == "__main__":
    main()
