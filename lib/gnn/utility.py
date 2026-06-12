import random
import copy
import numpy as np
import matplotlib.pyplot as plt
import xml.etree.ElementTree as ET
import networkx as nx

import torch
from torch.distributions import Multinomial, Beta
from torch_geometric.data import Data

import lib.graphing as graphing  #= lib/graphing/__init__.py
import preprocess as prep

import lib.xml.output as xmlout

import lib.utility as util

#from lib.structs.stationinfo import StationInfo, StationInfoDataset
from lib.structs.trip import Trip
from lib.structs.graphtranslator import GraphTranslator
from lib.structs.evaluation import Evaluation
#from lib.structs.params import Parameters

import sumolib
from lib.sumo.blank import sumoBlankRun
from lib.sumo.solo import sumoSoloRun
from lib.sumo.comp import sumoCompRun



def initialize(attr_list, attr_map, dvc):
    global edge_attr_list, edge_attr_map, device
    edge_attr_list = attr_list
    edge_attr_map = attr_map
    device = dvc


#### Utility
def calculate_log_probs(logits, selected_indices):
    log_probs = []
    mask = torch.ones_like(logits, dtype=torch.bool)
    for idx in selected_indices:
        current_logits = logits.masked_fill(~mask, float('-inf'))
        # Log-softmax equivalent for the specific index
        log_p = logits[idx] - torch.logsumexp(current_logits, dim=0)
        log_probs.append(log_p)
        mask[idx] = False
    return torch.stack(log_probs)
def createEdgeAttrUpdateList(attr_update, attr_list):
    return [(a if (a in attr_update) else None) for a in attr_list]

###### Main
#def formEdgeAttributes(vals : dict, num_edges : int=0, keys : list[str]=None):
#    if num_edges < 1: num_edges = len(vals[keys[0]]);
#    if keys == None: keys = vals.keys();
#    edges = list(vals[keys[0]].values())
#    edge_attr = torch.tensor(
#        [[vals[k][edges[i]] for k in keys] for i in range(num_edges)],
#        #[list(vals[k].values()) for k in keys],
#        dtype=torch.float
#    )
#    return edge_attr
#### Update graph 
# From edge attributes
def applyBaseGraphEdgeAttributes(graph, G, translator, attrs):
    global edge_attr_list, edge_attr_map
    num_features = len(edge_attr_list)
    new_edge_attrs = np.zeros((graph.edge_index.shape[1], num_features))
    edges = translator.getEdges()
    # Apply
    for attr in attrs:
        if attr in edge_attr_map:
            attr_i = edge_attr_map[attr]
            match (attr):
                case "travelTime":
                    travelTime = nx.get_edge_attributes(G, "travelTime")
                    travelTime = [(travelTime[e]) for e in edges]
                    new_edge_attrs[:, attr_i] = travelTime;
        else:
            raise Exception(f"Unknown attribute '{attr}'")
    global device
    graph.edge_attr = torch.as_tensor(new_edge_attrs, dtype=torch.float32, device=device)
    return graph
