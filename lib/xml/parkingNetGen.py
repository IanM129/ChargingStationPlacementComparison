import os
import math
from subprocess import call, check_output, DEVNULL
import xml.etree.ElementTree as ET
import sumolib

netconvertBinary = sumolib.checkBinary('netconvert')

from lib.globalVars import *

from lib.structs.stationinfo import StationInfoDataset


STATION_IN_LANES = 3
STATION_OUT_LANES = 2


def getEntryID(edge_id):
    return "pcsEntry_" + str(edge_id);
def getDeadEndID(edge_id):
    return "pcsEnd_" + str(edge_id);
def getEdgeID(edge_id, reverse=False, suffix=""):
    entry_id = getEntryID(edge_id);
    park_id = getDeadEndID(edge_id) + suffix
    if reverse: return park_id + ROAD_ID_SEPARATOR + entry_id;
    else: return entry_id + ROAD_ID_SEPARATOR + park_id;
def getLaneID(edge_id, lane_index, reverse=False, suffix=""):
    return getEdgeID(edge_id, reverse=reverse, suffix=suffix) + "_" + str(lane_index);
def getParkingID(edge_id, reverse=False, suffix=""):
    return "pcsParking_" + str(edge_id) + suffix + "_" + ("1" if reverse else "0");
def getStationID(edge_id, reverse=False, suffix="", with_index=True):
    val = "pcsStation_" + str(edge_id) + suffix
    if with_index: val += "_" + ("1" if reverse else "0");
    return val

def getEdgeOfStationID(station_id):
    last_sep = station_id.rindex("_")
    station_id_cut = station_id[:last_sep]
    penult_sep = station_id_cut.rindex("_")
    return station_id_cut[penult_sep+1:]
def getParkingIDOfStation(station_id):
    if station_id[-2] == '_': station_id = station_id.rsplit('_', 1)[0];
    parking_noind = "pcsParking_" + station_id.split('_', 1)[1];
    return parking_noind
def getParkingIDsOfStation(station_id):
    if station_id[-2] == '_': station_id = station_id.rsplit('_', 1)[0];
    parking_noind = "pcsParking_" + station_id.split('_', 1)[1];
    return (parking_noind + "_0", parking_noind + "_1")

def getVehicleLength(add_tree, electric=True):
    if electric:
        return float(add_tree.getroot().find("vType[@id='electric']").get("length"));
    else:
        return float(add_tree.getroot().find("vType[@id='conventional']").get("length"));
def calcVehicleQueueLength(vehicle_length, min_gap, n):
    if n == 1: return vehicle_length;
    return (n * vehicle_length) + ((n - 1) * min_gap);


def addNode(root, n_id, x, y, ntype="priority"):
    return ET.SubElement(root, "node", {
            "id": str(n_id),
            "type" : ntype,
            "x" : str(x),
            "y" : str(y)
        });
def addEdge(root, e_id, from_n_id, to_n_id, num_lanes=1):
    return ET.SubElement(root, "edge", {
            "id" : str(e_id),
            "from" : str(from_n_id),
            "to" : str(to_n_id),
            "numLanes" : str(num_lanes) #, "priority" : "1"
        });
def addLane(root, edge_id, index=0, speed=0, length=0):
    for edge in root:
        if edge.get("id") == edge_id:
            #lane_id = edge_id + "_" + str(index)
            item = ET.SubElement(edge, "lane", {
                    #"id" : str(lane_id),
                    "index" : str(index)
                });
            if speed > 0: item.set("speed", str(speed));
            if length > 0: item.set("length", str(length));
            return item
    return None
def addParking(add_tree, edge_id, lane_id, start_pos, end_pos, capacity=1, reverse=False, suffix=""):
    parkingArea_id = getParkingID(edge_id, reverse=reverse, suffix=suffix)
    add_main = add_tree.getroot();
    parking = ET.SubElement(add_main, "parkingArea")
    parking.set("id", parkingArea_id); parking.set("lane", str(lane_id));
    parking.set("startPos", str(start_pos)); parking.set("endPos", str(end_pos));
    parking.set("roadsideCapacity", str(capacity));
    return add_tree
