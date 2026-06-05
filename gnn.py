import os
import sys
import traceback
import math
from datetime import datetime
import time
import random
import pathlib
import sumolib
import networkx as nx
import copy
import numpy as np
import matplotlib.pyplot as plt
import xml.etree.ElementTree as ET
from tqdm import tqdm

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Multinomial
from torch_geometric.nn import GCNConv
from torch_geometric.data import Data
from torch_geometric.utils import from_networkx as torch_from_networkx

#import libsumo as traci
global libsumo_m, traci_m
import libsumo as libsumo_m
import traci as traci_m

import preprocess as prep

from lib.utility import clamp, welford, ema, ema_welford, zscore

import lib.graphing as graphing  #= lib/graphing/__init__.py
import lib.graphing.utility as graphutil
import lib.graphing.draw as graphdraw

from lib.gnn.model1 import EdgeGNN
from lib.gnn.model2 import EdgePosGNN
import lib.gnn.utility as gnnutil

import lib.traci_utility as traciutil
import lib.visual_utility as visutil

from lib.structs.stationinfo import StationInfo, StationInfoDataset
from lib.structs.trip import Trip
from lib.structs.graphtranslator import GraphTranslator
from lib.structs.evaluation import Evaluation
from lib.structs.params import Parameters

import lib.xml.tripsGen as tripsGen
import lib.xml.output as xmlOut

import lib.algorithms.coverage as coverAlg

from lib.sumo.blank import sumoBlankRun
from lib.sumo.solo import sumoSoloRun

MAIN_DIR = pathlib.Path(__file__).resolve().parent
os.chdir(MAIN_DIR)


###### FUNCTIONS
#### Training environment
def getReward_flow(selected_edges, graph, iteration):
    global edge_attr_map
    flow_sum = graph.edge_attr[selected_edges, edge_attr_map["flow"]].sum().item()
    return flow_sum
