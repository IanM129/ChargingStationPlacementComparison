import sys
import math
from collections import deque

import lib.graphing.utility as graphutil

import lib.xml.parkingNetGen as parkingNetGen



#### Station info
class StationInfo:
    # name_id           station id without index
    # edge_id           normal edge id
    # dedge_id          detailed edge id
    # redge_id          actual edge the station is on
    # park_id           parking id (without index)
    # dnode_id          detailed road node id
    # capacity          capacity of each parking space
    # total_capacity    summed capacity
    # occupied          (tuple) occupied spot count
    # wait_park_id      wait queue parking id
    # wait_queue        (deque) cars in wait queue
    # incoming          (set) cars going to the station
    # price             price per kWh for this station
    # suffix            id suffix
    # stop_distance      where to stop
    
    def __init__(self, edge_id, total_capacity : float, price : float,
                 dedge_id=None, redge_id=None, suffix=""):
        self.edge_id = edge_id
        self.name_id = parkingNetGen.getStationID(edge_id, suffix=suffix, with_index=False)
        #self.ids =(parkingNetGen.getStationID(edge_id, suffix=suffix), parkingNetGen.getStationID(edge_id, suffix=suffix, reverse=True))
        #     ids = (name_id + "_0", name_id + "_1")
        self.park_id = parkingNetGen.getParkingIDOfStation(self.name_id)
        self.total_capacity = total_capacity
        first_capacity = math.floor(total_capacity / 2.0)
        self.capacity = (first_capacity, total_capacity - first_capacity)
        self.occupied = [0, 0];
        self.wait_park_id = parkingNetGen.getWaitParkingIDOfStation(self.name_id)
        self.wait_queue = deque();
        self.incoming = set();
        self.price = price;
        # Utility
        #if dedge_id == None:
        #    dedge_id = graphutil.translateNetEdgeToDetailedEdgeID(edge_id);
        self.dedge_id = dedge_id
        if redge_id == None: redge_id = parkingNetGen.getEdgeID(edge_id, suffix=suffix);
        self.redge_id = redge_id
        self.dnode_id = None
        self.suffix = suffix
        self.stop_distance = None
    def setDetailedNode(self, net):
        net_edge = net.getEdge(self.edge_id)
        node_f = net_edge.getFromNode().getID(); node_t = net_edge.getToNode().getID();
        if node_f <= node_t:
            self.dnode_id = graphutil.getRoadIDFromNodes(node_f, node_t)
        else:
            self.dnode_id = graphutil.getRoadIDFromNodes(node_t, node_f)
    @staticmethod
    def fromDetailedEdge(dedge_id, total_capacity, price, suffix=""):
        edge_id = graphutil.translateDetailedRoad(dedge_id, as_tuple=False)
        s = StationInfo(edge_id, total_capacity, price, dedge_id=dedge_id, suffix=suffix);
        return s
    def getID(self, reverse=False, with_index=True):
        return self.name_id + ("_1" if reverse else "_0"); #self.ids[1 if reverse else 0];
    #station ids (2 -> normal and reverse)
    def getIDs(self): return (self.name_id + "_0", self.name_id + "_1"); #self.ids;
    # Waiting queue
    def addToWaiting(self, vehID):
        self.wait_queue.append(vehID)
    def removeNextWaiting(self):
        if len(self.wait_queue) > 0:
            return self.wait_queue.popleft()
        return None
    def getWaitingCount(self):
        return len(self.wait_queue)
    # > returns the amount of waiting cars expected from the number of taken spots, already waiting and incoming
    def getWaitingTotal(self):
        free_spots = self.total_capacity - self.getOccupancy()
        return self.getWaitingCount() + (self.getIncomingCount() - free_spots);
    # Spot management
    def requestSpot(self, auto_take=False, search_reverse=True):
        if search_reverse:
            if self.occupied[1] < self.capacity[1]:
                if auto_take: self.takeSpot(1); #self.occupied[1] += 1;
                return 1;
            elif self.occupied[0] < self.capacity[0]:
                if auto_take: self.takeSpot(0); #self.occupied[0] += 1;
                return 0;
        else:
            if self.occupied[0] < self.capacity[0]:
                if auto_take: self.takeSpot(0); #self.occupied[0] += 1;
                return 0;
            elif self.occupied[1] < self.capacity[1]:
                if auto_take: self.takeSpot(1); #self.occupied[1] += 1;
                return 1;
        return -1;
    def takeSpot(self, side_index):
        self.occupied[side_index] += 1;
    def releaseSpot(self, side_index):
        self.occupied[side_index] -= 1;
    def hasFreeSpotNow(self):
        return ((self.occupied[0] < self.capacity[0]) or (self.occupied[1] < self.capacity[1]))
    def hasFreeSpot(self):
        return ((self.getOccupancy() + self.getWaitingCount() + self.getIncomingCount()) < self.total_capacity)
    def getOccupancy(self):
        return self.occupied[0] + self.occupied[1]
    # Incoming set
    def addIncoming(self, vehID):
        self.incoming.add(vehID)
    def removeIncoming(self, vehID):
        self.incoming.remove(vehID)
    def getIncomingCount(self): return len(self.incoming);
    # Print overload
    def __repr__(self):
        return f"PCS({self.edge_id},|{self.total_capacity}|)"
