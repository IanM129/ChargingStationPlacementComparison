import os
import sys
import math
from datetime import datetime
import time
import random
import pathlib
import sumolib
import networkx as nx
import copy
import numpy as np
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
from tqdm import tqdm

global libsumo_m, traci_m
import libsumo as libsumo_m
import traci as traci_m

import preprocess as prep

from lib.utility import parseArgs, initializeResultsDict, updateResultsDict_comp
import lib.visual_utility as visutil
from lib.data_management import generateRandomChargeData, writeChargeData, loadChargeData

import lib.graphing as graphing  #= lib/graphing/__init__.py
import lib.graphing.utility as graphutil
import lib.graphing.draw as graphdraw
import lib.graphing.dijkstra as dijkstra

from lib.structs.stationinfo import StationInfo, StationInfoDataset
from lib.structs.trip import Trip, TripDataset
from lib.structs.graphtranslator import GraphTranslator
from lib.structs.evaluation import Evaluation, EvaluationDataset
from lib.structs.params import Parameters

import lib.algorithms.algorithms as alg

import lib.xml.tripsGen as tripsGen
import lib.xml.output as xmlOut

from lib.sumo.blank import sumoBlankRun
from lib.sumo.comp import sumoCompRun

MAIN_DIR = pathlib.Path(__file__).resolve().parent
os.chdir(MAIN_DIR)


def stationDistributionStart(weights_dict, already_chosen=None):
    # Get first station by selecting the edge with the biggest weight value
    if (already_chosen is not None) and (len(already_chosen) > 0):
        weights_dict_new = {}
        for key, val in weights_dict.items():
            if key not in already_chosen:
                weights_dict_new[key] = val
        weights_dict = weights_dict_new
    max_value = max(weights_dict.values())
    best_edges = [(u, v) for (u, v), w in weights_dict.items()if w == max_value]
    if len(best_edges) == 1:
        first_station = best_edges[0];
    else:
        first_station = random.choice(best_edges)
    return first_station
RANDOM_STATIONS = False
def stationDistribution(G, base_G_d, k, output_path, edge_value_weights="length",
                        first_station=None, already_chosen=None, debug=False):
    G_d = copy.deepcopy(base_G_d)
    candidates = graphing.calcCandidates(G_d, detailed_graph=True) #candidate_edges=candidate_edges_d
    if already_chosen is not None and len(already_chosen) > 0:
        candidates = candidates - already_chosen
    ## Charging stations
    #print("-- Station distribution algorithm (" +
    #      ("random" if RANDOM_STATIONS else "binary search") +
    #      ") started...")
    alg_stime = time.perf_counter()
    # Get station locations (edges)
    if RANDOM_STATIONS:
        # -> random
        stations_d = alg.pickRandom(candidates, k)
        radius = 0
    else:
        # -> algorithm
        if isinstance(edge_value_weights, str):
            edge_value_weights = nx.get_edge_attributes(G, edge_value_weights);
        radius, stations_d = alg.radiusBinarySearch_EdgeWeights(G, G_d, candidates, k,
                                                                edge_value_weights=edge_value_weights,
                                                                first_station=first_station,
                                                                distribution_alg=alg.farthestFirstCoverageBased_EdgeWeights,
                                                                debug=debug)
        #radius, stations_d = alg.radiusBinarySearch(G, G_d, candidates, k, epsilon=1,
        #                                            distribution_alg=alg.farthestFirstCoverageBased, debug=debug)
    alg_etime = time.perf_counter()
    # Save plot output
    if not RANDOM_STATIONS:
        plt.clf()
        graphdraw.drawCenters(G_d, stations_d, radius, node_labels=False, edge_labels=False)
        plt.savefig(output_path + "/distribution.jpg"); plt.clf();
    #
    #print(f"-- Station distribution finished in {alg_etime - alg_stime:0.2f} seconds")
    #stations_edges = [graphutil.translateDetailedRoad(s, as_tuple=False) for s in stations_d]
    #print("Edges selected for stations:", stations_edges)
    return stations_d, radius

