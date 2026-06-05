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

from lib.sumo.solo import sumoSoloRun

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

def runSimulation(network_name, G, stations, base_trips, params, results, iteration=None, debug=False):
    trips = copy.deepcopy(base_trips)
    output_subfolder = "solo";
    if iteration != None: output_subfolder += "_" + str(iteration);
    results = sumoSoloRun(base_net, G, data_path, network_name, trips, results, stations,
                          output_path=output_path, output_subfolder=output_subfolder,
                          params=params, debug=debug)
    return results


###### SETTINGS

###### MAIN
if __name__ == "__main__":
    # Parse arguments
    if len(sys.argv) < 2: network_name = "manhattan";
    else: network_name = str(sys.argv[1]);
    # Adjust params
    params = Parameters.config()
    print(params.groupPrint())
    # Load params
    VEHICLE_COUNT = params["sim.vehicleCount"]
    DESTINATION_COUNT_DIST = params["sim.destinationCountDistribution"]
    MIN_DISTANCE = params["sim.minDistance"]
    MAX_DISTANCE = params["sim.maxDistance"]
    PRINT_ERRORS = params["sim.printErrors"]
    EV_PEN = params["electric.penetration"]
    STATION_CAPACITY = params["station.capacity"]
    K = params["station.k"]
    MONEY_PER_KWH = params["station.moneyPerKWh"]
    print(params.groupPrint())
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
    if MIN_DISTANCE < 0:
        MIN_DISTANCE = abs(MIN_DISTANCE * network_diameter)
    if MAX_DISTANCE < 0:
        MAX_DISTANCE = abs(MAX_DISTANCE * network_diameter)
###### PRE-RUN
    start_datetime_str = str(datetime.now().strftime('%Y%m%d_%H%M%S'))
    output_folder = network_name + "_solo_" + start_datetime_str
    output_path = output_path + "/" + output_folder
    pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
    pathlib.Path(output_path + "/training").mkdir(parents=True, exist_ok=True)
    # Generate trips
    trips = tripsGen.main(base_net, base_G, VEHICLE_COUNT, output_path + "/trips.xml",
                            #[0, 0, 0, 0.3, 0.5, 0.2],  #4 -> 0.3; 5 -> 0.5 -> 6 -> 0.2
                            destination_count_probs=DESTINATION_COUNT_DIST,
                            #min_distance_per_des=(network_diameter / 4.0),
                            min_distance=MIN_DISTANCE, #network_diameter*0.5,
                            max_distance=MAX_DISTANCE, #network_diameter*2.0,
                            ev_pen=EV_PEN)
    # Station distribution
    stations = []; dist_radius = 0.0;
    stations, dist_radius = stationDistribution(base_G, base_G_d, K)
    # Station info from detailed edges
    stations = StationInfoDataset([StationInfo.fromDetailedEdge(s, STATION_CAPACITY, MONEY_PER_KWH) for s in stations])
    print("-- stations:", stations.printEdges())
    # Prepare results
    results = Evaluation(translator)
###### RUN
    results = runSimulation(network_name, base_G, stations, trips,
                  params, results, iteration=None, debug=False)

###### POSTPROCESS
    # Write results
    res_dict = results.getFullDict(include_edge_data=True)
    #Evaluation.suffixesToNames(res_dict)
    res_tree = ET.ElementTree(ET.fromstring('<results></results>'))
    xmlOut.dictToElement_recursive(res_dict, res_tree.getroot())
    ET.indent(res_tree, space="    ")
    res_tree.write(output_path + "/results.xml");
    full_save_path = pathlib.Path(output_path + "/results.xml").resolve()
    print(f"Simulation finished, saved results under\n'{str(full_save_path)}'")

    