def addParkingStation(add_tree, edge_id, lane_id, start_pos, end_pos, capacity=1, power=50000, reverse=False, suffix=""):
    addParking(add_tree, edge_id, lane_id, start_pos, end_pos, capacity=capacity, reverse=reverse, suffix=suffix)
    parkingArea_id = getParkingID(edge_id, reverse=reverse, suffix=suffix)
    station_id = getStationID(edge_id, reverse=reverse, suffix=suffix)
    add_main = add_tree.getroot();
    station = ET.SubElement(add_main, "chargingStation")
    station.set("id", station_id); station.set("lane", str(lane_id)); #"chargingStation_" + station_id
    station.set("startPos", str(start_pos)); station.set("endPos", str(end_pos));
    station.set("power", str(power));
    station.set("parkingArea", parkingArea_id);
    return add_tree

def addPOI(add_tree, id_name, x, y, color, type_str):
    add_main = add_tree.getroot();
    poi = ET.SubElement(add_main, "poi", {
            "id" : id_name,
            "x" : str(x),
            "y" : str(y),
            "color" : str(color[0]) + "," + str(color[1]) + "," + str(color[2]),
            "type": type_str,
            "width" : str(10),
            "height" : str(10)
        })
    return add_tree


    
    
def extractNetworkFeatures(network_tree=None, network_filepath=None):
    if network_tree != None: net_tree = network_tree;
    elif network_filepath != None: net_tree = ET.parse(network_filepath)
    else: raise Exception("Both tree and filepath are not given.")
    net_root = net_tree.getroot()
    nodes_tree = ET.ElementTree(ET.fromstring("<nodes></nodes>"));
    edges_tree = ET.ElementTree(ET.fromstring("<edges></edges>"));
    nodes_root = nodes_tree.getroot(); edges_root = edges_tree.getroot();
    ## Copy all edges
    for junction in net_root.findall("junction"):
        if junction.get("id")[0] != ":":
            ET.SubElement(nodes_root, "node", {
                    "id" : junction.get("id"),
                    "type" : junction.get("type"),
                    "x" : junction.get("x"),
                    "y" : junction.get("y")
                })
    for edge in net_root.findall("edge"):
        if edge.get("id")[0] != ":":
            ET.SubElement(edges_root, "edge", {
                    "id" : edge.get("id"),
                    "from" : edge.get("from"),
                    "to" : edge.get("to"),
                    "numLanes": str(len(edge.findall("lane")))
                })
    return (nodes_tree, edges_tree)
## Write network
def writeToXML(nodes_tree, edges_tree, output_filepath, temp_folder="", delete=False):
    nodes_filepath = "new_nodes.nod.xml"
    edges_filepath = "new_edges.edg.xml"
    if temp_folder != "":
        nodes_filepath = temp_folder + "/" + nodes_filepath;
        edges_filepath = temp_folder + "/" + edges_filepath;
    nodes_tree.write(nodes_filepath); edges_tree.write(edges_filepath);
    call([netconvertBinary,
          '--no-turnarounds.except-deadend', 'true',
          #'-s', output_filepath,
          '-n', nodes_filepath,
          '-e', edges_filepath,
          '-o', output_filepath],
          stdout=DEVNULL,
          stderr=DEVNULL)
    if delete:
        os.remove(nodes_filepath);
        os.remove(edges_filepath);

