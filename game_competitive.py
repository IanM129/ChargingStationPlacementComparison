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
from lib.utility import parseArgs, initializeResultsDict, updateResultsDict_comp
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
from lib.sumo.assigned import sumoAssignedRun

MAIN_DIR = pathlib.Path(__file__).resolve().parent
os.chdir(MAIN_DIR)



def fixTripsForAllCandidatesGraph(base_net, G_all, trips, all_stations=None):
    for vehID, trip in trips.dict.items():
        for i in range(len(trip.destinations)):
            edge_id = trip.destinations[i]
            edge = base_net.getEdge(edge_id)
            fnode = edge.getFromNode().getID()
            tnode = edge.getToNode().getID()
            road = graphutil.getRoadIDFromNodes(fnode, tnode);
            if all_stations is not None and edge_id not in all_stations:
                trip.destinations[i] = (fnode, tnode)
            else:
                trip.destinations[i] = ("pcsEntry_" + edge_id, tnode)
    trips_nx_cov = TripNXDataset.fromTripDataset(G_all, trips)
    return trips_nx_cov

def getStationUsers(chosen_station, stations):
    station_users = {}
    for si in stations:
        station_users[si.edge_id] = set()
    for vehID, si in chosen_station.items():
        if si.edge_id in station_users:
            station_users[si.edge_id].add(vehID);
    return station_users
def getAgentUsers(chosen_station, agent_stations):
    agent_users = []
    station_users = {}
    for vehID, si in chosen_station.items():
        if si.edge_id not in station_users:
            station_users[si.edge_id] = set()
        station_users[si.edge_id].add(vehID);
    for a in range(len(agent_stations)):
        sids = agent_stations[a]
        users = set()
        st_edges_set = set(sids.listEdges())
        for st_edge in st_edges_set:
            if st_edge in station_users:
                users.update(station_users[st_edge])
        agent_users.append(users)
    return agent_users

def runEvaluation(base_net, G, network_name, data_path, output_path,
                  chosen_trips, charge_data, stations, chosen_station,
                  agent_stations, prices, agent_colors,
                  results, params):
    for i in range(10):
        try:
            results = sumoAssignedRun(base_net, G, data_path, network_name, chosen_trips, stations, chosen_station,
                                      results, output_path, output_subfolder="assigned", charge_data=charge_data,
                                      agent_stations=agent_stations, prices=prices, agent_colors=agent_colors,
                                      params=params, add_stations_to_net=False, debug=False)
        except Exception as e:
            results = None
        if results is not None: break
    if results is None:
        raise Exception("Simulation failed to run 10 times in a row.")
    return results

