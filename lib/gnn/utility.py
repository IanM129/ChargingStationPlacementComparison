import numpy as np
import matplotlib.pyplot as plt
import xml.etree.ElementTree as ET
import networkx as nx

import torch

import lib.xml.output as xmlout

import lib.utility as util



def initialize(attr_list, attr_map, dvc):
    global edge_attr_list, edge_attr_map, device
    edge_attr_list = attr_list
    edge_attr_map = attr_map
    device = dvc
def setMaxCoverageRadius(value):
    global max_coverage
    max_coverage = value


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
def isMinOrMax(val_name : str) -> int:
    match (val_name):
        case "totalCoverage" | "coverage" | "simDuration" | "tripDuration" |\
             "tripLength" | "waitTime" | "stopTime" | "timeLoss":
            return -1; # -> minimize
        case "reward":
            return 1; # -> maximize
        case _: # totalCharge, charge
            return 0; # -> maximize from zero (0)
def createEdgeAttrUpdateList(attr_update, attr_list):
    return [(a if (a in attr_update) else None) for a in attr_list]

#### Main
##def formEdgeAttributes(vals : dict, num_edges : int=0, keys : list[str]=None):
##    if num_edges < 1: num_edges = len(vals[keys[0]]);
##    if keys == None: keys = vals.keys();
##    edges = list(vals[keys[0]].values())
##    edge_attr = torch.tensor(
##        [[vals[k][edges[i]] for k in keys] for i in range(num_edges)],
##        #[list(vals[k].values()) for k in keys],
##        dtype=torch.float
##    )
##    return edge_attr
## Edge attributes
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
                #train_results[p]["_red"] = np.zeros(iteration_count)
                #train_results[p]["_blue"] = np.zeros(iteration_count)
        train_results["generalReward"] = np.zeros(iteration_count)
        train_results["reward"] = np.zeros((agent_count, iteration_count))
        #train_results["reward"]["_general"] = np.zeros(iteration_count)
        #train_results["reward"]["_red"] = np.zeros(iteration_count)
        #train_results["reward"]["_blue"] = np.zeros(iteration_count)
        train_results["price"] = np.zeros((agent_count, iteration_count))
        train_results["stations"] = np.empty((agent_count, iteration_count, K), dtype=str)
    else:
        train_results["reward"] = np.zeros(iteration_count)
        #train_results["price"] = np.zeros(iteration_count)
        train_results["stations"] = np.empty(iteration_count, dtype=str)
    return train_results
def initializeBestDict(params, competitive=False):
    if competitive: group_name = "compReward";
    else: group_name = "reward";
    best = {}
    for p in params.groups[group_name]:
        if params[group_name + "." + p + ".monitor"] == True:
            m = isMinOrMax(p);
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
def updateResultsDict(train_results, stations, formula, iteration):
    for p in train_results:
        if p == "stations":
            train_results[p][iteration] = stations.listEdges();
        else:
            train_results[p][iteration] = formula[p][0];
def updateResultsDict_comp(train_results, stations, formula_general, formulas, iteration):
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
        m = isMinOrMax(p)
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


#### Plotting
def getPlotMetadata(stat):
    data = {"title": "",
            "unit" : "",
            "label": "Total"}
    match (stat):
        case "totalCoverage" | "coverage":
            data["title"] = "Coverage radius"
            if stat == "totalCoverage": data["title"] += " (Total)";
            data["unit"] = "Meters (m)"
            data["label"] = "Global"
            global max_coverage
            if max_coverage is not None:
                data["title"] += f" [max {max_coverage:0.2f} m]";
        case "totalCharge" | "charge":
            data["title"] = "Charge"
            if stat == "totalCharge": data["title"] += " (Total)";
            data["unit"] = "Watt hours (Wh)"
        case "simDuration":
            data["title"] = "Simulation duration"
            data["unit"] = "Seconds (s)"
        case "tripDuration":
            data["title"] = "Trip duration (average)"
            data["unit"] = "Seconds (s)"
        case "tripLength":
            data["title"] = "Trip length (average)"
            data["unit"] = "Meters (m)"
        case "waitTime":
            data["title"] = "Watiting time (average)"
            data["unit"] = "Seconds (s)"
        case "stopTime":
            data["title"] = "Stopped time (average)"
            data["unit"] = "Seconds (s)"
        case "timeLoss":
            data["title"] = "Time lost (average)"
            data["unit"] = "Seconds (s)"
        case "energyConsumed":
            data["title"] = "Energy consumed (average)"
            data["unit"] = "Watt hours (Wh)"
        case "totalMoneyEarned" | "moneyEarned":
            data["title"] = "Money earned"
            if stat == "totalMoneyEarned": data["title"] += " (Total)";
            data["unit"] = "Euro (€)"
        case "price":
            data["title"] = "Charge price"
            data["unit"] = "Euro (€) per kWh"
        case "reward" | "generalReward":
            data["title"] = "Reward"
            data["label"] = ""
    return data
def createPlotFigure(metadata):
    fig = plt.figure()
    # Set integer X line
    ax = fig.gca()
    ax.xaxis.get_major_locator().set_params(integer=True)
    # Set metadata
    fig.suptitle(metadata["title"])
    ax.set_ylabel(metadata["unit"])
    ax.set_xlabel("Iteration")
    return (fig, ax)
def combineFigures(axes, metadata):
    fig, ax = createPlotFigure(metadata)
    lines = []
    for ax_og in axes:
        for og_line in ax_og.lines:
            x = og_line.get_xdata(); y = og_line.get_ydata();
            label=og_line.get_label();
            if "agent" not in label:
                color = "black"
            else:
                color = label.split(' ', 1)[0].lower();
            line = ax.plot(x, y, color=color, label=label)
            if isinstance(line, list): lines.extend(line);
            else: lines.append(line);
    ax.legend(handles=lines)
    return (fig, ax)
def plotTrainingResults_figs(train_results, iterations, agent_colors=[]):
    figs = {}
    x = np.arange(0, iterations)
    for stat in train_results:
        if stat == "stations": continue;
        metadata = getPlotMetadata(stat)
        data = train_results[stat]
        if len(data.shape) > 1:
            fig, ax = createPlotFigure(metadata)
            handles = []
            for a in range(len(data)):
                line, = ax.plot(x, data[a], agent_colors[a], label=agent_colors[a].capitalize() + " agent")
                handles.append(line)
                #metadata_c = metadata.copy()
                #match (color):
                #    case "_general":
                #        line, = ax.plot(x, data[color], "g", label="Total")
                #        handles.append(line)
                #        #clr_title = "Total";
                #    case "_red":
                #        line, = ax.plot(x, data[color], "r", label="Red agent")
                #        handles.append(line)
                #        #clr_title = r"\textcolor{red}{Red}";
                #    case "_blue":
                #        line, = ax.plot(x, data[color], "b", label="Blue agent")
                #        handles.append(line)
                #        #clr_title = r"\textcolor{red}{Blue}";
                #metadata_c["title"] += " (" + clr_title + ")";
            ax.legend(handles=handles)
            figs[stat] = (fig, ax)
        else:
            fig, ax = createPlotFigure(metadata)
            ax.plot(x, data, label=metadata["label"])
            figs[stat] = (fig, ax)
    return figs
