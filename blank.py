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

import preprocess as prep

from lib.utility import clamp, welford, ema, ema_welford, zscore
from lib.utility import parseArgs
from lib.data_management import generateRandomChargeData, writeChargeData, loadChargeData

import lib.graphing as graphing  #= lib/graphing/__init__.py
import lib.graphing.utility as graphutil
import lib.graphing.draw as graphdraw

import lib.visual_utility as visutil

from lib.structs.trip import Trip, TripDataset
from lib.structs.graphtranslator import GraphTranslator
from lib.structs.evaluation import Evaluation
from lib.structs.params import Parameters

import lib.xml.tripsGen as tripsGen
import lib.xml.output as xmlOut

import lib.algorithms.coverage as coverAlg

from lib.sumo.blank import sumoBlankRun

MAIN_DIR = pathlib.Path(__file__).resolve().parent
os.chdir(MAIN_DIR)



if __name__ == "__main__":
    # Parse arguments
    if len(sys.argv) < 2: network_name = "manhattan";
    else:
        network_name = sys.argv[1]
        args = parseArgs(sys.argv[2:])
    # Adjust params
    params = Parameters.config()
    # Load params
    VEHICLE_COUNT = params["sim.vehicleCount"]
    #MAX_DURATION = params["sim.maxDuration"]
    #DURATION_SET = MAX_DURATION > 0
    DESTINATION_COUNT_DIST = params["sim.destinationCountDistribution"]
    MIN_DISTANCE = params["sim.minDistance"]
    MAX_DISTANCE = params["sim.maxDistance"]
    VISUALIZE = params["sim.visualize"]
    PRINT_RESULTS = params["sim.printResults"]
    PRINT_ERRORS = params["sim.printErrors"]
    EV_PEN = params["electric.penetration"]
    MEASURE_TIME = params["training.measureTime"]
    params["training.agents"] = 1
    print(params.groupPrint())
    
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
                                 internal_lengths=True, node_position=True)
    base_G_d = graphing.netToDetailedGraph(data_path + "/base_net.net.xml")
    print("Graph:    " + str(base_G) + "\nDetailed: " + str(base_G_d));
    num_nodes = base_G.number_of_nodes()
    # Detailed graph for coverage calculations
    global coverage_G_d
    coverage_G_d = graphing.netToDetailedGraph(data_path + "/base_net.net.xml", add_road_centers=True)
    # Edge translator
    translator = GraphTranslator(base_G)
    ## Other
    global network_diameter, coverage_radius_target, charge_max_eval
    network_diameter = graphutil.calcDiameter(base_G, weight="length")
    visutil.setMaxCoverageRadius(network_diameter)
    if MIN_DISTANCE < 0:
        MIN_DISTANCE = abs(MIN_DISTANCE * network_diameter)
    if MAX_DISTANCE < 0:
        MAX_DISTANCE = abs(MAX_DISTANCE * network_diameter)
    
###### PRE-RUN
    # Datetime now (file organization)
    start_datetime_str = str(datetime.now().strftime('%Y%m%d_%H%M%S'))
    output_folder = network_name + "_blank_" + start_datetime_str
    output_path = output_path + "/" + output_folder
    pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
    pathlib.Path(output_path + "/training").mkdir(parents=True, exist_ok=True)
    # Save params and metadata
    params.write(output_path + "/config.xml")
    xmlOut.writeMetadata(output_path + "/metadata.xml", network_name, start_datetime_str, "GNN", network_diameter)
    ## Vehicle data
    if "vehicle-data" in args:
        # Load
        trips = TripDataset.parseXML(base_G, translator, args["vehicle-data"] + "/trips.xml")
        trips.write(output_path + "/trips.xml")
        charge_data = loadChargeData(args["vehicle-data"] + "/charge_data.xml")
        print(f"INFO: Successfully loaded vehicle data for {len(trips.dict)} vehicles from '{args['vehicle-data']}'")
    else:
        # Generate trips for the whole training session
        trips = tripsGen.main(base_net, base_G, VEHICLE_COUNT, output_path + "/trips.xml",
                              destination_count_probs=DESTINATION_COUNT_DIST,
                              #min_distance_per_des=(network_diameter / 4.0),
                              min_distance=MIN_DISTANCE, #network_diameter*0.5,
                              max_distance=MAX_DISTANCE, #network_diameter*2.0,
                              ev_pen=EV_PEN)
        # Generate charge data
        vTypes_tree = ET.parse("networks/vTypes.add.xml")
        max_charge = prep.getMaxChargeFromAddTree(vTypes_tree)
        charge_data = generateRandomChargeData(trips, max_charge)
    average_trip_len = trips.averageTripLen()
    # Save used charge data
    writeChargeData(charge_data, output_path + "/charge_data.xml")
    ## Prepare results
    results = Evaluation(translator)
###### RUN 
    results = sumoBlankRun(base_net, data_path, network_name, trips, results, params=params,
                           output_path=output_path, output_subfolder="blank")
###### POSTPROCESS
    pathlib.Path(output_path + "/results").mkdir(parents=True, exist_ok=True)
    res_dict = results.getFullDict(include_edge_data=True)
    res_tree = ET.ElementTree(ET.fromstring('<results></results>'))
    xmlOut.dictToElement_recursive(res_dict, res_tree.getroot())
    ET.indent(res_tree, space="    ")
    res_tree.write(output_path + "/results/results.xml");
    full_save_path = pathlib.Path(output_path + "/results.xml").resolve()
    print(f"Simulation finished in {round(results.executionDuration, 2)} seconds, saved results under\n'{str(full_save_path)}'")
    # Clean up files
    if params["sim.deleteCache"] == True:
        xmlOut.cleanCache(output_path + "/_cache", network_name)
