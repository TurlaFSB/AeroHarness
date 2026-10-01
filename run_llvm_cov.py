import subprocess
import os

with open('fuzz_consolidated.c', 'r') as f:
    src = f.read()

# We need the pure original fuzz_consolidated.c without no_sanitize, but wait!
# If we compile with llvm-cov, it will track coverage for EVERYTHING, but llvm-cov lets us FILTER the report by filename!
# So we can just compile fuzz_consolidated.c as-is, and then run `llvm-cov report bin_cov -instr-profile=xxx.profdata uart_pl011.c` !!
# This is the beauty of llvm-cov! It tracks per-file coverage natively.

# Let's write the exact original back to fuzz_clean.c
with open('fuzz_clean.c', 'w') as f:
    f.write(src.replace('__attribute__((no_sanitize("coverage"))) ', ''))

# Compile with profile generation
subprocess.run('clang -O0 -g -fprofile-instr-generate -fcoverage-mapping -fsanitize=fuzzer -I./fake_zephyr fuzz_clean.c -o bin_cov', shell=True, check=True)

# Run for all 6 algos
for algo in range(6):
    print(f"\\n=== ALGO {algo} ===")
    
    # Run
    profraw = f"algo_{algo}.profraw"
    profdata = f"algo_{algo}.profdata"
    env = os.environ.copy()
    env['AGENT_ALGO'] = str(algo)
    env['LLVM_PROFILE_FILE'] = profraw
    
    subprocess.run(f'./bin_cov -runs=100000 -seed=1', shell=True, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Merge
    subprocess.run(f'llvm-profdata merge -sparse {profraw} -o {profdata}', shell=True, check=True)
    
    # Report
    # We want to see region/branch coverage for uart_pl011.c only
    out = subprocess.check_output(f'llvm-cov report ./bin_cov -instr-profile={profdata} | grep uart_pl011.c', shell=True, text=True)
    print(out.strip())