# Maybe make it use sumolib instead of xml
def createParkingNet(nodes_tree, edges_tree, add_tree, edge_id, edge_tuple, offset=0, vehicle_length=5,
                     capacity=1, wait_queue=0, min_gap=2.5, suffix="", reverse_angle=False):
    ## Caluclate offset
    #vehicle_length = getVehicleLength(add_tree)    # <- Calculate length (optional)
    half_cap_ceil = math.ceil(capacity / 2)
    if offset > 0: offset += 7.2;  # netconvert shortens it
    else:
        offset = (vehicle_length * half_cap_ceil) + 7.2 + 1.0;
        if wait_queue > 0: offset += calcVehicleQueueLength(vehicle_length, min_gap, wait_queue)
    
    #edge = edges_tree.getroot().find("edge[@id='" + str(edge_id) + "']")
    #from_n_id = edge.get("from"); to_n_id = edge.get("to");
    from_n_id = edge_tuple[0]; to_n_id = edge_tuple[1];
    nodes_root = nodes_tree.getroot(); edges_root = edges_tree.getroot();
    entry_id = getEntryID(edge_id); park_id = getDeadEndID(edge_id) + suffix;

    ## Remove existing edges
    element = edges_root.find("edge[@from='" + str(from_n_id) + "'][@to='" + str(to_n_id) + "']")
    if (element != None): edges_root.remove(element);
    element = edges_root.find("edge[@from='" + str(to_n_id) + "'][@to='" + str(from_n_id) + "']")
    if (element != None): edges_root.remove(element);
    
    ## Calculate positions
    from_n = nodes_root.find("node[@id='" + str(from_n_id) + "']");
    to_n = nodes_root.find("node[@id='" + str(to_n_id) + "']")
    x_from = float(from_n.get("x")); y_from = float(from_n.get("y"));
    x_to = float(to_n.get("x")); y_to = float(to_n.get("y"));
    dx = x_to - x_from; dy = y_to - y_from; length = math.sqrt(pow(dx, 2) + pow(dy, 2));
    norm_dx = dx / length; norm_dy = dy / length;
    x_mid = x_from + (dx / 2); y_mid = y_from + (dy / 2);

    ## Add entry node and connect
    if nodes_root.find("node[@id='" + str(entry_id) + "']") == None:
        # Add entry node
        addNode(nodes_root, entry_id, x_mid, y_mid)
        # Add edges connecting to entry node
        addEdge(edges_root, str(from_n_id) + ROAD_ID_SEPARATOR + entry_id, from_n_id, entry_id)
        addEdge(edges_root, entry_id + ROAD_ID_SEPARATOR + str(from_n_id), entry_id, from_n_id)
        addEdge(edges_root, str(to_n_id) + ROAD_ID_SEPARATOR + entry_id, to_n_id, entry_id)
        addEdge(edges_root, entry_id + ROAD_ID_SEPARATOR + str(to_n_id), entry_id, to_n_id)

    ## Add dead end node and connect
    # Add dead end node
    if reverse_angle: deadend_pos = (x_mid + (offset * norm_dy), y_mid + (offset * norm_dx));
    else: deadend_pos = (x_mid + (offset * -norm_dy), y_mid + (offset * -norm_dx));
    addNode(nodes_root, park_id, deadend_pos[0], deadend_pos[1], "dead_end")
    # Add edges connecting entry to dead end
    addEdge(edges_root, entry_id + ROAD_ID_SEPARATOR + park_id, entry_id, park_id, num_lanes=STATION_IN_LANES)
    addEdge(edges_root, park_id + ROAD_ID_SEPARATOR + entry_id, park_id, entry_id, num_lanes=STATION_OUT_LANES)

    first_park_len = vehicle_length * half_cap_ceil;
    second_park_len = vehicle_length * (capacity - half_cap_ceil);
    end_pos = (offset-7.2) - 1; start_pos = max(1, round(end_pos - first_park_len, 2));
    end_pos_second = min(end_pos, round(second_park_len, 2))
    # Add parkings and charging stations
    addParkingStation(add_tree, edge_id, getLaneID(edge_id, 0, suffix=suffix), start_pos, round(end_pos, 2), capacity=half_cap_ceil, suffix=suffix)
    addParkingStation(add_tree, edge_id, getLaneID(edge_id, 0, suffix=suffix, reverse=True), 1, end_pos_second, capacity=capacity-half_cap_ceil, reverse=True, suffix=suffix)
    
    return (nodes_tree, edges_tree, add_tree)

