#### EdgePoint
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
