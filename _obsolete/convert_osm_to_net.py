import xml.etree.ElementTree as ET

class Node:
    #id
    #lat
    #lon
    #name
    #crossing   :   priority, priority_stop, unregulated,
    #               traffic_light, traffic_light_right_on,
    #               (zipper), (dead_end [auto set])

    def __init__(self, node_id, lat, lon):
        self.id = node_id
        self.lat = lat
        self.lon = lon
        self.name = None
        self.crossing = None
    def __repr__(self):
        s = f"Node({self.id}"
        if self.name is None: pass; #s += ", /";
        else: s += f", {self.name}";
        s += f", ({self.lat}, {self.lon})"
        if self.crossing is not None:
            s += f", {self.crossing}"
        return s + ")"
class Edge:
    #id
    #name
    #nodes
    #lanes
    #tags

    def __init__(self, edge_id):
        self.id = edge_id
        self.name = None
        self.nodes = []
        self.lanes = 1
        self.tags = set()
    def addNode(self, node_id):
        self.nodes.append(node_id)
    def addTag(self, tag):
        self.tags.add(tag)
    def __repr__(self):
        s = f"Edge({self.id}"
        if self.name is None: pass; #s += ", /";
        else: s += f", {self.name}";
        s += f", |{self.lanes}|"
        s += ",["; first = True;
        for node_id in self.nodes:
            if first: first = False;
            else: s += ", ";
            s += str(node_id)
        s += "]"
        if len(self.tags) > 0:
            s += ", {"; first = True;
            for tag in self.tags:
                if first: first = False;
                else: s += ", ";
                s += str(tag)
            s += "}"
        return s + ")"

HIGHWAY_DRIVEABLE = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
    "tertiary",
    "tertiary_link",
    "residential",
    "unclassified",
    "living_street",
    "service"
}


def convertOSM(filepath):
    # Result XML
    res = ET.ElementTree(ET.fromstring("<net></net>"))
    res_root = res.getroot()
    res_root.set("junctionCornerDetail", "5"); res_root.set("limitTurnSpeed", "5.50")
    #### Parse
    tree = ET.parse(filepath)
    root = tree.getroot()
    bounds_el = root.find("bounds")
    min_lat = float(bounds_el.get("minlat")); max_lat = float(bounds_el.get("maxlat"));
    min_lon = float(bounds_el.get("minlon")); max_lon = float(bounds_el.get("maxlon"));
    lat_range = max_lat - min_lat; lon_range = max_lon - min_lon;
    # Nodes
    #nodes = [];
    #node_map = {};
    #for node_el in root.findall("node"):
    #    node_id = node_el.get("id")
    #    node = Node(node_id,
    #                float(node_el.get("lat")), float(node_el.get("lon")))
    #    if (name_el := node_el.find("tag[@k='name']")) is not None:
    #        node.name = name_el.get("v");
    #    node_map[node_id] = len(nodes);
    #    nodes.append(node);
    #print(nodes)
    # Edges
    edges = []; edge_map = {};
    connected_nodes = set();
    node_crossings = {};
    for way_el in root.findall("way"):
        edge_id = way_el.get("id")
        edge = Edge(edge_id)
        # nodes
        for node_ref in way_el.findall("nd"):
            node_id = int(node_ref.get("ref"))
            edge.addNode(node_id)
            connected_nodes.add(node_id)
        # tags
        is_road = None
        for tag_el in way_el.findall("tag"):
            match (tag_el.get("k")):
                case "name":
                    edge.name = tag_el.get("v")
                case "lanes":
                    edge.lanes = int(tag_el.get("v"))
                case "highway":
                    is_road = (tag_el.get("v") in HIGHWAY_DRIVEABLE)
                case "crossing":
                    cross_type = None;
                    match (tag_el.get("v")):
                        case "traffic_signals": cross_type = "traffic_light";
                    if len(edge.nodes) == 3:
                        #if edge.nodes[1] in node_map:
                            #nodes[node_map[edge.nodes[1]]].crossing = cross_type;
                        node_crossings[edge.nodes[1]] = cross_type;
                case "oneway":
                    if tag_el.get("v") == "yes": edge.addTag("oneway");
        if is_road is None:
            # Decide if add or not
            edge_map[edge_id] = len(edges); edges.append(edge);
        elif is_road:
            edge_map[edge_id] = len(edges); edges.append(edge);
    print(edges)
    # Nodes
    nodes = []; node_map = {};
    for node_ref in connected_nodes:
        node_el = root.find(f"node[@id='{node_ref}']")
        node_id = node_el.get("id")
        node = Node(node_id,
                    float(node_el.get("lat")), float(node_el.get("lon")))
        if (name_el := node_el.find("tag[@k='name']")) is not None:
            node.name = name_el.get("v");
        node_map[node_id] = len(nodes);
        nodes.append(node);
    #### Convert
    # Nodes
    for node in nodes:
        x = (node.lat - min_lat) / lat_range
        y = (node.lon - min_lon) / lon_range
        node_el = ET.SubElement(res_root, "junction")
        junc_type = node.crossing if (node.crossing is not None) else "unregulated";
        node_el.set("id", str(node.id))
        node_el.set("type", junc_type)
        node_el.set("x", str(x)); node_el.set("y", str(y));
        if node.name is not None: node_el.set("name", node.name);
    # Edges
    for edge in edges:
        for i in range(len(edge.nodes) - 1):
            edge_el = ET.SubElement(res_root, "edge")
            road_id = str(edge.id)
            if len(edge.nodes) > 2: road_id += "_" + str(i);
            edge_el.set("id", road_id)
            edge_el.set("from", str(edge.nodes[i]))
            edge_el.set("to", str(edge.nodes[i + 1]))
            edge_el.set("numLanes", str(edge.lanes))
            if edge.name is not None: edge_el.set("name", edge.name);
    return res







if __name__ == "__main__":
    res_tree = convertOSM("small.osm")
    ET.indent(res_tree, space=' ' * 4)
    res_tree.write("net.xml", encoding="UTF-8")
