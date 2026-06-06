import numpy as np
import matplotlib.pyplot as plt

def compare_lists(a : list, b : list):
    max_len = max(len(a), len(b))
    print("Compare lists (" + str(len(a)) + "|" + str(len(b)) + "):\n", end="")
    res = ""
    for i in range(max_len):
        val_a = a[i] if (len(a) > i) else None
        val_b = b[i] if (len(b) > i) else None
        res += f"  {i:5d}: {str(val_a):10s} | {str(val_b):10s}\n"
    print(res)
    return
def compare_dics(a : dict, b : dict):
    all_keys = a.keys() + b.keys()
    print(len(a.keys()),"|", str(len(b.keys())) + ":")
    for key in all_keys:
        val_a = a.get(key, None)
        val_b = b.get(keys, None)
        print(" ", key, ":", f"{str(val_a):10s} | {str(val_b):10s}")
    return


#### Plotting
def getAgentColors(): return ["red", "blue", "green", "orange", "purple", "olive", "brown", "cyan", "pink", "gray"];
max_coverage = None
def getPlotMetadata(stat):
    data = {"title": "",
            "unit" : "",
            "label": "Total"}
    match (stat):
        case "totalCoverage" | "coverage":
            data["title"] = "Coverage radius"
            if stat == "totalCoverage": data["title"] += " (Total)";
            data["unit"] = "Meters (m)"
            data["label"] = "Global"
            global max_coverage
            if max_coverage is not None:
                data["title"] += f" [max {max_coverage:0.2f} m]";
        case "totalCharge" | "charge":
            data["title"] = "Charge"
            if stat == "totalCharge": data["title"] += " (Total)";
            data["unit"] = "Watt hours (Wh)"
        case "simDuration":
            data["title"] = "Simulation duration"
            data["unit"] = "Seconds (s)"
        case "tripDuration":
            data["title"] = "Trip duration (average)"
            data["unit"] = "Seconds (s)"
        case "tripLength":
            data["title"] = "Trip length (average)"
            data["unit"] = "Meters (m)"
        case "waitTime":
            data["title"] = "Watiting time (average)"
            data["unit"] = "Seconds (s)"
        case "stopTime":
            data["title"] = "Stopped time (average)"
            data["unit"] = "Seconds (s)"
        case "timeLoss":
            data["title"] = "Time lost (average)"
            data["unit"] = "Seconds (s)"
        case "energyConsumed":
            data["title"] = "Energy consumed (average)"
            data["unit"] = "Watt hours (Wh)"
        case "totalMoneyEarned" | "moneyEarned":
            data["title"] = "Money earned"
            if stat == "totalMoneyEarned": data["title"] += " (Total)";
            data["unit"] = "Euro (€)"
        case "price":
            data["title"] = "Charge price"
            data["unit"] = "Euro (€) per kWh"
        case "reward" | "generalReward":
            data["title"] = "Reward"
            data["label"] = ""
    return data
def createPlotFigure(metadata):
    fig = plt.figure()
    # Set integer X line
    ax = fig.gca()
    ax.xaxis.get_major_locator().set_params(integer=True)
    # Set metadata
    fig.suptitle(metadata["title"])
    ax.set_ylabel(metadata["unit"])
    ax.set_xlabel("Iteration")
    return (fig, ax)
def combineFigures(axes, metadata):
    fig, ax = createPlotFigure(metadata)
    lines = []
    for ax_og in axes:
        for og_line in ax_og.lines:
            x = og_line.get_xdata(); y = og_line.get_ydata();
            label=og_line.get_label();
            if "agent" not in label:
                color = "black"
            else:
                color = label.split(' ', 1)[0].lower();
            line = ax.plot(x, y, color=color, label=label)
            if isinstance(line, list): lines.extend(line);
            else: lines.append(line);
    ax.legend(handles=lines)
    return (fig, ax)
def plotTrainingResults_figs(train_results, iterations, agent_colors=[]):
    figs = {}
    x = np.arange(0, iterations)
    for stat in train_results:
        if stat == "stations": continue;
        metadata = getPlotMetadata(stat)
        data = train_results[stat]
        if len(data.shape) > 1:
            fig, ax = createPlotFigure(metadata)
            handles = []
            for a in range(len(data)):
                line, = ax.plot(x, data[a], agent_colors[a], label=agent_colors[a].capitalize() + " agent")
                handles.append(line)
            ax.legend(handles=handles)
            figs[stat] = (fig, ax)
        else:
            fig, ax = createPlotFigure(metadata)
            ax.plot(x, data, label=metadata["label"])
            figs[stat] = (fig, ax)
    return figs
## High
def plotGNN(train_results, iterations=None):
    if iterations is None:
        iterations = int(train_results["simDuration"].shape[0])
    figs = plotTrainingResults_figs(train_results, iterations)
    return figs
def plotMARL(train_results, iterations=None, agent_colors=None):
    if iterations is None:
        iterations = int(train_results["simDuration"].shape[0])
    if agent_colors is None:
        agent_colors = getAgentColors();
    # Write plot figures
    figs = plotTrainingResults_figs(train_results, iterations, agent_colors=agent_colors)
    # Combine similar
    # reward
    metadata = getPlotMetadata("reward");
    metadata["title"] += " (Combined)";
    figs["rewardCombined"] = combineFigures([figs["generalReward"][1], figs["reward"][1]], metadata);
    # coverage
    metadata = getPlotMetadata("coverage");
    temp_title = metadata["title"].split('[', 1)
    if len(temp_title) > 1:
        metadata["title"] = temp_title[0] + " (Combined) [" + temp_title[1];
    figs["coverageCombined"] = combineFigures([figs["totalCoverage"][1], figs["coverage"][1]], metadata)
    # charge
    metadata = getPlotMetadata("charge");
    metadata["title"] += " (Combined)";
    figs["chargeCombined"] = combineFigures([figs["totalCharge"][1], figs["charge"][1]], metadata)
    return figs

## Other
def setMaxCoverageRadius(value):
    global max_coverage
    max_coverage = value