def rewardFunction(stations, results, params, formula):
    global running_dict
    reward = 0.0
    # Coverage penalty (bounded with target; minimize)
    if ((factor := params["reward.totalCoverage"]) != 0.0) or (params["reward.totalCoverage.monitor"]):
        global coverage_radius_target
        coverage_radius = float(coverAlg.coverageRadiusBinarySearch(coverage_G_d, stations.listDNodes(base_net),
                                                                    epsilon=50,
                                                                    max_radius=network_diameter))
        if factor != 0.0:
            radius_n = -np.tanh(coverage_radius / coverage_radius_target)
            reward += factor * radius_n;
            formula["totalCoverage"] = (coverage_radius, float(radius_n));
        else: formula["totalCoverage"] = (coverage_radius, 0.0);
    # Charge (EMA -> Z-score -> tanh; maximize)
    if ((factor := params["reward.totalCharge"]) != 0.0) or (params["reward.totalCharge.monitor"]):
        charge_val = float(results.station_data["totalCharge"])
        if factor != 0.0:
            charge_mean, charge_var = running_dict["totalCharge"]
            # EMA -> Z-score -> tanh
            charge_mean, charge_var = ema_welford(charge_val, charge_mean, charge_var, alpha=EMA_ALPHA)
            z = zscore(charge_val, charge_mean, math.sqrt(charge_var))
            charge_n = np.tanh(z)
            # Running scale
            #if sess_charge_scale == None:
            #    charge_n = 0.0; sess_charge_scale = charge_val;
            #else:
            #    charge_n = np.tanh(charge_val / sess_charge_scale)
            #    sess_charge_scale = (sess_charge_scale * 0.95) + (charge_val * 0.05)
            # Reward
            reward += factor * charge_n
            formula["totalCharge"] = (float(charge_val), float(charge_n));
            running_dict["totalCharge"] = (charge_mean, charge_var)
        else: formula["totalCharge"] = (float(charge_val), 0.0);
    # Duration (EMA -> Z-score -> tanh; minimize) and completeness
    if ((factor := params["reward.simDuration"]) != 0.0) or (params["reward.simDuration.monitor"]):
        fully_complete = results.fullyCompleted
        sim_time = float(results.simulationTime)
        if factor != 0.0:
            simDuration_mean, simDuration_var = running_dict["simDuration"]
            # EMA -> Z-score -> tanh
            simDuration_mean, simDuration_var = ema_welford(sim_time, simDuration_mean, simDuration_var, alpha=EMA_ALPHA)
            z = zscore(sim_time, simDuration_mean, math.sqrt(simDuration_var))
            time_n = -np.tanh(z)
            # Basic scaling
            #-np.tanh(sim_time / sess_duration_scale)
            #sess_duration_scale = (sess_duration_scale * 0.95) + (sim_time * 0.05)
            # Not completed penalty
            if not fully_complete: time_n -= 0.5;
            # Reward
            reward += factor * time_n
            formula["simDuration"] = (sim_time, float(time_n));
            running_dict["simDuration"] = (simDuration_mean, simDuration_var)
        else: formula["simDuration"] = (sim_time, 0.0);
    # Trip duration [average] (EMA -> Z-score -> tanh; minimize)
    if ((factor := params["reward.tripDuration"]) != 0.0) or (params["reward.tripDuration.monitor"]):
        trip_duration = float(results.trip_data["tripDuration"])
        if factor != 0.0:
            tripDuration_mean, tripDuration_var = running_dict["tripDuration"]
            # EMA -> Z-score -> tanh
            tripDuration_mean, tripDuration_var = ema_welford(trip_duration, tripDuration_mean, tripDuration_var, alpha=EMA_ALPHA)
            z = zscore(trip_duration, tripDuration_mean, math.sqrt(tripDuration_var))
            tripdur_n = -np.tanh(z)
            # Reward
            reward += factor * tripdur_n
            formula["tripDuration"] = (trip_duration, tripdur_n);
            running_dict["tripDuration"] = (tripDuration_mean, tripDuration_var)
        else: formula["tripDuration"] = (trip_duration, 0.0);
    # Trip length [average] (using calculated average trip length from blank simulation; minimize)
    if ((factor := params["reward.tripLength"]) != 0.0) or (params["reward.tripLength.monitor"]):
        trip_length = float(results.trip_data["tripLength"])
        global average_trip_len
        if factor != 0.0:
            # Divide by (blank average trip length * 2)
            triplen_n = -np.tanh(trip_length / (average_trip_len * 2.0))
            # Reward
            reward += factor * triplen_n
            formula["tripLength"] = (trip_length, float(triplen_n));
        else: formula["tripLength"] = (trip_length, 0.0);
    # Trip wait time [average] (EMA -> Z-score -> tanh; minimize)
    if ((factor := params["reward.waitTime"]) != 0.0) or (params["reward.waitTime.monitor"]):
        wait_time = float(results.trip_data["waitTime"])
        if factor != 0.0:
            waitTime_mean, waitTime_var = running_dict["waitTime"]
            # EMA -> Z-score -> tanh
            waitTime_mean, waitTime_var = ema_welford(wait_time, waitTime_mean, waitTime_var, alpha=EMA_ALPHA)
            z = zscore(wait_time, waitTime_mean, math.sqrt(waitTime_var))
            waittime_n = -np.tanh(z)
            # Reward
            reward += factor * waittime_n
            formula["waitTime"] = (wait_time, float(waittime_n));
            running_dict["waitTime"] = waitTime_mean, waitTime_var
        else: formula["waitTime"] = (wait_time, 0.0);
    # Stop time [average] (EMA -> Z-score -> tanh; minimize)
    if ((factor := params["reward.stopTime"]) != 0.0) or (params["reward.stopTime.monitor"]):
        stop_time = float(results.trip_data["stopTime"])
        if factor != 0.0:
            stopTime_mean, stopTime_var = running_dict["stopTime"]
            # EMA -> Z-score -> tanh
            stopTime_mean, stopTime_var = ema_welford(stop_time, stopTime_mean, stopTime_var, alpha=EMA_ALPHA)
            z = zscore(stop_time, stopTime_mean, math.sqrt(stopTime_var))
            stoptime_n = -np.tanh(z)
            # Reward
            reward += factor * stoptime_n
            formula["stopTime"] = (stop_time, float(stoptime_n));
            running_dict["stopTime"] = stopTime_mean, stopTime_var
        else: formula["stopTime"] = (stop_time, 0.0);
    # Time lost [average] (EMA -> Z-score -> tanh; minimize)
    if ((factor := params["reward.timeLoss"]) != 0.0) or (params["reward.timeLoss.monitor"]):
        time_loss = float(results.trip_data["timeLoss"])
        if factor != 0.0:
            timeLoss_mean, timeLoss_var = running_dict["timeLoss"]
            # EMA -> Z-score -> tanh
            timeLoss_mean, timeLoss_var = ema_welford(time_loss, timeLoss_mean, timeLoss_var, alpha=EMA_ALPHA)
            z = zscore(time_loss, timeLoss_mean, math.sqrt(timeLoss_var))
            timeloss_n = -np.tanh(z)
            # Reward
            reward += factor * timeloss_n
            formula["timeLoss"] = (time_loss, float(timeloss_n));
            running_dict["timeLoss"] = timeLoss_mean, timeLoss_var
        else: formula["timeLoss"] = (time_loss, 0.0);
    # Energy consumed [average] (EMA -> Z-score -> tanh; minimize)
    if ((factor := params["reward.energyConsumed"]) != 0.0) or (params["reward.energyConsumed.monitor"]):
        energy_consumed = float(results.trip_data["energyConsumed"])
        if factor != 0.0:
            enCons_mean, enCons_var = running_dict["energyConsumed"]
            # EMA -> Z-score -> tanh
            enCons_mean, enCons_var = ema_welford(energy_consumed, enCons_mean, enCons_var, alpha=EMA_ALPHA)
            z = zscore(energy_consumed, enCons_mean, math.sqrt(enCons_var))
            enrgcons_n = -np.tanh(z)
            # Reward
            reward += factor * 0.0
            formula["energyConsumed"] = (energy_consumed, float(enrgcons_n));
            running_dict["energyConsumed"] = enCons_mean, enCons_var
        else: formula["energyConsumed"] = (energy_consumed, 0.0);
    formula["reward"] = (float(reward), 0.0)
    return reward
