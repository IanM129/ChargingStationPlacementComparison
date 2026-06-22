import os
import sys
import pathlib
from datetime import datetime
import subprocess
import platform
import xml.etree.ElementTree as ET

from lib.utility import parseArgs, stringifyArgs
from lib.graphing.utility import diameter as graphutil_diameter

import lib.data_management as dm

from lib.structs.params import Parameters

#from lib.compare import rerunAndCompareSessions

VENV_PYTHON = os.path.join("_venv", "Scripts", "python.exe")



#### Functions
## Printing
def printSessionInfo(path, parent_folder="", metadata=None, index=None, prefix="", prec=0, iprec=0):
    print(prefix, end="")
    if index is not None:
        print(".{0:{iprec}d}: ".format(index+1, iprec=iprec), end="")
    print("{0:{prec}s}".format(path, prec=prec), end="")
    if metadata is None: metadata = dm.loadSessionMetadata(parent_folder + "/" + path);
    if metadata["metadataExists"]:
            s = ""
            date = [metadata["date"][:4], metadata["date"][4:6], metadata["date"][6:]]
            s += f"{date[2]}.{date[1]}.{date[0]}, "
            time = [metadata["time"][:2], metadata["time"][2:4], metadata["time"][4:]]
            s += f"{time[0]}:{time[1]}:{time[2]}"
            s += ", " + str(metadata["network"])
            print("> " + s)
    else: print("");
    if not metadata["configExists"]:
        print(prefix + f"[ {metadata['sessionType']} ]")
    else:
        sess = metadata["sessionType"]
        agent_count = metadata["agentCount"]
        if agent_count is None: agent_count = "?";
        if sess.startswith("cover"): sess = "Coverage"; #agent_count = s[5];
        elif sess.startswith("game"): sess = "Game"; #agent_count = s[4];
        elif sess.startswith("marl"): sess = "MARL"; #agent_count = s[4];
        elif sess == "gnn": sess = "GNN"; #agent_count = 1;
        # Print agent count
        if agent_count == "?":
            ac_s = "Agents: ?"
        elif agent_count == 1:
            ac_s = "Solo agent"
        else:
            ac_s = "Agents: " + str(agent_count)
        k_s = "K: " + str(metadata["k"])
        cen_s = ("Centralized" if (metadata["centralizedRouting"]) else "Selfish")
        print(prefix + (' ' * (prec + 5 + iprec)) + "[ {0:8s} | {1:10s} | {2:4s} | {3:11s} ]".format(sess, ac_s, k_s, cen_s))
def printSessionPaths(paths, prefix=""):
    prec = len(max(paths, key=len)[0]) + 4
    for i in range(len(paths)):
        printSessionInfo(paths[i], prefix=prefix, prec=prec)
def printSessionGroups(groups, prefix="", prec=0, width=80):
    if prec > 0: prec += 4;
    options = []
    print("=" * width);
    for parent_folder in groups:
        print("*" * width)
        print(f"{parent_folder:^{width}}")
        print("*" * width)
        fol_groups = groups[parent_folder]
        first_g = True
        for key in fol_groups:
            if first_g: first_g = False;
            else: print(":" * width)
            prnt_s = f"'{key[0]}' | k = {key[1]} | " + ("centralized" if key[2] else "selfish")
            print("{0:^{1}}".format(prnt_s, width))
            loc_group = fol_groups[key]
            iprec = len(str(len(loc_group)))
            for sec_key in loc_group:
                print("-" * width)
                if isinstance(sec_key[0], int):
                    print(f"{len(options)+1} | {sec_key[1]} ({sec_key[0]+1}) |{sec_key[2]}|")
                else:
                    print(f"{len(options)+1} | * |{sec_key[2]}|")
                for i in range(len(loc_group[sec_key])):
                    sess = loc_group[sec_key][i]
                    printSessionInfo(sess[0], parent_folder=sess[1], metadata=sess[2], index=i,
                                     prefix=" " * 2, prec=prec, iprec=iprec)
                options.append((parent_folder, key, sec_key))
    print("=" * width)
    return options
