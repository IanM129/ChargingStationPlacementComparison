class EdgeTranslator:
    #edge_to_id
    #edge_arr -> base
    #id_to_ind

    def __init__(self, net, G):
        self.edge_to_id = {}
        for edge in net.getEdges():
            from_n = edge.getFromNode(); to_n = edge.getToNode();
            self.edge_to_id[(from_n.getID(), to_n.getID())] = edge.getID()
        self.edge_arr = []
        self.id_to_ind = {}
        for i, edge in enumerate(list(G.edges)):
            self.edge_arr.append(edge)
            self.id_to_ind[i] = self.edge_to_id[edge]
    def edgeToID(self, edge):
        return self.edge_to_id[edge]
        # edge_to_id
    def edgeToIndex(self, edge):
        return self.id_to_ind[self.edge_to_id[edge]]
        # id_to_ind, edge_to_id
    def IDToEdge(self, ID):
        return self.edge_arr[self.id_to_ind[ID]]
        # edge_arr, id_to_ind
    def IDToIndex(self, ID):
        return self.id_to_ind[ID]
        # id_to_ind
    def IndexToID(self, index):
        return self.edge_to_id[self.edge_arr[index]]
        # edge_to_id, edge_arr
    def IndexToEdge(self, index):
        return self.edge_arr[index]
        # edge_arr
