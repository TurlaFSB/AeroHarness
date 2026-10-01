import json, math
import scipy.stats as stats
from statsmodels.stats.proportion import proportion_confint
from statsmodels.stats.contingency_tables import mcnemar

def main():
    with open("ablation_b_v2_results.json", "r") as f:
        data = json.load(f)
        
    total_trials = 0
    total_first_success = 0
    
    # Paired outcomes for McNemar
    # A_success, B_success
    a_yes_b_yes = 0
    a_yes_b_no = 0
    a_no_b_yes = 0
    a_no_b_no = 0
    
    arm_a_attempts = []
    arm_b_attempts = []
    
    categories = {}
    
    for target, trials in data.items():
        for t in trials:
            total_trials += 1
            if t["outcome"] == "first_attempt_success":
                total_first_success += 1
            else:
                a_succ = t["arm_a_success"]
                b_succ = t["arm_b_success"]
                
                if a_succ and b_succ: a_yes_b_yes += 1
                elif a_succ and not b_succ: a_yes_b_no += 1
                elif not a_succ and b_succ: a_no_b_yes += 1
                else: a_no_b_no += 1
                
                if a_succ: arm_a_attempts.append(t["arm_a_attempts"])
                if b_succ: arm_b_attempts.append(t["arm_b_attempts"])
                
                fail_cat = t["fail_type_attempt1"]
                if fail_cat not in categories:
                    categories[fail_cat] = {"count": 0, "a_succ": 0, "b_succ": 0}
                categories[fail_cat]["count"] += 1
                if a_succ: categories[fail_cat]["a_succ"] += 1
                if b_succ: categories[fail_cat]["b_succ"] += 1

    failures = total_trials - total_first_success
    print("=== Ablation B v2 Analysis ===")
    print(f"Total Trials: {total_trials}")
    print(f"First-attempt Successes: {total_first_success}")
    
    if total_trials > 0:
        ci_low, ci_high = proportion_confint(total_first_success, total_trials, method='wilson')
        print(f"First-attempt Success Rate: {total_first_success/total_trials:.2%} [95% CI: {ci_low:.2%} - {ci_high:.2%}]")
        
    print(f"First-attempt Failures (Sample size for comparison): {failures}")
    
    if failures > 0:
        a_succ_total = a_yes_b_yes + a_yes_b_no
        b_succ_total = a_yes_b_yes + a_no_b_yes
        
        ci_a_low, ci_a_high = proportion_confint(a_succ_total, failures, method='wilson')
        ci_b_low, ci_b_high = proportion_confint(b_succ_total, failures, method='wilson')
        
        print(f"Arm A (Real Feedback) Repair Rate: {a_succ_total/failures:.2%} [95% CI: {ci_a_low:.2%} - {ci_a_high:.2%}]")
        print(f"Arm B (Generic Feedback) Repair Rate: {b_succ_total/failures:.2%} [95% CI: {ci_b_low:.2%} - {ci_b_high:.2%}]")
        
        import statistics
        print(f"Arm A Attempts to Success (mean/median): {statistics.mean(arm_a_attempts) if arm_a_attempts else 0:.2f} / {statistics.median(arm_a_attempts) if arm_a_attempts else 0:.2f}")
        print(f"Arm B Attempts to Success (mean/median): {statistics.mean(arm_b_attempts) if arm_b_attempts else 0:.2f} / {statistics.median(arm_b_attempts) if arm_b_attempts else 0:.2f}")
        
        # McNemar
        table = [[a_yes_b_yes, a_yes_b_no],
                 [a_no_b_yes, a_no_b_no]]
        res = mcnemar(table, exact=True)
        print(f"McNemar's Test p-value: {res.pvalue:.4f}")
        diff = (a_succ_total - b_succ_total) / failures
        print(f"Difference in Repair Rate (A - B): {diff:.2%}")
        
        print("\\n--- Failure Categories ---")
        for cat, stats in categories.items():
            print(f"{cat}: {stats['count']} occurrences (A repaired {stats['a_succ']}, B repaired {stats['b_succ']})")
    
    print("\\nDone.")

if __name__ == "__main__":
    main()
