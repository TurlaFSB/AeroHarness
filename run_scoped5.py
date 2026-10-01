import subprocess

with open('fuzz_consolidated.c', 'r') as f:
    src = f.read()

src = src.replace('size_t get_new_coverage()', '__attribute__((no_sanitize("coverage"))) size_t get_new_coverage()')
src = src.replace('void dump_stats()', '__attribute__((no_sanitize("coverage"))) void dump_stats()')
src = src.replace('int LLVMFuzzerTestOneInput', '__attribute__((no_sanitize("coverage"))) int LLVMFuzzerTestOneInput')
src = src.replace('void dummy_irq_cb(struct device *dev) {', '__attribute__((no_sanitize("coverage"))) void dummy_irq_cb(struct device *dev) {')

with open('fuzz_cons_scoped5.c', 'w') as f:
    f.write(src)

subprocess.run('clang -O1 -g -fsanitize=fuzzer -fno-inline -I./fake_zephyr fuzz_cons_scoped5.c -o bin_cons_scoped5', shell=True)

for algo in range(6):
    runs = 100000
    out = subprocess.check_output(f'AGENT_ALGO={algo} ./bin_cons_scoped5 -runs={runs} -seed=1 2>&1 | grep FINAL_COV', shell=True, text=True)
    print(f'Algo {algo}:', out.strip())