def runSimulation(network_name, G, stations, base_trips, params, results, iteration=None, debug=False):
    trips = copy.deepcopy(base_trips)
    output_subfolder = "solo";
    if iteration != None: output_subfolder += "_" + str(iteration);
    results = sumoSoloRun(base_net, G, data_path, network_name, trips, results, stations,
                          output_path=output_path, output_subfolder=output_subfolder,
                          params=params, debug=debug)
    return results
        


###### SETTINGS
## Training
edge_attr_list = ["travelTime", "vehicles", "flow", "vaporized", "charged"]
edge_attr_map = dict(zip(edge_attr_list, [i for i in range(len(edge_attr_list))]))

###### INITIALIZATION
# Torch init
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
# GNN utility
gnnutil.initialize(edge_attr_list, edge_attr_map, device)


if __name__ == "__main__":
    # Parse arguments
    if len(sys.argv) < 2: network_name = "manhattan";
    else: network_name = str(sys.argv[1]);
    # Adjust params
    params = Parameters.config()
    # Load params
    VEHICLE_COUNT = params["sim.vehicleCount"]
    #MAX_DURATION = params["sim.maxDuration"]
    #DURATION_SET = MAX_DURATION > 0
    DESTINATION_COUNT_DIST = params["sim.destinationCountDistribution"]
    MIN_DISTANCE = params["sim.minDistance"]
    MAX_DISTANCE = params["sim.maxDistance"]
    if params["sim.visualize"]:
        print("INFO: 'visualize' ignored when training.")
        params["sim.visualize"] = False
    if params["sim.printResults"]:
        print("INFO: 'printResults' ignored when training.")
        params["sim.printResults"] = False
    PRINT_ERRORS = params["sim.printErrors"]
    EV_PEN = params["electric.penetration"]
    STATION_CAPACITY = params["station.capacity"]
    K = params["station.k"]
    MONEY_PER_KWH = params["station.moneyPerKWh"]
    ITERATIONS = params["training.iterations"]
    EMA_ALPHA = params["training.coefficients.emaAlpha"];
    TEMPERATURE = float(params["training.coefficients.temperature"])
    EFFECT_ON_RUN_REWARD = float(params["training.coefficients.momentum"]);
    ENTROPY_COEFF = float(params["training.coefficients.entropyCoeff"]);
    GRAD_CLIP = float(params["training.coefficients.gradClip"]);
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
    # Traci switch
    #traciutil.initialize(True)
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
    print("Graph:    " + str(base_G) + "\nDetailed: " + str(base_G_d) + "\n");
    num_nodes = base_G.number_of_nodes()
    # Detailed graph for coverage calculations
    global coverage_G_d
    coverage_G_d = graphing.netToDetailedGraph(data_path + "/base_net.net.xml", add_road_centers=True)
    # Edge translator
    translator = GraphTranslator(base_G)
    ## PyG Data
    # Edge index
    edge_index = translator.getEdgeIndexArray()
    edge_index = torch.as_tensor(edge_index, dtype=torch.int, device=device)
    # Pos
    pos = nx.get_node_attributes(base_G, "pos")
    pos = translator.dictToNodePos(pos)
    pos = torch.as_tensor(pos, dtype=torch.float32, device=device)
    # Create
    graph = Data(num_nodes=num_nodes,edge_index=edge_index, pos=pos)
    if graph.x == None:
        graph.x = torch.ones(num_nodes, 1, dtype=torch.float32)
    # Edge attributes
    edge_attr = np.zeros((graph.edge_index.shape[1], len(edge_attr_list)))
    gnnutil.applyBaseGraphEdgeAttributes(graph, base_G, translator, ["travelTime"])
    ## Other
    global network_diameter, coverage_radius_target, charge_max_eval
    network_diameter = float(nx.diameter(base_G, weight="length"))
    coverage_radius_target = network_diameter / np.sqrt(K)
    gnnutil.setMaxCoverageRadius(network_diameter)
    if MIN_DISTANCE < 0:
        MIN_DISTANCE = abs(MIN_DISTANCE * network_diameter)
    if MAX_DISTANCE < 0:
        MAX_DISTANCE = abs(MAX_DISTANCE * network_diameter)
    
