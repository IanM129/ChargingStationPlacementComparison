from collections import deque

def has_edge_path(G, start, target, int_lens):
    queue = deque([start])
    visited = {start}

    while queue:
        edge = queue.popleft()

        if edge == target:
            return True

        u, v = edge

        for _, n, _ in G.out_edges(v, data=True):
            if n not in int_lens[v].get(u, {}):
                continue

            next_edge = (v, n)

            if next_edge not in visited:
                visited.add(next_edge)
                queue.append(next_edge)

    return False