########## COST
def detourCost(G, vehID, trip : TripNX, st_redge_tup : tuple, chosen_trip=None):
    st_redge_tup_nosuffix = (st_redge_tup[0], st_redge_tup[1].rsplit('_', 1)[0])
    if st_redge_tup_nosuffix[1] == "pcsEnd":
        st_redge_tup_nosuffix = st_redge_tup
    # Check if in matrix
    global sttn_cand_index, detour_matrix
    cand_index = sttn_cand_index[st_redge_tup_nosuffix]
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
    #congestion_empty = True
    #for key in congestion:
    #    if congestion[key] > 0:
    #        congestion_empty = False; break;
    # Coefficients
    congestion_c = 10.0; price_c = 0.2;
    # Return vars
    chosen_sttn = None; chosen_trip = None; min_cost = np.inf;
    ## Total detour cost for each station
    #if (not congestion_empty): print(f"\n\n------------ {vehID}:")
    for si in stations:
        #if (not congestion_empty): print("--->", si.edge_id, f"({si.redge_id})")
        redge_tuple = translator.IDToEdge(si.redge_id)
        # Calculate
        trip_st = None
        insertIndex, cost = detourCost(G, vehID, trip, redge_tuple, chosen_trip=trip_st)
        if insertIndex == -1: continue;
        #if (not congestion_empty): print(f"- detour cost: {cost}")
        # Add congestion
        cong = congestion[si.edge_id]
        if cur_chosen is None or si != cur_chosen: cong += 1;
        cost += cong * congestion_c
        #if (not congestion_empty): print(f"- congestion cost ({congestion[si.edge_id]}): {congestion[si.edge_id] * congestion_c}")
        # Add price
        distance = trip.getTotalDistance()
        cost += (si.price * distance) * price_c
        #if (not congestion_empty): print(f"- price cost ({si.price}€, {distance} kWh): {(si.price * distance) * price_c}")
        # Recreate trip if not set
        if (trip_st is None):
            trip_st = copy.deepcopy(trip)
            trip_st.insert(redge_tuple, insertIndex)
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
def startingStationDistribution(candidates, k, agent_count, prices, suffixes, detailed=True):
    cands = set(candidates)
    agent_stations = [None] * agent_count
    for a in range(agent_count):
        # Random for first distribution
        selection = alg.pickRandom(cands, k)
        cands -= set(selection)
        # StationInfo from detailed edges
        if detailed:
            agent_stations[a] = [StationInfo.fromDetailedEdge(s, STATION_CAPACITY, prices[a], suffix=suffixes[a]) for s in selection]
        else:
            agent_stations[a] = [StationInfo(s, STATION_CAPACITY, prices[a], suffix=suffixes[a]) for s in selection]
        agent_stations[a] = StationInfoDataset(agent_stations[a])
    return agent_stations
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
def stationDistribution_detourCost(G, candidates_eid, candidates_tup,
                                   trips_cov_nx, K, station_users):
    cand_inds = [i for i in range(len(candidates_eid))]
    #### For each group of users
    station_users_keys = sorted(station_users.keys())
    stations = [None] * K
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
    #stations = StationInfoDataset([StationInfo(s, STATION_CAPACITY) for s in stations])
    return stations

########## PRICE + PROFIT
def calculateProfit(station_users : dict, price : float, trips):
    charged = 0.0
    for users in station_users.values():
        for vehID in users:
            charged += trips[vehID].getTotalDistance()
    return (charged * price)
def calculateProfitPerAgent(agent_users : list[set], prices : list[float], trips):
    agent_profits = []
    for a in range(len(agent_users)):
        charged = 0.0
        for vehID in agent_users[a]:
            charged += trips[vehID].getTotalDistance()
        agent_profits.append(charged * prices[a])
    return agent_profits
def priceLocalSearch_thread(network_name, net, G,
                    agent_stations, stations, base_trips, charge_data, prices,
                    params, results,
                    new_price, new_chosen_station, index):
    #agent_stations = copy.deepcopy(agent_stations)
    #for i in range(len(agent_stations[a].arr)):
    #    agent_stations[a].arr[i].price = new_price
    stations = []
    for sds in agent_stations: stations.extend(sds.arr);
    stations = StationInfoDataset(stations)
    trips = copy.deepcopy(base_trips)
    output_subfolder = "game" + str(len(agent_stations));
    chosen, _, _ = equilibriumGameRun(net, G, data_path, network_name,
                                      trips, charge_data, stations, costFunction,
                                      results, output_path=output_path, output_subfolder=output_subfolder,
                                      agent_stations=agent_stations, prices=prices, agent_colors=agent_colors,
                                      params=params, add_stations_to_net=False, evaluate=False,
                                      debug=False, return_sim_data=False)
    new_chosen_station[index] = chosen
    return

