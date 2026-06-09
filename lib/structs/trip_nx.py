import sys
import numpy as np

import networkx as nx

from lib.globalVars import ROAD_ID_SEPARATOR
from lib.graphing.astar import edgePath_internalWeights
import lib.graphing.utility as util

from lib.structs.graphtranslator import GraphTranslator



class TripNX:
    # G

    # veh_type
    # destinations
    # path
    # destinationIndeces

    # distance
    # travelTime
    # electric

    def __init__(self, G, destinations, is_electric : bool):
        self.G = G
        self.destinations = destinations
        self.electric = bool(is_electric)
        self.path = self.calcPath()
    @staticmethod
    def fromTrip(G, other_trip):
        return TripNX(G, other_trip.destinations, other_trip.electric)
    def calcPath(self):
        path = []
        self.destinationIndeces = [0]
        for i in range(1, len(self.destinations)):
            p = edgePath_internalWeights(self.G, self.destinations[i-1], self.destinations[i])
            path.extend(p[:-1])
            if p[-1] != self.destinations[i]: path.append(p[-1]);
            self.destinationIndeces.append(len(path))
        path.append(self.destinations[-1])
        self.path = path
        return path
    def __getitem__(self, idx):
        return self.destinations[idx];
    def __setitem__(self, idx, value):
        return NotImplemented
        #print("edge:", edge)
        #print("idx:", idx)
        #path_before = self.path[:self.destinationIndeces[idx]]
        #path_after = self.path[self.destinationIndeces[idx+1]:]
        #print("before:", path_before)
        #print("after:", path_after)
        #if idx > 0:
        #    path_front = edgePath_internalWeights(self.G, self.destinations[idx-1], edge)
        #else: path_front = [];
        #if idx < len(self.destinations):
        #    path_back = edgePath_internalWeights(self.G, edge, self.destinations[idx])
        #else: path_back = [];
        #self.path = path_before + path_front + path_back + path_after
        print(self.path)
    def getNodePath(self):
        node_path = []
        for p in self.path:
            node_path.append(str(p[0]))
        return node_path
    def insert(self, edge, idx):
        #print("edge:", edge)
        #print("idx:", idx)
        path_before = self.path[:self.destinationIndeces[idx-1]]
        path_after = self.path[self.destinationIndeces[idx]:]
        #print(f"before [{len(path_before) if path_before is not None else '/'}]:", path_before)
        #print(f"after [{len(path_after) if path_after is not None else '/'}]:", path_after)
        path_front = edgePath_internalWeights(self.G, self.destinations[idx-1], edge)[:-1]
        path_back = edgePath_internalWeights(self.G, edge, self.destinations[idx])[:-1]
        #print(f"front [{len(path_front) if path_front is not None else '/'}]:", path_front)
        #print(f"back [{len(path_back) if path_back is not None else '/'}]:", path_back)
        self.path = path_before + path_front + path_back + path_after
        #print(self.path)
        self.destinations.insert(idx, edge)
        # Indices
        removed_len = self.destinationIndeces[idx] - self.destinationIndeces[idx-1] - 1
        destIndx = self.destinationIndeces[idx-1] + len(path_front)
        self.destinationIndeces.insert(idx, destIndx)
        delta = len(path_front) + len(path_back) - removed_len - 1
        #print("delta:", delta)
        for i in range(idx+1, len(self.destinationIndeces)):
            self.destinationIndeces[i] += delta
    def __repr__(self):
        s = "Trip("
        s += str(self.destinations[0]) + " -> " + str(self.destinations[-1])
        s += " "
        s += "|" + str(len(self.destinations))
        s += ", [" + str(len(self.path)) + "]"
        s += ")"
        return s
    def fullPrint(self):
        s = str(self) + "\n"
        s += "  - destinations: " + str(self.destinations) + "\n"
        s += "  - path:         " + str(self.path) + "\n"
        s += "  - indices:      " + str(self.destinationIndeces) + "\n"
        return s


def updateTripXMLElement(el, trip : TripNX, translator=None):
    if translator is None: translator = GraphTranslator(trip.G);
    el.set("from", str(translator.edgeToID(trip.destinations[0])))
    el.set("to", str(translator.edgeToID(trip.destinations[-1])))
    el.set("depart", "0")
    el.set("type", "electric" if trip.electric else "conventional")
    via = [translator.edgeToID(edge) for edge in trip.destinations[1:-1]]
    el.set("via", ' '.join(via))
class TripNXDataset:
    # dict
    # xml_tree

    # translator
    
    def __init__(self, dictionary : dict[int,TripNX], xml_tree):
        self.dict = dictionary
        self.xml_tree = xml_tree
        self.translator = None
    @staticmethod
    def fromTripDataset(G, other):
        d = {}
        for vehID in other.dict:
            d[vehID] = TripNX.fromTrip(G, other.dict[vehID])
        return TripNXDataset(d, other.xml_tree)
    def __getitem__(self, vehID): return self.dict[vehID];
    def __setitem__(self, vehID, value):
        self.dict[vehID] = value
        self.updateElement(vehID)
    def __len__(self): return len(self.dict);
    def keys(self): return self.dict.keys();
    def values(self): return self.dict.values();
    def vehicles(self): return list(self.dict.keys());
    def EVs(self):
        res = set()
        for vehID, trip in self.dict.items():
            if trip.electric: res.add(vehID);
        return res
    def updateElement(self, vehID):
        if self.translator is None: self.translator = GraphTranslator(self.dict[vehID].G);
        trip_el = self.xml_tree.getroot().find(f"trip[@id='{vehID}']");
        if trip_el is None: trip_el = ET.SubElement(root, "trip", {"id": str(vehID)});
        updateTripXMLElement(trip_el, self.dict[vehID], translator=self.translator)
    def updateTree(self):
        for vehID in self.dict.keys():
            self.updateElement(vehID)
    def write(self, filepath, update_tree=True):
        if update_tree: self.updateTree();
        self.xml_tree.write(filepath)
