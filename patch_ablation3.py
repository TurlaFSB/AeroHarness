import os
with open("rl_strict_ablation.py", "r") as f:
    code = f.read()

new_main = """
def main():
    seeds = [111, 222, 333, 444, 555]
    print("Running STRICT PAIRED Real-Uncertainty UCB1...")
    real_results = []
    for s in seeds:
        res = run_ucb1(s, REAL_MULTIPLIERS, REAL_MULTIPLIERS)
        real_results.append(res[-1])
        
    print("Running STRICT PAIRED Random-Multiplier UCB1 across 3 assignments...")
    rand_results = []
    for assign in RANDOM_ASSIGNMENTS:
        for s in seeds:
            res = run_ucb1(s, assign, REAL_MULTIPLIERS)
            rand_results.append(res[-1])
            
    r_mean, r_std = mean_std(real_results)
    rand_mean, rand_std = mean_std(rand_results)
    
    t_stat, pool_sd = get_t_and_p(real_results, rand_results)
    cd = (r_mean - rand_mean) / pool_sd if pool_sd > 0 else 0
    
    print("\\nSTRICT RESULTS (Episode 15):")
    print(f"  Real-Uncertainty: {r_mean:.2f} +/- {r_std:.2f}")
    print(f"  Random-Multiplier: {rand_mean:.2f} +/- {rand_std:.2f}")
    print(f"  t-statistic: {t_stat:.4f}")
    print(f"  Cohen's d: {cd:.2f}")
    print(f"  Real raw: {real_results}")
    print(f"  Rand raw: {rand_results}")
"""

code = code[:code.find('from multiprocessing import Pool')] + new_main + '\nif __name__ == "__main__":\n    main()\n'

# Just to be safe with clean_corpora
code = code.replace('os.makedirs(d)', 'os.makedirs(d, exist_ok=True)')

with open("rl_strict_ablation.py", "w") as f:
    f.write(code)
