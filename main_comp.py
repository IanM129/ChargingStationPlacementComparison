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

import lib.graphing as graphing  #= lib/graphing/__init__.py
import preprocess as prep

import lib.traci_utility as traciutil

from lib.structs.stationinfo import StationInfo, StationInfoDataset
from lib.structs.trip import Trip

import lib.traci_utility as traciutil

import lib.algorithms.algorithms as alg

import lib.graphing.utility as graphutil
import lib.graphing.draw as graphdraw

import lib.xml.parkingNetGen as parkingNetGen
import lib.xml.tripsGen as tripsGen
import lib.xml.output as xmlOut


#### Parameters
## Network and simulation
RECREATE_NETWORK = True
RANDOM_STATIONS = True
GEN_OUTPUTCFG = True
SIM_DURATION = 300
VEHICLE_COUNT = 100
STEP_LENGTH = 0.1
FRAME_DUR = 0.01
WAIT_QUEUE_SIZE = 10
STATION_CAPACITY = 10
STATION_FILL_REVERSE = False
# (used euro)
MONEY_PER_KWH_RED = 0.25
MONEY_PER_KWH_BLUE = 0.3
MANUAL_CHARGE_DECIDE = True
BATTERY_EMPTY_THRESHOLD = 2.0
## Car distribution
EV_PEN = 0.8
NEED_TO_CHARGE_PROBABILITY = 1.0;



#### Functions
veh_colors = {}
def colorByCharge(vehID, cur_charge, gradient=True):
    soc = float(cur_charge / float(max_charge))
    if gradient:
        if soc < 0.5:                           # (255, 0, 0) -> (255, 255, 0)
            color = (255, 255 * int(soc / 0.5), 0)
        else:                                   # (255, 255, 0) -> (0, 255, 0)
            color = (255 * int((soc - 0.5) / 0.5), 255, 0)
    else:
        if soc > 0.4:
            color = (0, 255, 0, 255)
        elif soc > 0.225:
            color = (255, 165, 0, 255)
        else:
            color = (255, 0, 0, 255)
    if vehID not in veh_colors or veh_colors[vehID] != color:
        traci.vehicle.setColor(vehID, color)
        veh_colors[vehID] = color
def switchVType(vehID, vtype):
    traci.vehicle.setType(vehID, vtype)
    return
    pos = traci.vehicle.getPosition(vehID)
    speed = traci.vehicle.getSpeed(vehID)
    route = traci.vehicle.getRouteID(vehID)
    lane = traci.vehicle.getLaneIndex(vehID)
    edge = traci.vehicle.getRoadID(vehID)
    traci.vehicle.remove(vehID)
    traci.vehicle.add(vehID=vehID, routeID=route, typeID=vtype);
    traci.vehicle.moveToXY(vehID, edge, lane, pos[0], pos[1], keepRoute=2)
    traci.vehicle.setSpeed(vehID, speed)

## Write stations to XML
##def writeStationsToXML(net, stations_dataset : StationInfoDataset,
##                       data_path, out_data_path="", net_filepath=None, stations_filepath=None,
##                       vehicle_length=-1, suffix="", reverse_angle=False):
##    if out_data_path == "": out_data_path = data_path;
##    if vehicle_length <= 0:
##        vTypes_tree = ET.parse(data_path + "/vTypes.add.xml");
##        veh_len = parkingNetGen.getVehicleLength(vTypes_tree);
##    # Load stations add.xml
##    if stations_filepath == None: stations_tree = ET.ElementTree(ET.fromstring("<additional></additional>"))
##    else: stations_tree = ET.parse(stations_filepath);
##    # Load network net.xml
##    if net_filepath == None: net_filepath = data_path + "/base_net.net.xml"
##    nodes_tree, edges_tree = parkingNetGen.extractNetworkFeatures(net_filepath)
##    # Main
##    for stinfo in stations_dataset:
##        edge = net.getEdge(stinfo.edge_id)
##        nodes_tree, edges_tree, stations_tree = parkingNetGen.createParkingNet(nodes_tree, edges_tree, stations_tree,
##                                                                               stinfo.edge_id, (edge.getFromNode().getID(), edge.getToNode().getID()),
##                                                                               vehicle_length=vehicle_length,
##                                                                               capacity=stinfo.total_capacity,
##                                                                               wait_queue=WAIT_QUEUE_SIZE, min_gap=min_gap,
##                                                                               suffix=suffix, reverse_angle=reverse_angle)
##    stations_tree.write(out_data_path + "/stations.add.xml")
##    parkingNetGen.write(nodes_tree, edges_tree, out_data_path + "/net.net.xml")


