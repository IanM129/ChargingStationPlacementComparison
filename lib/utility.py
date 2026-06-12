import math
import random
import xml.etree.ElementTree as ET


#### Math
def clamp(val, smallest, largest):
    return max(smallest, min(val, largest))

## Is value minimized or maximized?
# -1 = minimize; 0,1 -> maximize
def isMinOrMax(val_name : str) -> int:
    match (val_name):
        case "totalCoverage" | "coverage" | "simDuration" | "tripDuration" |\
             "tripLength" | "waitTime" | "stopTime" | "timeLoss":
            return -1; # -> minimize
        case "reward":
            return 1; # -> maximize
        case _: # totalCharge, charge
            return 0; # -> maximize from zero (0)
    return None

def invertRange(values):
    import numpy as np
    """
    ranked = np.argsort(values)
    inv_vals = np.zeros(len(values))
    i = 0; j = len(values) - 1;
    while i < j:
        find = ranked[i]
        lind = ranked[j]
        inv_vals[find] = values[lind]
        inv_vals[lind] = values[find]
        i += 1
        j -= 1
    if i == j: inv_vals[i] = values[i];
    return inv_vals
    """
    values = np.asarray(values)
    unique = np.unique(values)
    inverted = unique[::-1]
    mapping = dict(zip(unique, inverted))
    return np.array([mapping[v] for v in values])
    

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


#### CLI
def parseArgs(args_str):
    args = {}
    i = 0
    while i < len(args_str):
        if args_str[i] == "-v" or args_str[i] == "-vd" or args_str[i] == "--vehicles" or args_str[i] == "--vehicle-data":
            value = args_str[i+1]
            if '/' not in value:
                from lib.data_management import getVehicleDataList
                data_list = dm.getVehicleDataList("vehicle_data")
                if value.isdigit():
                    index = int(value)-1
                    if index < 0:
                        raise Exception("ERROR: Indexing starts from 1.")
                    if index >= len(data_list):
                        raise Exception("ERROR: Out of range index given for '{args_str[i]}'.")
                    value = data_list[index][1]
                else:
                    if not any(e[0] == value for e in data_list):
                        raise Exception("ERROR: Vehicle data folder '{value}' not found in 'vehicle_data' folder.")
                    value = "vehicle_data/" + value;
            args["vehicle-data"] = value
            i += 2
        else: i += 1;
    return args


#### Other
#["red", "blue", "green", "orange", "purple", "olive", "brown", "cyan", "pink", "gray"]
def colorNameToRGB(color_name):
    match (color_name.lower()):
        case "red": return (1, 0, 0);
        case "green": return (0, 1, 0);
        case "blue": return (0, 0, 1);
        case "orange": return (1.0, 0.65, 0.0);
        case "purple": return (0.5, 0.0, 0.5);
        case "olive": return (0.5, 0.5, 0.0);
        case "brown": return (0.6, 0.3, 0.0);
        case "cyan": return (0.0, 1.0, 1.0);
        case "pink": return (1.0, 0.75, 0.8);
        case "gray": return (0.5, 0.5, 0.5);
    return None;

## Debugging
def prettyPrintDict(d, indent=0):
   for key, value in d.items():
      print('\t' * indent + str(key))
      if isinstance(value, dict):
         prettyPrintDict(value, indent+1)
      else:
         print('\t' * (indent+1) + str(value))

