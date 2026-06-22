import networkx as nx
import heapq


def voronoiPartitions(G, source_edges : list[tuple], use_internal=True, return_distances=False):
    # Vars
    owner = {}; dist = {}; heap = []
    int_lens = nx.get_node_attributes(G, "intLens")
    # Initialize all station-edge endpoints as sources
    for source in source_edges:
        from_node, to_node = source
        # from_node
        dist[from_node] = 0; owner[from_node] = source;
        heapq.heappush(heap, (0, from_node, to_node, source))
        # to_node
        dist[to_node] = 0; owner[to_node] = source;
        heapq.heappush(heap, (0, to_node, from_node, source))
    # Multi-source Dijkstra
    while heap:
        cur_dist, node, next_node, source = heapq.heappop(heap)
        if cur_dist > dist[node]: continue
        for prev in G.predecessors(node):
            if prev == next_node: continue;
            edge_len = G[prev][node]["length"]
            new_dist = cur_dist + edge_len
            if use_internal:
                if next_node not in int_lens[node][prev]: continue;
                new_dist += int_lens[node][prev][next_node]
            if prev not in dist or new_dist < dist[prev]:
                dist[prev] = new_dist
                owner[prev] = source
                heapq.heappush(heap, (new_dist, prev, node, source))
    # Output dictionary
    partitions = {}
    for source in source_edges:
        partitions[source] = []
    # Assign each graph edge
    for from_node, to_node in G.edges():
        if from_node not in owner or to_node not in owner:
            continue;
        source_from = owner[from_node]
        source_to = owner[to_node]
        if return_distances: data = ((from_node, to_node), dist[to_node])
        else: data = (from_node, to_node)
        if source_from == source_to:
            partitions[source_from].append(data)
        else:
            # Assign to closer
            if dist[from_node] <= dist[to_node]:
                partitions[source_from].append(data)
            else:
                partitions[source_to].append(data)
    return partitions
