import numpy as np
import matplotlib.pyplot as plt


def statDisplayName(stat):
    stat_names = {
        "totalCoverage": "Globalni radijus pokrivenosti",
        "totalCharge": "Ukupna napunjena energija",
        "simDuration": "Vrijeme izvršavanja",
        "tripDuration": "Dugotrajnost puta",
        "tripLength": "Duljina puta",
        "waitTime": "Vrijeme čekanja",
        "stopTime": "Vrijeme stajanja",
        "timeLoss": "Izgubljeno vrijeme",
        "energyConsumed": "Iskorištena energija",
        # Competitive
        "coverage": "Radijus pokrivenosti",
        "charge": "Napunjena energija",
        "moneyEarned": "Ukupna zarada"
    }
    if stat in stat_names: return stat_names[stat];
    return stat
    

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


#### Printing
def printResults_general(results, params):
    fully_completed = results.fullyCompleted
    sim_time = results.simulationTime
    exec_duration = results.executionDuration
    steps_processed = int(sim_time / params["stepLength"])
    print(f"-------- Simulation over at {sim_time} ({steps_processed} steps); after {exec_duration:0.2f} seconds" + (f"(max duration reached ({params['sim.maxDuration']}))" if not fully_completed else ""))
    veh_cnt = results.vehicle_data["vehicleCount"]
    EV_cnt = results.vehicle_data["electricCount"]
    EV_arrived = results.vehicle_data["electricArrived"]
    EV_set_charge = results.vehicle_data["electricSetToCharge"]
    EV_charged = results.vehicle_data["electricCharged"]
    print(f"         vehicle count: {veh_cnt:6d}")
    print(f"             - electric: {EV_cnt:6d} ({round((EV_cnt / veh_cnt)*100, 2):4.2f} %; expected {round((params['electric.penetration'])*100, 2):4.2f} %)")
    print("             > successfully charged:   {0:16s} | {1}%".format(f"{EV_charged} / {EV_set_charge}", round((EV_charged / EV_set_charge) * 100.0, 2)))
    print("             > arrived at destination: {0:16s} | {1}%".format(f"{EV_arrived} / {EV_cnt}", round((EV_arrived / EV_cnt) * 100.0, 2)))
def printResults_trips(results):
    EV_cnt = results.vehicle_data["electricCount"]
    print(f"Trip info (all are averages [{EV_cnt}]):")
    print("  - trip duration:   ", round(results.trip_data["tripDuration"], 2), "s")
    print("  - trip distance:   ", round(results.trip_data["tripLength"], 2), "m")
    print("  - wait time:       ", round(results.trip_data["waitTime"], 2), "s")
    print("  - times waited:    ", round(results.trip_data["waitCount"], 2), "times")
    print("  - time stopped:    ", round(results.trip_data["stopTime"], 2), "s")
    print("  - time lost:       ", round(results.trip_data["timeLoss"], 2), "s")
    #print("  - energy consumed: ", round(results.trip_data["energyConsumed"], 2), "Wh")
def printResults_solo(results):
    stations = list(results.station_data["charged"].keys())
    prec = len(max(stations, key=len))
    print("Total charge used per station | utilization rate:")
    if "vehicleCount" in results.station_data:
        print("    <station edge ID>: <energy recharged> | <vehicles_visited> (<occupancy>, <utilization>)")
    else:
        print("    <station edge ID>: <energy recharged> | (<occupancy>, <utilization>)")
    for edge in stations:
        edge_id = results.translator.edgeToID(edge)
        #edge = results.translator.IDToEdge(si.edge_id)
        total = results.station_data["charged"][edge]
        occup_rate = results.station_data["occupancyRate"][edge]
        util_rate = results.station_data["utilization"][edge]
        if "vehicleCount" in results.station_data:
            veh_cnt = results.station_data["vehicleCount"][edge]
            print(f"    {edge_id:{prec}s}: {round(total, 2):9.2f} | {veh_cnt:4d} | ",
                  f"({round(occup_rate * 100.0,2):5.2f} %, {round(util_rate * 100.0,2):5.2f} %)")
        else:
            print(f"    {edge_id:12s}: {round(total, 2):9.2f} | ",
                  f"({round(occup_rate * 100.0,2):5.2f} %, {round(util_rate * 100.0,2):5.2f} %)")
    total_charge = results.station_data["totalCharge"]
    money_earned = results.station_data["totalMoneyEarned"]
    price = results.station_data["price"]
    print(f"  > total charge: {round(total_charge / 1000.0, 2)} kWh")
    print(f"  > money earned: {round(money_earned, 2)}€ ({round(price,2)}€ per kWh)")
