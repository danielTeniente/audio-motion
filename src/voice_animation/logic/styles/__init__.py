"""Explicit renderer registry: add a focused module and register its class here."""
from .waveforms import LineRenderer, CircleRenderer
from .fractal import FractalRenderer, SnowflakeRenderer
from .automata_orbit import AutomataOrbitRenderer
from .dragon import DragonRenderer
from .brain_sphere import BrainSphereRenderer
from .pythagoras import PythagorasRenderer

from .apollonian import ApollonianRenderer

STYLES = {"line": LineRenderer, "circles": CircleRenderer,
          "fractal": FractalRenderer, "snowflake": SnowflakeRenderer,
          "automata orbit": AutomataOrbitRenderer, "dragon": DragonRenderer,
          "brain sphere": BrainSphereRenderer, "pythagoras": PythagorasRenderer,
          "apollonian": ApollonianRenderer}


def create_renderer(config):
    if config.style not in STYLES:
        raise ValueError(f"Unknown style {config.style!r}; choose from {', '.join(STYLES)}.")
    return STYLES[config.style](config)
