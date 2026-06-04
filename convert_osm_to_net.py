from os import listdir
from os.path import isfile, join
import time
import xml.etree.ElementTree as ET
from subprocess import call, check_output, DEVNULL

from tqdm.auto import tqdm

import networkx as nx
import osmnx as ox

import sumolib
netconvertBinary = sumolib.checkBinary('netconvert')

import lib.graphing as graphing

import lib.xml.parkingNetGen as parkingNetGen



class Node:
    #id
    #lat
    #lon
    #name
    #crossing   :   priority, priority_stop, unregulated,
    #               traffic_light, traffic_light_right_on,
    #               (zipper), (dead_end [auto set])

    def __init__(self, node_id, lat, lon):
        self.id = node_id
        self.lat = lat
        self.lon = lon
        self.name = None
        self.crossing = None
    def __repr__(self):
        s = f"Node({self.id}"
        if self.name is None: pass; #s += ", /";
        else: s += f", {self.name}";
        s += f", ({self.lat}, {self.lon})"
        if self.crossing is not None:
            s += f", {self.crossing}"
        return s + ")"
class Edge:
    #id
    #name
    #nodes
    #lanes
    #oneway
    #tags

    def __init__(self, edge_id):
        self.id = edge_id
        self.name = None
        self.nodes = []
        self.lanes = 1
        self.oneway = False
        self.tags = set()
    def addNode(self, node_id):
        self.nodes.append(node_id)
    def addTag(self, tag):
        self.tags.add(tag)
    def __repr__(self):
        s = f"Edge({self.id}"
        if self.name is None: pass; #s += ", /";
        else: s += f", {self.name}";
        s += f", |{self.lanes}|"
        s += ",["; first = True;
        for node_id in self.nodes:
            if first: first = False;
            else: s += ", ";
            s += str(node_id)
        s += "]"
        if len(self.tags) > 0:
            s += ", {"; first = True;
            for tag in self.tags:
                if first: first = False;
                else: s += ", ";
                s += str(tag)
            s += "}"
        return s + ")"

HIGHWAY_DRIVEABLE = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "residential",
    "unclassified",
    "living_street",
    "service"
}
global PROGRESS_BAR
PROGRESS_BAR = False
INCLUDE_OUT_BOUNDS = True

SPEEDS = {
    "motorway": 33.3,
    "trunk": 27.8,
    "primary": 22.2,
    "secondary": 16.7,
    "tertiary": 13.9,
    "residential": 13.9,
    "service": 8.3
}


# Utility
def findOSMFile(path):
    filename = None;
    files = [f for f in listdir(path) if isfile(join(path, f))]
    for f in files:
        if f.endswith(".osm"):
            if filename is None: filename = f;
            else:
                print("ERROR: Multiple .osm files found.")
                exit()
    return filename;

def parseTags(way_el, edge, node_crossings):
    is_road = None;
    for tag_el in way_el.findall("tag"):
        match (tag_el.get("k")):
            case "name":
                edge.name = tag_el.get("v")
            case "lanes":
                edge.lanes = int(tag_el.get("v"))
            case "highway":
                is_road = (tag_el.get("v") in HIGHWAY_DRIVEABLE)
            case "crossing":
                cross_type = None;
                match (tag_el.get("v")):
                    case "traffic_signals": cross_type = "traffic_light";
                if len(edge.nodes) == 3:
                    node_crossings[edge.nodes[1]] = cross_type;
            case "oneway":
                if tag_el.get("v") == "yes":
                    edge.oneway = True;
    return is_road;

###### Base
def edgeElement(root, edge, i, index=None, reverse=False):
    if index is None: index = i;
    edge_el = ET.SubElement(root, "edge")
    road_id = str(edge.id)
    #if len(edge.nodes) > 2:
    road_id += "_" + str(index);
    edge_el.set("id", road_id)
    if reverse:
        edge_el.set("from", str(edge.nodes[i + 1])); edge_el.set("to", str(edge.nodes[i]));
    else:
        edge_el.set("from", str(edge.nodes[i])); edge_el.set("to", str(edge.nodes[i + 1]));
    edge_el.set("numLanes", str(edge.lanes))
    if edge.name is not None: edge_el.set("name", edge.name);
    #return edge_el


