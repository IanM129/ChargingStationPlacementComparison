import sys
import numpy as np

class Trip:
    # destinations
    # distances
    # total_distance

    def __init__(self, destinations, distances, total_distance=None):
        self.destinations = destinations
        self.distances = distances
        if total_distance == None:
            self.total_distance = sum(distances)
        else: self.total_distance = total_distance
    def __getitem__(self, idx):
        return self.destinations[idx];
    def __setitem__(self, idx, value):
        self.destinations[idx] = value;
    def insertToNextDestination(self, other_trip, next_dest_index):
        from lib.traci_utility import traci as traci
        next_dest_edge = self[next_dest_index]
        if other_trip[-1] != next_dest_edge:
            print(self.fullPrint())
            print(other_trip.fullPrint())
            print("index:", next_dest_index)
            raise Exception("ERROR:", other_trip[-1], "!=", next_dest_edge)
        prev_dest_edge = self[next_dest_index - 1]
        if prev_dest_edge == other_trip[0]:
            return self.update(other_trip, index=next_dest_index-1)
        added_distance_info = traci.simulation.findRoute(prev_dest_edge, other_trip[0])
        self.destinations = self.destinations[:next_dest_index] +\
                            other_trip.destinations +\
                            self.destinations[next_dest_index + 1:]
        self.distances = self.distances[:next_dest_index - 1] +\
                         [added_distance_info.length] +\
                          other_trip.distances +\
                          self.distances[next_dest_index:]
        self.total_distance = sum(self.distances)
    def update(self, other_trip, index=-1):
        if index > -1:
            if other_trip[0] != self[index]:
                print(self.fullPrint())
                print(other_trip.fullPrint())
                print("index:", index)
                raise Exception("ERROR:", other_trip[0], "!=", self[index])
            if index < len(self.destinations) - 1:
                if other_trip[-1] != self[index + 1]:
                    print(self.fullPrint())
                    print(other_trip.fullPrint())
                    print("index:", index)
                    raise Exception("ERROR:", other_trip[-1], "!=", self[index + 1])
        else:  # get index
            other_start = other_trip.destinations[0]
            other_end = other_trip.destinations[-1]
            for i in range(len(self.destinations) - 1):
                if (self.destinations[i] == other_start) and (self.destinations[i + 1] == other_end):
                    index = i; break;
            if index == -1:
                if self.destinations[-1] == other_start:
                    index = len(self.destinations) - 1
                else:
                    raise Exception("Can't update, no matching start (and end).");
        if index == len(self.destinations) - 1:
            self.destinations = self.destinations[:-1] +\
                                other_trip.destinations
            self.distances = self.distances[:index] + other_trip.distances
        else:
            self.destinations = self.destinations[:index] +\
                    other_trip.destinations + self.destinations[index + 2:]
            self.distances = self.distances[:index] +\
                    other_trip.distances + self.distances[index+1:]
        self.total_distance = sum(self.distances)
    def remainingDistance(self, index):
        return sum(self.distances[index:]);
    def remainingDistanceFromEdge(self, edge, next_dest_index):
        from lib.traci_utility import traci as traci
        if next_dest_index == 0:
            raise Exception("Next destination index cannot be 0.")
        res = 0
        if edge == self.destinations[next_dest_index - 1]:
            res = self.distances[next_dest_index - 1]
        else:
            route_info = traci.simulation.findRoute(edge, self.destinations[next_dest_index])
            res = route_info.length
        res += sum(self.distances[next_dest_index:])
        return res
    def __repr__(self):
        s = "Trip("
        s += str(self.destinations[0]) + " -> " + str(self.destinations[-1])
        s += " "
        s += "|" + str(len(self.destinations)) + "|"
        s += "; "
        s += str(round(self.total_distance, 2))
        s += ")"
        return s
    def fullPrint(self):
        s = str(self) + "\n"
        s += "  " + str(self.destinations) + "\n"
        s += "  " + str(self.distances) + "\n"
        return s


class TripDataset:
    # dict
    # xml_tree
    
    def __init__(self, dictionary : dict[int,Trip], xml_tree=None):
        self.dict = dictionary
        self.xml_tree = xml_tree
    def __getitem__(self, idx): return self.dict[idx];
    def __len__(self): return len(self.dict);
    def keys(self): return self.dict.keys();
    def values(self): return self.dict.values();
    def averageTripLen(self):
        return np.mean([trip.total_distance for trip in self.dict.values()])
