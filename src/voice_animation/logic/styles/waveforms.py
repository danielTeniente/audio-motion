"""Time-domain line and concentric circular waveform renderers."""
import numpy as np
from .base import CanvasRenderer, RotatingRenderer
from ..colors import interpolate_color


class LineRenderer(CanvasRenderer):
    def render(self, features):
        image, draw = self.canvas()
        x = np.linspace(self.width * .06, self.width * .94, len(features.waveform))
        y = self.height / 2 - features.waveform * self.height * .36
        self.stroke(draw, list(zip(x, y)), interpolate_color(self.colors[0], .5),
                    width=max(2, self.height // 240))
        return image


class CircleRenderer(RotatingRenderer):
    def render(self, features):
        image, draw = self.canvas()
        size = min(self.width, self.height)
        angles = np.linspace(0, 2 * np.pi, len(features.waveform), endpoint=False)
        # Taper the displacement at the seam before explicitly closing the ring.
        displacement = features.waveform * np.sin(angles / 2) ** 2
        angles = angles + self.update_rotation(features)
        for i, colors in enumerate(self.colors):
            color = interpolate_color(colors, .5)
            radius = size * (.19 + i * .075 + features.bass * .025)
            r = radius + displacement * size * (.05 + .015 * i)
            points = list(zip(self.width / 2 + np.cos(angles) * r,
                              self.height / 2 + np.sin(angles) * r))
            self.stroke(draw, points + [points[0]], color)
        return image
