import sys
import os
import __main__
from subprocess import call, DEVNULL
import time
from datetime import datetime
import random
import math
import pathlib
import re
import copy
from enum import Enum
from collections import deque
import numpy as np
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt

import networkx as nx
import traci.constants as tc
import sumolib

sumoBinary = sumolib.checkBinary('sumo')
#import randomTrips
jtrrouterBinary = sumolib.checkBinary('jtrrouter')

import lib.graphing as graphing  #= lib/graphing/__init__.py
import preprocess as prep

import lib.visual_utility as visutil

import lib.sumo.utility as sumoutil
from lib.sumo.utility import StationRouting
import lib.traci_utility as traciutil

from lib.structs.stationinfo import StationInfo, StationInfoDataset
from lib.structs.trip import Trip, TripDataset
from lib.structs.trip_nx import TripNX, TripNXDataset
from lib.structs.evaluation import Evaluation
from lib.structs.params import Parameters
from lib.structs.graphtranslator import GraphTranslator

import lib.algorithms.algorithms as alg

import lib.graphing.utility as graphutil
import lib.graphing.draw as graphdraw

import lib.xml.parkingNetGen as parkingNetGen
import lib.xml.tripsGen as tripsGen
import lib.xml.output as xmlOut

from lib.sumo.assigned import sumoAssignedRun

MAIN_DIR = pathlib.Path(__main__.__file__).resolve().parent
os.chdir(MAIN_DIR)



def preprocess(base_G, data_path, network_name, output_path, trips, k, params=None):
    ## Folder organization
    output_path_full = str(MAIN_DIR) + "/" + output_path
    cache_data_path = output_path_full + "/_cache/"
    cache_output_path = cache_data_path + "/output/"
    pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
    pathlib.Path(cache_output_path).mkdir(parents=True, exist_ok=True)
    #### Pre-loop
    ## Preprocess sumo config
    # Copy
    prep.copyFile(data_path + "/" + network_name + ".sumocfg",
                  cache_data_path + "/" + network_name + ".sumocfg")
    sumo_filepath = cache_data_path + "/" + network_name + ".sumocfg"
    # Modify
    sumocfg_tree = ET.parse(sumo_filepath)
    sumocfg_tree = prep.config_enableStations(sumocfg_tree, enable=True)
    sumocfg_tree = xmlOut.config_enableStationOutput(sumocfg_tree, enable=True, aggregate=True)
    sumocfg_tree = xmlOut.config_enableBatteryOutput(sumocfg_tree, enable=False)
    sumocfg_tree.write(sumo_filepath)
    ## Copy requred files to run simulation
    prep.copyFile(data_path + "/base_net.net.xml", cache_data_path + "/base_net.net.xml")
    #prep.copyFile(output_path + "/trips.xml", cache_data_path + "/routes.xml")
    ## Load XMLs
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    vTypes_tree = ET.parse("networks/vTypes.add.xml", parser=parser)
    ## Update XML settings
    prep.enableBattery(vTypes_tree, True)
    prep.enableStationFinder(vTypes_tree, False)
    vTypes_tree.write(cache_data_path + "/vTypes.add.xml") # rewrite modified vTypes XML tree
    ## Side vars
    global network_diameter, EV_len, min_gap
    network_diameter = float(nx.diameter(base_G, weight="length"))
    EV_len = parkingNetGen.getVehicleLength(vTypes_tree);
    min_gap = prep.getMinGapFromAddTree(vTypes_tree)


####
def equilibriumGameRun(base_net, base_G, data_path, network_name,
                       trips : TripDataset, charge_data, stations, cost_function,
                       results, output_path, output_subfolder="equi",
                       agent_stations=None, prices=None, agent_colors=None, 
                       params=None, add_stations_to_net=True, evaluate=True,
                       debug=False, return_sim_data=False):
    if not params: params = Parameters.default();
    CPU_THREADS = params["sim.cpuThreads"]
    MAX_DURATION = params["sim.maxDuration"]
    DURATION_SET = MAX_DURATION > 0
    VISUALIZE = params["sim.visualize"]
    PRINT_RESULTS = params["sim.printResults"]
    BATTERY_EMPTY_THRESHOLD = params["electric.batteryEmptyThreshold"]
    WAIT_QUEUE_SIZE = params["station.waitQueue"]
    MONEY_PER_KWH = params["station.moneyPerKWh"]
    QUEUE_PARKING = params["station.routing.waitParking"]
    AGENT_COUNT = len(agent_stations) if agent_stations is not None else 1

