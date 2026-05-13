import sys
import os
from subprocess import call, DEVNULL
import time
from datetime import datetime
import random
import math
import numpy as np
import sumolib
import traci
import traci.constants as tc
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import pathlib
import networkx as nx
import re

sumoBinary = sumolib.checkBinary('sumo')
import randomTrips
jtrrouterBinary = sumolib.checkBinary('jtrrouter')

#from lib.sumo.params import Parameters

import lib.graphing as graphing  #= lib/graphing/__init__.py
import preprocess as prep

import lib.sumo.utility as sumoutil
import lib.traci_utility as traciutil

from lib.structs.stationinfo import StationInfo, StationInfoDataset
from lib.structs.trip import Trip

import lib.algorithms.algorithms as alg

import lib.graphing.utility as graphutil
import lib.graphing.draw as graphdraw

import lib.xml.parkingNetGen as parkingNetGen
import lib.xml.tripsGen as tripsGen
import lib.xml.output as xmlOut


#### Vars
vehicles = set()

#### Parameters
## Preprocess
RECREATE_NETWORK = False
## Simulation
STEP_LENGTH = 0.1
VEHICLE_COUNT = 200
#VISUALIZE
FRAME_DUR = 0.01
#SIM_DURATION = 300
## Electric
EV_PEN = 0.8
NEED_TO_CHARGE_PROBABILITY = 1.0
BATTERY_EMPTY_THRESHOLD = 2.0
MANUAL_CHARGE_DECIDE = True
## Station
RANDOM_STATIONS = True
STATION_CAPACITY = 10
WAIT_QUEUE_SIZE = 10
STATION_FILL_REVERSE = False
MONEY_PER_KWH = 0.25  # (used euro)




#### Functions
## Station choice
def blankStationDistribution(G, G_d, k, random=False, debug=False):
    candidates = graphing.calcCandidates(G_d, detailed_graph=True)
    ## Charging stations
    print("-- Station distribution algorithm () started...")
    alg_stime = time.perf_counter()
    # Get station locations (edges)
    if random:
        # -> random
        stations_d = alg.pickRandom(candidates, 6)
        radius = 0
    else:
        # -> algorithm
        radius, stations_d = alg.radiusBinarySearch(G, G_d, candidates, k, epsilon=1,
                                                    distribution_alg=alg.farthestFirstCoverageBased, debug=debug)
    alg_etime = time.perf_counter()
    # Save plot output
    if not random:
        plt.clf()
        graphdraw.drawCenters(G_d, stations_d, radius, node_labels=False, edge_labels=False)
        plt.savefig(iter_output_path + "/distribution.jpg"); plt.clf();
    #
    print(f"-- Station distribution finished in {alg_etime - alg_stime:0.2f} seconds")
    return stations_d, radius
def statsStationDistribution(G, G_d, k, edge_val_weights, first_station, debug=False):
    candidates = graphing.calcCandidates(G_d, detailed_graph=True)
    print("-- Station distribution algorithm () started...")
    alg_stime = time.perf_counter()
    radius, stations_d = alg.radiusBinarySearch_EdgeWeights(G, G_d, candidates, k, edge_val_weights, first_station=first_station,
                                       epsilon=50, default_edge_weight=1, debug=debug)
    alg_etime = time.perf_counter()
    # Save plot output
    plt.clf()
    graphdraw.drawCenters(G_d, stations_d, radius, node_labels=False, edge_labels=False)
    plt.savefig(iter_output_path + "/distribution.jpg"); plt.clf()
    #
    print(f"-- Station distribution finished in {alg_etime - alg_stime:0.2f} seconds")
    #stations_edges = [graphutil.translateDetailedRoad(s, as_tuple=False) for s in stations_d]
    #print("Edges selected for stations:", stations_edges)
    return stations_d, radius
## Recharge cost function
def stationCostFunction(detour_time, detour_distance):
    return detour_time + detour_distance