def blankStationDistribution(G, G_d, k, debug=False):
    candidates = graphing.calcCandidates(G_d, detailed_graph=True)
    ## Charging stations
    print("-- Station distribution algorithm () started...")
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
        plt.savefig(iter_output_path + "/distribution.jpg"); plt.clf();
    #
    print(f"-- Station distribution finished in {alg_etime - alg_stime:0.2f} seconds")
    #stations_edges = [graphutil.translateDetailedRoad(s, as_tuple=False) for s in stations_d]
    #print("Edges selected for stations:", stations_edges)
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


def getNextDestIndexInRoute(vehID, route=None, cur_index=-1):
    if route == None: route = traci.vehicle.getRoute(vehID);
    if cur_index < 0: cur_index = traci.vehicle.getRouteIndex(vehID);
    next_destination = None
    destinations = trips[vehID][1:]
    last_index = 0
    for dest in destinations:
        dest_index = route.index(dest, last_index, len(route))
        if dest_index > cur_index:
            return dest_index;
        if dest_index > last_index: last_index = dest_index;
    return -1
def getNextDestIndexInTrip(vehID, route=None, cur_index=-1):
    if route == None: route = traci.vehicle.getRoute(vehID);
    if cur_index < 0: cur_index = traci.vehicle.getRouteIndex(vehID);
    next_destination = None
    destinations = trips[vehID][1:]
    last_index = 0
    for i in range(len(destinations)):
        dest_index = route.index(destinations[i], last_index, len(route))
        if dest_index > cur_index:
            return i + 1;
        last_index = dest_index
    return -1

def calcNeededChargeLeft(vehID):
    average_consumption = float(traci.vehicle.getParameter(vehID, "device.battery.totalEnergyConsumed")) / traci.vehicle.getDistance(vehID)
    route = traci.vehicle.getRoute(vehID)
    cur_index = traci.vehicle.getRouteIndex(vehID)
    cur_edge = route[cur_index]
    next_dest_index = getNextDestIndexInTrip(vehID, route=route, cur_index=cur_index)
    distance = trips[vehID].remainingDistanceFromEdge(cur_edge, next_dest_index)
    #distance = traci.vehicle.getDrivingDistance(vehID, trips[vehID][-1], 0)
    #distance = traci.simulation.findRoute(fromEdge, toEdge).length
    return average_consumption * distance

def removeFromSimulationVars(vehicles : set):
    global sim_EVs, will_need_to_charge, going_to_charge, charging
    sim_EVs -= vehicles;
    if MANUAL_CHARGE_DECIDE:
        will_need_to_charge -= vehicles;
        for vehID in vehicles:
            going_to_charge.pop(vehID, None);
            if vehID in charging:
                si_index, park_side = charging[vehID][0]
                all_stations[si_index].releaseSpot(park_side)
                charging.pop(vehID, None);

def stationCostFunction(detour_time, detour_distance, money_cost):
    return detour_time + detour_distance + (money_cost * 100.0)
