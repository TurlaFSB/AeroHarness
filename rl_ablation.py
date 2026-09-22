import os
import subprocess
import re
import shutil
import random
import time
import math

TARGETS = ["target_poll_in", "target_poll_out", "target_isr", "target_set_baudrate", "target_fifo_fill"]
REAL_MULTIPLIERS = [1.0, 3.0, 3.0, 1.0, 1.0]

# 3 different random assignments (2 targets get 3.0, rest 1.0)
RANDOM_ASSIGNMENTS = [
    [3.0, 1.0, 1.0, 3.0, 1.0],
    [1.0, 1.0, 3.0, 1.0, 3.0],
    [3.0, 1.0, 1.0, 1.0, 3.0]
]

def clean_corpora():
    for h in TARGETS:
        d = f"corpus_deep_{h}"
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)

def run_fuzzer(harness, runs=20):
    cmd = f"./deep_targets/{harness} corpus_deep_{harness} -runs={runs} -timeout=1"
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        output = res.stderr
    except Exception as e:
        output = str(e)
    ft = 0
    matches = re.findall(r'ft:\s*(\d+)', output)
    if matches:
        ft = int(matches[-1])
    return ft

def run_ucb1(seed, agent_multipliers, eval_multipliers, episodes=15, steps_per_episode=13):
    random.seed(seed)
    ucb_rewards = []
    
    for ep in range(episodes):
        clean_corpora()
        fts = [0] * len(TARGETS)
        tot_r_eval = 0
        
        pulls = [0] * len(TARGETS)
        total_rewards_agent = [0.0] * len(TARGETS)
        
        for step in range(steps_per_episode):
            total_pulls = step + 1
            unpulled = [i for i, p in enumerate(pulls) if p == 0]
            if unpulled:
                action = unpulled[0]
            else:
                ucb_scores = []
                for i in range(len(TARGETS)):
                    avg_reward = total_rewards_agent[i] / pulls[i]
                    exploration = math.sqrt(2 * math.log(total_pulls) / pulls[i])
                    ucb_scores.append(avg_reward + exploration)
                action = max(range(len(TARGETS)), key=ucb_scores.__getitem__)
                
            old_ft = fts[action]
            new_ft = max(old_ft, run_fuzzer(TARGETS[action], runs=20))
            fts[action] = new_ft
            
            r_agent = (new_ft - old_ft) * agent_multipliers[action]
            pulls[action] += 1
            total_rewards_agent[action] += r_agent
            
            r_eval = (new_ft - old_ft) * eval_multipliers[action]
            tot_r_eval += r_eval
            
        ucb_rewards.append(tot_r_eval)
        
    return ucb_rewards

def mean_std(data):
    n = len(data)
    mean = sum(data) / n
    variance = sum((x - mean) ** 2 for x in data) / n
    std = variance ** 0.5
    return mean, std

def get_t_and_p(x, y):
    nx = len(x)
    ny = len(y)
    mean_x, std_x = mean_std(x)
    mean_y, std_y = mean_std(y)
    
    dof = nx + ny - 2
    pool_var = ((nx-1)*(std_x**2) + (ny-1)*(std_y**2)) / dof
    if pool_var == 0: return 0.0, 1.0
    pool_sd = math.sqrt(pool_var)
    t_stat = (mean_x - mean_y) / (pool_sd * math.sqrt(1/nx + 1/ny))
    
    # We will just print the lists and calculate precise p-value in output if needed,
    # or return t-stat.
    return t_stat, pool_sd

def main():
    seeds = [111, 222, 333, 444, 555]
    print("Running Real-Uncertainty UCB1...")
    real_results = []
    for s in seeds:
        res = run_ucb1(s, REAL_MULTIPLIERS, REAL_MULTIPLIERS)
        real_results.append(res[-1])
        
    print("Running Random-Multiplier UCB1 across 3 assignments...")
    rand_results = []
    for assign in RANDOM_ASSIGNMENTS:
        for s in seeds:
            res = run_ucb1(s, assign, REAL_MULTIPLIERS)
            rand_results.append(res[-1])
            
    r_mean, r_std = mean_std(real_results)
    rand_mean, rand_std = mean_std(rand_results)
    
    t_stat, pool_sd = get_t_and_p(real_results, rand_results)
    cd = (r_mean - rand_mean) / pool_sd if pool_sd > 0 else 0
    
    print("\nRESULTS (Episode 15):")
    print(f"  Real-Uncertainty: {r_mean:.2f} +/- {r_std:.2f}")
    print(f"  Random-Multiplier: {rand_mean:.2f} +/- {rand_std:.2f}")
    print(f"  t-statistic: {t_stat:.4f}")
    print(f"  Cohen's d: {cd:.2f}")
    print(f"  Real raw: {real_results}")
    print(f"  Rand raw: {rand_results}")

if __name__ == "__main__":
    main()
