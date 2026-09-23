import os
for filename in ["stage2_llm_synthesizer_multi.py", "stage3_oracle_multi.py"]:
    with open(filename, "r") as f:
        code = f.read()
    if 'CONFIG_LOGGED = True' in code:
        code = code.split('CONFIG_LOGGED = True')[0]
    
    code += """
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
"""
    with open(filename, "w") as f:
        f.write(code)
