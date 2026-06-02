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
        dest_index = route.index(destinations[i], last_index, len(route))
        if dest_index > cur_index:
            return i + 1;
        last_index = dest_index
    return -1
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
def findClosestChargingStation(vehID, charge, stations, cost_function, route=None, cur_index=-1, next_dest_index=-1):
    if route == None: route = traci.vehicle.getRoute(vehID);
    if cur_index < 0: cur_index = traci.vehicle.getRouteIndex(vehID);
    cur_edge = route[cur_index]
    if next_dest_index < 0:
        next_dest_index = getNextDestIndexInRoute(vehID, route, cur_index)
    next_dest_edge = route[next_dest_index]
    #print("-- destinations:\n", destinations)
    #print("-- route:\n", route)
    #print("---> next destination edge:", next_dest_edge)
    # General values
    #energy_needed = target - charge
    #charging_time = (energy_needed * 3600.0) / station_power
    # Get station values
    station_costs = {}
    station_routes = {}
    for sttn_info in stations:
        sttn_id = sttn_info.getID()
        #sttn_lane = traci.chargingstation.getLaneID(sttn_id)
        #sttn_edge = sttn_lane.rsplit('_', 1)[0]
        sttn_edge = sttn_info.redge_id
        # Normal route
        route_info = traci.simulation.findRoute(cur_edge, next_dest_edge)
        #ric = traciutil.calculateRouteInfo(route, cur_index, next_dest_index+1)
        # Route before station
        route_info_before = traci.simulation.findRoute(cur_edge, sttn_edge)
        detour_time = route_info_before.travelTime;
        detour_distance = route_info_before.length;
        # Route after station
        route_info_after = traci.simulation.findRoute(sttn_edge, next_dest_edge)
        detour_time += route_info_after.travelTime;
        detour_distance += route_info_after.length;
        detour_time_diff = detour_time - route_info.travelTime
        detour_distance_diff = detour_distance - route_info.length
        # Calculate cost (maybe use the exact price for charging instead of per KWh)
        station_costs[sttn_id] = cost_function(detour_time_diff, detour_distance_diff, sttn_info.price)
        # Save routes
        station_routes[sttn_id] = (route_info_before, route_info_after)
    #print(cur_edge, "->", next_dest_edge)
    #for stid, stct in station_costs.items():
        #print(f"{stid:20s}: {stct}")
    # Choose by minimum of cost function
    chosen_sttn_id = min(station_costs, key=station_costs.get)
    sttn_info = stations.getByID(chosen_sttn_id)
    # Create adjusted route
    route_info_before = station_routes[chosen_sttn_id][0]
    route_info_after = station_routes[chosen_sttn_id][1]
    station_route = station_routes[chosen_sttn_id][0].edges + station_routes[chosen_sttn_id][1].edges[1:]
    new_trip = Trip([cur_edge, sttn_info.redge_id, next_dest_edge], [route_info_before.length, route_info_after.length])
    return (chosen_sttn_id, new_trip, station_route)


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
