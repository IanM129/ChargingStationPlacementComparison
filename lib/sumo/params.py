import sys


## Hardcoded defaults
def getSimulationDefault():
    return {
        "stepLength" : 0.1,
        "vehicleCount" : 200,
        "visualize" : False,
        "frameDur" : 0.01,
        "saveLog" : True
    }
def getElectricDefault():
    return {
        "electric.penetration" : 0.8,
        "electric.needToChargeProb" : 1.0,
        "electric.batteryEmptyThreshold" : 2.0,
        "electric.manualChargeDecide" : True
    }
def getStationDefault():
    return {
        "station.capacity" : 10,
        "station.waitQueue" : 10,
        "station.fillReverse" : False,
        "station.moneyPerKWH" : 0.25
    }
def getPreprocessDefault():
    return {
        "prep.preprocess" : True,
        "prep.recreateNetwork" : False,
        "prep.saveInputs" : True
    };
def getAllDefault():
    return {
        **getSimulationDefault(),
        **getElectricDefault(),
        **getStationDefault(),
        **getPreprocessDefault()
    }
import xml.etree.ElementTree as ET

def castByTypeName(val, typename):
    typename = typename.lower()
    if typename == "bool": return bool(val);
    if typename == "int": return int(val);
    if typename == "float": return float(val);
    return val;
class Parameters:
    ## Static
    config_params = None
    default_params = None
    ## Local
    #values
    #names
    #size
    #conns
    

    def __init__(self):
        self.values = []
        self.names = {}
        self.size = 0
        self.conns = {}
    @classmethod
    def default(cls):
        if Parameters.default_params == None:
             Parameters.default_params = Parameters.parse("config.xml", use_default=True)
        return Parameters.default_params;
    @classmethod
    def config(cls):
        if Parameters.config_params == None:
             Parameters.config_params = Parameters.parse("config.xml")
        return Parameters.config_params;
    @classmethod
    def parse(cls, xml_tree, use_default=False):
        params = cls()
        if isinstance(xml_tree, str):
            xml_tree = ET.parse(xml_tree)
        root = xml_tree.getroot()
        # Nested in groups
        params.parse_recursive(root, "", use_default)
        return params
    def parse_recursive(self, node, path, use_default=False):
        if node.tag == "param":
            val_txt = node.find("default" if use_default else "value").text
            val_type = node.get("type")
            path = path + node.get("name")
            self[path] = castByTypeName(val_txt, val_type)
            path += "."
        elif node.tag == "group":
            path = path + node.get("name") + "."
        for child in node:
            self.parse_recursive(child, path, use_default)
    def __getitem__(self, item, default=None):
        index = self.names.get(item, None)
        if isinstance(index, int): return self.values[index];
        #elif isinstance(index, str): return self.values[self.names[index]];
        elif isinstance(index, str): # -> "dirty"
            dbg = ""; first = True;
            conn = self.conns[item]
            for s in conn:
                if first: first = False;
                else: dbg += " - ";
                dbg += s
            print(f"ERROR: Trying to retrieve ambigous parameter '{item}', between: ({dbg})", file=sys.stderr)
        else: print(f"ERROR: Failed to get '{item}' parameter.", file=sys.stderr)
    def __setitem__(self, item : str, value):
        if '.' in item:
            # Check if already exists
            cur = self.names.get(item, None)
            if isinstance(cur, int):
                self.values[cur] = value; # if yes, just set it
            else:
                name = item.rsplit('.', 1)[1]
                # Add the new parameter
                self.values.append(value)
                self.names[item] = self.size
                # Check if final name exists -> possible problem
                if name in self.names:
                    #print(f"ERROR: Trying to set ambigous parameter '{item}' with name '{name}'; current set parameter: {self.names[name]}", file=sys.stderr)
                    # Mark it as "dirty"
                    self.names[name] = "d"
                    conn = self.conns[name]
                    if isinstance(conn, list): self.conns[name].append(item)
                    else: self.conns[name] = [conn, item]
                else:
                    self.names[name] = self.size
                    self.conns[name] = item
                self.size += 1
                        
        else:
            # Check if already exists
            cur = self.names.get(item, None)
            if isinstance(cur, int):
                self.values[cur] = value
            elif isinstance(cur, str):
                #self.values[self.names[cur]] = value
                raise Exception("ERROR: Trying to add another parameter to already dirty name.")
    def __repr__(self):
        s = f"Parameters [{self.size}]:\n";
        f_max_len = len(max([n for n in self.names if ('.' not in n)], key=len))
        max_len = len(max(self.names, key=len))
        for name in self.names:
            if '.' not in name:
                item = self.conns[name]
                if isinstance(item, str):
                    s += "  {0:{prec1}s} | {1:{prec2}s} : {2}\n".format(name, item, self.values[self.names[name]], prec1=f_max_len, prec2=max_len)
                elif isinstance(item, list):
                    s += "  {0:{prec1}s} | {1:{prec2}s} : {2}\n".format(name, item[0], self.values[self.names[item[0]]], prec1=f_max_len, prec2=max_len)
                    for i in item[1:]:
                        s += "  {0:{prec1}s} | {1:{prec2}s} : {2}\n".format("", i, self.values[self.names[i]], prec1=f_max_len, prec2=max_len)
                #s += f"  {item} | {name}  : {self.values[self.names[item]]}\n"
        return s
            
        
        
        





