import math
import random
import numpy as np
import heapq

import networkx as nx
import matplotlib.pyplot as plt

import lib.graphing.utility as graphutil
import lib.graphing.draw as graphdraw



#### Utility
def isGraphCovered(G, centers, radius):
    covered = set()
    for center in centers:
        center_covered = graphutil.getNodesInRadius(G, center, radius)
        covered = center_covered.union(covered)
    return len(covered) == len(G.nodes())
## Choosing next center
# Choose by finding the node with the maximum distance to its closest center
def chooseFarthestFromCenters(G, candidates, distance_to_centers):
    min_distances = {}
    for center_ind in range(len(distance_to_centers)):
        for node, distance in distance_to_centers[center_ind]:
            if node in candidates:
                if node not in min_distances or distance < min_distances[node]:
                    min_distances[node] = distance;
    try:
        return max(min_distances, key=min_distances.get)
    except:
        print(min_distances)
        raise Exception("hmm")
# Choose by finding the node with the minimum sum of the distances to each of the centers
def chooseClosestFromCenters(G, candidates, distance_to_centers):
    distance_sum = {}
    for center_ind in range(len(distance_to_centers)):
        for node, distance in distance_to_centers[center_ind]:
            if node in candidates:
                if node not in distance_sum: distance_sum[node] = 0;
                distance_sum[node] += distance;
    return min(distance_sum, key=distance_sum.get)




#### Algorithms
## Coverage based optimization
def mostNodeCoverageClosest(G, center, candidates, radius) -> str:
    # Get all candidates in radius of selected node (origin)
    nodes_in_range = graphutil.getNodesInRadius_withDistance(G, center, radius, reverse_roads=True)
    cands_in_range = list(candidates & nodes_in_range.keys())
    # Calculate amount of coverage for each
    most_coverage = set(); max_cover = 0;
    for i in range(len(cands_in_range)):
        cover_val = len(graphutil.getNodesInRadius(G, cands_in_range[i], radius))
        if cover_val > max_cover:
            most_coverage.clear(); most_coverage.append(i);
            max_cover = cover_val;
        elif cover_val == max_cover: most_coverage.append(i);
    # Choose one with most coverage and then closest to origin node
    if len(most_coverage.keys()) == 0:
        print("(--base)\n--nodes_in_range:", nodes_in_range, \
              "\n--candidates:", candidates, \
              "\n--cand_in_range:", cands_in_range, \
              "\n--most_coverage:", most_coverage);
        return None #center;
    if len(most_coverage) > 1:
        closest_cand = -1; closest_val = radius;
        for cind in most_coverage:
            candidate = cands_in_range[cind]
            distance = nodes_in_range[candidate]
            if distance < closest_val:
                closest_cand = candidate; closest_val = distance;
        return closest_cand;
    else:
        return cands_in_range[most_coverage.pop()];
def mostNodeCoverageClosest_withCovered(G, center, candidates, radius, valid_nodes=None) -> tuple[str, set]:
    # Get all nodes in radius of selected node (origin)
    nodes_in_range = graphutil.getNodesInRadius_withDistance(G, center, radius, reverse_roads=True)
    # Filter only the candidates
    cands_in_range = list(candidates & nodes_in_range.keys())
    # Calculate amount of coverage for each
    most_coverage = {}; max_cover_val = 0;
    for candidate in cands_in_range:
        cover = graphutil.getNodesInRadius(G, candidate, radius)
        #cover_val = len(cover) -> just count the number of covered nodes
        # Less degree -> more value
        cover_val = 0; junc_degs = nx.get_node_attributes(G, "junctionDegree", default=10);
        for node in cover:
            if valid_nodes == None or node in valid_nodes:
                cover_val += (1 / float(junc_degs[node]))
        if cover_val > max_cover_val:
            most_coverage.clear(); most_coverage[candidate] = cover;
            max_cover_val = cover_val;
        elif cover_val == max_cover_val:
            most_coverage[candidate] = cover;
    # Choose one with most coverage and then closest to origin node
    if len(most_coverage.keys()) == 0:
        #print("(--withCovered)--nodes_in_range:", nodes_in_range, \
        #      "\n--candidates:", candidates, \
        #      "\n--cand_in_range:", cands_in_range, \
        #      "\n--most_coverage:", most_coverage);
        return (None, set())#(center, set(nodes_in_range.keys()));
    if len(most_coverage.keys()) > 1:
        closest_cand = -1; closest_val = radius;
        for candidate in most_coverage.keys():
            distance = nodes_in_range[candidate]
            if distance < closest_val:
                closest_cand = candidate; closest_val = distance;
        return (closest_cand, most_coverage[closest_cand])
    else:
        return next(iter(most_coverage.items()));
