"""Per-frame features on a fixed audio clock; no media I/O or drawing."""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class AudioFeatures:
    time: float
    waveform: np.ndarray
    envelope: float
    bass: float
    mid: float
    treble: float
    centroid: float
    dominant_hz: float


class AudioAnalyzer:
    """Analyze centered 2048-sample windows at 22050 Hz by default.

    Levels are absolute, gain-scaled values in [0, 1]. Silence stays silent.
    Dominant frequency is a spectral peak, not a fundamental-pitch estimate.
    Call sequentially for attack/release smoothing.
    """

    def __init__(self, samples, sample_rate=22050, gain=3.0, window_size=2048):
        self.samples = samples
        self.sample_rate = sample_rate
        self.gain = gain
        self.window_size = window_size
        self.window = np.hanning(window_size)
        self.frequencies = np.fft.rfftfreq(window_size, 1 / sample_rate)
        self.level = 0.0

    def frame(self, index: int, fps: int) -> AudioFeatures:
        center = round(index * self.sample_rate / fps)
        start = center - self.window_size // 2
        end = start + self.window_size
        chunk = np.zeros(self.window_size, dtype=np.float32)
        lo, hi = max(start, 0), min(end, len(self.samples))
        if hi > lo:
            chunk[lo - start:hi - start] = self.samples[lo:hi]
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        target = min(1.0, rms * self.gain)
        tau = 0.035 if target > self.level else 0.16
        self.level += (target - self.level) * (1 - np.exp(-1 / (fps * tau)))
        power = np.abs(np.fft.rfft(chunk * self.window)) ** 2
        total = float(power.sum())
        if rms < 1e-6 or total < 1e-12:
            centroid = dominant = 0.0
            bands = [0.0, 0.0, 0.0]
        else:
            centroid = float(np.dot(self.frequencies, power) / total / (self.sample_rate / 2))
            dominant = float(self.frequencies[np.argmax(power)])
            bands = [float(np.sqrt(power[(self.frequencies >= a) & (self.frequencies < b)].sum() / total)) * target
                     for a, b in [(0, 250), (250, 2000), (2000, self.sample_rate / 2 + 1)]]
        positions = np.linspace(0, self.window_size - 1, 512)
        waveform = np.clip(np.interp(positions, np.arange(self.window_size), chunk) * self.gain, -1, 1)
        return AudioFeatures(index / fps, waveform, float(self.level), *bands, centroid, dominant)
