import os, sys, time, json, subprocess, shutil
from datetime import datetime

TARGETS = {
    "pl011_poll_in": """Write a libFuzzer harness in C++ for the function 'pl011_poll_in' from Zephyr PL011.
You must mock the MMIO registers using a static struct and include an LLVMFuzzerTestOneInput function.

Here is the source of the driver target function:
```c
static int pl011_poll_in(const struct device *dev, unsigned char *c)
{
	volatile struct pl011_regs *uart = get_uart(dev);

	if (uart->fr & PL011_FR_RXFE) {
		return -1;
	}

	*c = (unsigned char)uart->dr;
	return 0;
}
```
The function definition will be appended by the build system, so do NOT include or rewrite it; forward-declare it and provide every mock, type, struct and macro it needs ABOVE that point. Note that these functions are static, so they must be in the same translation unit, and appending is what makes a forward declaration plus a later definition work.
You can #include "zephyr-src/drivers/serial/uart_pl011_registers.h" to get the hardware register structs.
Include all necessary standard headers.""",

    "pl011_poll_out": """Write a libFuzzer harness in C++ for the function 'pl011_poll_out' from Zephyr PL011.
You must mock the MMIO registers using a static struct and include an LLVMFuzzerTestOneInput function.

Here is the source of the driver target function:
```c
static void pl011_poll_out(const struct device *dev, unsigned char c)
{
	volatile struct pl011_regs *uart = get_uart(dev);

	while (uart->fr & PL011_FR_TXFF) {
		; /* Wait */
	}

	uart->dr = (uint32_t)c;
}
```
The function definition will be appended by the build system, so do NOT include or rewrite it; forward-declare it and provide every mock, type, struct and macro it needs ABOVE that point. Note that these functions are static, so they must be in the same translation unit, and appending is what makes a forward declaration plus a later definition work.
You can #include "zephyr-src/drivers/serial/uart_pl011_registers.h" to get the hardware register structs.
Include all necessary standard headers.""",

    "pl011_isr": """Write a libFuzzer harness in C++ for the function 'pl011_isr' from Zephyr PL011.
You must mock the MMIO registers using a static struct and include an LLVMFuzzerTestOneInput function.

Here is the source of the driver target function:
```c
static void pl011_isr(const struct device *dev)
{
	struct pl011_data *data = (struct pl011_data *)dev->data;
	volatile struct pl011_regs *uart = get_uart(dev);

	if (uart->mis & PL011_IMSC_CTSMIM) {
		uart->icr = PL011_IMSC_CTSMIM;
		uart->imsc &= ~PL011_IMSC_CTSMIM;
	}

	if (uart->mis & PL011_IMSC_ERROR_MASK) {
		uart->icr = uart->mis & PL011_IMSC_ERROR_MASK;
	}

	if (data->irq_cb) {
		K_SPINLOCK(&data->irq_cb_lock) {
			data->irq_cb(dev, data->irq_cb_data);
		}
	}
}
```
The function definition will be appended by the build system, so do NOT include or rewrite it; forward-declare it and provide every mock, type, struct and macro it needs ABOVE that point. Note that these functions are static, so they must be in the same translation unit, and appending is what makes a forward declaration plus a later definition work.
You can #include "zephyr-src/drivers/serial/uart_pl011_registers.h" to get the hardware register structs.
Include all necessary standard headers.""",

    "pl011_runtime_configure_internal": """Write a libFuzzer harness in C++ for the function 'pl011_runtime_configure_internal' from Zephyr PL011.
You must mock the MMIO registers using a static struct and include an LLVMFuzzerTestOneInput function.

Here is the source of the driver target function:
```c
static int pl011_runtime_configure_internal(const struct device *dev,
					    const struct uart_config *cfg)
{
	volatile struct pl011_regs *uart = get_uart(dev);
	uint32_t lcrh;

	uart->cr &= ~(PL011_CR_UARTEN);

	lcrh = uart->lcr_h & ~(PL011_LCRH_FORMAT_MASK | PL011_LCRH_STP2);

	switch (cfg->parity) {
	case UART_CFG_PARITY_NONE:
		break;
	case UART_CFG_PARITY_ODD:
		lcrh |= PL011_LCRH_PEN;
		break;
	case UART_CFG_PARITY_EVEN:
		lcrh |= PL011_LCRH_PEN | PL011_LCRH_EPS;
		break;
	default:
		return -ENOTSUP;
	}

	if (cfg->stop_bits == UART_CFG_STOP_BITS_2) {
		lcrh |= PL011_LCRH_STP2;
	}

	switch (cfg->data_bits) {
	case UART_CFG_DATA_BITS_5:
		lcrh |= PL011_LCRH_WLEN_5;
		break;
	case UART_CFG_DATA_BITS_6:
		lcrh |= PL011_LCRH_WLEN_6;
		break;
	case UART_CFG_DATA_BITS_7:
		lcrh |= PL011_LCRH_WLEN_7;
		break;
	case UART_CFG_DATA_BITS_8:
		lcrh |= PL011_LCRH_WLEN_8;
		break;
	default:
		return -ENOTSUP;
	}

	if (cfg->flow_ctrl == UART_CFG_FLOW_CTRL_RTS_CTS) {
		pl011_set_flow_control(dev, true);
	} else if (cfg->flow_ctrl == UART_CFG_FLOW_CTRL_NONE) {
		pl011_set_flow_control(dev, false);
	} else {
		return -ENOTSUP;
	}

	uart->lcr_h = lcrh;

	pl011_set_baudrate(dev, cfg->baudrate);

	uart->cr |= PL011_CR_UARTEN;

	return 0;
}
```
The function definition will be appended by the build system, so do NOT include or rewrite it; forward-declare it and provide every mock, type, struct and macro it needs ABOVE that point. Note that these functions are static, so they must be in the same translation unit, and appending is what makes a forward declaration plus a later definition work.
You can #include "zephyr-src/drivers/serial/uart_pl011_registers.h" to get the hardware register structs.
Include all necessary standard headers.""",

    "pl011_init": """Write a libFuzzer harness in C++ for the function 'pl011_init' from Zephyr PL011.
You must mock the MMIO registers using a static struct and include an LLVMFuzzerTestOneInput function.

Here is the source of the driver target function:
```c
static int pl011_init(const struct device *dev)
{
	const struct pl011_config *config = (const struct pl011_config *)dev->config;
	struct pl011_data *data = (struct pl011_data *)dev->data;
	volatile struct pl011_regs *uart = get_uart(dev);
	int ret;
	uint32_t lcrh;

	if (!data->sbsa) {
		uart->dmacr = 0U;
		uart->cr &= ~PL011_CR_SIREN;
		uart->cr |= PL011_CR_RXE | PL011_CR_TXE;
	}

	lcrh = uart->lcr_h & ~(PL011_LCRH_FORMAT_MASK | PL011_LCRH_STP2);
	lcrh |= PL011_LCRH_WLEN_8;
	uart->lcr_h = lcrh;

	if (config->sys_clk != 0U) {
		pl011_set_baudrate(dev, data->baud_rate);
	}

	uart->cr |= PL011_CR_UARTEN;

	return 0;
}
```
The function definition will be appended by the build system, so do NOT include or rewrite it; forward-declare it and provide every mock, type, struct and macro it needs ABOVE that point. Note that these functions are static, so they must be in the same translation unit, and appending is what makes a forward declaration plus a later definition work.
You can #include "zephyr-src/drivers/serial/uart_pl011_registers.h" to get the hardware register structs.
Include all necessary standard headers."""
}