def runSimulation(network_name, G, stations, all_stations, base_trips, charge_data, prices, params, results, iteration=None, debug=False):
    trips = copy.deepcopy(base_trips)
    output_subfolder = "cover" + str(len(stations));
    if iteration != None: output_subfolder += "_" + str(iteration);
    return sumoCompRun(base_net, G, data_path, network_name, trips, stations, all_stations,
                        results, output_path=output_path, output_subfolder=output_subfolder,
                        charge_data=charge_data, prices=prices, agent_colors=agent_colors,
                        params=params, debug=debug)


###### SETTINGS
agent_colors = ["red", "blue", "green", "orange", "purple", "olive", "brown", "cyan", "pink", "gray"]

if __name__ == "__main__":
    # Parse arguments
    if len(sys.argv) < 2:
        network_name = "manhattan";
        args = []
    else:
        network_name = sys.argv[1]
        args = parseArgs(sys.argv[2:])
    # Adjust params
    params = Parameters.config()
    # Load params
    VEHICLE_COUNT = params["sim.vehicleCount"]
    MIN_DISTANCE = params["sim.minDistance"]
    MAX_DISTANCE = params["sim.maxDistance"]
    PRINT_ERRORS = params["sim.printErrors"]
    EV_PEN = params["electric.penetration"]
    STATION_CAPACITY = params["station.capacity"]
    K = params["station.k"]
    ITERATIONS = params["training.iterations"]
    if "iterations" in args:
        ITERATIONS = int(args["iterations"])
        params["training.iterations"] = ITERATIONS
    AGENT_COUNT = params["training.agents"]
    if "agent-count" in args:
        AGENT_COUNT = int(args["agent-count"])
        params["training.agents"] = AGENT_COUNT
    MIN_PRICE = params["training.minPrice"]
    MAX_PRICE = params["training.maxPrice"]
    EMA_ALPHA = params["training.coefficients.emaAlpha"]
    print(params.groupPrint())
    # Inform about arg changes
    if "iterations" in args:
        print(f"INFO: Set ITERATIONS to {ITERATIONS} by received argument.")
    if "agent-count" in args:
        print(f"INFO: Set AGENT_COUNT to {AGENT_COUNT} by received argument.")
    # Charge routing info
    if params["station.routing.useStationFinder"]:
        print("INFO: Using StationFinder for vehicle charging and station routing.")
    else:
        charge_routing_str = "centralized" if (params["station.routing.centralized"]) else "selfish";
        print("INFO: Using " + charge_routing_str + " policy for station routing.")
    # Divide K
    if K % AGENT_COUNT == 0:
        K = int(K / AGENT_COUNT); params["station.k"] = K;
        print(f"INFO: Every agent chooses {K} stations.")
    else:
        print(f"WARNING: k ({K}) is not divisible by {AGENT_COUNT}, using it unchanged.")
    # Get prices
    prices = []
    base_price = params["station.moneyPerKWh"]
    for a in range(AGENT_COUNT):
        if a < len(agent_colors):
            param_name = "station.moneyPerKWh." + agent_colors[a]
            if param_name in params:
                prices.append(params[param_name])
                continue
        if PRINT_ERRORS:
            print(f"WARNING: Failed to fetch price for agent #{a} ('{agent_colors[a]}').")
        prices.append(base_price)
    print(f"INFO: Using prices: {prices} € per kWh.")
    # Traci switch
    global libsumo_m, traci_m
    traci = libsumo_m

###### LOADING
    # Folder paths (file organization)
    data_path = "networks/" + network_name + "/";
    in_data_path = data_path + network_name;
    output_path = "output/"
    print("Using network '" + network_name + "' under '" + data_path + "'")
    ## Graph
    base_net = sumolib.net.readNet(data_path + "/base_net.net.xml")
    base_G = graphing.netToGraph(data_path + "/base_net.net.xml",
                                 lengths=True, travel_time=True,
                                 internal_lengths=True, node_position=True)
    base_G_d = graphing.netToDetailedGraph(data_path + "/base_net.net.xml")
    # Edge translator
    translator = GraphTranslator(base_G)
    ## Other
    global network_diameter
    network_diameter = graphutil.diameter(base_G, weight="length")
    suffixes = [("_" + n) for n in agent_colors]
    if MIN_DISTANCE < 0:
        MIN_DISTANCE = abs(MIN_DISTANCE * network_diameter)
    if MAX_DISTANCE < 0:
        MAX_DISTANCE = abs(MAX_DISTANCE * network_diameter)
