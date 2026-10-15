"""Original recursive tree fractal driven by audio features."""
import math
import numpy as np
from .base import CanvasRenderer, RotatingRenderer
from ..colors import interpolate_color
from ...config import (SNOWFLAKE_THRESHOLDS, SNOWFLAKE_HYSTERESIS,
                       SNOWFLAKE_LAYER_ROTATION, SNOWFLAKE_BASE_RADIUS,
                       SNOWFLAKE_RADIUS_RATIO, SNOWFLAKE_ROTATION_RATES,
                       SNOWFLAKE_ROTATION_SMOOTHING)


def snowflake_points(detail, depth=3):
    """Unfold complete Koch levels from a hexagon, without waveform ripples."""
    angles = np.arange(6) * math.tau / 6 - math.pi / 2
    points = np.column_stack((np.cos(angles), np.sin(angles)))
    for level in range(depth):
        amount = float(np.clip(detail * depth - level, 0, 1))
        if amount == 0:
            break
        amount = amount * amount * (3 - 2 * amount)
        delta = np.roll(points, -1, axis=0) - points
        outward = np.column_stack((delta[:, 1], -delta[:, 0]))
        points = np.stack((points, points + delta / 3,
                           points + delta / 2 + outward * (math.sqrt(3) / 6) * amount,
                           points + 2 * delta / 3), axis=1).reshape(-1, 2)
    return points


def layer_detail(level, index):
    """Fill one outline's detail range before starting the next outline."""
    boundaries = (0.0, *SNOWFLAKE_THRESHOLDS, 1.0)
    return float(np.clip((level - boundaries[index]) /
                        (boundaries[index + 1] - boundaries[index]), 0, 1))


class SnowflakeRenderer(CanvasRenderer):
    """Grow a snowflake; add a new outline when the current one is full."""
    def __init__(self, config):
        super().__init__(config)
        self.level = 0.0
        self.ring_count = 1
        self.layer_angles = np.arange(3, dtype=float) * SNOWFLAKE_LAYER_ROTATION
        self.layer_speeds = np.zeros(3)

    def update_layer_rotation(self, features):
        target = np.array([features.bass, features.mid, features.treble]) * SNOWFLAKE_ROTATION_RATES
        dt = 1 / self.config.fps
        tau = SNOWFLAKE_ROTATION_SMOOTHING
        decay = math.exp(-dt / tau)
        # Integrate the smoothed velocity exactly, independent of frame rate.
        travel = target * dt + (self.layer_speeds - target) * tau * (1 - decay)
        self.layer_angles = (self.layer_angles + travel) % math.tau
        self.layer_speeds = target + (self.layer_speeds - target) * decay
        self.layer_speeds[(target == 0) & (self.layer_speeds < 1e-4)] = 0

    def render(self, features):
        image, draw = self.canvas()
        phases = np.linspace(0, 2 * np.pi, len(features.waveform), endpoint=False)
        # Same tapered radial waveform magnitude used by the circles, quantified
        # into fractal detail, then into additional outlines as detail saturates.
        target = float(np.max(np.abs(features.waveform) * np.sin(phases / 2) ** 2))
        tau = .025 if target > self.level else .12
        self.level += (target - self.level) * (1 - math.exp(-1 / (self.config.fps * tau)))
        if target == 0 and self.level < .001:
            self.level = 0.0
        while self.ring_count <= len(SNOWFLAKE_THRESHOLDS) and self.level >= SNOWFLAKE_THRESHOLDS[self.ring_count - 1]:
            self.ring_count += 1
        while self.ring_count > 1 and self.level < SNOWFLAKE_THRESHOLDS[self.ring_count - 2] - SNOWFLAKE_HYSTERESIS:
            self.ring_count -= 1
        # Advance hidden outlines too, so threshold changes never reset angles.
        self.update_layer_rotation(features)
        for index in range(self.ring_count):
            layer_angle = self.layer_angles[index]
            rotation = np.array([[math.cos(layer_angle), -math.sin(layer_angle)],
                                 [math.sin(layer_angle), math.cos(layer_angle)]])
            points = snowflake_points(layer_detail(self.level, index)) @ rotation.T
            # Geometric spacing leaves room for each outline's outward branches.
            radius = min(self.width, self.height) * (SNOWFLAKE_BASE_RADIUS * SNOWFLAKE_RADIUS_RATIO ** index)
            ring = points * radius + [self.width / 2, self.height / 2]
            path = [tuple(p) for p in ring]
            color = interpolate_color(self.colors[index], .5)
            self.stroke(draw, path + [path[0]], color, width=max(1, self.height // 300))
        return image


class FractalRenderer(RotatingRenderer):
    def render(self, features):
        image, draw = self.canvas()
        length = min(self.width, self.height) * (.085 + .035 * features.envelope)
        spread = .30 + .65 * features.mid + .5 * features.centroid
        rotation = self.update_rotation(features)

        def branch(x, y, angle, distance, depth):
            if depth == 0:
                return
            end = (x + math.cos(angle) * distance, y + math.sin(angle) * distance)
            color = interpolate_color(self.colors[(7-depth) % 3], (7-depth)/6)
            draw.line([(x, y), end], fill=color, width=max(1, depth // 2))
            for direction in (-1, 1):
                branch(*end, angle + direction * spread, distance * .69, depth - 1)

        for i in range(6):
            branch(self.width / 2, self.height / 2, i * math.tau / 6 + rotation, length, 7)
        return image
