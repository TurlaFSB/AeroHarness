import math

real = [81.0, 72.0, 83.0, 84.0, 84.0]
rand = [85.0, 72.0, 27.0, 85.0, 84.0, 82.0, 72.0, 71.0, 84.0, 83.0, 85.0, 72.0, 27.0, 85.0, 84.0]

def var(data):
    m = sum(data)/len(data)
    return sum((x - m)**2 for x in data) / (len(data) - 1)

var_real = var(real)
var_rand = var(rand)
f_stat = var_rand / var_real
df1 = len(rand) - 1
df2 = len(real) - 1

# Note: scipy isn't installed system wide, I'll calculate p-value using scipy if available via pip, else use a hardcoded lookup.
print(f"Var Real: {var_real:.2f}")
print(f"Var Rand: {var_rand:.2f}")
print(f"F-stat: {f_stat:.2f}")
print(f"df1: {df1}, df2: {df2}")
