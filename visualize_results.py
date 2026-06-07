import os
import pathlib
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt

from lib.structs.stationinfo import StationInfo, StationInfoDataset
from lib.structs.evaluation import Evaluation
from lib.structs.params import Parameters

import lib.visual_utility as visutil
import lib.traci_utility as traciutil

from lib.xml.tripsGen import load as tripsGen_load
import lib.xml.output as xmlOut



RESULTS_PATH = pathlib.Path("results/")


## bad:  -1 = parent folder doesn't exist   0 = no model file found,
## good: 1 = found model.pt (GNN)           2 = found model_1.pt (MARL)
def isValidModelFolder(folder, parent_folder=""):
    parent_path = folder
    if parent_folder != "": parent_path = parent_folder + "/" + folder
    if not pathlib.Path(parent_path).exists(): return -1;
    if pathlib.Path(parent_path + "/results/model.pt").exists(): return 1;
    if pathlib.Path(parent_path + "/results/model_1.pt").exists(): return 2;
    return 0;
def isValidResultsFolder(folder, parent_folder="results"):
    if not pathlib.Path(parent_folder + "/" + folder).exists(): return 1;
    if not pathlib.Path(parent_folder + "/" + folder + "/results").exists():
        return 2;
    return 0;
def isValidNetworkFolder(name):
    if not pathlib.Path("networks/" + name).exists(): return 1;
    #if not pathlib.Path("networks/" + name + "/" + name.lower() + ".sumocfg").exists():
    #   return 2;
    if not pathlib.Path("networks/" + name + "/base_net.net.xml").exists():
        return 3;
    return 0;


def adjustRunParameters(res_params, cfg_params):
    res_params["sim.visualize"] = cfg_params["sim.visualize"]
    res_params["prep.preprocess"] = True
    return res_params

def getSessionType(path, params, agentCount):
    sess_type = None
    if pathlib.Path(path + "/training").exists():
        if agentCount is None:
            if "marl" in path: sess_type = "MARL";
            if "gnn" in path:
                if sess_type is None: sess_type = "GNN";
                else: sess_type = None;
        else:
            if agentCount > 1: sess_type = "MARL";
            else: sess_type = "GNN";
    else:
        if agentCount == None: sess_type = "simulation"
        elif agentCount > 1: sess_type = "competitive";
        else: sess_type = "solo";
    return sess_type
def fetchSessionMetadata(path):
    metadata = {}
    if not pathlib.Path(path).exists(): return None;
    # Config xml
    config_path = pathlib.Path(path + "/config.xml")
    if config_path.exists():
        config_tree = ET.parse(str(config_path))
        params = Parameters.parse(config_tree)
        metadata["configExists"] = True
    else:
        params = Parameters();
        metadata["configExists"] = False
    metadata["agentCount"] = params.tryGet("training.agents")
    sess_type = getSessionType(path, params, metadata["agentCount"])
    metadata["sessionType"] = sess_type if (sess_type is not None) else "?"
    metadata["centralizedRouting"] = params.tryGet("station.routing.centralized")
    if metadata["centralizedRouting"] is None: metadata["centralizedRouting"] = False;
    metadata["k"] = params.tryGet("station.k")
    # Metadata xml
    mtdt_path = pathlib.Path(path + "/metadata.xml")
    if mtdt_path.exists():
        mtdt_tree = ET.parse(str(mtdt_path));
        mtdt_root = mtdt_tree.getroot();
        metadata["date"] = mtdt_root.find("date").text
        metadata["time"] = mtdt_root.find("time").text
        metadata["network"] = mtdt_root.find("network").text
        metadata["type"] = mtdt_root.find("type").text
        metadata["metadataExists"] = True
    else:
        metadata["metadataExists"] = False
    return metadata

def getSavedSessionPaths(folder):
    paths = []
    content = os.listdir(folder)
    for p in content:
        path = pathlib.Path(folder + "/" + p)
        if isValidResultsFolder(p, folder) == 0:
            paths.append((p, folder + "/" + p))
    return paths
