"""Shared RGB gradients, palettes, and complementary transitions for any style."""
import colorsys
from ..config import COMPLEMENT_FADE_RANGE, PALETTES


def make_palette(*gradients):
    """Return an immutable palette with any positive number of RGB gradient pairs.

    Each pair specifies the start and end tint of one element. Pass identical
    colors within a pair for a solid hue. Input lists are copied and validated.
    """
    if not gradients:
        raise ValueError("A palette needs at least one gradient.")
    result = []
    for gradient in gradients:
        if not isinstance(gradient, (tuple, list)) or len(gradient) != 2:
            raise ValueError("Each gradient needs a pair of RGB colors.")
        pair = []
        for color in gradient:
            if (not isinstance(color, (tuple, list)) or len(color) != 3
                    or any(type(c) is not int or not 0 <= c <= 255 for c in color)):
                raise ValueError("RGB colors need three integer channels from 0 to 255.")
            pair.append(tuple(color))
        result.append(tuple(pair))
    return tuple(result)


def get_palette(name):
    """Return a validated preset without exposing mutable renderer state."""
    if name not in PALETTES:
        raise ValueError(f"Unknown palette: {name}")
    return make_palette(*PALETTES[name])


def interpolate_color(colors, fraction):
    """Blend an RGB gradient, clamping its position to the endpoints."""
    fraction = min(1.0, max(0.0, fraction))
    return tuple(round(a*(1-fraction)+b*fraction) for a,b in zip(*colors))


def fading_complement(colors, opacity):
    """Shift any sequence of RGB colors halfway around the hue wheel on fading."""
    progress = min(1.0, max(0.0, (1.0-opacity)/COMPLEMENT_FADE_RANGE))
    progress = progress*progress*(3-2*progress)
    result = []
    for color in colors:
        hue, saturation, value = colorsys.rgb_to_hsv(*(channel/255 for channel in color))
        rgb = colorsys.hsv_to_rgb((hue + .5*progress) % 1, saturation, value)
        result.append(tuple(round(channel*255) for channel in rgb))
    return tuple(result)