def printNetworks(networks_data, default_net=None):
    name_prec = len(max([data[0] for data in networks_data], key=len))
    i_prec = len(str(len(networks_data)))
    print("==========================")
    print("Available networks:")
    for i in range(len(networks_data)):
        data = networks_data[i]
        print(f"{i:{i_prec}} | {data[0]:{name_prec}s}", end="")
        if (default_net == data[0]) or (data[2] != ""): print("  - ", end="");
        if default_net == data[0]: print(f"(default) ", end="");
        if data[2] != "": print(f"{data[2]}", end="");
        print("")
    print("==========================")
def printVehicleData(vehicle_data):
    name_prec = len(max([data[0] for data in vehicle_data], key=len))
    i_prec = len(str(len(vehicle_data)))
    print("==========================")
    print("Available vehicle data:")
    for i in range(len(vehicle_data)):
        data = vehicle_data[i]
        print(f"{i+1:{i_prec}} | {data[0]:{name_prec}s}  > ", end="")
        if data[2] is not None: print(f"'{data[2]}'");
        else: print("");
    print("==========================")
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
    base_net = sumolib.net.readNet(network_filepath + "/base_net.net.xml")
    base_G = graphing.netToGraph(network_filepath + "/base_net.net.xml",
                             lengths=True, travel_time=True,
                             internal_lengths=True, node_position=True)
    # Adjust max and min distances
    network_diameter = graphutil_diameter(base_G, weight="length")
    
    
    print("Generating vehicle data using parameter minimum and maximum distances:")
    print(f"  MIN_DISTANCE: {round(MIN_DISTANCE, 2)}", end="")
    if MIN_DISTANCE < 0:
        factor = round(abs(MIN_DISTANCE), 2)
        MIN_DISTANCE = abs(MIN_DISTANCE * network_diameter)
        print(f" | {round(MIN_DISTANCE, 2):9.2f}    ({factor} * {round(network_diameter, 2)})")
    else: print("")
    print(f"  MAX_DISTANCE: {round(MAX_DISTANCE, 2)}", end="")
    if MAX_DISTANCE < 0:
        factor = round(abs(MAX_DISTANCE), 2)
        MAX_DISTANCE = abs(MAX_DISTANCE * network_diameter)
        print(f" | {round(MAX_DISTANCE, 2):9.2f}    ({factor} * {round(network_diameter, 2)})")
    else: print("")
    #MIN_DISTANCE = 0.0; MAX_DISTANCE = 0.0;
    # Generate trips
    trips = tripsGen.main(base_net, base_G, VEHICLE_COUNT, folder_path + "/trips.xml",
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
    print(f"\nGenerated vehicle data in \n'{folder_path}'\n- average length: {average_trip_len}")
def parseCompare(inp_list):
    i = 1
    args = {}
    while i < len(inp_list):
        if inp_list[i] == "-s" or inp_list[i] == "--stats" or inp_list[i] == "-stats" or inp_list[i] == "-":
            args["stats"] = inp_list[i+1].split(',')
        elif inp_list[i] == "-nv" or inp_list[i] == "--no-values":
            args["no-values"] = True
        elif inp_list[i] == "-nl" or inp_list[i] == "--no-legend":
            args["no-legend"] = True
        elif inp_list[i] == "-c" or inp_list[i] == "--centerize":
            args["centerize"] = True
        i += 1
    return args
def parseSessionGroupSelect(inp, group_opts, groups):
    filepaths = []
    inp = inp.split(' ')
    for i in inp:
        if '.' in i:
            sel, index = i.split('.', 1)
            # Sel
            if not sel.isdigit():
                print(f"ERROR: Inputs '{sel}' is not an integers."); return None;
            sel = int(sel)-1;
            # Index
            if '-' in index:
                s = group_opts[sel]
                data = groups[s[0]][s[1]][s[2]]
                start, end = index.split('-',  1)
                start = max(int(start)-1, 0);
                end = min(int(end)-1, len(data)-1);
                for si in range(start, end+1):
                    filepaths.append((data[si][1] + "/" + data[si][0]))
            else:
                index = int(index)-1
                s = group_opts[sel]
                data = groups[s[0]][s[1]][s[2]]
                filepaths.append((data[index][1] + "/" + data[index][0]))
        else:
            if not i.isdigit():
                print(f"ERROR: Input '{i}' is not an integer."); return None;
            i = int(i)
            if i < 1 or i > len(group_opts):
                print(f"ERROR: Index {i} is out of range [1, {len(group_opts)}]."); return None
            s = group_opts[i-1]
            data = groups[s[0]][s[1]][s[2]]
            fps = [(el[1] + "/" + el[0]) for el in data]
            filepaths.extend(fps)
    return filepaths
def rerunAndCompare(filepaths, stat_list=None):
    #global groups
    #data = groups[sel[0]][sel[1]]
    #filepaths = [(el[1] + "/" + el[0]) for el in data]
    print(f"Comparing by rerunning...")
    print("=" * 20)
    cmnd = ["cmd", "/k", VENV_PYTHON, "compare_rerun.py"] #"start", f"Rerun and compare {len(filepaths)} sessions", 
    cmnd.extend(filepaths)
    if "stats" in args: cmnd.extend(["-stats", ','.join(args["stats"])]);
    if "no-values" in args and args["no-values"]: cmnd.append("no-values");
    if "no-legend" in args and args["no-legend"]: cmnd.append("no-legend");
    subprocess.Popen(cmnd)
def compareByBest(filepaths, args=None):
    #global groups
    #data = groups[sel[0]][sel[1]][sel[2]]
    #filepaths = [(el[1] + "/" + el[0]) for el in data]
    print(f"Comparing by best...")
    print("=" * 20)
    cmnd = ["cmd", "/k", VENV_PYTHON, "compare_best.py"] #"start", f"Rerun and compare {len(filepaths)} sessions", 
    cmnd.extend(filepaths)
    if "stats" in args: cmnd.extend(["-stats", ','.join(args["stats"])]);
    if "no-values" in args and args["no-values"]: cmnd.append("--no-values");
    if "no-legend" in args and args["no-legend"]: cmnd.append("--no-legend");
    if "centerize" in args and args["centerize"]: cmnd.append("--centerize");
    subprocess.Popen(cmnd)
def compareByDuration(filepaths, args):
    #global groups
    #data = groups[sel[0]][sel[1]][sel[2]]
    #filepaths = [(el[1] + "/" + el[0]) for el in data]
    print(f"Comparing durations...")
    print("=" * 20)
    cmnd = ["cmd", "/k", VENV_PYTHON, "compare_duration.py"]
    cmnd.extend(filepaths)
    if "no-values" in args and args["no-values"]: cmnd.append("no-values");
    if "no-legend" in args and args["no-legend"]: cmnd.append("no-legend");
    subprocess.Popen(cmnd)



def inputIsExit(inp):
    inp = inp.lower()
    return inp == "q" or inp == "quit" or inp == "exit"
def main(print_options=True):
    temp_print_options = print_options
    # Reused vars
    groups = None; prec = 0;
    while True:
        if temp_print_options:
            print("Main selection:")
            print("=" * 20)
            print("Analysis:")
            print("1  | gen             - generate new vehicle data in '/vehicle_data'")
            print("2  | compare         - compare finished sessions")
            print("3  | load            - load and visualize session results")
            print("-" * 20)
            print("Run options (n is number of agents or _/0 for reading from params)")
            print("0  | blank           - run a blank example (no charging stations)")
            print("11 | cover_solo      - run the coverage based algorithm")
            print("1n | cover_comp      - (default) run the competitive coverage based algorithm")
            print("21 | game_solo       - run the game theory based algorithm")
            print("2n | game_comp       - run the competitive game theory based algorithm")
            print("31 | gnn             - trains a solo GNN")
            print("3n | marl            - trains n competing GNNs (MARL)")
            print("=" * 20)
            print("Optional arguments:")
            print("-v | --vehicles : <filepath> | <index>       - use specific vehicle data")
            print("-i | --iterations : <integer>                - directly set iteration count")
        temp_print_options = True

        choice = input("\n> ")

        if choice == "": choice = "comp";

        command = choice.split(' ')[0]
        args = ' '.join(choice.split(' ')[1:])
        args = parseArgs(choice.split(' ')[1:])

        if len(command) == 1:
            options = {
                "1": (None, "generateChargeData"),
                "gen": (None, "generateChargeData"),
                
                "2": (None, "compare"),
                "compare": (None, "compare"),

                "3": (None, "load"),
                "load": (None, "load"),
                
                "0": ("blank.py", "Blank simulation"),
                "blank": ("blank.py", "Blank simulation"),

                "cover_solo": ("coverage_solo.py", "Coverage algorithm"),
                "cover_comp": ("coverage_competitive.py", "Competitive coverage algorithm"),

                "game_solo": ("game.py", "Equilibrium game algorithm"),
                "game_comp": ("game_competitive.py", "Competitive equilibrium game algorithm"),

                "gnn": ("gnn.py", "Graph NN RL"),
                "marl": ("marl.py", "Multi-Agent RL"),

                "-v": (None, "listVehicleData"),
                "v": (None, "listVehicleData"),
                "--vehicles": (None, "listVehicleData")
            }
            key = command.lower()
            if key not in options:
                print(f'\nERROR: Invalid choice "{choice}".')
                input("Press Enter to continue...")
                sys.exit(1)
            pyfile, value = options[key]
            AGENT_COUNT = 0
        elif len(command) == 2:
            if not command[1].isdigit() or int(command[1]) == 0:
                print(f'\nERROR: Invalid number of agents "{command[1]}".')
                input("Press Enter to continue...")
                sys.exit(1)
            if command[1] == "_": AGENT_COUNT = 0;
            else: AGENT_COUNT = int(command[1])
            match (command[0]):
                case "1":
                    if AGENT_COUNT == 1:
                        pyfile, value = ("coverage_solo.py", "Coverage algorithm")
                    else:
                        pyfile, value = ("coverage_competitive.py", "Competitive coverage algorithm")
                case "2":
                    if AGENT_COUNT == 1:
                        pyfile, value = ("game.py", "Equilibrium game algorithm")
                    else:
                        pyfile, value = ("game_competitive.py", "Competitive equilibrium game algorithm")
                case "3":
                    if AGENT_COUNT == 1:
                        pyfile, value = ("gnn.py", "Graph NN RL")
                    else:
                        pyfile, value = ("marl.py", "Multi-Agent RL")
            if AGENT_COUNT > 1:
                args["agent-count"] = AGENT_COUNT
        else:
            print(f'\nERROR: Invalid choice "{choice}".')
            input("Press Enter to continue...")
            sys.exit(1)

        # Check if file exists
        if (pyfile is not None):
            if (not os.path.exists(pyfile)):
                print(f"ERROR: File not found: {pyfile}")
                input("Press Enter to continue...")
                sys.exit(1)
        else:
            if value == "listVehicleData":
                vehicle_data = dm.getVehicleDataList()
                printVehicleData(vehicle_data);
                #main(print_options=False)
                temp_print_options = False
                continue
            elif value == "compare":
                # Select group
                if groups is None:
                    groups, prec = dm.getSessionGroups("results")
                print("\n\n\n\nChoose sessions to compare:")
                group_opts = printSessionGroups(groups, prefix="  ", prec=prec)
                print("")
                inp = ""
                while inp == "":
                    inp = input("Select groups: ")
                    if inputIsExit(inp): break;
                    filepaths = parseSessionGroupSelect(inp, group_opts, groups)
                    if filepaths is None:
                        inp = ""; continue;
                    print(filepaths)
                    print(f"Loaded {len(filepaths)} sessions.")
                inp = [inp]
                # Choose method
                while inp[0] != "" and not inputIsExit(inp[0]):
                    print("-" * 20)
                    print("Choose method:")
                    print("0 | rerun                            - compare by rerunning")
                    print("1 | best                             - compare by best achieved results")
                    print("2 | duraition                        - compare execution durations")
                    print("-" * 20)
                    print("Optional arguments:")
                    print("-s | --stats : <stat>,<stat>,...     - only show for listed stats")
                    print("-nv | --no-values                    - don't include exact value labels")
                    print("-nl | --no-legend                    - don't include legend")
                    print("-c | --centerize                     - center the data")
                    inp = input("> ").split(' ')
                    print("\n" * 1)
                    args = parseCompare(inp)
                    if inp[0] == "-s" or inp[0] == "s" or inp[0] == "-stats" or inp[0] == "--stats":
                        params = Parameters.config()
                        base_stat_list = params.getGroup("reward")
                        print(f"Base stats:({base_stat_list})")
                    if inp[0] == "0" or inp[0] == "rerun":
                        rerunAndCompare(filepaths, args);
                    elif inp[0] == "1" or inp[0] == "best":
                        compareByBest(filepaths, args);
                    elif inp[0] == "2" or inp[0] == "duration" or inp[0] == "time":
                        compareByDuration(filepaths, args);
                    print("\n" * 3)
                print("Returning to main menu...\n\n");
                continue; #sys.exit(0)

        ## Network
        # if vehicle data selected use the attached network
        if "vehicle-data" in args:
            vehicle_data_filepath = args["vehicle-data"]
            vehicle_data_name = pathlib.Path(vehicle_data_filepath).name
            metadata = dm.getVehicleDataMetadata(vehicle_data_name)
            network_name = metadata["network_name"]
            args["vehicle-data"] = vehicle_data_name
        # else let user select
        else:
            networks_data, default_net = dm.getNetworkList("networks")
            print()
            if value == "generateChargeData":
                print("Generate charge data for network:")
            else:
                print("Run on network:")
            printNetworks(networks_data, default_net)

            network_name = input("Select available: ").strip()

            if not network_name:
                network_name = "manhattan" if (default_net is None) else default_net
            elif network_name.isdigit():
                network_name = networks_data[int(network_name)][0]
        # Join
        network_filepath = os.path.join("networks", network_name)

        # Check if network exists
        if not os.path.exists(network_filepath):
            print(
                f'ERROR: Network folder not found: "{network_name}" '
                f'(path: "{network_filepath}")'
            )
            input("Press Enter to continue...")
            continue; #main()

        # Confirm
        params = Parameters.config()
        print(f"\n{value}")
        if AGENT_COUNT > 1:
            print(f"  - Agents:             {AGENT_COUNT}")
        print(f"  - Network:            {network_name}")
        if "iterations" in args:
            print(f"  - Iterations:         {int(args['iterations'])}")
        else:
            print(f"  - Iterations:         {params['training.iterations']}")
        centralized = params["station.routing.centralized"]
        stationfinder = params["station.routing.useStationFinder"]
        if stationfinder:
            print("  - Routing:            Stationfinder")
        elif centralized:
            print("  - Routing:            centralized");
        else:
            print("  - Routing:            selfish")
        if "vehicle-data" in args:
            print(f"  - Vehicle data:       {vehicle_data_name}")
            print(f"      - vehicle count:  {metadata['vehicle_count']}")
            print(f"      - EV count:       {metadata['EV_count']}")
            #print(f"    - network:       {metadata['network_name']}")
        else:
            print("  vehicle data: generate")
        inp = input("Confirm (anything for no): ")
        if inp != "": continue; main(True);

        if pyfile is not None:
            # Call
            args = stringifyArgs(args)
            system = platform.system()
            if system == "Windows":
                proc = subprocess.Popen(
                    f'start "{value}" cmd /k "{VENV_PYTHON} {pyfile} {network_name} {args}"',
                    shell=True)
                #proc = subprocess.Popen(
                #    ["cmd", "/k", VENV_PYTHON, pyfile, network_name] + args,
                #    creationflags=subprocess.CREATE_NEW_CONSOLE
                #    )
                #out, err = proc.communicate()
                #print("STDOUT:\n", out)
                #print("STDERR:\n", err)
                #print("Return code:", proc.returncode)
            else:
                cmd = [VENV_PYTHON, pyfile, network_name]
                proc = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
            #proc.wait()
        else:
            if value == "generateChargeData":
                generateVehicleData(network_name);
            else: raise Exception(f"ERROR: Unknown command '{value}'");
        print("\n\n\n")

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
    
    main();
    sys.exit(0)
