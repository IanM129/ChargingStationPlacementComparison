import matplotlib.pyplot as plt
import networkx as nx

import lib.graphing as graphing
import lib.graphing.draw as graphdraw




# 5 rows × 8 columns
G = nx.grid_2d_graph(4, 4)

# Nodes are already coordinate tuples: (row, col)
pos = {(r, c): (c, -r) for r, c in G.nodes()}
nx.set_node_attributes(G, pos, "pos")

fig, ax = plt.subplots()
graphdraw.drawGraph(G, edge_labels=False, node_labels=False, node_size=1000)
fig.show()
line_G = graphing.lineGraph(G)
fig, ax = plt.subplots()
graphdraw.drawGraph(line_G, edge_labels=False, node_labels=False, node_size=1000)
fig.show()

print(len(G.nodes()), "->", len(line_G.nodes()))
print(len(G.edges()), "->", len(line_G.edges()))