OLLAMA_MODEL = "qwen2.5-coder:14b"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
N_TRIALS = 2

def call_ollama(prompt, seed):
    data = {
        "model": OLLAMA_MODEL,
        "prompt": "You are a firmware fuzzing expert. Return ONLY valid C++ code for a libFuzzer harness. No markdown formatting.\n\n" + prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "seed": seed,
            "num_predict": 1024
        }
    }
    try:
        import requests
        resp = requests.post(OLLAMA_URL, json=data)
        if resp.status_code == 200:
            text = resp.json()["response"]
            return text.replace('```cpp', '').replace('```', '').strip()
    except Exception as e:
        print(f"Ollama API Error: {e}")
    return None

def write_log(path, content):
    with open(path, 'w') as f:
        f.write(content)

def evaluate_harness(harness_code, dir_path, target_func):
    cpp_file = os.path.join(dir_path, "harness.cpp")
    
    # Extract source from TARGETS
    prompt = TARGETS[target_func]
    import re
    match = re.search(r'```c\n(.*?)```', prompt, re.DOTALL)
    if match:
        target_source = match.group(1)
    else:
        target_source = ""
        
    # Check for redefinition (if LLM defined it anyway)
    # A genuine compile error will occur because we append it anyway
    full_code = harness_code + "\n\n// === APPENDED TARGET FUNCTION ===\n" + target_source
    
    write_log(cpp_file, full_code)
    
    # 4. Source Integrity (now we check if the LLM included its own copy BEFORE our append, by checking original harness_code)
    if target_func not in harness_code:
        return False, "Target function missing from generated code (Trivial)", "Target function missing"
        
    # 1. Compile
    res_compile = subprocess.run(
        ["wsl", "clang++", "-fsanitize=fuzzer,address", "-O1", "-fno-inline", "-I" + os.path.abspath("harnesses/include").replace("\\", "/").replace("D:/", "/mnt/d/"), "-I/mnt/d/aeroharness", "harness.cpp", "-o", "fuzz_bin"],
        cwd=dir_path, capture_output=True, text=True
    )
    if res_compile.returncode != 0:
        return False, "Compiler Error", res_compile.stderr

    try:
        res_run = subprocess.run(
            ["wsl", "./fuzz_bin", "-max_total_time=1", "-timeout=2"],
            cwd=dir_path, capture_output=True, text=True, timeout=5
        )
        out_stderr = res_run.stderr
        ret_code = res_run.returncode
    except subprocess.TimeoutExpired as e:
        subprocess.run(["wsl", "pkill", "-9", "fuzz_bin"])
        out_stderr = e.stderr if e.stderr else (e.output.decode('utf-8', errors='ignore') if e.output else "")
        ret_code = 77 # Libfuzzer timeout exit code is usually 77, we'll handle it below
        out_stderr += "\n== ALARM: libFuzzer timeout ==\n"
        
    is_timeout = ("ALARM: libFuzzer timeout" in out_stderr or "timeout after" in out_stderr.lower())
    
    if ret_code != 0 and ret_code != 77:
        if "AddressSanitizer" in out_stderr or "UndefinedBehaviorSanitizer" in out_stderr or "LeakSanitizer" in out_stderr:
            return False, "Sanitizer Error", out_stderr
        if not is_timeout and "Done" not in out_stderr:
            return False, "Runtime Crash", out_stderr
            
    # Check edges
    edges = 0
    for line in out_stderr.split('\n'):
        if "stat::edges:" in line or "cov: " in line:
            try:
                if "cov: " in line:
                    edges = max(edges, int(line.split("cov: ")[1].split()[0]))
                else:
                    edges = max(edges, int(line.split("stat::edges:")[1].strip()))
            except:
                pass
                
    if is_timeout:
        # A libFuzzer timeout counts as success only if the stack trace shows the hang inside the target function,
        # or coverage exceeded the 3-edge threshold before the hang.
        hang_in_target = target_func in out_stderr
        if not hang_in_target and edges <= 3:
            return False, "Timeout outside target func with Trivial Coverage", out_stderr
        return True, "Success (Timeout in target / adequate coverage)", out_stderr
        
    if edges <= 3:
        return False, "Trivial Coverage (<=3 edges)", out_stderr
        
    return True, "Success", out_stderr

