from subprocess import call, DEVNULL
import xml.etree.ElementTree as ET
import pathlib
import shutil
import random

import sumolib
netgenBinary = sumolib.checkBinary('netgenerate')
jtrrouterBinary = sumolib.checkBinary('jtrrouter')
duarouterBinary = sumolib.checkBinary('duarouter')
import lib.sumo.randomTrips as randomTrips

from lib.structs.trip import Trip, TripDataset

import lib.graphing.utility as graphutil
import lib.xml.parkingNetGen as parkingNetGen



#### Folder organization
def outputFolder(main_folder):
    pathlib.Path(main_folder + "/output").mkdir(parents=True, exist_ok=True)

#### Network
def recreateNetwork(input_filepath : str, output_filepath : str = "net.net"):
    if not input_filepath.endswith(".netgcfg"): input_filepath += ".netgcfg";
    if not output_filepath.endswith(".xml"): output_filepath += ".xml";
    call([netgenBinary, "-c", input_filepath, "-o", output_filepath])
#### Random trips
def genRandomTrips(net_filepath, trips_filepath, trips=100, duration=1, min_distance=100, use_jtrrouter=True):
    p = float(duration) / float(trips)
    options_arr = [
        #'--flows', flows,
        '-p', str(p),
        '-b', '0',
        '-e', str(duration),
        '-n', net_filepath,
        '-o', trips_filepath,
        '--min-distance', str(min_distance),
        '--random',
        '--random-departpos', '--random-arrivalpos',
        '--edge-permission', 'passenger',
        #'--trip-attributes', 'type="electric"',
        # probability that trips start/end at the fringe of the network
        '--fringe-factor', '2'
        #'--trip-attributes', 'departPos="random" departSpeed="max"'
        ]
    if use_jtrrouter: options_arr.append('--jtrrouter');
    randomTrips.main(randomTrips.get_options(options_arr))
# OBSOLETE
def jtrrouterSetVTypes(routes_filepath, ev_penetration, max_charge):
    tree = ET.parse(routes_filepath)
    root = tree.getroot()
    for vehicle in root.findall("vehicle"):
        # Set EV penetration
        if random.random() < ev_penetration:
            vehicle.set("type", "electric")
            # Set battery percent
            charge_param = ET.SubElement(vehicle, "param")
            charge_param.set("key", "device.battery.chargeLevel")
            rand_charge = max_charge * max(0.01, 0.1 + (random.gauss() * 0.02));
            charge_param.set("value", str(rand_charge));
        else:
            vehicle.set("type", "conventional")
    tree.write(routes_filepath)
def duarouter(net_filepath, trips_filepath, routes_filepath):
    call([duarouterBinary,
          "-n", net_filepath,
          "-r", trips_filepath,
          "-o", routes_filepath,
          "--repair"])
# /OBSOLETE

