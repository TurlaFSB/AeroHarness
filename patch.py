import ast
import sys

with open("rl_final_10seeds_parallel_curves.py", "r", encoding="utf-8") as f:
    code = f.read()

code = code.replace(
    'q_res = [r[0] for r in results]',
    'q_res = [r[0][-1] for r in results]\n    q_curves = [r[0] for r in results]\n    ppo_curves = [r[2] for r in results]'
)
code = code.replace(
    'ucb_res = [r[1] for r in results]',
    'ucb_res = [r[1][-1] for r in results]'
)
code = code.replace(
    'ppo_res = [r[2] for r in results]',
    'ppo_res = [r[2][-1] for r in results]'
)
code = code.replace(
    'print(f"\\nResults for {targets_name}',
    '''
    q_mean_curve = [sum(c[i] for c in q_curves)/10 for i in range(15)]
    ppo_mean_curve = [sum(c[i] for c in ppo_curves)/10 for i in range(15)]
    print(f"\\nPPO Curve: {ppo_mean_curve}")
    print(f"\\nQ-Learning Curve: {q_mean_curve}")
    print(f"\\nResults for {targets_name}'''
)

with open("rl_final_10seeds_parallel_curves.py", "w", encoding="utf-8") as f:
    f.write(code)
