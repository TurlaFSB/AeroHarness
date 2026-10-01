import rl_real_12
random = rl_real_12.random

def run_experiment_q(seed, episodes=15, steps_per_episode=32):
    random.seed(seed)
    
    # RL Agent
    rl_rewards = []
    q_table = {}
    for ep in range(episodes):
        rl_real_12.clean_corpora()
        fts = [0] * len(rl_real_12.HARNESSES)
        tot_r = 0
        state = rl_real_12.get_state(fts)
        eps = max(0.05, 0.5 - (ep * 0.03)) 
        
        for step in range(steps_per_episode):
            if state not in q_table:
                q_table[state] = [0.0] * len(rl_real_12.HARNESSES)

            if random.random() < eps:
                action = random.randint(0, len(rl_real_12.HARNESSES)-1)
            else:
                action = max(range(len(rl_real_12.HARNESSES)), key=q_table[state].__getitem__)
                
            old_ft = fts[action]
            new_ft = max(old_ft, rl_real_12.run_fuzzer(rl_real_12.HARNESSES[action], runs=20))
            fts[action] = new_ft
            
            r = (new_ft - old_ft) * rl_real_12.MULTIPLIERS[action]
            tot_r += r
            
            next_state = rl_real_12.get_state(fts)
            if next_state not in q_table:
                q_table[next_state] = [0.0] * len(rl_real_12.HARNESSES)
            
            old_q = q_table[state][action]
            best_next = max(q_table[next_state])
            q_table[state][action] = old_q + 0.3 * (r + 0.9 * best_next - old_q)
            
            state = next_state
    
    return q_table

print("Running seed 111 to get Q-table...")
q = run_experiment_q(111, 15, 32)
for state, values in q.items():
    print(f"State: {state}")
    for i, v in enumerate(values):
        print(f"  {rl_real_12.HARNESSES[i]}: {v:.2f}")
