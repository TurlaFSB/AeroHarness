import os
for filename in ["stage2_llm_synthesizer_multi.py", "stage3_oracle_multi.py"]:
    with open(filename, "r") as f:
        code = f.read()
    code = code.replace('if __name__ == "__main__":\n\nCONFIG_LOGGED = True', 'CONFIG_LOGGED = True')
    with open(filename, "w") as f:
        f.write(code)
