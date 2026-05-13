import random

import sumolib
import networkx as nx
import xml.etree.ElementTree as ET

from lib.structs import EdgePoint

import lib.graphing.utility as graphutil


def getRandomEdgePoint(net, G, start_point, min_distance=0, max_distance=0, return_length=False):
    #print("start point:", start_point)
    start_from_node = start_point.start; start_to_node = start_point.end;
    ## Get valid edges
    valid_end_edges = G.edges() - (start_from_node, start_to_node)
    # Get edges outside of min_distance range
    if min_distance > 0:
        remain_min_distance = min_distance - start_point.left
        edges_in_range = graphutil.getEdgesInRadius(G, start_to_node,
                                                  remain_min_distance,
                                                  include_reverse=True)
        valid_end_edges = (G.edges() - edges_in_range).intersection(valid_end_edges)
        if len(valid_end_edges) == 0:
            print(f"WARNING: No edges detected outside of given min distance ({min_distance}), reverting to all edges.")
            valid_end_edges = G.edges() - (start_from_node, start_to_node)
    # Get edges inside of max_distance range
    if max_distance > 0:
        remain_max_distance = max_distance - start_point.left
        edges_in_range = graphutil.getEdgesInRadius(G, start_to_node,
                                                  remain_max_distance,
                                                  include_reverse=True)
        valid_end_edges = edges_in_range.intersection(valid_end_edges)
        if len(valid_end_edges) == 0:
            print(f"WARNING: No edges detected inside of given max distance ({max_distance}), reverting to all edges.")
            valid_end_edges = G.edges() - (start_from_node, start_to_node)
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
    nodes_path_len = nx.shortest_path_length(G, source=start_to_node, target=end_gedge[0], weight="length")
    end_len = end_edge.getLength()
    diff = (start_point.left + nodes_path_len + end_len) - max_distance
    if diff > 0: end_len -= diff;
    #print("path:", nodes_path_len)
    end_point = EdgePoint(G, end_gedge[0], end_gedge[1],
                          random.uniform(0, end_len),
                          edge_id=end_edge.getID())
    #print("end point:", end_point)
    #print("-> full len:", (start_point.left + nodes_path_len + end_point.distance))
    if return_length: return (end_point, start_point.left + nodes_path_len + end_point.distance)
    return end_point

def genRandomRoute(net, G, destination_count=1, min_distance=0, min_distance_per_path=0, max_distance=0):
    route = []
    ## Choose start point
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
    start_to_node = start_edge.getToNode()
    # Set random depart point
    start_len = start_edge.getLength()
    start_point = EdgePoint(G, start_from_node.getID(),
                            start_to_node.getID(),
                            random.uniform(0, start_len),
                            edge_id = start_edge.getID())
    route.append(start_point)
    ## Generate rest
    if max_distance > 0:
        max_distance = max_distance / destination_count
    total_path_len = 0
    for i in range(destination_count - 1):
        next_point, path_length = getRandomEdgePoint(net, G, route[i],
                                                     min_distance=min_distance_per_path,
                                                     max_distance=max_distance,
                                                     return_length=True)
        route.append(next_point)
        total_path_len += path_length
    # Generate last
    if min_distance > 0 and total_path_len < min_distance:
        min_distance = total_path_len - min_distance;
    else: min_distance = 0;
    next_point, path_length = getRandomEdgePoint(net, G, route[destination_count - 1],
                                                     min_distance=max(min_distance, min_distance_per_path),
                                                     max_distance=max_distance,
                                                     return_length=True)
    route.append(next_point)
    total_path_len += path_length
    #print("-- total path length:", total_path_len)
    return route

def writeStops(parent, route):
    for stop in route:
        stop_el = ET.SubElement(parent, "stop", {
                "edge" : str(stop.edge_id),
                "endPos" : str(round(stop.distance,2))
            })
    return parent
def writeRoute(parent, route):
    edges_str = ""; first = True;
    for stop in route:
        if first: first = False;
        else: edges_str += ' ';
        edges_str += str(stop.edge_id)
    route_el = ET.SubElement(parent, "route", {
            "edges" : edges_str
        })
    return parent
def writeTrips(parent, route, trip_id=0, return_trip=False, ev_type="electric"):
    trip = ET.SubElement(parent, "trip", {
                "id" : str(trip_id), 
                "from" : str(route[0].edge_id),
                "to" : str(route[0].edge_id) if return_trip else str(route[-1].edge_id),
                "depart" : str(0),
                "type" : ev_type
            })
    via = ""; first = True;
    for stop in route[1:-1]:
        if first: first = False;
        else: via += ' ';
        via += stop.edge_id
    if return_trip:
        if first: first = False;
        else: via += ' ';
        via += route[-1].edge_id
    if via != "": trip.set("via", via)
    return parent

def main(net, G, vehicle_count, filepath, destination_count_probs=[1],
         min_distance=0, min_distance_per_path=0, max_distance=0,
         ev_pen=1, stops=False):
    tree = ET.ElementTree(ET.fromstring("<routes></routes>"))
    root = tree.getroot()
    for i in range(vehicle_count):
        vType = "electric"
        if ev_pen < 1:
            if random.random() > ev_pen:
                vType = "conventional"
        #trip = ET.SubElement(root, "vehicle", {
        #            "id" : str(i),
        #            "depart" : str(0),
        #            "type" : vType
        #        })
        # Sample destination count
        r = random.random(); total = 0;
        destination_count = 1;
        for j in range(len(destination_count_probs)):
            total += destination_count_probs[j];
            if r < total: break;
            destination_count += 1
        print(r, "->", destination_count)
        route = genRandomRoute(net, G, destination_count,
                               min_distance=min_distance, min_distance_per_path=min_distance_per_path,
                               max_distance=max_distance)
        #writeRoute(veh_el, route)
        #if stops:
        #    writeStops(veh_el, route);
        writeTrips(root, route, trip_id=i, ev_type=vType)
    ET.indent(tree); tree.write(filepath);

























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
    
