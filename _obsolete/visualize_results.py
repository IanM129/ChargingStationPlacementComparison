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


def adjustRunParameters(res_params, cfg_params):
    res_params["sim.visualize"] = cfg_params["sim.visualize"]
    res_params["prep.preprocess"] = True
    return res_params

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
def rerunSession(filepath, metadata, params=None):
    print(f"---------- Started rerun of '{filepath}'")
    ## Import
    import lib.utility as util
    import lib.graphing.utility as graphutil
    # Get needed
    if params is None: params = Parameters.load(filepath + "/config.xml")
    metadata = dm.loadSessionMetadata(filepath)
    network_name = metadata.get("network", None)
    if network_name is None:
        raise Exception("Trying rerun session at '{filepath}' without defined network_name")
    sess_type = metadata["sessionType"]
    if sess_type == "?":
        raise Exception("Trying to rerun session at '{filepath}' without defined session type.");
    # Preprocess
    output_path = filepath + "/_run"
    pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
    K = metadata[] #params["station.k"]
    STATION_CAPACITY = params["station.capacity"]
    VISUALIZE = params["sim.visualize"]
    params["sim.visualize"] = True
    if isCover(sess_type):
        AGENT_COUNT = params["training.agents"]
        ### Load system
        print("Importing...")
        ## Import
        import networkx as nx
        from lib.graphing.utility import edgeIDsFromDetailed
        ## Load network and environment
        # Network
        base_net, base_G, base_G_d, coverage_G_d, translator = util.loadEnvironment(network_name)
        # Vehicle data
        trips = TripDataset.parseXML(base_G, translator, filepath + "/trips.xml")
        charge_data = dm.loadChargeData(filepath + "/charge_data.xml")
        ## Run blank model
        results = Evaluation(translator)
        G = copy.deepcopy(base_G)
        print("Running blank simulation...")
        results = util.runSimulation_blank(network_name, output_path,
                                           base_net, trips, params, results)
        print(f"Simulation over in {round(results.executionDuration, 2)} seconds")
        print("")
        # Update graph
        G = graphutil.resultsToEdgeAttributes(G, translator, ["vehicles", "flow"], results)
        flow_dict = nx.get_edge_attributes(G, "flow")
        results.clear()
        ## Run algorithm
        if AGENT_COUNT == 1:
            from coverage_solo import stationDistributionStart, stationDistribution
            # Get first station
            first_station = stationDistributionStart(flow_dict)
            # Station distribution
            stations_d, dist_radius = stationDistribution(base_G, base_G_d, K, output_path,
                                                          edge_value_weights=flow_dict,
                                                          first_station=first_station)
            stations_ids = edgeIDsFromDetailed(base_G, stations_d)
            # Get price
            MONEY_PER_KWH = params["station.moneyPerKWh"]
            # Stations
            stations = StationInfoDataset([StationInfo(s, STATION_CAPACITY, MONEY_PER_KWH) for s in stations_ids])
            # Run
            print("Running solo simulation...")
            results = util.runSimulation_solo(network_name, output_path,
                                              base_net, base_G, stations,
                                              trips, charge_data, coverage_G_d,
                                              params, results)
        else:
            from coverage_competitive import stationDistributionStart, stationDistribution
            from lib.xml.output import loadTrainResults_numpy
            # Get prices
            prices = []
            prices_data = loadTrainResults_numpy(filepath + "/results/data")["price"]
            for a in range(AGENT_COUNT): prices.append(prices_data[a][-1]);
            agent_colors = visutil.getAgentColors()
            suffixes = [("_" + n) for n in agent_colors]
            # Select stations
            stations = []; dist_radius = []; all_stations = [];
            already_chosen_d = set(); already_chosen = set();
            for a in range(AGENT_COUNT):
                # First station
                first_station = stationDistributionStart(flow_dict, already_chosen)
                # Choose rest
                st, dr = stationDistribution(base_G, base_G_d, K, output_path,
                                             first_station=first_station,
                                             edge_value_weights=flow_dict,
                                             already_chosen=already_chosen_d)
                already_chosen_d.update(st)
                # Station info from detailed edges
                stations_ids = []
                for st_d in st:
                    from_node, to_node = graphutil.getNodesOfDetailedRoad(st_d)
                    if base_G.has_edge(from_node, to_node):
                        edge_id = base_G[from_node][to_node]["id"]
                    else:
                        edge_id = base_G[to_node][from_node]["id"]
                    stations_ids.append(edge_id)
                    already_chosen.add((from_node, to_node))
                # Station info from detailed edges
                st = StationInfoDataset([StationInfo(s, STATION_CAPACITY, prices[a], suffix=suffixes[a]) for s in stations_ids])
                stations.append(st); dist_radius.append(dr);
                all_stations.extend(st.arr)
            all_stations = StationInfoDataset(all_stations)
            # Run
            print("Running competitive simulation...")
            results = util.runSimulation_comp(network_name, output_path,
                                              base_net, base_G, stations, all_stations, prices,
                                              trips, charge_data, coverage_G_d,
                                              params, results)
    elif isGame(sess_type):
        AGENT_COUNT = params["training.agents"]
        ### Load system
        print("Importing...")
        ## Import
        from lib.xml.output import loadTrainResults_numpy
        ## Load network and environment
        # Network
        base_net, base_G, base_G_d, coverage_G_d, translator = util.loadEnvironment(network_name)
        # Vehicle data
        trips = TripDataset.parseXML(base_G, translator, filepath + "/trips.xml")
        charge_data = dm.loadChargeData(filepath + "/charge_data.xml")
        ## Load last state
        train_data = loadTrainResults_numpy(filepath + "/results/data")
        stations_data = train_data["stations"]
        results = Evaluation(translator)
        if AGENT_COUNT == 1:
            # Get price
            MONEY_PER_KWH = params["station.moneyPerKWh"]
            # Get stations
            stations = stations_data[-1]
            stations = StationInfoDataset([StationInfo(s, STATION_CAPACITY, MONEY_PER_KWH) for s in stations])
            # Stations
            # Run
            print("Running solo simulation...")
            results = util.runSimulation_solo(network_name, output_path,
                                              base_net, base_G, stations,
                                              trips, charge_data, coverage_G_d,
                                              params, results)
        else:
            agent_colors = visutil.getAgentColors()
            suffixes = [("_" + n) for n in agent_colors]
            # Get price
            prices = []
            prices_data = train_data["price"]
            # Get stations
            stations = []; all_stations = [];
            for a in range(AGENT_COUNT):
                prices.append(prices_data[a][-1]);
                sts = [StationInfo(s, STATION_CAPACITY, prices[a], suffix=suffixes[a]) for s in stations_data[a][-1]]
                stations.append(StationInfoDataset(sts))
                all_stations.extend(sts);
            all_stations = StationInfoDataset(all_stations)
            # Run
            print("Running competitive simulation...")
            results = util.runSimulation_comp(network_name, output_path,
                                              base_net, base_G, stations, all_stations, prices,
                                              trips, charge_data, coverage_G_d,
                                              params, results)   
    elif isGNN(sess_type) or isMARL(sess_type):
        #### Load system
        print("Importing...")
        ## Import
        import torch
        from lib.gnn.model2 import EdgePosGNN
        from lib.gnn.model3 import EdgePosAndPriceGNN
        import lib.gnn.utility as gnnutil
        global device
        device = gnnutil.initDevice()
        ## Load network and environment
        # Network
        print(f"Loading network '{network_name}'...")
        edge_attr_list = gnnutil.getEdgeAttrList(isMARL(sess_type))
        graph, base_net, base_G, base_G_d, coverage_G_d, translator = gnnutil.loadEnvironment(network_name, edge_attr_list)
        # Vehicle data
        trips = TripDataset.parseXML(base_G, translator, filepath + "/trips.xml")
        charge_data = dm.loadChargeData(filepath + "/charge_data.xml")
        ## Load model(s)
        prnt = "Loading model"
        if isMARL(sess_type):
            agent_count = metadata['agentCount'];
            prnt += f"s [{agent_count}]...";
        else:
            agent_count = 1;
            prnt += "...";
        print(prnt)
        model = dm.loadModels(filepath, agent_count, graph, device)
        print("Successfully loaded '" + filepath + "'\n")
        #### Rerun
        results = Evaluation(translator)
        # Run a blank model
        VISUALIZE = params["sim.visualize"]
        params["sim.visualize"] = False
        print("Running blank simulation...")
        results = util.runSimulation_blank(network_name, filepath + "/_run",
                                           base_net, trips, params, results)
        print(f"Simulation over in {round(results.executionDuration, 2)} seconds")
        print("")
        ## Update graph (Data)
        graph = gnnutil.applyResultsToGraph(graph, translator, ["vehicles", "flow"], results)
        results.clear()
        params["sim.visualize"] = VISUALIZE
        if isGNN(sess_type):
            MONEY_PER_KWH = params["station.moneyPerKWh"]
            # Model eval forward
            sel_edge_idxs = gnnutil.EdgePosGNN_chooseEdges(model, graph, K)
            sel_edge_ids = [translator.indexToID(sei) for sei in sel_edge_idxs]
            # Transform to stations
            stations = []
            for edge in sel_edge_ids: stations.append(StationInfo(edge, STATION_CAPACITY, MONEY_PER_KWH));
            stations = StationInfoDataset(stations)
            print("Chosen stations:")
            print(f"  {', '.join([si.edge_id for si in stations])}")
            print("")
            print("Running solo simulation...")
            results = util.runSimulation_solo(network_name, filepath + "/_run",
                                              base_net, base_G, stations,
                                              trips, charge_data, coverage_G_d,
                                              params, results)
            print(f"Simulation over in {round(results.executionDuration, 2)} seconds")
        else:
            MIN_PRICE = params["training.minPrice"]
            MAX_PRICE = params["training.maxPrice"]
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
            print("Chosen stations and prices:")
            clr_prec = len(max(agent_colors, key=len))
            for a in range(agent_count):
                print(f"  {agent_colors[a].capitalize():{clr_prec}s}:",
                      f"{', '.join([si.edge_id for si in agent_stations[a]])}")
            print("")
            all_stations = StationInfoDataset(all_stations)
            print("Running competitive simulation...")
            results = util.runSimulation_comp(network_name, filepath + "/_run",
                                              base_net, base_G, agent_stations, all_stations, prices,
                                              trips, charge_data, coverage_G_d,
                                              params, results)
            print(f"Simulation over in {round(results.executionDuration, 2)} seconds")
        #### Showcase results
        if PRINT_RESULTS:
            visutil.printResults_general(results, params)
            visutil.printResults_trips(results)
            if isGNN(sess_type): visutil.printResults_solo(results);
            else: visutil.printResults_comp(results);
    print()
    print(f"---------- Rerun of '{filepath}' successful.")
    print("\n" * 1)
    return results
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
    metadata = dm.loadSessionMetadata(filepath)
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
    
