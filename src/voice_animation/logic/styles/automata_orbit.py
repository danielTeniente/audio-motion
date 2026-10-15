"""The selected three-band automata orbit renderer; RGB frames only."""
import math
from secrets import randbits
import numpy as np
from .base import CanvasRenderer, BACKGROUND
from ..analysis import AudioFeatures
from ..automata import OrbitBand, initial_orbit_cells
from ..colors import get_palette, make_palette, fading_complement
from ...config import (
    ORBIT_RULES, ORBIT_CELLS, ORBIT_HISTORY, ORBIT_RADII, ORBIT_IDLE_SPEEDS,
    ORBIT_RESPONSE, ORBIT_DIRECTIONS, ORBIT_BRIGHTNESS, ORBIT_FADE_THRESHOLD,
    ORBIT_FADE_FULL_LEVEL, ORBIT_FADE_ATTACK, ORBIT_FADE_RELEASE, ORBIT_FADE_CUTOFF,
)


class AutomataOrbitRenderer(CanvasRenderer):
    def __init__(self, config):
        super().__init__(config)
        self.seed = randbits(64) if config.orbit_seed is None else config.orbit_seed
        cells = initial_orbit_cells(self.seed)
        self.bands = []
        for rule, length, idle in zip(ORBIT_RULES, ORBIT_HISTORY, ORBIT_IDLE_SPEEDS):
            band = OrbitBand(cells, rule, length, idle)
            self.bands.append(band)
            cells = band.cells
        self.opacity = 0.0
        self.colors = get_palette(config.palette)

    def set_colors(self, inner, middle, outer):
        """Apply three RGB gradient pairs without resetting simulation or rotation."""
        self.colors = make_palette(inner, middle, outer)

    def set_palette(self, name):
        """Switch to a named preset without restarting the animation."""
        self.colors = get_palette(name)

    def render(self, features: AudioFeatures):
        energies = (features.bass, features.treble, features.mid)
        for index, band in enumerate(self.bands):
            target = ORBIT_IDLE_SPEEDS[index] + ORBIT_RESPONSE[index]*energies[index]
            band.update(features, self.config.fps, target, ORBIT_DIRECTIONS[index])
        target = float(np.clip((features.envelope-ORBIT_FADE_THRESHOLD) /
                              (ORBIT_FADE_FULL_LEVEL-ORBIT_FADE_THRESHOLD), 0, 1))
        tau = ORBIT_FADE_ATTACK if target > self.opacity else ORBIT_FADE_RELEASE
        self.opacity += (target-self.opacity)*(1-math.exp(-1/(tau*self.config.fps)))
        if target == 0 and self.opacity < ORBIT_FADE_CUTOFF:
            self.opacity = 0.0
        image, draw = self.canvas()
        for index, band in enumerate(self.bands):
            opacity = self.opacity if index == 2 else 1.0
            if opacity:
                colors = fading_complement(self.colors[index], opacity) if index == 2 else self.colors[index]
                self.draw_band(draw, band, ORBIT_RADII[index], colors, opacity)
        return image

    def draw_band(self, draw, band, radii, colors, opacity):
        size = min(self.width, self.height)
        theta = np.arange(ORBIT_CELLS+1)*math.tau/ORBIT_CELLS + band.angle
        for index, row in enumerate(band.history):
            mix = index/(len(band.history)-1)
            radius = size*(radii[0] + index*(radii[1]-radii[0])/(len(band.history)-1))
            points = np.column_stack((np.cos(theta), np.sin(theta)))*radius+[self.width/2, self.height/2]
            value = ORBIT_BRIGHTNESS[0]*(1-mix) + ORBIT_BRIGHTNESS[1]*mix
            color = tuple(int((a*(1-mix)+b*mix)*value) for a, b in zip(*colors))
            color = tuple(round(bg+opacity*(c-bg)) for c, bg in zip(color, BACKGROUND))
            for cell in np.flatnonzero(row):
                draw.line([tuple(points[cell]), tuple(points[cell+1])], fill=color,
                          width=max(1, int(size*.006)))
