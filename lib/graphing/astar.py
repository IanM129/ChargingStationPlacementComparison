import networkx as nx

import lib.structs.edgepoint

from lib.graphing.utility import *



#### Graph
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




# Graph with junction weights
def edgePath(G, start, target, weight="length", use_internal=True):
    if (len(start) > 2): start = (start[0], start[1]);
    if (len(target) > 2): target = (target[0], target[1]);
    import heapq
    def neighbors(edge):
        from_node, to_node = edge
        for _, n, data in G.out_edges(to_node, data=True):
            cost = float(data[weight])
            if use_internal:
                try:
                    if n not in int_lens[to_node][from_node]: continue;
                except Exception as e:
                    print("n:", n)
                    print("to_node:", to_node)
                    print("from_node:", from_node)
                    print(from_node,"->",to_node,"->",n)
                    print(int_lens)
                    raise e
                cost += float(int_lens[to_node][from_node][n])
            yield ((to_node, n), cost)
    def spatial_heuristic(edge_a, edge_b):
        pos_a = pos[edge_a[1]]; pos_b = pos[edge_b[1]];
        return pow(pos_b[0] - pos_a[0], 2) + pow(pos_b[1] - pos_a[1], 2)
    # Get node attributes
    if use_internal:
        int_lens = nx.get_node_attributes(G, "intLens")
        if len(int_lens) == 0:
            raise Exception("ERROR: Calling 'use_internal=True' on a graph without internal weights loaded.");
    pos = nx.get_node_attributes(G, "pos")
    # Initialize with starting state
    start_state = (None, start)
    open_heap = []
    heapq.heappush(open_heap, (spatial_heuristic(start, target), 0.0, start_state))
    g_score = {start_state: 0.0}
    came_from = {}
    closed_set = set()
    # Main loop
    while open_heap:
        _, current_g, state = heapq.heappop(open_heap)
        if state in closed_set: continue;
        prev_edge, cur_edge = state
        if cur_edge == target:
            path = [cur_edge];
            while state in came_from:
                state = came_from[state]
                _, edge = state
                path.append(edge)
            path.reverse()
            return path
        closed_set.add(state)
        for next_edge, cost in neighbors(cur_edge):
            next_state = (cur_edge, next_edge)
            tentative_g = current_g + cost
            if tentative_g < g_score.get(next_state, float("inf")):
                g_score[next_state] = tentative_g
                came_from[next_state] = state
                f_score = tentative_g + spatial_heuristic(next_edge, target)
                heapq.heappush(
                    open_heap,
                    (f_score, tentative_g, next_state)
                )
    start_id = G[start[0]][start[1]].get("id", "/")
    start_len = float(G.get_edge_data(start[0], start[1])[weight])
    target_id = G[target[0]][target[1]].get("id", "/")
    target_len = float(G.get_edge_data(target[0], target[1])[weight])
    print(f"ERROR: No A* path found from {start} ({start_id}) [{start_len}] -> {target} ({target_id}) [{target_len}].")
    return None



"""
def path_internalWeights(G, start, target, weight="length", previous=None, edge_path=False):
    import heapq
    def neighbors(node, previous):
        res = []
        neighbors = list(G.neighbors(node))
        for n in neighbors:
            data = G.get_edge_data(node, n)
            cost = float(data[weight])
            if previous is not None:
                if n not in int_lens[node][previous]: continue;
                cost += float(int_lens[node][previous][n])
            res.append((n, cost))
        return res
    def spatial_heuristic(node_a, node_b):
        pos_a = pos[node_a]; pos_b = pos[node_b];
        return pow(pos_b[0] - pos_a[0], 2) + pow(pos_b[1] - pos_a[1], 2)
    # Get node attributes
    int_lens = nx.get_node_attributes(G, "intLens")
    pos = nx.get_node_attributes(G, "pos")
    # Initialize with starting state
    start_previous = previous
    start_state = (start_previous, start)
    open_heap = []
    heapq.heappush(open_heap, (spatial_heuristic(start, target), 0.0, start_state))
    came_from = {}
    g_score = {start_state: 0.0}
    closed_set = set()
    # Main loop
    while open_heap:
        _, current_g, state = heapq.heappop(open_heap)
        if state in closed_set: continue;
        previous, current = state
        if current == target:
            if edge_path: path = [];
            else: path = [current];
            while state in came_from:
                if edge_path:
                    prev_state = came_from[state]
                    _, from_node = prev_state
                    _, to_node = state
                    path.append((from_node, to_node))
                    state = prev_state
                else:
                    state = came_from[state]
                    _, node = state
                    path.append(node)
            if edge_path: path.append((start_state));
            path.reverse()
            return path
        closed_set.add(state)
        for neighbor, cost in neighbors(current, previous):
            next_state = (current, neighbor)
            tentative_g = current_g + cost
            if tentative_g < g_score.get(next_state, float("inf")):
                g_score[next_state] = tentative_g
                came_from[next_state] = state
                f_score = tentative_g + spatial_heuristic(neighbor, target)
                heapq.heappush(
                    open_heap,
                    (f_score, tentative_g, next_state)
                )
    return None
"""