class StationInfoDataset:
    def __init__(self, arr):
        self.arr = arr;
        self.IDs = None; self.IDss = None;
        self.parkIDss = None;
        self.nedges = None; self.dedges = None;
        self.dnodes = None;
        self.rev_dict = {}
        for i in range(len(arr)):
            self.rev_dict[arr[i].getID()] = i
    # Lists
    def listEdges(self):
        if not self.nedges:
            self.nedges = [si.edge_id for si in self.arr]
        return self.nedges
    def listDedges(self, net=None):
        if not self.dedges:
            return None
            self.dedges = [None] * len(self.arr) #[si.dedge_id for si in self.arr]
            for i in range(len(self.arr)):
                si = self.arr[i]
                if si.dedge_id == None:
                    if net == None: raise Exception("No net given to fetch detailed edge.");
                    si.setDetailedEdge(net)
                self.dedges[i] = si.dedge_id
        return self.dedges
    def listDNodes(self, net=None):
        if not self.dnodes:
            self.dnodes = [None] * len(self.arr) #[si.dedge_id for si in self.arr]
            for i in range(len(self.arr)):
                si = self.arr[i]
                if si.dnode_id == None:
                    if net == None: raise Exception("No net given to fetch detailed edge.");
                    si.setDetailedNode(net)
                self.dnodes[i] = si.dnode_id
        return self.dnodes
    def listIDss(self):
        if not self.IDss:
            self.IDss = [si.getIDs() for si in self.arr]
        return self.IDss
    def listIDs(self, reverse=False):
        if not self.IDs:
            self.IDs = [si.getID(reverse=reverse) for si in self.arr]
        return self.IDs
    def listParkIDss(self):
        if not self.parkIDss:
            self.parkIDss = [(si.park_id + "_0", si.park_id + "_1") for si in self.arr]
        return self.parkIDss
    def getFree(self):
        res = []
        for si in self.arr:
            if si.hasFreeSpot(): res.append(si);
        return res
    # Getters
    def __getitem__(self, idx): return self.arr[idx];
    def getByID(self, x): return self.arr[self.rev_dict[x]];
    def getIndexByID(self, x): return self.rev_dict[x];
    def getByEdgeID(self, edge_id):
        for si in self.arr:
            if si.edge_id == edge_id: return si;
        raise Exception(f"ERROR: No station found with edge id '{edge_id}'")
        #print(f"ERROR: No station found with edge id '{edge_id}'", file=sys.stderr);
        return None;
    # Overloads
    def __iter__(self):
        for el in self.arr:
            yield el
    def __len__(self): return len(self.arr);
    # Printing
    def __repr__(self):
        s = f"StationInfoDataset [{len(self.arr)}]:\n[";
        first = True
        for e in self.arr:
            if first: first = False;
            else: s += ", "
            s += str(e)
        s += "]"; return s;
    def printEdges(self):
        s = "["
        first = True;
        for e in self.arr:
            if first: first = False;
            else: s += ", ";
            s += str(e.edge_id)
        return s + "]"
