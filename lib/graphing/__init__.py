import networkx as nx
import sumolib
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import numpy as np
import heapq
import math
import random
from datetime import datetime
#import numpy as np

import lib.algorithms as alg

from lib.globalVars import *

from lib.structs.edgepoint import EdgePoint
from lib.structs.maxheap import TupleMaxHeap
from lib.structs.vector import normalizeVector


import lib.graphing.astar as astar
import lib.graphing.utility as util
import lib.graphing.draw as graphdraw



#### Network to networkx graph
def netToGraph(net_xml_filepath, net=None,
               lengths=True, travel_time=False,             # edge attributes
               internal_lengths=True, node_position=True    # node attributes
               ):
    if net is None: net = sumolib.net.readNet(net_xml_filepath);
    net_internal = sumolib.net.readNet(net_xml_filepath, withInternal=True)
    G = nx.DiGraph()
    if (node_position or internal_lengths):
        attrs = {}
        for node in net.getNodes():
            node_id = node.getID();
            G.add_node(node_id); attrs[node_id] = {};
            if internal_lengths:
                internal_lengths = {}
                # Get all outgoing edges
                for conn in node.getConnections():
                    cn_from_id = conn.getFrom().getFromNode().getID()
                    cn_to_id = conn.getTo().getToNode().getID()
                    lane = net_internal.getLane(conn.getViaLaneID())
                    if (cn_from_id not in internal_lengths):
                        internal_lengths[cn_from_id] = {};
                    internal_lengths[cn_from_id][cn_to_id] = float(lane.getLength())
                attrs[node_id]["intLens"] = internal_lengths
            if node_position:
                x, y = node.getCoord(); attrs[node_id]["pos"] = (float(x), float(y));
        nx.set_node_attributes(G, attrs)
    attrs = {}
    for edge in net.getEdges():
        from_id = edge.getFromNode().getID(); to_id = edge.getToNode().getID();
        G.add_edge(from_id, to_id, id=edge.getID()) #length=length, traveltime=travel_t)
        if lengths or travel_time:
            edge_nxid = (from_id, to_id)
            attrs[edge_nxid] = {}
            length = float(edge.getLength());
            if lengths: attrs[edge_nxid]["length"] = length;
            if travel_time:
                speed = float(edge.getSpeed());
                travel_t = length / speed;
                attrs[edge_nxid]["travelTime"] = travel_t;
    nx.set_edge_attributes(G, attrs)
    return G
def netToDetailedGraph(net_xml_filepath, save_position=True, save_junction_deg=True, add_road_centers=False):
    net = sumolib.net.readNet(net_xml_filepath)
    net_internal = sumolib.net.readNet(net_xml_filepath, withInternal=True)
    G = nx.DiGraph()
    pos = {}; degs = {}
    for edge in net.getEdges():
        from_node = edge.getFromNode(); to_node = edge.getToNode();
        from_id = from_node.getID(); to_id = to_node.getID();
        length = edge.getLength();
        start = util.genNodeEdgeID(from_id, to_id); end = util.genNodeEdgeID(to_id, from_id);
        if add_road_centers:
            if from_id < to_id: dn_id = util.getRoadIDFromNodes(from_id, to_id);
            else: dn_id = util.getRoadIDFromNodes(to_id, from_id);
            length_h = length / 2.0;
            G.add_edge(start, dn_id, length=length_h);
            G.add_edge(dn_id, end, length=length_h);
            if save_position:
                from_x, from_y = from_node.getCoord(); to_x, to_y = to_node.getCoord();
                from_x = float(from_x); from_y = float(from_y); to_x = float(to_x); to_y = float(to_y);
                pos[dn_id] = (from_x + ((to_x - from_x) / 2.0), from_y + ((to_y - from_y) / 2.0));
        else:
            G.add_edge(start, end, length=length);
    for node in net.getNodes():
        for conn in node.getConnections():
            length = net_internal.getLane(conn.getViaLaneID()).getLength()
            from_edge = conn.getFrom(); to_edge = conn.getTo();
            start_node_id = from_edge.getFromNode().getID();
            mid_node_id = from_edge.getToNode().getID();
            end_node_id = to_edge.getToNode().getID();
            if start_node_id != end_node_id:
                start = util.genNodeEdgeID(mid_node_id, start_node_id);
                end = util.genNodeEdgeID(mid_node_id, end_node_id);
                G.add_edge(start, end, length=length);
    if save_position or save_junction_deg:
        for node in G.nodes:
            if util.isNodeEdge(node):
                from_node_id, to_node_id = util.getNodesFromNodeEdgeID(node);
                from_node = net.getNode(from_node_id); to_node = net.getNode(to_node_id)
                if save_position:
                    from_x, from_y = from_node.getCoord(); to_x, to_y = to_node.getCoord();
                    from_x = float(from_x); from_y = float(from_y); to_x = float(to_x); to_y = float(to_y);
                    direction = normalizeVector(to_x - from_x, to_y - from_y)
                    pos[node] = (from_x + (10 * direction[0]), from_y + (10 * direction[1]))
                if save_junction_deg:
                    junc_deg = len(from_node.getIncoming())
                    degs[node] = junc_deg
            else:
                degs[node] = 2;
        if save_position:
            nx.set_node_attributes(G, pos, "pos")
        if save_junction_deg:
            nx.set_node_attributes(G, degs, "junctionDegree")
    return G

