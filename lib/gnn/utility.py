import numpy as np

import torch


def formEdgeAttributes(vals : dict, num_edges : int=0, keys : list[str]=None):
    if num_edges < 1: num_edges = len(vals[keys[0]]);
    if keys == None: keys = vals.keys();
    edges = list(vals[keys[0]].values())
    edge_attr = torch.tensor(
        [[vals[k][edges[i]] for k in keys] for i in range(num_edges)],
        #[list(vals[k].values()) for k in keys],
        dtype=torch.float
    )
    return edge_attr