def findClosestChargingStation(vehID, charge, route=None, cur_index=-1, next_dest_index=-1):
    if route == None: route = traci.vehicle.getRoute(vehID);
    if cur_index < 0: cur_index = traci.vehicle.getRouteIndex(vehID);
    cur_edge = route[cur_index]
    if next_dest_index < 0:
        next_dest_index = getNextDestIndexInRoute(vehID, route, cur_index)
    next_dest_edge = route[next_dest_index]
    #print("-- destinations:\n", destinations)
    #print("-- route:\n", route)
    #print("---> next destination edge:", next_dest_edge)
    # General values
    #energy_needed = target - charge
    #charging_time = (energy_needed * 3600.0) / station_power
    # Get station values
    station_costs = {}
    station_routes = {}
    for sttn_info in all_stations:
        sttn_id = sttn_info.getID()
        #sttn_lane = traci.chargingstation.getLaneID(sttn_id)
        #sttn_edge = sttn_lane.rsplit('_', 1)[0]
        sttn_edge = sttn_info.redge_id
        # Normal route
        route_info = traci.simulation.findRoute(cur_edge, next_dest_edge)
        #ric = traciutil.calculateRouteInfo(route, cur_index, next_dest_index+1)
        # Route before station
        route_info_before = traci.simulation.findRoute(cur_edge, sttn_edge)
        detour_time = route_info_before.travelTime;
        detour_distance = route_info_before.length;
        # Route after station
        route_info_after = traci.simulation.findRoute(sttn_edge, next_dest_edge)
        detour_time += route_info_after.travelTime;
        detour_distance += route_info_after.length;
        detour_time_diff = detour_time - route_info.travelTime
        detour_distance_diff = detour_distance - route_info.length
        # Money cost
        if sttn_info.suffix == "_red": money_cost = MONEY_PER_KWH_RED;
        elif sttn_info.suffix == "_blue": money_cost == MONEY_PER_KWH_BLUE;
        else: raise Exception(f"Unknown suffix '{sttn_info.suffix}'.");
        # Calculate cost (maybe use the exact price for charging instead of per KWh)
        station_costs[sttn_id] = stationCostFunction(detour_time_diff, detour_distance_diff, money_cost)
        # Save routes
        station_routes[sttn_id] = (route_info_before, route_info_after)
    #print(cur_edge, "->", next_dest_edge)
    #for stid, stct in station_costs.items():
        #print(f"{stid:20s}: {stct}")
    # Choose by minimum of cost function
    chosen_sttn_id = min(station_costs, key=station_costs.get)
    sttn_info = all_stations.getByID(chosen_sttn_id)
    # Create adjusted route
    route_info_before = station_routes[chosen_sttn_id][0]
    route_info_after = station_routes[chosen_sttn_id][1]
    station_route = station_routes[chosen_sttn_id][0].edges + station_routes[chosen_sttn_id][1].edges[1:]
    new_trip = Trip([cur_edge, sttn_info.redge_id, next_dest_edge], [route_info_before.length, route_info_after.length])
    return (chosen_sttn_id, new_trip, station_route)


def genSumoCommand(visualize, in_data_path, step_length, log_filepath):
    sumo_binary = "sumo-gui" if visualize else "sumo"
    cmnd = [sumo_binary, "-c", in_data_path + ".sumocfg",
            "--step-length", str(STEP_LENGTH), "--start",
            "--log", log_filepath]
    if visualize:
        cmnd.extend(["--delay", str(STEP_LENGTH * 1000)])
    return cmnd
