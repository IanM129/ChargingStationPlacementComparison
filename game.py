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

import threading

import preprocess as prep

import lib.visual_utility as visutil
from lib.utility import parseArgs
from lib.data_management import generateRandomChargeData, writeChargeData, loadChargeData

import lib.graphing as graphing  #= lib/graphing/__init__.py
import lib.graphing.utility as graphutil
from lib.graphing.utility import TupleEdge
import lib.graphing.draw as graphdraw

from lib.structs.stationinfo import StationInfo, StationInfoDataset
from lib.structs.trip import Trip, TripDataset
from lib.structs.trip_nx import TripNX, TripNXDataset
from lib.structs.graphtranslator import GraphTranslator
from lib.structs.evaluation import Evaluation, EvaluationDataset, getStatFromResult
from lib.structs.params import Parameters

import lib.algorithms.algorithms as alg

from lib.xml.parkingNetGen import getEdgeID as parkNetGen_getEdgeID
import lib.xml.parkingNetGen as parkingNetGen
import lib.xml.tripsGen as tripsGen
import lib.xml.output as xmlOut

from lib.algorithms.equilibriumGame import equilibriumGameRun

MAIN_DIR = pathlib.Path(__file__).resolve().parent
os.chdir(MAIN_DIR)



def fixTripsForAllCandidatesGraph(base_net, G_all, trips):
    for vehID, trip in trips.dict.items():
        for i in range(len(trip.destinations)):
            edge_id = trip.destinations[i]
            edge = base_net.getEdge(edge_id)
            fnode = edge.getFromNode().getID()
            tnode = edge.getToNode().getID()
            road = graphutil.getRoadIDFromNodes(fnode, tnode);
            trip.destinations[i] = ("pcsEntry_" + edge_id, tnode)
    trips_nx_cov = TripNXDataset.fromTripDataset(G_all, trips)
    return trips_nx_cov

def getStationUsers(chosen_station, stations):
    station_users = {}
    for si in stations:
        station_users[si.edge_id] = set()
    for vehID, si in chosen_station.items():
        station_users[si.edge_id].add(vehID);
    return station_users



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

########## COST
def detourCost(G, vehID, trip : TripNX, st_redge_tup : tuple, chosen_trip=None):
    # Check if in matrix
    global sttn_cand_index, detour_matrix
    cand_index = sttn_cand_index[st_redge_tup]
    if detour_matrix[int(vehID)][cand_index][0] >= 0.0:
        return detour_matrix[int(vehID)][cand_index][0], detour_matrix[int(vehID)][cand_index][1]
    else:
        # Coefficients
        distance_c = 0.0; travelTime_c = 1.0;
        min_cost = np.inf; chosen_insert_index = -1;
        # For each possible detour (detourCost)
        for i in range(1, len(trip.destinations)):
            cost = 0.0;
            # Get detour trip
            trip_st = copy.deepcopy(trip)
            insert_ret = trip_st.insert(st_redge_tup, i)
            if insert_ret is None: continue;
            # Calculate distance
            path = trip_st.path
            distance = graphutil.edgePathLength(G, trip_st.path, weight="length", use_internal=True)
            cost += distance * distance_c
            # Calculate travel time
            travel_time = graphutil.edgePathLength(G, trip_st.path, weight="travelTime", use_internal=False)
            cost += travel_time * travelTime_c
            # Update
            if chosen_trip is None or cost < min_cost:
                chosen_insert_index = i; min_cost = cost;
                chosen_trip = trip_st;
        # Update matrix
        detour_matrix[int(vehID)][cand_index][0] = chosen_insert_index
        detour_matrix[int(vehID)][cand_index][1] = min_cost
        return chosen_insert_index, min_cost
