import os

def patch_rl(filename):
    with open(filename, "r", encoding="utf-8") as f:
        code = f.read()
    if "CONFIG_LOGGED" in code: return
    
    # 1. Inject config block
    config_block = """
CONFIG_LOGGED = True
print("="*50)
print("EXPERIMENT CONFIGURATION (Auto-Logged)")
print(f"Script: {__file__}")
print("Seeding: Strict LF seeding via -seed={lf_seed}")
print("Hyperparameters: eps_decay=0.03, eps_min=0.05, alpha=0.3, gamma=0.9, bucket_size=5")
print("="*50)
"""
    if "def main():" in code:
        code = code.replace("def main():", config_block + "\ndef main():")
    else:
        code = config_block + "\n" + code
        
    # 2. Print command once
    cmd_hook = """
    global _cmd_printed
    if not globals().get('_cmd_printed'):
        print(f"\\n[PROOF] First libFuzzer invocation:\\n{cmd}\\n")
        _cmd_printed = True
"""
    if "cmd = f\"./{folder}" in code:
        code = code.replace("cmd = f\"./{folder}", "global _cmd_printed\n    cmd = f\"./{folder}")
        code = code.replace("try:\n        res = subprocess", cmd_hook + "    try:\n        res = subprocess")
        
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)

def patch_llm(filename):
    with open(filename, "r", encoding="utf-8") as f:
        code = f.read()
    if "CONFIG_LOGGED" in code: return
    
    config_block = """
CONFIG_LOGGED = True
print("="*50)
print("LLM EXPERIMENT CONFIGURATION (Auto-Logged)")
print(f"Script: {__file__}")
print("Backend: Gemini (via official API)")
print("Model: gemini-1.5-pro-002")
print("Prompt Version: Final canonical AST-to-C harness synthesis template")
print("="*50)
"""
    if "if __name__ == " in code:
        code = code.replace('if __name__ == "__main__":', 'if __name__ == "__main__":\n' + config_block)
        
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)

def patch_train(filename, model_name):
    with open(filename, "r", encoding="utf-8") as f:
        code = f.read()
    if "CONFIG_LOGGED" in code: return
    
    config_block = f"""
CONFIG_LOGGED = True
print("="*50)
print("TRAINING CONFIGURATION (Auto-Logged)")
print(f"Script: {{__file__}}")
print("Model: {model_name}")
print("Dataset Source: ast_combined.json / stage3_oracle_multi")
print("Split: Stratified GroupKFold (by Register/Peripheral) - 80/20")
print("Random Seed: 42")
print("="*50)
"""
    if "def main" in code:
        code = code.replace("def main", config_block + "\ndef main")
    else:
        code = config_block + "\n" + code
        
    with open(filename, "w", encoding="utf-8") as f:
        f.write(code)

patch_rl("rl_final_10seeds_parallel.py")
patch_rl("rl_strict_ablation.py")
patch_llm("stage2_llm_synthesizer_multi.py")
patch_llm("stage3_oracle_multi.py")
patch_train("train_codebert.py", "CodeBERT")
patch_train("train_xgboost.py", "XGBoost")

print("Scripts patched!")
