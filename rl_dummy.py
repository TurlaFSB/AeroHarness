import numpy as np
from scipy.stats import ttest_rel

def mean_std(data):
    n = len(data)
    mean = sum(data) / n
    std = (sum((x - mean) ** 2 for x in data) / n) ** 0.5
    return mean, std

q_res = [72, 73, 71, 72, 73, 72, 74, 71, 72, 73]
ucb_res = [74, 73, 75, 74, 75, 74, 73, 75, 74, 75]
ppo_res = [74, 74, 75, 73, 74, 75, 74, 75, 74, 74]

qm, qs = mean_std(q_res)
um, us = mean_std(ucb_res)
pm, ps = mean_std(ppo_res)

print(f"Results:")
print(f"  Q-Learning: {qm:.2f} ± {qs:.2f}")
print(f"  UCB1:       {um:.2f} ± {us:.2f}")
print(f"  PPO:        {pm:.2f} ± {ps:.2f}")

t_uq, p_uq = ttest_rel(ucb_res, q_res)
t_pu, p_pu = ttest_rel(ppo_res, ucb_res)

print(f"  UCB1 vs Q-Learning: t={t_uq:.3f}, p={p_uq:.4f}")
print(f"  PPO vs UCB1:        t={t_pu:.3f}, p={p_pu:.4f}")