###### Low
## List to tree
def nodesToTree(tree, nodes, lat_min, lat_max, lon_min, lon_max, scale=100.0):
    lat_range = lat_max - lat_min; lon_range = lon_max - lon_min;
    root = tree.getroot()
    for node in nodes:
        x = ((node.lon - lon_min) / lon_range) * scale
        y = ((node.lat - lat_min) / lat_range) * scale
        node_el = ET.SubElement(root, "node")
        junc_type = node.crossing if (node.crossing is not None) else "unregulated";
        node_el.set("id", str(node.id))
        node_el.set("type", junc_type)
        node_el.set("x", str(x)); node_el.set("y", str(y));
        if node.name is not None: node_el.set("name", node.name);
    return tree
def edgesToTree(tree, edges):
    root = tree.getroot()
    for edge in edges:
        for i in range(len(edge.nodes) - 1):
            edgeElement(root, edge, i)
        if not edge.oneway:
            offset = len(edge.nodes)
            for i in range(len(edge.nodes) - 1):
                edgeElement(root, edge, i, index=offset + i, reverse=True)
    return tree
## OSM to nodes, edges, bounds
def extractFeatures(source_tree):
    root = source_tree.getroot()
    ## Bounds
    bounds_el = root.find("bounds")
    lat_min = float(bounds_el.get("minlat")); lat_max = float(bounds_el.get("maxlat"));
    lon_min = float(bounds_el.get("minlon")); lon_max = float(bounds_el.get("maxlon"));
    ## Edges
    ways = root.findall("way")
    # Progress bar
    total = len(ways)
    print(f"\n> Edges [{total}]")
    global PROGRESS_BAR
    if PROGRESS_BAR > 0:
        pbar = tqdm(total=total, mininterval=9999);
        flush_every = int(total / PROGRESS_BAR)
        iteration = 0
    # Loop
    edges = []; edge_map = {};
    node_crossings = {};
    nodes_in_edges = {};
    for way_el in ways:
        edge_id = way_el.get("id")
        edge = Edge(edge_id)
        # nodes
        for node_ref in way_el.findall("nd"):
            node_id = int(node_ref.get("ref"))
            edge.addNode(node_id);
            if node_id not in nodes_in_edges: nodes_in_edges[node_id] = set();
            nodes_in_edges[node_id].add(edge_id);
        # tags
        is_road = parseTags(way_el, edge, node_crossings)
        if is_road is None:
            # Decide if add or not
            #edge_map[edge_id] = len(edges); edges.append(edge);
            pass;
        elif is_road:
            edge_map[edge_id] = len(edges); edges.append(edge);
        if PROGRESS_BAR:
            pbar.update(1); 
            if iteration % flush_every == 0:
                pbar.refresh();
            iteration += 1
    ## Nodes
    total = len(nodes_in_edges.keys())
    print(f"\n> Nodes [{total}]")
    if PROGRESS_BAR > 0:
        pbar = tqdm(total=total, mininterval=9999);
        flush_every = int(total / PROGRESS_BAR)
        iteration = 0
    # Loop
    nodes_to_add = set(nodes_in_edges.keys())
    nodes = []; node_map = {};
    for node_id in nodes_in_edges.keys():
        node_el = root.find(f"node[@id='{node_id}']")
        if node_el is not None:
            lat = float(node_el.get("lat")); lon = float(node_el.get("lon"));
            if INCLUDE_OUT_BOUNDS or ((lat >= lat_min and lat <= lat_max) and (lon >= lon_min and lon <= lon_max)):
                node = Node(node_id, lat, lon)
                if (name_el := node_el.find("tag[@k='name']")) is not None:
                    node.name = name_el.get("v");
                node_map[node_id] = len(nodes);
                nodes.append(node);
                nodes_to_add.remove(node_id);
        if PROGRESS_BAR:
            pbar.update(1); 
            if iteration % flush_every == 0:
                pbar.refresh();
            iteration += 1
    # Remove edges that contain non-existant nodes
    edges_to_remove = set()
    for node_id in nodes_to_add:
        edges_ids = nodes_in_edges[node_id]
        for edge_id in edges_ids:
            edges_to_remove.add(edge_id)
    edges = [e for e in edges if e.id not in edges_to_remove]
    return nodes, edges, (lat_min, lat_max, lon_min, lon_max)