####
def removeFromSimulationVars(vehicles : set):
    global sim_EVs, will_need_to_charge, going_to_charge, charging
    sim_EVs -= vehicles;
    if MANUAL_CHARGE_DECIDE:
        will_need_to_charge -= vehicles;
        for vehID in vehicles:
            going_to_charge.pop(vehID, None);
            if vehID in charging:
                si_index, park_side = charging[vehID][0]
                stations[si_index].releaseSpot(park_side)
                charging.pop(vehID, None);
#### MAIN
if __name__ == "__main__":
    prod = False

    if (prod):
        # Command line interface
        if (len(sys.argv) < 4):
            printUsage(); exit(0);
        filepath = ""
        if (isnumeric(sys.argv[1])):
            print("- Invalid <algorithm> value."); printUsage(); exit(0);
        algorithm = int(sys.argv[1])
        if (algorithm < 1 or algorithm > 7):
            print("- Invalid <algorithm> value."); printUsage(); exit(0);
        situation = sys.argv[2]
        visualize, duration = fetchOptionalParameters()
    else:
        algorithm = 2
        situation = "Manhattan"
        visualize = True
        #duration = 300

    sumo_binary = "sumo-gui" if visualize else "sumo"
    match (situation.lower()):
        case "manhattan":
            filepath = "manhattan/"; data_path = filepath + "data/"; in_data_path = data_path + "manhattan";
        case "zagreb":
            filepath = "Zagreb/"; data_path = filepath + "data/"; in_data_path = data_path + "zagreb";
        case _:
            print("- Invalid <situation> value."); printUsage(); exit(0);

    #### Settings
    LOOP = True
    iteration_count = 1
    k = 6

    if not LOOP: iteration_count = 1;

#### PREPROCESS
    ### Pre-loop
    ## Folder structure and file organization
    prep.outputFolder(data_path)
    # Datetime now (for file organization)
    start_datetime_str = str(datetime.now().strftime('%Y%m%d_%H%M%S'))
    if iteration_count > 0:
        output_path = data_path + "/output/" + start_datetime_str
        pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
    else: output_path = data_path;
    ## Network
    if RECREATE_NETWORK:
        prep.recreateNetwork(in_data_path + ".netgcfg", data_path + "/base_net.net.xml")
        print(f"-- Base network recreated. (at '" + (data_path + "/base_net.net.xml") + "')")
    base_net = sumolib.net.readNet(data_path + "/base_net.net.xml")
    G = graphing.netToGraph(data_path + "/base_net.net.xml")
    ## Preprocess sumo config
    sumocfg_tree = ET.parse(in_data_path + ".sumocfg")
    sumocfg_tree = prep.config_enableStations(sumocfg_tree, enable=True)
    sumocfg_tree = xmlOut.config_enableStationOutput(sumocfg_tree, enable=True, aggregate=True)
    sumocfg_tree = xmlOut.config_enableBatteryOutput(sumocfg_tree, enable=False)
    sumocfg_tree.write(in_data_path + ".sumocfg")
    #print("-- SUMO file output settings configured.")
    ## Load XMLs
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    vTypes_tree = ET.parse(data_path + "/vTypes.add.xml", parser=parser)
    ## Update XML settings
    prep.enableBattery(vTypes_tree, True)
    prep.enableStationFinder(vTypes_tree, not MANUAL_CHARGE_DECIDE)
    vTypes_tree.write(data_path + "/vTypes.add.xml") # rewrite modified vTypes XML tree
    ## Side vars
    network_diameter = float(nx.diameter(G, weight="length"))
    EV_len = parkingNetGen.getVehicleLength(vTypes_tree);
    min_gap = prep.getMinGapFromAddTree(vTypes_tree)
    max_charge = prep.getMaxChargeFromAddTree(vTypes_tree)
    min_charge = prep.calcApproxChargeNeeded(network_diameter / k) + 200; # padding
    min_charge_p = min_charge / max_charge;
    ## Routes and vehicle micromanagement
    trips = tripsGen.main(base_net, G, VEHICLE_COUNT, output_path + "/trips.xml",
                          destination_count_probs=[0, 0, 0, 0.3, 0.5, 0.2],  #4 -> 0.3; 5 -> 0.5 -> 6 -> 0.2
                          #min_distance_per_des=(network_diameter / 4.0),
                          min_distance=network_diameter*2.0,
                          max_distance=network_diameter*4.0,
                          ev_pen=EV_PEN)
    avg_trip_len = 0
    for trip in trips.values():
        avg_trip_len += trip.total_distance
    avg_trip_len /= len(trips)
    avg_trip_charge = prep.calcApproxChargeNeeded(avg_trip_len);
    print("-- generated random vehicles and trips.")
    print(f"     > trip average distance: {avg_trip_len:8.2f} -> ~{avg_trip_charge:6.1f} Wh ({avg_trip_charge / max_charge:4.2f}) charge")