#### Networkx graph to line graph
def lineGraph(G):
    G_line = nx.line_graph(G)
    return G_line
    

#### Graph utility
def discretizeGraph(G, max_distance, add_min=0, add_max=-1, roads_only=False):
    edges = set()
    for edge in G.edges():
        if edge[0] <= edge[1]: edges.add(edge);
        else: edges.add(edge[::-1]);
    lengths = nx.get_edge_attributes(G, "length")
    for edge in edges:
        if roads_only and util.areNodeEdgesSameNode(edge[0], edge[1]):
            continue;
        length = lengths[edge]
        node_count = max(math.floor(length / max_distance), add_min)
        if add_max > 0: node_count = min(node_count, add_max)
        if node_count == 1:
            util.insertNode(G, edge[0], edge[1])
        elif node_count > 1:
            util.insertNodes(G, edge[0], edge[1], node_count, length=length)
    return

#### Global utility
def _setNet(net):
    global global_net
    global_net = net;
    print("set global net:", global_net)
def _getNode(node_id):
    global global_net
    return global_net.getNode(node_id)
def _getEdge(edge_id):
    global global_net
    print("get global net:", global_net)
    return global_net.getEdge(edge_id)



#### Algorithms
## Calculate coverage
#def calcGraphEdgeCoverage(G, centers):
    
## Calculate graph space radius
def calcGraphSpaceRadius(G, start_node, radius, nodes_only=False) -> list[EdgePoint] | list[str]:
    result = []
    checked = set()
    heap = TupleMaxHeap(); heap.push((radius, start_node));
    all_lens = nx.get_edge_attributes(G, "length")
    while len(heap) > 0:
        dis_left, node = heap.pop()
        if node not in checked:
            checked.add(node)
            conns = G.out_edges(node)
            for c in conns:
                next_node = c[1]
                if next_node not in checked:
                    distance = all_lens[c]
                    if distance <= dis_left:
                        heap.push((dis_left - distance, next_node))
                    else:
                        if nodes_only:
                            result.append(c[0])
                        else:
                            result.append(EdgePoint(G, c[0], c[1], dis_left))
    return result
## Approximate candidates for station placement
## -> vertices + edge interior points where distances balance
## ----> for now add vertices created on edges as candidates
##       (so we dont place stations on intersections)
def calcCandidates(G, detailed_graph=True):
    candidates = []
    # Add vertices
    #for node in G.nodes():
    #    candidates.append(node)
    og_verts = set(G.nodes())
    # Add points on edges
    discretizeGraph(G, 50, add_min=1, roads_only=detailed_graph)
    candidates = set(G.nodes()) - og_verts
    return candidates



        
    

    
    
    
def bestStationDistribution(G, G_d, k, seed=None):
    if seed: random.seed(seed);
    else: random.seed(datetime.now().timestamp());
    # Get candidates
    candidates = calcCandidates(G_d, detailed_graph=True)
    candidates, peri_choice, in_radius, cand_in_radius, chosen = distStats_peripheryStart(G, G_d, candidates, k, radius = 200)

    
    cand_in_radius = [(x[0]) for x in cand_in_radius]
    return candidates, peri_choice, in_radius, cand_in_radius, chosen