def setParams(params):
    # Preprocess
    if ((value := params.get("prep.preprocess", None)) != None):
        global PREPROCESS; PREPROCESS = bool(value);
    if ((value := params.get("prep.recreateNetwork", None)) != None):
        global RECREATE_NETWORK; RECREATE_NETWORK = bool(value);
    if ((value := params.get("prep.saveInputs", None)) != None):
        global SAVE_INPUTS; SAVE_INPUTS = bool(value);
    # Simulation
    if ((value := params.get("stepLength", None)) != None):
        global STEP_LENGTH; STEP_LENGTH = float(value);
    if ((value := params.get("vehicleCount", None)) != None):
        global VEHICLE_COUNT; VEHICLE_COUNT = int(value);
    if ((value := params.get("frameDur", None)) != None):
        global FRAME_DUR; FRAME_DUR = float(value);
    if ((value := params.get("visualize", None)) != None):
        global VISUALIZE; VISUALIZE = bool(value);
    if ((value := params.get("saveLog", None)) != None):
        global SAVE_LOG; SAVE_LOG = bool(value);
    ## Electric
    if ((value := params.get("electric.penetration", None)) != None):
        global EV_PEN; EV_PEN = float(value);
    if ((value := params.get("electric.needToChargeProb", None)) != None):
        global NEED_TO_CHARGE_PROBABILITY; NEED_TO_CHARGE_PROBABILITY = float(value);
    if ((value := params.get("electric.batteryEmptyThreshold", None)) != None):
        global BATTERY_EMPTY_THRESHOLD; BATTERY_EMPTY_THRESHOLD = float(value);
    if ((value := params.get("electric.manualChargeDecide", None)) != None):
        global MANUAL_CHARGE_DECIDE; MANUAL_CHARGE_DECIDE = bool(value);
    ## Station
    if ((value := params.get("station.capacity", None)) != None):
        global STATION_CAPACITY; STATION_CAPACITY = int(value);
    if ((value := params.get("station.waitQueue", None)) != None):
        global WAIT_QUEUE_SIZE; WAIT_QUEUE_SIZE = int(value);
    if ((value := params.get("station.fillReverse", None)) != None):
        global STATION_FILL_REVERSE; STATION_FILL_REVERSE = bool(value);
    if ((value := params.get("station.moneyPerKWH", None)) != None):
        global MONEY_PER_KWH; MONEY_PER_KWH = float(value);