def printSessionPaths(paths, prefix=""):
    prec = len(max(paths, key=len)[0]) + 4
    for i in range(len(paths)):
        print("{0}- {1:2d}: {2:{prec}s}".format(prefix, i+1, paths[i][0], prec=prec), end="")
        metadata = fetchSessionMetadata(paths[i][1])
        if metadata["metadataExists"]:
                s = ""
                date = [metadata["date"][:4], metadata["date"][4:6], metadata["date"][6:]]
                s += f"{date[2]}.{date[1]}.{date[0]}, "
                time = [metadata["time"][:2], metadata["time"][2:4], metadata["time"][4:]]
                s += f"{time[0]}:{time[1]}:{time[2]}"
                s += " | " + str(metadata["network"])
                #print(prefix + "      { " + s + " }")
                print("> " + s)
        else: print("");
        if not metadata["configExists"]:
            print(prefix + f"      [ {metadata['sessionType']} ]")
        else:
            s = metadata["sessionType"]
            if metadata["sessionType"] == "MARL" or metadata["sessionType"] == "competitive":
                s += "; Agents: " + (str(metadata["agentCount"]) if (metadata["agentCount"] is not None) else "?")
            s += "; K: " + str(metadata["k"])
            s += "; " + ("Centralized" if (metadata["centralizedRouting"]) else "Selfish")
            print(prefix + f"      [ {s} ]")
def parseFolderInput(val, options):
    if val.isdigit():
        val = int(val)-1
        if val == -1 or val >= len(options):
            print("Given index is out of range, aborting.");
            exit();
        return options[val][1]
    else:
        valid = isValidResultsFolder(val)
        if valid == 1:
            print("No such folder exists, aborting.")
            exit()
        elif valid == 2:
            print(f"No '.pt' file inside 'results/{val}/results/', aborting.")
            exit();
        return ("results/" + val)

def loadModels(filepath, agent_count, graph):
    model = None;
    if (model_folder := isValidModelFolder(filepath)) > 0:
        global device
        if model_folder == 1:
            model = EdgePosGNN(graph.x.shape[1], graph.edge_attr.shape[1], 64)
            model.load_state_dict(torch.load(filepath + "/results/model.pt", weights_only=True))
            model.to(device); model.eval();
        else:
            model = []
            for a in range(agent_count):
                model.append(EdgePosAndPriceGNN(graph.x.shape[1], graph.edge_attr.shape[1], 64))
                model[a].load_state_dict(torch.load(filepath + "/results/model_" + str(a+1) + ".pt",
                                                    weights_only=True))
                model[a].to(device); model[a].eval();
    return model

###### Network selection
def getNetworkPaths():
    paths = []
    content = os.listdir("networks")
    for p in content:
        path = pathlib.Path("networks/" + p)
        if isValidNetworkFolder(p) == 0:
            paths.append((p, "networks/" + p))
    return paths
def selectNetwork():
    paths = getNetworkPaths()
    for i in range(len(paths)):
        print(f"  - {i+1}: {paths[i][0]}")
    inp = input()
    name = parseFolderInput(inp, paths).rsplit('/', 1)[1]
    return name


###### Options
def runSimulation(filepath, network_name, sess_type, params):
    pathlib.Path(filepath + "/_run").mkdir(parents=True, exist_ok=True)
    K = params["station.k"]
    STATION_CAPACITY = params["station.capacity"]
    if sess_type == "solo" or sess_type == "competitive":
        pass
    elif sess_type == "GNN" or sess_type == "MARL":
        global model, graph, base_net, base_G, base_G_d, translator, trips
        results = Evaluation(translator)
        # Run a blank model
        VISUALIZE = params["sim.visualize"]
        params["sim.visualize"] = False
        results = gnnutil.runSimulation_blank(network_name, "networks/" + network_name, filepath + "/_run",
                                              base_net, trips, params, results)
        ## Update graph (Data)
        graph = gnnutil.applyResultsToGraph(graph, translator, ["vehicles", "flow"], results)
        results = Evaluation(translator)
        params["sim.visualize"] = VISUALIZE
        if sess_type == "GNN":
            MONEY_PER_KWH = params["station.moneyPerKWh"]
            # Model eval forward
            sel_edge_idxs = gnnutil.EdgePosGNN_chooseEdges(model, graph, K)
            sel_edge_ids = [translator.indexToID(sei) for sei in sel_edge_idxs]
            # Transform to stations
            stations = []
            for edge in sel_edge_ids: stations.append(StationInfo(edge, STATION_CAPACITY, MONEY_PER_KWH));
            stations = StationInfoDataset(stations)
            results = gnnutil.runSimulation_solo(network_name, "networks/" + network_name, filepath + "/_run",
                                                 base_net, base_G, stations, trips,
                                                 params, results)
        else:
            MIN_PRICE = params["training.minPrice"]
            MAX_PRICE = params["training.maxPrice"]
            global agent_count
            agent_colors = visutil.getAgentColors()
            suffixes = gnnutil.getAgentSuffixes(agent_colors)
            agent_stations = []; all_stations = []; prices = [];
            for a in range(agent_count):
                # Model eval forward
                sel_edge_idxs, unit_price = gnnutil.EdgePosAndPriceGNN_chooseEdgesAndPrice(model[a], graph, K)
                sel_edge_ids = [translator.indexToID(sei) for sei in sel_edge_idxs]
                price = (MIN_PRICE + (unit_price * (MAX_PRICE - MIN_PRICE)))
                # Transform to stations
                chosen_stations = [];
                for edge in sel_edge_ids: chosen_stations.append(StationInfo(edge, STATION_CAPACITY, price, suffix=suffixes[a]));
                chosen_stations = StationInfoDataset(chosen_stations)
                # Save
                agent_stations.append(chosen_stations); all_stations.extend(chosen_stations.arr);
                prices.append(price)
            all_stations = StationInfoDataset(all_stations)
            results = gnnutil.runSimulation_comp(network_name, "networks/" + network_name, filepath + "/_run",
                                                 base_net, base_G, agent_stations, all_stations, prices, trips,
                                                 params, results)
        # Showcase results
        visutil.printResults_general(results, params)
        visutil.printResults_trips(results)
        if sess_type == "GNN": visutil.printResults_solo(results);
        else: visutil.printResults_comp(results);
        print()
    return
