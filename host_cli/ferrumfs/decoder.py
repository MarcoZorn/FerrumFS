"""Raw B-field samples -> frames -> file.

Pipeline: detrend (kills earth field + drift) -> PCA axis (orientation
invariant, works on 3-axis or 1-axis sensors) -> smooth -> per-bit
delay-locked clock recovery + matched filter -> sync search -> RS + CRC.
"""

import hashlib
import math
import struct
from bisect import bisect_left, bisect_right

from reedsolo import ReedSolomonError

from .encoder import ECC, PAYLOAD, SYNC, crc16, rs

BODY = 2 + PAYLOAD
MARKER = "".join(f"{b:08b}" for b in b"\xaa" + SYNC)  # last preamble byte + sync


def _moving_avg(xs: list[float], w: int) -> list[float]:
    if w <= 1:
        return list(xs)
    c = [0.0]
    for x in xs:
        c.append(c[-1] + x)
    n, h = len(xs), w // 2
    return [(c[min(n, i + h + 1)] - c[max(0, i - h)]) / (min(n, i + h + 1) - max(0, i - h)) for i in range(n)]


def project(samples: list[tuple[float, ...]], sps: float) -> list[float]:
    """Vectors -> 1-D signal along the axis of greatest variance."""
    dims = len(samples[0])
    w = max(3, int(sps * 4))  # ~4 bits: every Manchester bit is DC-free
    cols = [[s[d] for s in samples] for d in range(dims)]
    det = [[x - m for x, m in zip(col, _moving_avg(col, w))] for col in cols]
    cov = [[sum(a * b for a, b in zip(det[i], det[j])) for j in range(dims)] for i in range(dims)]
    v = [1.0] * dims
    for _ in range(50):  # power iteration, 3x3 converges fast
        v = [sum(cov[i][j] * v[j] for j in range(dims)) for i in range(dims)]
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        v = [x / n for x in v]
    proj = [sum(det[d][i] * v[d] for d in range(dims)) for i in range(len(samples))]
    return _moving_avg(proj, max(1, int(sps / 4)))


def bits_dll(sig: list[float], sps: float) -> str:
    """Delay-locked Manchester decoder.

    Every bit has a mid-bit edge: lock onto it, expect the next one T later
    (+-T/4 window, so clock error and jitter are re-synced each bit), and decide
    the bit with a matched filter (late half minus early half). Two missed
    edges in a row = lost lock (idle gap): emit 'x' and re-acquire.
    """
    T = sps
    edges = [i - sig[i] / (sig[i] - sig[i - 1]) for i in range(1, len(sig)) if (sig[i - 1] > 0) != (sig[i] > 0)]
    out, t, misses = [], edges[0] if edges else len(sig), 0
    h = max(1, int(T / 2))
    while t + T < len(sig):
        c = int(round(t))
        late = sum(sig[c:c + h])
        early = sum(sig[max(0, c - h):c])
        out.append("1" if late > early else "0")
        lo, hi = bisect_left(edges, t + 0.75 * T), bisect_right(edges, t + 1.25 * T)
        if lo < hi:
            t = min(edges[lo:hi], key=lambda e: abs(e - t - T))
            misses = 0
        else:
            t += T
            misses += 1
        if misses >= 2:
            out.append("x")
            k = bisect_right(edges, t)
            if k == len(edges):
                break
            t, misses = edges[k], 0
    return "".join(out)


def _bitstrings(sig: list[float], sps: float):
    bits = bits_dll(sig, sps)
    yield bits
    yield bits.translate(str.maketrans("01", "10"))  # PCA axis sign is arbitrary


def parse_frame(raw: bytes) -> tuple[int, bytes] | None:
    """28-byte frame minus preamble/sync (24 B) -> (seq, chunk) or None."""
    try:
        body = bytes(rs.decode(raw[:BODY + ECC])[0])
    except ReedSolomonError:
        return None
    if crc16(body) != struct.unpack(">H", raw[BODY + ECC:BODY + ECC + 2])[0]:
        return None
    seq, ln = body[0], body[1]
    return (seq, body[2:2 + ln]) if ln <= PAYLOAD else None


def demodulate(samples: list[tuple[float, ...]], sps: float) -> list[tuple[int, bytes]]:
    frames = []
    nbits = (BODY + ECC + 2) * 8
    for bits in _bitstrings(project(samples, sps), sps):
        i = bits.find(MARKER)
        while i != -1:
            chunk = bits[i + len(MARKER):i + len(MARKER) + nbits]
            if len(chunk) == nbits:
                if "x" not in chunk and (f := parse_frame(int(chunk, 2).to_bytes(nbits // 8, "big"))):
                    frames.append(f)
            i = bits.find(MARKER, i + 1)
    return frames


def snr_db(signal: list[float]) -> float:
    hi = [x for x in signal if x > 0]
    lo = [x for x in signal if x <= 0]
    if len(hi) < 2 or len(lo) < 2:
        return 0.0
    var = lambda xs, m: sum((x - m) ** 2 for x in xs) / len(xs)
    mh, ml = sum(hi) / len(hi), sum(lo) / len(lo)
    return 10 * math.log10((mh - ml) ** 2 / (var(hi, mh) + var(lo, ml) + 1e-12))


class Assembler:
    """Collects frames from the loop buffer until the blob is whole."""

    def __init__(self):
        self.chunks: dict[int, bytes] = {}
        self.total: int | None = None

    def add(self, seq: int, chunk: bytes):
        self.chunks.setdefault(seq, chunk)
        if self.total is None and 0 in self.chunks and len(self.chunks[0]) >= 5:
            size, nlen = struct.unpack(">IB", self.chunks[0][:5])
            self.total = math.ceil((5 + nlen + 32 + size) / PAYLOAD)

    @property
    def missing(self) -> list[int]:
        return [i for i in range(self.total or 1) if i not in self.chunks]

    def result(self) -> tuple[str, bytes] | None:
        """(name, data) once complete and SHA-256 verified, else None."""
        if self.total is None or self.missing:
            return None
        blob = b"".join(self.chunks[i] for i in range(self.total))
        size, nlen = struct.unpack(">IB", blob[:5])
        name = blob[5:5 + nlen].decode(errors="replace")
        digest, data = blob[5 + nlen:37 + nlen], blob[37 + nlen:37 + nlen + size]
        if hashlib.sha256(data).digest() != digest:
            self.chunks.clear()  # a bad frame slipped past CRC: start over
            self.total = None
            return None
        return name, data