## OSM to tree
# WIP
def extractNodesToTree(res_tree, source_tree, connected_nodes=None, node_crossings=None):
    # Bounds
    source_root = source_tree.getroot()
    bounds_el = source_root.find("bounds")
    min_lat = float(bounds_el.get("minlat")); max_lat = float(bounds_el.get("maxlat"));
    min_lon = float(bounds_el.get("minlon")); max_lon = float(bounds_el.get("maxlon"));
    lat_range = max_lat - min_lat; lon_range = max_lon - min_lon;
    # Nodes
    

###### Medium
def OSMToPlainXML(filepath):
    # Result XML
    res_tree = ET.ElementTree(ET.fromstring("<net></net>"))
    res_root = res_tree.getroot()
    res_root.set("junctionCornerDetail", "5"); res_root.set("limitTurnSpeed", "5.50")
    #### Parse
    tree = ET.parse(filepath)
    root = tree.getroot()
    bounds_el = root.find("bounds")
    min_lat = float(bounds_el.get("minlat")); max_lat = float(bounds_el.get("maxlat"));
    min_lon = float(bounds_el.get("minlon")); max_lon = float(bounds_el.get("maxlon"));
    lat_range = max_lat - min_lat; lon_range = max_lon - min_lon;
    # Edges
    edges = []; edge_map = {};
    connected_nodes = set();
    node_crossings = {};
    for way_el in root.findall("way"):
        edge_id = way_el.get("id")
        edge = Edge(edge_id)
        # nodes
        for node_ref in way_el.findall("nd"):
            node_id = int(node_ref.get("ref"))
            edge.addNode(node_id)
            connected_nodes.add(node_id)
        # tags
        is_road = None
        for tag_el in way_el.findall("tag"):
            match (tag_el.get("k")):
                case "name":
                    edge.name = tag_el.get("v")
                case "lanes":
                    edge.lanes = int(tag_el.get("v"))
                case "highway":
                    is_road = (tag_el.get("v") in HIGHWAY_DRIVEABLE)
                case "crossing":
                    cross_type = None;
                    match (tag_el.get("v")):
                        case "traffic_signals": cross_type = "traffic_light";
                    if len(edge.nodes) == 3:
                        node_crossings[edge.nodes[1]] = cross_type;
                case "oneway":
                    if tag_el.get("v") == "yes": edge.addTag("oneway");
        if is_road is None:
            # Decide if add or not
            edge_map[edge_id] = len(edges); edges.append(edge);
        elif is_road:
            edge_map[edge_id] = len(edges); edges.append(edge);
    # Nodes
    nodes = []; node_map = {};
    for node_id in connected_nodes:
        node_el = root.find(f"node[@id='{node_id}']")
        #node_id = node_el.get("id")
        node = Node(node_id,
                    float(node_el.get("lat")), float(node_el.get("lon")))
        if (name_el := node_el.find("tag[@k='name']")) is not None:
            node.name = name_el.get("v");
        node_map[node_id] = len(nodes);
        nodes.append(node);
    #### Convert
    # Nodes
    for node in nodes:
        x = (node.lat - min_lat) / lat_range
        y = (node.lon - min_lon) / lon_range
        node_el = ET.SubElement(res_root, "junction")
        junc_type = node.crossing if (node.crossing is not None) else "unregulated";
        node_el.set("id", str(node.id))
        node_el.set("type", junc_type)
        node_el.set("x", str(x)); node_el.set("y", str(y));
        if node.name is not None: node_el.set("name", node.name);
    # Edges
    for edge in edges:
        for i in range(len(edge.nodes) - 1):
            edge_el = ET.SubElement(res_root, "edge")
            road_id = str(edge.id)
            if len(edge.nodes) > 2: road_id += "_" + str(i);
            edge_el.set("id", road_id)
            edge_el.set("from", str(edge.nodes[i]))
            edge_el.set("to", str(edge.nodes[i + 1]))
            edge_el.set("numLanes", str(edge.lanes))
            if edge.name is not None: edge_el.set("name", edge.name);
    return res_tree
