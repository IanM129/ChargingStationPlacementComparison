import networkx as nx
import numpy as np
import re

from lib.globalVars import *

from lib.structs.edgepoint import EdgePoint
from lib.structs.maxheap import TupleMaxHeap
from lib.structs.trip import Trip
from lib.structs.graphtranslator import GraphTranslator


class TupleEdge:
    def __init__(self, from_node, to_node=None):
        if isinstance(from_node, tuple):
            self.__init__(from_node[0], from_node[1])
            return
        if to_node < from_node:
            self.from_node = to_node;
            self.to_node = from_node;
        else:
            self.from_node = from_node;
            self.to_node = to_node;
    def __getitem__(self, idx):
        if idx == 0: return self.from_node;
        elif idx == 1: return self.to_node;
        else: raise Exception(f"Index OOR for tuple ('{idx}')")
    def __setitem__(self, idx, value):
        if idx == 0:
            if value <= self.to_node: self.from_node = value;
            else: self.to_node = value;
        elif idx == 1:
            if value >= self.from_node: self.to_node = value;
            else: self.from_node = value;
        else: raise Exception(f"Index OOR for tuple ('{idx}')")
    def __eq__(self, other):
        #if isinstance(other, tuple):
        return self.from_node == other[0] and self.to_node == other[1];
        #return self.from_node == other.from_node and self.to_node == other.to_node;
    def __hash__(self):
        return hash((self.from_node, self.to_node))
    def __repr__(self):
        return "(" + str(self.from_node) + ", " + str(self.to_node) + ")"


def netHasNodeID(net, node_id):
    try:
        net.getNode(node_id); return True;
    except KeyError: return False;
def netHasEdgeID(net, edge_id):
    try:
        net.getEdge(edge_id); return True;
    except KeyError: return False;

## Node edge
def genNodeEdgeID(from_id : str, to_id : str) -> str:
    return from_id + NODE_EDGE_ID_SEPARATOR + to_id
def getNodesFromNodeEdgeID(node_edge_id : str) -> (str, str):
    from_node_id = node_edge_id[:node_edge_id.index(NODE_EDGE_ID_SEPARATOR)];
    to_node_id = node_edge_id[node_edge_id.index(NODE_EDGE_ID_SEPARATOR)+1:];
    return (from_node_id, to_node_id)
def isNodeEdge(n : str) -> bool:
    return NODE_EDGE_ID_SEPARATOR in n;
def areNodeEdgesSameNode(a : str, b : str) -> bool:
    from_a, _ = getNodesFromNodeEdgeID(a)
    from_b, _ = getNodesFromNodeEdgeID(b)
    return from_a == from_b


## Get nodes from road id
def getNodesFromRoadID(road_id):
    from_id = road_id[:road_id.index(ROAD_ID_SEPARATOR)]
    to_id = road_id[road_id.index(ROAD_ID_SEPARATOR)+1:]
    return (from_id, to_id)
## Get road id from nodes
def getRoadIDFromNodes(from_id, to_id):
    if to_id < from_id:
        return to_id + ROAD_ID_SEPARATOR + from_id
    return from_id + ROAD_ID_SEPARATOR + to_id
## Get road id from nodes
def getRoadIDFromTuple(edge_tuple):
    return getRoadIDFromNodes(edge_tuple[0], edge_tuple[1])

## Translate EdgePoint to detailed nodes
def getDetailedNodesFromEdgePoint(ep : EdgePoint):
    from_id = ep.start + NODE_EDGE_ID_SEPARATOR + ep.end;
    to_id = ep.end + NODE_EDGE_ID_SEPARATOR + ep.start;
    return (from_id, to_id)

## Translate detailed to normal
def translateDetailedPath(path):
    res = []; i = 0;
    while i < len(path):
        if type(path[i]) is EdgePoint:
            res.append(path[i]); i += 1;
        else:
            res.append(path[i][:path[i].index(NODE_EDGE_ID_SEPARATOR)]);
            i += 2;
    return res

## Translate detailed node to normal node
def translateDetailedNode(node_d):
    return node_d[:node_d.index(NODE_EDGE_ID_SEPARATOR)]

