import sys
#import libsumo as traci
import traci.constants as tc

#from lib.structs.stationinfo import StationInfo, StationInfoDataset
from lib.structs.trip import Trip

import traci as traci_m
import libsumo as libsumo_m
global traci
traci = None

#### Initialize -> must be called for traci to libsumo switch
def initialize(libsumo_on):
    global traci
    if libsumo_on: traci = libsumo_m;
    else: traci = traci_m;

#### Subscriptions and steps
def subscribeParkingVehicleCount(park_id):
    traci.parkingarea.subscribe(park_id, [
        tc.VAR_STOP_STARTING_VEHICLES_NUMBER
    #    tc.VAR_PARKING_STARTING_VEHICLES_NUMBER,
    #    tc.VAR_PARKING_MANEUVERING_VEHICLES_NUMBER,
    #    tc.VAR_PARKING_ENDING_VEHICLES_NUMBER
    ])
def getStepParkingVehicleCount(park_id):
    data = traci.parkingarea.getSubscriptionResults(park_id)
    #res = data[tc.VAR_PARKING_STARTING_VEHICLES_NUMBER]
    #res = data[tc.VAR_PARKING_MANEUVERING_VEHICLES_NUMBER]
    #res = data[tc.VAR_PARKING_ENDING_VEHICLES_NUMBER]
    res = data[tc.VAR_STOP_STARTING_VEHICLES_NUMBER]
    return res


#### Routes and trips
def calculateRouteInfo(route, start_index=0, end_index=-1):
    if end_index == -1: end_index = len(route);
    t = 0.0; l = 0.0;
    for i in range(start_index, end_index):
        edge = route[i]
        lane = edge + "_0"
        length = traci.lane.getLength(lane)
        l += length;
        max_speed = traci.lane.getMaxSpeed(lane)
        t += length / max_speed;
    return {"travelTime" : t, "length" : l}
def getNextDestIndexInRoute(vehID, trip, route=None, cur_index=-1):
    if route == None: route = traci.vehicle.getRoute(vehID);
    if cur_index < 0: cur_index = traci.vehicle.getRouteIndex(vehID);
    next_destination = None
    destinations = trip[1:]
    last_index = 0
    for dest in destinations:
        dest_index = route.index(dest, last_index, len(route))
        if dest_index > cur_index:
            return dest_index;
        if dest_index > last_index: last_index = dest_index;
    return -1
def getNextDestIndexInTrip(vehID, trip, route=None, cur_index=-1):
    if route == None: route = traci.vehicle.getRoute(vehID);
    if cur_index < 0: cur_index = traci.vehicle.getRouteIndex(vehID);
    next_destination = None
    destinations = trip[1:]
    last_index = 0
    for i in range(len(destinations)):
        #print("trip:", trip)
        #print("destinations:", destinations)
        #print("route:", route)
        #print("destinations[i]:", destinations[i])
        #print("last_index:", last_index, " len(route):", len(route))
        dest_index = route.index(destinations[i], last_index, len(route))
        if dest_index > cur_index:
            return i + 1;
        last_index = dest_index
    return -1

def clearStops(vehID):
    stops = traci.vehicle.getStops(vehID)
    for i in reversed(range(len(stops))):
        traci.vehicle.replaceStop(vehID, i, "")
#def simFindRoute(a, b):
#    return traci.simulation.findRoute(a, b)


#### Charge
def calcNeededChargeLeft(vehID, trip):
    average_consumption = float(traci.vehicle.getParameter(vehID, "device.battery.totalEnergyConsumed")) / traci.vehicle.getDistance(vehID)
    route = traci.vehicle.getRoute(vehID)
    cur_index = traci.vehicle.getRouteIndex(vehID)
    cur_edge = route[cur_index]
    next_dest_index = getNextDestIndexInTrip(vehID, trip, route=route, cur_index=cur_index)
    distance = trip.remainingDistanceFromEdge(cur_edge, next_dest_index)
    #distance = traci.vehicle.getDrivingDistance(vehID, trips[vehID][-1], 0)
    #distance = traci.simulation.findRoute(fromEdge, toEdge).length
    return average_consumption * distance


