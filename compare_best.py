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
    args = {"stats": None}
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "-stats":
            args["stats"] = sys.argv[i+1].split(',')
            i += 2
        elif sys.argv[i] == "--no-values":
            args["no-values"] = True
            i += 1
        elif sys.argv[i] == "--no-legend":
            args["no-legend"] = True
            i += 1
        elif sys.argv[i] == "--centerize":
            args["centerize"] = True
            i += 1
        else:
            filepaths.append(sys.argv[i])
            i += 1
    return filepaths, args

PRINT_RESULTS = False

if __name__ == "__main__":
    # Parse filepaths from args
    filepaths, args = parseArgs();
    if "stats" in args: stats = args["stats"];
    else: stats = None;
    print("Comparing by best:", filepaths, "\n")
    # Rerun and compare
    stime = time.perf_counter()
    results_ds = []
    params_arr = []
    i = 0
    for filepath in filepaths:
        params = Parameters.load(filepath + "/config.xml")
        res = getBestResults(filepath, params=params)
        #print(f"{i:2d}:", res)
        results_ds.append(res)
        params_arr.append(params)
        i += 1
    results_ds = EvaluationDataset(results_ds)
    scores = results_ds.calcScores(params_arr)
    sess_names = [filepath.rsplit('/', 1)[1] for filepath in filepaths]
    rank_prec = len(str(len(scores)))
    name_prec = len(max(sess_names, key=len)) + 4
    ranked_indeces = list(np.argsort(scores))
    ranked_indeces.reverse()
    print("Final scores:")
    for rank in range(len(ranked_indeces)):
        i = ranked_indeces[rank]
        filepath = filepaths[i]
        print(f"  {(rank+1):{rank_prec}}. {sess_names[i]:{name_prec}s}: {scores[i]}")
    print("")
    etime = time.perf_counter()
    print(f"Finished in {round(etime - stime, 2)} seconds")
    #### Plot stats
    ## Global
    # Check if dups
    seen = set()
    dup = False
    for name in sess_names:
        if name in seen:
            dup = True; break;
        seen.add(name)
    if dup:
        indeces = {};
        for i in range(len(filepaths)):
            p = filepaths[i].rsplit('/', 1)[0]
            if p not in indeces: indeces[p] = [];
            indeces[p].append(i)
        print(indeces)
        for key, inds in indeces.items():
            fig = visutil.plotResultDataset(results_ds, sess_names, params_arr, win_title=key,
                                            stat_list=["simDuration", "tripDuration", "totalCoverage"],
                                            index_list=inds,
                                            legend=("no-legend" not in args),
                                            value_labels=("no-values" not in args),
                                            centerize=("centerize" in args))
    else:
        fig1 = visutil.plotResultDataset(results_ds, sess_names, params_arr,
                                         stat_list=["simDuration", "tripDuration", "totalCoverage"],
                                         legend=("no-legend" not in args),
                                         value_labels=("no-values" not in args),
                                         centerize=("centerize" in args))
    ## Competitive
    # Coverage
    if stats is None or "coverage" in stats:
        fig2 = visutil.plotCompetitiveResultDataset(results_ds, sess_names, params_arr, stat="coverage",
                                                     legend=("no-legend" not in args),
                                                     value_labels=("no-values" not in args),
                                                     centerize=("centerize" in args))
    # Price
    price_data = []
    name_data = []
    for i in range(len(results_ds.arr)):
        res = results_ds.arr[i]
        if "price" in res.station_data:
            prices = res.station_data["price"]
            price_data.append(prices)
            name_data.append(sess_names[i])
    fig3 = visutil.plotCompetitiveValues(price_data, name_data, "price",
                                         title="Usporedba cijena", xlabel="Cijena punjenja (€ po kWh)")
    ## Plot scores
    # Round to 2
    for i in range(len(scores)):
        scores[i] = round(scores[i], 2)
    fig3 = visutil.plotScores(scores, sess_names,
                              legend=("no-legend" not in args),
                              value_labels=("no-values" not in args))
    plt.show()
