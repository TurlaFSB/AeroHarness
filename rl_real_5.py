import os
import subprocess
import re
import shutil
import random
import time

TARGETS = [
    ("target_poll_in", 1.0),
    ("target_poll_out", 3.0),
    ("target_isr", 3.0),
    ("target_set_baudrate", 1.0),
    ("target_fifo_fill", 1.0)
]

HARNESSES = [t[0] for t in TARGETS]
MULTIPLIERS = [t[1] for t in TARGETS]

def clean_corpora():
    for h in HARNESSES:
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

def get_state(fts):
    return tuple([f // 5 for f in fts])

def run_experiment(seed, episodes=15, steps_per_episode=13):
    random.seed(seed)
    
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
        
    rl_rewards = []
    q_table = {}
    for ep in range(episodes):
        clean_corpora()
        fts = [0] * len(HARNESSES)
        tot_r = 0
        state = get_state(fts)
        eps = max(0.05, 0.5 - (ep * 0.03)) 
        
        for step in range(steps_per_episode):
            if state not in q_table:
                q_table[state] = [0.0] * len(HARNESSES)

            if random.random() < eps:
                action = random.randint(0, len(HARNESSES)-1)
            else:
                action = max(range(len(HARNESSES)), key=q_table[state].__getitem__)
                
            old_ft = fts[action]
            new_ft = max(old_ft, run_fuzzer(HARNESSES[action], runs=20))
            fts[action] = new_ft
            
            r = (new_ft - old_ft) * MULTIPLIERS[action]
            tot_r += r
            
            next_state = get_state(fts)
            if next_state not in q_table:
                q_table[next_state] = [0.0] * len(HARNESSES)
            
            old_q = q_table[state][action]
            best_next = max(q_table[next_state])
            q_table[state][action] = old_q + 0.3 * (r + 0.9 * best_next - old_q)
            
            state = next_state
            
        rl_rewards.append(tot_r)
        
    return rand_rewards, rl_rewards

def mean_std(data):
    n = len(data)
    mean = sum(data) / n
    variance = sum((x - mean) ** 2 for x in data) / n
    std = variance ** 0.5
    return mean, std

def main():
    print("Starting REAL 5-deep-target libFuzzer experiment (5 seeds, 15 episodes)...")
    seeds = [111, 222, 333, 444, 555]
    episodes = 15
    
    all_rand = []
    all_rl = []
    
    t0 = time.time()
    for s in seeds:
        print(f"Running seed {s}...", flush=True)
        rr, rlr = run_experiment(s, episodes=episodes, steps_per_episode=13)
        all_rand.append(rr)
        all_rl.append(rlr)
    print(f"Finished in {time.time()-t0:.1f}s")
    
    for pt in [5, 10, 15]:
        rand_at_pt = [seed_data[pt-1] for seed_data in all_rand]
        rl_at_pt = [seed_data[pt-1] for seed_data in all_rl]
        
        r_mean, r_std = mean_std(rand_at_pt)
        rl_mean, rl_std = mean_std(rl_at_pt)
        
        print(f"Episode {pt} (Average across 5 seeds):")
        print(f"  Random: {r_mean:.2f} +/- {r_std:.2f}")
        print(f"  RL:     {rl_mean:.2f} +/- {rl_std:.2f}")

    print("\nGetting feature counts for a single blank run of each target:")
    for h in HARNESSES:
        clean_corpora()
        ft = run_fuzzer(h, runs=100)
        print(f"  {h}: ~{ft} features max")

if __name__ == "__main__":
    main()