###### PRE-RUN
    # Datetime now (file organization)
    start_datetime_str = str(datetime.now().strftime('%Y%m%d_%H%M%S'))
    output_folder = network_name + "_gnn_" + start_datetime_str
    output_path = output_path + "/" + output_folder
    pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
    pathlib.Path(output_path + "/training").mkdir(parents=True, exist_ok=True)
    # Generate trips for the whole training session
    base_trips = tripsGen.main(base_net, base_G, VEHICLE_COUNT, output_path + "/trips.xml",
                               destination_count_probs=DESTINATION_COUNT_DIST,
                               #min_distance_per_des=(network_diameter / 4.0),
                               min_distance=MIN_DISTANCE, #network_diameter*0.5,
                               max_distance=MAX_DISTANCE, #network_diameter*2.0,
                               ev_pen=EV_PEN)
    average_trip_len = base_trips.averageTripLen()
    # Prepare results
    results = Evaluation(translator)
    #### Run blank simulation once with conventional vehicles for statistics
    # Prepare files
    #prep.copyFile(data_path + "/base_net.net.xml", data_path + "/net.net.xml")
    #prep.copyFile(output_path + "/trips.xml", data_path + "/routes.xml")
    ## Run
    results = sumoBlankRun(base_net, data_path, network_name, base_trips, results, params=params,
                           output_path=output_path, output_subfolder="blank")
    ## Update graph (Data)
    graph = gnnutil.applyResultsToGraph(graph, translator, ["vehicles", "flow"], results)