#### LOOP
    for i in range(iteration_count):
        print(f"---------- Iteration {i+1:3d}:");
        #### Process
        ## Folder organization
        if iteration_count > 0:
            iter_output_path = data_path + "output/" + start_datetime_str + "/" + str(i+1)
            pathlib.Path(iter_output_path).mkdir(parents=True, exist_ok=True)
        else: iter_output_path = output_path;
        ## Reload graphs
        G = graphing.netToGraph(data_path + "/base_net.net.xml")
        G_d = graphing.netToDetailedGraph(data_path + "/base_net.net.xml")
        ## Station distribution (_d -> detailed, un-discretized; _edges -> normal graph; _edges_d -> detailed, discretized (=actual in graph))
        if i == 0:
            stations_d, dist_radius = blankStationDistribution(G, G_d, k, random=True)
            if dist_radius == 0: dist_radius = network_diameter / 2.0;
        else:
            stations_d, dist_radius = statsStationDistribution(G, G_d, k, edge_val_weights, first_station_d)
        #min_charge = prep.calcApproxChargeNeeded(dist_radius); min_charge_p = min_charge / max_charge;
        # Station info from detailed edges
        stations = StationInfoDataset([StationInfo.fromDetailedEdge(s, STATION_CAPACITY) for s in stations_d])
        ## Write stations to XML
        parkingNetGen.addStationsToNetwork(base_net, stations,
                                           data_path, out_data_path=iter_output_path, write=True,
                                           network_filepath=data_path + "/base_net.net.xml",
                                           vehicle_length=EV_len, min_gap=min_gap, wait_queue_size=WAIT_QUEUE_SIZE)
        print("-- stations written to network XML. (at '" + (iter_output_path + "/net.net.xml") + "')")
        # Reload net
        net = sumolib.net.readNet(iter_output_path + "/net.net.xml")
        ## Preprocess output config (post station generation)
        # Induction loop
        xmlOut.config_createInductionLoopOutputFile(net.getEdges(), xml_filepath=data_path + "/output.add.xml",
                                                    output_filepath="output/" + start_datetime_str + "/" + str(i+1) + "/loop.out.xml",
                                                    overwrite=True)
        # Edge based macroscopic traffic measures
        xmlOut.config_createEdgeOutputFile(xml_filepath=data_path + "/output.add.xml",
                                           output_filepath="output/" + start_datetime_str + "/" + str(i+1) + "/edgeData.out.xml",
                                           overwrite=False)
        ## Fix stops
        trips = prep.fixTripEdges(base_net, net, stations.listEdges(),
                                  output_filepath=iter_output_path + "/trips.xml",
                                  trips=trips)
        prep.copyFileForSimulation(iter_output_path + "/trips.xml", data_path + "/routes.xml")
        ## Copy requred files to run simulation
        prep.copyFileForSimulation(iter_output_path + "/net.net.xml", data_path + "/net.net.xml")
        prep.copyFileForSimulation(iter_output_path + "/stations.add.xml", data_path + "/stations.add.xml")
        ## Command
        log_filepath = iter_output_path + "/log.txt"
        cmnd = sumoutil.genSumoCommand(in_data_path + ".sumocfg", STEP_LENGTH, visualize, log_filepath)
        print("-> SUMO command:\n'" + ' '.join(cmnd) + "'")
        
