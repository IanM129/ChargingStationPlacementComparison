import math
import random
import copy
import numpy as np
import xml.etree.ElementTree as ET

import lib.data_management as dm


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
    args_dict = {}
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
                        raise Exception(f"ERROR: Out of range index given for '{args_str[i]}'.")
                    value = data_list[index][1]
                else:
                    if not any(e[0] == value for e in data_list):
                        raise Exception(f"ERROR: Vehicle data folder '{value}' not found in 'vehicle_data' folder.")
                    value = "vehicle_data/" + value;
            args_dict["vehicle-data"] = value
            i += 2
        elif args_str[i] == "-a" or args_str[i] == "-ac" or args_str[i] == "--agents" or args_str[i] == "--agents-count":
            value = int(args_str[i+1])
            args_dict["agent-count"] = value
            i += 2
        elif args_str[i] == "-i" or args_str[i] == "-it" or args_str[i] == "--iterations":
            value = int(args_str[i+1])
            args_dict["iterations"] = value
            i += 2
        elif args_str[i] == "-l" or args_str[i] == "--limit":
            args_dict["limit"] = True
            i += 1
        else: i += 1;
    return args_dict
def stringifyArgs(args_dict):
    args_str = ""
    if "vehicle-data" in args_dict:
        args_str += " --vehicles " + str(args_dict["vehicle-data"])
    if "agent-count" in args_dict:
        args_str += " --agents " + str(args_dict["agent-count"])
    if "iterations" in args_dict:
        args_str += " --iterations " + str(args_dict["iterations"])
    if "limit" in args_dict:
        args_str += " --limit"
    return args_str.strip()

#### Bookkeeping
def initializeResultsDict(params, iteration_count, K, agent_count):
    train_results = {}
    for p in params.groups["reward"]:
        if params["reward." + p + ".monitor"] == True:
            train_results[p] = np.zeros(iteration_count)
    if agent_count > 1:
        for p in params.groups["compReward"]:
            if params["compReward." + p + ".monitor"] == True:
                train_results[p] = np.zeros((agent_count, iteration_count))
        train_results["price"] = np.zeros((agent_count, iteration_count))
        train_results["stations"] = np.empty((agent_count, iteration_count, K), dtype=np.dtypes.StringDType())
    else:
        train_results["stations"] = np.empty((iteration_count, K), dtype=np.dtypes.StringDType())
    return train_results
def updateResultsDict(train_results, stations, results, iteration, agent_count=1):
    from lib.structs.evaluation import getStatFromResult
    for p in train_results:
        if p == "stations":
            train_results[p][iteration] = stations.listEdges();
        else:
            train_results[p][iteration] = getStatFromResult(results, p)
def updateResultsDict_comp(train_results, agent_stations, results, iteration):
    from lib.structs.evaluation import getStatFromResult
    suffixes = results.suffixes
    for p in train_results:
        if p == "stations":
            for a in range(len(train_results[p])):
                train_results[p][a][iteration] = agent_stations[a].listEdges()
        elif len(train_results[p].shape) > 1:
            stats = getStatFromResult(results, p)
            for a in range(len(train_results[p])):
                train_results[p][a][iteration] = stats[suffixes[a]];
        else:
            train_results[p][iteration] = getStatFromResult(results, p);

#### Simulation
## Network
def loadEnvironment(network_name):
    import sumolib
    import lib.graphing as graphing
    from lib.structs.graphtranslator import GraphTranslator
    # Folder paths (file organization)
    data_path = "networks/" + network_name + "/";
    #print("Using network '" + network_name + "' under '" + data_path + "'")
    ## Graph
    base_net = sumolib.net.readNet(data_path + "/base_net.net.xml")
    base_G = graphing.netToGraph(data_path + "/base_net.net.xml",
                                 lengths=True, travel_time=True,
                                 internal_lengths=True, node_position=True)
    base_G_d = graphing.netToDetailedGraph(data_path + "/base_net.net.xml")
    print("Graph:    " + str(base_G) + "\nDetailed: " + str(base_G_d) + "\n");
    num_nodes = base_G.number_of_nodes()
    # Detailed graph for coverage calculations
    #global coverage_G_d
    coverage_G_d = graphing.netToDetailedGraph(data_path + "/base_net.net.xml", add_road_centers=True)
    # Edge translator
    translator = GraphTranslator(base_G)
    return base_net, base_G, base_G_d, coverage_G_d, translator
## Run simulation
def runSimulation_blank(network_name, output_path, net, trips, params, results):
    from lib.sumo.blank import sumoBlankRun
    results = sumoBlankRun(net, "networks/" + network_name, network_name, trips, results, params=params,
                           output_path=output_path, output_subfolder="blank")
    return results
def runSimulation_solo(network_name, output_path,
                       net, G, stations, base_trips, charge_data, coverage_G_d, 
                       params, results, iteration=None, debug=False):
    from lib.sumo.solo import sumoSoloRun
    trips = copy.deepcopy(base_trips)
    output_subfolder = "solo";
    if iteration != None: output_subfolder += "_" + str(iteration);
    results = sumoSoloRun(net, G, "networks/" + network_name, network_name, trips, stations, results,
                          output_path=output_path, output_subfolder=output_subfolder,
                          charge_data=charge_data, coverage_G_d=coverage_G_d, params=params, debug=debug)
    return results
def runSimulation_comp(network_name, output_path,
                       net, G, stations, all_stations, prices, base_trips, charge_data, coverage_G_d,
                       params, results, iteration=None, debug=False, agent_colors=None):
    from lib.sumo.comp import sumoCompRun
    trips = copy.deepcopy(base_trips)
    output_subfolder = "comp";
    if iteration != None: output_subfolder += "_" + str(iteration);
    results = sumoCompRun(net, G, "networks/" + network_name, network_name, trips, stations, all_stations,
                          results, output_path, output_subfolder=output_subfolder,
                          charge_data=charge_data, prices=prices,
                          agent_colors=agent_colors, coverage_G_d=coverage_G_d,
                          params=params, debug=debug)
    return results

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

