import math

def clamp(val, smallest, largest):
    return max(smallest, min(val, largest))


## Z-score
def zscore(x, mean, std):
    return ((x - mean) / (std + 1e-8))
# Welford
def welford(x, mean, m2, iteration):
    n = iteration + 1
    delta = x - mean
    mean += (delta / n)
    delta2 = x - mean
    m2 += delta * delta2
    variance = m2 / max(n - 1, 1)
    std = math.sqrt(variance)
    return mean, m2, std
# Exponential moving average
def ema(x, mean, var, alpha=0.01):
    if mean == None or var == None:
        return float(x), 1.0;
    mean = ((1 - alpha) * mean) + (alpha * x)
    var = ((1 - alpha) * var) + (alpha * pow(x - mean, 2))
    return mean, var
# Hybrid
def ema_welford(x, mean, var, alpha=0.01):
    if mean == None or var == None:
        return float(x), 1.0;
    delta = x - mean
    mean = mean + (alpha * delta)
    var = ((1 - alpha) * var) + (alpha * delta * (x - mean))
    return mean, var


## Debugging
def prettyPrintDict(d, indent=0):
   for key, value in d.items():
      print('\t' * indent + str(key))
      if isinstance(value, dict):
         prettyPrintDict(value, indent+1)
      else:
         print('\t' * (indent+1) + str(value))

