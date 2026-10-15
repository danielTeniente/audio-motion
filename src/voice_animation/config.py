"""Validated render settings, independent of the command-line interface."""
from dataclasses import dataclass
import math
import sys
from pathlib import Path


def application_root():
    """Writable portable folder, or the source checkout when running Python."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]

# Brian's Brain sphere: connected and rings modes.
BRAIN_SPHERE_CELLS = 2400
BRAIN_SPHERE_UPDATE_RATE = 12
BRAIN_SPHERE_TRAIL_SECONDS = 1.1
BRAIN_SPHERE_RING_TRAIL_SECONDS = .65
BRAIN_SPHERE_MODES = ("connected", "rings")
BRAIN_SPHERE_AUDIO_GAIN = 5
BRAIN_SPHERE_SOURCE_RATE = 8  # Ignitions per second at full band energy.
# Three-cell motifs verified to spread on this 2400-cell spherical graph.
# Indices address [center, eight nearest neighbors] at each fixed source.
BRAIN_SPHERE_SOURCE_MOTIFS = (
    (0, 1, 3), (0, 1, 3), (0, 1, 3), (0, 1, 3),
    (3, 4, 7), (0, 1, 5), (0, 2, 3), (0, 2, 3),
    (0, 1, 3), (0, 1, 3), (0, 1, 3), (0, 1, 3),
)

# A new snowflake outline starts only after the previous detail range fills.
SNOWFLAKE_THRESHOLDS = (.30, .65)
SNOWFLAKE_HYSTERESIS = .025
SNOWFLAKE_LAYER_ROTATION = math.radians(10)
SNOWFLAKE_BASE_RADIUS = .17
SNOWFLAKE_RADIUS_RATIO = 1.4
# Inner/middle/outer: bass, midrange, treble, in radians/second at full level.
SNOWFLAKE_ROTATION_RATES = (.9, 1.2, 1.6)
SNOWFLAKE_ROTATION_SMOOTHING = .15

# Automata orbit: inner / middle / outer, matching the selected gallery version.
ORBIT_RULES = (110, 30, 90)
ORBIT_CELLS = 192
ORBIT_WARMUP = 26
ORBIT_HISTORY = (13, 13, 9)
ORBIT_RADII = ((.10, .205), (.235, .34), (.37, .45))
ORBIT_IDLE_SPEEDS = (.12, .08, .12)
ORBIT_RESPONSE = (1.5, 2.4, .90)
ORBIT_DIRECTIONS = (1, -1, 1)
ORBIT_ROTATION_ATTACK = .12
ORBIT_ROTATION_RELEASE = .45
ORBIT_GENERATION_RATE = (2, 28, 15)  # Idle, envelope, treble.
ORBIT_FADE_THRESHOLD = .015
ORBIT_FADE_FULL_LEVEL = .20
ORBIT_FADE_ATTACK = .10
ORBIT_FADE_RELEASE = .25
ORBIT_FADE_CUTOFF = .005
ORBIT_BRIGHTNESS = (1.0, .90)

# Pythagoras: centered mirrored squares, clockwise rotation and tip fade.
PYTHAGORAS_DEPTH = 8
PYTHAGORAS_SILENCE_LEVEL = .015
PYTHAGORAS_AUDIO_RESPONSE = .12
PYTHAGORAS_IDLE_ROTATION = .12
PYTHAGORAS_ROTATION_RESPONSE = (.85, .5, .45)  # Loudness, bass, treble.
PYTHAGORAS_ROTATION_ATTACK = .12
PYTHAGORAS_ROTATION_RELEASE = .45
PYTHAGORAS_ROOF_ANGLE = (.60, .36, .20)  # Base, bass, mids.
PYTHAGORAS_RADIUS = .41*.91
PYTHAGORAS_FILL = .45
PYTHAGORAS_GHOST_SECONDS = 3.0
PYTHAGORAS_GHOST_OPACITY = .65

# Apollonian gasket: bounded packing and clockwise disk-preserving motion.
APOLLONIAN_DEPTH = 6
APOLLONIAN_LIMIT = 650
APOLLONIAN_MIN_RADIUS = .008
APOLLONIAN_AUDIO_RESPONSE = .12
APOLLONIAN_IDLE_ROTATION = .12
APOLLONIAN_ROTATION_RESPONSE = (.85, .5, .45)
APOLLONIAN_ROTATION_ATTACK = .12
APOLLONIAN_ROTATION_RELEASE = .45
APOLLONIAN_PHASE_RATE = (.25, 1.8)
APOLLONIAN_RADIUS = .41
APOLLONIAN_CENTER_Y = .53
APOLLONIAN_DISK_SCALE = .94
APOLLONIAN_MOBIUS = (.12, .38)
APOLLONIAN_REVEAL = (.016, .008)

# Shared color settings, usable by any renderer.
COMPLEMENT_FADE_RANGE = .65
PALETTES = {
    "aurora": (
        ((72, 237, 191), (123, 255, 220)),
        ((170, 136, 255), (208, 175, 255)),
        ((255, 180, 65), (255, 214, 117)),
    ),
    "ember": (
        ((255, 203, 95), (255, 230, 156)),
        ((255, 104, 109), (255, 153, 135)),
        ((80, 204, 255), (140, 231, 255)),
    ),
    "orchid": (
        ((118, 151, 255), (168, 191, 255)),
        ((246, 117, 208), (255, 173, 230)),
        ((187, 246, 83), (218, 255, 140)),
    ),
}

# Dragon: continuous folded spiral and temporary echo.
DRAGON_FOLD_ORDER = 6
DRAGON_TILE_ANGLE = 1.0471975511965976
DRAGON_CONTRACTION = .24
DRAGON_SILENCE_LEVEL = .015
DRAGON_IDLE_ROTATION = .12  # Radians/second, counterclockwise.
DRAGON_ROTATION_LOUDNESS = .70
DRAGON_ROTATION_BASS = .65
DRAGON_ROTATION_TREBLE = .30
DRAGON_ROTATION_ATTACK = .12
DRAGON_ROTATION_RELEASE = .40
DRAGON_FOLD_VARIATION = .48  # Maximum deviation from a right-angle fold.
DRAGON_MOTIF_SEED = 173
# Independent, reproducible folding histories for the second and temporary arms.
DRAGON_BRANCH_SEEDS = (9317, 27183)
DRAGON_BRANCH_FOLD_VARIATIONS = (.80, .65)
DRAGON_FULL_SIZE_TILES = 20  # Size limit only; folded history keeps advancing.
DRAGON_START_RADIUS = .20  # Two 144-pixel seed strokes at 720p, shrinking inward.
DRAGON_FULL_RADIUS = .34
DRAGON_ECHO_LIFETIME = 1.35
DRAGON_ECHO_ATTACK = .10
DRAGON_ECHO_GAP = .18
DRAGON_ECHO_RISE = .035
DRAGON_ECHO_BASELINE_TIME = .30
DRAGON_ECHO_TILES = 9
DRAGON_ECHO_DRIFT = .10


@dataclass(frozen=True)
class RenderConfig:
    style: str = "line"
    brain_mode: str = "connected"
    width: int = 1280
    height: int = 720
    fps: int = 30
    gain: float = 3.0
    duration: float | None = None
    quality: str = "fast"
    palette: str = "aurora"
    orbit_seed: int | None = None

    @property
    def encoder_preset(self):
        return "veryfast" if self.quality == "fast" else "medium"

    def __post_init__(self):
        if self.brain_mode not in BRAIN_SPHERE_MODES:
            raise ValueError("Brain mode must be connected or rings.")
        if self.palette not in PALETTES:
            raise ValueError(f"Palette must be one of: {', '.join(PALETTES)}.")
        if self.orbit_seed is not None and (type(self.orbit_seed) is not int or self.orbit_seed < 0):
            raise ValueError("Orbit seed must be a nonnegative integer or None.")
        if self.quality not in ("fast", "balanced"):
            raise ValueError("Quality must be fast or balanced.")
        if self.width < 64 or self.height < 64 or self.width % 2 or self.height % 2:
            raise ValueError("Width and height must be even numbers of at least 64.")
        if not 1 <= self.fps <= 120:
            raise ValueError("FPS must be between 1 and 120.")
        if not math.isfinite(self.gain) or self.gain <= 0:
            raise ValueError("Gain must be finite and positive.")
        if self.duration is not None and (not math.isfinite(self.duration) or self.duration <= 0):
            raise ValueError("Duration must be finite and positive.")

# Local server and decoder safety limits.
WEB_MAX_CONNECTIONS = 16
WEB_SOCKET_TIMEOUT = 15
WEB_UPLOAD_TIMEOUT = 120
MEDIA_DECODE_TIMEOUT = 120
# Direct media containers only: no playlists, manifests, or script formats.
MEDIA_INPUT_FORMATS = "mp3,wav,flac,ogg,mov,aac,aiff,matroska,webm,asf,ape,wv"