def addStationPOIs(net_filepath, add_filepath, station_edges, suffix=""):
    net_tree = ET.parse(net_filepath); net_root = net_tree.getroot();
    add_tree = ET.parse(add_filepath); add_root = add_tree.getroot();
    for edge_id in station_edges:
        deadend_id = getDeadEndID(edge_id) + suffix
        deadend_el = net_tree.find("junction[@id='" + deadend_id + "']")
        x = deadend_el.get("x"); y = deadend_el.get("y");
        if suffix == "_red": poi_clr = (1, 0, 0);
        elif suffix == "_blue": poi_clr = (0, 0, 1);
        else: poi_clr = (0, 0, 0);
        addPOI(add_tree, "station_" + edge_id + suffix, x, y, poi_clr, "chargingStation")
    add_tree.write(add_filepath)


#### Write stations to XML
def addStationsToNetwork(net, stations_dataset : StationInfoDataset,
                         data_path, output_path="", write=True,
                         network_tree=None, network_filepath=None,
                         stations_tree=None,stations_filepath=None,
                         vehicle_length=-1, min_gap=2.5, wait_queue_size=2,
                         suffix="", reverse_angle=False):
    if write and output_path == "": output_path = data_path;
    if vehicle_length <= 0:
        vTypes_tree = ET.parse(data_path + "/vTypes.add.xml");
        veh_len = getVehicleLength(vTypes_tree);
    # Load network net.xml
    if network_tree != None:
        nodes_tree, edges_tree = extractNetworkFeatures(network_tree=network_tree)
    else:
        if network_filepath == None: network_filepath = data_path + "/base_net.net.xml"
        nodes_tree, edges_tree = extractNetworkFeatures(network_filepath=network_filepath)
    # Load stations add.xml
    if stations_tree == None:
        if stations_filepath == None: stations_tree = ET.ElementTree(ET.fromstring("<additional></additional>"))
        else: stations_tree = ET.parse(stations_filepath);
    # Main
    for stinfo in stations_dataset:
        edge = net.getEdge(stinfo.edge_id)
        nodes_tree, edges_tree, stations_tree = createParkingNet(nodes_tree, edges_tree, stations_tree,
                                                                 stinfo.edge_id, (edge.getFromNode().getID(), edge.getToNode().getID()),
                                                                 vehicle_length=vehicle_length,
                                                                 capacity=stinfo.total_capacity,
                                                                 wait_queue=wait_queue_size, min_gap=min_gap,
                                                                 suffix=suffix, reverse_angle=reverse_angle)
    if write:
        stations_tree.write(output_path + "/stations.add.xml")
        writeToXML(nodes_tree, edges_tree, output_path + "/net.net.xml",
                   temp_folder=output_path)
    else:
        return (nodes_tree, edges_tree, stations_tree)
def appendStationsToNetwork(net, stations_dataset : StationInfoDataset,
                            nodes_tree, edges_tree, stations_tree,
                            output_path="", write=True,
                            vehicle_length=5, min_gap=2.5, wait_queue_size=2,
                            suffix="", reverse_angle=False):
    # Main
    for stinfo in stations_dataset:
        edge = net.getEdge(stinfo.edge_id)
        nodes_tree, edges_tree, stations_tree = createParkingNet(nodes_tree, edges_tree, stations_tree,
                                                                 stinfo.edge_id, (edge.getFromNode().getID(), edge.getToNode().getID()),
                                                                 vehicle_length=vehicle_length,
                                                                 capacity=stinfo.total_capacity,
                                                                 wait_queue=wait_queue_size, min_gap=min_gap,
                                                                 suffix=suffix, reverse_angle=reverse_angle)
    if write:
        stations_tree.write(output_path + "/stations.add.xml")
        writeToXML(nodes_tree, edges_tree, output_path + "/net.net.xml",
                   temp_folder=output_path)
    else:
        return (nodes_tree, edges_tree, stations_tree)

















"""
def addChargingStations(net_filepath, add_filepath, output_filepath, stations, capacity=1):
    if not net_filepath.endswith(".xml"): net_filepath += ".xml";
    net = sumolib.net.readNet(net_filepath)
    add_tree = ET.parse(add_filepath)
    nodes_tree, edges_tree = parkingNetGen.extractNetworkFeatures(net_filepath)
    for st in stations:
        nodes_tree, edges_tree, add_tree = parkingNetGen.createParkingNet(nodes_tree, edges_tree, add_tree, st, capacity=capacity)
        parking_id = parkingNetGen.getLaneID(st, 0)
    add_tree.write(data_path + "/add.xml")
    parkingNetGen.write(nodes_tree, edges_tree, (data_path + "/net.net.xml"))
"""