###### PRE-RUN
    start_datetime_str = str(datetime.now().strftime('%Y%m%d_%H%M%S'))
    output_folder = network_name + "_cover" + str(AGENT_COUNT) + "_" + start_datetime_str
    output_path = output_path + "/" + output_folder
    pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
    pathlib.Path(output_path + "/training").mkdir(parents=True, exist_ok=True)
    # Save params and metadata
    params.write(output_path + "/config.xml")
    xmlOut.writeMetadata(output_path + "/metadata.xml", network_name, start_datetime_str, "cover",
                         network_diameter=network_diameter)
    #candidate_edges = graphing.getCandidateEdges(base_G, base_net)
    ## Vehicle data
    if "vehicle-data" in args:
        # Load
        trips = TripDataset.parseXML(base_G, translator, args["vehicle-data"] + "/trips.xml")
        trips.write(output_path + "/trips.xml")
        charge_data = loadChargeData(args["vehicle-data"] + "/charge_data.xml")
        print(f"INFO: Successfully loaded vehicle data for {len(trips.dict)} vehicles from '{args['vehicle-data']}'")
    else:
        # Generate trips
        trips = tripsGen.main(base_net, base_G, VEHICLE_COUNT, output_path + "/trips.xml",
                                #[0, 0, 0, 0.3, 0.5, 0.2],  #4 -> 0.3; 5 -> 0.5 -> 6 -> 0.2
                                destination_count_probs=[0, 0.3, 0.5, 0.2],  #2 -> 0.3; 3 -> 0.5 -> 4 -> 0.2
                                #min_distance_per_des=(network_diameter / 4.0),
                                min_distance=MIN_DISTANCE, #network_diameter*0.5,
                                max_distance=MAX_DISTANCE, #network_diameter*2.0,
                                ev_pen=EV_PEN)
                                #candidate_edges=candidate_edges)
        # Generate charge data
        vTypes_tree = ET.parse("networks/vTypes.add.xml")
        max_charge = prep.getMaxChargeFromAddTree(vTypes_tree)
        charge_data = generateRandomChargeData(trips, max_charge)
    # Save used charge data
    writeChargeData(charge_data, output_path + "/charge_data.xml")
    # Generate candidates
    #candidate_edges = graphing.getCandidateEdges_trips(base_G, base_net, trips)
    #print(candidate_edges)
    #candidate_edges_d = []
    #for edge_tup in candidate_edges:
    #    edge_d = graphutil.translateEdgeToDetailedEdgeTuple(edge_tup)
    #    candidate_edges_d.append(edge_d)
    
###### BLANK RUN
    G = copy.deepcopy(base_G)
    results = Evaluation(translator)
    results = sumoBlankRun(base_net, data_path, network_name, trips, results, params=params,
                           output_path=output_path, output_subfolder="blank")
    G = graphutil.resultsToEdgeAttributes(G, translator, ["vehicles", "flow"], results)
    flow_dict = nx.get_edge_attributes(G, "flow")
    #flow_dict = {k: v for k, v in flow_dict.items() if k in candidate_edges}
    
