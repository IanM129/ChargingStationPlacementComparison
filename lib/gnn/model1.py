import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import TransformerConv

import numpy as np


class EdgeGNN(nn.Module):
    def __init__(self, node_dim, edge_dim, hidden_dim):
        super().__init__()
        self.conv1 = TransformerConv(node_dim, hidden_dim, edge_dim=edge_dim)
        self.conv2 = TransformerConv(hidden_dim, hidden_dim, edge_dim=edge_dim)
        self.lrelu = nn.LeakyReLU(0.1)
        # Edge scoring MLP; inputs [Node_A, Road_Attributes, Node_B]
        self.edge_mlp = nn.Sequential(
            nn.Linear(2 * hidden_dim + edge_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1)
        )
        
    def forward(self, x, edge_index, edge_attr):
        # Update edge features based on neighbors and edge attributes
        h = self.conv1(x, edge_index, edge_attr)
        h = self.lrelu(h)
        h = self.conv2(h, edge_index, edge_attr)
        h = self.lrelu(h)

        # Combine intersections and edge features
        src, dst = edge_index
        edge_emb = torch.cat([h[src], edge_attr, h[dst]], dim=-1)
        scores = self.edge_mlp(edge_emb).squeeze(-1)
        
        return scores
