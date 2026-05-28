import networkx as nx
import numpy as np

class GraphTranslator:
    #  Nodes
    #node_arr
    #node_to_ind
    #  Edges
    #edge_to_id
    #edge_arr -> base
    #id_to_ind

    def __init__(self, G):
        # Nodes
        self.node_arr = np.array(list(G.nodes()))
        self.node_to_ind = {};
        for i in range(len(self.node_arr)):
            self.node_to_ind[str(self.node_arr[i])] = i
        # Edges        
        self.edge_to_id = nx.get_edge_attributes(G, "id")
        edge_arr = []
        self.id_to_ind = {}
        for i, edge in enumerate(list(G.edges)):
            edge_arr.append(edge)
            self.id_to_ind[self.edge_to_id[edge]] = i
        self.edge_arr = np.empty(len(edge_arr), dtype=object)
        self.edge_arr[:] = edge_arr
    # Nodes
    def indexToNode(self, idx):
        return self.node_arr[idx]
    def nodeToIndex(self, node):
        return self.node_to_ind[node]
    # Edges
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
    def indexToID(self, index):
        return self.edge_to_id[self.edge_arr[index]]
        # edge_to_id, edge_arr
    def indexToEdge(self, index):
        return self.edge_arr[index]
        # edge_arr
    # Mixed
    

    # Other
    def getNodes(self):
        return list(self.node_arr)
    def getEdges(self):
        return list(self.edge_arr) #set(self.edge_to_id.keys())
    def getEdges_nodeIndeces(self):
        res = np.empty((len(self.edge_arr)), dtype=object)
        for i in range(len(self.edge_arr)):
            res[i] = (self.nodeToIndex(self.edge_arr[i][0]),
                      self.nodeToIndex(self.edge_arr[i][1]))
        return res
    def getIDs(self):
        return set(self.id_to_ind.keys())

    def getEdgeIndexArray(self):
        edge_index = np.empty((2, len(self.edge_arr)), dtype=int)
        for i in range(len(self.edge_arr)):
            edge_index[0][i] = self.nodeToIndex(self.edge_arr[i][0])
            edge_index[1][i] = self.nodeToIndex(self.edge_arr[i][1])
        return edge_index

    def dictToNodePos(self, pos, pos_dim=2):
        node_count = len(self.node_arr)
        res = np.zeros((node_count, pos_dim))
        for i in range(node_count):
            node = self.node_arr[i] #self.indexToNode(i)
            res[i] = pos[node]
        return res
    def dictToEdgeAttributes(self, d, dtype=None):
        if dtype==None: dtype = type(list(d.values())[0]);
        edge_count = len(self.getEdges())
        attrs = np.zeros(edge_count, dtype=dtype)
        for i in range(edge_count):
            edge = self.indexToEdge(i)
            if edge in d:
                attrs[i] = d[edge]
        return attrs

    # Base overrides
    def __repr__(self):
        s = f"GraphTranslator ({len(self.getNodes())} | {len(self.getEdges())}):\n"
        s += "- node_arr:\n" + str(self.node_arr) + "\n"
        s += "- node_to_ind:\n" + str(self.node_to_ind) + "\n"
        s += "- edge_to_id:\n" + str(self.edge_to_id) + "\n"
        s += "- edge_arr:\n" + str(self.edge_arr) + "\n"
        s += "- id_to_ind:\n" + str(self.id_to_ind) + "\n"
        return s
