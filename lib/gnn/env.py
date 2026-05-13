import numpy as np

class RLEnv:
    def __init__(self, graph, k):
        self.graph = graph
        self.k = k
        self.num_edges = graph["edge_index"].shape[1]

    def reset(self):
        self.selected_edges = []
        return self.graph

    def step(self, action_edges):
        # action_edges: indices of selected edges
        self.selected_edges = action_edges
        reward = self.compute_reward(action_edges)
        done = True  # one-shot decision
        return self.graph, reward, done, {}

    def compute_reward(self, edges):
        # Replace with SUMO-based evaluation later
        demand = self.graph["edge_demand"]  # [num_edges]
        profit = demand[edges].sum()
        coverage_penalty = self.coverage_penalty(edges)
        return profit - coverage_penalty

    def coverage_penalty(self, edges):
        # Simple placeholder: penalize if too few edges selected
        if len(edges) < self.k:
            return 10.0
        return 0.0
