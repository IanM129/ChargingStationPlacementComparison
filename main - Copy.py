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

sumoBinary = sumolib.checkBinary('sumo')
import randomTrips

import graphing
import preprocess as prep

import lib.algorithms.algorithms as alg

import lib.graphing.utility as graphutil

import lib.xml.parkingNetGen as parkingNetGen
import lib.xml.output as xmlOut




#### Vars
vehicles = set()

#### Parameters
## Network and simulation
RECREATE_NETWORK = True
RANDOM_TRIPS = True
USE_JTRROUTER = False
RANDOM_STATIONS = True
GEN_OUTPUTCFG = True
STEP_LENGTH = 0.1
FRAME_DUR = 0.01
STATION_LANE_LEN = 20
## Car distribution
EV_PEN = 0.8

#### Simulation vars
EV_PEN_IN_SIM = not USE_JTRROUTER
sim_vehicles = set()



#### Functions
veh_colors = {}
def colorByCharge(vehID):
    capacity = float(traci.vehicle.getParameter(vehID, "device.battery.capacity"))
    currentCharge = float(traci.vehicle.getParameter(vehID, "device.battery.chargeLevel"))
    stateOfCharge = currentCharge / capacity
    if stateOfCharge > 0.4:
        color = (0, 255, 0, 255)
    elif stateOfCharge > 0.225:
        color = (255, 165, 0, 255)
    else:
        color = (255, 0, 0, 255)
    if vehID not in veh_colors or veh_colors[vehID] != color:
        traci.vehicle.setColor(vehID, color)
        veh_colors[vehID] = color


def switchVType(vehID, vtype):
    pos = traci.vehicle.getPosition(vehID)
    speed = traci.vehicle.getSpeed(vehID)
    route = traci.vehicle.getRouteID(vehID)
    lane = traci.vehicle.getLaneIndex(vehID)
    edge = traci.vehicle.getRoadID(vehID)
    traci.vehicle.remove(vehID)
    traci.vehicle.add(vehID=vehID, routeID=route, typeID=vtype);
    traci.vehicle.moveToXY(vehID, edge, lane, pos[0], pos[1], keepRoute=2)
    traci.vehicle.setSpeed(vehID, speed)
    

def blankStationDistribution(G, G_d):
    candidates = graphing.calcCandidates(G_d, detailed_graph=True)
    ## Charging stations
    vTypes_tree = ET.parse(data_path + "/vTypes.add.xml");
    print("-- Station distribution algorithm started...")
    alg_stime = time.perf_counter()
    # Get station locations (edges)
    if RANDOM_STATIONS:
        # -> random
        stations_d = alg.pickRandom(candidates, 6)
    else:
        # -> algorithm
        radius, stations_d = alg.radiusBinarySearch(G, G_d, candidates, 7, epsilon=1,
                                                    distribution_alg=alg.farthestFirstCoverageBased)
    alg_etime = time.perf_counter()
    print(f"-- Station distribution finished in {alg_etime - alg_stime:0.2f} seconds")
    stations_edges = [graphutil.translateDetailedRoad(s, as_tuple=False) for s in stations_d]
    print("Edges selected for stations:", stations_edges)
    return stations_d