###### RUN
    pbar = tqdm(total=ITERATIONS)
    best = None; train_results = initializeResultsDict(params, ITERATIONS, K, AGENT_COUNT);
    loop_stime = time.perf_counter();
    for iteration in range(ITERATIONS):
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
            #st = StationInfoDataset([StationInfo.fromDetailedEdge(s, STATION_CAPACITY, prices[a], suffix=suffixes[a]) for s in st])
            st = StationInfoDataset([StationInfo(s, STATION_CAPACITY, prices[a], suffix=suffixes[a]) for s in stations_ids])
            stations.append(st); dist_radius.append(dr);
            all_stations.extend(st.arr)
            #print("-- " + str(agent_colors[a].capitalize()) + " stations:", stations[a].printEdges())
        all_stations = StationInfoDataset(all_stations)
        #### Captured demand
        # Partition edges to closest station
        sources = []
        for si in all_stations:
            edge_id = si.edge_id
            sources.append(translator.IDToEdge(edge_id))
        partitions = dijkstra.voronoiPartitions(base_G, sources, use_internal=True, return_distances=True)
        #graphdraw.drawVoronoiPartitions(base_G, partitions)
        # Get demand from partitions
        agent_demand = [];
        for a in range(AGENT_COUNT):
            demand = 0.0
            for si in stations[a]:
                st_edge_id = si.edge_id
                st_edge_tup = translator.IDToEdge(st_edge_id)
                for edge, distance in partitions[st_edge_tup]:
                    edge_demand = G[st_edge_tup[0]][st_edge_tup[1]]["flow"]
                    edge_demand *= np.exp(-0.01 * distance)
                    demand += edge_demand
            agent_demand.append(float(demand))
        #print(agent_demand)
        # Normalize
        demand_mean = float(np.mean(agent_demand))
        demand_sum = sum(agent_demand)
        agent_demand_norm = [];
        for a in range(AGENT_COUNT):
            # Mean deviation
            agent_demand_norm.append((agent_demand[a] - demand_mean) / (demand_mean + 1e-10))
            # Relative
            #agent_demand_norm.append(agent_demand[a] / demand_sum)
        # Update prices
        for a in range(AGENT_COUNT):
            prices[a] = prices[a] + (EMA_ALPHA * agent_demand_norm[a])
        #### Run
        # Prepare results
        results = Evaluation(translator)
        results = runSimulation(network_name, base_G, stations, all_stations, trips, charge_data, prices,
                      params, results, iteration=None, debug=False)
        G = graphutil.resultsToEdgeAttributes(G, translator, ["vehicles", "flow"], results)
        flow_dict = nx.get_edge_attributes(G, "flow")
        #flow_dict = {k: v for k, v in flow_dict.items() if k in candidate_edges}
        #### Bookkeeping
        # Update best
        if best is None:
            best = copy.deepcopy(results);
        else:
            # Compare with best
            res_ds = EvaluationDataset([results, best])
            scores = res_ds.calcScores(params)
            #print(f" >  {iteration+1:4d}:", scores[0], " | best:", scores[1])
            if scores[0] > scores[1]:
                best = copy.deepcopy(results);
                #print("> best updated!")
        # Update training results
        updateResultsDict_comp(train_results, stations, results, iteration)
        #### End iteration
        pbar.update(1)
        
    pbar.close()
    loop_etime = time.perf_counter();
    time_diff = loop_etime - loop_stime
    
###### FINISH AND SAVE
    pathlib.Path(output_path + "/results").mkdir(parents=True, exist_ok=True)
    if ITERATIONS == 1:
        # Save results
        res_dict = results.getFullDict(include_edge_data=True)
        #Evaluation.suffixesToNames(res_dict)
        res_tree = ET.ElementTree(ET.fromstring('<results></results>'))
        xmlOut.dictToElement_recursive(res_dict, res_tree.getroot())
        ET.indent(res_tree, space="    ")
        res_tree.write(output_path + "/results/results.xml");
        full_save_path = pathlib.Path(output_path + "/results.xml").resolve()
    else:
        # Save loop results data
        xmlOut.saveTrainResults_numpy(train_results, output_path + "/results/data")
        xmlOut.saveTrainResults_XML(train_results, output_path + "/results/data_visualize.xml")
        xmlOut.saveTrainResults_csv(train_results, output_path + "/results/data")
        xmlOut.saveTotalDuration_txt(time_diff, output_path + "/results")
        # Write plot figures
        figs = visutil.plotComp(train_results, iterations=ITERATIONS, agent_colors=agent_colors);
        for stat in figs:
            fig, ax = figs[stat]
            fig.savefig(output_path + f"/training/graph_" + stat + ".jpg")
        # Save best
        res_dict = best.getFullDict(include_edge_data=True)
        Evaluation.suffixesToNames(res_dict)
        res_tree = ET.ElementTree(ET.fromstring('<results></results>'))
        xmlOut.dictToElement_recursive(res_dict, res_tree.getroot())
        ET.indent(res_tree, space="    ")
        res_tree.write(output_path + "/training/best.xml");
        res_tree.write(output_path + "/results/best.xml");
        plt.show()
    # Print
    full_path = pathlib.Path(output_path + "/results/").resolve()
    print(f"\nTraining finished in {round(time_diff, 2)}, saved results inside\n'{full_path}'")
    # Clean up files
    if params["sim.deleteCache"] == True:
        xmlOut.cleanCache(output_path + "/_cache", network_name)

    