#### PREPROCESS
    if AGENT_COUNT > 1:
        if agent_stations is None or len(agent_stations) == 1:
            AGENT_COUNT = 1;
        else:
            k = len(agent_stations[0]);
            K = len(stations)
            if agent_colors is None: agent_colors = visutil.getAgentColors();
            suffixes = [("_" + n) for n in agent_colors]
    else:
        k = len(stations)
    if params["prep.preprocess"]:
        preprocess(base_G, data_path, network_name, output_path, trips, k, params)
        params["prep.preprocess"] = False;
    output_path_full = str(MAIN_DIR) + "/" + output_path
    cache_data_path = output_path_full + "/_cache/"
    cache_output_path = cache_data_path + "/output/"
    sumo_filepath = cache_data_path + "/" + network_name + ".sumocfg"
    global network_diameter, EV_len, min_gap

#### STATION WRITE
    if add_stations_to_net:
        if AGENT_COUNT > 1:
            basenet_tree = ET.parse(cache_data_path + "/base_net.net.xml")
            nodes_tree, edges_tree, stations_tree = parkingNetGen.addStationsToNetwork(base_net, agent_stations[0],
                                                            cache_data_path, write=False, output_path=cache_data_path,
                                                            network_tree=basenet_tree,
                                                            #network_filepath=cache_data_path + "/base_net.net.xml",
                                                            vehicle_length=EV_len, min_gap=min_gap,
                                                            wait_queue_size=WAIT_QUEUE_SIZE,
                                                            wait_queue_parking=QUEUE_PARKING,
                                                            suffix=suffixes[0])
            #parkingNetGen.removeStationLeftTurns_netXML(cache_data_path + "/net.net.xml", agent_stations[0]);
            for a in range(1, AGENT_COUNT):
                _, _, stations_tree = parkingNetGen.appendStationsToNetwork(base_net, agent_stations[a],
                                                                            nodes_tree, edges_tree, stations_tree,
                                                                            output_path=cache_data_path, write=True,
                                                                            vehicle_length=EV_len, min_gap=min_gap,
                                                                            wait_queue_size=WAIT_QUEUE_SIZE,
                                                                            wait_queue_parking=QUEUE_PARKING,
                                                                            suffix=suffixes[a], reverse_angle=True);
            # DEBUG -> Show POIs for stations
            if VISUALIZE:
                for a in range(AGENT_COUNT):
                    parkingNetGen.addStationPOIs(cache_data_path + "/net.net.xml", cache_data_path + "/stations.add.xml",
                                                 agent_stations[a].listEdges(), suffix=suffixes[a])

        else:
            ## Write stations to XML
            parkingNetGen.addStationsToNetwork(base_net, stations, data_path,
                                               write=True, output_path=cache_data_path,
                                               network_filepath=cache_data_path + "/base_net.net.xml",
                                               vehicle_length=EV_len, min_gap=min_gap,
                                               wait_queue_size=WAIT_QUEUE_SIZE,
                                               wait_queue_parking=QUEUE_PARKING)
            parkingNetGen.removeStationLeftTurns_connXML(cache_data_path + "/net.net.xml",
                                                         cache_data_path + "/del_left_turns.con.xml",
                                                         stations,
                                                         delete=False)
        # Load modified net
        net = sumolib.net.readNet(cache_data_path + "/net.net.xml")
        G = graphing.netToGraph(cache_data_path + "/net.net.xml",
                                lengths=True, travel_time=True,
                                internal_lengths=True, node_position=True)
    else:
        #net = base_net
        G = base_G
    translator = GraphTranslator(G)
    #print(G)
    #graphdraw.drawGraph(G)
    #plt.show()
    