def statsStationDistribution():

    return



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
        duration = 300

    sumo_binary = "sumo-gui" if visualize else "sumo"
    match (situation.lower()):
        case "manhattan":
            filepath = "manhattan/"; data_path = filepath + "data/"; in_data_path = data_path + "manhattan";
        case "zagreb":
            filepath = "Zagreb/"; data_path = filepath + "data/"; in_data_path = data_path + "zagreb";
        case _:
            print("- Invalid <situation> value."); printUsage(); exit(0);

    #### Preprocess
    ### Pre-loop
    ## Folder structure
    prep.outputFolder(data_path)
    ## Network
    if RECREATE_NETWORK:
        prep.recreateNetwork(in_data_path + ".netgcfg", "base_net.net.xml")
    net = sumolib.net.readNet(data_path + "/base_net.net.xml")
    ## Preprocess output config
    if GEN_OUTPUTCFG:
        xmlOut.config_enableStationOutput(in_data_path + ".sumocfg", enable=True, aggregate=True)
        xmlOut.config_enableBatteryOutput(in_data_path + ".sumocfg", enable=False)
    ### In-loop
    ## Graphs
    G = graphing.netToGraph(data_path + "/base_net.net.xml")
    G_d = graphing.netToDetailedGraph(data_path + "/base_net.net.xml")
    candidates = graphing.calcCandidates(G_d, detailed_graph=True)
    ## Charging stations
    vTypes_tree = ET.parse(data_path + "/vTypes.add.xml");
    print("-- Station distribution algorithm started...")
    alg_stime = time.perf_counter()
    # Get station locations (edges)
    if RANDOM_STATIONS:
        # -> random
        stations_d = alg.pickRandom(candidates, 6)
    else:
        # -> algorithm
        radius, stations_d = alg.radiusBinarySearch(G, G_d, candidates, 7, epsilon=1,
                                                    distribution_alg=alg.farthestFirstCoverageBased)
    alg_etime = time.perf_counter()
    print(f"-- Station distribution finished in {alg_etime - alg_stime:0.2f} seconds")
    stations_edges = [graphutil.translateDetailedRoad(s, as_tuple=False) for s in stations_d]
    print("Edges selected for stations:", stations_edges)
    # Add charging stations to XML
    net_filepath = data_path + "/base_net.net.xml"
    stations_tree = ET.ElementTree(ET.fromstring("<additional></additional>"))
    veh_len = parkingNetGen.getVehicleLength(vTypes_tree);
    nodes_tree, edges_tree = parkingNetGen.extractNetworkFeatures(net_filepath)
    stations_ids = []
    for ste in stations_edges:
        nodes_tree, edges_tree, stations_tree = parkingNetGen.createParkingNet(nodes_tree, edges_tree, stations_tree, ste, vehicle_length=veh_len, capacity=5)
        parking_id = parkingNetGen.getLaneID(ste, 0)
        station_id = parkingNetGen.getStationID(ste)
        stations_ids.append(station_id)
    stations_tree.write(data_path + "/stations.add.xml")
    parkingNetGen.write(nodes_tree, edges_tree, (data_path + "/net.net.xml"))
    net = sumolib.net.readNet(data_path + "/net.net.xml") # Reload net
    ## Routes and vehicle micromanagement
    if RANDOM_TRIPS:
        prep.genRandomTrips(data_path + 'net.net.xml', data_path, flows=500, use_jtrrouter=USE_JTRROUTER)
        if USE_JTRROUTER:
            call([jtrrouterBinary, '-c', in_data_path + '.jtrrcfg'])
            prep.jtrrouterSetVTypes(data_path + "/routes.xml", ev_penetration=EV_PEN)
    ## Preprocess output config (post station generation)
    if GEN_OUTPUTCFG:
        xmlOut.config_createEdgeOutputFile(net.getEdges(), xml_filepath=data_path + "/output.add.xml",
                                           output_filepath="output/loop.out.xml")
        

    #### Execute simulation
    #printRunStart(0, situation);

    ## Setup metric dics
    if False:
        max_steps = int((duration // STEP_LENGTH) + 1)

    # Side vars
    max_charge = prep.getMaxChargeFromAddTree(vTypes_tree)

    # Settings
    LOOP = True
    iteration_count = 5

    if not LOOP: iteration_count = 1;
    # Start
    date_time_now_str = str(datetime.now().strftime('%Y%m%d_%H%M%S'))
    log_filepath = data_path + "/output/logs/log_" + date_time_now_str
    cmnd = [sumo_binary, "-c", in_data_path + ".sumocfg",
            #"-battery-output", "battery_out.xml",
            #"-chargingstations-output", "chargingstations_out.xml",
            "--step-length", str(STEP_LENGTH), "--start",
            "--log", log_filepath + ".txt"]
    if visualize:
        cmnd.extend(["--delay", str(STEP_LENGTH * 1000)])
    print("-> SUMO command:\n'" + ' '.join(cmnd) + "'")

    #### LOOP
    for i in range(iteration_count):
        #### Process
        ## Graphs
        G = graphing.netToGraph(data_path + "/base_net.net.xml")
        G_d = graphing.netToDetailedGraph(data_path + "/base_net.net.xml")
        if i == 0:
            blankStationDistribution(G, G_d)
        else:
            pass
        net = sumolib.net.readNet(data_path + "/net.net.xml") # Reload net

        #### Simulation
        sim_EVs = set(); manually_added_last_step = set();
        EVs_count = 0; total_veh_count = 0;
        sim_stime = time.perf_counter()
        print(f"-- Simulation started ({i + 1:3d} / {iteration_count:3d})...")
        traci.start(cmnd)
        while traci.simulation.getMinExpectedNumber() > 0 and traci.simulation.getTime() < duration:
            # Step
            traci.simulationStep();

            #### Process state
            #for vehID in manually_added_last_step:
            #    vtype = traci.vehicle.getTypeID(vehID)
            #    if vtype == "electric":
                    ## Subscribe for dead battery checks
            #        traci.vehicle.subscribe(vehID, (tc.VAR_SPEED, tc.VAR_ROAD_ID))
            ## Newly added
            departed = set(traci.simulation.getDepartedIDList());
            newly_added = departed - manually_added_last_step
            manually_added_last_step.clear()
            for vehID in newly_added:
                ## Set type
                if EV_PEN_IN_SIM:
                    manually_added_last_step.add(vehID); total_veh_count += 1;
                    if random.random() < EV_PEN:
                        switchVType(vehID, "electric"); EVs_count += 1;
                        # Set battery percent
                        rand_charge = 0.1 * max_charge#max(0.01, 0.1 + (random.gauss() * 0.02)) * max_charge;
                        traci.vehicle.setParameter(vehID, "device.battery.chargeLevel", str(rand_charge))
                        #parking_edge_id = parkingNetGen.getParkingEdgeID(rand_edges[i].getID(), 0)
                        #traci.vehicle.changeTarget(vehID, parking_edge_id)
                        sim_EVs.add(vehID);
                    else:
                        switchVType(vehID, "conventional");

            #removed = set()
            #for vehID in sim_EVs:
            #    if vehID in traci.vehicle.getIDList():
            #        sub = traci.vehicle.getSubscriptionResults(vehID)
            #        if not sub: continue;

            #        speed = sub[tc.VAR_SPEED]
            #        edge = sub[tc.VAR_ROAD_ID]
            #        if speed < 0.1:
            #            cur_charge = float(traci.vehicle.getParameter(vehID, "device.battery.chargeLevel"))
            #            if cur_charge < 10:
            #                print(f"-> {vehID} ({speed}): {cur_charge}")
            #                traci.vehicle.remove(vehID);
            #                removed.add(vehID);
            #sim_EVs = sim_EVs - removed

            
            ## Visualize
            #if visualize:
            #    for vehID in sim_EVs:
            #        # Color by charge
            #        colorByCharge(vehID)
                        

        # Simulation done
        traci.close()
        sim_etime = time.perf_counter()
        print(f"\n\n-- Simulation over after {sim_etime - sim_stime:0.2f} seconds")

        #### Fetch stats and results
        ## Total charge from station
        print("Total charge used per station:")
        stations_charges_data = xmlOut.getAllStationCharges(data_path)
        station_charges = {}
        for stid in stations_ids:
            stid_edge = parkingNetGen.getEdgeOfStationID(stid)
            total = 0;
            if stid in stations_charges_data:
                charges = stations_charges_data[stid];
                for vehID in charges.keys():
                    for charge in charges[vehID]:
                        total += charge["totalEnergy"]
            print(f"{stid_edge:10s}: {round(total, 2)}")
            station_charges[stid_edge] = total
        print()
        ## Get broken down (empty battery) cars
        # WARNING: This uses the debug logs so isn't consistent between different SUMO versions,
        # but is most performance optimal (instead of polling every simulation step)
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
        print(f"--> Arrived EVs ratio: {arrived_EVs_ratio} ({arrived_EVs_cnt} / {EVs_count}) [total: {total_veh_count}]")
        print()

        ## Get battery depletion warnings
        bd_warnings = xmlOut.getBatteryDepletionWarnings(log_filepath)
        if len(bd_warnings) == 0: print("No battery depletion warnings.");
        else:
            print(f"Battery depletion warnings [{len(bd_warnings)}]:")
            for warning in bd_warnings:
                vehID, time = warning
                print(f"- {time}: {vehID}")
        print()
        ## Get flow at edges
        edge_stats = xmlOut.getEdgeLoopStats(data_path, max_flow=True)
        
        #### Rerun algorithm with new edge weigths
        net = sumolib.net.readNet(data_path + "/base_net.net.xml")
        ## Get best station
        best_station = max(station_charges, key=station_charges.get)
        best_station_d = graphutil.translateNetEdgeToDetailedEdgeID(net.getEdge(best_station))
        print(f"-> best station: {best_station} ({best_station_d})")
        ## Calculate weights
        edge_val_weights = {}
        # Improve by flow at the edge
        max_flow = edge_stats["_maxFlow"]
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
        print(f"Updated edge value weights:")
        print(edge_val_weights)


        G = graphing.netToGraph(data_path + "/base_net.net.xml")
        G_d = graphing.netToDetailedGraph(data_path + "/base_net.net.xml")
        candidates = graphing.calcCandidates(G_d, detailed_graph=True)
        alg.radiusBinarySearch_EdgeWeights(G, G_d, candidates, 6, edge_val_weights, first_station=best_station_d,
                                           epsilon=50, default_edge_weight=1, debug=True)
    







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