# From results
def applyResultsToGraph(graph, translator, attrs, results):
    global edge_attr_list, edge_attr_map
    num_features = len(edge_attr_list)
    #new_edge_attrs = np.zeros((graph.edge_index.shape[1], num_features))
    edges = translator.getEdges()
    # Apply
    for attr in attrs:
        if attr in edge_attr_map:
            attr_i = edge_attr_map[attr]
            match (attr):
                # Edges
                case "vehicles":
                    vehicles = translator.dictToEdgeAttributes(results.edge_data["vehicles"], dtype=float)
                    #print("vehicles:", vehicles.shape, "\n", vehicles)
                    vehicles = torch.from_numpy(vehicles).to(graph.edge_attr.device)
                    graph.edge_attr[:, attr_i] = vehicles;
                case "flow":
                    flow = translator.dictToEdgeAttributes(results.edge_data["flow"], dtype=float)
                    #print("flow:", flow.shape, "\n", flow)
                    flow = torch.from_numpy(flow).to(graph.edge_attr.device)
                    graph.edge_attr[:, attr_i] = flow;
                case "vaporized":
                    vaporized = translator.dictToEdgeAttributes(results.edge_data["vaporized"], dtype=float)
                    #print("vaporized:", vaporized.shape, "\n", vaporized)
                    vaporized = torch.from_numpy(vaporized).to(graph.edge_attr.device)
                    graph.edge_attr[:, attr_i] = vaporized;
                # Stations
                case "charged":
                    rand_key = next(iter(results.station_data["charged"].keys()))
                    #if "_red" in results.station_data["charged"]:
                    if rand_key[0] == '_':
                        data = {}
                        for suffix in results.station_data["charged"]:
                            data = data | results.station_data["charged"][suffix]
                        #data = results.station_data["charged"]["_red"] | results.station_data["charged"]["_blue"];
                    else:
                        data = results.station_data["charged"];
                    charged = np.zeros(len(edges), dtype=float)
                    for edge in data:
                        edge_ind = translator.edgeToIndex(edge)
                        charged[edge_ind] = data[edge]
                    #print("charged:", charged.shape, "\n", charged)
                    charged = torch.from_numpy(charged).to(graph.edge_attr.device)
                    graph.edge_attr[:, attr_i] = charged;
                case "price":
                    data = {}
                    rand_key = next(iter(results.station_data["price"].keys()))
                    if rand_key[0] == '_':
                        for suffix in results.station_data["price"]:
                            for edge in results.station_data["charged"][suffix]:
                                data[edge] = results.station_data["price"][suffix]
                    else:
                        for edge in results.station_data["charged"]:
                            data[edge] = results.station_data["price"];
                    price = np.zeros(len(edges), dtype=float)
                    for edge in data:
                        edge_ind = translator.edgeToIndex(edge)
                        price[edge_ind] = data[edge]
                    #print("price:", price.shape, "\n", price)
                    price = torch.from_numpy(price).to(graph.edge_attr.device)
                    graph.edge_attr[:, attr_i] = price;
                # Other
                case _:
                    raise Exception(f"Undefined attribute '{attr}'")
        else:
            raise Exception(f"Unknown attribute '{attr}'")
    return graph


#### Simulation
def initDevice():
    global device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    return device
## Load environment
def getEdgeAttrList(competitive):
    edge_attr_list = ["travelTime", "vehicles", "flow", "vaporized", "charged"]
    if competitive: edge_attr_list.append("price");
    return edge_attr_list
def getEdgeAttrMap(edge_attr_list):
    return dict(zip(edge_attr_list, [i for i in range(len(edge_attr_list))]))
def loadEnvironment(network_name, edge_attr_list_loc):
    global edge_attr_list, edge_attr_map
    edge_attr_list = edge_attr_list_loc
    edge_attr_map = getEdgeAttrMap(edge_attr_list);
    # Folder paths (file organization)
    data_path = "networks/" + network_name + "/";
    #print("Using network '" + network_name + "' under '" + data_path + "'")
    ## Graph
    base_net = sumolib.net.readNet(data_path + "/base_net.net.xml")
    base_G = graphing.netToGraph(data_path + "/base_net.net.xml",
                                 lengths=True, travel_time=True,
                                 internal_lengths=True, node_position=True)
    base_G_d = graphing.netToDetailedGraph(data_path + "/base_net.net.xml")
    print("Graph:    " + str(base_G) + "\nDetailed: " + str(base_G_d) + "\n");
    num_nodes = base_G.number_of_nodes()
    # Detailed graph for coverage calculations
    #global coverage_G_d
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
        graph.x = torch.ones(num_nodes, 1, dtype=torch.float32, device=device)
    graph.to(device)
    # Edge attributes
    edge_attr = np.zeros((graph.edge_index.shape[1], len(edge_attr_list)))
    applyBaseGraphEdgeAttributes(graph, base_G, translator, ["travelTime"])
    return graph, base_net, base_G, base_G_d, coverage_G_d, translator
## Models
def getAgentSuffixes(agent_colors):
    return [("_" + n) for n in agent_colors]
