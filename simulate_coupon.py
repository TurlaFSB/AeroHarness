import random

seeds = [111, 222, 333, 444, 555]

def get_steps_to_cover(seed, N):
    random.seed(seed)
    covered = set()
    steps = 0
    while len(covered) < N:
        action = random.randint(0, N-1)
        covered.add(action)
        steps += 1
    return steps

def run_sim(N):
    steps_list = []
    for s in seeds:
        steps = get_steps_to_cover(s, N)
        steps_list.append(steps)
        
    mean = sum(steps_list) / len(steps_list)
    variance = sum((x - mean) ** 2 for x in steps_list) / (len(steps_list) - 1) if len(steps_list) > 1 else 0
    std = variance ** 0.5
    
    # theoretical
    H_n = sum(1.0/i for i in range(1, N+1))
    theo = N * H_n
    
    print(f"N={N}")
    print(f"  Theoretical: {theo:.2f}")
    print(f"  Actual Mean: {mean:.2f} +/- {std:.2f}")
    print(f"  Raw values: {steps_list}")
    print()

run_sim(5)
run_sim(12)
