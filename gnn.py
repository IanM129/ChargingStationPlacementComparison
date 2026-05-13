from datetime import datetime
import random
import pathlib
import sumolib
import networkx as nx
import copy
import numpy as np
from tqdm import tqdm

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Multinomial
from torch_geometric.nn import GCNConv
from torch_geometric.utils import from_networkx as torch_from_networkx

#from lib.gnn.env import ChargingEnv
from lib.gnn.model1 import EdgeGNN
import lib.gnn.utility as gnnutil

import lib.visual_utility as visutil

import lib.graphing as graphing  #= lib/graphing/__init__.py
import preprocess as prep

from lib.structs.stationinfo import StationInfo, StationInfoDataset
from lib.structs.trip import Trip
from lib.structs.edge_translator import EdgeTranslator
from lib.structs.evaluation import Evaluation

import lib.xml.tripsGen as tripsGen

from lib.sumo.params import Parameters
from lib.sumo.blank import sumoBlankRun
from lib.sumo.solo import sumoSoloRun


###### FUNCTIONS
#### Utility
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
def calculate_log_probs(logits, selected_indices):
    log_probs = []
    mask = torch.ones_like(logits, dtype=torch.bool)
    for idx in selected_indices:
        # Numerator: log(exp(logit)) -> just the logit
        # Denominator: log(sum(exp(logits_remaining)))
        # We use log_sum_exp for numerical stability
        # Zero out the ones we already picked using a mask
        current_logits = logits.masked_fill(~mask, float('-inf'))
        # Log-softmax equivalent for the specific index
        log_p = logits[idx] - torch.logsumexp(current_logits, dim=0)
        log_probs.append(log_p)
        mask[idx] = False
    return torch.stack(log_probs)
#### Training environment
def getReward_flow(selected_edges, graph, iteration):
    global edge_attr_map
    flow_sum = graph.edge_attr[selected_edges, edge_attr_map["flow"]].sum().item()
    return flow_sum
def runSimulation(selected_edges, graph, G, params, edge_translator, iteration=None):
    stations = []
    for edge in selected_edges: stations.append(StationInfo(edge, STATION_CAPACITY));
    stations = StationInfoDataset(stations)
    results = Evaluation(edge_translator)
    results = sumoSoloRun(base_net, data_path, "manhattan", trips, stations, params=params, results=results,
                          output_folder=output_folder, output_subfolder="solo_" + str(iteration))
    edge_attrs = extractEdgeAttrs(G, edge_stats, edge_data)
    return results
def getReward(results, last_results):
    return results.station_data["totalCharge"] - last_results.station_data["totalCharge"]
        


###### SETTINGS
## Filesystem
filepath = "manhattan/";
data_path = filepath + "data/";
in_data_path = data_path + "manhattan";
## Simulation
vehicle_count = 100
STATION_CAPACITY = 10
ev_penetration = 0.8
## Stations
k = 3


if __name__ == "__main__":
####### LOADING
    # Graph
    base_net = sumolib.net.readNet(data_path + "/base_net.net.xml")
    G = graphing.netToGraph(data_path + "/base_net.net.xml",
                            lengths=True, travel_time=True,
                            internal_lengths=False, node_position=True)
    print(G);
    # Edge translator
    edge_trans = EdgeTranslator(base_net, G)
    # Other
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')