## Translate detailed edge to normal edge
def translateDetailedRoad(road_d, as_tuple=True):
    from_node_d, to_node_d = getNodesFromRoadID(road_d)
    from_node = translateDetailedNode(from_node_d);
    to_node = translateDetailedNode(to_node_d);
    if as_tuple: return (from_node, to_node);
    else: return (from_node + to_node);

## Translate normal edge to detailed edge node
def translateNetEdgeToDetailedEdgeID(net_edge):
    from_id = net_edge.getFromNode().getID(); to_id = net_edge.getToNode().getID();
    return from_id + NODE_EDGE_ID_SEPARATOR + to_id + ROAD_ID_SEPARATOR +\
           to_id + NODE_EDGE_ID_SEPARATOR + from_id
def translateNetEdgeToDetailedEdgeTuple(net_edge):
    from_id = net_edge.getFromNode().getID(); to_id = net_edge.getToNode().getID();
    return (from_id + NODE_EDGE_ID_SEPARATOR + to_id, to_id + NODE_EDGE_ID_SEPARATOR + from_id)
    


## Extract original edge ID from edge ID
# type: 0 - normal, 1 - detailed (WIP), 2 - charging station
def extractEdgeID(edge_id) -> tuple[str, int]:
    pattern = r'pcs(?:Entry|End)_([A-Za-z0-9]+)';
    sep_ind = edge_id.find(ROAD_ID_SEPARATOR)
    if sep_ind == -1:
        re_match = re.search(pattern, edge_id)
        if re_match:
            return (re_match.group(1), 0)
        else: return (edge_id, 0)
    else:
        first = edge_id[:sep_ind]
        second = edge_id[sep_ind+1:]
        match_l = re.search(pattern, first)
        match_r = re.search(pattern, second)
        if match_l and match_r: return (edge_id, 2);
        if match_l:
            re_match = match_l.group(1); other = second;
            other_ind = re_match.index(other)
            if other_ind == 0:
                return (re_match[len(other):] + other, 0);
            else:
                return (re_match, 0);
        elif match_r:
            re_match = match_r.group(1); other = first;
            other_ind = re_match.index(other)
            if other_ind == 0:
                return (re_match, 0);
            else:
                return (other + re_match[:other_ind], 0);
        else:
            return (edge_id, 2);

#### Pathing
## Get length of defined path
def pathLength(G, path, weight="length"):
    res = 0
    intLens = nx.get_node_attributes(G, "intLens")
    has_internal_lanes = len(intLens) > 0
    for i in range(1, len(path)):
        if (type(path[i-1]) is EdgePoint): res += path[i-1].left;
        elif (type(path[i]) is EdgePoint): res += path[i].distance;
        else:
            res += G.edges[(path[i-1], path[i])][weight]
        # Take internal lengths into account
        if i > 1 and has_internal_lanes and type(path[i-1]) != EdgePoint:
            if type(path[i]) == EdgePoint: cur = path[i].end;
            else: cur = path[i];
            mid = path[i-1];
            if type(path[i-2]) == EdgePoint: last = path[i-2].start;
            else: last = path[i-2];
            res += intLens[mid][last][cur]
    return res
def edgePathLength(G, path : list[tuple], weight="length", use_internal=True):
    res = 0
    intLens = nx.get_node_attributes(G, "intLens")
    has_internal_lanes = len(intLens) > 0 and use_internal
    for i in range(len(path)):
        if (type(path[i-1]) is EdgePoint): res += path[i-1].left;
        elif (type(path[i]) is EdgePoint): res += path[i].distance;
        else:
            res += G.edges[path[i]][weight]
        # Take internal lengths into account
        if i > 0 and has_internal_lanes and type(path[i-1]) != EdgePoint:
            if type(path[i]) == EdgePoint: cur = path[i].end;
            else: cur = path[i][1];
            mid = path[i][0];
            if type(path[i-2]) == EdgePoint: last = path[i-2].start;
            else: last = path[i-1][0];
            res += intLens[mid][last][cur]
    return res
