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
from enum import Enum
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

import lib.sumo.utility as sumoutil
from lib.sumo.utility import StationRouting
import lib.traci_utility as traciutil

from lib.structs.stationinfo import StationInfo, StationInfoDataset
from lib.structs.trip import Trip, TripDataset
from lib.structs.evaluation import Evaluation
from lib.structs.params import Parameters

import lib.algorithms.algorithms as alg
import lib.algorithms.coverage as coverAlg

import lib.graphing.utility as graphutil
import lib.graphing.draw as graphdraw

import lib.xml.parkingNetGen as parkingNetGen
import lib.xml.tripsGen as tripsGen
import lib.xml.output as xmlOut

MAIN_DIR = pathlib.Path(__main__.__file__).resolve().parent
os.chdir(MAIN_DIR)


## Recharge cost function
def stationCostFunction(detour_time, detour_distance, price, charge_amount=None):
    global TIME_COST_COEFF, DISTANCE_COST_COEFF 
    # No price because only one agent
    return (TIME_COST_COEFF * detour_time) +\
           (DISTANCE_COST_COEFF * detour_distance)

def preprocess(G, data_path, network_name, output_path, trips, k, params=None):
    if not params: params = Parameters.default();
    VISUALIZE = params["sim.visualize"]
    # Traci switch
    traciutil.initialize(not VISUALIZE)
    traci = traciutil.traci
    #output_path_full = str(MAIN_DIR) + "/" + output_path
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
    prep.enableStationFinder(vTypes_tree, CHARGE_ROUTING == 0)
    vTypes_tree.write(cache_data_path + "/vTypes.add.xml") # rewrite modified vTypes XML tree
    ## Side vars
    global network_diameter, EV_len, min_gap, max_charge, min_charge, min_charge_p
    network_diameter = graphutil.diameter(G, weight="length")
    EV_len = parkingNetGen.getVehicleLength(vTypes_tree);
    min_gap = prep.getMinGapFromAddTree(vTypes_tree)
    max_charge = prep.getMaxChargeFromAddTree(vTypes_tree)
    min_charge = prep.calcApproxChargeNeeded(network_diameter / k) + 200; # padding
    min_charge_p = min_charge / max_charge;
    # Trip len
    global avg_trip_len, avg_trip_charge;
    avg_trip_len = 0.0;
    for trip in trips.values():
        avg_trip_len += trip.total_distance
    avg_trip_len /= len(trips)
    avg_trip_charge = prep.calcApproxChargeNeeded(avg_trip_len);


####
def removeFromSimulationVars(vehicles : set, stations, params):
    global sim_EVs, CHARGE_ROUTING
    sim_EVs -= vehicles;
    if CHARGE_ROUTING != StationRouting.STATIONFINDER:
        global will_need_to_charge, going_to_charge, charging
        will_need_to_charge -= vehicles;
        for vehID in vehicles:
            going_to_charge.pop(vehID, None);
            if vehID in charging:
                si_index, park_side = charging[vehID][0]
                stations[si_index].releaseSpot(park_side)
                charging.pop(vehID, None);
#### Sumo
def sumoSoloRun(base_net, G, data_path, network_name, trips : TripDataset, stations, results,
                output_path, output_subfolder="solo", charge_data=None, coverage_G_d=None,
                params=None, debug=False):
    if not params: params = Parameters.default();
    CPU_THREADS = params["sim.cpuThreads"]
    MAX_DURATION = params["sim.maxDuration"]
    DURATION_SET = MAX_DURATION > 0
    VISUALIZE = params["sim.visualize"]
    PRINT_RESULTS = params["sim.printResults"]
    BATTERY_EMPTY_THRESHOLD = params["electric.batteryEmptyThreshold"]
    WAIT_QUEUE_SIZE = params["station.waitQueue"]
    MONEY_PER_KWH = params["station.moneyPerKWh"]
    # Charge routing enum
    global CHARGE_ROUTING
    if params["station.routing.useStationFinder"]: CHARGE_ROUTING = StationRouting.STATIONFINDER;
    else:
        if params["station.routing.centralized"]:
            CHARGE_ROUTING = StationRouting.CENTRALIZED;
        else:
            CHARGE_ROUTING = StationRouting.SELFISH;
    QUEUE_PARKING = params["station.routing.waitParking"]
    # Coeffs
    global TIME_COST_COEFF, DISTANCE_COST_COEFF
    TIME_COST_COEFF = params["station.routing.costFunction.timeCoefficient"]
    DISTANCE_COST_COEFF = params["station.routing.costFunction.distanceCoefficient"]
    # Traci switching
    if VISUALIZE: import traci;
    else: import libsumo as traci;