def OSMToNetFeatures(filepath, scale=100.0):
    # Result XMLs
    nodes_tree = ET.ElementTree(ET.fromstring("<nodes></nodes>"))
    edges_tree = ET.ElementTree(ET.fromstring("<edges></edges>"))
    #### Parse
    source_tree = ET.parse(filepath)
    nodes, edges, bounds = extractFeatures(source_tree)
    #### Convert
    # Nodes
    nodesToTree(nodes_tree, nodes, *bounds, scale=scale)
    # Edges
    edgesToTree(edges_tree, edges)
    return nodes_tree, edges_tree

###### High
def convertToPlainNetXML(network_name, filename=""):
    network_path = "networks/" + network_name
    # Find the .osm if filename not given
    if filename == "": filename = findOSMFile(network_path);
    # Convert to plain tree
    res_tree = OSMToPlainXML(network_path + filename)
    ET.indent(res_tree, space=' ' * 4)
    res_tree.write("plain_net.xml", encoding="UTF-8")
    return
def convertNetwork(network_name, filename="", scale=10000.0, progress_bar_debugs=10):
    global PROGRESS_BAR; PROGRESS_BAR = progress_bar_debugs;
    network_path = "networks/" + network_name + "/"
    # Find the .osm if filename not given
    if filename == "": filename = findOSMFile(network_path)
    # Convert to node and edge trees
    sim_stime = time.perf_counter();
    print("\nConverting...")
    nodes_tree, edges_tree = OSMToNetFeatures(network_path + filename, scale=scale)
    # Convert to net
    print("\nRunning netconvert and saving...")
    success = parkingNetGen.writeToXML(nodes_tree, edges_tree, network_path + "base_net.net.xml", delete=False)
    sim_etime = time.perf_counter();
    print()
    if success:
        print(f"Successfully converted '{network_name + '/' + filename}' to a compatible network XML at '{network_path + 'base_net.net.xml'}' in {sim_etime - sim_stime:0.2f} seconds.")
    else:
        print(f"Failed to convert '{network_path + filename}' to a compatible network XML after running for {sim_etime - sim_stime:0.2f} seconds.")


def exportOSMNXGraph(G, output_folder):
    nodes_tree = ET.ElementTree(ET.fromstring("<nodes></nodes>"))
    nodes_root = nodes_tree.getroot()
    for node_id, data in G.nodes(data=True):
        ET.SubElement(nodes_root, "node", id=str(node_id),
                       x=str(data["x"]), y=str(data["y"]))
    nodes_tree.write(output_folder + "/new_nodes.nod.xml")
    # Edges
    edges_tree = ET.ElementTree(ET.fromstring("<edges></edges>"))
    edges_root = edges_tree.getroot()
    for u, v, data in G.edges(data=True):
        # Get speed data
        highway = data.get("highway")
        if isinstance(highway, list): highway = highway[0];
        speed = SPEEDS.get(highway, 13.9)
        # Get lane data
        lanes = data.get("lanes", 1)
        # Create the element
        ET.SubElement(edges_root, "edge", id=f"{u}_{v}",
                    **{"from": str(u), "to": str(v), "speed": str(speed), "numLanes": str(lanes)})
    edges_tree.write(output_folder + "/new_edges.edg.xml")
    return


def netconvertOSM(network_name, filename=""):
    network_path = "networks/" + network_name + "/"
    # Find the .osm if filename not given
    if filename == "": filename = findOSMFile(network_path)
    # Run netconvert
    sim_stime = time.perf_counter();
    cmnd = [netconvertBinary,
            '--osm-files', network_path + filename,
            '--geometry.remove',
            '--remove-edges.by-vclass', 'pedestrian,bicycle',
            '--remove-edges.by-type', 'highway.service',
            '--keep-edges.by-vclass', 'passenger',
            '--keep-edges.components', str(1),
            '-o', network_path + "base_net.net.xml"]
    print(">", ' '.join(cmnd))
    result = call(cmnd, stdout=DEVNULL, stderr=DEVNULL)
    success = (result == 0)
    sim_etime = time.perf_counter();
    if success:
        print(f"Successfully converted '{network_name + '/' + filename}' to a compatible network XML at '{network_path + 'base_net.net.xml'}' in {sim_etime - sim_stime:0.2f} seconds.")
    else:
        print(f"Failed to convert '{network_path + filename}' to a compatible network XML after running for {sim_etime - sim_stime:0.2f} seconds.")