## Fix destinations
def fixTripEdges(base_net, net, stations_edges, output_filepath, trips=None,
                 routes_filepath=None, routes_tree=None, write=True):
    ## Get replacements
    targets = {}
    for st_edge in stations_edges:
        entry_id = parkingNetGen.getEntryID(st_edge)
        edge = base_net.getEdge(st_edge)
        from_id = edge.getFromNode().getID();
        to_node = edge.getToNode(); to_id = to_node.getID();
        first_id = graphutil.getRoadIDFromNodes(from_id, entry_id)
        #first_len = float(net.getEdge(first_id).getLength())
        #second_id = graphutil.getRoadIDFromNodes(entry_id, to_id)
        #second_len = float(net.getEdge(second_id).getLength())
        #len_dif = edge_len - (first_len + second_len)
        targets[st_edge] = first_id
        # Reverse
        # Get reverse edge id
        rev_st_edge = None
        for out_edge in to_node.getOutgoing():
            if (out_edge.getToNode().getID() == from_id):
                rev_st_edge = out_edge.getID(); break;
        if rev_st_edge == None:
            raise Exception(f"No reverse edge found for edge '{st_edge}'")
        #print(f"--  REVERSE: {rev_st_edge}")
        rev_edge = base_net.getEdge(rev_st_edge)
        #rev_edge_len = float(rev_edge.getLength())
        first_id = graphutil.getRoadIDFromNodes(to_id, entry_id)
        #first_len = float(net.getEdge(first_id).getLength())
        #second_id = graphutil.getRoadIDFromNodes(entry_id, from_id)
        #second_len = float(net.getEdge(second_id).getLength())
        #len_dif = edge_len - (first_len + second_len)
        targets[rev_st_edge] = first_id
    ## Replace
    if trips.xml_tree != None: tree = trips.xml_tree;
    elif routes_tree != None: tree = routes_tree;
    elif routes_filepath != None: tree = ET.parse(routes_filepath);
    else: raise Exception("No routes' tree nor filepath given.");
    root = tree.getroot()
    if trips == None:
        # Scrape XML
        for trip in root.findall("trip"):
            from_id = trip.get("from")
            if from_id in targets:
                trip.set("from", targets[from_id])
            to_id = trip.get("to")
            if to_id in targets:
                trip.set("to", targets[to_id])
            via = trip.get("via")
            if via and via != "":
                edge_list = via.split(' ')
                edge_list = [targets.get(edge, edge) for edge in edge_list]
                trip.set("via", ' '.join(edge_list))
    else:
        # Use trips dict
        for i in range(len(trips)):
            trip = trips[str(i)]
            trip_el = root[i]
            changed = False
            for j in range(len(trip.destinations)):
                if trip[j] in targets:
                    trip[j] = targets[trip[j]]
                    changed = True
            if changed:
                trip_el.set("from", trip[0])
                trip_el.set("to", trip[-1])
                trip_el.set("via", ' '.join(trip[1:-1]))
    ## Save
    trips.xml_tree = tree
    if write:
        tree.write(output_filepath)
    return trips

def processTrips(input_filepath, output_filepath=None, sim_duration=1000, ev_pen=0.5):
    if output_filepath == None: output_filepath = input_filepath;
    tree = ET.parse(input_filepath)
    root = tree.getroot()
    for trip in root.findall("trip"):
        if random.random() <= ev_pen:
            trip.set("type", "electric")
        else:
            trip.set("type", "conventional")
    tree.write(output_filepath)

#### Enable or disable settings
def enableStationFinder(tree, value : bool):
    root = tree.getroot()
    vtype = root.find("vType[@id='electric']")
    el = vtype.find("param[@key='has.stationfinder.device']")
    el.set("value", str(value).lower())
    return tree
def enableBattery(tree, value : bool):
    root = tree.getroot()
    vtype = root.find("vType[@id='electric']")
    el = vtype.find("param[@key='has.battery.device']")
    el.set("value", str(value).lower())
    return tree
def config_enableStations(sumocfg, enable=True, add_filename="stations.add.xml"):
    changed = False;
    load = isinstance(sumocfg, str)
    if load: tree = ET.parse(sumocfg)
    else: tree = sumocfg;
    #
    root = tree.getroot()
    input_el = root.find("input")
    add_el = input_el.find("additional-files")
    adds = add_el.get("value").split(',')
    index = -1
    for i in range(len(adds)):
        if adds[i] == add_filename:
            index = i; break;
    if (index == -1):
        if enable: adds.append(add_filename);
        changed = True;
    else:
        if (not enable): adds.pop(index);
        changed = True;
    #
    if changed:
        add_el.set("value", ",".join(adds))
        if load: tree.write(sumocfg);
    if not load:
        return tree;


#### Calculate 
def calcApproxRange(battery_capacity):
    consumption = 83 * random.uniform(0.8, 1.2)  # Wh/km
    range_m = (battery_capacity / consumption) * 1000.0
    return range_m
def calcApproxChargeNeeded(range_m):
    consumption = 83 * random.uniform(0.8, 1.2)  # Wh/km
    charge_needed = ((range_m / 1000.0) * consumption)
    return charge_needed


#### Get side variables
def getMaxChargeFromAddTree(add_tree):
    root = add_tree.getroot()
    for vtype_item in root.findall("vType"):
        if vtype_item.get("id") == "electric":
            for param in vtype_item.findall("param"):
                if param.get("key") == "device.battery.capacity":
                    return float(param.get("value"));
    return None;
