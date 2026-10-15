"""Centered, two-sided Pythagoras tree with audio growth and fading tips."""
import math
import numpy as np
from .base import CanvasRenderer, BACKGROUND
from ..colors import interpolate_color, fading_complement
from ...config import (
    PYTHAGORAS_DEPTH, PYTHAGORAS_SILENCE_LEVEL, PYTHAGORAS_AUDIO_RESPONSE,
    PYTHAGORAS_IDLE_ROTATION, PYTHAGORAS_ROTATION_RESPONSE,
    PYTHAGORAS_ROTATION_ATTACK, PYTHAGORAS_ROTATION_RELEASE,
    PYTHAGORAS_ROOF_ANGLE, PYTHAGORAS_RADIUS, PYTHAGORAS_FILL,
    PYTHAGORAS_GHOST_SECONDS, PYTHAGORAS_GHOST_OPACITY,
)


def pythagoras_squares(angle, depth=PYTHAGORAS_DEPTH, *, both_sides=False):
    """Grow a fractional final generation from the parent corners."""
    pending = [(complex(-.5,0),complex(.5,0),0)]
    result = []
    while pending:
        a,b,level = pending.pop()
        edge = b-a
        d,c = a+1j*edge,b+1j*edge
        result.append((np.array([a,b,c,d]),level))
        if level<depth:
            roof = d+edge*math.cos(angle)**2+1j*edge*math.cos(angle)*math.sin(angle)
            growth = min(1,depth-level)
            pending.extend([(d,d+(roof-d)*growth,level+1),
                            (c+(roof-c)*growth,c,level+1)])
    if both_sides:
        result += [(p.conjugate()+1j,level) for p,level in result if level>0]
    return result


class PythagorasRenderer(CanvasRenderer):
    def __init__(self, config):
        super().__init__(config)
        self.audio = np.zeros(5)
        self.angle = 0.0
        self.speed = PYTHAGORAS_IDLE_ROTATION
        self.radius = min(self.width,self.height)*PYTHAGORAS_RADIUS
        self.ghosts = {}
        self.previous_depth = 1.0

    def advance(self, features):
        dt = 1/self.config.fps
        target = np.array([features.envelope,features.bass,features.mid,
                           features.treble,features.centroid])
        self.audio += (target-self.audio)*(1-math.exp(-dt/PYTHAGORAS_AUDIO_RESPONSE))
        e,b,_,t,_ = self.audio
        loudness,bass,treble = PYTHAGORAS_ROTATION_RESPONSE
        target_speed = PYTHAGORAS_IDLE_ROTATION+loudness*e+bass*b+treble*t
        tau = PYTHAGORAS_ROTATION_ATTACK if target_speed>self.speed else PYTHAGORAS_ROTATION_RELEASE
        self.speed += (target_speed-self.speed)*(1-math.exp(-dt/tau))
        self.angle = (self.angle-self.speed*dt) % math.tau
        return self.audio

    @property
    def depth(self):
        activity = float(np.clip((self.audio[0]-PYTHAGORAS_SILENCE_LEVEL)/
                                 (1-PYTHAGORAS_SILENCE_LEVEL),0,1))
        return 1+(PYTHAGORAS_DEPTH-1)*activity

    def xy(self, z):
        z = np.asarray(z)*np.exp(1j*self.angle)
        return np.column_stack((z.real,-z.imag))*self.radius+[self.width/2,self.height/2]

    def branch_colors(self, level, depth):
        # Only the growing/retracting frontier fades. The five seed squares stay.
        opacity = 1.0 if level<=1 else float(np.clip(depth-level+1,0,1))
        gradient = self.colors[level % len(self.colors)]
        color = interpolate_color(fading_complement(gradient,opacity),.5)
        outline = tuple(round(bg+opacity*(c-bg)) for c,bg in zip(color,BACKGROUND))
        fill = tuple(round(bg+opacity*(c*PYTHAGORAS_FILL-bg)) for c,bg in zip(color,BACKGROUND))
        return fill,outline

    def update_ghosts(self, groups, depth):
        """Keep one bounded outline snapshot per generation during contraction."""
        for level in range(2,PYTHAGORAS_DEPTH+1):
            coverage = float(np.clip(depth-level+1,0,1))
            previous = float(np.clip(self.previous_depth-level+1,0,1))
            if coverage>0 and coverage>=previous:
                self.ghosts[level] = (groups[level],coverage,0.0)
            elif level in self.ghosts:
                points,strength,age = self.ghosts[level]
                age += 1/self.config.fps
                if age>=PYTHAGORAS_GHOST_SECONDS:
                    del self.ghosts[level]
                else:
                    self.ghosts[level] = (points,strength,age)
        self.previous_depth = depth

    def draw_ghosts(self, draw):
        for level,(polygons,strength,age) in self.ghosts.items():
            if age==0:
                continue
            progress = age/PYTHAGORAS_GHOST_SECONDS
            fade = 1-progress*progress*(3-2*progress)
            opacity = PYTHAGORAS_GHOST_OPACITY*strength*fade
            gradient = fading_complement(self.colors[level % len(self.colors)],opacity)
            tint = interpolate_color(gradient,.5)
            color = tuple(round(bg+opacity*(c-bg)) for c,bg in zip(tint,BACKGROUND))
            for points in polygons:
                draw.polygon([tuple(p) for p in self.xy(points)],outline=color,
                             width=max(1,round(self.width/640)))

    def render(self, features):
        _,b,m,_,_ = self.advance(features)
        base,bass,mids = PYTHAGORAS_ROOF_ANGLE
        angle = math.pi/2-(base+bass*b+mids*m)
        depth = self.depth
        squares = pythagoras_squares(angle,depth,both_sides=True)
        full_tree = pythagoras_squares(angle,both_sides=True)
        all_points = np.concatenate([p for p,_ in full_tree])
        # Fixed pivot in the root square; full-tree bounds affect scale only.
        center = .5j
        extent = max(np.abs(all_points-center).max(),1)
        groups = {}
        for points,level in squares:
            if level>=2:
                groups.setdefault(level,[]).append((points-center)/extent)
        self.update_ghosts(groups,depth)
        image,draw = self.canvas()
        for points,level in squares:
            pixels = self.xy((points-center)/extent)
            fill,outline = self.branch_colors(level,depth)
            draw.polygon([tuple(p) for p in pixels],fill=fill,outline=outline,
                         width=max(1,round(self.width/640)))
        self.draw_ghosts(draw)
        return image
