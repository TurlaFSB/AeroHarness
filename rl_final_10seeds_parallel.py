import os
import subprocess
import re
import shutil
import random
import time
import math
import numpy as np
from multiprocessing import Pool

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
import gymnasium as gym
from gymnasium import spaces
from scipy.stats import ttest_rel

# N=5 Targets
TARGETS_5 = [
    ("target_poll_in", 1.0, "deep_targets"),
    ("target_poll_out", 3.0, "deep_targets"),
    ("target_isr", 3.0, "deep_targets"),
    ("target_set_baudrate", 1.0, "deep_targets"),
    ("target_fifo_fill", 1.0, "deep_targets")
]

# N=12 Targets
TARGETS_12 = [
    ("target_poll_in_sbsa", 1.0, "targets"),
    ("target_poll_in_cr_uarten", 1.0, "targets"),
    ("target_poll_in_cr_rxe", 1.0, "targets"),
    ("target_poll_in_fr_rxfe", 1.0, "targets"),
    ("target_poll_in_dr", 1.0, "targets"),
    ("target_poll_out_fr_txff", 3.0, "targets"),
    ("target_poll_out_dr", 1.0, "targets"),
    ("target_isr_ctsmim", 1.0, "targets"),
    ("target_isr_error", 1.0, "targets"),
    ("target_isr_w1c_clobber", 3.0, "targets"),
    ("target_isr_imsc", 1.0, "targets"),
    ("target_isr_irq_cb", 1.0, "targets")
]

def clean_corpora(targets, seed):
    for h, _, _ in targets:
        d = f"/tmp/corpus_final_{seed}_{h}"
        if os.path.exists(d):
            shutil.rmtree(d)
        os.makedirs(d)

def run_fuzzer(harness, folder, lf_seed, base_seed, runs=20):
    cmd = f"./{folder}/{harness} /tmp/corpus_final_{base_seed}_{harness} -runs={runs} -timeout=1 -seed={lf_seed}"
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

class FuzzEnv(gym.Env):
    def __init__(self, targets, base_seed, steps_per_episode):
        super(FuzzEnv, self).__init__()
        self.targets = targets
        self.num_targets = len(targets)
        self.action_space = spaces.Discrete(self.num_targets)
        self.observation_space = spaces.Box(low=0, high=1000, shape=(self.num_targets,), dtype=np.float32)
        
        self.base_seed = base_seed
        self.steps_per_episode = steps_per_episode
        
        self.current_episode = -1
        self.current_step = 0
        self.fts = [0] * self.num_targets
        
        self.episode_rewards = []
        self.current_ep_reward = 0.0

    def reset(self, seed=None, options=None):
        if seed is not None:
            self.base_seed = seed
        self.current_episode += 1
        self.current_step = 0
        self.fts = [0] * self.num_targets
        clean_corpora(self.targets, self.base_seed)
        if self.current_episode > 0:
            self.episode_rewards.append(self.current_ep_reward)
        self.current_ep_reward = 0.0
        return np.array([f / 5.0 for f in self.fts], dtype=np.float32), {}

    def step(self, action):
        harness, multiplier, folder = self.targets[action]
        old_ft = self.fts[action]
        lf_seed = self.base_seed + self.current_episode * 1000 + self.current_step
        
        new_ft = max(old_ft, run_fuzzer(harness, folder, lf_seed, self.base_seed, runs=20))
        self.fts[action] = new_ft
        
        reward = (new_ft - old_ft) * multiplier
        self.current_ep_reward += reward
        
        self.current_step += 1
        terminated = False
        truncated = bool(self.current_step >= self.steps_per_episode)
        
        obs = np.array([f / 5.0 for f in self.fts], dtype=np.float32)
        return obs, reward, terminated, truncated, {}

