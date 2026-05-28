import numpy as np
import matplotlib.pyplot as plt
import xml.etree.ElementTree as ET

import torch

import lib.xml.output as xmlout


#### Training dictionaries
## Init
def initializeResultsDict(params, iteration_count):
    res_dict = {}
    for p in params.groups["reward"]:
        if params["reward." + p + ".monitor"] == True:
            res_dict[p] = np.zeros(iteration_count)
    res_dict["reward"] = np.zeros(iteration_count)
    return res_dict
def initializeBestDict(params):
    best = {}
    for p in params.groups["reward"]:
        if params["reward." + p + ".monitor"] == True:
            match (p):
                case "coverage" | "simDuration" | "tripDuration" | "tripLength" |\
                "waitTime" | "stopTime" | "timeLoss":
                    best[p] = (np.inf, None)
                case "reward":
                    best[p] = (-np.inf, None)
                case _: # charge
                    best[p] = (0.0, None)
    return best
## Update
def updateResultsDict(train_results, formula, iteration):
    for p in train_results:
        train_results[p][iteration] = formula[p][0];
    #return train_results
def updateBestDict(best, station_edges, formula, modified=None):
    if not modified: modified = set();
    result = {}
    for p in formula:
        result[p] = formula[p][0]
    result["stations"] = station_edges
    for p in best:
        value = formula[p][0]
        cur = best[p][0]
        match (p):
            case "coverage" | "simDuration" | "tripDuration" | "tripLength" |\
                "waitTime" | "stopTime" | "timeLoss":
                if value < cur:
                    best[p] = (value, result.copy()); modified.add(p);
            case _: # charge, reward
                if value > cur:
                    best[p] = (value, result.copy()); modified.add(p);
    return modified
## Write
def updateBestTree(best_tree, best : dict, modified : set = None):
    if not modified: modified = best.keys();
    root = best_tree.getroot()
    for p in modified:
        el = root.find(p)
        if el == None: el = ET.SubElement(root, p);
        xmlout.dictToElement(best[p][1], root=el)
    return
    

def formEdgeAttributes(vals : dict, num_edges : int=0, keys : list[str]=None):
    if num_edges < 1: num_edges = len(vals[keys[0]]);
    if keys == None: keys = vals.keys();
    edges = list(vals[keys[0]].values())
    edge_attr = torch.tensor(
        [[vals[k][edges[i]] for k in keys] for i in range(num_edges)],
        #[list(vals[k].values()) for k in keys],
        dtype=torch.float
    )
    return edge_attr



def getPlotMetadata(stat):
    data = {}
    match (stat):
        case "coverage":
            data["title"] = "Coverage radius"
            data["unit"] = "Meters (m)"
        case "charge":
            data["title"] = "Total charge"
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
        case "reward":
            data["title"] = "Reward"
            data["unit"] = ""
    return data


def plotTrainingResults_figs(train_results, iterations):
    figs = {}
    x = np.arange(0, iterations)
    for stat in train_results:
        metadata = getPlotMetadata(stat)
        fig = plt.figure()
        # Set integer X line
        ax = fig.gca()
        ax.xaxis.get_major_locator().set_params(integer=True)
        # Set metadata
        fig.suptitle(metadata["title"])
        ax.set_ylabel(metadata["unit"])
        ax.set_xlabel("Iteration")
        # Plot
        ax.plot(x, train_results[stat])
        figs[stat] = (fig, ax)
    return figs
def plotTrainingResults_axes(train_results, iterations):
    fig, axs = plt.subplots(len(train_results.keys()))
    fig.suptitle("Iterations: " + str(iterations))
    x = np.arange(0, iterations)
    i = 0
    for stat in train_results:
        metadata = getPlotMetadata(stat)
        axs[i].set_title(metadata["title"])
        axs[i].plot(x, train_results[stat])
        i += 1
    return fig, axs
