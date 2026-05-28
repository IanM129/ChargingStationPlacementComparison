import os
import xml.etree.ElementTree as ET
import re

import lib.graphing.utility as graphutil



def dictToElement(d, root=None):
    if root == None: root = ET.Element("dictionary");
    for key, value in d.items():
        child = root.find(key)
        if child == None: child = ET.SubElement(root, key)
        else: child.clear()
        if isinstance(value, list):
            for el in value:
                el_child = ET.SubElement(child, "element")
                el_child.text = el
        else: child.text = str(value);
    return root

#### Output config for sumo config file
def config_getOutputElement(root):
    output_el = root.find("output")
    if output_el == None:
        output_el = ET.SubElement(root, "output", {});
    return output_el
def config_enableStationOutput(sumocfg, enable=True, aggregate=True):
    changed = False
    load = isinstance(sumocfg, str)
    if load: tree = ET.parse(sumocfg)
    else: tree = sumocfg;
    root = tree.getroot()
    output_el = config_getOutputElement(root)
    cs_out_el = output_el.find("chargingstations-output")
    cs_agg_el = output_el.find("chargingstations-output.aggregated")
    agg_str = str(aggregate).lower()
    if enable:
        if cs_out_el == None:
            cs_out_el = ET.SubElement(output_el, "chargingstations-output", {
                "value" : "output/chargingstations.out.xml" }); changed = True;
        if cs_agg_el == None:
            cs_agg_el = ET.SubElement(output_el, "chargingstations-output.aggregated", {
            "value" : agg_str }); changed = True;
        else:
            value = cs_agg_el.get("value")
            if value != agg_str:
                cs_agg_el.set("value", agg_str); changed = True;
    elif not enable:
        if cs_out_el != None:
            output_el.remove(cs_out_el); changed = True;
        if cs_agg_el != None:
            output_el.remove(cs_agg_el); changed = True;
    cs_agg_el = output_el.find("chargingstations-output.aggregated")
    if load:
        if changed: tree.write(sumocfg);
    else:
        return tree;
def config_enableBatteryOutput(sumocfg, enable=True):
    changed = False;
    load = isinstance(sumocfg, str)
    if load: tree = ET.parse(sumocfg)
    else: tree = sumocfg;
    root = tree.getroot()
    output_el = config_getOutputElement(root)
    bat_out_el = output_el.find("battery-output")
    if enable and bat_out_el == None:
        bat_out_el = ET.SubElement(output_el, "battery-output", {
            "value" : "output/battery.out.xml" }); changed = True;
    elif not enable and bat_out_el != None:
        output_el.remove(bat_out_el); changed = True;
    if load:
        if changed: tree.write(sumocfg);
    else:
        return tree;
#### Output config for additional output file
def config_createInductionLoopOutputFile(edges, xml_filepath="output.add.xml",
                                         relative_out_filepath="loop.out.xml", overwrite=True):
    if not xml_filepath.endswith(".xml"): xml_filepath += ".xml";
    if not relative_out_filepath.endswith(".xml"): relative_out_filepath += ".xml";
    if overwrite:
        tree = ET.ElementTree(ET.fromstring("<additional></additional>"))
    else:
        tree = ET.parse(xml_filepath)
    root = tree.getroot()
    for edge in edges:
        edgeID = edge.getID();
        i = 0
        for lane in edge.getLanes():
            laneID = lane.getID();
            lane_length = float(lane.getLength())
            loop_el = ET.SubElement(root, "inductionLoop", {
                "id" : (edgeID + "_loop" + str(i)),
                "lane" : laneID,
                "pos" : str(lane_length / 2),
                #"period" : "0",
                "file" : relative_out_filepath
                })
            i += 1
    tree.write(xml_filepath)
