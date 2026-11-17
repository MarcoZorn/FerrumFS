"""Regenerate docs/img/*.svg from the real code (simulator + decoder + CLI).

    cd host_cli && .venv/bin/python ../docs/make_figures.py
"""

import os
import tempfile
from pathlib import Path

from rich.console import Console
from typer.testing import CliRunner

from ferrumfs import cli
from ferrumfs.channel import Channel
from ferrumfs.decoder import Assembler, bits_dll, demodulate, project, snr_db
from ferrumfs.encoder import encode_file
from ferrumfs.visualizer import render

IMG = Path(__file__).parent / "img"
INK, MUTED, GRID = "#1f2328", "#6e7781", "#d8dee4"
AXES = ("#cf222e", "#1a7f37", "#0969da")  # Bx By Bz


def polyline(xs, ys, color, width=1.2):
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linejoin="round"/>'


def scale(vals, top, h):
    lo, hi = min(vals), max(vals)
    return [top + h - (v - lo) / ((hi - lo) or 1) * h for v in vals]


def signal_svg():
    """One frame: raw 3-axis field -> PCA projection -> recovered clock + bits."""
    ch = Channel(seed=7, amp=10)
    frames = encode_file("note.txt", b"hello through the desk")
    samples = ch.transmit(frames[:1])
    sig = project(samples, ch.sps)
    centers: list[float] = []
    bits = bits_dll(sig, ch.sps, centers)

    # crop: preamble starts after 32 idle + 8 gap bits; show from 4 bits before
    start = int(36 * ch.sps)
    end = start + int(44 * ch.sps)
    W, L, R, ph = 1100, 120, 20, 120
    xs = [L + (i - start) / (end - start) * (W - L - R) for i in range(start, end)]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} 470" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="12">',
           f'<rect width="{W}" height="470" fill="#ffffff"/>']

    def panel(top, label, sub):
        out.append(f'<text x="12" y="{top + 18}" fill="{INK}" font-weight="600">{label}</text>')
        out.append(f'<text x="12" y="{top + 34}" fill="{MUTED}">{sub}</text>')
        out.append(f'<line x1="{L}" y1="{top + ph}" x2="{W - R}" y2="{top + ph}" stroke="{GRID}"/>')

    panel(20, "raw B", "x y z, uT")
    for a in range(3):
        out.append(polyline(xs, scale([s[a] for s in samples[start:end]], 20 + 10 + a * 30, 40), AXES[a]))
    panel(170, "projected", "PCA axis")
    out.append(f'<line x1="{L}" y1="{170 + ph / 2}" x2="{W - R}" y2="{170 + ph / 2}" stroke="{GRID}" stroke-dasharray="4 4"/>')
    out.append(polyline(xs, scale(sig[start:end], 180, ph - 20), INK, 1.6))
    panel(320, "decoded", "DLL clock + bits")
    for t, b in zip(centers, bits.replace("x", "")):
        if start <= t < end:
            x = L + (t - start) / (end - start) * (W - L - R)
            out.append(f'<line x1="{x:.1f}" y1="330" x2="{x:.1f}" y2="400" stroke="{AXES[2]}" stroke-width="1"/>')
            out.append(f'<text x="{x:.1f}" y="425" fill="{INK}" text-anchor="middle">{b}</text>')
    out.append(f'<text x="{L}" y="455" fill="{MUTED}">SNR {snr_db(sig):.1f} dB  ·  {ch.bitrate:.0f} bit/s  ·  {ch.fs:.0f} Hz  ·  preamble AA then sync 2D D4</text>')
    out.append("</svg>")
    (IMG / "signal.svg").write_text("\n".join(out))


def terminal_svgs():
    con = Console(record=True, width=82, force_terminal=True)
    cli.con = con
    with tempfile.TemporaryDirectory() as d:
        f = Path(d, "note.txt")
        f.write_bytes(b"FerrumFS: hello through the desk.\n" * 30)
        CliRunner().invoke(cli.app, ["simulate", str(f), "--seed", "4"])
    (IMG / "simulate.svg").write_text(con.export_svg(title="ferrum simulate note.txt"))

    # receive, caught mid-flight: one noisy pass, some frames still missing
    con = Console(record=True, width=82, force_terminal=True)
    frames = encode_file("photo.jpg", os.urandom(900))
    for seed in range(100):  # first seed where the header made it but some frames didn't
        ch = Channel(seed=seed, noise=1.4)
        samples = ch.transmit(frames)
        asm = Assembler()
        for seq, chunk in demodulate(samples, ch.sps):
            asm.add(seq, chunk)
        if asm.total and len(asm.missing) >= 4:
            break
    sig = project(samples, ch.sps)[int(ch.sps * 40):int(ch.sps * 54)]
    goodput = sum(len(c) for c in asm.chunks.values()) * 8 / (len(samples) / ch.fs)
    con.print(render(sig, snr_db(sig), goodput, asm, "rx /dev/ttyUSB1"))
    (IMG / "receive.svg").write_text(con.export_svg(title="ferrum receive --port /dev/ttyUSB1"))


if __name__ == "__main__":
    IMG.mkdir(exist_ok=True)
    signal_svg()
    terminal_svgs()
    print("wrote", sorted(p.name for p in IMG.glob("*.svg")))