def printResults_comp(results):
    suffixes = list(results.station_data["charged"].keys())
    all_stations = []
    for suffix in suffixes:
        all_stations.extend(list(results.station_data["charged"][suffix].keys()))
    prec = len(max(all_stations, key=len))
    ## Color specific stats
    print("Station stats:")
    if "vehicleCount" in results.station_data:
        print("    <station edge ID>: <energy recharged> | <vehicles_visited> | (<occupancy>, <utilization>)")
    else:
        print("    <station edge ID>: <energy recharged> | (<occupancy>, <utilization>)")
    for suffix in suffixes:
        clr_name = str(suffix[1:].capitalize())
        stations = list(results.station_data["charged"][suffix].keys())
        print(f"  -- {clr_name}:");
        for edge in stations:
            edge_id = results.translator.edgeToID(edge)
            charge = results.station_data["charged"][suffix][edge]
            occup_rate = results.station_data["occupancyRate"][suffix][edge]
            util_rate = results.station_data["utilization"][suffix][edge]
            if "vehicleCount" in results.station_data:
                veh_cnt = results.station_data["vehicleCount"][suffix][edge]
                print(f"    {edge_id:{prec}s}: {round(charge, 2):9.2f} | {veh_cnt:4d} | ",
                      f"({round(occup_rate * 100.0,2):5.2f} %, {round(util_rate * 100.0, 2):4.2f} %)")
            else:
                print(f"    {edge_id:{prec}s}: {round(charge, 2):9.2f} | ",
                      f"({round(occup_rate * 100.0,2):5.2f} %, {round(util_rate * 100.0, 2):4.2f} %)")
        total_charge = results.agent_data["totalCharge"][suffix]
        money_earned = results.agent_data["moneyEarned"][suffix]
        price = results.station_data["price"][suffix]
        print(f"  > total charge: {round(total_charge/1000.0, 2)} kWh")
        print(f"  > money earned: {round(money_earned,2)}€ ({round(price,2)}€ per kWh)\n")
    total_charge = results.station_data["totalCharge"]
    total_money_earned = results.station_data["totalMoneyEarned"]
    print(f"> total charge overall:       {round(total_charge/1000.0,2)} kWh")
    print(f"> total money earned overall: {round(total_money_earned,2)}€")



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
        case "loss":
            data["title"] = "Loss"
    return data
