import random

import sumolib
import numpy as np
import networkx as nx
import xml.etree.ElementTree as ET

from lib.structs.edgepoint import EdgePoint
from lib.structs.trip import Trip, TripDataset

import lib.graphing as graphing  #= lib.graphing.__init__.py
import lib.graphing.utility as graphutil
#import lib.graphin.astar as astar



def getRandomEdge(net, G, G_sc, start_edge_id, min_distance=0, max_distance=0, return_length=False):
    start_edge = net.getEdge(start_edge_id)
    start_fn_id = start_edge.getFromNode().getID(); start_tn_id = start_edge.getToNode().getID();
    start_edge_t = (start_fn_id, start_tn_id)
    lens = nx.get_edge_attributes(G, "length")
    ## Get valid edges
    valid_end_edges = G_sc.edges() - (start_fn_id, start_tn_id)
    # Get only edges with length >= 1.0
    length_check = set()
    for e in valid_end_edges:
        if lens[e] >= 1.0: length_check.add(e);
    valid_end_edges = length_check
    # If min or max is set
    if min_distance > 0 or max_distance > 0:
        # Get edges outside of min_distance range
        if min_distance > 0:
            edges_in_range = graphutil.getEdgesInEdgeRadius(G_sc, start_edge_t, min_distance, use_internal=True,
                                                            include_reverse=False, include_reached=True)
            valid_end_edges -= edges_in_range    #(G_sc.edges() - edges_in_range).intersection(valid_end_edges)
            #print("MIN: " + str(min_distance) + ": " + str(len(edges_in_range)) + " / " + str(len(G.edges())) +
            #      " -> " + str(len(valid_end_edges)))
            if len(valid_end_edges) == 0:
                #print(f"WARNING: No edges detected outside of given min distance ({min_distance:8.2f}).")
                if return_length: return (None, -1)
                return None
                #print(f"WARNING: No edges detected outside of given min distance ({min_distance:8.2f}), reverting to all edges.")
                #valid_end_edges = G_sc.edges() - (start_fn_id, start_tn_id)
        # Get edges inside of max_distance range
        if max_distance > 0:
            edges_in_range = graphutil.getEdgesInEdgeRadius(G_sc, start_edge_t, max_distance, use_internal=True,
                                                            include_reverse=False, include_reached=True)
            valid_end_edges = edges_in_range.intersection(valid_end_edges)
            #print("MAX: " + str(max_distance) + ": " + str(len(edges_in_range)) + " / " + str(len(G.edges())) +
            #      " -> " + str(len(valid_end_edges)))
            if len(valid_end_edges) == 0:
                #print(f"WARNING: No edges detected inside of given max distance ({max_distance:8.2f}).")
                if return_length: return (None, 1);
                return None
                #print(f"WARNING: No edges detected inside of given max distance ({max_distance:8.2f}), reverting to all edges.")
                #valid_end_edges = G_sc.edges() - (start_fn_id, start_tn_id)
    # Otherwise infinity range
    else:
        print("Checing graph for all reachable edges...")
        edges_in_range = graphutil.getEdgesInEdgeRadius(G_sc, start_edge_t, np.inf, use_internal=True,
                                                            include_reverse=False, include_reached=True)
        valid_end_edges = (G_sc.edges() - edges_in_range).intersection(valid_end_edges)
    ## Choose
    # Choose random
    end_gedge = random.choice(list(valid_end_edges))
    # Get edge ID from net
    end_fn_id = end_gedge[0]
    end_tn_id = end_gedge[1]
    end_edge = None
    for e in net.getNode(end_fn_id).getOutgoing():
        if e.getToNode().getID() == end_tn_id:
            end_edge = e; break;
    if end_edge == None:
        print(f"{end_gedge} : ({end_fn_id}, {end_tn_id})"); print(G.edges());
    assert(end_edge != None)
    # Get path length from start edge to chosen edge
    #nodes_path_len_nx = nx.shortest_path_length(G, source=start_tn_id, target=end_fn_id, weight="length")
    nodes_path_len = graphutil.getShortestEdgePathLength(G, (start_edge.getFromNode().getID(), start_edge.getToNode().getID()),
                                                         end_gedge)
    #if nodes_path_len < min_distance: print("YO MIN (", min_distance - nodes_path_len, ")");
    #if nodes_path_len > max_distance: print("YO MAX");
    if nodes_path_len is None: print("Failed to get shortest edge path.");
    if return_length: return (end_edge.getID(), nodes_path_len)
    return end_edge.getID()

