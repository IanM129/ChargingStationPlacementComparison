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


#### Preparation
# Charge data
def generateRandomChargeData(trips, max_charge):
    import preprocess as prep
    charge_data = {}
    for vehID, trip in trips.dict.items():
        need_to_charge_level = random.uniform(0.15, 0.4)
        trip_len = trip.total_distance
        approx_charge_needed = prep.calcApproxChargeNeeded(trip_len)
        # v1 : random.uniform(0.2, 0.3) * max_charge
        # v0 : max(0.02, 0.1 + (random.gauss() * 0.03)) * max_charge;
        # v2 : max(min_charge, random.uniform(0.4, 0.8) * approx_charge_needed)
        set_charge = (need_to_charge_level * max_charge) + (approx_charge_needed * random.uniform(0.0, 1.0))
        charging_min = random.uniform(250, 750)
        # (need_to_charge_level, starting_charge, charging_min)
        charge_data[vehID] = (need_to_charge_level, set_charge, charging_min)
    return charge_data
def writeChargeData(charge_data, filepath):
    tree = ET.ElementTree(ET.fromstring("<chargeData></chargeData>"))
    root = tree.getroot()
    for vehID, data in charge_data.items():
        el = ET.SubElement(root, "vehicle", {
                                "id": vehID,
                                "needToChargeLevel": str(data[0]),
                                "startingCharge": str(data[1]),
                                "chargingMin": str(data[2])})
    tree.write(filepath)
def loadChargeData(filepath):
    charge_data = {}
    tree = ET.parse(filepath)
    for el in tree.getroot():
        vehID = str(el.get("id"))
        data = [float(el.get("needToChargeLevel")),
                float(el.get("startingCharge")),
                float(el.get("chargingMin"))]
        charge_data[vehID] = data
    return charge_data


#### CLI
def parseArgs(args_str):
    args = {}
    i = 0
    while i < len(args_str):
        if args_str[i] == "-v" or args_str[i] == "-vd" or args_str[i] == "--vehicles" or args_str[i] == "--vehicle-data":
            value = args_str[i+1]
            if '/' not in value:
                from lib.data_management import getVehicleDataList
                data_list = getVehicleDataList("vehicle_data")
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

