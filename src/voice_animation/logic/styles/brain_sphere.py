"""Brian's Brain sphere: connected propagation or audio-driven rings."""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops
from ...config import (BRAIN_SPHERE_CELLS, BRAIN_SPHERE_UPDATE_RATE,
                       BRAIN_SPHERE_TRAIL_SECONDS, BRAIN_SPHERE_AUDIO_GAIN,
                       BRAIN_SPHERE_SOURCE_RATE, BRAIN_SPHERE_SOURCE_MOTIFS,
                       BRAIN_SPHERE_RING_TRAIL_SECONDS)
from ..brain_sphere import sphere_graph, sphere_step
from ..colors import interpolate_color
from .base import CanvasRenderer


class BrainSphereRenderer(CanvasRenderer):
    def __init__(self, config):
        super().__init__(config)
        self.points, self.neighbors = sphere_graph(BRAIN_SPHERE_CELLS)
        self.state = np.zeros(BRAIN_SPHERE_CELLS, dtype=np.uint8)
        self.trail = np.zeros(BRAIN_SPHERE_CELLS)
        self.levels = np.zeros(3)
        self.live = np.zeros(BRAIN_SPHERE_CELLS)
        self.origins = np.zeros(BRAIN_SPHERE_CELLS, dtype=int)
        self.links = np.zeros(self.neighbors.shape)
        self.phase = 0.
        self.angle = 0.
        self.credits = np.zeros(3)
        self.injected = np.zeros(3, dtype=int)
        self.born = np.zeros(BRAIN_SPHERE_CELLS, dtype=bool)
        self.mode = config.brain_mode
        self.bands = np.where(self.points[:, 1] < -.28, 0, np.where(self.points[:, 1] > .28, 2, 1))
        self.sources = []
        for latitude in (-.55, 0., .55):
            patches = []
            for longitude in (-.72, .72, 2.4, -2.4):
                r = math.sqrt(1-latitude*latitude)
                direction = np.array([r*math.sin(longitude), latitude, r*math.cos(longitude)])
                center = int(np.argmax(self.points @ direction))
                motif = BRAIN_SPHERE_SOURCE_MOTIFS[len(self.sources)*4 + len(patches)]
                patches.append(np.r_[center, self.neighbors[center]][list(motif)])
            self.sources.append(patches)

    def advance(self):
        previous = self.state
        self.state = sphere_step(previous, self.neighbors)
        births = (self.state == 1) & (previous == 0)
        self.born |= births
        for i in np.flatnonzero(births):
            parents = previous[self.neighbors[i]] == 1
            self.origins[i] = self.origins[self.neighbors[i, np.flatnonzero(parents)[0]]]
            # Only real parent-child propagation draws a connection.
            strength = self.levels[self.origins[i]]
            self.links[i, parents] = np.maximum(self.links[i, parents], strength)

    def render(self, f):
        dt = 1 / self.config.fps
        energy = np.array([f.bass, f.mid, f.treble])
        target = np.clip((energy - .008) * BRAIN_SPHERE_AUDIO_GAIN, 0, 1)
        tau = np.where(target > self.levels, .035, .12)
        self.levels += (target - self.levels) * (1 - np.exp(-dt / tau))
        lifetime = BRAIN_SPHERE_TRAIL_SECONDS if self.mode == "connected" else BRAIN_SPHERE_RING_TRAIL_SECONDS
        decay = math.exp(-dt / lifetime)
        self.links *= decay
        self.phase += BRAIN_SPHERE_UPDATE_RATE * dt
        while self.phase >= 1:
            if self.mode == "connected":
                self.advance()
            else:
                self.state = sphere_step(self.state, self.neighbors)
            self.phase -= 1
        if self.mode == "connected":
            self.ignite_connected(dt)
            self.live = (self.state == 1) * self.levels[self.origins]
        else:
            self.ignite_rings()
        self.trail *= decay
        self.trail = np.maximum(self.trail, self.live)
        return self.draw_sphere()

    def ignite_connected(self, dt):
        # Fixed small sources make repeated sound recognizable. Stronger sound
        # activates more source clusters; all subsequent spread uses the rule.
        self.credits += self.levels * BRAIN_SPHERE_SOURCE_RATE * dt
        for band, level in enumerate(self.levels):
            if level < .025:
                self.credits[band] = 0
                continue
            if self.credits[band] >= 1:
                self.credits[band] %= 1
                count = min(4, 1 + int(level * 4))
                for patch in self.sources[band][:count]:
                    resting = patch[self.state[patch] == 0]
                    self.state[resting] = 1
                    self.origins[resting] = band
                    self.injected[band] += len(resting)

    def ignite_rings(self):
        fronts = np.zeros(len(self.state))
        self.origins[:] = self.bands
        for band, latitude in enumerate((-.62, 0., .62)):
            level = self.levels[band]
            if level < .025:
                continue
            distance = abs(self.points[:, 1] - latitude)
            extent = .025 + .27 * level
            ridge = np.exp(-((distance - extent) / .045) ** 2)
            ridge[self.bands != band] = 0
            fronts = np.maximum(fronts, ridge * level)
            resting = (ridge > .45) & (self.state == 0)
            self.state[resting] = 1
            self.injected[band] += int(resting.sum())
        self.live = np.maximum(fronts, (self.state == 1) * self.levels[self.bands] * .7)

    def rotated_points(self):
        """Fixed orientation and tilt for a stationary sphere."""
        p = self.points.copy()
        c, s = math.cos(self.angle), math.sin(self.angle)
        p[:, 0] = self.points[:, 0] * c + self.points[:, 2] * s
        p[:, 2] = -self.points[:, 0] * s + self.points[:, 2] * c
        # Fixed tilt shows the upper and lower emitting regions together.
        y = p[:, 1].copy()
        p[:, 1] = .94 * y - .342 * p[:, 2]
        p[:, 2] = .342 * y + .94 * p[:, 2]
        return p

    def draw_sphere(self):
        image, draw = self.canvas()
        radius = min(self.width, self.height) * .38
        cx, cy = self.width / 2, self.height / 2
        for r in range(int(radius), 0, -2):
            depth = math.sqrt(max(0., 1 - (r / radius) ** 2))
            color = tuple(int(v) for v in np.array([10, 18, 33]) + depth * np.array([6, 12, 18]))
            draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=color)
        p = self.rotated_points()
        cells = Image.new("RGB", image.size)
        draw = ImageDraw.Draw(cells)
        glow = Image.new("RGB", image.size)
        gd = ImageDraw.Draw(glow)
        for i, slot in np.argwhere(self.links > .025):
            j = self.neighbors[i, slot]
            if p[i, 2] <= 0 or p[j, 2] <= 0:
                continue
            strength = self.links[i, slot] * (.35 + .65*min(p[i, 2], p[j, 2]))
            base = interpolate_color(self.colors[self.origins[i]], strength)
            color = tuple(int(v*strength*.65) for v in base)
            draw.line((cx+radius*p[i, 0], cy-radius*p[i, 1],
                       cx+radius*p[j, 0], cy-radius*p[j, 1]),
                      fill=color, width=max(1, round(radius/220)))
        for i in np.argsort(p[:, 2]):
            x, y, z = p[i]
            if z <= 0:
                continue
            px, py = cx + radius*x, cy - radius*y
            live = self.live[i]
            ghost = self.trail[i] * .42
            strength = max(live, ghost)
            if strength < .015:
                continue
            size = max(.6, radius * (.004 + .014*strength) * (.45 + .55*z))
            band = self.origins[i]
            base = np.array(interpolate_color(self.colors[band], strength))
            color = tuple(int(v) for v in base * strength * (.4 + .6*z))
            gd.ellipse((px-size*1.6, py-size*1.6, px+size*1.6, py+size*1.6), fill=color)
            draw.ellipse((px-size, py-size, px+size, py+size), fill=color)
        return ImageChops.add(ImageChops.add(image, cells), glow.filter(ImageFilter.GaussianBlur(max(1, radius*.009))).point(lambda value: int(value * .35)), scale=1.)