#### Stations
def getWaitingByDistance(sttn_info):
    waiting = list(sttn_info.wait_queue)
    if len(waiting) == 0: return None;
    return sorted(waiting, key=lambda vehID: traci.vehicle.getLanePosition(vehID), reverse=True)
def getClosestWaitingToStation(sttn_info):
    waiting = list(sttn_info.wait_queue)
    if len(waiting) == 0: return None;
    #for vehID in waiting:
    #    print(f"{vehID}: {traci.vehicle.getLanePosition(vehID)}")
    #print("->", max(waiting, key=lambda vehID: traci.vehicle.getLanePosition(vehID)))
    #exit()
    return max(waiting, key=lambda vehID: traci.vehicle.getLanePosition(vehID))
def stationCostWrapper(sttn_info, cur_edge, next_dest_edge, cost_function, approx_charge_needed=None):
    sttn_id = sttn_info.getID()
    #sttn_lane = traci.chargingstation.getLaneID(sttn_id)
    #sttn_edge = sttn_lane.rsplit('_', 1)[0]
    sttn_edge = sttn_info.redge_id
    # Normal route
    route_info = traci.simulation.findRoute(cur_edge, next_dest_edge)
    #ric = traciutil.calculateRouteInfo(route, cur_index, next_dest_index+1)
    # Route before station
    route_info_before = traci.simulation.findRoute(cur_edge, sttn_edge)
    if len(route_info_before.edges) == 0 and cur_edge != sttn_edge:
        return None, None
    detour_time = route_info_before.travelTime;
    detour_distance = route_info_before.length;
    # Route after station
    route_info_after = traci.simulation.findRoute(sttn_edge, next_dest_edge)
    if len(route_info_after.edges) == 0 and cur_edge != sttn_edge:
        return None, None
    detour_time += route_info_after.travelTime;
    detour_distance += route_info_after.length;
    detour_time_diff = detour_time - route_info.travelTime
    detour_distance_diff = detour_distance - route_info.length
    # Calculate cost
    cost = cost_function(detour_time_diff, detour_distance_diff, sttn_info.price, approx_charge_needed)
    return cost, (route_info_before, route_info_after)
## Find best
def findClosestChargingStation(vehID, charge, stations, cost_function, approx_charge_needed=None,
                               route=None, cur_index=-1, next_dest_index=-1):
    if route == None: route = traci.vehicle.getRoute(vehID);
    if cur_index < 0: cur_index = traci.vehicle.getRouteIndex(vehID);
    cur_edge = route[cur_index]
    #if next_dest_index < 0:
    #    next_dest_index = getNextDestIndexInRoute(vehID, trip, route, cur_index)
    next_dest_edge = route[next_dest_index]
    #print("-- route:\n", route)
    #print("---> next destination edge:", next_dest_edge)
    # Get station values
    station_costs = {}; station_routes = {};
    for sttn_info in stations:
        sttn_id = sttn_info.getID()
        cost, routes = stationCostWrapper(sttn_info, cur_edge, next_dest_edge, cost_function, approx_charge_needed)
        if cost is not None:
            station_costs[sttn_id] = cost;
            station_routes[sttn_id] = routes;
    #print(cur_edge, "->", next_dest_edge)
    #for stid, stct in station_costs.items():
        #print(f"{stid:20s}: {stct}")
    # If no accessible
    if len(station_costs) == 0: return None, None, None;
    # Choose by minimum of cost function
    chosen_sttn_id = min(station_costs, key=station_costs.get)
    sttn_info = stations.getByID(chosen_sttn_id)
    # Create adjusted route
    route_info_before = station_routes[chosen_sttn_id][0]
    route_info_after = station_routes[chosen_sttn_id][1]
    #print("before:", station_routes[chosen_sttn_id][0].edges)
    #print("after:", station_routes[chosen_sttn_id][1].edges)
    station_route = station_routes[chosen_sttn_id][0].edges + station_routes[chosen_sttn_id][1].edges[1:]
    new_trip = Trip([cur_edge, sttn_info.redge_id, next_dest_edge], [route_info_before.length, route_info_after.length], True)
    return chosen_sttn_id, new_trip, station_route
