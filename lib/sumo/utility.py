from enum import Enum

class StationRouting(Enum):
    STATIONFINDER = 0
    SELFISH = 1
    CENTRALIZED = 2




def genSumoCommand(sumo_filepath, step_length, visualize,
                   trip_stats_folder=None, log_filepath=None,
                   threads=1, warnings=False):
    sumo_binary = "sumo-gui" if visualize else "sumo"
    cmnd = [sumo_binary, "-c", sumo_filepath,
            "--step-length", str(step_length), "--start"]
    if trip_stats_folder != None:
        cmnd.extend(["--tripinfo-output", trip_stats_folder + "/tripStats.out.xml"])
    if log_filepath != None:
        cmnd.extend(["--log", log_filepath])
    if visualize:
        cmnd.extend(["--delay", str(step_length * 1000)])
    if threads > 1:
        cmnd.extend(["--threads", str(threads)])
    if warnings == False:
        cmnd.extend(["--no-warnings"]) #,"true"
    return cmnd



def postprocessComp(base_net, coverage_G_d,
                    data_path, cache_data_path, cache_output_path,
                    results, agent_stations, all_stations, prices,
                    fully_completed, sim_time, exec_duration, steps_processed,
                    EVs_count, total_veh_count, set_need_to_charge_cnt, 
                    sttn_util_rate,
                    agent_colors, suffixes,
                    params):
    # Modules
    import lib.xml.output as xmlOut
    # Get params
    #MAX_DURATION = params["sim.maxDuration"]
    #DURATION_SET = MAX_DURATION > 0
    #VISUALIZE = params["sim.visualize"]
    PRINT_RESULTS = params["sim.printResults"]
    #BATTERY_EMPTY_THRESHOLD = params["electric.batteryEmptyThreshold"]
    #WAIT_QUEUE_SIZE = params["station.waitQueue"]
    #MONEY_PER_KWH = params["station.moneyPerKWh"]
    AGENT_COUNT = len(agent_stations)
    results.clear();
    results.setSimulationData(fully_completed, sim_time, exec_duration)
    ## Process step data
    # Utilization rate
    for si in all_stations:
        st_id = si.getID(); st_cap = si.total_capacity;
        sttn_util_rate[st_id] = (float(sttn_util_rate[st_id][0] / steps_processed),
                                 float(sttn_util_rate[st_id][1] / (steps_processed * st_cap)));

    ## Total charge from station
    if PRINT_RESULTS:
        print("Total charge used per station | utlization rate:")
    stations_charges_data = xmlOut.getAllStationCharges(cache_data_path)
    station_charges = {}
    veh_charges = {}
    sttn_vehicle_count = {}
    total_charge = 0
    for si in all_stations:
        station_ids = si.getIDs()
        total = 0.0;
        sttn_vehicle_count[si.getID()] = 0
        for station_id in station_ids:
            if station_id in stations_charges_data:
                charges = stations_charges_data[station_id];
                sttn_vehicle_count[si.getID()] += len(charges)
                for vehID in charges.keys():
                    for charge in charges[vehID]:
                        total += float(charge["totalEnergy"])
                    if vehID not in veh_charges: veh_charges[vehID] = set();
                    veh_charges[vehID].add(si.getID())
        station_charges[si.getID()] = total
        EVs_charged = len(veh_charges.keys()); EVs_charged_ratio = EVs_charged / set_need_to_charge_cnt;
        total_charge += total
    #money_earned = (total_charge * float(params["station.moneyPerKWH"])) / 1000.0

    ## Color specific stats
    if PRINT_RESULTS:
        print("---- Station stats:")
        print("     <station edge ID>: <energy recharged> | <utilization per step>, <utilization normalized by total parking capacity>")
    charge = []; money_earned = [];
    total_money_earned = 0.0;
    for a in range(AGENT_COUNT):
        clr_name = agent_colors[a].capitalize()
        charge.append(0.0); money_earned.append(0.0);
        if PRINT_RESULTS: print(f"-- {clr_name}:");
        for si in agent_stations[a]:
            val = station_charges[si.getID()]
            if PRINT_RESULTS:
                print(f"  {si.edge_id:10s}: {round(val, 2):9.2f} | {sttn_vehicle_count[si.getID()]:4d}",
                      f"(util: {round(sttn_util_rate[si.getID()][0] * 100.0,2):5.2f} %, {round(sttn_util_rate[si.getID()][1] * 100.0, 2):4.2f} %)")
            charge[a] += val
        money_earned[a] = (charge[a] * prices[a]) / 1000.0
        total_money_earned += money_earned[a]
        if PRINT_RESULTS:
            print(f"  > total charge: {round(total_charge[a] / 1000.0, 2)} KWh")
            print(f"  > money earned: {round(money_earned[a], 2)}€ ({round(prices[a],2)}€ per KWh)")
    if PRINT_RESULTS: print();
    results.setStationDataComp(agent_stations, prices, station_charges, sttn_util_rate, sttn_vehicle_count,
                               total_charge, total_money_earned, charge, money_earned,
                               suffixes)

    ## Trip stats/info
    trip_stats = xmlOut.getTripStats(cache_output_path)
    results.setTripData(trip_stats)
    
    ## Get flow at edges
    edge_stats = xmlOut.getEdgeLoopStats(base_net,
                                         cache_output_path + "/loop.out.xml",
                                         max_flow=True)
    edge_data = xmlOut.getEdgeDataStats(cache_output_path + "/edgeData.out.xml")
    results.setEdgeData(edge_stats, edge_data)

    ## Get vaporized vehicles and edges where they vaporized
    vaporized_count = 0
    for data in edge_data.values():
        vap = data["vaporized"]
        if vap > 0: vaporized_count += vap
    arrived_EVs_cnt = EVs_count - vaporized_count
    arrived_EVs_ratio = float(arrived_EVs_cnt) / float(EVs_count)
    if PRINT_RESULTS:
        print(f"Total vaporized: {vaporized_count}")
        print(f"--> Arrived EVs ratio: {round(arrived_EVs_ratio*100, 2):5.2f} % ({arrived_EVs_cnt} / {EVs_count}) [total: {total_veh_count}]")
        print(f"--> EVs charged ratio: {round(EVs_charged_ratio*100, 2):5.2f} % ({EVs_charged} / {set_need_to_charge_cnt})")
        print()
    results.setVehicleData(vehicle_count=total_veh_count,
                           EV_count=EVs_count, EV_set_charge=set_need_to_charge_cnt,
                           EV_arrived=arrived_EVs_cnt, EV_charged=EVs_charged)

    ## Get total coverage
    if coverage_G_d is None:
        import lib.graphing as graphing  #= lib/graphing/__init__.py
        coverage_G_d = graphing.netToDetailedGraph(data_path + "/base_net.net.xml", add_road_centers=True)
    coverage_radius = float(coverAlg.coverageRadiusBinarySearch(coverage_G_d, stations.listDNodes(base_net),
                                                                epsilon=50,
                                                                max_radius=network_diameter))
    results.setCoverageData(coverage_radius, network_diameter)

    return results