def EdgePosGNN_chooseEdges(model, graph, K):
    #### 1. Model forward
    # Get edge scores and probability
    # x: [junctions, features], edge_index: [2, roads], edge_attr: [roads, features]
    logits = model(graph.x, graph.edge_index, graph.edge_attr, graph.pos)
    #### 2. Sample edges
    sel_probs = torch.softmax(logits, dim=0)
    # Select K edges - sampling (multinomial)
    selected_indices_t = torch.multinomial(sel_probs, num_samples=K, replacement=False)
    selected_edge_indices = selected_indices_t.tolist()
    #selected_edge_ids = [translator.indexToID(sei) for sei in selected_edge_indices]
    return selected_edge_indices
def EdgePosAndPriceGNN_chooseEdgesAndPrice(model, graph, K):
     #### 1. Model forward
    # Get edge scores and probability, and price distribution parameters
    # x: [junctions, features], edge_index: [2, roads], edge_attr: [roads, features]
    logits, price_alpha, price_beta = model(graph.x, graph.edge_index, graph.edge_attr, graph.pos)
    #### 2. Sample edges and price
    ## Edge sampling
    sel_probs = torch.softmax(logits, dim=0)
    # Select K edges - sampling (multinomial)
    selected_indices_t = torch.multinomial(sel_probs, num_samples=K, replacement=False)
    selected_edge_indices = selected_indices_t.tolist()
    #selected_edge_ids = [translator.indexToID(sei) for sei in selected_edge_indices] #[translator.edgeToID(edge) for edge in selected_edges]
    ## Price sampling
    # Price decision distribution
    price_dist = Beta(price_alpha, price_beta)
    unit_price = price_dist.rsample()
    #price = (MIN_PRICE + (unit_price * (MAX_PRICE - MIN_PRICE)))
    #price = price.detach().item()
    unit_price = unit_price.detach().item()
    return selected_edge_indices, unit_price
## Run simulation
def runSimulation_blank(network_name, data_path, output_path, net, trips, params, results):
    results = sumoBlankRun(net, data_path, network_name, trips, results, params=params,
                           output_path=output_path, output_subfolder="blank")
    return results
def runSimulation_solo(network_name, data_path, output_path,
                       net, G, stations, base_trips, charge_data, coverage_G_d, 
                       params, results, iteration=None, debug=False):
    trips = copy.deepcopy(base_trips)
    output_subfolder = "solo";
    if iteration != None: output_subfolder += "_" + str(iteration);
    results = sumoSoloRun(net, G, data_path, network_name, trips, stations, results,
                          output_path=output_path, output_subfolder=output_subfolder,
                          charge_data=charge_data, coverage_G_d=coverage_G_d, params=params, debug=debug)
    return results
def runSimulation_comp(network_name, data_path, output_path,
                       net, G, stations, all_stations, prices, base_trips, charge_data, coverage_G_d,
                       params, results, iteration=None, debug=False, agent_colors=None):
    trips = copy.deepcopy(base_trips)
    output_subfolder = "comp";
    if iteration != None: output_subfolder += "_" + str(iteration);
    results = sumoCompRun(net, G, data_path, network_name, trips, stations, all_stations,
                          results, output_path, output_subfolder=output_subfolder,
                          charge_data=charge_data, prices=prices,
                          agent_colors=agent_colors, coverage_G_d=coverage_G_d,
                          params=params, debug=debug)
    return results


###### Bookkeeping
#### Training dictionaries
## Init
def initializeResultsDict(params, iteration_count, K, agent_count=1):
    train_results = {}
    for p in params.groups["reward"]:
        if params["reward." + p + ".monitor"] == True:
            train_results[p] = np.zeros(iteration_count)
    if agent_count > 1:
        for p in params.groups["compReward"]:
            if params["compReward." + p + ".monitor"] == True:
                train_results[p] = np.zeros((agent_count, iteration_count))
        train_results["generalReward"] = np.zeros(iteration_count)
        train_results["reward"] = np.zeros((agent_count, iteration_count))
        train_results["price"] = np.zeros((agent_count, iteration_count))
        train_results["stations"] = np.empty((agent_count, iteration_count, K), dtype=np.dtypes.StringDType())
        train_results["loss"] = np.empty((agent_count, iteration_count))
    else:
        train_results["reward"] = np.zeros(iteration_count)
        train_results["stations"] = np.empty((iteration_count, K), dtype=np.dtypes.StringDType())
        train_results["loss"] = np.empty(iteration_count)
    return train_results
