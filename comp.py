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

global libsumo_m, traci_m
import libsumo as libsumo_m
import traci as traci_m

import preprocess as prep

import lib.graphing as graphing  #= lib/graphing/__init__.py
import lib.graphing.utility as graphutil
import lib.graphing.draw as graphdraw

from lib.structs.stationinfo import StationInfo, StationInfoDataset
from lib.structs.trip import Trip
from lib.structs.graphtranslator import GraphTranslator
from lib.structs.evaluation import Evaluation
from lib.structs.params import Parameters

import lib.algorithms.algorithms as alg

import lib.xml.tripsGen as tripsGen
import lib.xml.output as xmlOut

from lib.sumo.comp import sumoCompRun

MAIN_DIR = pathlib.Path(__file__).resolve().parent
os.chdir(MAIN_DIR)



RANDOM_STATIONS = True
def stationDistribution(G, G_d, k, debug=False):
    candidates = graphing.calcCandidates(G_d, detailed_graph=True)
    ## Charging stations
    print("-- Station distribution algorithm (" +
          ("random" if RANDOM_STATIONS else "binary search") +
          ") started...")
    alg_stime = time.perf_counter()
    # Get station locations (edges)
    if RANDOM_STATIONS:
        # -> random
        stations_d = alg.pickRandom(candidates, k)
        radius = 0
    else:
        # -> algorithm
        radius, stations_d = alg.radiusBinarySearch(G, G_d, candidates, k, epsilon=1,
                                                    distribution_alg=alg.farthestFirstCoverageBased, debug=debug)
    alg_etime = time.perf_counter()
    # Save plot output
    if not RANDOM_STATIONS:
        plt.clf()
        graphdraw.drawCenters(G_d, stations_d, radius, node_labels=False, edge_labels=False)
        plt.savefig(cache_output_path + "/distribution.jpg"); plt.clf();
    #
    #print(f"-- Station distribution finished in {alg_etime - alg_stime:0.2f} seconds")
    #stations_edges = [graphutil.translateDetailedRoad(s, as_tuple=False) for s in stations_d]
    #print("Edges selected for stations:", stations_edges)
    return stations_d, radius

def runSimulation(network_name, G, stations, all_stations, base_trips, prices, params, results, iteration=None, debug=False):
    trips = copy.deepcopy(base_trips)
    output_subfolder = "comp";
    if iteration != None: output_subfolder += "_" + str(iteration);
    results = sumoCompRun(base_net, G, data_path, network_name, trips, results, stations, all_stations,
                          output_path=output_path, output_subfolder=output_subfolder,
                          prices=prices, agent_colors=agent_colors,
                          params=params, debug=debug)
    return results


###### SETTINGS
agent_colors = ["red", "blue", "green", "orange", "purple", "olive", "brown", "cyan", "pink", "gray"]

if __name__ == "__main__":
    # Parse arguments
    if len(sys.argv) < 2: network_name = "manhattan";
    else: network_name = str(sys.argv[1]);
    # Adjust params
    params = Parameters.config()
    print(params.groupPrint())
    # Load params
    VEHICLE_COUNT = params["sim.vehicleCount"]
    MAX_DURATION = params["sim.maxDuration"]
    DURATION_SET = MAX_DURATION > 0
    MIN_DISTANCE = params["sim.minDistance"]
    MAX_DISTANCE = params["sim.maxDistance"]
    VISUALIZE = params["sim.visualize"]
    PRINT_ERRORS = params["sim.printErrors"]
    EV_PEN = params["electric.penetration"]
    STATION_CAPACITY = params["station.capacity"]
    K = params["station.k"]
    ITERATIONS = params["training.iterations"]
    AGENT_COUNT = params["training.agents"]
    EMA_ALPHA = params["training.emaAlpha"]
    MEASURE_TIME = params["training.measureTime"]
    PRINTS = params["training.progressDebugs"]
    PROGRESS_PRINT = params["training.printProgress"]
    PROGRESS_WRITE = params["training.writeProgress"]
    PROGRESS_DRAW = params["training.drawProgress"]
    print(params.groupPrint())
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
    print(f"INFO: Using prices: {prices}.")
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
                                 internal_lengths=False, node_position=True)
    base_G_d = graphing.netToDetailedGraph(data_path + "/base_net.net.xml")
    # Edge translator
    translator = GraphTranslator(base_G)
    ## Other
    global network_diameter
    network_diameter = float(nx.diameter(base_G, weight="length"))
    suffixes = [("_" + n) for n in agent_colors]
###### PRE-RUN
    start_datetime_str = str(datetime.now().strftime('%Y%m%d_%H%M%S'))
    output_folder = network_name + "_comp_" + start_datetime_str
    output_path = output_path + "/" + output_folder
    pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
    pathlib.Path(output_path + "/training").mkdir(parents=True, exist_ok=True)
    # Generate trips
    trips = tripsGen.main(base_net, base_G, VEHICLE_COUNT, output_path + "/trips.xml",
                            #[0, 0, 0, 0.3, 0.5, 0.2],  #4 -> 0.3; 5 -> 0.5 -> 6 -> 0.2
                            destination_count_probs=[0, 0.3, 0.5, 0.2],  #2 -> 0.3; 3 -> 0.5 -> 4 -> 0.2
                            #min_distance_per_des=(network_diameter / 4.0),
                            min_distance=network_diameter*0.5,
                            max_distance=network_diameter*2.0,
                            ev_pen=EV_PEN)
    # Station distribution
    stations = []; dist_radius = []; all_stations = [];
    for a in range(AGENT_COUNT):
        st, dr = stationDistribution(base_G, base_G_d, K)
        # Station info from detailed edges
        st = StationInfoDataset([StationInfo.fromDetailedEdge(s, STATION_CAPACITY, prices[a], suffix=suffixes[a]) for s in st])
        stations.append(st); dist_radius.append(dr);
        all_stations.extend(st.arr)
        print("-- " + str(agent_colors[a].capitalize()) + " stations:", stations[a].printEdges())
    all_stations = StationInfoDataset(all_stations)
    # Prepare results
    results = Evaluation(translator)
###### RUN
    results = runSimulation(network_name, base_G, stations, all_stations, trips, prices,
                  params, results, iteration=None, debug=False)

###### POSTPROCESS
    # Write results
    res_dict = results.getFullDict(include_edge_data=True)
    Evaluation.suffixesToNames(res_dict)
    res_tree = ET.ElementTree(ET.fromstring('<results></results>'))
    xmlOut.dictToElement_recursive(res_dict, res_tree.getroot())
    ET.indent(res_tree, space="    ")
    res_tree.write(output_path + "/results.xml");
    full_save_path = pathlib.Path(output_path + "/results.xml").resolve()
    print(f"Simulation finished, saved results under\n'{str(full_save_path)}'")

    