########## EUQILIBRIUM
def findEquilibrium(network_name, net, G,
                    agent_stations, stations, base_trips, charge_data, prices,
                    params, results, iteration=None, evaluate=True, add_stations_to_net=True,
                    debug=False, return_sim_data=False):
    trips = copy.deepcopy(base_trips)
    output_subfolder = "game" + str(len(agent_stations));
    if iteration != None: output_subfolder += "_" + str(iteration);
    return equilibriumGameRun(net, G, data_path, network_name,
                              trips, charge_data, stations, costFunction,
                              results, output_path=output_path, output_subfolder=output_subfolder,
                              agent_stations=agent_stations, prices=prices, agent_colors=agent_colors,
                              params=params, add_stations_to_net=add_stations_to_net, evaluate=evaluate,
                              debug=debug, return_sim_data=return_sim_data)

LIMIT_CANDIDATES = False

agent_colors = visutil.getAgentColors()

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
    MIN_PRICE = params["training.minPrice"]
    MAX_PRICE = params["training.maxPrice"]
    AGENT_COUNT = params["training.agents"]
    if "agent-count" in args:
        AGENT_COUNT = int(args["agent-count"])
        params["training.agents"] = AGENT_COUNT
    PROGRESS_PRINT = params["training.printProgress"]
    WAIT_QUEUE_SIZE = params["station.waitQueue"]
    QUEUE_PARKING = params["station.routing.waitParking"]
    print(params.groupPrint())
    # Inform about arg changes
    if "limit" in args:
        LIMIT_CANDIDATES = True
        print("INFO: Limiting candidates.")
    if "iterations" in args:
        print(f"INFO: Set ITERATIONS to {ITERATIONS} by received argument.")
    if "agent-count" in args:
        print(f"INFO: Set AGENT_COUNT to {AGENT_COUNT} by received argument.")
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
                prices.append(float(params[param_name]))
                continue
        if PRINT_ERRORS:
            print(f"WARNING: Failed to fetch price for agent #{a} ('{agent_colors[a]}').")
        prices.append(base_price)
    print(f"INFO: Using starting prices: {prices} € per kWh.")

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
    vTypes_tree = ET.parse("networks/vTypes.add.xml")
    EV_len = parkingNetGen.getVehicleLength(vTypes_tree);
    min_gap = prep.getMinGapFromAddTree(vTypes_tree)
        
###### PRE-RUN
    start_datetime_str = str(datetime.now().strftime('%Y%m%d_%H%M%S'))
    output_folder = network_name + "_game" + str(AGENT_COUNT) + "_" + start_datetime_str
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
        all_stations.append(StationInfo(edge_id, STATION_CAPACITY, 0.0))
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
    ## Modify candidates
    if LIMIT_CANDIDATES:
        perm = np.random.permutation(len(candidates))[:10]
        candidates = [all_candidates[i] for i in perm]
        candidates_eid = [candidates_eid[i] for i in perm]
        candidates_tup = [candidates_tup[i] for i in perm]
    #graphdraw.drawGraph(G_all)
    #import matplotlib.pyplot as plt
    #plt.show()
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
    agent_stations = startingStationDistribution(candidates_eid, K, AGENT_COUNT, prices, suffixes, detailed=False)
    stations = []
    for i in range(len(agent_stations)):
        stations.extend(agent_stations[i].arr)
    stations = StationInfoDataset(stations)
    #print("-- starting stations:")
    #for a in range(AGENT_COUNT):
    #    print(f"  {agent_colors[a].capitalize():6s}: {agent_stations[a].listEdges()}")
    # Prepare results
    results = Evaluation(translator)
    print("")

