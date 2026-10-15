"""Paperfolding motifs appended to a continuously contracting spiral."""
import math
import numpy as np
from PIL import Image, ImageDraw
from ...config import (DRAGON_BRANCH_SEEDS,
                      DRAGON_FULL_SIZE_TILES, DRAGON_START_RADIUS, DRAGON_FULL_RADIUS,
                      DRAGON_BRANCH_FOLD_VARIATIONS,
                      DRAGON_ECHO_LIFETIME, DRAGON_ECHO_ATTACK, DRAGON_ECHO_GAP,
                      DRAGON_ECHO_RISE, DRAGON_ECHO_BASELINE_TIME,
                      DRAGON_ECHO_TILES, DRAGON_ECHO_DRIFT)
from ..colors import fading_complement, get_palette, make_palette, interpolate_color
from .base import CanvasRenderer
from ...config import (DRAGON_FOLD_ORDER, DRAGON_TILE_ANGLE,
                        DRAGON_CONTRACTION, DRAGON_SILENCE_LEVEL,
                        DRAGON_IDLE_ROTATION, DRAGON_ROTATION_LOUDNESS,
                        DRAGON_ROTATION_BASS, DRAGON_ROTATION_TREBLE,
                        DRAGON_ROTATION_ATTACK, DRAGON_ROTATION_RELEASE,
                        DRAGON_FOLD_VARIATION, DRAGON_MOTIF_SEED)


def dragon_curve(order):
    points = np.array([0j, 1+0j])
    for _ in range(order):
        points = np.concatenate((points, points[-1] + (points[-2::-1] - points[-1]) * 1j))
    xy = np.column_stack((points.real, points.imag))
    xy -= (xy.min(axis=0) + xy.max(axis=0)) / 2
    return xy / np.ptp(xy, axis=0).max()


class _DragonBranch(CanvasRenderer):
    def __init__(self, config, motif_seed=DRAGON_MOTIF_SEED,
                 fold_variation=DRAGON_FOLD_VARIATION):
        super().__init__(config)
        self.motif_seed = motif_seed
        self.fold_variation = fold_variation
        path = dragon_curve(DRAGON_FOLD_ORDER)
        folded = path[:,0] + 1j*path[:,1]
        folded -= folded[0]
        self.motif = folded / folded[-1]
        self.edges_per_tile = len(self.motif)-1
        self.progress = 0.0
        self.full_size_progress = None
        self.growth_speed = 0.0
        self.angle = 0.0
        self.rotation_speed = DRAGON_IDLE_ROTATION
        self.motifs = {}
        self.previous_centroid = 0.0
        self.visible_tiles = math.ceil(math.log(max(self.width,self.height)*2)/DRAGON_CONTRACTION)

    def remember_motifs(self, f):
        """Freeze each new section's folds from the audio at its birth."""
        last = math.floor(self.progress/self.edges_per_tile)
        first = max(0,last-self.visible_tiles-1)
        brightness = float(np.clip(f.centroid*6,0,1))
        change = float(np.clip((f.centroid-self.previous_centroid)*12,-1,1))
        peak = math.log2(1+max(0,f.dominant_hz)/80)
        for tile in range(first,last+1):
            if tile in self.motifs:
                continue
            rng = np.random.default_rng(self.motif_seed+tile)
            path = np.array([0j,1+0j])
            for level in range(DRAGON_FOLD_ORDER):
                variation = (rng.uniform(-1,1)*(.4+.6*brightness)
                             + .45*math.sin(peak+level*1.7) + .35*change)
                turn = math.pi/2 + self.fold_variation*np.clip(variation,-1,1)
                path = np.concatenate((path,path[-1]+(path[-2::-1]-path[-1])*np.exp(1j*turn)))
            path = path/path[-1]
            # Bound the folds around a connecting segment; endpoints stay 0/1.
            straight = np.linspace(0,1,len(path))
            deviation = path-straight
            scale = min(1,.75/max(float(np.abs(deviation).max()),1e-9))
            self.motifs[tile] = straight+deviation*scale
        self.motifs = {k:v for k,v in self.motifs.items() if k>=first}
        self.previous_centroid = f.centroid

    def advance(self, f):
        dt = 1/self.config.fps
        if f.envelope <= DRAGON_SILENCE_LEVEL:
            self.growth_speed = 0.0
        else:
            target = 80 + 380*f.envelope + 140*f.treble
            decay = math.exp(-dt/.10)
            self.progress += target*dt + (self.growth_speed-target)*.10*(1-decay)
            self.growth_speed = target + (self.growth_speed-target)*decay
        activity = 0.0 if f.envelope <= DRAGON_SILENCE_LEVEL else float(np.clip(f.envelope,0,1))
        target_rotation = DRAGON_IDLE_ROTATION + activity * (
            DRAGON_ROTATION_LOUDNESS
            + DRAGON_ROTATION_BASS*float(np.clip(f.bass,0,1))
            + DRAGON_ROTATION_TREBLE*float(np.clip(f.treble,0,1)))
        response = (DRAGON_ROTATION_ATTACK if target_rotation > self.rotation_speed
                    else DRAGON_ROTATION_RELEASE)
        decay = math.exp(-dt/response)
        turn = target_rotation*dt + (self.rotation_speed-target_rotation)*response*(1-decay)
        self.rotation_speed = target_rotation + (self.rotation_speed-target_rotation)*decay
        self.angle = (self.angle - turn) % math.tau
        self.remember_motifs(f)

    def positions(self, indices):
        """Earlier material contracts monotonically as new material is appended."""
        tiles = np.floor(indices/self.edges_per_tile)
        offsets = indices % self.edges_per_tile
        motif = np.empty(len(indices),dtype=complex)
        for tile in np.unique(tiles):
            mask = tiles==tile
            path = self.motifs.get(int(tile),self.motif)
            motif[mask] = (np.interp(offsets[mask],np.arange(len(path)),path.real)
                          + 1j*np.interp(offsets[mask],np.arange(len(path)),path.imag))
        along = tiles + motif.real
        radius = min(self.width,self.height)*.34 * np.exp(
            DRAGON_CONTRACTION*(along-self.progress/self.edges_per_tile)
            - DRAGON_TILE_ANGLE*motif.imag)
        if self.full_size_progress is not None:
            # Ease into the full envelope, retaining the original inward flow.
            fraction = min(1.0, self.progress/self.full_size_progress)
            fraction = fraction*fraction*(3-2*fraction)
            radius *= (DRAGON_START_RADIUS +
                       (DRAGON_FULL_RADIUS-DRAGON_START_RADIUS)*fraction) / .34
        theta = DRAGON_TILE_ANGLE*along + DRAGON_CONTRACTION*motif.imag + self.angle
        return np.column_stack((radius*np.cos(theta),radius*np.sin(theta)))