def costFunction(G, vehID, trip : TripNX, stations, cur_chosen, congestion, translator, return_cost=False):
    # Coefficients
    congestion_c = 10.0;
    # Return vars
    chosen_sttn = None; chosen_trip = None; min_cost = np.inf;
    ## Total detour cost for each station
    for si in stations:
        redge_tuple = translator.IDToEdge(si.redge_id)
        # Calculate
        trip_st = None
        insertIndex, cost = detourCost(G, vehID, trip, redge_tuple, chosen_trip=trip_st)
        if insertIndex == -1: continue;
        # Add congestion
        cong = congestion[si.edge_id]
        if cur_chosen is None or si != cur_chosen: cong += 1;
        cost += cong * congestion_c
        # Recreate trip if not set
        if (trip_st is None):
            trip_st = copy.deepcopy(trip)
            insert_ret = trip_st.insert(redge_tuple, insertIndex)
        ## Update
        if chosen_sttn is None or cost < min_cost:
            chosen_sttn = si; chosen_trip = trip_st;
            min_cost = cost;
    # Convert insert index to trip
    if isinstance(chosen_trip, int):
        trip_st = copy.deepcopy(trip)
        trip_st.insert(translator.IDToEdge(chosen_sttn.redge_id), chosen_trip)
        chosen_trip = trip_st
    if return_cost: return chosen_sttn, chosen_trip, cost
    return chosen_sttn, chosen_trip

########## STATION DISTRIBUTION
def startingStationDistribution(candidates, k, detailed=True):
    # Random for first distribution
    stations = alg.pickRandom(candidates, k)
    # StationInfo from detailed edges
    if detailed:
        stations = StationInfoDataset([StationInfo.fromDetailedEdge(s, STATION_CAPACITY, MONEY_PER_KWH) for s in stations])
    else:
        stations = StationInfoDataset([StationInfo(s, STATION_CAPACITY, MONEY_PER_KWH) for s in stations])
    return stations
def stationDistribution_detourCost_thread(G, cand_inds, candidates_eid, candidates_tup, trips_cov_nx,
                                          users, stations, stations_index):
    best_ci = -1; min_cost = np.inf;
    for ci in cand_inds:
        #if candidates_eid[ci] in stations: continue;
        cand_cost = 0.0
        redge_tuple = candidates_tup[ci]
        edge_id = candidates_eid[ci]
        # Calculate
        for vehID in users:
            trip_cov_nx = trips_cov_nx[vehID]
            insertIndex, cost = detourCost(G, vehID, trip_cov_nx, redge_tuple)
            cand_cost += cost
        # Update
        if best_ci == -1 or cost < min_cost:
            best_ci = ci; min_cost = cost;
        #print(f"{ci+1} / {len(candidates_eid)}")
    stations[stations_index] = best_ci
def stationDistribution_detourCost(G, candidates_eid, candidates_tup, trips_cov_nx,
                                   k, station_users):
    cand_inds = [i for i in range(len(candidates_eid))]
    #### For each group of users
    station_users_keys = sorted(station_users.keys())
    stations = [None] * k
    while any(s is None for s in stations):
        threads = []
        for i in range(len(station_users_keys)):
            if stations[i] is None:
                key = station_users_keys[i]
                users = station_users[key]
                #print(key, "|" + str(len(users)) + "|")
                #print("candidates:", cand_inds)
                if len(users) == 0:
                    # Choose random
                    best_ci = random.choice(cand_inds)
                    stations[i] = best_ci
                else:
                    #trips_cov_nx_copy = copy.deepcopy()
                    t = threading.Thread(target=stationDistribution_detourCost_thread,
                                         args=(G, cand_inds, candidates_eid, candidates_tup, trips_cov_nx,
                                               users, stations, i))
                    threads.append(t)
                    t.start()
        for t in threads:
            t.join();
        # Check if any repeating
        #print("->", stations)
        exist = set()
        #new_cand_inds = copy.copy(cand_inds)
        for i in range(len(stations)):
            if stations[i] in exist:
                stations[i] = None;
            elif stations[i] in cand_inds:
                cand_inds.remove(stations[i]);
            exist.add(stations[i])
    for i in range(len(stations)):
        stations[i] = candidates_eid[stations[i]]
    #print("---->", stations)
    stations = StationInfoDataset([StationInfo(s, STATION_CAPACITY, MONEY_PER_KWH) for s in stations])
    return stations

########## EUQILIBRIUM
def findEquilibrium(network_name, base_net, base_G, stations, base_trips, charge_data,
                    params, results, iteration=None, debug=False):
    trips = copy.deepcopy(base_trips)
    output_subfolder = "game1";
    if iteration != None: output_subfolder += "_" + str(iteration);
    return equilibriumGameRun(base_net, base_G, data_path, network_name,
                              trips, charge_data, stations, costFunction,
                              results, output_path=output_path, output_subfolder=output_subfolder,
                              add_stations_to_net=True, evaluate=True,
                              params=params, debug=debug)