def run_q_learning(targets, base_seed, episodes, steps_per_episode):
    random.seed(base_seed)
    q_table = {}
    rewards = []
    
    for ep in range(episodes):
        clean_corpora(targets, base_seed)
        fts = [0] * len(targets)
        tot_r = 0.0
        
        state = tuple([f // 5 for f in fts])
        eps = max(0.05, 0.5 - (ep * 0.03)) 
        
        for step in range(steps_per_episode):
            if state not in q_table:
                q_table[state] = [0.0] * len(targets)

            if random.random() < eps:
                action = random.randint(0, len(targets)-1)
            else:
                action = max(range(len(targets)), key=q_table[state].__getitem__)
                
            harness, multiplier, folder = targets[action]
            old_ft = fts[action]
            lf_seed = base_seed + ep * 1000 + step
            new_ft = max(old_ft, run_fuzzer(harness, folder, lf_seed, base_seed, runs=20))
            fts[action] = new_ft
            
            r = (new_ft - old_ft) * multiplier
            tot_r += r
            
            next_state = tuple([f // 5 for f in fts])
            if next_state not in q_table:
                q_table[next_state] = [0.0] * len(targets)
            
            old_q = q_table[state][action]
            best_next = max(q_table[next_state])
            q_table[state][action] = old_q + 0.3 * (r + 0.9 * best_next - old_q)
            
            state = next_state
            
        rewards.append(tot_r)
    return rewards[-1]

def run_ucb1(targets, base_seed, episodes, steps_per_episode):
    random.seed(base_seed)
    rewards = []
    
    for ep in range(episodes):
        clean_corpora(targets, base_seed)
        fts = [0] * len(targets)
        tot_r = 0.0
        
        pulls = [0] * len(targets)
        total_rewards_agent = [0.0] * len(targets)
        
        for step in range(steps_per_episode):
            total_pulls = step + 1
            unpulled = [i for i, p in enumerate(pulls) if p == 0]
            if unpulled:
                action = unpulled[0]
            else:
                ucb_scores = []
                for i in range(len(targets)):
                    avg_reward = total_rewards_agent[i] / pulls[i]
                    exploration = math.sqrt(2 * math.log(total_pulls) / pulls[i])
                    ucb_scores.append(avg_reward + exploration)
                action = max(range(len(targets)), key=ucb_scores.__getitem__)
                
            harness, multiplier, folder = targets[action]
            old_ft = fts[action]
            lf_seed = base_seed + ep * 1000 + step
            new_ft = max(old_ft, run_fuzzer(harness, folder, lf_seed, base_seed, runs=20))
            fts[action] = new_ft
            
            r = (new_ft - old_ft) * multiplier
            tot_r += r
            
            pulls[action] += 1
            total_rewards_agent[action] += r
            
        rewards.append(tot_r)
    return rewards[-1]

def run_ppo(targets, base_seed, episodes, steps_per_episode):
    env = FuzzEnv(targets, base_seed, steps_per_episode)
    model = PPO("MlpPolicy", env, n_steps=steps_per_episode, batch_size=steps_per_episode, 
                n_epochs=4, ent_coef=0.1, seed=base_seed, verbose=0)
    
    model.learn(total_timesteps=steps_per_episode * episodes)
    env.episode_rewards.append(env.current_ep_reward) 
    return env.episode_rewards[:episodes][-1]

def run_seed_eval(args):
    targets, steps_per_episode, s = args
    episodes = 15
    q = run_q_learning(targets, s, episodes, steps_per_episode)
    ucb = run_ucb1(targets, s, episodes, steps_per_episode)
    ppo = run_ppo(targets, s, episodes, steps_per_episode)
    return (q, ucb, ppo)

def mean_std(data):
    n = len(data)
    mean = sum(data) / n
    std = (sum((x - mean) ** 2 for x in data) / n) ** 0.5
    return mean, std

def run_all(targets_name, targets, steps_per_episode):
    print(f"\n--- Running {targets_name} (10 seeds) ---")
    seeds = [111, 222, 333, 444, 555, 666, 777, 888, 999, 1010]
    
    t0 = time.time()
    args = [(targets, steps_per_episode, s) for s in seeds]
    
    with Pool(processes=10) as pool:
        results = pool.map(run_seed_eval, args)
        
    q_res = [r[0] for r in results]
    ucb_res = [r[1] for r in results]
    ppo_res = [r[2] for r in results]
    
    print(f"Finished {targets_name} in {time.time()-t0:.1f}s")
    
    qm, qs = mean_std(q_res)
    um, us = mean_std(ucb_res)
    pm, ps = mean_std(ppo_res)
    
    print(f"\nResults for {targets_name} (Episode 15 Final Reward):")
    print(f"  Q-Learning: {qm:.2f} +/- {qs:.2f}")
    print(f"  UCB1:       {um:.2f} +/- {us:.2f}")
    print(f"  PPO:        {pm:.2f} +/- {ps:.2f}")
    
    t_uq, p_uq = ttest_rel(ucb_res, q_res)
    t_pu, p_pu = ttest_rel(ppo_res, ucb_res)
    
    print("\nPaired t-tests (Holm-Bonferroni omitted for simplicity, showing raw p-values):")
    print(f"  UCB1 vs Q-Learning: t={t_uq:.3f}, p={p_uq:.4f}")
    print(f"  PPO vs UCB1:        t={t_pu:.3f}, p={p_pu:.4f}")
    
    return q_res, ucb_res, ppo_res

def main():
    print("Hypothesis: PPO will be constrained by the same Coupon Collector limit as Q-learning and UCB1. "
          "Target saturation speed, not algorithm sophistication, bounds performance.")
    
    run_all("N=12 Shallow Set", TARGETS_12, steps_per_episode=32)
    run_all("N=5 Deep Set", TARGETS_5, steps_per_episode=13)

if __name__ == "__main__":
    main()
