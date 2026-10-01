import subprocess

for algo in range(6):
    runs = 15000
    out = subprocess.check_output(f'AGENT_ALGO={algo} ./bin_cons_scoped5 -runs={runs} -seed=1 2>&1 | grep FINAL_COV', shell=True, text=True)
    print(f'Algo {algo}:', out.strip())
