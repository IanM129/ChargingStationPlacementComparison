import os
import sys
import pathlib
from datetime import datetime
import subprocess
import platform

import lib.data_management as dm

from lib.structs.params import Parameters

#from lib.compare import rerunAndCompareSessions

VENV_PYTHON = os.path.join("_venv", "Scripts", "python.exe")



#### Functions
## Helper
def printSessionInfo(path, parent_folder="", metadata=None, prefix="", prec=0):
    print("{0}{1:{prec}s}".format(prefix, path, prec=prec), end="")
    if metadata is None: metadata = dm.loadSessionMetadata(parent_folder + "/" + path);
    if metadata["metadataExists"]:
            s = ""
            date = [metadata["date"][:4], metadata["date"][4:6], metadata["date"][6:]]
            s += f"{date[2]}.{date[1]}.{date[0]}, "
            time = [metadata["time"][:2], metadata["time"][2:4], metadata["time"][4:]]
            s += f"{time[0]}:{time[1]}:{time[2]}"
            s += " | " + str(metadata["network"])
            print("> " + s)
    else: print("");
    if not metadata["configExists"]:
        print(prefix + f"[ {metadata['sessionType']} ]")
    else:
        s = metadata["sessionType"]
        if metadata["sessionType"] == "MARL" or metadata["sessionType"] == "competitive":
            s += "; Agents: " + (str(metadata["agentCount"]) if (metadata["agentCount"] is not None) else "?")
        s += "; K: " + str(metadata["k"])
        s += "; " + ("Centralized" if (metadata["centralizedRouting"]) else "Selfish")
        print(prefix + (' ' * (prec + 2)) + f"[ {s} ]")
def printSessionPaths(paths, prefix=""):
    prec = len(max(paths, key=len)[0]) + 4
    for i in range(len(paths)):
        printSessionInfo(paths[i], prefix=prefix, prec=prec)
def printSessionGroups(groups, prefix="", prec=0):
    if prec > 0: prec += 4;
    options = []
    print("=" * 30); first_g = True;
    for key in groups:
        if first_g: first_g = False;
        else: print("=" * 20)
        print(f"'{key[0]}' | k = {key[1]} |", ("centralized" if key[2] else "selfish"))
        for sec_key in groups[key]:
            print("-" * 20)
            if isinstance(sec_key[0], int): print(f"{len(options)+1:2d}: {sec_key[1]} ({sec_key[0]+1}) |{sec_key[2]}|")
            else: print(f"{len(options)+1:2d}: * |{sec_key[2]}|")
            for sess in groups[key][sec_key]:
                printSessionInfo(sess[0], parent_folder=sess[1], metadata=sess[2], prefix=" " * 2, prec=prec)
            options.append((key, sec_key))
    return options
## Main
def generateVehicleData(network_name):
    # Import modules
    import xml.etree.ElementTree as ET
    import sumolib
    import preprocess as prep
    import lib.graphing as graphing  #= lib/graphing/__init__.py
    import lib.xml.tripsGen as tripsGen
    # Prepare folder
    network_filepath = os.path.join("networks", network_name)
    start_datetime_str = str(datetime.now().strftime('%Y%m%d_%H%M%S'))
    folder_path = "vehicle_data/" + start_datetime_str
    pathlib.Path(folder_path).mkdir(parents=True, exist_ok=True)
    # Load params
    params = Parameters.config()
    VEHICLE_COUNT = params["sim.vehicleCount"]
    DESTINATION_COUNT_DIST = params["sim.destinationCountDistribution"]
    MIN_DISTANCE = params["sim.minDistance"]
    MAX_DISTANCE = params["sim.maxDistance"]
    EV_PEN = params["electric.penetration"]
    # Load net
    net = sumolib.net.readNet(network_filepath + "/base_net.net.xml")
    G = graphing.netToGraph(network_filepath + "/base_net.net.xml",
                             lengths=True, travel_time=True,
                             internal_lengths=True, node_position=True)
    # Generate trips
    trips = tripsGen.main(net, G, VEHICLE_COUNT, folder_path + "/trips.xml",
                           destination_count_probs=DESTINATION_COUNT_DIST,
                           min_distance=MIN_DISTANCE,
                           max_distance=MAX_DISTANCE,
                           ev_pen=EV_PEN)
    average_trip_len = trips.averageTripLen()
    # Generate charge data
    vTypes_tree = ET.parse("networks/vTypes.add.xml")
    max_charge = prep.getMaxChargeFromAddTree(vTypes_tree)
    charge_data = dm.generateRandomChargeData(trips, max_charge)
    dm.writeChargeData(charge_data, folder_path + "/charge_data.xml")
    # Save vehicle types
    vTypes_tree.write(folder_path + "/vTypes.add.xml")
    # Save metadata (network name)
    metadata_tree = ET.ElementTree(ET.fromstring("<metadata></metadata>"))
    el = ET.SubElement(metadata_tree.getroot(), "network")
    el.text = network_name
    metadata_tree.write(folder_path + "/metadata.xml")
    print(f"\nGenerated vehicle data in '{folder_path}'")
def rerunAndCompare(sel):
    global groups, prec, group_opts
    data = groups[sel[0]][sel[1]]
    filepaths = [(el[1] + "/" + el[0]) for el in data]
    print("Comparing", filepaths)
    print("=" * 20)
    cmnd = ["cmd", "/k", VENV_PYTHON, "compare_rerun.py"] #"start", f"Rerun and compare {len(filepaths)} sessions", 
    cmnd.extend(filepaths)
    subprocess.run(cmnd)