###### PRE-RUN
    # Datetime now (for file organization)
    start_datetime_str = str(datetime.now().strftime('%Y%m%d_%H%M%S'))
    output_folder = "output/" + start_datetime_str
    output_path = data_path + "/" + output_folder
    pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
    # Generate trips for the whole training session
    network_diameter = float(nx.diameter(G, weight="length"))
    trips = tripsGen.main(base_net, G, vehicle_count, output_path + "/trips.xml",
                          #[0, 0, 0, 0.3, 0.5, 0.2],  #4 -> 0.3; 5 -> 0.5 -> 6 -> 0.2
                          destination_count_probs=[0, 0.3, 0.5, 0.2],  #2 -> 0.3; 3 -> 0.5 -> 4 -> 0.2
                          #min_distance_per_des=(network_diameter / 4.0),
                          min_distance=network_diameter*0.5,
                          max_distance=network_diameter*2.0,
                          ev_pen=ev_penetration)
    # Prepare results
    results = Evaluation(edge_trans)
    #### Run blank simulation once with conventional vehicles for statistics
    # Adjust params
    params = Parameters.config()
    params["sim.visualize"] = False
    params["prep.saveInputs"] = False
    params["sim.saveLog"] = False
    params["sim.printResults"] = False
    print(params)
    params["prep.saveLog"] = 0.0
    print(params)
    exit()
    # Prepare files
    prep.copyFileForSimulation(data_path + "/base_net.net.xml", data_path + "/net.net.xml")
    prep.copyFileForSimulation(output_path + "/trips.xml", data_path + "/routes.xml")
    ## Run
    if True:
        results = sumoBlankRun(base_net, data_path, "manhattan", trips, results, params=params,
                                             output_folder=output_folder, output_subfolder="blank")
    else:
        stations = random.sample(base_net.getEdges(), k)
        for i in range(len(stations)): stations[i] = StationInfo(stations[i].getID(), STATION_CAPACITY);
        stations = StationInfoDataset(stations)
        print(stations)
        results = sumoSoloRun(base_net, data_path, "manhattan", trips, results, stations, params=params,
                                            output_folder=output_folder, output_subfolder="solo")
    ## Extract edge attributes
    edge_attrs = extractEdgeAttrs(G, edge_stats, edge_data)
    ## Update G
    G = applyEdgeAttributes(G, edge_attrs)
    ## PyG graph
    node_map = {node: i for i, node in enumerate(G.nodes())}
    edge_map = {edge: i for i, edge in enumerate(G.edges())}
    edge_attr_list = ["travelTime", "vehicles", "flow", "vaporized"]
    edge_attr_map = dict(zip(edge_attr_list, [i for i in range(len(edge_attr_list))]))
    graph = torch_from_networkx(G,
                    group_node_attrs=["pos"],
                    group_edge_attrs=edge_attr_list)
    print(graph)

    # Calculate max possible flow (brute force)
    max_flow = 0.0
    flows = [graph.edge_attr[i, edge_attr_map["flow"]].sum().item() for i in range(graph.num_edges)]
    max_inds = []
    for i in range(k):
        mind = int(np.argmax(flows))
        max_flow += flows[mind]
        flows[mind] = 0.0
        max_inds.append(mind)
    print("max flow indeces:", max_inds)


###### TRAINING
    #### Preprocess
    graph.to(device)
    model = EdgeGNN(graph.x.shape[1], graph.edge_attr.shape[1], 64)
    model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    run_reward = None; effect_on_run_reward = 0.1;
    #### Loop
    for iteration in tqdm(range(10000)):        #for iteration in range(10000):
        model.train()
        optimizer.zero_grad()

        # 2. Get edge scores from your GNN
        # x: [intersections, features], edge_index: [2, roads], edge_attr: [roads, features]
        logits = model(graph.x, graph.edge_index, graph.edge_attr)

        # 3. Convert scores to a probability distribution over edges
        probs = torch.softmax(logits, dim=0)

        # 4. Agent selects 'n' edges (hubs) based on probabilities
        # Sampling (multinomial)
        selected_indices_t = torch.multinomial(probs, num_samples=k, replacement=False)
        log_probs = calculate_log_probs(logits, selected_indices_t) #m.log_prob()
        selected_edge_indices = selected_indices_t.tolist()
        selected_edges = [(e[0], e[1]) for e in edges_arr[selected_edge_indices]]
        selected_edge_ids = [edge_to_id_map[edge] for edge in selected_edges]

        # 5. Run evaluation
        last_results = results
        results = runSimulation(selected_edge_ids, graph, G, params, edge_translator, iteration)

        # 5. Environment Reward        
        flow = getReward(results, last_results)
        reward = flow
        if run_reward == None: run_reward = reward;
        else:
            run_reward = ((1 - effect_on_run_reward) * run_reward) +\
                         (effect_on_run_reward * reward)
        advantage = reward - run_reward
            

        # 6. Policy Gradient Update
        # Loss = -log_prob * reward (we minimize negative to maximize reward)
        loss = -(log_probs.sum()) * advantage;  #-torch.stack(log_probs).mean() * reward

        loss.backward()
        optimizer.step()

        if iteration % 100 == 0:
            print(iteration)
            print("  chosen:", selected_edge_indices)
            print(f"  flow:   {flow:10.4f}  | {max_flow}")
            print(f"  reward: {reward:7.2f}  | {run_reward:0.2f}")
            print("  loss: ", loss.item())
            print(" ", len(set(selected_edge_indices).intersection(set(max_inds))), "/", k)
            print()




    
