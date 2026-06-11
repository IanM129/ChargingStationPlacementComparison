import os
import sys
import pathlib


def getNetworkList(parent_folder="networks"):
    data = []
    default = None
    for folder in os.listdir(parent_folder):
        folder_path = os.path.join(parent_folder, folder)
        if os.path.isdir(folder_path):
            net_file = os.path.join(folder_path, "base_net.net.xml")
            if os.path.isfile(net_file):
                info = [folder, folder_path, ""]
                desc_file = os.path.join(folder_path, "description.txt")
                if os.path.isfile(desc_file):
                    with open(desc_file, "r", encoding="utf-8") as f: text = f.read();
                    info[2] = text
                data.append(info)
                default_file = os.path.join(folder_path, "default.txt")
                if os.path.isfile(default_file): default = folder;
    return data, default
def getVehicleDataList(parent_folder="vehicle_data"):
    data = []
    default = None
    for folder in os.listdir(parent_folder):
        folder_path = os.path.join(parent_folder, folder)
        if os.path.isdir(folder_path):
            trips_file = os.path.join(folder_path, "trips.xml")
            charge_file = os.path.join(folder_path, "charge_data.xml")
            if os.path.isfile(trips_file) and os.path.isfile(charge_file):
                data.append([folder, folder_path])
    return data
