import subprocess
import os

os.makedirs('stage7_final_logs', exist_ok=True)

for algo in range(6):
    for seed in range(1, 11):
        out_file = f"stage7_final_logs/algo_{algo}_seed_{seed}.log"
        print(f"Running Algo {algo} Seed {seed}...")
        subprocess.run(f"AGENT_ALGO={algo} ./bin_cons_scoped5 -runs=100000 -seed={seed} > {out_file} 2>&1", shell=True)

print("Done generating logs.")