def ShowBest(filepath):
    return
def ShowTrainingStats(filepath, metadata):
    # Load training stats
    train_results = xmlOut.loadTrainResulst_numpy(filepath + "/results/data")
    # Show graphs
    if metadata["sessionType"] == "GNN":
        visutil.plotGNN(train_results)
    elif metadata["sessionType"] == "MARL":
        visutil.plotMARL(train_results)
    plt.show()
    return



###### MAIN
if __name__ == "__main__":
    models_paths = getSavedSessionPaths("results")
    print("Detected results:")
    printSessionPaths(models_paths, prefix="  ")
    print("")
    
    inp = input("Enter folder name or index: ").strip()
    filepath = parseFolderInput(inp, models_paths)
    # Load params
    cfg_params = Parameters.parse("config.xml")
    res_params = Parameters.parse(filepath + "/config.xml")
    params = adjustRunParameters(res_params, cfg_params)
    # Load metadata
    metadata = fetchSessionMetadata(filepath)
    # Load environment and model(s) (if applicable)
    if (model_folder := isValidModelFolder(filepath)) > 0:
        print("Training session detected, importing...")
        import torch
        #from lib.gnn.model1 import EdgeGNN
        from lib.gnn.model2 import EdgePosGNN
        from lib.gnn.model3 import EdgePosAndPriceGNN
        import lib.gnn.utility as gnnutil
        if not metadata["metadataExists"]:
            print("Failed to detect used network, please enter manually:")
            network_name = selectNetwork()
        else: network_name = metadata["network"];
        # Load network
        print(f"Loading network '{network_name}'...")
        global device
        device = gnnutil.initDevice()
        edge_attr_list = gnnutil.getEdgeAttrList(model_folder == 2)
        global graph, base_net, base_G, base_G_d, translator, trips
        graph, base_net, base_G, base_G_d, translator = gnnutil.loadEnvironment(network_name, edge_attr_list)
        trips = tripsGen_load(filepath + "/trips.xml", base_net, base_G)
        # Load model(s)
        global model, agent_count
        prnt = "Loading model"
        if model_folder == 2:
            agent_count = metadata['agentCount'];
            prnt += f"s [{agent_count}]...";
        else:
            agent_count = 1;
            prnt += "...";
        print(prnt)
        model = loadModels(filepath, agent_count, graph)
    print("Successfully loaded '" + filepath + "'\n")

    while inp != "" and inp != "q" and inp != "quit":
        # Options
        print("Options:")
        print("  - [r]un      | Run a simulation using the models")
        print("  - [c]ompare  | Compare with another session")
        if metadata["sessionType"] == "GNN" or metadata["sessionType"] == "MARL":
            print("  - [b]est     | Show the statistics for the best runs")
            print("  - [t]raining | Visualize the training statistics")
        print("  - [q]uit     | Quit")
        inp = input().strip()

        if inp == "r" or inp == "1":
            runSimulation(filepath, network_name, metadata["sessionType"], params)
        elif inp == "b" or inp == "2":
            ShowBest(filepath)
        elif inp == "t" or inp == "3":
            ShowTrainingStats(filepath, metadata)
        print()
    
