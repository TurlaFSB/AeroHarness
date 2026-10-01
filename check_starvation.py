import os, subprocess, re, shutil, random, math

TARGETS = ["poll_in", "poll_out", "isr", "set_baudrate", "fifo_fill"]
HARNESSES = ["target_" + t for t in TARGETS]

def run_fuzzer(harness, lf_seed, runs=20):
    cmd = f"./deep_targets/{harness} corpus_deep_{harness} -runs={runs} -timeout=1 -seed={lf_seed}"
    try:
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return int(re.findall(r'ft:\s*(\d+)', res.stderr)[-1]) if re.findall(r'ft:\s*(\d+)', res.stderr) else 0
    except:
        return 0

def run_log_episode(name, base_seed, multipliers, target_ep=15, steps_per_episode=13):
    print(f"\n--- Logging {name} (Seed {base_seed}, Mult: {multipliers}) ---")
    random.seed(base_seed)
    
    for ep in range(target_ep):
        for h in HARNESSES:
            d = f"corpus_deep_{h}"
            if os.path.exists(d): shutil.rmtree(d)
            os.makedirs(d)
            
        fts = [0] * 5
        pulls = [0] * 5
        total_rewards_agent = [0.0] * 5
        
        # Only print details for the last episode
        log_this_ep = (ep == target_ep - 1)
        if log_this_ep:
            print(f"Episode {ep+1} Target Selection Log:")
            
        for step in range(steps_per_episode):
            total_pulls = step + 1
            unpulled = [i for i, p in enumerate(pulls) if p == 0]
            if unpulled:
                action = unpulled[0]
            else:
                ucb_scores = []
                for i in range(5):
                    avg_reward = total_rewards_agent[i] / pulls[i]
                    exploration = math.sqrt(2 * math.log(total_pulls) / pulls[i])
                    ucb_scores.append(avg_reward + exploration)
                action = max(range(5), key=ucb_scores.__getitem__)
                
            old_ft = fts[action]
            lf_seed = base_seed + ep * 1000 + step
            new_ft = max(old_ft, run_fuzzer(HARNESSES[action], lf_seed, runs=20))
            fts[action] = new_ft
            
            r_agent = (new_ft - old_ft) * multipliers[action]
            
            if log_this_ep:
                print(f"  Step {step+1:2d} | Picked: {TARGETS[action]:12s} | New FT: {new_ft-old_ft:2d} | Agent Reward: {r_agent:5.1f} | Tot Pulls of this target: {pulls[action]+1}")
                
            pulls[action] += 1
            total_rewards_agent[action] += r_agent

    print("Final Pull Counts:", dict(zip(TARGETS, pulls)))
    print("Final Features Found:", dict(zip(TARGETS, fts)))

# A1: poll_in and set_baudrate get 3.0
run_log_episode("Random-Multiplier A1", 333, [3.0, 1.0, 1.0, 3.0, 1.0])

# Real: poll_out and isr get 3.0
run_log_episode("Real-Uncertainty", 333, [1.0, 3.0, 3.0, 1.0, 1.0])
