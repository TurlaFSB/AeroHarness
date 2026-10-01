import os, shutil
from run_ablation_b_v2 import evaluate_harness

def main():
    print("Testing Control Group...")
    
    controls = [
        ("poll_in_good", "harnesses/fuzz_pl011_poll_in.cpp", "pl011_poll_in", True),
        ("poll_out_good", "harnesses/fuzz_pl011_poll_out.cpp", "pl011_poll_out", True),
        ("isr_good", "harnesses/fuzz_pl011_isr.cpp", "pl011_isr", True),
        
        ("empty_harness", None, "pl011_poll_in", False),
        ("reimplemented_harness", None, "pl011_poll_in", False),
    ]
    
    empty_code = """
    #include <stdint.h>
    #include <stddef.h>
    
    static int pl011_poll_in() { return 0; }
    
    extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
        return 0;
    }
    """
    
    reimplemented_code = """
    #include <stdint.h>
    #include <stddef.h>
    
    // Missing the actual pl011_poll_in body! It's stubbed out.
    extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
        return 0;
    }
    """
    
    base_dir = "test_eval_logs"
    if os.path.exists(base_dir):
        shutil.rmtree(base_dir)
    os.makedirs(base_dir)
    
    all_passed = True
    
    for name, path, target_func, expected_success in controls:
        print(f"Testing {name}...")
        dir_path = f"{base_dir}_{name}"
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
        os.makedirs(dir_path)
        
        if path:
            with open(path, "r") as f:
                code = f.read()
            import re
            if "poll_in" in name:
                code = re.sub(r'static int pl011_poll_in\(.*?\).*?return 0;\n\}', 'static int pl011_poll_in(const struct device *dev, unsigned char *c);', code, flags=re.DOTALL)
                code = re.sub(r'static bool pl011_is_readable\(.*?\).*?== 0U;\n\}', '', code, flags=re.DOTALL)
            elif "poll_out" in name:
                code = re.sub(r'static void pl011_poll_out\(.*?\).*?\(uint32_t\)c;\n\}', 'static void pl011_poll_out(const struct device *dev, unsigned char c);', code, flags=re.DOTALL)
            elif "isr" in name:
                code = code[:code.find("static void pl011_isr")] + "static void pl011_isr(const struct device *dev);\n" + code[code.find("// === LIBFUZZER HARNESS ==="):]
        elif name == "empty_harness":
            code = empty_code
        elif name == "reimplemented_harness":
            code = reimplemented_code
            
        success, fail_type, err_out = evaluate_harness(code, dir_path, target_func)
        
        if success == expected_success:
            print(f"  [PASS] Got expected result: {success} ({fail_type})")
        else:
            print(f"  [FAIL] Expected {expected_success}, but got {success} ({fail_type})")
            all_passed = False
            
    print(f"\nAll controls passed: {all_passed}")

if __name__ == "__main__":
    main()