###### RUN
    pbar = tqdm(total=ITERATIONS)
    best = None; train_results = initializeResultsDict(params, ITERATIONS, K, AGENT_COUNT);
    price_delta = []
    for a in range(AGENT_COUNT): price_delta.append(0.25);
    loop_stime = time.perf_counter();
    #### Main loop
    for iteration in range(ITERATIONS):
        #print(stations.listEdges())
        ## Find selection equilibrium and run evaluation
        chosen_station, congestion, _, sim_data = findEquilibrium(network_name, base_net, base_G,
                                                              agent_stations, stations,
                                                              trips, charge_data, prices,
                                                              params, results, iteration=None, debug=False,
                                                              evaluate=False,
                                                              return_sim_data=True)
        # Load modified net
        net, G, translator, trips_nx, chosen_trips = sim_data
        ## Local search price through equilibrium
        if PROGRESS_PRINT:
            print("\nStarting decisions:")
            for a in range(AGENT_COUNT):
                station_users_a = getStationUsers(chosen_station, agent_stations[a])
                start_profit = calculateProfit(station_users_a, prices[a], trips_nx)
                user_count = sum(len(v) for v in station_users_a.values())
                print(f"  {agent_colors[a].capitalize():6s} ({prices[a]} €): {user_count} | {round(start_profit/1000.0, 2)} €")
        # Multithreading loop
        opp_profits = [];
        og_chosen_station = chosen_station
        threads = []
        new_prices = []
        new_chosen_stations = []
        all_deltas = []
        agent_users = getAgentUsers(chosen_station, agent_stations)
        og_profits = calculateProfitPerAgent(agent_users, prices, trips_nx)
        for a in range(AGENT_COUNT):
            opp_profit = 0.0
            for p in range(len(og_profits)):
                if p != a: opp_profit += og_profits[p]
            opp_profits.append(opp_profit)
            profit_delta = og_profits[a] - opp_profit
            if PROGRESS_PRINT:
                print(f"-- {agent_colors[a].capitalize()}:")
                print(f"  normal profit ({prices[a]} €, |{len(agent_users[a])}|): " +
                      f"{round(og_profits[a]/1000.0, 2)} | {round(opp_profit/1000.0, 2)}" +
                      f" => {round(profit_delta/1000.0, 2)}")
            # Small -> medium -> large search
            # Define vars
            #PRICE_RANGE = MAX_PRICE - MIN_PRICE
            deltas =    [round(random.uniform(0.1, 0.15), 2),      # large
                         #round(random.uniform(0.1, 0.15), 2),     # medium
                         round(random.uniform(0.025, 0.075), 2)]      # small
            all_deltas.append(deltas)
            deltas_size = len(deltas)
            #print("deltas:", deltas)
            # Local search
            for di in range(len(deltas)):
                # (- delta) and (+ delta)
                for sign in [-1, 1]:
                    index = (a * deltas_size * 2) + (di * 2) + (1 if sign == 1 else 0)
                    delta = deltas[di]
                    new_price = round(min(max(prices[a] + (delta * sign), MIN_PRICE), MAX_PRICE), 2)
                    new_prices.append(new_price)
                    new_chosen_stations.append(None)
                    if new_price == og_profits[a]:
                        new_chosen_stations[index] = chosen_station
                        continue
                    agent_stations_a = copy.deepcopy(agent_stations)
                    for i in range(len(agent_stations[a].arr)):
                        agent_stations_a[a].arr[i].price = new_price
                    prices_a = copy.deepcopy(prices)
                    t = threading.Thread(target=priceLocalSearch_thread,
                                         args=(network_name, net, G,
                                               agent_stations_a, stations,
                                               trips_nx, charge_data, prices_a,
                                               params, results,
                                               new_price, new_chosen_stations, index))
                    threads.append(t)
        for t in threads: t.start();
        for t in threads: t.join();
        # Check resulting prices
        best_prices = []
        for a in range(AGENT_COUNT):
            if PROGRESS_PRINT: print(f"-- {agent_colors[a].capitalize()}:")
            #indeces = range(a * deltas_size * 2, ((a + 1) * deltas_size * 2) - 1)
            best_profit = (og_profits[a], opp_profits[a]);
            best_price = prices[a];
            for i in range(a * deltas_size * 2, (a + 1) * deltas_size * 2):
                new_price = new_prices[i]
                if new_price == best_price: continue;
                chosen_station = new_chosen_stations[i]
                agent_users = getAgentUsers(chosen_station, agent_stations)
                temp_prices = copy.copy(prices); temp_prices[a] = new_price;
                profits = calculateProfitPerAgent(agent_users, temp_prices, trips_nx)
                new_profit = profits[a]
                opp_profit = 0.0
                for p in range(len(profits)):
                    if p != a: opp_profit += profits[p];
                own_gain = new_profit - best_profit[0]
                opp_gain = opp_profit - best_profit[1]
                best_delta = best_profit[0] - best_profit[1]    # own advantage
                cur_delta = new_profit - opp_profit             # opp advantage
                if PROGRESS_PRINT:
                    print(f"  [{a}] new profit ({new_price} €, |{len(agent_users[a])}|): " +
                          f"{round(new_profit/1000.0, 2)} | {round(opp_profit/1000.0, 2)}" +
                          f" => {round(cur_delta/1000.0,2)}")
                #if new_profit > (best_profit[0] * random.uniform(0.9, 1.0)) and \
                #   opp_profit <= (best_profit[1] * random.uniform(0.5, 1.0)):
                #if cur_delta > (best_delta * random.uniform(0.9, 1.0)):
                if cur_delta > (best_delta * random.uniform(0.75, 0.9)) or\
                    (own_gain > 0.0 and own_gain > (opp_gain * random.uniform(0.9, 1.0))):
                    best_profit = (new_profit, opp_profit);
                    best_price = new_price;
            best_prices.append(best_price)
        prices = best_prices
        for a in range(AGENT_COUNT):
            for si in agent_stations[a]:
                si.price = prices[a];
        ## Run evaluation
        # Recreate stations
        stations = []
        for sds in agent_stations: stations.extend(sds.arr);
        stations = StationInfoDataset(stations)
        # Run equilibrium + evaluation
        chosen_station, congestion, _ = findEquilibrium(network_name, base_net, G,
                                                        agent_stations, stations,
                                                        trips_nx, charge_data, prices,
                                                        params, results,
                                                        add_stations_to_net=False,
                                                        iteration=None, debug=False)
        ## Gather users for each station
        station_users = getStationUsers(chosen_station, stations)
        if PROGRESS_PRINT:
            print("Final decisions:")
            for a in range(AGENT_COUNT):
                station_users_a = getStationUsers(chosen_station, agent_stations[a])
                final_profit = calculateProfit(station_users_a, prices[a], trips_nx)
                user_count = sum(len(v) for v in station_users_a.values())
                print(f"  {agent_colors[a].capitalize():6s} ({prices[a]:0.2f} €): {user_count} | {round(final_profit/1000.0, 2)} €")
        ## Bookkeeping
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
        updateResultsDict_comp(train_results, agent_stations, results, iteration)
        # Calculate new stations
        st_edges = stationDistribution_detourCost(G_all, candidates_eid, candidates_tup,
                                                  trips_cov_nx, K * AGENT_COUNT, station_users)
        agent_stations = []
        for a in range(AGENT_COUNT):
            agent_stations.append([])
            for k in range(K):
                agent_stations[a].append(StationInfo(st_edges[(K * a) + k], STATION_CAPACITY, prices[a], suffix=suffixes[a]))
            agent_stations[a] = StationInfoDataset(agent_stations[a])
        stations = []
        for ds in agent_stations: stations.extend(ds.arr);
        stations = StationInfoDataset(stations)
        if PROGRESS_PRINT:
            #print(f" > {iteration+1:4d}: done, new stations:", stations.listEdges())
            for a in range(AGENT_COUNT):
                print(f"  {agent_colors[a].capitalize():6s}: {agent_stations[a].listEdges()}")
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
    # Clean up files
    if params["sim.deleteCache"]:
        xmlOut.cleanCache(output_path + "/_cache", network_name)
    # Print
    full_path = pathlib.Path(output_path + "/results/").resolve()
    print(f"Loop finished in {round(time_diff, 2)}, saved results inside\n'{full_path}'")
    # Show loop results
    plt.show()
    
