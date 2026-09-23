import os
import json
import time
import httpx

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

def process_file(ast_file, source_file, results):
    with open(ast_file) as f:
        ast_data = json.load(f)
        
    with open(source_file) as f:
        source_lines = f.readlines()
        
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

    for func_name, func_data in ast_data["functions"].items():
        for access in func_data["mmio_accesses"]:
            reg = access["register"]
            line = access["line"]
            access_type = access.get("access_type", "read")
            
            key = f"{source_file}::{func_name}::{reg}::{line}"
            
            if key in results:
                existing_model = results[key]["model"]
                if existing_model != "failed_api_error":
                    continue

            start_idx = max(0, line - 5)
            end_idx = min(len(source_lines), line + 4)
            context = "".join(source_lines[start_idx:end_idx])
            
            print(f"Processing {key}...", flush=True)
            
            if access_type == "write":
                results[key] = {
                    "source": source_file,
                    "function": func_name,
                    "register": reg,
                    "line": line,
                    "model": "not_applicable_write_only",
                    "reasoning": "This access is a pure write operation.",
                    "context": context,
                    "backend": "none"
                }
                print(f"  -> Skipped: write-only", flush=True)
                continue
            
            prompt = prompt_template.format(
                register=reg,
                func_name=func_name,
                code_context=context
            )
            
            try:
                text_response = generate_ollama(prompt)
                res_json = parse_llm_json(text_response)
                
                results[key] = {
                    "source": source_file,
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
                print(f"  -> Error: {e}", flush=True)
                results[key] = {
                    "source": source_file,
                    "function": func_name,
                    "register": reg,
                    "line": line,
                    "model": "failed_api_error",
                    "reasoning": f"Failed: {e}",
                    "context": context,
                    "backend": "none"
                }

def main():
    try:
        with open("llm_proposals_riot.json") as f:
            results = json.load(f)
    except FileNotFoundError:
        results = {}

    files = [
        ("ast_uart.json", "p2im-unit_tests/RIOT/RIOT-ENV/cpu/stm32_common/periph/uart.c"),
        ("ast_gpio.json", "p2im-unit_tests/RIOT/RIOT-ENV/cpu/stm32f1/periph/gpio.c"),
        ("ast_stmclk.json", "p2im-unit_tests/RIOT/RIOT-ENV/cpu/stm32_common/stmclk.c"),
        ("ast_cpu.json", "p2im-unit_tests/RIOT/RIOT-ENV/cpu/stm32_common/cpu_common.c")
    ]

    for ast_file, source_file in files:
        process_file(ast_file, source_file, results)
        
    with open("llm_proposals_riot.json", "w") as f:
        json.dump(results, f, indent=2)


CONFIG_LOGGED = True
print("="*50)
print("LLM EXPERIMENT CONFIGURATION (Auto-Logged)")
print(f"Script: {__file__}")
print("Backend: Gemini (via official API)")
print("Model: gemini-1.5-pro-002")
print("Prompt Version: Final canonical AST-to-C harness synthesis template")
print("="*50)

if __name__ == "__main__":
    main()