# Wrapper function; accepts both edge ID and edge tuples
def getShortestEdgePathLength(G, source : tuple | str, target : tuple | str, translator=None, weight="length", use_internal=True):
    from lib.graphing.astar import edgePath
    # Translate to tuples
    if (not isinstance(source, tuple)):
        if translator is None: translator = GraphTranslator(G);
        source = translator.IDToEdge(source)
    if (not isinstance(target, tuple)):
        if translator is None: translator = GraphTranslator(G);
        target = translator.IDToEdge(target)
    # Main
    path = edgePath(G, source, target, weight=weight, use_internal=use_internal)
    return edgePathLength(G, path, weight=weight, use_internal=use_internal)


## Check if nodes are directly connected
def nodesConnected(G, a, b):
    return b in G.neighbors(a);

## Insert node
def insertNode(G, start_id, end_id, name="", bidirectional=True,
               offset=0.5, absolute_offset=-1, calc_pos=True):
    if not nodesConnected(G, start_id, end_id):
        raise Exception(f"Nodes ({start_id}, {end_id}) are not directly connected (aren't neighbors).")
    # Name
    if name=="": name = getRoadIDFromNodes(start_id, end_id);
    full_length = G.get_edge_data(start_id, end_id)["length"]
    # Offsets
    if absolute_offset >= 0:
        if absolute_offset > full_length:
            raise Exception(f"Given absolute offset is bigger than the length of the edge. ({absolute_offset} > {full_length})")
        len_a = absolute_offset; len_b = full_length - absolute_offset;
    else:
        len_a = full_length * offset; len_b = full_length - len_a;
    # Positions
    if calc_pos:
        start_x, start_y = G.nodes[start_id]["pos"]; end_x, end_y = G.nodes[end_id]["pos"];
        dif = (end_x - start_x, end_y - start_y)
        ratio = (dif[0] / full_length, dif[1] / full_length)
        pos = (start_x + (len_a * ratio[0]), start_y + (len_a * ratio[1]))

    # --
    if calc_pos: G.add_node(name, pos=pos)
    else: G.add_node(name)
    G.remove_edge(start_id, end_id)
    G.add_edge(start_id, name, length=len_a)
    G.add_edge(name, end_id, length=len_b)
    if (bidirectional):
        G.remove_edge(end_id, start_id)
        G.add_edge(end_id, name, length=len_b)
        G.add_edge(name, start_id, length=len_a)
    return
def insertNodes(G, start_id, end_id, count, name="", bidirectional=True,
                relative_lengths : list=None, absolute_lengths : list=None, length=None, calc_pos=True):
    if count < 2: return;
    if not nodesConnected(G, start_id, end_id):
        raise Exception(f"Nodes ({start_id}, {end_id}) are not directly connected (aren't neighbors).")
    # Name
    if name == "": name = getRoadIDFromNodes(start_id, end_id);
    # Length
    if length == None: full_length = G.get_edge_data(start_id, end_id)["length"]
    else: full_length = length;
    # Interval lengths
    if absolute_lengths != None:
        if len(absolute_lengths) != count: raise Exception("Array not equal len as count.");
        relative_lengths = None
    elif relative_lengths != None:
        if len(relative_lengths) != count: raise Exception("Array not equal len as count.");
        for i in range(count):
            absolute_lengths[i] = relative_lengths[i] * full_length
    else:
        interval_len = full_length / (count + 1);
        absolute_lengths = [interval_len] * count
    # Positions
    if calc_pos:
        start_x, start_y = G.nodes[start_id]["pos"]; end_x, end_y = G.nodes[end_id]["pos"];
        dif = (end_x - start_x, end_y - start_y)
        ratio = (dif[0] / full_length, dif[1] / full_length)
        posts = [(start_x, start_y)] * count
        for i in range(count):
            add = (absolute_lengths[i] * ratio[0], absolute_lengths[i] * ratio[1])
            for j in range(i, count):
                posts[j] = (posts[j][0] + add[0], posts[j][1] + add[1])
    # --
    G.remove_edge(start_id, end_id);
    if (bidirectional):
        G.remove_edge(end_id, start_id);
    last_id = start_id
    for i in range(count):
        cur_id = name + "_" + str(i);
        if calc_pos: G.add_node(cur_id, pos=posts[i]);
        else: G.add_node(cur_id)
        G.add_edge(last_id, cur_id, length=absolute_lengths[i])
        if (bidirectional):
            G.add_edge(cur_id, last_id, length=absolute_lengths[i])
        last_id = cur_id
    G.add_edge(last_id, end_id, length=absolute_lengths[count - 1])
    if (bidirectional):
        G.add_edge(end_id, last_id, length=absolute_lengths[count-1])
    return