#### SIMULATION
        sim_EVs = set(); manually_added_last_step = set();
        EVs_count = 0; total_veh_count = 0;
        set_need_to_charge_cnt = 0;
        sttn_util_rate = {}
        if MANUAL_CHARGE_DECIDE:
            will_need_to_charge = set()
            going_to_charge = {}
            charging = {}
            ev_ntc_charge = {}
            remaining_range = {}
        if visualize:
            veh_colors = {}
        for sttn_edge_id, _ in stations.listIDss():
            sttn_util_rate[sttn_edge_id] = [0, 0];
        ## Run simulation
        sim_stime = time.perf_counter()
        print(f"-- Simulation started ({i + 1:3d} / {iteration_count:3d})...")
        traci.start(cmnd)
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
        ## Loop
        while traci.simulation.getMinExpectedNumber() > 0: #and traci.simulation.getTime() < duration:
            # Step
            traci.simulationStep();
            data_sim = traci.simulation.getSubscriptionResults()

            #### Process state
            ## Arrived
            # -> remove arrived EVs
            arrived = set(data_sim.get(tc.VAR_ARRIVED_VEHICLES_IDS, []))            #set(traci.simulation.getArrivedIDList())
            removeFromSimulationVars(arrived)

            ## STEP
            if MANUAL_CHARGE_DECIDE:
                vaporized = set()
                go_charge_this_step = {}
                for vehID in sim_EVs:
                    cur_edge = traci.vehicle.getRoadID(vehID);
                    if cur_edge and cur_edge[0] != ':':
                        charge = float(traci.vehicle.getParameter(vehID, "device.battery.chargeLevel"))
                        if MANUAL_CHARGE_DECIDE:
                            # Check if battery empty
                            if charge <= BATTERY_EMPTY_THRESHOLD:
                                traci.vehicle.remove(vehID, reason=3)
                                vaporized.add(vehID)
                            # Check if needs to search for a charging station
                            if (vehID in will_need_to_charge) and (charge < ev_ntc_charge[vehID]): # find charging station
                                route = traci.vehicle.getRoute(vehID);
                                cur_index = traci.vehicle.getRouteIndex(vehID);
                                next_dest_index_r = traciutil.getNextDestIndexInRoute(vehID, trips[vehID], route, cur_index)
                                # Get charging station and station trip
                                target_station, station_trip, station_route =\
                                                traciutil.findClosestChargingStation(vehID, charge, stations, stationCostFunction,
                                                                                     route=route, cur_index=cur_index,
                                                                                     next_dest_index=next_dest_index_r)
                                # Update new route and trip
                                new_route = station_route + route[next_dest_index_r + 1:]
                                #trips[vehID].update(station_trip, index=cur_index)
                                next_dest_index_t = traciutil.getNextDestIndexInTrip(vehID, trips[vehID], route, cur_index)
                                trips[vehID].insertToNextDestination(station_trip, next_dest_index_t)
                                # Set stop
                                target_si = stations.getByID(target_station)
                                traci.vehicle.setRoute(vehID, new_route)
                                traci.vehicle.setStop(vehID, target_si.redge_id, pos=parkingNetGen.calcVehicleQueueLength(EV_len, min_gap, WAIT_QUEUE_SIZE));
                                # Update set
                                go_charge_this_step[vehID] = target_station
                    if visualize:
                        # Color by charge
                        traciutil.colorByCharge(vehID, charge, veh_colors, max_charge)
                # Update sets and dicts
                will_need_to_charge -= go_charge_this_step.keys()
                going_to_charge.update(go_charge_this_step)
                removeFromSimulationVars(vaporized) #sim_EVs -= vaporized
                #if len(vaporized) > 0: print("> Vaporized:", vaporized);

            ## Vehicles driving to charge stations
                start_charging_this_step = {};
                for vehID in going_to_charge:
                    if traci.vehicle.isStopped(vehID):
                        target_station = going_to_charge[vehID]
                        target_si_index = stations.getIndexByID(target_station)
                        target_si = stations[target_si_index]
                        target_parks = (target_si.park_id + "_0", target_si.park_id + "_1")
                        # Request a charging/parking spot
                        parking_spot_side = target_si.requestSpot(auto_take=True, search_reverse=STATION_FILL_REVERSE)
                        found_spot = (parking_spot_side != -1)
                        if found_spot:
                            traci.vehicle.setParkingAreaStop(vehID, target_parks[parking_spot_side])
                            traci.vehicle.resume(vehID)
                            start_charging_this_step[vehID] = (target_si_index, parking_spot_side)
                        # else keep waiting
            ## Vehicles charging
                done_charging_this_step = set()
                for vehID in charging:
                    if traci.vehicle.isStopped(vehID):
                        charge = float(traci.vehicle.getParameter(vehID, "device.battery.chargeLevel"))
                        charge_target = charging[vehID][1]
                        if charge >= charge_target and charge >= ev_ntc_charge[vehID]:
                            si_index, park_side = charging[vehID][0]
                            stations[si_index].releaseSpot(park_side)
                            # Check if can make journey; if not keep monitoring it
                            approx_charge_needed = traciutil.calcNeededChargeLeft(vehID, trips[vehID])
                            # DISTANCE
                            route = traci.vehicle.getRoute(vehID)
                            cur_index = traci.vehicle.getRouteIndex(vehID)
                            cur_edge = route[cur_index]
                            next_dest_index = traciutil.getNextDestIndexInTrip(vehID, trips[vehID], route=route, cur_index=cur_index)
                            distance = trips[vehID].remainingDistanceFromEdge(cur_edge, next_dest_index)
                            #
                            #print("Recharged:", charge, "/", charge_target, "(approx needed: " + str(approx_charge_needed) + ", " +\
                            #      "total consumed: " + str(float(traci.vehicle.getParameter(vehID, "device.battery.totalEnergyConsumed"))))
                            #print("    route:", traci.vehicle.getRoute(vehID))
                            #print("    trip end:", trips[vehID][-1])
                            #print("    distance left:", "~" + str(distance), "/", trips[vehID].total_distance, " (passed:", traci.vehicle.getDistance(vehID), ")")
                            #print("    current:", traci.vehicle.getRoadID(vehID), "(index: " + str(traci.vehicle.getRouteIndex(vehID)) + ")")
                            #print()
                            if approx_charge_needed > charge:
                                will_need_to_charge.add(vehID)
                            traci.vehicle.resume(vehID)
                            done_charging_this_step.add(vehID)
                # Update dict (done charging)
                for vehID in done_charging_this_step:
                    charging.pop(vehID, None)
                # Update dict (found spot/started charging)
                for vehID in start_charging_this_step:
                    going_to_charge.pop(vehID, None)
                    charge_target = min(traciutil.calcNeededChargeLeft(vehID, trips[vehID]) + 500, max_charge) # padding so it doesn't need to go recharge
                    charging[vehID] = (start_charging_this_step[vehID], charge_target)


            ######################
            ## Newly added
            departed = set(data_sim.get(tc.VAR_DEPARTED_VEHICLES_IDS, []))          #set(traci.simulation.getDepartedIDList());
            for vehID in departed:
                total_veh_count += 1;
                vtype = traci.vehicle.getTypeID(vehID)
                if vtype == "electric":
                    sim_EVs.add(vehID); EVs_count += 1;
                    # Set when vehicle needs to charge
                    need_to_charge_level = random.uniform(0.15, 0.4)
                    if MANUAL_CHARGE_DECIDE:
                        ev_ntc_charge[vehID] = float(need_to_charge_level * max_charge)
                    else:
                        traci.vehicle.setParameter(vehID, "device.stationfinder.needToChargeLevel", str(need_to_charge_level))
                    # Set battery charge on start
                    #min_charge = prep.calcApproxChargeNeeded(dist_radius); min_charge_p = min_charge / max_charge;
                    trip_len = trips[vehID].total_distance
                    approx_charge_needed = prep.calcApproxChargeNeeded(trip_len)
                    if random.random() < NEED_TO_CHARGE_PROBABILITY:
                        # v1 : random.uniform(0.2, 0.3) * max_charge
                        # v0 : max(0.02, 0.1 + (random.gauss() * 0.03)) * max_charge;
                        # v2 : max(min_charge, random.uniform(0.4, 0.8) * approx_charge_needed)
                        set_charge = (need_to_charge_level * max_charge) + (approx_charge_needed * random.uniform(0.0, 1.0))
                        set_charge_p = set_charge / max_charge
                        set_need_to_charge_cnt += 1
                    else:
                        set_charge = max_charge
                    traci.vehicle.setParameter(vehID, "device.battery.chargeLevel", str(min(set_charge, max_charge)))
                    if MANUAL_CHARGE_DECIDE:
                        will_need_to_charge.add(vehID)


            ## Keep tracking of station use per time
            for si in stations:
                #traci.chargingstation.getVehicleCount(st_id) #traci.parkingarea.getVehicleCount(si.park_id + "_0")
                sttn_veh_cnt = traciutil.getStepParkingVehicleCount(si.park_id + "_0")
                #traci.chargingstation.getVehicleCount(st_id_r) #traci.parkingarea.getVehicleCount(si.park_id + "_1")
                sttn_veh_cnt += traciutil.getStepParkingVehicleCount(si.park_id + "_1")
                sttn_util_rate[si.getID()][1] += sttn_veh_cnt;
                if sttn_veh_cnt > 0: sttn_util_rate[si.getID()][0] += 1;
                        

        ## Simulation done
        sim_time = traci.simulation.getTime()
        traci.close()
        sim_etime = time.perf_counter()
        steps_processed = int(sim_time / STEP_LENGTH)
        print("\n")
        print(f"-------- Simulation over at {sim_time} ({steps_processed} steps); after {sim_etime - sim_stime:0.2f} seconds")
        print(f"         vehicle count: {total_veh_count:6d}")
        print(f"             - electric: {EVs_count:6d} ({round((EVs_count / total_veh_count)*100, 2):4.2f} % | expected: {round(EV_PEN*100, 2)} %)")
        print(f"                 - set to charge: {set_need_to_charge_cnt} ({round((set_need_to_charge_cnt / EVs_count)*100, 2):4.2f} % | expected: {round(NEED_TO_CHARGE_PROBABILITY*100, 2)} %)")
        print()

