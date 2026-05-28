class Evaluation:
    #fullyCompleted
    #simulationTime
    ## Data
    #vehicle_data
        # * vehicleCount
        # * electricCount
        # * electricArrived
        # * electricSetToCharge
        # * electricCharged
        # * averageTripTime         WIP
    #trip_data (all are averages)
        # * tripDuration
        # * tripLength
        # * waitTime
        # * waitCount
        # * stopTime
        # * timeLoss
        # * energyConsumed
    #edge_data              data for each edge
        # . vehicles
        # . flow
        # . vaporized
    #station_data           data for each station
        # . charged
        # . occupancyRate
        # . utilization
        # * totalCharge


    ## Initialization
    def __init__(self, translator):
        self.translator = translator
        self.clear();
    @classmethod
    def copy(cls, other):
        return cls(other.translator)
    def clear(self):
        self.fullyCompleted = True
        self.simulationTime = -1.0
        self.vehicle_data = {}
        self.trip_data = {}
        self.edge_data = {
            "vehicles" : None,
            "flow" : None,
            "vaporized" : None
            }
        self.station_data = {
            "charged" : None,
            "occupancyRate" : None,
            "utilization" : None,
            "totalCharge" : 0.0
            }
    ## Set
    def setSimulationData(self, fully_completed, simulationTime):
        self.fullyCompleted = fully_completed
        self.simulationTime = simulationTime
    def setVehicleData(self, vehicle_count,
                       EV_count, EV_set_charge, EV_arrived, EV_charged):
        self.vehicle_data["vehicleCount"] = int(vehicle_count)
        self.vehicle_data["electricCount"] = int(EV_count)
        self.vehicle_data["electricArrived"] = int(EV_arrived)
        self.vehicle_data["electricSetToCharge"] = int(EV_set_charge)
        self.vehicle_data["electricCharged"] = int(EV_charged)
    def setTripData(self, trip_results):
        self.trip_data = trip_results
    def setEdgeData(self, edge_stats, edge_data):
        self.edge_data["vehicles"] = {};
        self.edge_data["flow"] = {};
        self.edge_data["vaporized"] = {};
        for edge in self.translator.getEdges():
            self.edge_data[edge] = {}
            edge_id = self.translator.edgeToID(edge)
            data = edge_data.get(edge_id, {"entered" : 0, "vaporized" : 0})
            stats = edge_stats.get(edge_id, {"vehicles" : 0, "flow" : 0.0})
            self.edge_data["vehicles"][edge] = int(data["entered"]);
            self.edge_data["flow"][edge] = float(stats["flow"]);
            self.edge_data["vaporized"][edge] = int(data["vaporized"]);
    def setStationData(self, stations, sttn_util_rate, station_charges, total_charge):
        self.station_data["charged"] = {};
        self.station_data["occupancyRate"] = {};
        self.station_data["utilization"] = {};
        for si in stations:
            sid = si.getID()
            seid = self.translator.IDToEdge(si.edge_id)
            self.station_data["charged"][seid] = float(station_charges[sid]);
            self.station_data["occupancyRate"][seid] = float(sttn_util_rate[sid][0]);
            self.station_data["utilization"][seid] = float(sttn_util_rate[sid][1]);
        self.station_data["totalCharge"] = float(total_charge)
    # Get
    # /
    # Base overrides
    def __repr__(self):
        s = "Evaluation:\n"
        s += "- duration:\n    " + str(self.simulationTime) +\
             (" | NOT COMPLETED" if not self.fullyCompleted else "") + "\n"
        s += "- vehicles:\n    " + str(self.vehicle_data) + "\n"
        s += "- trips:\n    " + str(self.trip_data) + "\n"
        #s += "- edge_data:\n    " + str(self.edge_data) + "\n"
        s += "- stations:\n    " + str( self.station_data) + "\n"
        return s
