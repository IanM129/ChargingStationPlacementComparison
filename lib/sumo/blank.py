import sys
import os
import __main__
from subprocess import call, DEVNULL
import time
from datetime import datetime
import random
import math
import numpy as np
import sumolib
import traci
import traci.constants as tc
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import pathlib
import networkx as nx
import re

sumoBinary = sumolib.checkBinary('sumo')
#import randomTrips
jtrrouterBinary = sumolib.checkBinary('jtrrouter')

import lib.graphing as graphing  #= lib/graphing/__init__.py
import preprocess as prep

import lib.sumo.utility as sumoutil

import lib.traci_utility as traciutil

from lib.structs.stationinfo import StationInfo, StationInfoDataset
from lib.structs.trip import Trip
from lib.structs.evaluation import Evaluation
from lib.structs.params import Parameters

import lib.algorithms.algorithms as alg

import lib.graphing.utility as graphutil
import lib.graphing.draw as graphdraw

import lib.xml.parkingNetGen as parkingNetGen
import lib.xml.tripsGen as tripsGen
import lib.xml.output as xmlOut

SCRIPT_DIR = pathlib.Path(__main__.__file__).resolve().parent
os.chdir(SCRIPT_DIR)



def preprocess(data_path, sumo_filename, output_path, params=None):
    if not params: params = Parameters.default();
    sumo_filepath = data_path + "/" + sumo_filename + ".sumocfg"
    ## Folder organization
    #output_path = data_path + "/" + output_folder + "/" + output_subfolder
    pathlib.Path(output_path).mkdir(parents=True, exist_ok=True)
    pathlib.Path(data_path + "/output").mkdir(parents=True, exist_ok=True)
    #### Pre-loop
    ## Preprocess sumo config
    sumocfg_tree = ET.parse(sumo_filepath)
    sumocfg_tree = prep.config_enableStations(sumocfg_tree, enable=False)
    sumocfg_tree = xmlOut.config_enableStationOutput(sumocfg_tree, enable=False)
    sumocfg_tree = xmlOut.config_enableBatteryOutput(sumocfg_tree, enable=False)
    sumocfg_tree.write(sumo_filepath)
    ## Load XMLs
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    vTypes_tree = ET.parse("networks/vTypes.add.xml", parser=parser)
    ## Update XML settings
    prep.enableBattery(vTypes_tree, False)
    prep.enableStationFinder(vTypes_tree, False)
    vTypes_tree.write(data_path + "/vTypes.add.xml") # rewrite modified vTypes XML tree


def sumoBlankRun(net, data_path, sumo_filename, trips, results : Evaluation,
                 output_path, output_subfolder="blank",
                 params=None, debug=False):
    if not params: params = Parameters.default();
    MAX_DURATION = params["sim.maxDuration"]
    DURATION_SET = MAX_DURATION > 0
#### PREPROCESS
    #output_path = data_path + "/" + output_folder
    if params["saveLog"] or params["saveInputs"]:# or params["saveOutputs"]:
        output_path += "/" + output_subfolder
    if params["preprocess"]:
        preprocess(data_path, sumo_filename, output_path, params)
    sumo_filepath = data_path + "/" + sumo_filename + ".sumocfg"
    #output_path = output_path + "/" + output_subfolder
    output_path_full = str(SCRIPT_DIR) + "/" + output_path
#### MAIN
    #### Process
    ## Preprocess output config (post station generation)
    # Induction loop
    xmlOut.config_createInductionLoopOutputFile(net.getEdges(), xml_filepath=data_path + "/output.add.xml",
                                                relative_out_filepath="output/loop.out.xml", overwrite=True)
    # Edge based macroscopic traffic measures
    xmlOut.config_createEdgeOutputFile(xml_filepath=data_path + "/output.add.xml",
                                       relative_out_filepath="output/edgeData.out.xml",
                                       overwrite=False)
    ## Copy requred files to run simulation
    ...
    ## Command
    if params["saveLog"]: log_filepath = output_path_full + "/log.txt"
    else: log_filepath = None;
    cmnd = sumoutil.genSumoCommand(sumo_filepath, params["stepLength"], params["visualize"], log_filepath)
    if debug: print("-> SUMO command:\n'" + ' '.join(cmnd) + "'");
        
#### SIMULATION
    fully_completed = True;
    EVs_count = 0; total_veh_count = 0;
    ## Run simulation
    if debug:
        sim_stime = time.perf_counter()
    traci.start(cmnd)
    ## Subscriptions
    traci.simulation.subscribe([
        traci.constants.VAR_DEPARTED_VEHICLES_IDS
    ])
    while traci.simulation.getMinExpectedNumber() > 0: #and traci.simulation.getTime() < duration:
        # Check max duration
        if DURATION_SET:
            if traci.simulation.getTime() >= MAX_DURATION:
                fully_completed = False; break;
        # Step
        traci.simulationStep();
        data_sim = traci.simulation.getSubscriptionResults()

        #### Process state
        ## Newly added
        departed = set(data_sim.get(tc.VAR_DEPARTED_VEHICLES_IDS, []))          #set(traci.simulation.getDepartedIDList());
        for vehID in departed:
            total_veh_count += 1;
            vtype = traci.vehicle.getTypeID(vehID)
            if vtype == "electric":
                EVs_count += 1;

                    

    ## Simulation done
    sim_time = traci.simulation.getTime()
    traci.close()
    if debug:
        sim_etime = time.perf_counter()
        steps_processed = int(sim_time / params["sim.stepLength"])
        print("\n")
        print(f"-------- Simulation over at {sim_time} ({steps_processed} steps); after {sim_etime - sim_stime:0.2f} seconds")
        print(f"         vehicle count: {total_veh_count:6d}")
        print(f"             - electric: {EVs_count:6d} ({round((EVs_count / total_veh_count)*100, 2):4.2f} %)")
        print()

#### POSTPROCESS
    results.clear()
    results.setSimulationData(fully_completed, sim_time)
    ## Get flow at edges
    edge_stats = xmlOut.getEdgeLoopStats(filepath=data_path + "output/loop.out.xml",
                                         max_flow=True)
    edge_data = xmlOut.getEdgeDataStats(filepath=data_path + "output/edgeData.out.xml")
    results.setEdgeData(edge_stats, edge_data)
    results.setVehicleData(vehicle_count=total_veh_count,
                           EV_count=0, EV_set_charge=0,
                           EV_arrived=0, EV_charged=0)
    results.setStationData([], None, None, 0.0)
    return results
        
