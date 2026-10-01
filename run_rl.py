import os
import subprocess
import numpy as np
from scipy import stats
import re

# We will read fuzz_state_machine.c, extract the stubs and driver code, and append our RL logic.
with open("fuzz_state_machine.c", "r") as f:
    orig_code = f.read()

# Find the start of LLVMFuzzerTestOneInput
fuzzer_idx = orig_code.find("int LLVMFuzzerTestOneInput")
stubs_code = orig_code[:fuzzer_idx]

rl_code = """
#include <stdio.h>
#include <math.h>
#include <stdlib.h>

extern uint8_t __start___sancov_cntrs[] __attribute__((weak));
extern uint8_t __stop___sancov_cntrs[] __attribute__((weak));
size_t get_coverage() {
    size_t cov = 0;
    if (__start___sancov_cntrs) {
        for (uint8_t *p = __start___sancov_cntrs; p < __stop___sancov_cntrs; p++) {
            if (*p) cov++;
        }
    }
    return cov;
}

#define NUM_STATES 100 // 2 (is_init) * 5 (prev_cmd) * 10 (step)
#define NUM_ACTIONS 4  // 0=init, 1=poll_in, 2=poll_out, 3=isr
#define MAX_STEPS 10

static float Q[NUM_STATES][NUM_ACTIONS] = {0};
static int N_s[NUM_STATES] = {0};
static int N_sa[NUM_STATES][NUM_ACTIONS] = {0};
static float V[NUM_STATES][NUM_ACTIONS] = {0}; // empirical mean reward

// Uncertainty weights from Stage 3 data (approximate based on prompt logic)
// init: cr, imsc, icr, dmacr, ifls -> high uncertainty
// poll_in: dr, fr -> moderate
// poll_out: dr, fr -> moderate
// isr: mis, icr, imsc -> high
static const float U_weights[4] = {0.8, 0.4, 0.4, 0.7};

static unsigned long long total_executions = 0;

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 1) return 0;
    
    struct pl011_data pl_data; memset(&pl_data, 0, sizeof(pl_data));
    struct pl011_config pl_config; memset(&pl_config, 0, sizeof(pl_config));
    struct pl011_regs regs; memset(&regs, 0, sizeof(regs));
    
    pl_data.sbsa = 0;
    pl_data.clk_freq = 4000000;
    pl_config.fifo_disable = false;
    pl_data.irq_cb = dummy_irq_cb;
    
    mock_regs_ptr = &regs;
    struct device dev; 
    dev.data = &pl_data;
    dev.config = &pl_config;
    
    bool is_initialized = false;
    int last_cmd = 0; // 0=none, 1=init, 2=read, 3=write, 4=isr
    size_t data_idx = 0;
    
    total_executions++;
    
    for (int step = 0; step < MAX_STEPS; step++) {
        int state = (is_initialized ? 1 : 0) * 50 + last_cmd * 10 + step;
        uint8_t cmd;
        
        static bool seeded = false;
        if (!seeded) {
            char *env_seed = getenv("AGENT_SEED");
            if (env_seed) srand(atoi(env_seed));
            seeded = true;
        }
        
#ifdef MODE_RANDOM
        cmd = rand() % 4;
#elif defined(MODE_CONSTRAINED_RANDOM)
        if (!is_initialized) {
            cmd = 0;
        } else {
            cmd = rand() % 4;
        }
#elif defined(MODE_QLEARNING)
        float epsilon = 1.0f / (1.0f + (total_executions / 1000.0f));
        if ((rand() % 10000) / 10000.0f < epsilon) {
            cmd = rand() % 4;
        } else {
            cmd = 0; float best_q = Q[state][0];
            for (int a = 1; a < 4; a++) {
                if (Q[state][a] > best_q) { best_q = Q[state][a]; cmd = a; }
            }
        }
#elif defined(MODE_UCB1)
        if (N_s[state] < 4) {
            cmd = N_s[state]; // Try each action once
        } else {
            cmd = 0; float best_ucb = -1e9;
            for (int a = 0; a < 4; a++) {
                float ucb = V[state][a] + 1.0f * sqrtf(logf(N_s[state]) / (N_sa[state][a]));
                if (ucb > best_ucb) { best_ucb = ucb; cmd = a; }
            }
        }
#endif
        
        // Supply payload data from fuzzer input
        if (data_idx + 1 < size) {
            regs.dr = data[data_idx];
            regs.fr = data[data_idx];
            regs.fr &= ~PL011_FR_TXFF; 
            data_idx++;
        }
        
        size_t features_before = get_coverage();
        
        if (cmd == 0) {
            pl011_init(&dev);
            is_initialized = true;
            last_cmd = 1;
        } else if (cmd == 1) {
            if (is_initialized) { unsigned char c = 0; pl011_poll_in(&dev, &c); }
            last_cmd = 2;
        } else if (cmd == 2) {
            if (is_initialized && data_idx < size) { pl011_poll_out(&dev, data[data_idx++]); }
            last_cmd = 3;
        } else if (cmd == 3) {
            if (is_initialized && data_idx + 1 < size) {
                regs.mis = data[data_idx];
                regs.imsc = data[data_idx];
                data_idx++;
            }
            if (is_initialized) { pl011_isr(&dev); }
            last_cmd = 4;
        }
        
        size_t features_after = get_coverage();
        long long delta = (long long)features_after - (long long)features_before;
        if (delta < 0) delta = 0; // Prevent underflow from 8-bit coverage counter wrap-around
        float reward = (float)delta * (1.0f + U_weights[cmd]);
        
        // Prerequisite violation penalty!
        if (!is_initialized && cmd != 0) {
            reward = -1.0f;
        }
        
        static size_t max_cov = 0;
        if (features_after > max_cov) {
            max_cov = features_after;
            printf("MAX_COV: %zu\\n", max_cov);
        }
        
#ifdef MODE_QLEARNING
        float next_max_q = 0;
        if (step + 1 < MAX_STEPS) {
            int next_state = (is_initialized ? 1 : 0) * 50 + last_cmd * 10 + (step + 1);
            next_max_q = Q[next_state][0];
            for(int a=1; a<4; a++) if (Q[next_state][a] > next_max_q) next_max_q = Q[next_state][a];
        }
        Q[state][cmd] += 0.1f * (reward + 0.9f * next_max_q - Q[state][cmd]);
#elif defined(MODE_UCB1)
        N_s[state]++;
        N_sa[state][cmd]++;
        V[state][cmd] += (reward - V[state][cmd]) / N_sa[state][cmd];
#endif
    }
    
    return 0;
}
"""