#### PREPROCESS
    k = len(stations)
    if params["saveLog"] or params["saveInputs"]:# or params["saveOutputs"]:
        output_path += "/" + output_subfolder
    if params["prep.preprocess"]:
        preprocess(G, data_path, network_name, output_path, trips, k, params)
    output_path_full = str(MAIN_DIR) + "/" + output_path
    cache_data_path = output_path_full + "/_cache/"
    cache_output_path = cache_data_path + "/output/"
    sumo_filepath = cache_data_path + "/" + network_name + ".sumocfg"
    global network_diameter, EV_len, min_gap, max_charge, min_charge, min_charge_p
    global avg_trip_len, avg_trip_charge
    
#### STATION WRITE
    ## Write stations to XML
    _, _, stations_tree = parkingNetGen.addStationsToNetwork(base_net, stations, data_path,
                                                               write=True, output_path=cache_data_path,
                                                               network_filepath=cache_data_path + "/base_net.net.xml",
                                                               vehicle_length=EV_len, min_gap=min_gap,
                                                               wait_queue_size=WAIT_QUEUE_SIZE,
                                                               wait_queue_parking=QUEUE_PARKING)
    #parkingNetGen.removeStationLeftTurns_netXML(cache_data_path + "/net.net.xml", stations);
    parkingNetGen.removeStationLeftTurns_connXML(cache_data_path + "/net.net.xml",
                                                 cache_data_path + "/del_left_turns.con.xml",
                                                 stations,
                                                 delete=False)
    STOP_DISTANCE = parkingNetGen.calcStationStopDistance(WAIT_QUEUE_SIZE, EV_len, min_gap, QUEUE_PARKING)
    SEARCH_REVERSE = params["station.fillReverse"]
    WAIT_QUEUE_COEFF = params["station.routing.waitQueueCoefficient"]
    # Load modified net
    net = sumolib.net.readNet(cache_data_path + "/net.net.xml")
    # Update station lane positions
    sttn_start_pos = parkingNetGen.updateStationsLanePos(net, stations_tree)
    stations_tree.write(cache_data_path + "/stations.add.xml")
    for si in stations:
        si.stop_distance = float(sttn_start_pos[si.getID()])
#### POST STATION WRITE
    # Induction loop
    xmlOut.config_createInductionLoopOutputFile(net.getEdges(), xml_filepath=cache_data_path + "/output.add.xml",
                                                relative_out_filepath=cache_output_path + "/loop.out.xml", overwrite=True)
    # Edge based macroscopic traffic measures
    xmlOut.config_createEdgeOutputFile(xml_filepath=cache_data_path + "/output.add.xml",
                                       relative_out_filepath=cache_output_path + "/edgeData.out.xml", overwrite=False)
    ## Fix stops
    trips = prep.fixTripEdges(base_net, net, stations.listEdges(),
                              routes_filepath=output_path + "/trips.xml",
                              write=True, output_filepath=cache_data_path + "/routes.xml",
                              trips=trips)
    ## Copy inputs
    if params["prep.saveInputs"]:
        prep.copyFile(cache_data_path + "/net.net.xml", output_path + "/net.net.xml")            # net
        prep.copyFile(cache_data_path + "/stations.add.xml", output_path + "/stations.add.xml")  # stations
    ## Command
    if params["saveLog"]: log_filepath = output_path_full + "/log.txt"
    else: log_filepath = None;
    cmnd = sumoutil.genSumoCommand(sumo_filepath, params["stepLength"], params["visualize"],
                                   threads=CPU_THREADS,
                                   log_filepath=log_filepath,
                                   trip_stats_folder=cache_output_path)
    if debug:
        print("-> SUMO command:\n'" + ' '.join(cmnd) + "'")