def waitQueueCost(cost, waiting, wait_coef=100.0):
    return cost + (wait_coef * waiting);
def findClosestChargingStation_centralized(vehID, charge, stations, cost_function,
                                           approx_charge_needed=None, wait_coef=100.0,
                                           route=None, cur_index=-1, next_dest_index=-1):
    if route == None: route = traci.vehicle.getRoute(vehID);
    if cur_index < 0: cur_index = traci.vehicle.getRouteIndex(vehID);
    cur_edge = route[cur_index]
    if next_dest_index < 0:
        next_dest_index = getNextDestIndexInRoute(vehID, route, cur_index)
    next_dest_edge = route[next_dest_index]
    # Get stations with an open spot
    chosen_sttn_id = None
    station_costs = {}; station_routes = {};
    free_stations = stations.getFree()
    if len(free_stations) > 0:
        # Get station values
        for sttn_info in free_stations:
            sttn_id = sttn_info.getID()
            cost, routes = stationCostWrapper(sttn_info, cur_edge, next_dest_edge, cost_function, approx_charge_needed)
            if cost is not None:
                station_costs[sttn_id] = cost;
                station_routes[sttn_id] = routes;
        if len(station_costs) > 0:
            # Go through them by minimum of cost function
            sorted_sttns = [stid for stid, val in sorted(station_costs.items(), key=lambda e: e[1])]
            for sttn_id in sorted_sttns:
                sttn_info = stations.getByID(sttn_id)
                has_spot = sttn_info.hasFreeSpot() #requestSpot(auto_take=False, search_reverse=search_reverse)
                if has_spot != -1:
                    #sttn_info.addIncoming(vehID)
                    chosen_sttn_id = sttn_id
                    break
    # No free stations -> get best based on cost and current waiting queue size
    if chosen_sttn_id is None:
        for sttn_info in stations:
            sttn_id = sttn_info.getID()
            if sttn_id not in station_costs:
                cost, routes = stationCostWrapper(sttn_info, cur_edge, next_dest_edge, cost_function, approx_charge_needed)
                if cost is not None:
                    station_costs[sttn_id] = cost;
                    station_routes[sttn_id] = routes;
            if sttn_id in station_costs:
                station_costs[sttn_id] = waitQueueCost(station_costs[sttn_id], sttn_info.getWaitingTotal(), wait_coef=wait_coef)
        if len(station_costs) == 0: return None, None, None
        chosen_sttn_id = min(station_costs, key=station_costs.get)
    # Create adjusted route
    sttn_info = stations.getByID(chosen_sttn_id)
    route_info_before = station_routes[chosen_sttn_id][0]
    route_info_after = station_routes[chosen_sttn_id][1]
    station_route = station_routes[chosen_sttn_id][0].edges + station_routes[chosen_sttn_id][1].edges[1:]
    new_trip = Trip([cur_edge, sttn_info.redge_id, next_dest_edge], [route_info_before.length, route_info_after.length], True)
    return chosen_sttn_id, new_trip, station_route

#### Visuals
## Set color by charge
def colorByCharge(vehID, cur_charge, veh_colors, max_charge, gradient=True):
    soc = float(cur_charge / float(max_charge))
    if gradient:
        if soc < 0.5:                           # (255, 0, 0) -> (255, 255, 0)
            color = (255, 255 * int(soc / 0.5), 0)
        else:                                   # (255, 255, 0) -> (0, 255, 0)
            color = (255 * int((soc - 0.5) / 0.5), 255, 0)
    else:
        if soc > 0.4:
            color = (0, 255, 0, 255)
        elif soc > 0.225:
            color = (255, 165, 0, 255)
        else:
            color = (255, 0, 0, 255)
    if vehID not in veh_colors or veh_colors[vehID] != color:
        traci.vehicle.setColor(vehID, color)
        veh_colors[vehID] = color
## Set color based on if the vehicle is going to a station or not
def colorByGoingToStation(vehID, going_to_station, veh_colors):
    if going_to_station:
        color = (255, 0, 0)
    else:
        color = (0, 255, 0)
    if vehID not in veh_colors or veh_colors[vehID] != color:
        traci.vehicle.setColor(vehID, color)
        veh_colors[vehID] = color
