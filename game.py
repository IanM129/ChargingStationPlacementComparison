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

import preprocess as prep

import lib.visual_utility as visutil

import lib.graphing as graphing  #= lib/graphing/__init__.py
import lib.graphing.utility as graphutil
from lib.graphing.utility import TupleEdge
import lib.graphing.draw as graphdraw

from lib.structs.stationinfo import StationInfo, StationInfoDataset
from lib.structs.trip_nx import TripNX, TripNXDataset
from lib.structs.graphtranslator import GraphTranslator
from lib.structs.evaluation import Evaluation, EvaluationDataset, getStatFromResult
from lib.structs.params import Parameters

import lib.algorithms.algorithms as alg

import lib.xml.tripsGen as tripsGen
import lib.xml.output as xmlOut

from lib.algorithms.equilibriumGame import equilibriumGameRun

MAIN_DIR = pathlib.Path(__file__).resolve().parent
os.chdir(MAIN_DIR)

########## BOOKKEEPING
def initializeResultsDict(params, iteration_count, K):
    train_results = {}
    for p in params.groups["reward"]:
        if params["reward." + p + ".monitor"] == True:
            train_results[p] = np.zeros(iteration_count)
    train_results["stations"] = np.empty((iteration_count, K), dtype=np.dtypes.StringDType())
    return train_results
def updateResultsDict(train_results, stations, results, iteration):
    for p in train_results:
        if p == "stations":
            train_results[p][iteration] = stations.listEdges();
        else:
            train_results[p][iteration] = getStatFromResult(results, p)


def generateRandomChargeAmounts(vehicle_ids, max_charge):
    charge_amounts = {}
    for vehID in vehicle_ids:
        # Set amount to charge (starts with 50% and needs to charge to 50% + [250,750]
        need_to_charge_amount = random.uniform(0.25, 0.75) * 1000.0
        charge_amounts[vehID] = float(min((0.5 * max_charge) + need_to_charge_amount, max_charge))
    return charge_amounts


def startingStationDistribution(candidates, k, detailed=True):
    # Random
    stations = alg.pickRandom(candidates, k)
    # StationInfo from detailed edges
    if detailed:
        stations = StationInfoDataset([StationInfo.fromDetailedEdge(s, STATION_CAPACITY, MONEY_PER_KWH) for s in stations])
    else:
        stations = StationInfoDataset([StationInfo(s, STATION_CAPACITY, MONEY_PER_KWH) for s in stations])
    return stations    
def stationDistribution(G, k, last_stations):
    stations = last_stations
    return stations

def costFunction(G, vehID, trip : TripNX, stations, congestion, translator):
    # Coefficients
    distance_c = 0.0; travelTime_c = 1.0; congestion_c = 10.0;
    chosen = None; chosen_trip = None; min_cost = 0.0;
    for si in stations:
        tedge = si.redge_id #translator.IDToEdge(si.edge_id)  #TupleEdge()
        # For each possible detour
        for i in range(1, len(trip.destinations)):
            cost = 0;
            # Get detour trip
            trip_st = copy.deepcopy(trip)
            trip_st.insert(translator.IDToEdge(tedge), i)
            # Calculate distance
            path = trip_st.path
            distance = graphutil.edgePathLength(G, trip_st.path)
            cost += distance * distance_c
            # Calculate travel time
            travel_time = graphutil.edgePathLength(G, trip_st.path, weight="travelTime", use_internal=False)
            cost += travel_time * travelTime_c
            # Add congestion
            cost += congestion[si.edge_id] * congestion_c
            #print(travel_time, "+ (" + str(congestion[si.edge_id]), "* 20.0) =", cost)
            # Update
            if chosen is None or cost < min_cost:
                chosen = si.edge_id; chosen_trip = trip_st;
                min_cost = cost;
    return chosen, chosen_trip

def findEquilibrium(network_name, base_net, base_G, stations, base_trips, charge_amounts,
                    params, results, iteration=None, debug=False):
    trips = copy.deepcopy(base_trips)
    output_subfolder = "game";
    if iteration != None: output_subfolder += "_" + str(iteration);
    results = equilibriumGameRun(base_net, base_G, data_path, network_name, trips, charge_amounts, stations, costFunction,
                                 results, output_path=output_path, output_subfolder=output_subfolder,
                                 params=params, debug=debug)
    return results