# Wrapper


## Distribute stations
def pickRandom(candidates, k):
    return random.sample(list(candidates), k=k)

def farthestFirstCoverageBased(G, G_d, candidates, k, radius, debug=False):
    # Loop: 1. get furthest node from already selected centers
    #       2. get the candidate in the radius of the selected node (origin)
    #          that covers the most of the nodes in the graph, and set it as the next station
    #       3. set distances to remaining uncovered candidates from the newly selected station
    non_candidates = G_d.nodes() - candidates
    stations = [None] * k
    # First station: select random in periphery, execute 2.- 4.
    periphery = nx.periphery(G_d, weight="length")
    peri_choice = random.choice(periphery)
    stations[0], covered = mostNodeCoverageClosest_withCovered(G_d, peri_choice, candidates, radius)
    remaining_cands = candidates - covered;
    remaining_nodes = remaining_cands.union(non_candidates - covered)
    if len(remaining_cands) == 0: return [st for st in stations if st != None];
    dis_to_centers = [None]; dis_to_centers[0] = [];
    for o in remaining_nodes:
        path_len = nx.shortest_path_length(G_d, stations[0], o, weight="length");
        dis_to_centers[0].append((o, path_len));
    #dis_to_centers[0].sort(reverse=True, key=lambda e: e[1])
    for i in range(1, k):
        farthest = chooseFarthestFromCenters(G, remaining_nodes, dis_to_centers)
        stations[i], covered = mostCoverageClosest_withCovered(G_d, farthest, remaining_cands, radius, valid_nodes=remaining_nodes)
        # -- DEBUG
        if (debug):
            print("farthest from ", stations, ":\n", farthest)
            print(f"  station {i+1}: {stations[i]}")
            inp = input("Paused, draw graph?").strip().lower()
            if len(inp) > 0 and inp[0] == "y":
                print("  Drawing graph...")
                node_colors = {};
                for nc in covered:
                    if nc in remaining_nodes: node_colors[nc] = "lightblue";
                    else: node_colors[nc] = "teal";
                if farthest == stations[i]: node_colors[stations[i]] = "purple";
                else:
                    node_colors[farthest] = "red"; node_colors[stations[i]] = "blue";
                graphdraw.drawCenters(G_d, [x for x in stations if x != None], radius, node_colors=node_colors, node_labels=False)                
                plt.show()
        # --
        if stations[i] == None:
            if (debug):
                print("station is None; distances to farthest(" + str(farthest) + "):")
                for dis_ind in range(len(dis_to_centers)):
                    for node, dis in dis_to_centers[dis_ind]:
                        if node == farthest:
                            print("-- " + str(dis_ind) + ":", dis); break;
            break;
        remaining_cands = remaining_cands - covered;
        remaining_nodes = remaining_nodes - covered
        if len(remaining_cands) == 0: break;
        dis_to_centers.append([]);
        for o in remaining_nodes:
            path_len = nx.shortest_path_length(G_d, stations[i], o, weight="length");
            dis_to_centers[i].append((o, path_len));
        #dis_to_centers[i].sort(reverse=True, key=lambda e: e[1])
    if (debug): print("\n\n---- final stations:", stations);
    return [st for st in stations if st != None]

