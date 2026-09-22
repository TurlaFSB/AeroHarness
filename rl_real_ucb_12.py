import os
import subprocess
import re
import shutil
import random
import time
import math

TARGETS = [
    ("target_poll_in_sbsa", 1.0),
    ("target_poll_in_cr_uarten", 1.0),
    ("target_poll_in_cr_rxe", 1.0),
    ("target_poll_in_fr_rxfe", 1.0),
    ("target_poll_in_dr", 1.0),
    ("target_poll_out_fr_txff", 3.0),
    ("target_poll_out_dr", 1.0),
    ("target_isr_ctsmim", 1.0),
    ("target_isr_error", 1.0),
    ("target_isr_w1c_clobber", 3.0),
    ("target_isr_imsc", 1.0),
    ("target_isr_irq_cb", 1.0)
]

HARNESSES = [t[0] for t in TARGETS]
MULTIPLIERS = [t[1] for t in TARGETS]

def clean_corpora():
    for h in HARNESSES:
        d = f"corpus_{h}"
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)

def run_fuzzer(harness, runs=20):
    cmd = f"./targets/{harness} corpus_{harness} -runs={runs} -timeout=1"
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

def run_experiment(seed, episodes=15, steps_per_episode=32):
    random.seed(seed)
    
    # Random Baseline
    rand_rewards = []
    for ep in range(episodes):
        clean_corpora()
        fts = [0] * len(HARNESSES)
        tot_r = 0
        for step in range(steps_per_episode):
            action = random.randint(0, len(HARNESSES)-1)
            old_ft = fts[action]
            new_ft = max(old_ft, run_fuzzer(HARNESSES[action], runs=20))
            fts[action] = new_ft
            tot_r += (new_ft - old_ft) * MULTIPLIERS[action]
        rand_rewards.append(tot_r)
        
    # UCB1 Agent
    ucb_rewards = []
    # UCB state is continuous over the episode
    for ep in range(episodes):
        clean_corpora()
        fts = [0] * len(HARNESSES)
        tot_r = 0
        
        pulls = [0] * len(HARNESSES)
        total_rewards = [0.0] * len(HARNESSES)
        
        for step in range(steps_per_episode):
            total_pulls = step + 1
            
            # First, pull each arm once to initialize
            unpulled = [i for i, p in enumerate(pulls) if p == 0]
            if unpulled:
                action = unpulled[0]
            else:
                ucb_scores = []
                for i in range(len(HARNESSES)):
                    avg_reward = total_rewards[i] / pulls[i]
                    exploration = math.sqrt(2 * math.log(total_pulls) / pulls[i])
                    ucb_scores.append(avg_reward + exploration)
                action = max(range(len(HARNESSES)), key=ucb_scores.__getitem__)
                
            old_ft = fts[action]
            new_ft = max(old_ft, run_fuzzer(HARNESSES[action], runs=20))
            fts[action] = new_ft
            
            r = (new_ft - old_ft) * MULTIPLIERS[action]
            tot_r += r
            
            pulls[action] += 1
            total_rewards[action] += r
            
        ucb_rewards.append(tot_r)
        
    return rand_rewards, ucb_rewards

def mean_std(data):
    n = len(data)
    mean = sum(data) / n
    variance = sum((x - mean) ** 2 for x in data) / n
    std = variance ** 0.5
    return mean, std

def main():
    print("Starting REAL 12-target UCB1 libFuzzer experiment (5 seeds, 15 episodes)...")
    seeds = [111, 222, 333, 444, 555]
    episodes = 15
    
    all_rand = []
    all_ucb = []
    
    t0 = time.time()
    for s in seeds:
        print(f"Running seed {s}...", flush=True)
        rr, rlr = run_experiment(s, episodes=episodes, steps_per_episode=32)
        all_rand.append(rr)
        all_ucb.append(rlr)
    print(f"Finished in {time.time()-t0:.1f}s")
    
    for pt in [5, 10, 15]:
        rand_at_pt = [seed_data[pt-1] for seed_data in all_rand]
        ucb_at_pt = [seed_data[pt-1] for seed_data in all_ucb]
        
        r_mean, r_std = mean_std(rand_at_pt)
        ucb_mean, ucb_std = mean_std(ucb_at_pt)
        
        print(f"Episode {pt} (Average across 5 seeds):")
        print(f"  Random: {r_mean:.2f} +/- {r_std:.2f}")
        print(f"  UCB1:   {ucb_mean:.2f} +/- {ucb_std:.2f}")

if __name__ == "__main__":
    main()