def createPlotFigure(metadata):
    fig = plt.figure()
    # Set integer X line
    ax = fig.gca()
    ax.xaxis.get_major_locator().set_params(integer=True)
    # Set metadata
    fig.suptitle(metadata["title"])
    fig.canvas.manager.set_window_title(metadata["title"])
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
def plotResultDataset(results_ds, names, params, stat_list=None,
                      invert_min=False,
                      legend=True, value_labels=True, centerize=False, 
                      croatian=True):
    from lib.structs.evaluation import getStatFromResult
    from lib.utility import isMinOrMax, invertRange
    default_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    if isinstance(params, list):
        params_arr = params
        stats = sorted(params_arr[0].getGroup("reward"))
    else:
        params_arr = None;
        stats = sorted(params_arr.getGroups("reward"))
    if stat_list is not None:
        stats = set(stat_list).intersection(stats)
    stats = sorted(stats)
    if croatian:
        stats_display = [statDisplayName(s) for s in stats];
    else: stats_display = stats;
    # Get values
    real_vals = results_ds.realStats(params, stat_list=stats)
    norm_vals = results_ds.normalizedStats(params, stat_list=stats, invert_by_coeff=False)
    # Extract
    ext_vals = {}
    for stat in stats:
        vals = []
        for i in range(len(results_ds.arr)):
            vals.append(norm_vals[i][stat])
        # Invert if minimizing or coefficient is negative
        if invert_min:
            invert = False
            if (isMinOrMax(stat) == -1): invert = True;
            ext_vals[stat] = invertRange(vals) if invert else vals
        else: ext_vals[stat] = vals;
    # Create plot data
    data = {}
    for i in range(len(results_ds.arr)):
        vals = []
        for stat in stats:
            vals.append(ext_vals[stat][i])
        data[names[i]] = vals
    # Plot
    fig, ax = plt.subplots()
    if len(stats) > 1:
        if centerize:
            vals = [];
            for i in range(len(stats)):
                vals.append([]);
                for name in names:
                    vals[i].append(data[name][i])
            min_vals = []; deltas = [];
            for i in range(len(stats)):
                min_val = min(vals[i])
                max_val = max(vals[i])
                min_vals.append(min_val)
                deltas.append(max_val - min_val)
            for name in data:
                for i in range(len(stats)):
                    data[name][i] = (0.1 + ((data[name][i] - min_vals[i]) * (0.9 / deltas[i])))
        plot = ax.grouped_bar(data, tick_labels=stats_display, group_spacing=1, orientation="horizontal")
        if value_labels:
            for i in range(len(plot.bar_containers)):
                container = plot.bar_containers[i]
                labels = [f"{real_vals[i][stat]:.2f}" for stat in stats]
                ax.bar_label(container, padding=3,labels=labels)
        ax.set_title("Usporedba rezultata")
        ax.set_xlabel("Normalizirani uspjeh")
    else:
        values = []
        #for val in data.values(): values.append(val[0]);
        for i in range(len(names)): values.append(real_vals[i][stats[0]]);
        bars = ax.barh(names, values, color=default_colors[:len(names)])
        if centerize:
            min_val = min(values); max_val = max(values);
            delta = max_val - min_val
            ax.set_xlim(max(min_val - (0.1 * delta), 0.0), max_val + (0.1 * delta))
        if value_labels:
            labels = [f"{real_vals[i][stats[0]]:.2f}" for i in range(len(names))]
            ax.bar_label(bars, labels, padding=3)
        stat_title = ""
        for i in range(len(stats[0])):
            if stats[0][i].isupper():
                stat_title += " ";
            stat_title += stats[0][i].lower()
        ax.set_title(stat_title.capitalize() + " comparison")
        ax.set_ylabel("Normalizirani uspjeh")
    if legend: ax.legend(loc="best");
    return fig
def plotCompetitiveResultDataset(results_ds, names, params, stat,
                                  invert_min=False,
                                  legend=True, value_labels=True, centerize=False, 
                                  croatian=True):
    from lib.structs.evaluation import getStatFromResult
    from lib.utility import isMinOrMax, invertRange
    default_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    if isinstance(params, list):
        params = params[0]
    stats = sorted(params.getGroup("compReward"))
    if stat not in stats: 
        print("Invalid stat given")
        return;
    if croatian:
        stat_display = statDisplayName(stat)
    else: stat_display = stat;
    # Get values
    real_vals = results_ds.realStats(params, stat_list=[stat])
    norm_vals = results_ds.normalizedStats(params, stat_list=[stat], invert_by_coeff=False)
    # Extract
    ext_vals = []
    for i in range(len(results_ds.arr)):
        val = norm_vals[i][stat]
        # Invert if minimizing or coefficient is negative
        if invert_min:
            invert = False
            if (isMinOrMax(stat) == -1): invert = True;
            val = invertRange(val) if invert else val
        ext_vals.append(val);
    # Create plot data
    data = []
    max_len = len(max([ev for ev in ext_vals if ev is not None], key=len))
    for i in range(max_len):
        vals = []
        for j in range(len(ext_vals)):
            if ext_vals[j] is not None:
                if i < len(ext_vals[j]):
                    vals.append(ext_vals[j][i]);
                else: vals.append(np.nan);
        data.append(vals)
    # Plot
    fig, ax = plt.subplots()
    bars = ax.grouped_bar(data, group_spacing=1, orientation="horizontal")
    if value_labels:
        for i in range(len(bars.bar_containers)):
            container = bars.bar_containers[i]
            labels = [f"{data[i][j]:.2f}" for j in range(max_len)]
            ax.bar_label(container, padding=3, labels=labels)
    ax.set_yticks(range(len(data[0])))
    ax.set_yticklabels([names[i] for i in range(len(names)) if ext_vals[i] is not None])
    ax.set_title(stat_display.capitalize())
    ax.set_ylabel("Normalizirana vrijednost")
    #if legend: ax.legend(loc="best");
    return fig