def run_experiment():
    print(f"=== Ablation B v2 ===")
    print(f"Model: {OLLAMA_MODEL}")
    print(f"Temperature: 0.7")
    print(f"Trials per target: {N_TRIALS}")
    print(f"Time: {datetime.now().isoformat()}")
    
    results = {}
    base_dir = "ablation_b_v2_logs"
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
        
    results_file = "ablation_b_v2_results.json"
    if os.path.exists(results_file):
        with open(results_file, "r") as f:
            results = json.load(f)
    
    for target, prompt in TARGETS.items():
        print(f"\n--- Target: {target} ---")
        if target not in results:
            results[target] = []
            
        target_dir = os.path.join(base_dir, target)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        
        completed_trials = {t["trial"] for t in results[target]}
        
        for trial in range(1, N_TRIALS + 1):
            if trial in completed_trials:
                print(f"  Trial {trial} already completed. Skipping.")
                continue
            seed = int(time.time() * 1000) % 10000 + trial
            print(f"  Trial {trial} (Seed {seed})...")
            
            trial_dir = os.path.join(target_dir, f"trial_{trial}")
            os.makedirs(trial_dir, exist_ok=True)
            
            # Attempt 1
            code = call_ollama(prompt, seed)
            if not code:
                print("    API Failed.")
                continue
                
            success, fail_type, err_out = evaluate_harness(code, trial_dir, target)
            
            if success:
                print("    -> First-Attempt Success")
                results[target].append({"trial": trial, "outcome": "first_attempt_success"})
                continue
                
            print(f"    -> First-Attempt Failed ({fail_type}). Branching...")
            
            arm_a_dir = os.path.join(trial_dir, "arm_a_real")
            arm_b_dir = os.path.join(trial_dir, "arm_b_generic")
            os.makedirs(arm_a_dir, exist_ok=True)
            os.makedirs(arm_b_dir, exist_ok=True)
            
            # Arm A: Real Feedback
            arm_a_success = False
            arm_a_attempts = 1
            cur_prompt_a = prompt + f"\n\nYour previous code failed with the following error:\n```\n{err_out}\n```\nPlease try again. Output ONLY C++."
            
            for retry in range(2, 6):
                arm_a_attempts = retry
                retry_code = call_ollama(cur_prompt_a, seed + retry)
                if not retry_code: continue
                s, ft, eo = evaluate_harness(retry_code, arm_a_dir, target)
                if s:
                    arm_a_success = True
                    break
                cur_prompt_a = prompt + f"\n\nYour previous code failed with the following error:\n```\n{eo}\n```\nPlease try again. Output ONLY C++."
                
            # Arm B: Generic Feedback
            arm_b_success = False
            arm_b_attempts = 1
            cur_prompt_b = prompt + f"\n\nThe code failed to compile. Please try again. Output ONLY C++."
            
            for retry in range(2, 6):
                arm_b_attempts = retry
                retry_code = call_ollama(cur_prompt_b, seed + retry * 10)
                if not retry_code: continue
                s, ft, eo = evaluate_harness(retry_code, arm_b_dir, target)
                if s:
                    arm_b_success = True
                    break
                cur_prompt_b = prompt + f"\n\nThe code failed to compile. Please try again. Output ONLY C++."
                
            print(f"      Arm A (Real): {'SUCCESS' if arm_a_success else 'FAIL'} in {arm_a_attempts} total attempts")
            print(f"      Arm B (Generic): {'SUCCESS' if arm_b_success else 'FAIL'} in {arm_b_attempts} total attempts")
            
            results[target].append({
                "trial": trial,
                "outcome": "branched",
                "fail_type_attempt1": fail_type,
                "arm_a_success": arm_a_success,
                "arm_a_attempts": arm_a_attempts,
                "arm_b_success": arm_b_success,
                "arm_b_attempts": arm_b_attempts
            })
            
            # Write partial results
            with open("ablation_b_v2_results.json", "w") as f:
                json.dump(results, f, indent=2)
                
    print("\nExperiment Complete.")

if __name__ == "__main__":
    run_experiment()