def getMaxChargeFromAddXML(add_filepath):
    return getMaxChargeFromAddTree(ET.parse(add_filepath))

def getMinGapFromAddTree(add_tree):
    root = add_tree.getroot()
    for vtype_item in root.findall("vType"):
        if vtype_item.get("id") == "electric":
            val = vtype_item.get("minGap")
            if val: return float(val);
            break;
    return 2.5;


#### Other
def copyFile(source_path, target_path):
    shutil.copyfile(source_path, target_path)

"""
def preprocessNetwork():
    ## Charging stations
    if RANDOM_STATIONS:
        net_filepath = data_path + ("/net.net.xml" if RECREATE_NETWORK else "/base_net.net.xml")
        net = sumolib.net.readNet(net_filepath)
        edges = net.getEdges()
        rand_edges = random.sample(edges, 3)
        print("Random stations:", rand_edges)
        add_tree = ET.parse(data_path + "/add_base.xml")
        nodes_tree, edges_tree = parkingNetGen.extractNetworkFeatures(net_filepath)
        stations = []
        for i in range(len(rand_edges)):
            nodes_tree, edges_tree, add_tree = parkingNetGen.createParkingNet(nodes_tree, edges_tree, add_tree, rand_edges[i].getID(), capacity=5)
            parking_id = parkingNetGen.getLaneID(rand_edges[i].getID(), 0)
        add_tree.write(data_path + "/add.xml")
        parkingNetGen.write(nodes_tree, edges_tree, (data_path + "/net.net.xml"))
    ## Routes and vehicle micromanagement
    if RANDOM_TRIPS:
        options_arr = [
            '--flows', '500',
            '-b', '0',
            '-e', '1',
            '-n', data_path + 'net.net.xml',
            '-o', data_path + 'routes.xml',
            '--random',
            #'--additional-file', data_path + 'add.xml',
            '--edge-permission', 'passenger',
            '--trip-attributes', 'departPos="random" departSpeed="max"']
        if USE_JTRROUTER: options_arr.append('--jtrrouter');
        randomTrips.main(randomTrips.get_options(options_arr))
        if USE_JTRROUTER:
            call([jtrrouterBinary, '-c', in_data_path + '.jtrrcfg'])
            ## Modify vehicles
            tree = ET.parse(data_path + "/routes.xml")
            root = tree.getroot()
            # Get max charge from add.xml
            add_root = ET.parse(data_path + "/add.xml").getroot()
            for vtype_item in add_root.findall("vType"):
                if vtype_item.get("id") == "electric":
                    for param in vtype_item.findall("param"):
                        if param.get("key") == "device.battery.capacity":
                            max_charge = float(param.get("value")); break;
                    break
            for vehicle in root.findall("vehicle"):
                # Set EV penetration
                if random.random() < EV_PEN:
                    vehicle.set("type", "electric")
                    # Set battery percent
                    charge_param = ET.SubElement(vehicle, "param")
                    charge_param.set("key", "device.battery.chargeLevel")
                    rand_charge = max_charge * max(0.01, 0.1 + (random.gauss() * 0.02));
                    charge_param.set("value", str(rand_charge));
                else:
                    vehicle.set("type", "conventional")
            tree.write(data_path + "/routes.xml")
"""