def plotCompetitiveValues(values, names, stat_name,
                          title="Title", xlabel="Normalizirana vrijednost",
                          invert_min=False,
                          legend=True, value_labels=True, centerize=False, 
                          croatian=True):
    from lib.structs.evaluation import getStatFromResult
    from lib.utility import isMinOrMax, invertRange
    import matplotlib.patches as mpatches
    default_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    # Create plot data
    data = []
    max_len = len(max(values, key=len))
    for i in range(max_len):
        vals = []
        for j in range(len(values)):
            if i < len(values[j]):
                vals.append(values[j][i]);
            else: vals.append(np.nan);
        data.append(vals)
    # Colors
    colors = []
    seen = {}
    for name in names:
        if name in seen:
            seen[name] += 1
        else:
            seen[name] = 0
        colors.append(seen[name] % len(default_colors))
    # Plot
    fig, ax = plt.subplots()
    bars = ax.grouped_bar(data, group_spacing=1, orientation="horizontal")
    if value_labels:
        for i in range(len(bars.bar_containers)):
            container = bars.bar_containers[i]
            labels = [f"{v:.2f}" if not np.isnan(v) else "" for v in data[i]]
            ax.bar_label(container, padding=3, labels=labels)
    # Colors
    for i, container in enumerate(bars.bar_containers):
        color = default_colors[i % len(default_colors)]
        j = 0
        for bar in container:
            bar.set_color(default_colors[colors[j]])
            j += 1
    ax.set_yticks(range(len(data[0])))
    ax.set_yticklabels([names[i] for i in range(len(names))])
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    #if legend: ax.legend(loc="best");
    if max(colors) > 0:
        handles = [mpatches.Patch(color=default_colors[0],label="Centralizirano"),
                   mpatches.Patch(color=default_colors[1],label="Sebično")]
        ax.legend(handles=handles, loc="best");
    return fig
def plotScores(scores, names, title="Usporedba uspješnosti", ylabel="Uspjeh",
               legend=True, value_labels=True):
    default_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    # Define colors per type
    data = {}
    colors = []
    labels = []
    cnt = {}
    for i in range(len(scores)):
        name = names[i]; score = scores[i];
        name_i = names.index(name)
        cnt[name] = cnt.get(name, -1) + 1
        if cnt[name] == 0: labels.append(name);
        colors.append(default_colors[cnt[name]])
        if cnt[name] not in data: data[cnt[name]] = [];
        data[cnt[name]].append(score)
    # Plot
    fig, ax = plt.subplots()
    if max(cnt.values()) > 0:
        bars = ax.grouped_bar(data, tick_labels=labels, group_spacing=1)
        if value_labels:
            for i in range(len(bars.bar_containers)):
                container = bars.bar_containers[i]
                ax.bar_label(container, padding=3)
        ax.legend(["Centralizirano", "Sebično"])
    else:
        bars = ax.bar(names, scores)
        if value_labels: ax.bar_label(bars, padding=3);
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    return fig
    
## High
def plotSolo(train_results, iterations=None):
    if iterations is None:
        iterations = int(train_results["simDuration"].shape[0])
    figs = plotTrainingResults_figs(train_results, iterations)
    return figs
def plotComp(train_results, iterations=None, agent_colors=None):
    if iterations is None:
        iterations = int(train_results["simDuration"].shape[0])
    if agent_colors is None:
        agent_colors = getAgentColors();
    # Write plot figures
    figs = plotTrainingResults_figs(train_results, iterations, agent_colors=agent_colors)
    # Combine similar
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
