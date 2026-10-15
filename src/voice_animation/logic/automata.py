"""Elementary cellular state, bounded history, and smooth band motion; no I/O."""
import math
import numpy as np
from ..config import (
    ORBIT_WARMUP, ORBIT_GENERATION_RATE, ORBIT_ROTATION_ATTACK,
    ORBIT_ROTATION_RELEASE, ORBIT_CELLS,
)


def elementary_step(cells, rule):
    """Advance a binary ring with periodic boundaries using an elementary rule."""
    code = (np.roll(cells, 1) << 2) | (cells << 1) | np.roll(cells, -1)
    return ((rule >> code) & 1).astype(np.uint8)


class OrbitBand:
    def __init__(self, initial_cells, rule, history_length, idle_speed):
        self.rule = rule
        self.initial_cells = np.array(initial_cells, dtype=np.uint8, copy=True)
        self.cells = self.initial_cells.copy()
        self.history = []
        for _ in range(ORBIT_WARMUP):
            self.cells = elementary_step(self.cells, rule)
            self.history.append(self.cells.copy())
        # Preserve the selected experiment's initial history and setup transfer.
        self.history = self.history[:history_length]
        self.phase = self.angle = 0.0
        self.angular_speed = idle_speed

    def update(self, features, fps, target_speed, direction):
        idle, loudness, treble = ORBIT_GENERATION_RATE
        self.phase += (idle + loudness*features.envelope + treble*features.treble)/fps
        while self.phase >= 1:
            self.cells = elementary_step(self.cells, self.rule)
            self.history = [self.cells.copy(), *self.history[:-1]]
            self.phase -= 1
        tau = ORBIT_ROTATION_ATTACK if target_speed > self.angular_speed else ORBIT_ROTATION_RELEASE
        self.angular_speed += (target_speed-self.angular_speed)*(1-math.exp(-1/(tau*fps)))
        self.angle = (self.angle + direction*self.angular_speed/fps) % math.tau


def initial_orbit_cells(seed):
    return np.random.default_rng(seed).integers(0, 2, ORBIT_CELLS, dtype=np.uint8)
