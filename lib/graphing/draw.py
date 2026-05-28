import networkx as nx
import matplotlib.pyplot as plt

import lib.graphing.utility as graphutil


## Presentation
def setColors(color_dict, nodes, color):
    for node in nodes:
        color_dict[node] = color
    return color_dict

def drawGraph(G, base_color="red", node_colors=None, edge_colors=None, node_labels=True, edge_labels=True):
    plt.clf()
    pos = nx.get_node_attributes(G, "pos")
    colors = []
    for node in G.nodes():
        if node_colors != None and node in node_colors:
            colors.append(node_colors[node])
        else: colors.append(base_color);
    edge_colors_arr = []
    for edge in G.edges():
        if edge_colors != None and edge in edge_colors:
            edge_colors_arr.append(edge_colors[edge])
        else: edge_colors_arr.append("black");
    nx.draw(G, pos=pos, 
        node_color=colors,
        edge_color=edge_colors_arr,
        with_labels=node_labels,
        node_size=250)
    if edge_labels:
        edge_lbls = nx.get_edge_attributes(G, "length")
        for k, val in edge_lbls.items():
            edge_lbls[k] = round(val, 2)
        nx.draw_networkx_edge_labels(G, pos, edge_lbls, label_pos=0.3)


def drawCenters(G, centers, radius, ax=None, base_node_clr="grey",
                node_colors={}, node_labels=True, node_size=100,
                edge_labels=False):
    # Coverage
    nodes_covered = set(); edges_covered = set();
    for i in range(len(centers)):
        nodes_covered = nodes_covered.union(graphutil.getNodesInRadius(G, centers[i], radius))
        edges_covered = edges_covered.union(graphutil.getEdgesInRadius(G, centers[i], radius, ignore_edges=edges_covered))
    pos = nx.get_node_attributes(G, "pos")
    node_colors_arr = []
    centers_detected = set()
    for node in G.nodes():
        if node in node_colors: node_colors_arr.append(node_colors[node]);
        elif node in centers:
            node_colors_arr.append("green"); centers_detected.add(node);
        elif node in nodes_covered: node_colors_arr.append("lightgreen");
        else: node_colors_arr.append(base_node_clr);
    miss = set(centers) - centers_detected
    if len(miss) > 0:
        raise Exception("Didn't detect some of the centers:\n- " + str(miss) + " / " + str(centers))
    edge_colors_arr = []
    for edge in G.edges():
        if edge in edges_covered: edge_colors_arr.append("green");
        else: edge_colors_arr.append("black");
    nx.draw(G, ax=ax, pos=pos,
        node_color=node_colors_arr,
        edge_color=edge_colors_arr,
        with_labels=node_labels,
        node_size=node_size)
    if edge_labels:
        edge_labels = nx.get_edge_attributes(G, "length")
        for k, val in edge_labels.items():
            edge_labels[k] = round(val, 2)
        nx.draw_networkx_edge_labels(G, pos, edge_labels, ax=ax, label_pos=0.3)

def drawCoverage(G, stations, radius, covered, remaining_nodes):
    node_colors = {};
    for nc in covered:
        if nc in remaining_nodes: node_colors[nc] = "lightblue";
        else: node_colors[nc] = "teal";
    if closest == stations[i]: node_colors[stations[i]] = "purple";
    else:
        node_colors[closest] = "red"; node_colors[stations[i]] = "blue";
    drawCenters(G, [x for x in stations if x != None], radius, node_colors=node_colors, node_labels=False)                
    plt.show()

def drawEdgeWeights(G, edge_weights, ax=None, default_width=0.0):
    pos = nx.get_node_attributes(G, "pos")
    widths = []
    for edge in G.edges():
        if edge in edge_weights:
            #print(edge, "found:", float(edge_weights[edge]))
            widths.append(float(edge_weights[edge]))
        elif (edge[1], edge[0]) in edge_weights:
            #print(edge, "found (as reverse):", float(edge_weights[(edge[1], edge[0])]))
            widths.append(float(edge_weights[(edge[1], edge[0])]))
        else:
            #print(edge, "not found")
            widths.append(default_width)
    #print(list(edge_weights.keys())[:10])
    #print(list(G.edges())[:10])
    nx.draw_networkx_edges(G, pos, ax=ax, arrows=False, width=widths)

def drawNodes(G, nodelist, node_size=300, color="#1f78b4"):
    pos = nx.get_node_attributes(G, "pos")
    nx.draw_networkx_nodes(G, pos, nodelist=nodelist,
                           node_size=node_size, node_color=[color])

def drawCircleStations(G, net, station_edges, fig, ax, circle_size=50, color="#1f78b4", font_size=12, station_weights=None, show=False):
    pos = nx.get_node_attributes(G, "pos")
    handles = []
    legend_labels = []
    for i in range(len(station_edges)):
        s = station_edges[i]
        net_edge = net.getEdge(s)
        node_f = net_edge.getFromNode(); node_t = net_edge.getToNode();
        pos_f = pos[node_f.getID()]; pos_t = pos[node_t.getID()];
        v = (pos_t[0] - pos_f[0], pos_t[1] - pos_f[1])
        pos_s = (pos_f[0] + (v[0] / 2.0), pos_f[1] + (v[1] / 2.0));
        if station_weights != None and s in station_weights:
            label = str(station_weights[s])
        else: label = None;
        circle = plt.Circle(pos_s, circle_size / 2.0, color=color, fill=True, label=label)
        ax.add_patch(circle)
        ax.set_aspect('equal')
        if station_weights != None and s in station_weights:
            # Add index text
            ax.text(pos_s[0], pos_s[1], str(i), ha='center', va='center', fontsize=font_size, color="white")
            # Legend
            handles.append(circle)#plt.Line2D([0], [0]))
            legend_labels.append(f"{i}: {station_weights[s]}")
    if station_weights != None:
        fig.legend(handles, legend_labels, loc="outside right upper")
    #if station_weights != None: return handles;
    return