#### SIMULATION
    fully_completed = True;
    global sim_EVs
    sim_EVs = set(); manually_added_last_step = set();
    EVs_count = 0; total_veh_count = 0;
    set_need_to_charge_cnt = 0;
    sttn_util_rate = {}
    if CHARGE_ROUTING != StationRouting.STATIONFINDER:
        global will_need_to_charge, going_to_charge, charging
        will_need_to_charge = set()
        cooldown = {}
        going_to_charge = {}
        charging = {}
        ev_ntc_charge = {}
        charging_min = {}
        remaining_range = {}
    if VISUALIZE:
        veh_colors = {}
    for sttn_edge_id, _ in stations.listIDss():
        sttn_util_rate[sttn_edge_id] = [0, 0];
    ## Run simulation
    sim_stime = time.perf_counter();
    traci.start(cmnd);
    ## Subscriptions
    traci.simulation.subscribe([
            traci.constants.VAR_DEPARTED_VEHICLES_IDS,                          #
            traci.constants.VAR_ARRIVED_VEHICLES_IDS                            # getArrivedIDList()
            #traci.constants.VAR_TELEPORT_END
    ])
    for sttn_info in stations:
        park_id = sttn_info.park_id
        traciutil.subscribeParkingVehicleCount(park_id + "_0")
        traciutil.subscribeParkingVehicleCount(park_id + "_1")
    ########## Loop
    while traci.simulation.getMinExpectedNumber() > 0:
        # Check max duration
        if DURATION_SET:
            if traci.simulation.getTime() >= MAX_DURATION:
                fully_completed = False; break;
        # Step
        traci.simulationStep();
        data_sim = traci.simulation.getSubscriptionResults()

        #### Process state
        ## Arrived
        # -> remove arrived EVs
        arrived = set(data_sim.get(tc.VAR_ARRIVED_VEHICLES_IDS, []))
        removeFromSimulationVars(arrived, stations, params)

        #################### VEHICLE STEP
        if CHARGE_ROUTING != StationRouting.STATIONFINDER:
            start_charging_this_step = {};
            arrived_to_station_this_step = set();
        ## Check batteries and reroute to station if low
            vaporized = set()
            go_charge_this_step = {}
            for vehID in sim_EVs:
                cur_edge = traci.vehicle.getRoadID(vehID);
                if cur_edge and cur_edge[0] != ':':
                    charge = float(traci.vehicle.getParameter(vehID, "device.battery.chargeLevel"))
                    # Check if battery empty
                    if charge <= BATTERY_EMPTY_THRESHOLD:
                        traci.vehicle.remove(vehID, reason=3)
                        vaporized.add(vehID)
                    # Check if needs to search for a charging station
                    if (vehID in will_need_to_charge) and (charge < ev_ntc_charge[vehID]): # find charging station
                        # Check if already checked while on this edge
                        if vehID in cooldown and cooldown[vehID] == cur_edge: continue;
                        # Proceed
                        route = traci.vehicle.getRoute(vehID);
                        cur_index = traci.vehicle.getRouteIndex(vehID);
                        next_dest_index_r = traciutil.getNextDestIndexInRoute(vehID, trips[vehID], route, cur_index)
                        approx_charge_needed = traciutil.calcNeededChargeLeft(vehID, trips[vehID]) - charge
                        # Find a charging station to charge at
                        if CHARGE_ROUTING == StationRouting.SELFISH:
                            # Get best charging station and station trip
                            data = traciutil.findClosestChargingStation(vehID, charge,
                                                                        stations, stationCostFunction,
                                                                        approx_charge_needed=approx_charge_needed,
                                                                        route=route, cur_index=cur_index,
                                                                        next_dest_index=next_dest_index_r)
                        else:
                            # Get the first best station with free spots open; otherwise the one less filled up (linear function)
                            data = traciutil.findClosestChargingStation_centralized(vehID, charge,
                                                                        stations, stationCostFunction,
                                                                        approx_charge_needed=approx_charge_needed,
                                                                        wait_coef=WAIT_QUEUE_COEFF,
                                                                        route=route, cur_index=cur_index,
                                                                        next_dest_index=next_dest_index_r)
                        # If not found
                        if data[0] == None:
                            cooldown[vehID] = cur_edge
                            continue;
                        else:
                            if vehID in cooldown:
                                cooldown.pop(vehID);
                        target_sttn_id, station_trip, station_route = data
                        target_si_index = stations.getIndexByID(target_sttn_id)
                        target_si = stations[target_si_index]
                        # Update new route and trip
                        new_route = station_route + route[next_dest_index_r + 1:]
                        next_dest_index_t = traciutil.getNextDestIndexInTrip(vehID, trips[vehID], route, cur_index)
                        trips[vehID].insertToNextDestination(station_trip, next_dest_index_t)
                        traci.vehicle.setRoute(vehID, new_route)
                        # > Stop at the waiting queue parking
                        if QUEUE_PARKING:
                            traci.vehicle.setParkingAreaStop(vehID, target_si.wait_park_id)
                        # > Stop and wait in front of the charging spots; creates jam at the entrance if too many vehicles in queue
                        else:
                            # -> sometimes error happens because the vehicle is too close to the stop? (less than ~1 in 1000)
                            # even though the getStationDistance and backup STOP_DISTANCE should always prevent that...
                            try:
                                traci.vehicle.setStop(vehID, target_si.redge_id,
                                                      pos=parkingNetGen.getStationStopDistance(target_si, STOP_DISTANCE));
                            except Exception as e:
                                removeFromSimulationVars({vehID})
                                vaporized.add(vehID)
                                traci.vehicle.remove(vehID)
                                continue;
                        #target_si.addToWaiting(vehID); -> add when they reach the waiting spot
                        target_si.addIncoming(vehID);
                        # Update set
                        go_charge_this_step[vehID] = target_sttn_id
                        # Visualization
                        if VISUALIZE:
                            # Color by going to station or not
                            traciutil.colorByGoingToStation(vehID, True, veh_colors)
                #if VISUALIZE:
                    # Color by charge
                    #traciutil.colorByCharge(vehID, charge, veh_colors, max_charge)
            # Update sets and dicts
            will_need_to_charge -= go_charge_this_step.keys()
            going_to_charge.update(go_charge_this_step)
            removeFromSimulationVars(vaporized, stations, params) #sim_EVs -= vaporized
            #if len(vaporized) > 0: print("> Vaporized:", vaporized);

        ## Vehicles driving to charge stations
            for vehID in going_to_charge:
                target_sttn_id = going_to_charge[vehID]
                target_si_index = stations.getIndexByID(target_sttn_id)
                target_si = stations[target_si_index]
                # Check if vehicle entered the station lane, otherwise ignore it
                veh_edge_id = traci.vehicle.getRoadID(vehID)
                if veh_edge_id == target_si.redge_id:
                    target_si.removeIncoming(vehID);
                    target_parks = (target_si.park_id + "_0", target_si.park_id + "_1")
                    # Request a charging/parking spot
                    parking_spot_side = target_si.requestSpot(auto_take=True, search_reverse=SEARCH_REVERSE)
                    found_spot = (parking_spot_side != -1)
                    if found_spot:
                        traciutil.clearStops(vehID);
                        traci.vehicle.setParkingAreaStop(vehID, target_parks[parking_spot_side])
                        start_charging_this_step[vehID] = (target_si_index, parking_spot_side)
                    else:
                        target_si.addToWaiting(vehID);
                        arrived_to_station_this_step.add(vehID);
            # Update sets and dicts
            for vehID in arrived_to_station_this_step: going_to_charge.pop(vehID, None);                        

        ## Vehicles charging
            done_charging_this_step = set()
            for vehID in charging:
                if traci.vehicle.isStopped(vehID):
                    charge = float(traci.vehicle.getParameter(vehID, "device.battery.chargeLevel"))
                    charge_target = charging[vehID][1]
                    if charge >= charge_target and charge >= ev_ntc_charge[vehID]:
                        si_index, park_side = charging[vehID][0]
                        target_si = stations[si_index]
                        target_si.releaseSpot(park_side)
                        # Check if can make journey; if not keep monitoring it
                        approx_charge_needed = traciutil.calcNeededChargeLeft(vehID, trips[vehID])
                        if approx_charge_needed > charge:
                            will_need_to_charge.add(vehID)
                        traci.vehicle.resume(vehID)
                        done_charging_this_step.add(vehID)
                        if QUEUE_PARKING:
                            # Get next in line to charge
                            nextID = target_si.removeNextWaiting()
                        else:
                            # Get closest to station to charge
                            nextID = traciutil.getClosestWaitingToStation(target_si)
                        if nextID is not None:
                            target_parks = (target_si.park_id + "_0", target_si.park_id + "_1")
                            # Get the charging/parking spot
                            parking_spot_side = target_si.requestSpot(auto_take=True, search_reverse=params["station.fillReverse"])
                            found_spot = (parking_spot_side != -1)
                            if found_spot != -1:
                                if traci.vehicle.isStopped(nextID):
                                    traci.vehicle.setParkingAreaStop(nextID, target_parks[parking_spot_side])
                                    traci.vehicle.resume(nextID);
                                else:
                                    traciutil.clearStops(nextID)
                                    traci.vehicle.setParkingAreaStop(nextID, target_parks[parking_spot_side])
                                start_charging_this_step[nextID] = (si_index, parking_spot_side)
                                if not QUEUE_PARKING: target_si.wait_queue.remove(nextID);
                            else:
                                print("ERROR: Spot released but no spot found for the next vehicle, this shouldn't happen.")
                        if VISUALIZE:
                            # Color by going to station or not
                            traciutil.colorByGoingToStation(vehID, False, veh_colors)
            # Update dict (done charging)
            for vehID in done_charging_this_step:
                charging.pop(vehID, None)
            # Update dict (found spot/started charging)
            for vehID in start_charging_this_step:
                going_to_charge.pop(vehID, None)
                charge = float(traci.vehicle.getParameter(vehID, "device.battery.chargeLevel"))
                charge_target = min(max(traciutil.calcNeededChargeLeft(vehID, trips[vehID]), charge + charging_min[vehID]), max_charge)
                charging[vehID] = (start_charging_this_step[vehID], charge_target)

        ## Newly added
        departed = set(data_sim.get(tc.VAR_DEPARTED_VEHICLES_IDS, []))
        for vehID in departed:
            total_veh_count += 1;
            vtype = traci.vehicle.getTypeID(vehID)
            if vtype == "electric":
                sim_EVs.add(vehID); EVs_count += 1;
                # Set when vehicle needs to charge
                if charge_data is not None and vehID in charge_data:
                    need_to_charge_level, set_charge, charge_min = charge_data[vehID]
                    set_need_to_charge_cnt += 1
                else:
                    need_to_charge_level = random.uniform(0.15, 0.4)
                    # Set battery charge on start
                    #min_charge = prep.calcApproxChargeNeeded(dist_radius);
                    #min_charge_p = min_charge / max_charge;
                    trip_len = trips[vehID].total_distance
                    approx_charge_needed = prep.calcApproxChargeNeeded(trip_len)
                    if random.random() < params["electric.needToChargeProb"]:
                        # v1 : random.uniform(0.2, 0.3) * max_charge
                        # v0 : max(0.02, 0.1 + (random.gauss() * 0.03)) * max_charge;
                        # v2 : max(min_charge, random.uniform(0.4, 0.8) * approx_charge_needed)
                        set_charge = (need_to_charge_level * max_charge) + (approx_charge_needed * random.uniform(0.0, 1.0))
                        charge_min = random.uniform(250, 750)
                        set_need_to_charge_cnt += 1
                    else:
                        set_charge = max_charge
                if CHARGE_ROUTING != StationRouting.STATIONFINDER:
                    ev_ntc_charge[vehID] = float(need_to_charge_level * max_charge)
                    charging_min[vehID] = float(charge_min)
                    will_need_to_charge.add(vehID);
                else:
                    traci.vehicle.setParameter(vehID, "device.stationfinder.needToChargeLevel", str(need_to_charge_level))
                traci.vehicle.setParameter(vehID, "device.battery.chargeLevel", str(min(set_charge, max_charge)))
        ####################

        ## Keep tracking of station use per time
        for si in stations:
            sttn_veh_cnt = traciutil.getStepParkingVehicleCount(si.park_id + "_0")
            sttn_veh_cnt += traciutil.getStepParkingVehicleCount(si.park_id + "_1")
            sttn_util_rate[si.getID()][1] += sttn_veh_cnt;
            if sttn_veh_cnt > 0: sttn_util_rate[si.getID()][0] += 1;

                    
    ########## Simulation done
    sim_time = traci.simulation.getTime()
    traci.close()
    sim_etime = time.perf_counter()
    steps_processed = int(sim_time / params["stepLength"])
    exec_duration = sim_etime - sim_stime;
    if params["printResults"]:
        print("\n")
        print(f"-------- Simulation over at {sim_time} ({steps_processed} steps); after {exec_duration:0.2f} seconds" + (f"(max duration reached ({MAX_DURATION}))" if not fully_completed else ""))
        print(f"         vehicle count: {total_veh_count:6d}")
        print(f"             - electric: {EVs_count:6d} ({round((EVs_count / total_veh_count)*100, 2):4.2f} %; expected {round((params['electric.penetration'])*100, 2):4.2f} %)")
        print()