def genRandomRoute(net, G, G_sc, destination_count=1, min_distance=0.0, min_distance_per_des=0.0, max_distance=0.0, return_len=False, return_len_arr=False):
    ## Choose start point
    # Filter out nodes whose maximum distance is less than minimum distance
    start_max_distance = max_distance
    start_min_distance = min_distance
    if min_distance > 0:
        min_ecc_distance = min_distance / destination_count
        eccentricity = graphutil.eccentricity(G_sc, weight="length")
        valid_nodes = set()
        for node in net.getNodes():
            nodeID = node.getID()
            if nodeID in eccentricity and eccentricity[nodeID] > min_ecc_distance:
                valid_nodes.add(node)
        valid_nodes = list(valid_nodes)
    else: valid_nodes = list(net.getNodes())
    if len(valid_nodes) == 0:
        raise Exception(f"No valid nodes with eccentricity (maximum distance) > given (min_distance / destination_count) ({min_ecc_distance})")
    # Choose an edge of a randomly chosen valid node
    edge_lens = nx.get_edge_attributes(G, "length")
    while len(valid_nodes) > 0:
        start_from_node = random.choice(valid_nodes)
        valid_nodes.remove(start_from_node)
        candidate_edges = list(start_from_node.getOutgoing())
        # Remove edges with length < 1.0
        length_check = set()
        for ce in candidate_edges:
            ce_tuple = (ce.getFromNode().getID(), ce.getToNode().getID())
            if edge_lens[ce_tuple] >= 1.0: length_check.add(ce);
        candidate_edges = list(length_check)
        # Generate path
        while len(candidate_edges) > 0:
            route = []
            start_edge = candidate_edges.pop(random.randrange(len(candidate_edges)))
            # Set random depart point
            route.append(start_edge.getID())
            ## Generate rest
            if max_distance > 0:
                max_distance = float(float(start_max_distance) / destination_count)
            if min_distance > 0:
                total_min_distance = start_min_distance
                min_distance = float(float(start_min_distance) / destination_count)
            total_path_len = 0;
            path_lengths = []
            for i in range(destination_count - 1):
                next_edge, path_length = getRandomEdge(net, G, G_line_sc, route[i],
                                                       min_distance=max(min_distance_per_des, min_distance),
                                                       max_distance=max_distance,
                                                       return_length=True)
                route.append(next_edge)
                if next_edge == None: break;
                path_lengths.append(path_length); total_path_len += path_length;
            if route[-1] == None: continue;
            # Generate last
            if min_distance > 0 and total_path_len < total_min_distance:
                min_distance = total_min_distance - total_path_len;
            else: min_distance = 0;
            next_edge, path_length = getRandomEdge(net, G, G_line_sc, route[destination_count - 1],
                                                   min_distance=max(min_distance, min_distance_per_des),
                                                   max_distance=max_distance,
                                                   return_length=True)
            if next_edge == None: continue;
            route.append(next_edge)
            path_lengths.append(path_length); total_path_len += path_length;
            #print("-- total path length:", total_path_len)
            #print("    per des:", total_path_len / destination_count)
            if return_len_arr: return route, path_lengths
            if return_len: return route, total_path_len #sum(path_lengths)
            return route
    raise Exception(f"No valid routes found.")
    #if return_len: return (None, -1)
    #return None

def writeTrip(parent, route, trip_id=0, return_trip=False, ev_type="electric"):
    trip = ET.SubElement(parent, "trip", {
                "id" : str(trip_id), 
                "from" : str(route[0]),
                "to" : str(route[0]) if return_trip else str(route[-1]),
                "depart" : str(0),
                "type" : ev_type
            })
    via = ""; first = True;
    for stop in route[1:-1]:
        if first: first = False;
        else: via += ' ';
        via += stop
    if return_trip:
        if first: first = False;
        else: via += ' ';
        via += route[-1]
    if via != "": trip.set("via", via)
    return parent
def parseTripXMLElement(element, net, G):
    trip_id = str(element.get("id"))
    from_edge_id = str(element.get("from"))
    to_edge_id = str(element.get("to"))
    return_trip = (from_edge_id == to_edge_id)
    # Generate route and distances
    route = []; distances = [];
    route.append(from_edge_id); last_edge = net.getEdge(from_edge_id);
    via = str(element.get("via"))
    for edge_id in via.split(' '):
        edge = net.getEdge(edge_id);
        path_len = nx.shortest_path_length(G, source=last_edge.getToNode().getID(), target=edge.getFromNode().getID(),
                                           weight="length")
        distances.append(path_len); route.append(edge_id);
        last_edge = edge;
    to_edge = net.getEdge(to_edge_id)
    path_len = nx.shortest_path_length(G, source=last_edge.getToNode().getID(), target=to_edge.getFromNode().getID(),
                                       weight="length")
    distances.append(path_len); route.append(to_edge_id);
    ev_type = str(element.get("type"))
    return trip_id, Trip(route, distances, ev_type == "electric")

def main(net, G, vehicle_count, filepath, destination_count_probs=[1],
         min_distance=0, min_distance_per_des=0, max_distance=0,
         ev_pen=1, write=True):
    G_line_sc = graphing.getLargestConnected(graphing.lineGraph(G))
    tree = ET.ElementTree(ET.fromstring("<routes></routes>"))
    root = tree.getroot()
    trips = {};
    for i in range(vehicle_count):
        vType = "electric"
        if ev_pen < 1:
            if random.random() > ev_pen:
                vType = "conventional"
        # Sample destination count
        r = random.random(); total = 0;
        destination_count = 1;
        for j in range(len(destination_count_probs)):
            total += destination_count_probs[j];
            if r < total: break;
            destination_count += 1
        route, distances = genRandomRoute(net, G, G_line_sc, destination_count,
                                          min_distance=min_distance, min_distance_per_des=min_distance_per_des,
                                          max_distance=max_distance,
                                          return_len=False, return_len_arr=True)
        #print(f"[{destination_count:2d}] {route_len:8.2f} e [{min_distance:8.2f}, {max_distance:8.2f}]")
        writeTrip(root, route, trip_id=i, ev_type=vType)
        trip = Trip(route, distances, vType == "electric")
        trips[str(i)] = trip
    if write:
        ET.indent(tree); tree.write(filepath);
    return TripDataset(trips, tree)


def load(filepath, net, G):
    trips = {}
    tree = ET.parse(filepath)
    for child in tree.getroot():
        trip_id, trip = parseTripXMLElement(child, net, G)
        trips[trip_id] = trip
    return TripDataset(trips, tree)


## Utility
def overwriteVTypes(tree, value):
    root = tree.getroot()
    for trip in root.findall("trip"):
        trip.set("type", value)
    return tree
    











    