def fetchOptionalParameters():
    visualize = False
    duration = 120
    for i in range(3, len(sys.argv)):
        if sys.argv[i] == "--visualize" or sys.argv[i] == "-v":
            visualize = True
        elif sys.argv[i] == "--duration" or sys.argv[i] == "-d":
            if (len(sys.argv[i]) == i + 1 or not isnumeric(sys.argv[i + 1])):
                print("- No value given for duration argument."); printUsage(); exit(0);
            duration = int(sys.argv[i + 1])
    return (visualize, duration)
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
    ## Preprocess output config
    if GEN_OUTPUTCFG:
        xmlOut.config_enableStationOutput(in_data_path + ".sumocfg", enable=True, aggregate=True)
        xmlOut.config_enableBatteryOutput(in_data_path + ".sumocfg", enable=False)
        print("-- SUMO file output settings configured.")
    ## Load XMLs
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    vTypes_tree = ET.parse(data_path + "/vTypes.add.xml", parser=parser)
    basenet_tree = ET.parse(data_path + "/base_net.net.xml")
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
                          min_distance_per_des=(network_diameter / 4.0),
                          min_distance=network_diameter*3.0,
                          #max_distance=network_diameter*4.0,
                          ev_pen=EV_PEN)
    #print(trips)
    avg_trip_len = 0
    for trip in trips.values():
        avg_trip_len += trip.total_distance
    avg_trip_len /= len(trips)
    avg_trip_charge = prep.calcApproxChargeNeeded(avg_trip_len);
    print("-- generated random vehicles and trips.")
    print(f"     > trip average distance: {avg_trip_len:8.2f} -> ~{avg_trip_charge:6.1f} Wh ({avg_trip_charge / max_charge:4.2f}) charge")
    ## Update XML settings
    prep.enableBattery(vTypes_tree, True)
    prep.enableStationFinder(vTypes_tree, not MANUAL_CHARGE_DECIDE)
    vTypes_tree.write(data_path + "/vTypes.add.xml") # rewrite modified vTypes XML tree

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
            stations_r_d, dist_radius_r = blankStationDistribution(G, G_d, k)
            if dist_radius_r == 0: dist_radius_r = network_diameter / 2.0;
            stations_b_d, dist_radius_b = blankStationDistribution(G, G_d, k)
            if dist_radius_b == 0: dist_radius_b = network_diameter / 2.0;
        else:
            stations_r_d, dist_radius_r = statsStationDistribution(G, G_d, k, edge_val_weights, first_station_d)
            stations_b_d, dist_radius_b = statsStationDistribution(G, G_d, k, edge_val_weights, first_station_d)
        dist_radius = max(dist_radius_r, dist_radius_b)
        #min_charge = prep.calcApproxChargeNeeded(dist_radius); min_charge_p = min_charge / max_charge;
        print(f"-- min charge ~= {prep.calcApproxChargeNeeded(dist_radius):6.1f} Wh ({min_charge_p:4.2f})")
        # Station info from detailed edges
        stations_r = StationInfoDataset([StationInfo.fromDetailedEdge(s, STATION_CAPACITY, suffix="_red") for s in stations_r_d])
        stations_b = StationInfoDataset([StationInfo.fromDetailedEdge(s, STATION_CAPACITY, suffix="_blue") for s in stations_b_d])
        print("-- Red stations: ", stations_r.printEdges())
        print("-- Blue stations:", stations_b.printEdges())
        ## Write stations to XML
        nodes_tree, edges_tree, stations_tree = parkingNetGen.addStationsToNetwork(base_net, stations_r,
                                                    data_path, write=False, #out_data_path=iter_output_path,
                                                    network_tree=basenet_tree, #network_filepath=data_path + "/base_net.net.xml",
                                                    #stations_filepath=None,
                                                    vehicle_length=EV_len, min_gap=min_gap, wait_queue_size=WAIT_QUEUE_SIZE,
                                                    suffix="_red")
        parkingNetGen.appendStationsToNetwork(base_net, stations_b,
                                              nodes_tree, edges_tree, stations_tree,
                                              write=True, out_data_path=iter_output_path,
                                              vehicle_length=EV_len, min_gap=min_gap, wait_queue_size=WAIT_QUEUE_SIZE,
                                              suffix="_blue", reverse_angle=True);
        print("-- stations written to network XML. (at '" + (iter_output_path + "/net.net.xml") + "')")
        # DEBUG -> Show POIs for stations
        parkingNetGen.addStationPOIs(iter_output_path + "/net.net.xml", iter_output_path + "/stations.add.xml", stations_r.listEdges(), suffix="_red")
        parkingNetGen.addStationPOIs(iter_output_path + "/net.net.xml", iter_output_path + "/stations.add.xml", stations_b.listEdges(), suffix="_blue")
        # Reload net
        net = sumolib.net.readNet(iter_output_path + "/net.net.xml")
        ## Preprocess output config (post station generation)
        # Induction loop
        xmlOut.config_createInductionLoopOutputFile(net.getEdges(), xml_filepath=data_path + "/output.add.xml",
                                                    output_filepath="output/" + start_datetime_str + "/" + str(i+1) + "/loop.out.xml", overwrite=True)
        # Edge based macroscopic traffic measures
        xmlOut.config_createEdgeOutputFile(xml_filepath=data_path + "/output.add.xml", output_filepath="output/" + start_datetime_str + "/" + str(i+1) + "/edgeData.out.xml", overwrite=False)
        ## Fix trip destinations
        trips = prep.fixTripEdges(base_net, net, output_path + "/trips.xml",
                                 stations_r.listEdges() + stations_b.listEdges(),
                                 output_filepath=iter_output_path + "/trips.xml",
                                 trips=trips)
        prep.copyFileForSimulation(iter_output_path + "/trips.xml", data_path + "/routes.xml")
        ## Copy requred files to run simulation
        if iteration_count > 0:
            prep.copyFileForSimulation(iter_output_path + "/net.net.xml", data_path + "/net.net.xml")
            prep.copyFileForSimulation(iter_output_path + "/stations.add.xml", data_path + "/stations.add.xml")
        ## Command
        if iteration_count > 0:
            log_filepath = iter_output_path + "/log.txt"
        else:
            log_filepath = data_path + "/output/logs/log_" + start_datetime_str + ".txt"
        cmnd = genSumoCommand(visualize, in_data_path, STEP_LENGTH, log_filepath)
        print("-> SUMO command:\n'" + ' '.join(cmnd) + "'")
        