def closestFirstCoverageBased(G, G_d, candidates, k, radius, debug=False):
    # Loop: 1. get closest node from already selected centers
    #       2. get the candidate in the radius of the selected node (origin)
    #          that covers the most of the nodes in the graph, and set it as the next station
    #       3. set distances to remaining uncovered candidates from the newly selected station
    non_candidates = G_d.nodes() - candidates
    stations = [None] * k
    # First station: select random in periphery, execute 2.- 4.
    periphery = nx.periphery(G_d, weight="length")
    peri_choice = random.choice(periphery)
    stations[0], covered = mostCoverageClosest_withCovered(G_d, peri_choice, candidates, radius)
    remaining_cands = candidates - covered;
    remaining_nodes = remaining_cands.union(non_candidates - covered)
    if len(remaining_cands) == 0: return [st for st in stations if st != None];
    dis_to_centers = [None]; dis_to_centers[0] = [];
    for o in remaining_nodes:
        path_len = nx.shortest_path_length(G_d, stations[0], o, weight="length");
        dis_to_centers[0].append((o, path_len));
    #dis_to_centers[0].sort(reverse=True, key=lambda e: e[1])
    for i in range(1, k):
        closest = chooseClosestFromCenters(G, remaining_nodes, dis_to_centers)
        stations[i], covered = mostCoverageClosest_withCovered(G_d, closest, remaining_cands, radius, valid_nodes=remaining_nodes)
        # -- DEBUG
        if (debug):
            print("closest from ", stations, ":\n", closest)
            print(f"  station {i+1}: {stations[i]}")
            inp = input("Paused, draw graph?").strip().lower()
            if len(inp) > 0 and inp[0] == "y":
                print("  Drawing graph...")
                node_colors = {};
                for nc in covered:
                    if nc in remaining_nodes: node_colors[nc] = "lightblue";
                    else: node_colors[nc] = "teal";
                if closest == stations[i]: node_colors[stations[i]] = "purple";
                else:
                    node_colors[closest] = "red"; node_colors[stations[i]] = "blue";
                graphdraw.drawCenters(G_d, [x for x in stations if x != None], radius, node_colors=node_colors, node_labels=False)                
                plt.show()
        # --
        if stations[i] == None:
            if (debug):
                print("station is None; distances to closest (" + str(closest) + "):")
                for dis_ind in range(len(dis_to_centers)):
                    for node, dis in dis_to_centers[dis_ind]:
                        if node == farthest:
                            print("-- " + str(dis_ind) + ":", dis); break;
            break;
        remaining_cands = remaining_cands - covered;
        remaining_nodes = remaining_nodes - covered
        if len(remaining_cands) == 0: break;
        dis_to_centers.append([]);
        for o in remaining_nodes:
            path_len = nx.shortest_path_length(G_d, stations[i], o, weight="length");
            dis_to_centers[i].append((o, path_len));
        #dis_to_centers[i].sort(reverse=True, key=lambda e: e[1])
    if (debug): print("\n\n---- final stations:", stations);
    return [st for st in stations if st != None]

## 
def radiusBinarySearch(G, G_d, candidates, k, epsilon=50, distribution_alg=None) -> tuple[float,list]:
    if distribution_alg == None: distribution_alg = farthestFirstCoverageBased;
    max_radius = float(nx.diameter(G_d, weight="length")) / (math.ceil(k / 2))
    a = 0; b = max_radius; radius = 0; centers = [];
    while (b - a > epsilon):
        radius = (b + a) / 2
        #print(f"-- {radius} [{b - a}]")
        centers = distribution_alg(G, G_d, candidates, k, radius, debug=False)
        feasible = len(centers) < k or isGraphCovered(G_d, centers, radius);
        if feasible: b = radius;
        else: a = radius;
    return (radius, centers)
        














"""
def distStats_peripheryStart(G, G_d, candidates, k, radius):
    ## Start from periphery
    # Take a node on the periphery
    periphery = nx.periphery(G_d, weight="length")
    peri_choice = random.choice(periphery)
    # Calculate radius and choose the furthest candidate on the edge
    in_radius = calcGraphSpaceRadius(G_d, peri_choice, radius, nodes_only=True)
    cand_in_radius = graphutil.getValidNodesAtRadius(G_d, peri_choice, radius, candidates)
    heap = [];
    for tup in cand_in_radius: heapq.heappush(heap, tup);
    print("heap:", heap)
    chosen = heapq.heappop(heap)[0]
    print("chosen:", chosen)
    return candidates, peri_choice, in_radius, cand_in_radius, chosen
"""
