"""Shared visual palette and the renderer contract."""
from typing import Protocol
import math
from PIL import Image, ImageDraw
from ...config import RenderConfig
from ..analysis import AudioFeatures
from ..colors import get_palette, make_palette

BACKGROUND = (8, 12, 24)
CYAN = (83, 235, 222)
PURPLE = (161, 122, 255)


class Renderer(Protocol):
    def render(self, features: AudioFeatures) -> Image.Image: ...


class CanvasRenderer:
    def __init__(self, config: RenderConfig):
        self.config = config
        self.width, self.height = config.width, config.height
        self.colors = get_palette(config.palette)

    def set_palette(self, name):
        """Switch shared presets without resetting animation state."""
        self.colors = get_palette(name)

    def set_colors(self, first, second, third):
        """Apply three RGB gradient pairs using the global palette validator."""
        self.colors = make_palette(first, second, third)

    def canvas(self):
        image = Image.new("RGB", (self.width, self.height), BACKGROUND)
        return image, ImageDraw.Draw(image)

    def stroke(self, draw, points, color=CYAN, width=2):
        draw.line(points, fill=tuple(c // 5 for c in color), width=width + 6, joint="curve")
        draw.line(points, fill=color, width=width, joint="curve")


class RotatingRenderer(CanvasRenderer):
    """Shared audio-driven angular velocity; coast to a stop in silence."""
    def __init__(self, config):
        super().__init__(config)
        self.angle = 0.0
        self.angular_speed = 0.0

    def update_rotation(self, features):
        target_speed = .15 * features.envelope + .25 * features.mid + .65 * features.treble
        self.angular_speed += (target_speed - self.angular_speed) * (1 - math.exp(-1 / (.15 * self.config.fps)))
        if target_speed == 0 and self.angular_speed < 1e-4:
            self.angular_speed = 0.0
        self.angle = (self.angle + self.angular_speed / self.config.fps) % math.tau
        return self.angle
