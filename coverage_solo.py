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

from lib.utility import parseArgs, initializeResultsDict, updateResultsDict
import lib.visual_utility as visutil
from lib.data_management import generateRandomChargeData, writeChargeData, loadChargeData

import lib.graphing as graphing  #= lib/graphing/__init__.py
import lib.graphing.utility as graphutil
import lib.graphing.draw as graphdraw

from lib.structs.stationinfo import StationInfo, StationInfoDataset
from lib.structs.trip import Trip, TripDataset
from lib.structs.graphtranslator import GraphTranslator
from lib.structs.evaluation import Evaluation, EvaluationDataset
from lib.structs.params import Parameters

import lib.algorithms.algorithms as alg

import lib.xml.tripsGen as tripsGen
import lib.xml.output as xmlOut

from lib.sumo.blank import sumoBlankRun
from lib.sumo.solo import sumoSoloRun

MAIN_DIR = pathlib.Path(__file__).resolve().parent
os.chdir(MAIN_DIR)


def stationDistributionStart(weights_dict):
    # Get first station by selecting the edge with the biggest weight value
    max_value = max(weights_dict.values())
    best_edges = [(u, v) for (u, v), w in weights_dict.items()if w == max_value]
    if len(best_edges) == 1:
        first_station = best_edges[0];
    else:
        first_station = random.choice(best_edges)
    return first_station
RANDOM_STATIONS = False
def stationDistribution(G, base_G_d, k, output_path, edge_value_weights="length", first_station=None, debug=False):
    G_d = copy.deepcopy(base_G_d)
    candidates = graphing.calcCandidates(G_d, detailed_graph=True)  #candidate_edges=candidate_edges_d
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

def runSimulation(network_name, G, stations, base_trips, charge_data, params, results, iteration=None, debug=False):
    trips = copy.deepcopy(base_trips)
    output_subfolder = "cover1";
    if iteration != None: output_subfolder += "_" + str(iteration);
    results = sumoSoloRun(base_net, G, data_path, network_name, trips, stations, results,
                          output_path=output_path, output_subfolder=output_subfolder,
                          charge_data=charge_data,
                          params=params, debug=debug)
    return results


###### SETTINGS

###### MAIN
if __name__ == "__main__":
    # Parse arguments
    if len(sys.argv) < 2:
        network_name = "manhattan";
        args = {}
    else:
        network_name = sys.argv[1]
        args = parseArgs(sys.argv[2:])
    print(args)
    # Adjust params
    params = Parameters.config()
    params["agents"] = 1
    # Load params
    VEHICLE_COUNT = params["sim.vehicleCount"]
    DESTINATION_COUNT_DIST = params["sim.destinationCountDistribution"]
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
    params["training.agents"] = 1;
    MONEY_PER_KWH = params["station.moneyPerKWh"]
    print(params.groupPrint())
    # Inform about args changes
    if "iterations" in args:
        print(f"INFO: Set ITERATIONS to {ITERATIONS} by received argument.")
    # Charge routing info
    if params["station.routing.useStationFinder"]:
        print("INFO: Using StationFinder for vehicle charging and station routing.")
    else:
        charge_routing_str = "centralized" if (params["station.routing.centralized"]) else "selfish";
        print("INFO: Using " + charge_routing_str + " policy for station routing.")
    # Get price
    print(f"INFO: Using price: {MONEY_PER_KWH} € per kWh.")
    # Traci switch
    global libsumo_m, traci_m
    traci = libsumo_m

###### LOADING
    # Folder paths (file organization)
    data_path = "networks/" + network_name + "/";
    in_data_path = data_path + network_name;
    output_path = "output/"
    print("INFO: Using network '" + network_name + "' under '" + data_path + "'")
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
    if MIN_DISTANCE < 0:
        MIN_DISTANCE = abs(MIN_DISTANCE * network_diameter)
    if MAX_DISTANCE < 0:
        MAX_DISTANCE = abs(MAX_DISTANCE * network_diameter)
    #candidate_edges = graphing.getCandidateEdges(base_G)
    #candidate_edges_d = []
    #for edge_tup in candidate_edges:
    #    edge_d = graphutil.translateEdgeToDetailedEdgeTuple(edge_tup)
    #    candidate_edges_d.append(edge_d)
