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
