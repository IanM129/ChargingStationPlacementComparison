import os
import sys
import random
import pathlib
import xml.etree.ElementTree as ET

from lib.structs.params import Parameters
from lib.structs.trip import Trip, TripDataset
from lib.structs.graphtranslator import GraphTranslator



#### Utility
def hashChargeData(charge_data):
    data = []
    for vehID in sorted(charge_data.keys()):
        data.append((vehID, tuple(charge_data[vehID])))
    return hash(tuple(data))
## Sessions
def isValidSessionFolder(filepath):
    res_path = pathlib.Path(filepath + "/results/")
    train_path = pathlib.Path(filepath + "/training/")
    cfg_path = pathlib.Path(filepath + "/config.xml")
    mtdt_path = pathlib.Path(filepath + "/metadata.xml")
    cd_path = pathlib.Path(filepath + "/charge_data.xml")
    trps_path = pathlib.Path(filepath + "/trips.xml")
    return res_path.exists() and train_path.exists() and\
           cfg_path.exists() and mtdt_path.exists() and\
           cd_path.exists() and trps_path.exists()
def getSessionType(path, params, agentCount):
    path = path.lower()
    sess_type = None
    if isValidSessionFolder(path):
        if agentCount is None:
            if "cover" in path:
                sess_type = "cover";
            if "game" in path:
                if sess_type is None: sess_type = "game";
                else: sess_type = "?";
            if "gnn" in path:
                if sess_type is None: sess_type = "gnn";
                else: sess_type = "?";
            if "marl" in path:
                if sess_type is None: sess_type = "marl";
                else: sess_type = "?";
        else:
            if agentCount > 1: sess_type = "MARL";
            else: sess_type = "GNN";
    else:
        if agentCount == None: sess_type = "simulation"
        elif agentCount > 1: sess_type = "competitive";
        else: sess_type = "solo";
    return sess_type
## Vehicle data
def getIndexInVehicleList(vd_list, value):
    for i in range(len(vd_list)):
        if vd_list[i][0] == value: return i;
    return -1;
#### Validation
## bad:  -1 = parent folder doesn't exist   0 = no model file found,
## good: 1 = found model.pt (GNN)           2 = found model_1.pt (MARL)
def isValidModelFolder(folder, parent_folder=""):
    parent_path = folder
    if parent_folder != "": parent_path = parent_folder + "/" + folder
    if not pathlib.Path(parent_path).exists(): return -1;
    if pathlib.Path(parent_path + "/results/model.pt").exists(): return 1;
    if pathlib.Path(parent_path + "/results/model_1.pt").exists(): return 2;
    return 0;
def isValidResultsFolder(folder, parent_folder="results"):
    if not pathlib.Path(parent_folder + "/" + folder).exists(): return 1;
    if not pathlib.Path(parent_folder + "/" + folder + "/results").exists():
        return 2;
    return 0;
def isValidNetworkFolder(name):
    if not pathlib.Path("networks/" + name).exists(): return 1;
    #if not pathlib.Path("networks/" + name + "/" + name.lower() + ".sumocfg").exists():
    #   return 2;
    if not pathlib.Path("networks/" + name + "/base_net.net.xml").exists():
        return 3;
    return 0;


#### Get lists
def getNetworkList(parent_folder="networks"):
    data = []
    default = None
    for folder in os.listdir(parent_folder):
        folder_path = os.path.join(parent_folder, folder)
        if os.path.isdir(folder_path):
            net_file = os.path.join(folder_path, "base_net.net.xml")
            if os.path.isfile(net_file):
                info = [folder, folder_path, ""]
                desc_file = os.path.join(folder_path, "description.txt")
                if os.path.isfile(desc_file):
                    with open(desc_file, "r", encoding="utf-8") as f: text = f.read();
                    info[2] = text
                data.append(info)
                default_file = os.path.join(folder_path, "default.txt")
                if os.path.isfile(default_file): default = folder;
    return data, default
def getVehicleDataList(parent_folder="vehicle_data"):
    data = []
    default = None
    for folder in os.listdir(parent_folder):
        folder_path = os.path.join(parent_folder, folder)
        if os.path.isdir(folder_path):
            trips_file = os.path.join(folder_path, "trips.xml")
            charge_file = os.path.join(folder_path, "charge_data.xml")
            if os.path.isfile(trips_file) and os.path.isfile(charge_file):
                metadata_file = os.path.join(folder_path, "metadata.xml")
                if os.path.isfile(metadata_file):
                    tree = ET.parse(metadata_file)                    
                    network_name = tree.getroot().find("network").text
                else:
                    network_name = None
                data.append([folder, folder_path, network_name])
    return data