def initializeBestDict(params, competitive=False):
    if competitive: group_name = "compReward";
    else: group_name = "reward";
    best = {}
    for p in params.groups[group_name]:
        if params[group_name + "." + p + ".monitor"] == True:
            m = util.isMinOrMax(p);
            match (m):
                case -1: best[p] = (np.inf, None);
                case 1: best[p] = (-np.inf, None);
                case _: best[p] = (0.0, None);
    return best
def initializeRunningDict(suffixes=[]):
    d = {}
    general = {"totalCharge", "simDuration", "tripDuration", "waitTime",
               "stopTime", "timeLoss", "energyConsumed"}
    for n in general:
        d[n] = (None, None);
    if len(suffixes) > 0:
        comp_list = {"coverage", "charge", "moneyEarned"}
        for n in comp_list:
            d[n] = {}
            for suffix in suffixes:
                d[n][suffix] = (None, None);
            #d[n]["_red"] = (None, None); d[n]["_blue"] = (None, None);
    return d
## Update
# Dictionary
def updateResultsDict(train_results, stations, loss, formula, iteration):
    for p in train_results:
        if p == "stations":
            train_results[p][iteration] = stations.listEdges();
        elif p == "loss":
            train_results[p][iteration] = loss
        else:
            train_results[p][iteration] = formula[p][0];
def updateResultsDict_comp(train_results, stations, losses, formula_general, formulas, iteration):
    for p in train_results:
        #if p == "reward":
        #      train_results[p]["_general"][iteration] = formula[p][0]
        #      train_results[p]["_red"][iteration] = formula_r[p][0]
        #      train_results[p]["_blue"][iteration] = formula_b[p][0]
        #elif isinstance(train_resulst[p], dict):
        #    train_results[p]["_red"][iteration] = formula_r[p][0];
        #    train_results[p]["_blue"][iteration] = formula_b[p][0];
        if p == "stations":
            for a in range(len(train_results[p])):
                train_results[p][a][iteration] = stations[a].listEdges()
        elif p == "generalReward":
            train_results[p][iteration] = formula_general["reward"][0]
        elif p == "loss":
            for a in range(len(train_results[p])):
                train_results[p][a][iteration] = losses[a];
        elif len(train_results[p].shape) > 1:
            for a in range(len(train_results[p])):
                train_results[p][a][iteration] = formulas[a][p][0];
        else:
            train_results[p][iteration] = formula_general[p][0];
    return
def updateBestDict(best, station_edges, formula, prices=None, modified=None):
    if not modified: modified = set();
    result = {}
    for p in formula:
        result[p] = formula[p][0]
    result["stations"] = station_edges
    if prices is not None:
        result["prices"] = prices
    for p in best:
        value = formula[p][0]
        cur = best[p][0]
        m = util.isMinOrMax(p)
        if m == -1:
            if value < cur:
                best[p] = (value, result.copy()); modified.add(p);
        else:
            if value > cur:
                best[p] = (value, result.copy()); modified.add(p);
    return modified
# XML tree
def updateBestTree(best_tree, best : dict, modified : set = None):
    if not modified: modified = best.keys();
    root = best_tree.getroot()
    for p in modified:
        el = root.find(p)
        if el == None: el = ET.SubElement(root, p);
        xmlout.dictToElement(best[p][1], root=el)
    return
def updateBestTree_comp(best_tree, best : dict, modified : set = None):
    #util.prettyPrintDict(best)
    if not modified: modified = best.keys();
    root = best_tree.getroot()
    for r in modified:
        parent = root.find(r)
        if parent == None: parent = ET.SubElement(root, r);
        for p in modified[r]:
            el = parent.find(p)
            if el == None: el = ET.SubElement(parent, p);
            xmlout.dictToElement(best[r][p][1], root=el)
    return
