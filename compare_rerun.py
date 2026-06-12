import os
import sys
import pathlib
import time
import numpy as np

import lib.data_management as dm

import lib.visual_utility as visutil

from lib.structs.params import Parameters
from lib.structs.evaluation import Evaluation, EvaluationDataset
from lib.structs.trip import Trip, TripDataset
from lib.structs.stationinfo import StationInfo, StationInfoDataset 




def rerunSession(filepath, params=None):
    print(f"---------- Started rerun of '{filepath}'")
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
    pathlib.Path(filepath + "/_run").mkdir(parents=True, exist_ok=True)
    K = params["station.k"]
    STATION_CAPACITY = params["station.capacity"]
    if sess_type == "solo" or sess_type == "competitive":
        pass
    elif sess_type == "GNN" or sess_type == "MARL":
        #### Load system
        print("Importing...")
        ## Import
        import torch
        #from lib.gnn.model1 import EdgeGNN
        from lib.gnn.model2 import EdgePosGNN
        from lib.gnn.model3 import EdgePosAndPriceGNN
        import lib.gnn.utility as gnnutil
        global device
        device = gnnutil.initDevice()
        ## Load network and environment
        print(f"Loading network '{network_name}'...")
        edge_attr_list = gnnutil.getEdgeAttrList(sess_type == "MARL")
        graph, base_net, base_G, base_G_d, coverage_G_d, translator = gnnutil.loadEnvironment(network_name, edge_attr_list)
        trips = TripDataset.parseXML(base_G, translator, filepath + "/trips.xml")
        charge_data = dm.loadChargeData(filepath + "/charge_data.xml")
        ## Load model(s)
        prnt = "Loading model"
        if sess_type == "MARL":
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
        results = gnnutil.runSimulation_blank(network_name, "networks/" + network_name, filepath + "/_run",
                                              base_net, trips, params, results)
        print(f"Simulation over in {round(results.executionDuration, 2)} seconds")
        print("")
        ## Update graph (Data)
        graph = gnnutil.applyResultsToGraph(graph, translator, ["vehicles", "flow"], results)
        results.clear()
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
            print("Chosen stations:")
            print(f"  {', '.join([si.edge_id for si in stations])}")
            print("")
            print("Running solo simulation...")
            results = gnnutil.runSimulation_solo(network_name, "networks/" + network_name, filepath + "/_run",
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
            results = gnnutil.runSimulation_comp(network_name, "networks/" + network_name, filepath + "/_run",
                                                 base_net, base_G, agent_stations, all_stations, prices,
                                                 trips, charge_data, coverage_G_d,
                                                 params, results)
            print(f"Simulation over in {round(results.executionDuration, 2)} seconds")
        #### Showcase results
        if PRINT_RESULTS:
            visutil.printResults_general(results, params)
            visutil.printResults_trips(results)
            if sess_type == "GNN": visutil.printResults_solo(results);
            else: visutil.printResults_comp(results);
    print()
    print(f"---------- Rerun of '{filepath}' successful.")
    print("\n" * 1)
    return results


PRINT_RESULTS = False

#def rerunAndCompareSessions(filepaths):
if __name__ == "__main__":
    # Parse filepaths from args
    filepaths = []
    for i in range(1, len(sys.argv)):
        filepaths.append(sys.argv[i])
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