def compareByBest(sel):
    global groups, prec, group_opts
    data = groups[sel[0]][sel[1]]
    filepaths = [(el[1] + "/" + el[0]) for el in data]
    print("Comparing", filepaths)
    print("=" * 20)
    cmnd = ["cmd", "/k", VENV_PYTHON, "compare_best.py"] #"start", f"Rerun and compare {len(filepaths)} sessions", 
    cmnd.extend(filepaths)
    subprocess.run(cmnd)




#### MAIN
if __name__ == "__main__":
    # Check if venv exists
    if not os.path.exists(VENV_PYTHON):
        # Create _venv
        print("INFO: Virtual environment not found, creating...")
        subprocess.run(["python", "-m", "venv", "_venv"])
        print("- upgrading pip...")
        subprocess.run([VENV_PYTHON, "-m", "pip", "install", "--upgrade", "pip"])
        print("- installing requirements...")
        subprocess.run([VENV_PYTHON, "-m", "pip", "install", "-r", "requirements.txt"])
        print("INFO: Successfully created and updated virtual environment.")
    
    print()
    print("=" * 20)
    print("Analysis:")
    print("0 | gen            - generate new vehicle data in '/vehicle_data'")
    print("1 | compare        - compare finished sessions")
    print("-" * 20)
    print("Run options")
    print("2 | blank          - run a blank example (no charging stations)")
    print("3 | solo           - run an algorithmic solo simulation")
    print("4 | comp           - (default) run an algorithmic competitive simulation")
    print("5 | game           - finds the placement through a game theory based algorithm")
    print("6 | gnn            - trains a solo network")
    print("7 | marl           - trains two competing networks")
    print("=" * 20)
    print("Optional arguments:")
    print("-v | --vehicles : <filepath> | <index>      - use specific vehicle data")

    choice = input("\n> ")

    if choice == "": choice = "comp";

    command = choice.split(' ')[0]
    args = ' '.join(choice.split(' ')[1:])
    #print(args)

    options = {
        "0": (None, "generateChargeData"),
        "gen": (None, "generateChargeData"),
        
        "1": (None, "compare"),
        "rerun": (None, "compare"),
        
        "2": ("blank.py", "Blank simulation"),
        "blank": ("blank.py", "Blank simulation"),

        "3": ("solo.py", "Solo algorithm"),
        "solo": ("solo.py", "Solo algorithm"),

        "4": ("comp.py", "Competitive algorithm"),
        "comp": ("comp.py", "Competitive algorithm"),

        "5": ("game.py", "Equilibrium game algorithm"),
        "game": ("game.py", "Equilibrium game algorithm"),

        "6": ("gnn.py", "Graph NN RL"),
        "gnn": ("gnn.py", "Graph NN RL"),

        "7": ("marl.py", "Multi-Agent RL"),
        "marl": ("marl.py", "Multi-Agent RL"),
    }

    key = command.lower()

    if key not in options:
        print(f'\nERROR: Invalid choice "{choice}".')
        input("Press Enter to continue...")
        sys.exit(1)

    pyfile, value = options[key]

    # Check if file exists
    if (pyfile is not None):
        if (not os.path.exists(pyfile)):
            print(f"ERROR: File not found: {pyfile}")
            input("Press Enter to continue...")
            sys.exit(1)
    else:
        if value == "compare":
            global groups, prec, group_opts
            # Select group
            groups, prec = dm.getSessionGroups("results")
            print("Choose sessions to compare:")
            group_opts = printSessionGroups(groups, prefix="  ", prec=prec)
            print("")
            inp = int(input("Select group: "))
            sel = group_opts[inp-1]
            # Choose method
            while inp != "" and inp != "q" and inp != "quit" and inp != "exit":
                print("-" * 20)
                print("Choose method:")
                print("0 | rerun        - compare by rerunning")
                print("1 | best         - compare by best achieved results")
                print("-" * 20)
                inp = input("> ")
                if inp == "0" or inp == "rerun":
                    rerunAndCompare(sel);
                elif inp == "1" or inp == "best":
                    compareByBest(sel);
                print("\n" * 1)
            exit()

    # Detect network options
    networks_data, default_net = dm.getNetworkList("networks")
    name_prec = len(max([data[0] for data in networks_data], key=len))

    print()
    print("==========================")
    print("Available networks:")
    for i in range(len(networks_data)):
        data = networks_data[i]
        print(f"{data[0]:{name_prec}s}", end="")
        if (default_net == data[0]) or (data[2] != ""): print("  - ", end="");
        if default_net == data[0]: print(f"(default) ", end="");
        if data[2] != "": print(f"{data[2]}", end="");
        print("")
    print("==========================")

    network_name = input("Enter network name: ").strip()

    if not network_name:
        network_name = "manhattan" if (default_net is None) else default_net

    network_filepath = os.path.join("networks", network_name)

    # Check if network exists
    if not os.path.exists(network_filepath):
        print(
            f'ERROR: Network folder not found: "{network_name}" '
            f'(path: "{network_filepath}")'
        )
        input("Press Enter to continue...")
        sys.exit(1)

    if pyfile is not None:
        # Call
        system = platform.system()
        if system == "Windows":
            subprocess.Popen(
                f'start "{value}" cmd /k "{VENV_PYTHON} {pyfile} {network_name} {args}"',
                shell=True)
        else:
            cmd = [VENV_PYTHON, pyfile, network_name]
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        if value == "generateChargeData":
            generateVehicleData(network_name);
        else: raise Exception(f"ERROR: Unknown command '{value}'");

    sys.exit(0)