#### Radius calculations
## Inside radius
def getNodesInRadius(G, center, radius, reverse_roads=False) -> set:
    if center not in G:
        raise Exception(f"Node {center} not in graph!")
    checked = set()
    heap = TupleMaxHeap(); heap.push((radius, center));
    all_lens = nx.get_edge_attributes(G, "length")
    while len(heap) > 0:
        dis_left, node = heap.pop()
        if node not in checked:
            checked.add(node)
            conns = G.in_edges(node) if reverse_roads else G.out_edges(node)
            for c in conns:
                next_node = c[0] if reverse_roads else c[1]
                if next_node not in checked:
                    distance = all_lens[c]
                    if distance <= dis_left:
                        heap.push((dis_left - distance, next_node))
    return checked
def getNodesInRadius_withDistance(G, center, radius, reverse_roads=False) -> dict:
    if center not in G:
        raise Exception(f"Node {center} not in graph!")
    result = {};
    heap = TupleMaxHeap(); heap.push((radius, center));
    all_lens = nx.get_edge_attributes(G, "length")
    while len(heap) > 0:
        dis_left, node = heap.pop()
        if node not in result.keys():
            result[node] = radius - dis_left
            conns = G.in_edges(node) if reverse_roads else G.out_edges(node)
            for c in conns:
                next_node = c[0] if reverse_roads else c[1]
                if next_node not in result.keys():
                    distance = all_lens[c]
                    if distance <= dis_left:
                        heap.push((dis_left - distance, next_node))
    return result
def getEdgesInRadius(G, center, radius, ignore_edges=None, include_reverse=True, include_reached=False) -> set:
    nodes_checked = set()
    edges_covered = set()
    heap = TupleMaxHeap(); heap.push((radius, center));
    all_lens = nx.get_edge_attributes(G, "length")
    while len(heap) > 0:
        dis_left, node = heap.pop()
        if node not in nodes_checked:
            nodes_checked.add(node)
            conns = G.out_edges(node)
            for c in conns:
                if ignore_edges != None and c in ignore_edges:
                    continue;
                next_node = c[1]
                if next_node not in nodes_checked:
                    distance = all_lens[c]
                    if distance <= dis_left:
                        heap.push((dis_left - distance, next_node))
                    if distance <= dis_left or include_reached:
                        edges_covered.add(c)
                        if include_reverse:
                            edges_covered.add((c[1], c[0]))
    return edges_covered
## At edge of radius
def getValidNodesAtRadius(G, start_node, radius, valid) -> dict:
    result = {}
    checked = set()
    heap = TupleMaxHeap(); heap.push((radius, (start_node, (None, 0))));
    all_lens = nx.get_edge_attributes(G, "length")
    while len(heap) > 0:
        dis_left, data = heap.pop()
        node, last_valid_data = data
        if node not in checked:
            checked.add(node)
            conns = G.out_edges(node)
            for c in conns:
                next_node = c[1]
                if next_node not in checked:
                    distance = all_lens[c]
                    if distance <= dis_left:
                        next_dis_left = dis_left - distance
                        if next_node in valid:
                            heap.push((next_dis_left, (next_node, (next_node, next_dis_left))))
                        else:
                            heap.push((next_dis_left, (next_node, last_valid_data)))
                    else:
                        if c[0] in valid:
                            if c[0] not in result.keys():
                                result[c[0]] = radius - dis_left;
                        else:
                            last_valid_node, last_valid_dis_left = last_valid_data
                            if last_valid_node not in result.keys():
                                result[last_valid_node] = radius - last_valid_dis_left;
    return result
# !UNTESTED!
def getEdgePointsAtRadius(G, start_ep, radius) -> set:
    result = set()
    checked = set()
    start_node_s = start_ep.start; start_node_e = start_ep.end
    heap = TupleMaxHeap();
    heap.push((radius - start_ep.distance, start_node_s));
    heap.push((radius - start_ep.left, start_node_e));
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
                        next_dis_left = dis_left - distance
                        heap.push((next_dis_left, next_node))
                    else:
                        result.add(EdgePoint(G, node, next_node, dis_left))
    return result