LIMIT_CANDIDATES = False

###### MAIN
if __name__ == "__main__":
    # Parse arguments
    if len(sys.argv) < 2:
        network_name = "manhattan";
        args = {}
    else:
        network_name = sys.argv[1]
        args = parseArgs(sys.argv[2:])
    # Adjust params
    params = Parameters.config()
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
    ITERATIONS = params["training.iterations"]
    if "iterations" in args:
        ITERATIONS = int(args["iterations"])
        params["training.iterations"] = ITERATIONS
    params["training.agents"] = 1
    MONEY_PER_KWH = params["station.moneyPerKWh"]
    WAIT_QUEUE_SIZE = params["station.waitQueue"]
    QUEUE_PARKING = params["station.routing.waitParking"]
    print(params.groupPrint())
    # Inform about arg changes
    if "limit" in args:
        LIMIT_CANDIDATES = True
        print("INFO: Limiting candidates.")
    if "iterations" in args:
        print(f"INFO: Set ITERATIONS to {ITERATIONS} by received argument.")
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
    network_diameter = graphutil.diameter(base_G, weight="length")
    if MIN_DISTANCE < 0:
        MIN_DISTANCE = abs(MIN_DISTANCE * network_diameter)
    if MAX_DISTANCE < 0:
        MAX_DISTANCE = abs(MAX_DISTANCE * network_diameter)
    vTypes_tree = ET.parse("networks/vTypes.add.xml")
    EV_len = parkingNetGen.getVehicleLength(vTypes_tree);
    min_gap = prep.getMinGapFromAddTree(vTypes_tree)
        
###### PRE-RUN
    start_datetime_str = str(datetime.now().strftime('%Y%m%d_%H%M%S'))
    output_folder = network_name + "_game1_" + start_datetime_str
    output_path = output_path + "/" + output_folder
    pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
    pathlib.Path(output_path + "/training").mkdir(parents=True, exist_ok=True)
    output_path_full = str(MAIN_DIR) + "/" + output_path
    cache_data_path = output_path_full + "/_cache/"
    cache_output_path = cache_data_path + "/output/"
    pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
    pathlib.Path(cache_output_path).mkdir(parents=True, exist_ok=True)
    # Save params and metadata
    params.write(output_path + "/config.xml")
    xmlOut.writeMetadata(output_path + "/metadata.xml", network_name, start_datetime_str, "game",
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
                                destination_count_probs=DESTINATION_COUNT_DIST,
                                min_distance=MIN_DISTANCE,
                                max_distance=MAX_DISTANCE,
                                ev_pen=EV_PEN)
        # Generate charge data
        vTypes_tree = ET.parse("networks/vTypes.add.xml")
        max_charge = prep.getMaxChargeFromAddTree(vTypes_tree)
        charge_data = generateRandomChargeData(trips, max_charge)
    # Save used charge data
    writeChargeData(charge_data, output_path + "/charge_data.xml")
    ## Station distribution
    # Discretize graph and get candidates
    candidates = set()
    for edge in base_G.edges():
        candidates.add(edge)
    all_candidates = sorted(list(candidates))
    # Real edge candidates
    candidates_eid = []; candidates_tup = [];
    for i in range(len(all_candidates)):
        edge_tup = all_candidates[i]
        #from_node, to_node = graphutil.getNodesFromRoadID(dedge_id)
        edge_id = base_G.edges[edge_tup]["id"]#G_cov.nodes[dedge_id]["edge_id"]
        #edge_id = graphutil.translateDetailedRoad(dedge_id, as_tuple=False)
        candidates_eid.append(edge_id)
        redge_id = parkNetGen_getEdgeID(edge_id);
        redge_tuple = graphutil.getNodesFromRoadID(redge_id) #translator.IDToEdge(redge_id)
        candidates_tup.append(redge_tuple)
    # Create graph with all stations
    all_stations = []
    for edge_id in candidates_eid:
        all_stations.append(StationInfo(edge_id, STATION_CAPACITY, MONEY_PER_KWH))
    all_stations = StationInfoDataset(all_stations)
    _, _, stations_tree = parkingNetGen.addStationsToNetwork(base_net, all_stations, data_path,
                                                               write=True, output_path=cache_data_path,
                                                               network_filepath=data_path + "/base_net.net.xml",
                                                               vehicle_length=EV_len, min_gap=min_gap,
                                                               wait_queue_size=WAIT_QUEUE_SIZE,
                                                               wait_queue_parking=QUEUE_PARKING)
    parkingNetGen.removeStationLeftTurns_connXML(cache_data_path + "/net.net.xml",
                                                 cache_data_path + "/del_left_turns.con.xml",
                                                 all_stations,
                                                 delete=False)
    STOP_DISTANCE = parkingNetGen.calcStationStopDistance(WAIT_QUEUE_SIZE, EV_len, min_gap, QUEUE_PARKING)
    # Load modified net
    all_net = sumolib.net.readNet(cache_data_path + "/net.net.xml")
    G_all = graphing.netToGraph(cache_data_path + "/net.net.xml",
                                lengths=True, travel_time=True,
                                internal_lengths=True, node_position=True)
    #graphdraw.drawGraph(G_all)
    #import matplotlib.pyplot as plt
    #plt.show()
    ## Modify candidates
    if LIMIT_CANDIDATES:
        perm = np.random.permutation(len(candidates))[:10]
        candidates = [all_candidates[i] for i in perm]
        candidates_eid = [candidates_eid[i] for i in perm]
        candidates_tup = [candidates_tup[i] for i in perm]
    ## Update trips
    trips_cov_nx = copy.deepcopy(trips)
    trips_cov_nx = fixTripsForAllCandidatesGraph(base_net, G_all, trips_cov_nx)
    ## Create detour matrix
    # Map station (detailed edge) to index in candidates
    global sttn_cand_index, detour_matrix
    sttn_cand_index = {}
    for i in range(len(candidates_tup)):
        sttn_cand_index[candidates_tup[i]] = i
    # Matrix
    detour_matrix = np.full([VEHICLE_COUNT, len(candidates), 2], -1)
    ## Starting selection -> random
    stations = startingStationDistribution(candidates_eid, K, detailed=False)
    #print("-- starting stations:", stations.printEdges())
    # Prepare results
    results = Evaluation(translator)
    print("")

