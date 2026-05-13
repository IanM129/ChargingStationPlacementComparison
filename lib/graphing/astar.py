import networkx as nx

import lib.structs.edgepoint

from lib.graphing.utility import *




## A*, with default use of spatial heuristic
def path(G, start = None, target = None, use_spatial_heuristic=True, weight="length"):
    def spatial_heuristic(node_a, node_b):
        pos_a = G.nodes[node_a]["pos"]; pos_b = G.nodes[node_b]["pos"];
        return pow(pos_b[0] - pos_a[0], 2) + pow(pos_b[1] - pos_a[1], 2)
    return nx.astar_path(G, start, target,
                         heuristic = spatial_heuristic if use_spatial_heuristic else None,
                         weight=weight)
def detailed(G, start = None, target = None, length_only=False, use_spatial_heuristic=True, weight="length"):
    def spatial_heuristic(node_a, node_b):
        pos_a = G.nodes[node_a]["pos"]; pos_b = G.nodes[node_b]["pos"];
        return pow(pos_b[0] - pos_a[0], 2) + pow(pos_b[1] - pos_a[1], 2)
    start_arr = []; target_arr = [];
    for node in G.nodes:
        if start != None and node.startswith(start): start_arr.append(node);
        if target != None and node.startswith(target): target_arr.append(node);
    start = start_arr if (start != None) else [None];
    target = target_arr if (target != None) else [None];
    paths = []
    for s in start:
        for t in target:
            path = nx.astar_path(G, s, t,
                                 heuristic=spatial_heuristic if use_spatial_heuristic else None,
                                 weight=weight)
            path_len = pathLength(G, path);
            heapq.heappush(paths, (path_len, path));
    return heapq.heappop(paths)[1]
# Uses detailed graph; start and target are EdgePoints (using normal nodes, not detailed nodes)
def detailedEdgePoint(G, start : EdgePoint = None, target : EdgePoint = None, length_only=False, use_spatial_heuristic=True, weight="length"):
    def spatial_heuristic(node_a, node_b):
        pos_a = G.nodes[node_a]["pos"]; pos_b = G.nodes[node_b]["pos"];
        return pow(pos_b[0] - pos_a[0], 2) + pow(pos_b[1] - pos_a[1], 2)
    if start != None or target != None:
        G = G.copy()
        if start != None:
            from_id_d, to_id_d = getDetailedNodesFromEdgePoint(start)
            length = G.get_edge_data(from_id_d, to_id_d)["length"]
            G.remove_edge(from_id_d, to_id_d); G.remove_edge(to_id_d, from_id_d);
            if use_spatial_heuristic:
                from_pos = G.nodes[from_id_d]["pos"]; to_pos = G.nodes[to_id_d]["pos"];
                dif = (to_pos[0] - from_pos[0], to_pos[1] - from_pos[1]);
                G.add_node("start", pos=(from_pos[0] + (dif[0] / 2), from_pos[1] + (dif[1] / 2)))
            G.add_edge(from_id_d, "start", length=start.distance);
            G.add_edge("start", to_id_d, length=length-start.distance);
        if target != None:
            from_id_d, to_id_d = getDetailedNodesFromEdgePoint(target)
            length = G.get_edge_data(from_id_d, to_id_d)["length"]
            G.remove_edge(from_id_d, to_id_d); G.remove_edge(to_id_d, from_id_d);
            if use_spatial_heuristic:
                from_pos = G.nodes[from_id_d]["pos"]; to_pos = G.nodes[to_id_d]["pos"];
                dif = (to_pos[0] - from_pos[0], to_pos[1] - from_pos[1]);
                G.add_node("target", pos=(from_pos[0] + (dif[0] / 2), from_pos[1] + (dif[1] / 2)))
            G.add_edge(from_id_d, "target", length=start.distance);
            G.add_edge("target", to_id_d, length=length-start.distance);
    if length_only:
        return nx.astar_path_length(G, "start" if start!=None else None,
                                    "target" if target!=None else None,
                                    heuristic=spatial_heuristic if use_spatial_heuristic else None,
                                    weight=weight)
    else:
        path = nx.astar_path(G, "start" if start!=None else None,
                             "target" if target!=None else None,
                             heuristic=spatial_heuristic if use_spatial_heuristic else None,
                             weight=weight)
        if start != None: path[0] = start;
        if target != None: path[-1] = target;
        return path
        