def getVehicleDataHashList(parent_folder="vehicle_data"):
    data = {}
    default = None
    for folder in os.listdir(parent_folder):
        folder_path = os.path.join(parent_folder, folder)
        if os.path.isdir(folder_path):
            trips_file = os.path.join(folder_path, "trips.xml")
            charge_file = os.path.join(folder_path, "charge_data.xml")
            if os.path.isfile(trips_file) and os.path.isfile(charge_file):
                network_name = ET.parse(folder_path + "/metadata.xml").find("network").text
                trips = loadSessionTrips(folder_path, network_name)
                trips_hash = hash(trips)
                charge_data = loadChargeData(folder_path + "/charge_data.xml")
                chargedata_hash = hashChargeData(charge_data)    
                data[(trips_hash, chargedata_hash)] = folder
    return data
## Get session groups based on network and vehicle data they were trained on
# - network
# - vehicle data (trips, charge_data)
# - k (total), capacity, wait_queue
# - centralized
# - (maxDuration?)
def getSessionGroups(parent_folder="results"):
    vd_hashlist = getVehicleDataHashList()
    vd_pathlist = getVehicleDataList()
    if (not os.path.exists(parent_folder)): return None, 0;
    groups = {}
    prec = 0
    for folder in os.listdir(parent_folder):
        folder_path = os.path.join(parent_folder, folder)
        if os.path.isdir(folder_path) and folder[0] != '_':
            if isValidSessionFolder(folder_path) and\
                isValidResultsFolder(folder, parent_folder) == 0:
                if parent_folder not in groups:
                    groups[parent_folder] = {}
                loc_groups = groups[parent_folder]
                # Get data
                metadata = loadSessionMetadata(folder_path)
                network_name = metadata["network"]
                trips_hash = metadata.get("tripsHash", None)
                cd_hash = metadata.get("chargeDataHash", None)
                k = metadata["k"]# * metadata["agentCount"]
                centralized = metadata["centralizedRouting"]
                # Update groups dict
                key = (network_name, k, centralized)
                if key not in loc_groups: loc_groups[key] = {};
                if (trips_hash, cd_hash) in vd_hashlist:
                    vd_folder = vd_hashlist[(trips_hash, cd_hash)]
                    index = getIndexInVehicleList(vd_pathlist, vd_folder)
                    sec_key = (index, vd_folder, int(metadata["vehicleCount"]))
                else:
                    sec_key = (trips_hash, cd_hash, int(metadata["vehicleCount"]))
                if sec_key not in loc_groups[key]: loc_groups[key][sec_key] = [];
                loc_groups[key][sec_key].append((folder, parent_folder, metadata))
                if len(folder) > prec: prec = len(folder);
            else:
                sub_groups, sub_prec = getSessionGroups(folder_path)
                groups.update(sub_groups)
                if sub_prec > prec: prec = sub_prec;
    return groups, prec



   

###### Data management
#### Session management
def getSavedSessionPaths(folder):
    paths = []
    content = os.listdir(folder)
    for p in content:
        path = pathlib.Path(folder + "/" + p)
        if isValidResultsFolder(p, folder) == 0:
            paths.append((p, folder + "/" + p))
    return paths
def loadSessionTrips(path, network_name):
    net_path = pathlib.Path("networks/" + network_name + "/base_net.net.xml")
    trips_path = pathlib.Path(path + "/trips.xml")
    if not net_path.exists():
        raise Exception(f"ERROR: Trying to load trips from {path}, but 'base_net.net.xml' doesn't exist.");
    if not trips_path.exists():
        raise Exception(f"ERROR: Trying to load trips from {path}, but 'trips.xml' doesn't exist.");
    from lib.graphing import netToGraph
    G = netToGraph(net_path, lengths=True, travel_time=True,
                   internal_lengths=True, node_position=True)
    import networkx as nx
    translator = GraphTranslator(G)
    return TripDataset.parseXML(G, translator, trips_path)