#### SIMULATION
        sim_EVs = set(); manually_added_last_step = set();
        EVs_count = 0; total_veh_count = 0;
        set_need_to_charge_cnt = 0;
        sttn_util_rate = {}
        all_stations = StationInfoDataset(stations_r.arr + stations_b.arr)
        if MANUAL_CHARGE_DECIDE:
            will_need_to_charge = set()
            going_to_charge = {}
            charging = {}
            ev_ntc_charge = {}
            remaining_range = {}
        for sttn_edge_id, _ in all_stations.listIDss():
            sttn_util_rate[sttn_edge_id] = [0, 0];
        ## Run simulation
        sim_stime = time.perf_counter()
        print(f"-- Simulation started ({i + 1:3d} / {iteration_count:3d})...")
        traci.start(cmnd)
        ## Subscriptions
        traci.simulation.subscribe([
            traci.constants.VAR_DEPARTED_VEHICLES_IDS,                          #
            traci.constants.VAR_ARRIVED_VEHICLES_IDS                            # getArrivedIDList()
            #traci.constants.VAR_TELEPORT_END                                   # getDepartedIDList()
        ])
        for sttn_info in all_stations:
            park_id = sttn_info.park_id
            traciutil.subscribeParkingVehicleCount(park_id + "_0")
            traciutil.subscribeParkingVehicleCount(park_id + "_1")
        while traci.simulation.getMinExpectedNumber() > 0: #and traci.simulation.getTime() < duration:
            # Step
            traci.simulationStep();
            data_sim = traci.simulation.getSubscriptionResults()

            #### Process state
            ## Arrived
            # -> remove arrived EVs
            arrived = set(data_sim.get(tc.VAR_ARRIVED_VEHICLES_IDS, []))            #set(traci.simulation.getArrivedIDList())
            removeFromSimulationVars(arrived) #sim_EVs -= arrived
                   
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
                                next_dest_index_r = getNextDestIndexInRoute(vehID, route, cur_index)
                                # Get charging station and station trip
                                target_station, station_trip, station_route = findClosestChargingStation(vehID, charge, route=route, cur_index=cur_index, next_dest_index=next_dest_index_r)
                                # Update new route and trip
                                new_route = station_route + route[next_dest_index_r + 1:]
                                #trips[vehID].update(station_trip, index=cur_index)
                                next_dest_index_t = getNextDestIndexInTrip(vehID, route, cur_index)
                                trips[vehID].insertToNextDestination(station_trip, next_dest_index_t)
                                # Set stop
                                target_si = all_stations.getByID(target_station)
                                traci.vehicle.setRoute(vehID, new_route)
                                traci.vehicle.setStop(vehID, target_si.redge_id, pos=parkingNetGen.calcVehicleQueueLength(EV_len, min_gap, WAIT_QUEUE_SIZE));
                                # Update set
                                go_charge_this_step[vehID] = target_station
                    if visualize:
                        # Color by charge
                        colorByCharge(vehID, charge)
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
                        target_si_index = all_stations.getIndexByID(target_station)
                        target_si = all_stations[target_si_index]
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
                            all_stations[si_index].releaseSpot(park_side)
                            # Check if can make journey; if not keep monitoring it
                            approx_charge_needed = calcNeededChargeLeft(vehID)
                            # DISTANCE
                            route = traci.vehicle.getRoute(vehID)
                            cur_index = traci.vehicle.getRouteIndex(vehID)
                            cur_edge = route[cur_index]
                            next_dest_index = getNextDestIndexInTrip(vehID, route=route, cur_index=cur_index)
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
                    charge_target = calcNeededChargeLeft(vehID) + 500 # padding so it doesn't need to go recharge
                    charge_target = ev_ntc_charge[vehID] + charge_target
                    charging[vehID] = (start_charging_this_step[vehID], min(charge_target, max_charge))
            
                    
            ## Newly added
            # -> count and add newly created EVs; set starting charge
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
            for si in all_stations:
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
        for si in all_stations:
            st_id = si.getID(); st_cap = si.total_capacity;
            sttn_util_rate[st_id] = (float(sttn_util_rate[st_id][0] / steps_processed),
                                     float(sttn_util_rate[st_id][1] / (steps_processed * st_cap)));

        ## Total charge from station
        #print("Total charge used per station | utlization rate:")
        stations_charges_data = xmlOut.getAllStationCharges(data_path)
        station_charges = {}
        veh_charges = {}
        sttn_vehicle_count = {}
        for si in all_stations:
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
            #print(f"{si.edge_id:10s}: {round(total, 2):8.2f} | {round(sttn_util_rate[station_id],2)}")
            station_charges[si.getID()] = total
        EVs_charged = len(veh_charges.keys()); EVs_charged_ratio = EVs_charged / set_need_to_charge_cnt;
        #print(f"-> total money earned: {round(money_earned,2)}€ ({round(MONEY_PER_KWH,2)}€ per KWh)")
        #print()

        print("---- Station stats:")
        print("     <station edge ID>: <energy recharged> | <utilization per step>, <utilization normalized by total parking capacity>")
        print("-- Red:")
        total_charge_r = 0;
        for si in stations_r:
            val = station_charges[si.getID()]
            print(f"  {si.edge_id:10s}: {round(val, 2):9.2f} | {sttn_vehicle_count[si.getID()]:4d}",
                  f"(util: {round(sttn_util_rate[si.getID()][0] * 100.0,2):5.2f} %, {round(sttn_util_rate[si.getID()][1] * 100.0, 2):4.2f} %)")
            total_charge_r += val
        money_earned_r = (total_charge_r * float(MONEY_PER_KWH_RED)) / 1000.0
        print(f"  > total charge: {round(total_charge_r / 1000.0, 2)} KWh")
        print(f"  > money earned: {round(money_earned_r, 2)}€ ({round(MONEY_PER_KWH_RED,2)}€ per KWh)")
        print("-- Blue:")
        total_charge_b = 0
        for si in stations_b:
            val = station_charges[si.getID()]
            print(f"  {si.edge_id:12s}: {round(val, 2):9.2f} | {sttn_vehicle_count[si.getID()]:4d}",
                  f"(util: {round(sttn_util_rate[si.getID()][0] * 100.0,2):5.2f} %, {round(sttn_util_rate[si.getID()][1] * 100.0, 2):4.2f} %)")
            total_charge_b += val
        money_earned_b = (total_charge_b * float(MONEY_PER_KWH_BLUE)) / 1000.0
        print(f"  > total charge: {round(total_charge_b / 1000.0, 2)} KWh")
        print(f"  > money earned: {round(money_earned_b, 2)}€ ({round(MONEY_PER_KWH_BLUE,2)}€ per KWh)")
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
        best_station_r = max(stations_r.listIDs(), key=station_charges.get)
        best_station_b = max(stations_b.listIDs(), key=station_charges.get)
        best_station = max(station_charges, key=station_charges.get)
        best_station_info = all_stations.getByID(best_station)
        best_sttn_r_info = stations_r.getByID(best_station_r)
        best_sttn_b_info = stations_b.getByID(best_station_b)
        best_station_d = graphutil.translateNetEdgeToDetailedEdgeID(net.getEdge(best_station_info.edge_id))
        best_sttn_d_r = graphutil.translateNetEdgeToDetailedEdgeID(net.getEdge(best_sttn_r_info.edge_id))
        best_sttn_d_b = graphutil.translateNetEdgeToDetailedEdgeID(net.getEdge(best_sttn_b_info.edge_id))
        print(f"--> best stations:")
        print(f"    - Red:     {best_sttn_r_info.edge_id:10s} ({round(station_charges[best_station_r] / 1000.0, 2)} KWh)")
        print(f"    - Blue:    {best_sttn_b_info.edge_id:10s} ({round(station_charges[best_station_b] / 1000.0, 2)} KWh)")
        print(f"    - OVERALL: {best_station_info.edge_id:10s} ({round(station_charges[best_station] / 1000.0, 2)} KWh)")
        first_station_d_r = best_sttn_d_r; first_station_d_b = best_sttn_d_b;
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
        graphdraw.drawNodes(G_d, stations_r_d, node_size=100, color=(1, 0, 0))
        graphdraw.drawNodes(G_d, stations_b_d, node_size=100, color=(0, 0, 1))
        graphdraw.drawNodes(G_d, set(stations_r_d).intersection(set(stations_b_d)), node_size=100, color=(1, 0, 1))
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