###### MAIN
if __name__ == "__main__":
    # Parse arguments
    if len(sys.argv) < 2: network_name = "manhattan";
    else: network_name = str(sys.argv[1]);
    # Adjust params
    params = Parameters.config()
    params["agents"] = 1
    # Load params
    VEHICLE_COUNT = params["sim.vehicleCount"]
    DESTINATION_COUNT_DIST = params["sim.destinationCountDistribution"]
    MIN_DISTANCE = params["sim.minDistance"]
    MAX_DISTANCE = params["sim.maxDistance"]
    if params["sim.visualize"]:
        params["sim.visualize"] = False
    #params["sim.visualize"] = True
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
    network_diameter = float(nx.diameter(base_G, weight="length"))
    if MIN_DISTANCE < 0:
        MIN_DISTANCE = abs(MIN_DISTANCE * network_diameter)
    if MAX_DISTANCE < 0:
        MAX_DISTANCE = abs(MAX_DISTANCE * network_diameter)
        
###### PRE-RUN
    start_datetime_str = str(datetime.now().strftime('%Y%m%d_%H%M%S'))
    output_folder = network_name + "_game_" + start_datetime_str
    output_path = output_path + "/" + output_folder
    pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
    pathlib.Path(output_path + "/training").mkdir(parents=True, exist_ok=True)
    # Save params and metadata
    params.write(output_path + "/config.xml")
    xmlOut.writeMetadata(output_path + "/metadata.xml", network_name, start_datetime_str, "solo")
    ## Generate vehicles
    # Generate trips
    trips = tripsGen.main(base_net, base_G, VEHICLE_COUNT, output_path + "/trips.xml",
                            #[0, 0, 0, 0.3, 0.5, 0.2],  #4 -> 0.3; 5 -> 0.5 -> 6 -> 0.2
                            destination_count_probs=DESTINATION_COUNT_DIST,
                            #min_distance_per_des=(network_diameter / 4.0),
                            min_distance=MIN_DISTANCE, #network_diameter*0.5,
                            max_distance=MAX_DISTANCE, #network_diameter*2.0,
                            ev_pen=EV_PEN)
    # Generate charging amount
    vTypes_tree = ET.parse("networks/vTypes.add.xml")
    max_charge = prep.getMaxChargeFromAddTree(vTypes_tree)
    charge_amounts = generateRandomChargeAmounts(trips.EVs(), max_charge)
    ## Station distribution
    # Discretize graph and get candidates
    G_d = base_G_d.copy()
    print(G_d)
    candidates = graphing.calcCandidates(G_d, detailed_graph=True)
    print(G_d)
    #graphdraw.drawGraph(G_d)
    #import matplotlib.pyplot as plt
    #plt.show()
    # Starting selection -> random
    stations = startingStationDistribution(candidates, K, detailed=True)
    #print("-- starting stations:", stations.printEdges())
    # Prepare results
    results = Evaluation(translator)
    print("")

###### RUN
    ITERATIONS = params["training.iterations"]
    pbar = tqdm(total=ITERATIONS)
    best = None; train_results = initializeResultsDict(params, ITERATIONS, K);
    loop_stime = time.perf_counter();
    for i in range(ITERATIONS):
        # Find selection equilibrium and run evaluation
        results = findEquilibrium(network_name, base_net, base_G, stations, trips, charge_amounts,
                                  params, results, iteration=None, debug=False)
        updateResultsDict(train_results, stations, results, i)
        # Update best
        if best is None:
            best = copy.deepcopy(results);
            print(f" >  {i+1:4d} done")
        else:
            # Compare with best
            res_ds = EvaluationDataset([results, best])
            scores = res_ds.calcScores(params)
            print(f" >  {i+1:4d}:", scores[0], " | best:", scores[1])
            if scores[0] > scores[1]:
                best = copy.deepcopy(results);
                #print("> best updated!")
        # Get new stations
        stations = startingStationDistribution(candidates, K, detailed=True)
        pbar.update(1)
    pbar.close()
    loop_etime = time.perf_counter();
    time_diff = loop_etime - loop_stime
    #### Finish and save
    pathlib.Path(output_path + "/results").mkdir(parents=True, exist_ok=True)
    # Save loop results data
    xmlOut.saveTrainResults_numpy(train_results, output_path + "/results/data")
    xmlOut.saveTrainResults_XML(train_results, output_path + "/results/data_visualize.xml")
    xmlOut.saveTrainResults_csv(train_results, output_path + "/results/data")
    # Write plot figures
    figs = visutil.plotTrainingResults_figs(train_results, ITERATIONS)
    for stat in figs:
        fig, ax = figs[stat]
        fig.savefig(output_path + f"/training/graph_" + stat + ".jpg")
    # Clean up files
    if params["sim.deleteCache"]:
        xmlOut.cleanCache(output_path + "/_cache", network_name)
    # Print
    full_path = pathlib.Path(output_path + "/results/").resolve()
    print(f"Loop finished in {round(time_diff, 2)}, saved results inside\n'{full_path}'")
    # Show loop results
    plt.show()
    
