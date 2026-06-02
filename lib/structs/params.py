import sys
import xml.etree.ElementTree as ET


## Hardcoded defaults
"""
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
"""

import xml.etree.ElementTree as ET

def castByTypeName(val, typename):
    typename = typename.lower()
    if typename == "bool":
        if val == "" or val.lower() == "false":
            return False;
        return True;
    if typename == "int": return int(val);
    if typename == "float": return float(val);
    return val;
class Parameters:
    ## Static
    config_params = None
    default_params = None
    ## Local
    #values
    #size
    #names
    #groups
    #parents
    #xml_tree

    def __init__(self):
        self.values = []
        self.size = 0
        self.names = {}
        self.groups = {}
        self.parents = {}
        self.xml_tree = None
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
            #parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
            xml_tree = ET.parse(xml_tree)#, parser=parser)
        params.xml_tree = xml_tree
        root = xml_tree.getroot()
        # Nested in groups
        params.parse_recursive(root, "", use_default)
        return params
    def parse_recursive(self, node, path, use_default=False):
        if node.tag == "param":
            if use_default: val_txt = node.get("default");
            else: val_txt = node.text.strip();
            val_type = node.get("type")
            path = path + node.get("name")
            self[path] = castByTypeName(val_txt, val_type)
            path += "."
        elif node.tag == "group":
            path = path + node.get("name") + "."
        for child in node:
            self.parse_recursive(child, path, use_default)
    def write(self, filepath):
        self.xml_tree.write(filepath)
    def getGroup(self, group):
        return self.groups[group];
    def __getitem__(self, item, default=None):
        index = self.names.get(item, None)
        if isinstance(index, int): return self.values[index];
        #elif isinstance(index, str): return self.values[self.names[index]];
        elif isinstance(index, str): # -> "dirty"
            dbg = ""; first = True;
            par = self.parents[item]
            for s in par:
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
                group, name = item.rsplit('.', 1)
                # Add the new parameter
                self.values.append(value)
                self.names[item] = self.size
                # Add to group
                if (group not in self.groups): self.groups[group] = set()
                self.groups[group].add(name)
                # Check if final name exists -> possible problem
                if name in self.names:
                    #print(f"ERROR: Trying to set ambigous parameter '{item}' with name '{name}'; current set parameter: {self.names[name]}", file=sys.stderr)
                    # Mark it as "dirty"
                    self.names[name] = "d"
                    par = self.parents[name]
                    if isinstance(par, list): self.parents[name].append(item)
                    else: self.parents[name] = [par, item]
                else:
                    self.names[name] = self.size
                    self.parents[name] = item
                self.size += 1  
        else:
            # Check if already exists
            cur = self.names.get(item, None)
            if isinstance(cur, int):
                self.values[cur] = value
            elif isinstance(cur, str):
                #self.values[self.names[cur]] = value
                raise Exception("ERROR: Trying to add another parameter to already dirty name.")
            else:
                raise Exception(f"ERROR: No parameter name '{item}'.")
    def __contains__(self, item):
        return item in self.names;
    def __repr__(self):
        s = f"Parameters [{self.size}]:\n";
        f_max_len = len(max([n for n in self.names if ('.' not in n)], key=len))
        max_len = len(max(self.names, key=len))
        for name in self.names:
            if '.' not in name:
                item = self.parents[name]
                if isinstance(item, str):
                    s += "  {0:{prec1}s} | {1:{prec2}s} : {2}\n".format(name, item, self.values[self.names[name]], prec1=f_max_len, prec2=max_len)
                elif isinstance(item, list):
                    s += "  {0:{prec1}s} | {1:{prec2}s} : {2}\n".format(name, item[0], self.values[self.names[item[0]]], prec1=f_max_len, prec2=max_len)
                    for i in item[1:]:
                        s += "  {0:{prec1}s} | {1:{prec2}s} : {2}\n".format("", i, self.values[self.names[i]], prec1=f_max_len, prec2=max_len)
                #s += f"  {item} | {name}  : {self.values[self.names[item]]}\n"
        return s
    def _groupPrintRecursive(self, g_dict, g_max_len, f_max_len, index=0, parent=""):
        s = ""
        for g in sorted(g_dict):
            if isinstance(g_dict[g], dict):
                if index==0:
                    s += "{0:{indent}}- {1:{prec}s}  [{2}]\n".format(" ", g, len(g_dict[g]),
                                                                     indent=2+(index*2), prec=g_max_len[index])
                else:
                    item = parent + '.' + g
                    s += "{0:{indent}}- {1:{prec}s} | {2}\n".format(" ", g, self.values[self.names[item]],
                                                                     indent=2+(index*2), prec=f_max_len-((index-1)*2))
                s += self._groupPrintRecursive(g_dict[g], g_max_len, f_max_len, index=index+1,
                                               parent=(('' if parent=="" else (parent + '.')) + g))
            else:
                name = g
                item = parent + '.' + name
                s += "{0:{indent}}{1:{prec1}s} | {2}\n".format(" ", name, self.values[self.names[item]],
                                                                     indent=2+(index*2)+2, prec1=f_max_len-((index-1)*2))
        return s
    def groupPrint(self):
        s = f"Parameters [{self.size}]:\n";
        g_dict = {};
        g_max_len = [0, 0]; f_max_len = 0;
        for g in self.groups:
            level = 1
            if '.' in g:
                group = g; cur_dict = g_dict;
                while '.' in group:
                    f_group = group.rsplit('.', 1)[1]
                    p_group, group = group.split('.', 1)
                    if not isinstance(cur_dict[p_group], dict): cur_dict[p_group] = {};
                    cur_dict = cur_dict[p_group];
                    if len(g_max_len) <= level: g_max_len.append(0);
                    if g_max_len[level] < len(f_group): g_max_len[level] = len(f_group);
                    level += 1
                if not isinstance(cur_dict[group], dict):
                    cur_dict[group] = {};
                for n in self.groups[g]:
                    cur_dict[group][n] = None;
                    if f_max_len < len(n): f_max_len = len(n);
            else:
                if g not in g_dict: g_dict[g] = {};
                for n in self.groups[g]:
                    g_dict[g][n] = None;
                    if f_max_len < len(n): f_max_len = len(n);
        g_max_len[0] = len(max(g_dict, key=len))
        s += self._groupPrintRecursive(g_dict, g_max_len, f_max_len)
        del g_dict
        return s


                    
        for g in sorted(g_dict):
            s += "  - {0:{prec}s}  [{1}]\n".format(g, len(g_dict[g]), prec=g_max_len)
            for name in sorted(self.groups[g]):
                s += "       {0:{prec1}s} | {1}\n".format(name, self.values[self.names[name]], prec1=f_max_len)
        del g_dict
        return s
            
        
        
        




"""
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
"""
