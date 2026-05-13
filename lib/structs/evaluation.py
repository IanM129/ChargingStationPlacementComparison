class Evaluation:
    ## Data
    #vehicle_data
        # * vehicleCount
        # * electricCount
        # * electricArrived
        # * electricSetToCharge
        # * electricCharged
        # * averageTripTime         WIP
    #edge_data              data for each edge
        # . entered
        # . flow
        # . vaporized
    #station_data           data for each station
        # . occupancyRate
        # . utilization
        # * totalCharge


    ## Initialization
    def __init__(self, edge_translator):
        self.edge_translator = edge_translator
        self.edge_data = {}
        self.station_data = {}
        self.vehicle_data = {}
    @classmethod
    def copy(cls, other):
        return cls(other.edge_translator)
    def clear(self):
        self.edge_data = dict.fromkeys(self.edge_data, None)
        self.station_data = {}
        self.vehicle_data = {}
    ## Set
    def setVehicleData(self, vehicle_count,
                       EV_count, EV_set_charge, EV_arrived, EV_charged):
        self.vehicle_data["vehicleCount"] = int(vehicle_count)
        self.vehicle_data["electricCount"] = int(EV_count)
        self.vehicle_data["electricArrived"] = int(EV_arrived)
        self.vehicle_data["electricSetToCharge"] = int(EV_set_charge)
        self.vehicle_data["electricCharged"] = int(EV_charged)
    def setEdgeData(self, edge_stats, edge_data):
        for edge in self.edge_data.keys():
            self.edge_data[edge] = {}
            edge_id = self.edge_translator.edgeToID(edge)
            data = edge_data.get(edge_id, {"entered" : 0, "vaporized" : 0})
            stats = edge_stats.get(edge_id, {"vehicles" : 0, "flow" : 0.0})
            self.edge_data[edge]["entered"] = int(data["entered"]);
            self.edge_data[edge]["flow"] = float(stats["flow"]);
            self.edge_data[edge]["vaporized"] = int(data["vaporized"]);
    def setStationData(self, stations, sttn_util_rate, total_charge):
        self.station_data = {}
        for si in stations:
            sid = si.getID()
            self.station_data[sid] = {}
            self.station_data[sid]["occupancyRate"] = float(sttn_util_rate[sid][0]);
            self.station_data[sid]["utilization"] = float(sttn_util_rate[sid][1]);
        self.station_data["totalCharge"] = float(total_charge)

    def __repr__(self):
        s = "Evaluation:\n"
        s += "- vehicle_data:\n    " + str(self.vehicle_data) + "\n"
        #s += "- edge_data:\n    " + str(self.edge_data) + "\n"
        s += "- station_data:\n    " + str( self.station_data) + "\n"
        return s