"""
def createParkingNet_filepath(network_filepath, edge_id, parknet_id, offset=50-7.2, output_path=""):
    if output_path == "": output_path = network_filepath;
    net = sumolib.net.readNet(network_filepath)
    edge = net.getEdge(edge_id)
    from_n = edge.getFromNode(); to_n = edge.getToNode();
    from_n_id = from_n.getID(); to_n_id = to_n.getID();
    
    net_tree = ET.parse(network_filepath)
    net_root = net_tree.getroot()
    nodes_filepath = "new_nodes.nod.xml"
    edges_filepath = "new_edges.edg.xml"
    with open(nodes_filepath, 'w') as file: file.write("<nodes></nodes>");
    with open(edges_filepath, 'w') as file: file.write("<edges></edges>");
    nodes_tree = ET.parse(nodes_filepath); edges_tree = ET.parse(edges_filepath);
    nodes_root = nodes_tree.getroot(); edges_root = edges_tree.getroot();

    ## Copy all edges
    for junction in net_root.findall("junction"):
        if junction.get("id")[0] != ":":
            ET.SubElement(nodes_root, "node", {
                    "id" : junction.get("id"),
                    "type" : junction.get("type"),
                    "x" : junction.get("x"),
                    "y" : junction.get("y")
                })
    for edge in net_root.findall("edge"):
        if edge.get("id")[0] != ":":
            ET.SubElement(edges_root, "edge", {
                    "id" : edge.get("id"),
                    "from" : edge.get("from"),
                    "to" : edge.get("to")
                })

    ## Remove existing edges
    element = edges_root.find("edge[@from='" + str(from_n_id) + "'][@to='" + str(to_n_id) + "']")
    if (element): edges_root.remove(element);
    element = edges_root.find("edge[@from='" + str(to_n_id) + "'][@to='" + str(from_n_id) + "']")
    if (element): edges_root.remove(element);
    #net_tree.write(output_path)

    
    ## Create junction and connect
    x_from, y_from = from_n.getCoord(); x_to, y_to = to_n.getCoord();
    dx = x_to - x_from; dy = y_to - y_from; length = math.sqrt(pow(dx, 2) + pow(dy, 2));
    norm_dx = dx / length; norm_dy = dy / length;
    x_mid = x_from + (dx / 2); y_mid = y_from + (dy / 2);
    offset += 7.2; # netconvert shortens it

    entry_id = getEntryID(edge_id, parknet_id); park_id = getParkingID(edge_id, parknet_id);
    addNode(nodes_root, entry_id, x_mid, y_mid)
    addNode(nodes_root, park_id, x_mid + (offset * -norm_dy), y_mid + (offset * -norm_dx), "dead_end")

    addEdge(edges_root, str(from_n_id) + "_" + entry_id, from_n_id, entry_id)
    addEdge(edges_root, entry_id + "_" + str(from_n_id), entry_id, from_n_id)
    addEdge(edges_root, str(to_n_id) + "_" + entry_id, to_n_id, entry_id)
    addEdge(edges_root, entry_id + "_" + str(to_n_id), entry_id, to_n_id)
    addEdge(edges_root, entry_id + "_" + park_id, entry_id, park_id)
    addEdge(edges_root, park_id + "_" + entry_id, park_id, entry_id)

    #addLane(edges_root, entry_id + "_" + park_id, length=offset)
    #addLane(edges_root, park_id + "_" + entry_id, length=offset)

    nodes_tree.write(nodes_filepath); edges_tree.write(edges_filepath);
    print(check_output([netconvertBinary,
                        '--no-turnarounds', 'true',
                        #'-s', output_path,
                        '-n', nodes_filepath,
                        '-e', edges_filepath,
                        '-o', output_path]))
    #os.remove(nodes_filepath); os.remove(edges_filepath);
"""