#### POSTPROCESS
        ## Process step data
        # Utilization rate
        for si in stations:
            st_id = si.getID(); st_cap = si.total_capacity; 
            sttn_util_rate[st_id] = (float(sttn_util_rate[st_id][0] / steps_processed),
                                     float(sttn_util_rate[st_id][1] / (steps_processed * st_cap)));
        
        ## Total charge from station
        print("Total charge used per station | utlization rate:")
        stations_charges_data = xmlOut.getAllStationCharges(data_path)
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
            print(f"  {si.edge_id:12s}: {round(total, 2):9.2f} | {sttn_vehicle_count[si.getID()]:4d}",
                  f"(util: {round(sttn_util_rate[si.getID()][0]*100.0,2):5.2f} %, {round(sttn_util_rate[si.getID()][1]*100.0,2):5.2f} %)")
            station_charges[si.getID()] = total
            EVs_charged = len(veh_charges.keys()); EVs_charged_ratio = EVs_charged / set_need_to_charge_cnt;
            total_charge += total
        money_earned = (total_charge * float(MONEY_PER_KWH)) / 1000.0
        print(f"  > total charge: {round(total_charge / 1000.0, 2)} KWh")
        print(f"  > money earned: {round(money_earned, 2)}€ ({round(MONEY_PER_KWH,2)}€ per KWh)")
        print()
        
        ## Get broken down (empty battery) cars (!uses debug, don't use!)
        # WARNING: This uses the debug logs so isn't consistent between different SUMO versions,
        # but is most performance optimal (instead of polling every simulation step)
        if False:
            bd_warnings = xmlOut.getBreakdownWarnings(log_filepath)
            bdw_perlane = xmlOut.getBreakdownsPerEdge(bd_warnings)
            breakdown_count = 0
            if len(bdw_perlane) == 0: print("No break down warnings.");
            else:
                print(f"Break down warnings per lane [{len(bd_warnings)}]:")
                for edge, count in bdw_perlane.items():
                    print(f"- {edge}: {count}")
                    breakdown_count += count;
            arrived_EVs_cnt = EVs_count - breakdown_count
            arrived_EVs_ratio = float(arrived_EVs_cnt) / float(EVs_count)
            print(f"--> Arrived EVs ratio: {round(arrived_EVs_ratio*100, 2)} % ({arrived_EVs_cnt} / {EVs_count}) [total: {total_veh_count}]")
            print()
        ## Get battery depletion warnings (!uses debug, don't use!)
        if False:
            bd_warnings = xmlOut.getBatteryDepletionWarnings(log_filepath)
            if len(bd_warnings) == 0: print("No battery depletion warnings.");
            else:
                print(f"Battery depletion warnings [{len(bd_warnings)}]:")
                for warning in bd_warnings:
                    vehID, time = warning
                    print(f"- {time}: {vehID}")
            print()
            
        ## Get flow at edges
        edge_stats = xmlOut.getEdgeLoopStats(data_path, file_path="output/" + start_datetime_str + "/" + str(i+1) + "/loop.out.xml",
                                             max_flow=True)
        edge_data = xmlOut.getEdgeDataStats(data_path, file_path="output/" + start_datetime_str + "/" + str(i+1) + "/edgeData.out.xml")
        #print(edge_data)

        ## Get vaporized vehicles and edges where they vaporized
        vaporized_count = 0
        #vaporized_per_lane = {}
        #print(f"Vaporized per lane:")
        for data in edge_data.values():
            vap = data["vaporized"]
            #vaporized_per_lane[edge] = vap
            if vap > 0:
                #print(f"- {edge}: {vap}")
                vaporized_count += vap
        print(f"Total vaporized: {vaporized_count}")
        arrived_EVs_cnt = EVs_count - vaporized_count
        arrived_EVs_ratio = float(arrived_EVs_cnt) / float(EVs_count)
        print(f"--> Arrived EVs ratio: {round(arrived_EVs_ratio*100, 2):5.2f} % ({arrived_EVs_cnt} / {EVs_count}) [total: {total_veh_count}]")
        print(f"--> EVs charged ratio: {round(EVs_charged_ratio*100, 2):5.2f} % ({EVs_charged} / {set_need_to_charge_cnt})")
        print()
        
        
        #### Rerun algorithm with new edge weigths
        net = sumolib.net.readNet(data_path + "/base_net.net.xml")
        ## Get best station
        best_station = max(station_charges, key=station_charges.get)
        best_station_info = stations.getByID(best_station)
        best_station_d = graphutil.translateNetEdgeToDetailedEdgeID(net.getEdge(best_station_info.edge_id))
        print(f"-> best station: {best_station} ({best_station_d})")
        first_station_d = best_station_d
        ## Calculate weights
        edge_val_weights = {}
        # Get max entered
        # Filter to ignore station edges
        max_entered = 0
        for edge in edge_data:
            edge_n, edge_type = graphutil.extractEdgeID(edge)
            edge_data[edge]["edge_n"] = edge_n; edge_data[edge]["edge_type"] = edge_type;
            if edge_type == 0:
                entered = edge_data[edge]["entered"]
                if entered > max_entered: max_entered = entered;
        for edge, data in edge_data.items():
            if data["edge_type"] == 0:
                edge_d = graphutil.translateNetEdgeToDetailedEdgeTuple(net.getEdge(data["edge_n"]))
                if edge_d not in edge_val_weights: edge_val_weights[edge_d] = 1;
                # Improve by number of vehicles (num / max)
                entered = data["entered"]
                edge_val_weights[edge_d] += (entered / max_entered)
                # Improve by amount of broken down (vaporized) cars
                vap = data["vaporized"]
                if vap > 0:
                    if edge_d in edge_val_weights: edge_val_weights[edge_d] += vap;
                    else: edge_val_weights[edge_d] = 1 + vap;
        print(f"Updated edge value weights:")
        print(edge_val_weights)
        print()
        # Save visualization of edge weights
        plt.clf()
        graphdraw.drawNodes(G_d, stations_d, node_size=100)
        G_d = graphing.netToDetailedGraph(data_path + "/base_net.net.xml")
        graphdraw.drawEdgeWeights(G_d, edge_val_weights)
        plt.savefig(iter_output_path + "/edge_weights.jpg")
    