""" OLD fix flows (slightly changed already)
def fixDestinations(base_net, net, routes_filepath, stations_edges, output_filepath):
    tree = ET.parse(routes_filepath)
    root = tree.getroot()
    for st_edge in stations_edges:
        #print(f"-- {st_edge}:")
        entry_id = parkingNetGen.getEntryID(st_edge)
        #print(f"    {entry_id}")
        edge = base_net.getEdge(st_edge)
        edge_len = float(edge.getLength())
        #print(f"    og edge: {edge}, len {edge_len}")
        from_id = edge.getFromNode().getID();
        to_node = edge.getToNode(); to_id = to_node.getID();
        #print(f"    {from_id} | {to_id}")
        first_id = graphutil.getRoadIDFromNodes(from_id, entry_id)
        first_len = float(net.getEdge(first_id).getLength())
        #print(f"    first:   {first_id}, len {first_len}")
        second_id = graphutil.getRoadIDFromNodes(entry_id, to_id)
        second_len = float(net.getEdge(second_id).getLength())
        #print(f"    second:  {second_id}, len {second_len}")
        len_dif = edge_len - (first_len + second_len)
        #print(f"    -> len dif {len_dif}")
        for stop in root.findall(".//*stop[@edge='" + st_edge + "']"):
            pos = float(stop.get("endPos"))
            #print(f"!  {trip.get('from')}; {flow.get('departPos')}")
            if pos < first_len:                 # In first edge
                target_id = first_id
            elif pos < first_len + len_dif:     # In between
                target_id = first_id
                pos = first_len / 2
            else:                               # In second edge
                target_id = second_id
                pos -= (first_len + len_dif)
            stop.set("edge", str(target_id))
            stop.set("endPos", str(round(pos,2)))
            #print(f"-> {trip.get('from')}; {trip.get('departPos')}")
        for trip in root.findall("trip[@to='" + st_edge + "']"):
            pos = float(trip.get("arrivalPos"))
            #print(f"!  {trip.get('to')}; {trip.get('arrivalPos')}")
            if pos < first_len:                 # In first edge
                target_id = first_id
            elif pos < first_len + len_dif:     # In between
                target_id = first_id
                pos = first_len / 2
            else:                               # In second edge
                target_id = second_id
                pos -= (first_len + len_dif)
            trip.set("to", str(target_id))
            trip.set("arrivalPos", str(round(pos,2)))
            #print(f"-> {trip.get('to')}; {trip.get('arrivalPos')}")
        # Reverse
        # Get reverse edge id
        rev_st_edge = None
        for out_edge in to_node.getOutgoing():
            if (out_edge.getToNode().getID() == from_id):
                rev_st_edge = out_edge.getID(); break;
        if rev_st_edge == None:
            raise Exception(f"No reverse edge found for edge '{st_edge}'")
        #print(f"--  REVERSE: {rev_st_edge}")
        rev_edge = base_net.getEdge(rev_st_edge)
        rev_edge_len = float(rev_edge.getLength())
        #print(f"    og rev edge: {rev_edge}, len {rev_edge_len}")
        first_id = graphutil.getRoadIDFromNodes(to_id, entry_id)
        first_len = float(net.getEdge(first_id).getLength())
        #print(f"    first:   {first_id}, len {first_len}")
        second_id = graphutil.getRoadIDFromNodes(entry_id, from_id)
        second_len = float(net.getEdge(second_id).getLength())
        #print(f"    second:  {second_id}, len {second_len}")
        len_dif = edge_len - (first_len + second_len)
        #print(f"    -> len dif {len_dif}")
        for trip in root.findall("trip[@from='" + rev_st_edge + "']"):
            pos = float(trip.get("departPos"))
            #print(f"!  {trip.get('from')}; {trip.get('departPos')}")
            if pos < first_len:                 # In first edge
                target_id = first_id
            elif pos < first_len + len_dif:     # In between
                target_id = first_id
                pos = first_len / 2
            else:                               # In second edge
                target_id = second_id
                pos -= (first_len + len_dif)
            trip.set("from", str(target_id))
            trip.set("departPos", str(round(pos,2)))
            #print(f"-> {trip.get('from')}; {trip.get('departPos')}")
        for trip in root.findall("trip[@to='" + rev_st_edge + "']"):
            pos = float(trip.get("arrivalPos"))
            #print(f"!  {trip.get('to')}; {trip.get('arrivalPos')}")
            if pos < first_len:                 # In first edge
                target_id = first_id
            elif pos < first_len + len_dif:     # In between
                target_id = first_id
                pos = first_len / 2
            else:                               # In second edge
                target_id = second_id
                pos -= (first_len + len_dif)
            trip.set("to", str(target_id))
            trip.set("arrivalPos", str(round(pos,2)))
            #print(f"-> {trip.get('to')}; {trip.get('arrivalPos')}")
        tree.write(output_filepath)
"""