class DragonRenderer(_DragonBranch):
    """Three distinct folding histories sharing a growth and rotation clock."""

    def __init__(self, config):
        super().__init__(config)
        self.colors = get_palette(config.palette)
        self.partner, self.echo_source = [
            _DragonBranch(config, seed, variation)
            for seed, variation in zip(DRAGON_BRANCH_SEEDS, DRAGON_BRANCH_FOLD_VARIATIONS)
        ]
        for branch in (self, self.partner, self.echo_source):
            branch.progress = 0.0
            branch.full_size_progress = float(DRAGON_FULL_SIZE_TILES * self.edges_per_tile)
        self.first_frame = True
        self.baseline = 0.0
        self.echo_points = None
        self.echo_age = 0.0
        self.echo_angle = 0.0
        self.cooldown = 0.0
        self.echo_count = 0

    def set_palette(self, name):
        """Use shared presets without resetting any folding or echo state."""
        self.colors = get_palette(name)

    def set_colors(self, first, second, echo):
        """Apply three validated RGB gradient pairs, one per dragon arm."""
        self.colors = make_palette(first, second, echo)

    def draw_gradient(self, draw, points, colors):
        """Tint from older inner folds to newer outer folds."""
        for start in range(0, len(points)-1, 32):
            mix = start/max(1, len(points)-2)
            color = interpolate_color(colors, mix)
            self.stroke(draw, [tuple(p) for p in points[start:start+33]], color, 2)

    def advance(self, f):
        super().advance(f)
        for branch in (self.partner, self.echo_source):
            branch.progress = self.progress
            branch.angle = self.angle
            branch.remember_motifs(f)
        dt = 1 / self.config.fps
        self.cooldown = max(0.0, self.cooldown - dt)
        if self.echo_points is not None:
            self.echo_age += dt
            if self.echo_age >= DRAGON_ECHO_LIFETIME:
                self.echo_points = None
                self.cooldown = DRAGON_ECHO_GAP
        rise = f.envelope - self.baseline
        self.baseline += (f.envelope-self.baseline) * (1-math.exp(-dt/DRAGON_ECHO_BASELINE_TIME))
        if (self.echo_points is None and self.cooldown <= 0
                and f.envelope > DRAGON_SILENCE_LEVEL and rise > DRAGON_ECHO_RISE):
            first = max(0, self.progress-DRAGON_ECHO_TILES*self.edges_per_tile)
            indices = np.append(np.arange(first, self.progress), self.progress)
            points = self.echo_source.positions(indices)
            # A quarter-turn places the echo between the two permanent arms.
            self.echo_points = np.column_stack((-points[:, 1], points[:, 0]))
            self.echo_age = 0.0
            self.echo_angle = self.angle
            self.echo_count += 1

    def render(self, f):
        if self.first_frame:
            self.first_frame = False
        else:
            self.advance(f)
        image, draw = self.canvas()
        center = np.array([self.width/2, self.height/2])
        if self.echo_points is not None:
            life = self.echo_age / DRAGON_ECHO_LIFETIME
            release = (1-life)**1.2
            opacity = min(1, self.echo_age/DRAGON_ECHO_ATTACK) * release
            colors = fading_complement(self.colors[2], release)
            turn = self.angle-self.echo_angle
            rotation = np.array([[math.cos(turn), -math.sin(turn)],
                                 [math.sin(turn), math.cos(turn)]])
            points = self.echo_points @ rotation.T * (1+DRAGON_ECHO_DRIFT*life) + center
            layer, layer_draw = self.canvas()
            self.draw_gradient(layer_draw, points, colors)
            image = Image.blend(image, layer, opacity)
            draw = ImageDraw.Draw(image)
        first = max(0, int(self.progress)-self.visible_tiles*self.edges_per_tile)
        indices = np.append(np.arange(first, math.floor(self.progress)+1), self.progress)
        for branch, sign, colors in zip((self, self.partner), (1, -1), self.colors[:2]):
            points = branch.positions(indices)
            points = np.vstack(([0.0, 0.0], points))
            self.draw_gradient(draw, sign*points+center, colors)
        return image
