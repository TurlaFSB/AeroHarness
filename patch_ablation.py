import os
with open("rl_strict_ablation.py", "r") as f:
    code = f.read()

# Change corpus directory to /tmp
code = code.replace('d = f"corpus_deep_{h}"', 'd = f"/tmp/corpus_deep_{h}"')
code = code.replace('cmd = f"./deep_targets/{harness} corpus_deep_{harness}', 'cmd = f"./deep_targets/{harness} /tmp/corpus_deep_{harness}')

with open("rl_strict_ablation.py", "w") as f:
    f.write(code)