with open("fuzz_rl.c", "w") as f:
    f.write(stubs_code + "\n" + rl_code)

def run_experiment():
    modes = [("Random", "-DMODE_RANDOM"), ("Constrained-Random", "-DMODE_CONSTRAINED_RANDOM"), ("Q-Learning", "-DMODE_QLEARNING"), ("UCB1", "-DMODE_UCB1")]
    results = {m[0]: [] for m in modes}
    
    for mode_name, mode_flag in modes:
        print(f"Compiling {mode_name}...")
        # Compile
        compile_cmd = f"clang -O1 -g -fsanitize=fuzzer -I./fake_zephyr {mode_flag} fuzz_rl.c -o fuzz_{mode_name.replace('-', '').lower()}"
        subprocess.run(compile_cmd, shell=True, check=True)
        
        for seed in range(1, 11):
            print(f"Running {mode_name} seed {seed}...")
            run_cmd = f"./fuzz_{mode_name.replace('-', '').lower()} -runs=100000 -seed={seed} -use_value_profile=0 2>&1"
            
            # Generate a distinct seed for the LCG based on mode and replicate
            mode_hash = sum(ord(c) for c in mode_name)
            env = os.environ.copy()
            env["AGENT_SEED"] = str(seed * 1000 + mode_hash)
            
            out = subprocess.check_output(run_cmd, shell=True, env=env).decode("utf-8", errors="ignore")
            
            max_covs = re.findall(r"MAX_COV:\s*(\d+)", out)
            
            if max_covs:
                results[mode_name].append(int(max_covs[-1]))
            else:
                results[mode_name].append(0)
                
    print("\nRESULTS:")
    print(results)
    
    import json
    with open("rl_state_machine_raw_seeds.json", "w") as f:
        json.dump(results, f, indent=4)
        
    # Calculate stats
    base = results["Random"]
    base_mean = np.mean(base)
    base_std = np.std(base)
    print(f"Random baseline: {base_mean:.2f} ± {base_std:.2f}")
    
    for mode in ["Q-Learning", "UCB1"]:
        vals = results[mode]
        mean = np.mean(vals)
        std = np.std(vals)
        
        if np.std(base) == 0 and std == 0:
            print(f"{mode}: {mean:.2f} ± {std:.2f}, (Deterministic convergence, p-value N/A)")
        else:
            t, p = stats.ttest_rel(vals, base)
            diff = np.array(vals) - np.array(base)
            d = np.mean(diff) / (np.std(diff, ddof=1) + 1e-8)
            print(f"{mode}: {mean:.2f} ± {std:.2f}, p-value vs random: {p:.4e}, Cohen's d: {d:.2f}")

if __name__ == "__main__":
    run_experiment()
