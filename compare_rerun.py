import os
import sys
import pathlib
import time
import copy
import numpy as np
import matplotlib.pyplot as plt

import lib.data_management as dm

import lib.visual_utility as visutil

from lib.structs.params import Parameters
from lib.structs.evaluation import Evaluation, EvaluationDataset
from lib.structs.trip import Trip, TripDataset
from lib.structs.stationinfo import StationInfo, StationInfoDataset

def isCover(s):
    return s == "cover";
def isGame(s):
    return s == "game"
def isGNN(s):
    return s == "gnn";
def isMARL(s):
    return s == "marl";

def rerunSession(filepath, params=None):
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
    K = params["station.k"]
    STATION_CAPACITY = params["station.capacity"]
    VISUALIZE = params["sim.visualize"]
    params["sim.visualize"] = False
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


def parseArgs():
    filepaths = [];
    args = {"stats": None}
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "-stats":
            args["stats"] = sys.argv[i+1].split(',')
            i += 2
        elif sys.argv[i] == "--no-values":
            args["no-values"] = True
            i += 1
        elif sys.argv[i] == "--no-legend":
            args["no-legend"] = True
            i += 1
        elif sys.argv[i] == "--centerize":
            args["centerize"] = True
            i += 1
        else:
            filepaths.append(sys.argv[i])
            i += 1
    return filepaths, args

PRINT_RESULTS = False

#def rerunAndCompareSessions(filepaths):
if __name__ == "__main__":
    # Parse filepaths from args
    filepaths, args = parseArgs();
    if "stats" in args: stats = args["stats"];
    else: stats = None;
    print("Comparing by rerun:", filepaths, "\n")
    #print("=" * 20)
    # Rerun and compare
    stime = time.perf_counter()
    results_ds = []
    params_arr = []
    for filepath in filepaths:
        params = Parameters.load(filepath + "/config.xml")
        res = rerunSession(filepath, params=params)
        results_ds.append(res)
        params_arr.append(params)
    results_ds = EvaluationDataset(results_ds)
    scores = results_ds.calcScores(params_arr)
    sess_names = [filepath.rsplit('/', 1)[1] for filepath in filepaths]
    rank_prec = len(str(len(scores)))
    name_prec = len(max(sess_names, key=len)) + 4
    ranked_indeces = list(np.argsort(scores))
    ranked_indeces.reverse()
    print("Final scores:")
    for rank in range(len(ranked_indeces)):
        i = ranked_indeces[rank]
        filepath = filepaths[i]
        print(f"  {(rank+1):{rank_prec}}. {sess_names[i]:{name_prec}s}: {scores[i]}")
    print("")
    etime = time.perf_counter()
    print(f"Finished in {round(etime - stime, 2)} seconds")
    # Plot
    fig = visutil.plotResultDataset(results_ds, sess_names, params_arr)
    plt.show()
