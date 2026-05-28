def genSumoCommand(sumo_filepath, step_length, visualize,
                   trip_stats_filepath=None, log_filepath=None,
                   warnings=False):
    sumo_binary = "sumo-gui" if visualize else "sumo"
    cmnd = [sumo_binary, "-c", sumo_filepath,
            "--step-length", str(step_length), "--start"]
    if trip_stats_filepath != None:
        cmnd.extend(["--tripinfo-output", trip_stats_filepath])
    if log_filepath != None:
        cmnd.extend(["--log", log_filepath])
    if visualize:
        cmnd.extend(["--delay", str(step_length * 1000)])
    if not warnings:
        cmnd.extend(["--no-warnings", "true"])
    return cmnd