def config_createEdgeOutputFile(xml_filepath="output.add.xml",
                                relative_out_filepath="edgeData.out.xml", overwrite=True):
    if not xml_filepath.endswith(".xml"): xml_filepath += ".xml";
    if not relative_out_filepath.endswith(".xml"): relative_out_filepath += ".xml";
    if overwrite:
        tree = ET.ElementTree(ET.fromstring("<additional></additional>"))
    else:
        tree = ET.parse(xml_filepath)
    root = tree.getroot()
    el = ET.SubElement(root, "edgeData", {
        "id" : "0",
        #"period" : "0",
        "file" : relative_out_filepath
        })
    tree.write(xml_filepath)

#### Get values
## Station charges
def getAllStationCharges(data_path) -> dict[dict[list[dict]]]:
    result = {}
    tree = ET.parse(data_path + "/output/chargingstations.out.xml")
    root = tree.getroot()
    for e in root.findall("chargingEvent"):
        csID = e.get("chargingStationId")
        if csID in result: st_dict = result[csID];
        else: st_dict = {};
        vehID = e.get("vehicle")
        if vehID in st_dict: arr = st_dict[vehID];
        else: arr = [];
        charge = {
            "totalEnergy" : float(e.get("totalEnergyChargedIntoVehicle")),
            "begin" : float(e.get("chargingBegin")),
            "end" : float(e.get("chargingEnd")),
            "batteryCapacity" : e.get("actualBatteryCapacity")
            }
        arr.append(charge)
        st_dict[vehID] = arr;
        result[csID] = st_dict;
    return result;
def getStationCharges(data_path, station_id) -> dict[list[dict]]:
    result = {}
    tree = ET.parse(data_path + "/chargingstations.out.xml")
    root = tree.getroot()
    for e in root.findall("chargingEvent"):
        csID = e.get("chargingStationId")
        if csID == station_id:
            vehID = e.get("vehicle")
            if vehID in result: arr = result[vehID];
            else: arr = [];
            charge = {
                "totalEnergy" : float(e.get("totalEnergyChargedIntoVehicle")),
                "begin" : float(e.get("chargingBegin")),
                "end" : float(e.get("chargingEnd")),
                "batteryCapacity" : e.get("actualBatteryCapacity")
                }
            arr.append(charge)
            result[vehID] = arr;
    return result;
## Trips
def getTripStats(folder_path):
    result = {}
    tree = ET.parse(folder_path + "/tripStats.out.xml")
    root = tree.getroot()
    count = 0; battery_count = 0;
    trip_duration = 0.0
    trip_length = 0.0
    wait_time = 0.0
    wait_count = 0
    stop_time = 0.0
    time_loss = 0.0
    energy_consumed = 0.0
    for item in root.findall("tripinfo"):
        count += 1
        trip_duration += float(item.get("duration"))
        trip_length += float(item.get("routeLength"))
        wait_time = float(item.get("waitingTime"))
        wait_count = int(item.get("waitingCount"))
        stop_time = float(item.get("stopTime"))
        time_loss = float(item.get("timeLoss"))
        if (item.get("vType") == "electric"):
            bat_item = item.find("battery")
            battery_count += 1
            energy_consumed = float(bat_item.get("totalEnergyConsumed"))
    if count == 0.0: count = 1.0;
    if battery_count == 0.0: battery_count = 1.0;
    result["tripDuration"] = trip_duration / count
    result["tripLength"] = trip_length / count
    result["waitTime"] = wait_time / count
    result["waitCount"] = wait_count / count
    result["stopTime"] = stop_time / count
    result["timeLoss"] = time_loss / count
    result["energyConsumed"] = energy_consumed / battery_count
    return result
## Vehicle break down warnings
def getBreakdownWarnings(log_filepath):
    events = []
    pattern = re.compile(
        r"Warning:\s*Removing vehicle\s*'([^']+)'\s*after breaking down,\s*lane='([^']+)'\s*,\s*time=([0-9.]+)\."
        )
    with open(log_filepath) as file:
        for line in file:
            re_match = re.search(pattern, line)
            if re_match:
                vehID = re_match.group(1)
                lane = re_match.group(2)
                time = float(re_match.group(3))
                events.append((vehID, lane, time))
    return events;
