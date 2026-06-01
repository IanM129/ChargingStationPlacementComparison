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
            edge_id = self.translator.edgeToID(edge)
            data = edge_data.get(edge_id, {"entered" : 0, "vaporized" : 0})
            stats = edge_stats.get(edge_id, {"vehicles" : 0, "flow" : 0.0})
            self.edge_data["vehicles"][edge] = int(data["entered"]);
            self.edge_data["flow"][edge] = float(stats["flow"]);
            self.edge_data["vaporized"][edge] = int(data["vaporized"]);
    def setStationData(self, stations, sttn_util_rate, station_charges, total_charge, money_earned):
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
        self.station_data["totalMoneyEarned"] = float(money_earned)
    def setStationDataComp(self, stations, sttn_util_rate, station_charges, total_charge, money_earned,
                           total_charge_r, total_charge_b, money_earned_r, money_earned_b):
        for k in ["charged", "occupancyRate", "utilization"]:
            self.station_data[k] = {};
            self.station_data[k]["_red"] = {};
            self.station_data[k]["_blue"] = {};
        for si in stations:
            sid = si.getID()
            seid = self.translator.IDToEdge(si.edge_id)
            suff = si.suffix
            self.station_data["charged"][suff][seid] = float(station_charges[sid]);
            self.station_data["occupancyRate"][suff][seid] = float(sttn_util_rate[sid][0]);
            self.station_data["utilization"][suff][seid] = float(sttn_util_rate[sid][1]);
        self.station_data["totalCharge"] = float(total_charge)
        self.station_data["charge"] = {}
        self.station_data["charge"]["_red"] = float(total_charge_r)
        self.station_data["charge"]["_blue"] = float(total_charge_b)
        self.station_data["totalMoneyEarned"] = float(money_earned)
        self.station_data["moneyEarned"] = {}
        self.station_data["moneyEarned"]["_red"] = float(money_earned_r)
        self.station_data["moneyEarned"]["_blue"] = float(money_earned_b)
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
    # Other
    def printEdgeData(self):
        print("Edge data:\n- Vehicles:")
        max_e_len = 0.0
        for key in self.edge_data["vehicles"].keys():
            if len(str(key)) > max_e_len: max_e_len = len(str(key));
        s = ""
        for key, value in self.edge_data["vehicles"].items():
            s += "  {0:{prec}s}: {1}\n".format(str(key), value, prec=max_e_len)
        print(s); print("- Flow:"); s = "";
        for key, value in self.edge_data["flow"].items():
            s += "  {0:{prec}s}: {1}\n".format(str(key), value, prec=max_e_len)
        print(s); print("- Vaporized:"); s = "";
        for key, value in self.edge_data["vaporized"].items():
            s += "  {0:{prec}s}: {1}\n".format(str(key), value, prec=max_e_len)
        print(s)
        return ""
