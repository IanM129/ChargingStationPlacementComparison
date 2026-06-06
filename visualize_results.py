import os
import pathlib
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt

from lib.structs.params import Parameters

import lib.visual_utility as visutil

import lib.xml.output as xmlOut


RESULTS_PATH = pathlib.Path("results/")


def isValidModelFolder(folder, parent_folder="results"):
    if not pathlib.Path(parent_folder + "/" + folder).exists(): return 1;
    if not pathlib.Path(parent_folder + "/" + folder + "/results/model.pt").exists() and\
       not pathlib.Path(parent_folder + "/" + folder + "/results/model_1.pt").exists():
               return 2;
    return 0;
def isValidResultsFolder(folder, parent_folder="results"):
    if not pathlib.Path(parent_folder + "/" + folder).exists(): return 1;
    if not pathlib.Path(parent_folder + "/" + folder + "/results").exists():
        return 2;
    return 0;

def getSessionType(path, params, agentCount):
    sess_type = None
    if pathlib.Path(path + "/training").exists():
        if agentCount is None:
            if "marl" in path: sess_type = "MARL";
            if "gnn" in path:
                if sess_type is None: sess_type = "GNN";
                else: sess_type = None;
        else:
            if agentCount > 1: sess_type = "MARL";
            else: sess_type = "GNN";
    else:
        if agentCount == None: sess_type = "simulation"
        elif agentCount > 1: sess_type = "competitive";
        else: sess_type = "solo";
    return sess_type
def fetchSessionMetadata(path):
    metadata = {}
    if not pathlib.Path(path).exists(): return None;
    config_path = pathlib.Path(path + "/config.xml")
    if config_path.exists():
        config_tree = ET.parse(str(config_path))
        params = Parameters.parse(config_tree)
        metadata["configExists"] = True
    else:
        params = Parameters();
        metadata["configExists"] = False
    # Extract
    metadata["agentCount"] = params.tryGet("training.agents")
    sess_type = getSessionType(path, params, metadata["agentCount"])
    metadata["sessionType"] = sess_type if (sess_type is not None) else "?"
    metadata["centralizedRouting"] = params.tryGet("station.routing.centralized")
    if metadata["centralizedRouting"] is None: metadata["centralizedRouting"] = False;
    metadata["k"] = params.tryGet("station.k")
    return metadata

def getSavedSessionPaths(folder):
    paths = []
    content = os.listdir(folder)
    for p in content:
        path = pathlib.Path(folder + "/" + p)
        if isValidResultsFolder(p, folder) == 0:
            paths.append((p, folder + "/" + p))
    return paths
def printSessionPaths(paths, prefix=""):
    for i in range(len(paths)):
        print(f"{prefix}- {i+1:2d}: {paths[i][0]}")
        metadata = fetchSessionMetadata(paths[i][1])
        if not metadata["configExists"]:
            print(prefix + f"      [ {metadata['sessionType']} ]")
        else:
            s = metadata["sessionType"]
            if metadata["sessionType"] == "MARL" or metadata["sessionType"] == "competitive":
                s += "; Agents: " + (str(metadata["agentCount"]) if (metadata["agentCount"] is not None) else "?")
            s += "; K: " + str(metadata["k"])
            s += "; " + ("Centralized routing" if (metadata["centralizedRouting"]) else "Selfish routing")
            print(prefix + f"      [ {s} ]")
def parseFolderInput(val, options):
    if val.isdigit():
        val = int(val)-1
        if val == -1 or val >= len(options):
            print("Given index is out of range, aborting.");
            exit();
        return options[val][1]
    else:
        valid = isValidResultsFolder(val)
        if valid == 1:
            print("No such folder exists, aborting.")
            exit()
        elif valid == 2:
            print(f"No '.pt' file inside 'results/{val}/results/', aborting.")
            exit();
        return ("results/" + val)

###### Options
def runSimulation(filepath):
    return
def ShowBest(filepath):
    return
def ShowTrainingStats(filepath, metadata):
    # Load training stats
    train_results = xmlOut.loadTrainResulst_numpy(filepath + "/results/data")
    # Show graphs
    if metadata["sessionType"] == "GNN":
        visutil.plotGNN(train_results)
    elif metadata["sessionType"] == "MARL":
        visutil.plotMARL(train_results)
    plt.show()
    return



###### MAIN
if __name__ == "__main__":
    models_paths = getSavedSessionPaths("results")
    print("Detected results:")
    printSessionPaths(models_paths, prefix="  ")
    print("")
    
    inp = input("Enter folder name or index: ").strip()
    filepath = parseFolderInput(inp, models_paths)
    metadata = fetchSessionMetadata(filepath)
    print("Successfully loaded '" + filepath + "'\n")

    while inp != "" and inp != "q" and inp != "quit":
        # Options
        print("Options:")
        print("  - [r]un      | Run a simulation using the models")
        print("  - [c]ompare  | Compare with another session")
        if metadata["sessionType"] == "GNN" or metadata["sessionType"] == "MARL":
            print("  - [b]est     | Show the statistics for the best runs")
            print("  - [t]raining | Visualize the training statistics")
        print("  - [q]uit     | Quit")
        inp = input().strip()

        if inp == "r" or inp == "1":
            runSimulation(filepath)
        elif inp == "b" or inp == "2":
            ShowBest(filepath)
        elif inp == "t" or inp == "3":
            ShowTrainingStats(filepath, metadata)
        print()
    