###### RUN
    pbar = tqdm(total=ITERATIONS)
    best = None; train_results = initializeResultsDict(params, ITERATIONS, K);
    loop_stime = time.perf_counter();
    for i in range(ITERATIONS):
        #print(stations.listEdges())
        # Find selection equilibrium and run evaluation
        chosen_station, congestion, results = findEquilibrium(network_name, base_net, base_G,
                                                                 stations, trips, charge_data,
                                                                 params, results, iteration=None, debug=False)
        updateResultsDict(train_results, stations, results, i)
        station_users = getStationUsers(chosen_station, stations)
        #print(f" >  {i+1:4d} equilibrium found")
        # Update best
        if best is None:
            best = copy.deepcopy(results);
        else:
            # Compare with best
            res_ds = EvaluationDataset([results, best])
            scores = res_ds.calcScores(params)
            #print(f" >  {i+1:4d}:", scores[0], " | best:", scores[1])
            if scores[0] > scores[1]:
                best = copy.deepcopy(results);
                #print("> best updated!")
        # Calculate new stations
        stations = stationDistribution_detourCost(G_all, candidates_eid, candidates_tup, trips_cov_nx,
                                                  K, station_users)
        #print(f" > {i+1:4d}: done, new stations:", stations.listEdges())
        pbar.update(1)
    pbar.close()
    loop_etime = time.perf_counter();
    time_diff = loop_etime - loop_stime
    

###### FINISH AND SAVE
    pathlib.Path(output_path + "/results").mkdir(parents=True, exist_ok=True)
    # Save loop results data
    xmlOut.saveTrainResults_numpy(train_results, output_path + "/results/data")
    xmlOut.saveTrainResults_XML(train_results, output_path + "/results/data_visualize.xml")
    xmlOut.saveTrainResults_csv(train_results, output_path + "/results/data")
    xmlOut.saveTotalDuration_txt(time_diff, output_path + "/results")
    # Write plot figures
    figs = visutil.plotTrainingResults_figs(train_results, ITERATIONS)
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
    # Clean up files
    if params["sim.deleteCache"]:
        xmlOut.cleanCache(output_path + "/_cache", network_name)
    # Print
    full_path = pathlib.Path(output_path + "/results/").resolve()
    print(f"Loop finished in {round(time_diff, 2)}, saved results inside\n'{full_path}'")
    # Show loop results
    plt.show()
    
