import random

import sumolib
import networkx as nx
import xml.etree.ElementTree as ET

from lib.structs.edgepoint import EdgePoint
from lib.structs.trip import Trip, TripDataset

import lib.graphing.utility as graphutil



def getRandomEdge(net, G, start_edge_id, min_distance=0, max_distance=0, return_length=False):
    start_edge = net.getEdge(start_edge_id)
    start_fn_id = start_edge.getFromNode().getID(); start_tn_id = start_edge.getToNode().getID();
    ## Get valid edges
    valid_end_edges = G.edges() - (start_fn_id, start_tn_id)
    # Get edges outside of min_distance range
    if min_distance > 0:
        edges_in_range = graphutil.getEdgesInRadius(G, start_tn_id, min_distance,
                                                    include_reverse=True, include_reached=True)
        valid_end_edges = (G.edges() - edges_in_range).intersection(valid_end_edges)
        if len(valid_end_edges) == 0:
            if return_length: return (None, -1)
            return None
            #print(f"WARNING: No edges detected outside of given min distance ({min_distance:8.2f}), reverting to all edges.")
            #valid_end_edges = G.edges() - (start_fn_id, start_tn_id)
    # Get edges inside of max_distance range
    if max_distance > 0:
        edges_in_range = graphutil.getEdgesInRadius(G, start_tn_id, max_distance,
                                                    include_reverse=True)
        valid_end_edges = edges_in_range.intersection(valid_end_edges)
        if len(valid_end_edges) == 0:
            if return_length: return (None, 1);
            return None
            #print(f"WARNING: No edges detected inside of given max distance ({max_distance:8.2f}), reverting to all edges.")
            #valid_end_edges = G.edges() - (start_fn_id, start_tn_id)
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
    nodes_path_len = nx.shortest_path_length(G, source=start_tn_id, target=end_fn_id, weight="length")
    #print("path:", nx.shortest_path(G, source=start_tn_id, target=end_fn_id, weight="length"))
    #print("-> full len:", (nodes_path_len))
    #if nodes_path_len < min_distance: print("YO MIN (", min_distance - nodes_path_len, ")");
    #if nodes_path_len > max_distance: print("YO MAX");
    if return_length: return (end_edge.getID(), nodes_path_len)
    return end_edge.getID()

def genRandomRoute(net, G, destination_count=1, min_distance=0.0, min_distance_per_des=0.0, max_distance=0.0, return_len=False, return_len_arr=False):
    #print("min_distance:", min_distance)
    #print("max_distance:", max_distance)
    ## Choose start point
    # Filter out nodes whose maximum distance is less than minimum distance
    start_max_distance = max_distance
    start_min_distance = min_distance
    if min_distance > 0:
        min_ecc_distance = min_distance / destination_count
        eccentricity = graphutil.getEccentricity(G, weight="length") #nx.eccentricity(G, weight="length")
        valid_nodes = set()
        for node in net.getNodes():
            nodeID = node.getID()
            if eccentricity[nodeID] > min_ecc_distance:
                valid_nodes.add(node)
        valid_nodes = list(valid_nodes)
    else: valid_nodes = list(net.getNodes())
    if len(valid_nodes) == 0:
        raise Exception(f"No valid nodes with eccentricity (maximum distance) > given (min_distance / destination_count) ({min_ecc_distance})")
    # Choose an edge of a randomly chosen valid node
    while len(valid_nodes) > 0:
        start_from_node = random.choice(valid_nodes)
        valid_nodes.remove(start_from_node)
        candidate_edges = list(start_from_node.getOutgoing())
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
                next_edge, path_length = getRandomEdge(net, G, route[i],
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
            next_edge, path_length = getRandomEdge(net, G, route[destination_count - 1],
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
        route, distances = genRandomRoute(net, G, destination_count,
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
    




















""" FULL
    print("min distance:", min_distance)
    print("max distance:", max_distance)
    # Filter out nodes whose maximum distance is less than minimum distance
    if min_distance > 0:
        eccentricity = nx.eccentricity(G, weight="length")
        valid_nodes = set()
        for node in net.getNodes():
            nodeID = node.getID()
            if eccentricity[nodeID] > min_distance:
                valid_nodes.add(node)
        valid_nodes = list(valid_nodes)
    else: valid_nodes = list(net.getNodes())
    if len(valid_nodes) == 0:
        raise Exception(f"No valid nodes with eccentricity (maximum distance) > given min_distance ({min_distance})")
    # Choose an edge of a randomly chosen valid node
    start_from_node = random.choice(valid_nodes)
    start_edge = random.choice(start_from_node.getOutgoing())
    print("start edge:", start_edge)
    start_to_node = start_edge.getToNode()
    # Set random depart point
    start_len = start_edge.getLength()
    start_point = EdgePoint(G, start_from_node.getID(),
                            start_to_node.getID(),
                            random.uniform(0, start_len))
    print("start point:", start_point)
    ## Get valid edges
    valid_end_edges = G.edges() - (start_from_node.getID(), start_to_node.getID())
    # Get edges outside of min_distance range
    if min_distance > 0:
        remain_min_distance = min_distance - start_point.left
        edges_in_range = graphutil.getEdgesInRadius(G, start_to_node.getID(),
                                                  remain_min_distance,
                                                  include_reverse=True)
        valid_end_edges = (G.edges() - edges_in_range).intersection(valid_end_edges)
        if len(valid_end_edges) == 0:
            print(f"WARNING: No edges detected outside of given min distance ({min_distance}), reverting to all edges.")
            valid_end_edges = G.edges() - (start_from_node.getID(), start_to_node.getID())
    # Get edges inside of max_distance range
    if max_distance > 0:
        remain_max_distance = max_distance - start_point.left
        edges_in_range = graphutil.getEdgesInRadius(G, start_to_node.getID(),
                                                  remain_max_distance,
                                                  include_reverse=True)
        valid_end_edges = edges_in_range.intersection(valid_end_edges)
        if len(valid_end_edges) == 0:
            print(f"WARNING: No edges detected inside of given max distance ({max_distance}), reverting to all edges.")
            valid_end_edges = G.edges() - (start_from_node.getID(), start_to_node.getID())
    # Choose random
    end_gedge = random.choice(list(valid_end_edges))
    end_from_node = end_gedge[0]
    end_to_node = end_gedge[1]
    end_edge = None
    for e in net.getNode(end_from_node).getOutgoing():
        if e.getToNode().getID() == end_to_node:
            end_edge = e; break;
    assert(end_edge != None)
    # Get path length from start edge to chosen edge
    nodes_path_len = nx.shortest_path_length(G, source=start_to_node.getID(), target=end_gedge[0], weight="length")
    end_len = end_edge.getLength()
    diff = (nodes_path_len + end_len) - max_distance
    if diff > 0: end_len -= diff;
    print("path:", nodes_path_len)
    end_point = EdgePoint(G, end_gedge[0], end_gedge[1], random.uniform(0, end_len))
    print("end point:", end_point)
    print("-> full len:", (start_point.left + nodes_path_len + end_point.distance))
"""
    