###### TRAINING
    #### Preprocess
    graph = graph.to(device)
    model = EdgePosGNN(graph.x.shape[1], graph.edge_attr.shape[1], 64) #EdgeGNN
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    # Reward side variables
    run_reward = None;
    global running_dict
    running_dict = gnnutil.initializeRunningDict();
    # Progress printing
    if PRINTS > 0: print_every = int(ITERATIONS / PRINTS);
    else: print_every = 0;
    if PROGRESS_WRITE:
        f = open(output_path + "/training/progress.txt", "w"); f.close();
        #f = open(output_path + "/training/best.xml", "w"); f.close()
        best_tree = ET.ElementTree(ET.fromstring("<best></best>"))
    if MEASURE_TIME:
        eval_time = 0.0; rewardcalc_time = 0.0; envupdate_time = 0.0;
    # Monitor training results
    global train_results
    train_results = gnnutil.initializeResultsDict(params, ITERATIONS, K)
    best = gnnutil.initializeBestDict(params)
    #### Loop
    pbar = tqdm(total=ITERATIONS)
    iteration = 0
    sim_tries = 0
    best_modified = {}
    training_stime = time.perf_counter();
    while iteration < ITERATIONS:
        model.train()
        optimizer.zero_grad()

        #### 1. Get edge scores and probability
        # x: [junctions, features], edge_index: [2, roads], edge_attr: [roads, features]
        logits = model(graph.x, graph.edge_index, graph.edge_attr, graph.pos)
        if TEMPERATURE > 0.0:
            logits = logits / TEMPERATURE
        probs = torch.softmax(logits, dim=0)
        log_probs = torch.log(probs + 1e-10)
        entropy = -(probs * log_probs).sum(dim=-1).mean()

        #### 2. Select k edges
        # Sampling (multinomial)
        selected_indices_t = torch.multinomial(probs, num_samples=K, replacement=False)
        sel_log_probs = gnnutil.calculate_log_probs(logits, selected_indices_t)
        selected_edge_indices = selected_indices_t.tolist()
        selected_edges = [translator.indexToEdge(sei) for sei in selected_edge_indices]
        selected_edge_ids = [translator.edgeToID(edge) for edge in selected_edges]
        # Transform to stations
        stations = []
        for edge in selected_edge_ids: stations.append(StationInfo(edge, STATION_CAPACITY, MONEY_PER_KWH));
        stations = StationInfoDataset(stations)
        # Check if double
        if len(selected_edge_indices) != len(set(selected_edge_indices)):
            print("ERROR: One edge selected twice:", selected_edge_indices, "->", stations.listEdges())

        #### 3. Run evaluation
        if sim_tries > 10:
            raise Exception(f"Simulation failed 10 times in a row at iteration {iteration+1} for stations: {stations.listEdges()}.")
        last_results = results
        if (iteration == 1): params["prep.preprocess"] = False;
        if MEASURE_TIME: sim_stime = time.perf_counter();
        results = Evaluation(translator)
        try:
            results = runSimulation(network_name, base_G, stations, base_trips,
                                    params, results, iteration, debug=False)
            sim_tries = 0
        except Exception as e:
            # Very rarely crashes when setting stop for charging - WIP
            if PRINT_ERRORS:
                print(f"WARNING: Simulation failed at iteration {iteration+1} for stations {stations.listEdges()}:")
                traceback.print_tb(e.__traceback__)
                print(e)
            sim_tries += 1
            traci.close()
            continue
        if MEASURE_TIME:
            sim_etime = time.perf_counter();
            eval_time += sim_etime - sim_stime;

        #### 4. Calcualte reward
        if MEASURE_TIME: sim_stime = time.perf_counter();
        formula = {}
        reward = rewardFunction(stations, results, params, formula)
        gnnutil.updateResultsDict(train_results, stations, formula, iteration)
        best_modified = gnnutil.updateBestDict(best, stations.listEdges(), formula, modified=best_modified)
        # Running reward/advantage
        if EFFECT_ON_RUN_REWARD > 0.0:
            if run_reward == None: run_reward = reward;
            advantage = float(reward - run_reward)
            run_reward = ((1 - EFFECT_ON_RUN_REWARD) * run_reward) +\
                         (EFFECT_ON_RUN_REWARD * reward)
        else:
            advantage = reward
        if MEASURE_TIME:
            sim_etime = time.perf_counter();
            rewardcalc_time += sim_etime - sim_stime;
            

        # 5. Policy Gradient Update
        # Entropy loss for exploration
        entropy_loss = -ENTROPY_COEFF * entropy
        # Loss; minimize negative to maximize reward
        #  Mean
        #loss = (-sel_log_probs * advantage).mean();
        #  Normalized by sqrt
        loss = (-sel_log_probs.sum() * advantage) / np.sqrt(K)
        loss += entropy_loss;
        # Backprop
        loss.backward()
        # Gradient clipping
        if GRAD_CLIP > 0.0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP)
        # Step
        optimizer.step()

        # 6. Update environment
        if MEASURE_TIME: sim_stime = time.perf_counter();
        graph = gnnutil.applyResultsToGraph(graph, translator, ["vehicles", "flow", "vaporized", "charged"], results)
        if MEASURE_TIME:
            sim_etime = time.perf_counter();
            envupdate_time += sim_etime - sim_stime;

        iteration += 1
        pbar.update(1)
        
        # Debug
        if print_every > 0 and (iteration + 1) % print_every == 0:
            s = f"> {(iteration + 1):5d} / {ITERATIONS}:\n"
            s += "  chosen: " + str(selected_edge_indices) + "\n"
            #s += f"  flow:   {flow:10.4f}  | {max_flow}\n";
            s += f"  reward: {reward:7.2f}  | {run_reward:0.2f}\n";
            s += "  loss: " + str(loss.item()) + "\n"
            #s += " " + str(len(set(selected_edge_indices).intersection(set(max_inds)))) + "/" + str(K) + "\n"
            if MEASURE_TIME:
                avg_eval_time = eval_time / (iteration + 1)
                avg_reward_time = rewardcalc_time / (iteration + 1)
                avg_envupdate_time = envupdate_time / (iteration + 1)
                s += f"  average part durations:\n"
                s += f"    evaluation:          {round(avg_eval_time, 2)}\n"
                s += f"    reward calculation:  {round(avg_reward_time, 2)}\n"
                s += f"    env update:          {round(avg_envupdate_time, 2)}\n"
            s += "\n"
            s += str(formula) + "\n"
            if PROGRESS_PRINT: print(s);
            if PROGRESS_WRITE:
                # Write in progress log
                with open(output_path + "/training/progress.txt", "a") as f:
                    f.write(s)
                    f.write(str(results))
                    f.write("\n")
                # Write best
                gnnutil.updateBestTree(best_tree, best, best_modified)
                ET.indent(best_tree, space="    ")
                best_tree.write(output_path + "/training/best.xml");
            if PROGRESS_DRAW:
                # Draw current evaluation
                plt.close()
                fig, ax = plt.subplots()
                ew_range = (0.1, 2.0)
                max_flow = max(results.edge_data["flow"].values()) / (ew_range[1] - ew_range[0])
                edge_weights = {key: ((ew_range[0] + (value / max_flow))) for key, value in results.edge_data["flow"].items()}
                graphdraw.drawEdgeWeights(base_G, edge_weights, ax=ax, default_width=0.0)
                station_weights = {si.edge_id: (results.station_data["charged"][translator.IDToEdge(si.edge_id)]) for si in stations}
                graphdraw.drawCircleStations(base_G, base_net, stations.listEdges(), fig, ax, circle_size=50, font_size=8, station_weights=station_weights)
                fig.savefig(output_path + f"/training/iteration_{(iteration + 1)}.jpg")
                plt.close(fig)
                # Draw coverage
                if "coverage" in formula:
                    fig, ax = plt.subplots()
                    graphdraw.drawCenters(coverage_G_d, stations.listDNodes(), formula["coverage"][0], ax=ax,
                                          node_size=150, node_labels=False, edge_labels=False)
                    ax.set_title(f"Radius: " + str(round(formula["coverage"][0], 2)))
                    fig.savefig(output_path + f"/training/coverage_{(iteration + 1)}.jpg")
    pbar.close()
    training_etime = time.perf_counter();
    #### Finish and save
    pathlib.Path(output_path + "/results").mkdir(parents=True, exist_ok=True)
    ## Save model
    torch.save(model.state_dict(), output_path + "/results/model.pt")
    ## Save training results
    # Write best
    gnnutil.updateBestTree(best_tree, best, best_modified)
    ET.indent(best_tree, space="    ")
    best_tree.write(output_path + "/training/best.xml");
    best_tree.write(output_path + "/results/best.xml");
    # Write plot figures
    figs = gnnutil.plotTrainingResults_figs(train_results, ITERATIONS)
    for stat in figs:
        fig, ax = figs[stat]
        fig.savefig(output_path + f"/training/graph_" + stat + ".jpg")
    # Clean up files
    xmlOut.cleanCache(output_path + "/_cache", network_name)
    # Print
    full_path = pathlib.Path(output_path + "/results/").resolve()
    time_diff = training_etime - training_stime
    print(f"Training finished in {round(time_diff, 2)}, saved results inside\n'{full_path}'")
    # Show training results
    plt.show()











"""
# "edge_attrs" middleman variable (OBSOLETE)
def extractEdgeAttrs(G, edge_stats, edge_data):
    edge_attrs = {"vehicles" : {}, "flow" : {}, "vaporized" : {}}
    ids = nx.get_edge_attributes(G, "id")
    for edge in G.edges():
        edge_id = ids[edge]
        stats = edge_stats.get(edge_id, {"vehicles" : 0, "flow" : 0.0})
        edge_attrs["vehicles"][edge] = stats["vehicles"]
        edge_attrs["flow"][edge] = stats["flow"]
        data = edge_data.get(edge_id, {"entered" : 0, "vaporized" : 0})
        edge_attrs["vaporized"][edge] = data["vaporized"]
    return edge_attrs
def applyEdgeAttributes(G, edge_attrs):
    nx.set_edge_attributes(G, edge_attrs["vehicles"], "vehicles")
    nx.set_edge_attributes(G, edge_attrs["flow"], "flow")
    nx.set_edge_attributes(G, edge_attrs["vaporized"], "vaporized")
    return G
"""
