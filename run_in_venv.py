import os
import sys
import pathlib
from datetime import datetime
import subprocess
import platform

from lib.data_management import getNetworkList

from lib.utility import generateRandomChargeData, writeChargeData, loadChargeData

from lib.structs.params import Parameters

VENV_PYTHON = os.path.join("_venv", "Scripts", "python.exe")




# Check if venv exists
if not os.path.exists(VENV_PYTHON):
    print("ERROR: venv not found.")
    input("Press Enter to continue...")
    sys.exit(1)

print()
print("==========================")
print("Choose an option to run:")
print("0 gen            - generate new vehicle data in '/vehicle_data'")
print("1 blank          - run a blank example (no charging stations)")
print("2 solo           - run an algorithmic solo simulation")
print("3 comp           - (default) run an algorithmic competitive simulation")
print("4 gnn            - trains a solo network")
print("5 marl           - trains two competing networks")
print("6 game           - finds the placement through a game theory based algorithm")
print("==========================")
print("Arguments:")
print("-v | --vehicles : <filepath> | <index>      - use specific vehicle data")

choice = input("\n> ")

if choice == "": choice = "comp";

command = choice.split(' ')[0]
args = ' '.join(choice.split(' ')[1:])
#print(args)

options = {
    "0": (None, "generateChargeData"),
    "gen": (None, "generateChargeData"),
    
    "1": ("blank.py", "Blank simulation"),
    "blank": ("blank.py", "Blank simulation"),

    "2": ("solo.py", "Solo algorithm"),
    "solo": ("solo.py", "Solo algorithm"),

    "3": ("comp.py", "Competitive algorithm"),
    "comp": ("comp.py", "Competitive algorithm"),

    "4": ("gnn.py", "Graph NN RL"),
    "gnn": ("gnn.py", "Graph NN RL"),

    "5": ("marl.py", "Multi-Agent RL"),
    "marl": ("marl.py", "Multi-Agent RL"),

    "6": ("game.py", "Equilibrium game algorithm"),
    "game": ("game.py", "Equilibrium game algorithm"),
}

key = command.lower()

if key not in options:
    print(f'\nERROR: Invalid choice "{choice}".')
    input("Press Enter to continue...")
    sys.exit(1)

pyfile, value = options[key]

# Check if file exists
if (pyfile is not None) and (not os.path.exists(pyfile)):
    print(f"ERROR: File not found: {pyfile}")
    input("Press Enter to continue...")
    sys.exit(1)

# Detect network options
networks_data, default_net = getNetworkList("networks")
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
        # Import modules
        import xml.etree.ElementTree as ET
        import sumolib
        import preprocess as prep
        import lib.graphing as graphing  #= lib/graphing/__init__.py
        import lib.xml.tripsGen as tripsGen
        # Prepare folder
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
                                 internal_lengths=False, node_position=True)
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
        charge_data = generateRandomChargeData(trips, max_charge)
        writeChargeData(charge_data, folder_path + "/charge_data.xml")
        vTypes_tree.write(folder_path + "/vTypes.add.xml")
        print(f"\nGenerated vehicle data in '{folder_path}'")
    else: raise Exception(f"ERROR: Unknown command '{value}'");

sys.exit(0)