def getBreakdownsPerEdge(events):
    result = {}
    for e in events:
        _, lane, _ = e
        edge = lane[:lane.rindex('_')]
        if edge in result: result[edge] += 1;
        else: result[edge] = 1;
    return result
## Battery depletion warnings
def getBatteryDepletionWarnings(log_filepath):
    events = []
    pattern = re.compile(
        r"Warning:\s*Battery of vehicle\s*'([^']+)'\s*is depleted,\s*time=([0-9.]+)\."
        )
    with open(log_filepath) as file:
        for line in file:
            re_match = re.search(pattern, line)
            if re_match:
                vehID = re_match.group(1)
                time = float(re_match.group(2))
                events.append((vehID, time))
    return events;
## Edge stats
def getEdgeLoopStats(filepath, max_flow=False, max_vehicles=False) -> dict:
    result = {}
    tree = ET.parse(filepath)
    root = tree.getroot()
    if max_flow: max_flow_val = 0.0;
    if max_vehicles: max_vehs_val = 0.0;
    for e in root.findall("interval"):
        elID = e.get("id")
        #print(f"elID: '{elID}'")
        edgeID = elID[:elID.rindex('_')]
        edgeID, edgeType = graphutil.extractEdgeID(edgeID);
        #print(elID, "-> (" + edgeID + ",", str(edgeType) + ")")
        if edgeType == 0:
            stats = {
                "vehicles" : float(e.get("nVehContrib")),
                "flow" : float(e.get("flow"))#,
                #"occupancy" : float(e.get("occupancy")),
                #"speed" : float(e.get("speed"))
                }
            if max_flow and stats["flow"] > max_flow_val:
                max_flow_val = stats["flow"]
            if max_vehicles and stats["vehicles"] > max_vehs_val:
                max_vehs_val = stats["vehicles"]
            if edgeID not in result:
                result[edgeID] = stats
                result[edgeID]["n"] = 1
            else:
                for key in stats.keys():
                    result[edgeID][key] += stats[key];
                result[edgeID]["n"] += 1
    for edgeID, e in result.items():
        n = float(e.get("n"))
        if n > 1:
            for key in e:
                e[key] = float(e[key]) / n;
        e.pop("n")
    if max_flow: result["_maxFlow"] = float(max_flow_val);
    if max_vehicles: result["_maxVehicles"] = float(max_vehs_val);
    return result
def getEdgeDataStats(filepath):
    result = {}
    tree = ET.parse(filepath)
    root = tree.getroot()
    for e in root.find("interval").findall("edge"):
        edgeID = e.get("id")
        stats = {
            "entered" : int(e.get("entered")),
            "vaporized" : int(e.get("vaporized")) if e.get("vaporized") != None else 0 #,
            #"occupancy" : float(e.get("occupancy")),
            #"speed" : float(e.get("speed"))
            }
        if edgeID not in result: result[edgeID] = stats;
        else: raise Exception("Found same edge multiple times in edgeData?");
    return result
    


def clean(data_path):
    files_to_delete = [
            # Base
            "net.net.xml",
            "routes.xml",
            # Additional
            "vTypes.add.xml",
            "output.add.xml",
            "stations.add.xml",
            # Temp net
            "new_edges.edg.xml",
            "new_nodes.nod.xml",
            # Output
            "output/loop.out.xml",
            "output/edgeData.out.xml",
            "output/chargingstations.out.xml",
            "output/tripStats.out.xml"
        ]
    for file in files_to_delete:
        filepath = data_path + "/" + file;
        if os.path.exists(filepath):
            os.remove(filepath);
    # Output folder
    os.rmdir(data_path + "/output")