#### POST STATION WRITE
    if isinstance(trips, TripDataset):
        if add_stations_to_net:
            ## Fix stops
            trips = prep.fixTripEdges(base_net, net, stations.listEdges(),
                                      routes_filepath=output_path + "/trips.xml",
                                      write=True, output_filepath=cache_data_path + "/routes.xml",
                                      trips=trips)
        for trip in trips.values():
            for i in range(len(trip.destinations)):
                trip.destinations[i] = translator.IDToEdge(trip.destinations[i]);
        trips_nx = TripNXDataset.fromTripDataset(G, trips)
    elif isinstance(trips, TripNXDataset):
        if add_stations_to_net:
            raise Exception("Function called with intent to add stations to network, but TripNXDataset received instead of TripDataset.")
        trips_nx = trips
    
#### EQUILIBRIUM LOOP
    separate_congestion_update = False
    EVs = sorted(trips.EVs())
    chosen_station = {};
    congestion = {}
    trip_dict = copy.deepcopy(trips_nx.dict)
    history = deque(); check_back = 3;
    costs = {}
    for vehID in EVs: costs[vehID] = 0.0
    for st in stations:
        congestion[st.edge_id] = 0;
    for i in range(1000):
        #max_cost_delta = 0.0;
        #total_cost_delta = 0.0;
        #switches = 0
        update = {};
        ## Users select best station
        for vehID in EVs:
            cur_chosen = chosen_station.get(vehID, None)
            chosen, new_trip, cost = cost_function(G, vehID, trips_nx[vehID], stations, cur_chosen, congestion, translator,
                                                   return_cost=True);  # cost function
            #last_cost = costs[vehID]
            #cost_delta = cost - last_cost
            #if cost_delta > max_cost_delta:
            #    max_cost_delta = cost_delta
            #total_cost_delta += cost_delta
            #costs[vehID] = cost
            if (vehID not in chosen_station) or (chosen_station[vehID] != chosen):
                update[vehID] = (chosen, new_trip);
                if not separate_congestion_update:
                    if vehID in chosen_station:
                        congestion[chosen_station[vehID].edge_id] -= 1;
                    congestion[chosen.edge_id] += 1;
                #switches += 1
        ## Check if equilibrium
        if len(update) == 0: break;
        ## Update congestion
        for vehID in update:
            if separate_congestion_update:
                if vehID in chosen_station:
                    congestion[chosen_station[vehID].edge_id] -= 1;
                congestion[update[vehID][0].edge_id] += 1;
            chosen_station[vehID] = update[vehID][0];
            trip_dict[vehID] = update[vehID][1];
        ## Check if done
        h = hash(tuple(chosen_station.values()))
        #print(i, " [", h, "]")
        cycle = False;
        for j in range(len(history)):
            if int(h) == int(history[len(history)-j-1]):
                cycle = True; break;
        if cycle: break;
        history.append(h)
        if len(history) > check_back: history.popleft();
        #print(f"> |{switches:3d}|, {max_cost_delta}, {total_cost_delta}")
        ## Print state
        #print(f"\n---- Iteration {i}:");
        #print("congestion:")
        #for st in stations:
        #    print(f"  - {st.edge_id:10s}: {congestion[st.edge_id]}")
        #print("chosen stations:")
        #for vehID in chosen_station:
        #    print(f"  - {vehID:4s}: {chosen_station[vehID]}")
        #print("")
        
#### EVALUATION
    # Update trips
    chosen_trips = copy.deepcopy(trips_nx)
    for vehID in trip_dict:
        chosen_trips[vehID] = trip_dict[vehID]
    if evaluate:
        # Run evaluation
        for i in range(10):
            try:
                results = sumoAssignedRun(base_net, G, data_path, network_name, chosen_trips, stations, chosen_station,
                                          results, output_path, output_subfolder="assigned", charge_data=charge_data,
                                          agent_stations=agent_stations, prices=prices, agent_colors=agent_colors,
                                          params=params, add_stations_to_net=False, debug=False)
            except Exception as e:
                print(translator)
                raise e
                results = None
            if results is not None: break
        if results is None:
            raise Exception("Simulation failed to run 10 times in a row.")
    else:
        results = None
    # Print results
    #visutil.printResults_general(results, params)
    #visutil.printResults_trips(results)
    #visutil.printResults_solo(results);
    
    if return_sim_data:
        return chosen_station, congestion, results, (net, G, translator, trips_nx, chosen_trips)
    else:
        return chosen_station, congestion, results
    

