import os
import sys
import pathlib
import time
import numpy as np

import lib.data_management as dm

import lib.visual_utility as visutil

import lib.xml.output as xmlOut

from lib.structs.params import Parameters
from lib.structs.evaluation import Evaluation, EvaluationDataset
from lib.structs.trip import Trip, TripDataset
from lib.structs.stationinfo import StationInfo, StationInfoDataset 




def getBestResults(filepath, params=None):
    if params is None: params = Parameters.load(filepath + "/config.xml")
    metadata = dm.loadSessionMetadata(filepath)
    sess_type = dm.isValidModelFolder(filepath)
    train_results = xmlOut.loadTrainResults_numpy(filepath + "/results/data")
    results_ds = EvaluationDataset.fromTrainResults(train_results, params, metadata["networkDiameter"])
    #for ri in range(len(results_ds.arr)):
    #    print(str(ri) + ": " + str(results_ds.arr[ri]))
    scores = results_ds.calcScores(params)
    print(scores)
    ranked_indeces = list(np.argsort(scores))
    best_index = ranked_indeces[-1]
    print("best index:", best_index)
    return results_ds.arr[best_index]


PRINT_RESULTS = False

#def rerunAndCompareSessions(filepaths):
if __name__ == "__main__":
    # Parse filepaths from args
    filepaths = []
    for i in range(1, len(sys.argv)):
        filepaths.append(sys.argv[i])
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
