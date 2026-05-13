import math
import heapq
import networkx as nx

#import lib.graphing.utility as graphutil

#import lib.xml.parkingNetGen as parkingNetGen




#### Vector
class Vector2:
    def __init__(self, x, y):
        self.x = x; self.y = y;
    def __getitem__(self, i):
        if (i == 0): return self.x;
        if (i == 1): return self.y;
        raise IndexError(f'list index out of range: {i} / 2');
    def __len__(self): return 2;
    def magnitude(self):
        return math.sqrt(pow(self.x, 2) + pow(self.y, 2));
    def normalized(self):
        length = self.magnitude();
        return (self.x / length, self.y / length);
def normalizeVector(x : float, y : float):
    length = math.sqrt(pow(x, 2) + pow(y, 2))
    return (x / length, y / length)




#### EdgePoint and graphs
class EdgePoint:
    def __init__(self, G, start_node : str, end_node : str, distance : float, edge_id : str = None):
        self.start = start_node
        self.end = end_node
        self.distance = distance
        self.left = G.get_edge_data(start_node, end_node)["length"] - distance
        self.edge_id = edge_id
    def edgeTuple(self):
        return (self.start, self.end)
    def __repr__(self):
        return "(" + self.start + " -> " + self.end +\
                " | " + str(round(self.distance, 2)) + "+" +\
                str(round(self.left, 2)) + ")";

#### Other
class TupleMaxHeap:
    def __init__(self): self.heap = [];
    def push(self, x): heapq.heappush(self.heap, (-x[0], x[1]));
    def pop(self):
        x = heapq.heappop(self.heap); return (-x[0], x[1]);
    def __getitem__(self, i):
        x = self.heap[i]; return (-x[0], x[1]);
    def __len__(self): return len(self.heap);
    def __repr__(self):
        s = "["
        for i in range(len(self)):
            s += str(self[i])
            if i < len(self) - 1: s += ", "
        return s + "]"
