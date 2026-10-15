"""Tangent-circle packing with clockwise audio-reactive disk motion."""
from collections import deque
import math
import numpy as np
from .base import CanvasRenderer
from ..colors import interpolate_color
from ...config import (
    APOLLONIAN_DEPTH, APOLLONIAN_LIMIT, APOLLONIAN_MIN_RADIUS,
    APOLLONIAN_AUDIO_RESPONSE, APOLLONIAN_IDLE_ROTATION,
    APOLLONIAN_ROTATION_RESPONSE, APOLLONIAN_ROTATION_ATTACK,
    APOLLONIAN_ROTATION_RELEASE, APOLLONIAN_PHASE_RATE,
    APOLLONIAN_RADIUS, APOLLONIAN_CENTER_Y, APOLLONIAN_DISK_SCALE,
    APOLLONIAN_MOBIUS, APOLLONIAN_REVEAL,
)


def apollonian_circles(depth=APOLLONIAN_DEPTH, limit=APOLLONIAN_LIMIT):
    initial = ((-1.,0j),(2.,-.5+0j),(2.,.5+0j),(3.,2j/3))
    circles = list(initial)
    seen = {(round(k,7),round(z.real,7),round(z.imag,7)) for k,z in circles}
    queue = deque([(initial,0,-1)])
    while queue and len(circles)<limit:
        quad,level,last = queue.popleft()
        if level>=depth:
            continue
        for i in range(4):
            if i==last:
                continue
            k,z = quad[i]
            others = [quad[j] for j in range(4) if j!=i]
            nk = 2*sum(v[0] for v in others)-k
            nz = (2*sum(q*w for q,w in others)-k*z)/nk
            key = (round(nk,7),round(nz.real,7),round(nz.imag,7))
            if nk<=0 or 1/nk<APOLLONIAN_MIN_RADIUS or key in seen:
                continue
            seen.add(key)
            circles.append((nk,nz))
            new = list(quad)
            new[i] = (nk,nz)
            queue.append((tuple(new),level+1,i))
            if len(circles)>=limit:
                break
    return circles


def disk_mobius_circle(center, radius, a):
    denominator = abs(1-a.conjugate()*center)**2-abs(a)**2*radius**2
    new_center = ((center-a)*(1-a*center.conjugate())+a*radius**2)/denominator
    new_radius = radius*(1-abs(a)**2)/denominator
    return new_center,new_radius


class ApollonianRenderer(CanvasRenderer):
    def __init__(self, config):
        super().__init__(config)
        self.circles = apollonian_circles()
        self.audio = np.zeros(5)
        self.angle = 0.0
        self.phase = 0.0
        self.speed = APOLLONIAN_IDLE_ROTATION
        self.radius = min(self.width, self.height)*APOLLONIAN_RADIUS

    def advance(self, features):
        dt = 1/self.config.fps
        target = np.array([features.envelope, features.bass, features.mid,
                           features.treble, features.centroid])
        self.audio += (target-self.audio)*(1-math.exp(-dt/APOLLONIAN_AUDIO_RESPONSE))
        e,b,_,t,_ = self.audio
        loudness,bass,treble = APOLLONIAN_ROTATION_RESPONSE
        target_speed = APOLLONIAN_IDLE_ROTATION+loudness*e+bass*b+treble*t
        tau = APOLLONIAN_ROTATION_ATTACK if target_speed>self.speed else APOLLONIAN_ROTATION_RELEASE
        self.speed += (target_speed-self.speed)*(1-math.exp(-dt/tau))
        # Screen coordinates invert y: negative angles rotate clockwise.
        self.angle = (self.angle-self.speed*dt) % math.tau
        idle,response = APOLLONIAN_PHASE_RATE
        self.phase = (self.phase-(idle+response*e)*dt) % math.tau
        return self.audio

    def xy(self, z):
        z = np.asarray(z)*np.exp(1j*self.angle)
        return np.column_stack((z.real,-z.imag))*self.radius+[self.width/2,self.height*APOLLONIAN_CENTER_Y]

    def render(self, features):
        e,b,m,_,_ = self.advance(features)
        base,response = APOLLONIAN_MOBIUS
        a = (base+response*b)*np.exp(1j*self.phase)
        image,draw = self.canvas()
        cutoff,reveal = APOLLONIAN_REVEAL
        for i,(k,z) in enumerate(self.circles):
            center,r = disk_mobius_circle(z,1/abs(k),a)
            if r < cutoff-reveal*e:
                continue
            x,y = self.xy([center*APOLLONIAN_DISK_SCALE])[0]
            radius = r*self.radius*APOLLONIAN_DISK_SCALE
            tint = interpolate_color(self.colors[i % len(self.colors)],.5)
            brightness = .70+.30*min(1,r*18)
            color = tuple(round(channel*brightness) for channel in tint)
            draw.ellipse((x-radius,y-radius,x+radius,y+radius),outline=color,
                         width=max(1,round(self.width/640*(1+m))))
        return image
