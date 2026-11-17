"""Noisy magnetic channel simulator: lets the codec be tested with no hardware.

Models: random sensor orientation, earth field (~50 uT) with slow drift,
50 Hz mains hum, gaussian sensor noise, TX clock error and per-symbol jitter.
"""

import math
import random
from dataclasses import dataclass

from .encoder import manchester


@dataclass
class Channel:
    fs: float = 4000.0          # sensor sample rate, Hz
    bitrate: float = 500.0      # bits/s
    amp: float = 8.0            # coil field at the sensor, uT
    noise: float = 1.0          # gaussian noise per axis, uT
    hum: float = 1.5            # 50 Hz mains amplitude, uT
    drift: float = 2.0          # earth field random walk, uT/s
    clock_err: float = 0.02     # TX vs RX clock mismatch (fraction)
    jitter: float = 0.05        # per half-bit timing jitter (fraction)
    gap_bits: int = 8           # coil off between frames
    seed: int | None = None

    def __post_init__(self):
        self.rnd = random.Random(self.seed)  # one stream: each pass gets fresh noise

    @property
    def sps(self) -> float:
        return self.fs / self.bitrate

    def transmit(self, frames: list[bytes], loops: int = 1) -> list[tuple[float, float, float]]:
        rnd = self.rnd
        levels = [0] * 64  # idle lead-in
        for _ in range(loops):
            for f in frames:
                levels += [0] * (2 * self.gap_bits) + manchester(f)
        levels += [0] * 64

        # symbol boundaries in sample units, with clock error + jitter
        half = self.sps / 2 * (1 + self.clock_err)
        edges, t = [], 0.0
        for _ in levels:
            t += max(0.1, half * (1 + rnd.gauss(0, self.jitter)))
            edges.append(t)

        d = [rnd.gauss(0, 1) for _ in range(3)]
        n = math.sqrt(sum(x * x for x in d))
        coil = [x / n * self.amp for x in d]  # arbitrary orientation
        earth = [20.0, 5.0, -40.0]
        step = self.drift / math.sqrt(self.fs)
        hum_dir = [0.3, 0.9, 0.3]

        out, k = [], 0
        for i in range(int(edges[-1])):
            while edges[k] <= i:
                k += 1
            on = levels[k]
            h = self.hum * math.sin(2 * math.pi * 50 * i / self.fs)
            earth = [e + rnd.gauss(0, step) for e in earth]
            out.append(tuple(
                earth[a] + on * coil[a] + h * hum_dir[a] + rnd.gauss(0, self.noise) for a in range(3)
            ))
        return out
