import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import TransformerConv

import numpy as np


class EdgePosGNN(nn.Module):
    def __init__(self, node_dim, edge_dim, hidden_dim):
        super().__init__()

        # Encode edge features + geometry
        self.edge_encoder = nn.Sequential(
            nn.Linear(edge_dim + 1, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
        )
        
        self.conv1 = TransformerConv(node_dim, hidden_dim, edge_dim=hidden_dim, beta=True)
        self.conv2 = TransformerConv(hidden_dim, hidden_dim, edge_dim=hidden_dim, beta=True)
        self.lrelu = nn.LeakyReLU(0.1)
        # Edge scoring MLP; inputs [Node_A, Road_Attributes, Node_B]
        self.edge_mlp = nn.Sequential(
            nn.Linear(3 * hidden_dim + 1, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1)
        )
        
    def forward(self, x, edge_index, edge_attr, pos):
        src, dst = edge_index
        ## Geometry from node positions
        edge_vec = pos[dst] - pos[src]
        edge_dist = torch.norm(edge_vec, dim=1, keepdim=True)
        # Combine learned edge attrs + geometry
        edge_feat = torch.cat([edge_attr, edge_dist],
                              dim=1)
        edge_feat = self.edge_encoder(edge_feat)
        ## Message passing
        h = self.conv1(x, edge_index, edge_feat)
        h = self.lrelu(h)
        h = self.conv2(h, edge_index, edge_feat)
        h = self.lrelu(h)
        # Edge scoring
        edge_emb = torch.cat([h[src], edge_feat, h[dst], edge_dist], dim=-1)
        scores = self.edge_mlp(edge_emb).squeeze(-1)
        return scores