"""
# Improve by flow at the edge
        max_entered = max(edge_data.values(), key=lambda x: x["entered"])
        print(max_entered)
        for edge in edge_stats:
            if edge[0] != '_':
                edge_d = graphutil.translateNetEdgeToDetailedEdgeTuple(net.getEdge(edge))
                if edge_d not in edge_val_weights: edge_val_weights[edge_d] = 1;
                flow = edge_stats[edge]["flow"]
                edge_val_weights[edge_d] += (flow / max_flow)
        # Improve by amount of cars broken down at the edge
        for edge, count in bdw_perlane.items():
            edge_n, edge_type = graphutil.extractEdgeID(edge)
            if edge_type == 0:
                edge_d = graphutil.translateNetEdgeToDetailedEdgeTuple(net.getEdge(edge_n))
                if edge_d in edge_val_weights: edge_val_weights[edge_d] += count;
                else: edge_val_weights[edge_d] = 1 + count;
"""




""" (Another way of detecting newly added)
sim_vehicles = set(traci.vehicle.getIDList())
## Set type
if EV_PEN_IN_SIM:
    departed = set(traci.simulation.getDepartedIDList());
    newly_added = departed - manually_added_last_step
    manually_added_last_step.clear()
    for vehID in newly_added:
        if random.random() < EV_PEN:
            switchVType(vehID, "electric")
            # Set battery percent
            rand_charge = 0.1 * max_charge#max(0.01, 0.1 + (random.gauss() * 0.02)) * max_charge;
            traci.vehicle.setParameter(vehID, "device.battery.chargeLevel", str(rand_charge))

            #parking_edge_id = parkingNetGen.getParkingEdgeID(rand_edges[i].getID(), 0)
            #traci.vehicle.changeTarget(vehID, parking_edge_id)
        else:
            switchVType(vehID, "conventional")
        manually_added_last_step.add(vehID)
"""
#prep.genRandomTrips(data_path + 'base_net.net.xml', output_path + '/trips.xml', trips=200,
    #                    duration=SIM_DURATION, min_distance=(network_diameter / 4.0),
    #                    use_jtrrouter=USE_JTRROUTER)
    #print("-- randomTrips.py generated base trips. (at '" + (output_path + '/trips.xml') + "')")
    #prep.duarouter(data_path + 'base_net.net.xml', output_path + '/trips.xml', output_path + '/routes.xml')
    #print("-- duarouter generated base routes. (at '" + (output_path + '/routes.xml') + "')")