if __name__ == "__main__":
    node_colors = {}; edge_colors = {};
    radius = 300
    # Create graph
    G = netToGraph("manhattan/data/base_net.net.xml")
    G_d = netToDetailedGraph("manhattan/data/base_net.net.xml")
    # Calculate graph-space radius
    #print("radius:", calcGraphSpaceRadius(G_d, "A0.A1", 300))
    # A star distance
    if False:  # Path calculation and translation
        path_d = astar.detailed(G_d, "A0", "G8")
        path = translateDetailedPath(path_d)
        print("\nA* path 1:\n    detailed:", path_d, "\n    len:", pathLength(G_d, path_d))
        print("    normal:  ", path, "\n    len:", pathLength(G, path))
        path_d = astar.detailed(G_d, "A0", "G8", use_spatial_heuristic=False)
        path = util.translateDetailedPath(path_d)
        print("\nA* path 2:\n    detailed:", path_d, "\n    len:", pathLength(G_d, path_d))
        print("    normal:  ", path, "\n    len:", pathLength(G, path))
    if False:  # Edge points and paths
        a = EdgePoint(G, "A0", "A1", 0); print(a);
        b = EdgePoint(G, "B2", "C2", 0); print(b);
        path_d = astar.detailedEdgePoint(G_d, a, b)
        print("\nA* path ep:\n    detailed:", path_d);
        print("    len:", util.pathLength(G_d, path_d))
        print("    shortest len:", astar.detailedEdgePoint(G_d, a, b, length_only=True))
        path = util.translateDetailedPath(path_d)
        print("    normal:", path)
        print("    len:", util.pathLength(G, path))
    if False:  # Candidate list and farthest-first station distribution
        #discretizeGraph(G, 40)
        candidates, peri_choice, in_radius, cand_in_radius, chosen = bestStationDistribution(G, G_d, 6)
        node_colors = graphdraw.setColors({}, candidates, "lightgreen")
        node_colors[peri_choice] = "black"
        node_colors = graphdraw.setColors(node_colors, in_radius, "orange")
        node_colors = graphdraw.setColors(node_colors, cand_in_radius, "green")
        node_colors[chosen] = "purple"
    if True:   # Graph coverage
        candidates = calcCandidates(G_d, detailed_graph=True)
        radius, stations = alg.radiusBinarySearch(G, G_d, candidates, 7, epsilon=1,
                                                  distribution_alg=alg.farthestFirstCoverageBased)
        print(f"final radius = {radius}\n-- stations [{len(stations)}]:\n", stations)
        #node_colors = setColors({}, candidates, "lightgreen")
        nodes_covered = set(); edges_covered = set();
        for i in range(len(stations)):
            nodes_covered = nodes_covered.union(util.getNodesInRadius(G_d, stations[i], radius))
            edges_covered = edges_covered.union(util.getEdgesInRadius(G_d, stations[i], radius, ignore_edges=edges_covered))
        node_colors = graphdraw.setColors(node_colors, nodes_covered, "lightgreen")
        edge_colors = graphdraw.setColors({}, edges_covered, "lightgreen")
        node_colors = graphdraw.setColors(node_colors, stations, "green")
    # Draw graph
    graphdraw.drawGraph(G_d, node_colors=node_colors, edge_colors=edge_colors, base_color="lightblue", node_labels=False, edge_labels=False)
    plt.show()











#### BACKUP
"""
def aStarPath(G, start = None, target = None, use_spatial_heuristic=True, weight="length"):
    def spatial_heuristic(node_a, node_b):
        pos_a = G.nodes[node_a]["pos"]; pos_b = G.nodes[node_b]["pos"];
        return pow(pos_b[0] - pos_a[0], 2) + pow(pos_b[1] - pos_a[1], 2)
    return nx.astar_path(G, start, target,
                         heuristic = spatial_heuristic if use_spatial_heuristic else None,
                         weight=weight)
def netToDetailedGraph_xml(net_xml_filepath, save_position=True):
    def seperateNodeIDs(name_id):
        if '-' in name_id: from_id = name_id[:name_id.index('-')]; to_id = name_id[name_id.index('-')+1:];
        else: from_id = name_id[:2]; to_id = name_id[2:];
        return from_id, to_id;
    tree = ET.parse(net_xml_filepath)
    root = tree.getroot()
    G = nx.DiGraph()
    for edge in root.findall("edge"):
        if edge.get("id")[0] != ":":
            from_id = edge.get("from"); to_id = edge.get("to");
            length = float(edge[0].get("length"))
            start = from_id + "." + to_id; end = to_id + "." + from_id;
            G.add_edge(start, end, length=length)
    for conn in root.findall("connection"):
        if conn.get("from")[0] != ":":
            via = conn.get("via")
            length = float(root.find(".//lane[@id='" + via + "']").get("length"))
            from_id = conn.get("from"); to_id = conn.get("to");
            start_id, junc_id = seperateNodeIDs(from_id)
            _, end_id = seperateNodeIDs(to_id)
            if start_id != end_id:
                G.add_edge(junc_id + "." + start_id, junc_id + "." + end_id, length=length);
    if save_position:
        pos = {}
        for node in G.nodes:
            from_jid = node[:node.index('.')]
            to_jid = node[node.index('.')+1:];
            from_junc = root.find("junction[@id='" + from_jid + "']");
            to_junc = root.find("junction[@id='" + to_jid + "']");
            from_coords = (float(from_junc.get("x")), float(from_junc.get("y")))
            to_coords = (float(to_junc.get("x")), float(to_junc.get("y")))
            direction = normalizeVector(to_coords[0] - from_coords[0], to_coords[1] - from_coords[1])
            pos[node] = (from_coords[0] + (10 * direction[0]), from_coords[1] + (10 * direction[1]))
        nx.set_node_attributes(G, pos, "pos")
    return G

def chooseFarthestFromCenters_OLD(G, candidates, distance_to_centers, min_distance=0):
    size = len(distance_to_centers)
    if (size == 0): raise Exception("Received empty distance array.");
    elif (size == 1): return (distance_to_centers[0][0])[0];
    else:
        ranking = dict.fromkeys(candidates, 0);
        for dis_ind in range(len(distance_to_centers)):
            for i in range(len(distance_to_centers[dis_ind])):
                node, distance = (distance_to_centers[dis_ind][i])
                if node in ranking.keys():
                    if distance < min_distance: ranking.pop(node);
                    else: ranking[node] += i;
        return min(ranking.keys(), key=lambda e: ranking[e])
"""