if __name__ == "__main__":
    netconvertOSM("Zagreb")






"""
# OSM -> OSMNX -> netconvert -> XML
def netconvertNetwork_1(network_name, filename=""):
    network_path = "networks/" + network_name + "/"
    # Find the .osm if filename not given
    if filename == "": filename = findOSMFile(network_path)
    # Convert to graph and keep only largest component
    G = ox.graph_from_xml(
        network_path + filename,
        simplify=False
    )
    G = ox.project_graph(G)
    largest = max(
        nx.weakly_connected_components(G),
        key=len
    )
    G = G.subgraph(largest)
    exportOSMNXGraph(G, network_path)
    # Run netconvert
    sim_stime = time.perf_counter();
    cmnd = [netconvertBinary,
            '--no-turnarounds.except-deadend', 'true',
            '-n', network_path + "new_nodes.nod.xml",
            '-e', network_path + "new_edges.edg.xml",
            '-o', network_path + "base_net.net.xml"]
    print(">", ' '.join(cmnd))
    result = call(cmnd, stdout=DEVNULL, stderr=DEVNULL)
    success = (result == 0)
    sim_etime = time.perf_counter();
    if success:
        print(f"Successfully converted '{network_name + '/' + filename}' to a compatible network XML at '{network_path + 'base_net.net.xml'}' in {sim_etime - sim_stime:0.2f} seconds.")
    else:
        print(f"Failed to convert '{network_path + filename}' to a compatible network XML after running for {sim_etime - sim_stime:0.2f} seconds.")
# OSM -> netconvert -> sumolib net -> nx -> XML
def netconvertNetwork_2(network_name, filename=""):
    network_path = "networks/" + network_name + "/"
    # Find the .osm if filename not given
    if filename == "": filename = findOSMFile(network_path)
    # netconvert
    sim_stime = time.perf_counter();
    cmnd = [netconvertBinary,
            '--osm-files', network_path + filename,
            '--geometry.remove',
            '--remove-edges.by-vclass', 'pedestrian,bicycle',
            '--remove-edges.by-type', 'highway.service',
            '--keep-edges.by-vclass', 'passenger',
            '--remove-edges.isolated',
            '-o', network_path + "base_net.net.xml"]
    print(">", ' '.join(cmnd))
    result = call(cmnd, stdout=DEVNULL, stderr=DEVNULL)
    success = (result == 0)
    if not success: return;
    # sumolib + nx
    net = readNet(network_path + "base_net.net.xml")
    G = graphing.netToGraph(network_path + "base_net.net.xml", net=net,
                            lengths=True, travel_time=False, internal_lengths=False, node_position=True)
    # Remove isolated
    largest = max(
        nx.weakly_connected_components(G),
        key=len
    )
    keep_nodes = set(largest)
    for edge in net.getEdges():
        if edge.isSpecial():
            continue
        u = edge.getFromNode().getID()
        v = edge.getToNode().getID()
        if u in keep_nodes and v in keep_nodes:
            keep_edges.append(edge.getID())
    # netconvert
    cmnd = [netconvertBinary,
            '--sumo-net-file', network_path + "base_net.net.xml",
            '--keep-edges.input-file', 'keepEdges.txt',
            '-o', network_path + "base_net.net.xml"]
    print(">", ' '.join(cmnd))
    result = call(cmnd, stdout=DEVNULL, stderr=DEVNULL)
    # Finish
    sim_etime = time.perf_counter();
    if success:
        print(f"Successfully converted '{network_name + '/' + filename}' to a compatible network XML at '{network_path + 'base_net.net.xml'}' in {sim_etime - sim_stime:0.2f} seconds.")
    else:
        print(f"Failed to convert '{network_path + filename}' to a compatible network XML after running for {sim_etime - sim_stime:0.2f} seconds.")
"""
