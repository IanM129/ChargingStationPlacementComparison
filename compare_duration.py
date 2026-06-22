import os
import sys
import pathlib
import time
import numpy as np
import matplotlib.pyplot as plt

import lib.data_management as dm

import lib.visual_utility as visutil

import lib.xml.output as xmlOut

from lib.structs.params import Parameters
from lib.structs.evaluation import Evaluation, EvaluationDataset
from lib.structs.trip import Trip, TripDataset
from lib.structs.stationinfo import StationInfo, StationInfoDataset 


network_diameter = {}
def getNetworkDiameter(network_name):
    if network_name not in network_diameter:
        from lib.graphing.utility import diameter as gutil_diameter
        data_path = "networks/" + network_name + "/";
        base_G = graphing.netToGraph(data_path + "/base_net.net.xml",
                                     lengths=True, travel_time=True,
                                     internal_lengths=True, node_position=True)
        diameter = gutil_diameter(base_G, weight="length")
        network_diameter[network_name] = diameter
    return network_diameter[network_name]

def getBestResults(filepath, params=None):
    if params is None: params = Parameters.load(filepath + "/config.xml")
    metadata = dm.loadSessionMetadata(filepath)
    if metadata["networkDiameter"] == 0.0:
        metadata["networkDiameter"] = getNetworkDiameter(metadata["network"])
    sess_type = dm.isValidModelFolder(filepath)
    train_results = xmlOut.loadTrainResults_numpy(filepath + "/results/data")
    results_ds = EvaluationDataset.fromTrainResults(train_results, params, metadata["networkDiameter"])
    #for ri in range(len(results_ds.arr)):
    #    print(str(ri) + ": " + str(results_ds.arr[ri]))
    scores = results_ds.calcScores(params)
    ranked_indeces = list(np.argsort(scores))
    best_index = ranked_indeces[-1]
    return results_ds.arr[best_index]


def parseArgs():
    filepaths = [];
    i = 1
    while i < len(sys.argv):
        filepaths.append(sys.argv[i])
        i += 1
    return filepaths

PRINT_RESULTS = False

if __name__ == "__main__":
    # Parse filepaths from args
    filepaths = parseArgs();
    print("Comparing by duration:", filepaths, "\n")
    # Gather info and compare
    stime = time.perf_counter()
    durations = []
    per_iteration = []
    i = 0
    for filepath in filepaths:
        dur = float(xmlOut.loadTotalDuration_txt(filepath + "/results"))
        durations.append(round(dur, 2))
        params = Parameters.load(filepath + "/config.xml")
        iterations = float(params["training.iterations"])
        per_iteration.append(round((dur / iterations), 2))
        i += 1
    sess_names = [filepath.rsplit('/', 1)[1] for filepath in filepaths]
    rank_prec = len(str(len(durations)))
    name_prec = len(max(sess_names, key=len)) + 4
    ranked_indeces = list(np.argsort(durations))
    ranked_indeces.reverse()
    print("Final durations:")
    for rank in range(len(ranked_indeces)):
        i = ranked_indeces[rank]
        filepath = filepaths[i]
        print(f"  {(rank+1):{rank_prec}}. {filepaths[i]:{name_prec}s}: {durations[i]}")
    print("")
    etime = time.perf_counter()
    print(f"Finished in {round(etime - stime, 2)} seconds")
    # Plot
    fig1 = visutil.plotScores(durations, sess_names, title="Vrijeme izvršavanja", ylabel="Sekunda")
    fig2 = visutil.plotScores(per_iteration, sess_names, title="Vrijeme izvršavanja iteracije", ylabel="Sekunda")
    plt.show()