###### PRE-RUN
    start_datetime_str = str(datetime.now().strftime('%Y%m%d_%H%M%S'))
    output_folder = network_name + "_cover1_" + start_datetime_str
    output_path = output_path + "/" + output_folder
    pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
    pathlib.Path(output_path + "/training").mkdir(parents=True, exist_ok=True)
    # Save params and metadata
    params.write(output_path + "/config.xml")
    xmlOut.writeMetadata(output_path + "/metadata.xml", network_name, start_datetime_str, "cover",
                         network_diameter=network_diameter)
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
                                destination_count_probs=DESTINATION_COUNT_DIST,
                                #min_distance_per_des=(network_diameter / 4.0),
                                min_distance=MIN_DISTANCE, #network_diameter*0.5,
                                max_distance=MAX_DISTANCE, #network_diameter*2.0,
                                ev_pen=EV_PEN)
        # Generate charge data
        vTypes_tree = ET.parse("networks/vTypes.add.xml")
        max_charge = prep.getMaxChargeFromAddTree(vTypes_tree)
        charge_data = generateRandomChargeData(trips, max_charge)
    # Save used charge data
    writeChargeData(charge_data, output_path + "/charge_data.xml")
    
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
    best = None; train_results = initializeResultsDict(params, ITERATIONS, K, 1);
    loop_stime = time.perf_counter();
    for iteration in range(ITERATIONS):
        # Get first station
        first_station = stationDistributionStart(flow_dict)
        #first_station = base_G[first_station[0]][first_station[1]]["id"]
        #print("first_station:", first_station)
        # Station distribution
        stations_d, dist_radius = stationDistribution(base_G, base_G_d, K, output_path,
                                                      edge_value_weights=flow_dict,
                                                      first_station=first_station)
        # Station info from detailed edges
        stations_ids = []
        for st_d in stations_d:
            from_node, to_node = graphutil.getNodesOfDetailedRoad(st_d)
            if base_G.has_edge(from_node, to_node):
                edge_id = base_G[from_node][to_node]["id"]
            else:
                edge_id = base_G[to_node][from_node]["id"]
            stations_ids.append(edge_id)
        #stations = StationInfoDataset([StationInfo.fromDetailedEdge(s, STATION_CAPACITY, MONEY_PER_KWH) for s in stations])
        stations = StationInfoDataset([StationInfo(s, STATION_CAPACITY, MONEY_PER_KWH) for s in stations_ids])
        #print("-- stations:", stations.printEdges())
        #### Run
        # Prepare results
        results = Evaluation(translator)
        results = runSimulation(network_name, base_G, stations, trips, charge_data,
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
        updateResultsDict(train_results, stations, results, iteration)
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
        figs = visutil.plotSolo(train_results, iterations=ITERATIONS);
        for stat in figs:
            fig, ax = figs[stat]
            fig.savefig(output_path + f"/training/graph_" + stat + ".jpg")
        # Save best
        res_dict = best.getFullDict(include_edge_data=True)
        res_tree = ET.ElementTree(ET.fromstring('<results></results>'))
        xmlOut.dictToElement_recursive(res_dict, res_tree.getroot())
        ET.indent(res_tree, space="    ")
        res_tree.write(output_path + "/training/best.xml");
        res_tree.write(output_path + "/results/best.xml");
        plt.show()
    # Print
    full_path = pathlib.Path(output_path + "/results/").resolve()
    print(f"\nTraining finished in {round(time_diff, 2)}, saved results inside\n'{full_path}'")
    #print(f"Simulation finished, saved results under\n'{str(full_save_path)}'")
    # Clean up files
    if params["sim.deleteCache"] == True:
        xmlOut.cleanCache(output_path + "/_cache", network_name)


    
