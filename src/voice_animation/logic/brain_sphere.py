"""Spherical nearest-neighbor topology and Brian's Brain transition rule."""
import math
import numpy as np


def sphere_graph(count):
    """Nearly uniform Fibonacci points, with eight closest neighbors per cell."""
    i = np.arange(count)
    y = 1 - 2 * (i + .5) / count
    angle = i * math.pi * (3 - math.sqrt(5))
    r = np.sqrt(1 - y * y)
    points = np.column_stack((r * np.cos(angle), y, r * np.sin(angle)))
    similarity = points @ points.T
    np.fill_diagonal(similarity, -np.inf)
    neighbors = np.argsort(-similarity, axis=1, kind="stable")[:, :8]
    return points, neighbors


def sphere_step(state, neighbors):
    count = (state[neighbors] == 1).sum(axis=1)
    result = np.zeros_like(state)
    result[state == 1] = 2
    result[(state == 0) & (count == 2)] = 1
    return result


