import networkx as nx

import lib.graphing.utility as graphutil



#### Coverage utility
def isGraphCovered(G, centers, radius):
    covered = set()
    for center in centers:
        center_covered = graphutil.getNodesInRadius(G, center, radius)
        covered = center_covered.union(covered)
    return len(covered) == len(G.nodes())
# Binary search the radius of optimal coverage for given centers
def coverageRadiusBinarySearch(G_d, centers, max_radius=0, epsilon=50):
    if max_radius == 0:
        max_radius = float(nx.diameter(G_d, weight="length")) / (math.ceil(len(centers) / 2))
    a = 0; b = max_radius;
    while (b - a > epsilon):
        radius = (b + a) / 2
        feasible = isGraphCovered(G_d, centers, radius);
        if feasible: b = radius;
        else: a = radius;
    return radius


#### Coverage based optimization
## Nodes
# nodes, amount of covered nodes, returns candidate
def nodeCountClosest(G, center, candidates, radius, heuristic="none") -> str:
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
# nodes, node value weighted by its junction's degree, returns (candidate, covered nodes)
def nodeDegreesClosest_Nodes(G, center, candidates, radius, valid_nodes=None) -> tuple[str, set]:
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
## Edges
# edges, edge value weighted by its junctions' degrees / 2, returns (candidate, covered nodes)
def edgeDegreesClosest_Nodes(G, center, candidates, radius, valid_nodes=None) -> tuple[str, set]:
    # Get all nodes in radius of selected node (origin)
    nodes_in_range = graphutil.getNodesInRadius_withDistance(G, center, radius, reverse_roads=True)
    # Filter only the candidates
    cands_in_range = list(candidates & nodes_in_range.keys())
    # Calculate amount of coverage for each
    most_coverage = {}; max_cover_val = 0;
    for candidate in cands_in_range:
        cover = graphutil.getEdgesInRadius(G, candidate, radius)
        node_cover = set()
        #cover_val = len(cover) -> just count the number of covered nodes
        # Less degree -> more value
        cover_val = 0; junc_degs = nx.get_node_attributes(G, "junctionDegree", default=10);
        for edge in cover:
            from_n, to_n = edge
            if valid_nodes == None or (from_n in valid_nodes or to_n in valid_nodes):
                deg_sum = (float(junc_degs[from_n]) + float(junc_degs[to_n])) / 2
                cover_val += (1 / deg_sum)
                node_cover.add(from_n); node_cover.add(to_n);
        if cover_val > max_cover_val:
            most_coverage.clear(); most_coverage[candidate] = node_cover;
            max_cover_val = cover_val;
        elif cover_val == max_cover_val:
            most_coverage[candidate] = node_cover;
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
# edges, edge value weighted by edge_value_weights, returns (candidate, covered nodes)
def edgeWeightsClosest_Nodes(G, center, candidates, radius, edge_value_weights:dict, default_weight=1, valid_nodes=None) -> tuple[str, set]:
    # Get all nodes in radius of selected node (origin)
    nodes_in_range = graphutil.getNodesInRadius_withDistance(G, center, radius, reverse_roads=True)
    # Filter only the candidates
    cands_in_range = list(candidates & nodes_in_range.keys())
    # Calculate amount of coverage for each
    most_coverage = {}; max_cover_val = 0;
    for candidate in cands_in_range:
        cover = graphutil.getEdgesInRadius(G, candidate, radius)
        node_cover = set()
        # Use given weight dictionary
        cover_val = 0;
        for edge in cover:
            from_n, to_n = edge
            if valid_nodes == None or (from_n in valid_nodes or to_n in valid_nodes):
                if edge in edge_value_weights: cover_val += edge_value_weights[edge];
                else: cover_val += default_weight;
                node_cover.add(from_n); node_cover.add(to_n);
        if cover_val > max_cover_val:
            most_coverage.clear(); most_coverage[candidate] = node_cover;
            max_cover_val = cover_val;
        elif cover_val == max_cover_val:
            most_coverage[candidate] = node_cover;
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