#### POSTPROCESS
    results.clear();
    results.setSimulationData(fully_completed, sim_time, exec_duration)
    ## Process step data
    # Utilization rate
    for si in stations:
        st_id = si.getID(); st_cap = si.total_capacity;
        sttn_util_rate[st_id] = (float(sttn_util_rate[st_id][0] / steps_processed),
                                 float(sttn_util_rate[st_id][1] / (steps_processed * st_cap)));

    ## Total charge from station
    if params["printResults"]:
        print("Total charge used per station | utlization rate:")
    stations_charges_data = xmlOut.getAllStationCharges(cache_data_path)
    station_charges = {}
    veh_charges = {}
    sttn_vehicle_count = {}
    total_charge = 0
    for si in stations:
        station_ids = si.getIDs()
        total = 0.0;
        sttn_vehicle_count[si.getID()] = 0
        for station_id in station_ids:
            if station_id in stations_charges_data:
                charges = stations_charges_data[station_id];
                sttn_vehicle_count[si.getID()] += len(charges)
                for vehID in charges.keys():
                    for charge in charges[vehID]:
                        total += float(charge["totalEnergy"])
                    if vehID not in veh_charges: veh_charges[vehID] = set();
                    veh_charges[vehID].add(si.getID())
        if params["printResults"]:
            print(f"  {si.edge_id:12s}: {round(total, 2):9.2f} | {sttn_vehicle_count[si.getID()]:4d}",
                  f"(util: {round(sttn_util_rate[si.getID()][0]*100.0,2):5.2f} %, {round(sttn_util_rate[si.getID()][1]*100.0,2):5.2f} %)")
        station_charges[si.getID()] = total
        EVs_charged = len(veh_charges.keys()); EVs_charged_ratio = EVs_charged / set_need_to_charge_cnt;
        total_charge += total
    money_earned = (total_charge * MONEY_PER_KWH) / 1000.0
    if params["printResults"]:
        print(f"  > total charge: {round(total_charge / 1000.0, 2)} KWh")
        print(f"  > money earned: {round(money_earned, 2)}€ ({round(MONEY_PER_KWH,2)}€ per KWh)")
        print()
    results.setStationData(stations, MONEY_PER_KWH, station_charges, sttn_util_rate, sttn_vehicle_count, total_charge, money_earned)

    ## Trip stats/info
    trip_stats = xmlOut.getTripStats(cache_output_path)
    results.setTripData(trip_stats)
    
    ## Get flow at edges
    edge_stats = xmlOut.getEdgeLoopStats(base_net,
                                         cache_output_path + "/loop.out.xml",
                                         max_flow=True)
    edge_data = xmlOut.getEdgeDataStats(cache_output_path + "/edgeData.out.xml")
    results.setEdgeData(edge_stats, edge_data)

    ## Get vaporized vehicles and edges where they vaporized
    vaporized_count = 0
    for data in edge_data.values():
        vap = data["vaporized"]
        if vap > 0: vaporized_count += vap
    arrived_EVs_cnt = EVs_count - vaporized_count
    arrived_EVs_ratio = float(arrived_EVs_cnt) / float(EVs_count)
    if params["printResults"]:
        print(f"Total vaporized: {vaporized_count}")
        print(f"--> Arrived EVs ratio: {round(arrived_EVs_ratio*100, 2):5.2f} % ({arrived_EVs_cnt} / {EVs_count}) [total: {total_veh_count}]")
        print(f"--> EVs charged ratio: {round(EVs_charged_ratio*100, 2):5.2f} % ({EVs_charged} / {set_need_to_charge_cnt})")
        print()
    results.setVehicleData(vehicle_count=total_veh_count,
                           EV_count=EVs_count, EV_set_charge=set_need_to_charge_cnt,
                           EV_arrived=arrived_EVs_cnt, EV_charged=EVs_charged)

    ## Get total coverage
    if coverage_G_d is None:
        coverage_G_d = graphing.netToDetailedGraph(data_path + "/base_net.net.xml", add_road_centers=True)
    coverage_radius = float(coverAlg.coverageRadiusBinarySearch(coverage_G_d, stations.listDNodes(base_net),
                                                                epsilon=50,
                                                                max_radius=network_diameter))
    results.setCoverageData(coverage_radius, network_diameter)

    return results
        
