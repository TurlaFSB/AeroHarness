import statsmodels.api as sm
from statsmodels.stats.proportion import proportion_confint

# Data
count = 35
nobs = 42

# Calculate point estimate
point_estimate = count / nobs * 100

# Calculate 95% CI using Wilson score interval
ci_low, ci_upp = proportion_confint(count, nobs, alpha=0.05, method='wilson')

# Convert to percentages
ci_low_pct = ci_low * 100
ci_upp_pct = ci_upp * 100

print(f"Point Estimate: {point_estimate:.1f}%")
print(f"95% Confidence Interval (Wilson Score): [{ci_low_pct:.1f}%, {ci_upp_pct:.1f}%]")