def loadSessionMetadata(path):
    metadata = {}
    if not pathlib.Path(path).exists(): return None;
    ## Config xml
    config_path = pathlib.Path(path + "/config.xml")
    if config_path.exists():
        config_tree = ET.parse(str(config_path))
        params = Parameters.parse(config_tree)
        metadata["configExists"] = True
    else:
        params = Parameters();
        metadata["configExists"] = False
    metadata["agentCount"] = params.tryGet("training.agents")
    metadata["centralizedRouting"] = params.tryGet("station.routing.centralized")
    if metadata["centralizedRouting"] is None: metadata["centralizedRouting"] = False;
    metadata["k"] = params.tryGet("station.k")
    if metadata["agentCount"] is not None:
        metadata["k"] *= metadata["agentCount"]
    metadata["vehicleCount"] = params.tryGet("sim.vehicleCount")
    ## Metadata xml
    mtdt_path = pathlib.Path(path + "/metadata.xml")
    if mtdt_path.exists():
        mtdt_tree = ET.parse(str(mtdt_path));
        mtdt_root = mtdt_tree.getroot();
        metadata["date"] = mtdt_root.find("date").text
        metadata["time"] = mtdt_root.find("time").text
        metadata["network"] = mtdt_root.find("network").text
        metadata["networkDiameter"] = mtdt_root.find("networkDiameter").text
        type_el = mtdt_root.find("type")
        if type_el is not None:
            metadata["sessionType"] = type_el.text
        else: metadata["sessionType"] = None
        metadata["metadataExists"] = True
    else:
        metadata["metadataExists"] = False
    # Check session type
    if metadata["sessionType"] is None:
        metadata["sessionType"] = getSessionType(path, params, metadata["agentCount"])
    ## Vehicle data
    trips_path = pathlib.Path(path + "/trips.xml")
    if trips_path.exists():
        trips = loadSessionTrips(path, metadata["network"])
        metadata["tripsHash"] = hash(trips)
    chargedata_path = pathlib.Path(path + "/charge_data.xml")
    if chargedata_path.exists():
        charge_data = loadChargeData(chargedata_path)
        metadata["chargeDataHash"] = hashChargeData(charge_data)
    return metadata
#### Data
## Generate
def generateRandomChargeData(trips, max_charge):
    import preprocess as prep
    charge_data = {}
    for vehID, trip in trips.dict.items():
        need_to_charge_level = random.uniform(0.15, 0.4)
        trip_len = trip.total_distance
        approx_charge_needed = prep.calcApproxChargeNeeded(trip_len)
        # v1 : random.uniform(0.2, 0.3) * max_charge
        # v0 : max(0.02, 0.1 + (random.gauss() * 0.03)) * max_charge;
        # v2 : max(min_charge, random.uniform(0.4, 0.8) * approx_charge_needed)
        set_charge = (need_to_charge_level * max_charge) + (approx_charge_needed * random.uniform(0.0, 1.0))
        charging_min = random.uniform(250, 750)
        # (need_to_charge_level, starting_charge, charging_min)
        charge_data[vehID] = (need_to_charge_level, set_charge, charging_min)
    return charge_data
## Write
def writeChargeData(charge_data, filepath):
    tree = ET.ElementTree(ET.fromstring("<chargeData></chargeData>"))
    root = tree.getroot()
    for vehID, data in charge_data.items():
        el = ET.SubElement(root, "vehicle", {
                                "id": vehID,
                                "needToChargeLevel": str(data[0]),
                                "startingCharge": str(data[1]),
                                "chargingMin": str(data[2])})
    tree.write(filepath)
## Load
def loadChargeData(filepath):
    charge_data = {}
    tree = ET.parse(filepath)
    for el in tree.getroot():
        vehID = str(el.get("id"))
        data = [float(el.get("needToChargeLevel")),
                float(el.get("startingCharge")),
                float(el.get("chargingMin"))]
        charge_data[vehID] = data
    return charge_data
def loadModels(filepath, agent_count, graph, device):
    import torch
    model = None;
    if (model_folder := isValidModelFolder(filepath)) > 0:
        from lib.gnn.model2 import EdgePosGNN
        if model_folder == 1:
            model = EdgePosGNN(graph.x.shape[1], graph.edge_attr.shape[1], 64)
            model.load_state_dict(torch.load(filepath + "/results/model.pt", weights_only=True))
            model.to(device); model.eval();
        else:
            from lib.gnn.model3 import EdgePosAndPriceGNN
            model = []
            for a in range(agent_count):
                model.append(EdgePosAndPriceGNN(graph.x.shape[1], graph.edge_attr.shape[1], 64))
                model[a].load_state_dict(torch.load(filepath + "/results/model_" + str(a+1) + ".pt",
                                                    weights_only=True))
                model[a].to(device); model[a].eval();
    return model
## Metadata
def getVehicleDataMetadata(folder, parent_folder="vehicle_data"):
    # vehicle_count, EV_count, network_name
    metadata = {}
    folder_path = os.path.join(parent_folder, folder)
    if os.path.isdir(folder_path):
        trips_file = os.path.join(folder_path, "trips.xml")
        trips_tree = ET.parse(trips_file)
        metadata["vehicle_count"] = len(trips_tree.getroot())
        EV_count = 0
        for el in trips_tree.getroot():
            if el.get("type") == "electric": EV_count += 1;
        metadata["EV_count"] = EV_count
        metadata["network_name"] = ET.parse(folder_path + "/metadata.xml").find("network").text
    return metadata
