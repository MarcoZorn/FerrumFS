"""ferrum: simulate | send | receive | scope | mount"""

import os
import struct
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.live import Live

from .channel import Channel
from .decoder import Assembler, demodulate, project, snr_db
from .encoder import FRAME_LEN, encode_file
from .visualizer import render

app = typer.Typer(add_completion=False, help="Files stored in a magnetic field.")
con = Console()

FS = typer.Option(4000.0, help="RX sample rate, Hz (4000 Hall, 200 QMC5883L)")
BPS = typer.Option(500, help="bitrate, bit/s (500 Hall, 25 QMC5883L)")
PORT = typer.Option("/dev/ttyUSB0", help="serial port")


def _serial(port: str):
    import serial

    return serial.Serial(port, 921600, timeout=2)


def _samples(port: str):
    """Serial port, or a CSV recording (from `simulate --dump` or a capture) to replay."""
    return open(port, "rb") if os.path.isfile(port) else _serial(port)


def upload(port: str, name: str, data: bytes, bitrate: int):
    """Encode and hand the frames to the TX board, which then loops them."""
    frames = encode_file(name, data)
    with _serial(port) as s:
        time.sleep(1.5)  # board resets on open
        s.reset_input_buffer()
        cmds = [b"C", struct.pack(">cH", b"R", bitrate)] + [b"F" + f for f in frames] + [b"G"]
        for c in cmds:
            s.write(c)
            if s.read(1) != b"K":
                con.print(f"[red]TX did not ack {c[:1]!r}[/]")
                raise typer.Exit(1)
    return frames


@app.command()
def simulate(file: Path, fs: float = FS, bitrate: int = BPS, noise: float = 1.0, amp: float = 8.0,
             loops: int = 3, seed: int = 0, dump: Path = typer.Option(None, help="write samples as CSV")):
    """Push a file through the noisy channel model and decode it."""
    data = file.read_bytes()
    frames = encode_file(file.name, data)
    ch = Channel(fs=fs, bitrate=bitrate, noise=noise, amp=amp, seed=seed)
    asm, sent = Assembler(), 0
    t0 = time.time()
    csv = dump.open("w") if dump else None
    for _ in range(loops):
        samples = ch.transmit(frames)
        sent += len(samples)
        if csv:
            csv.writelines(f"{x:.3f},{y:.3f},{z:.3f}\n" for x, y, z in samples)
        for seq, chunk in demodulate(samples, ch.sps):
            asm.add(seq, chunk)
        if asm.result():
            break
    if csv:
        csv.close()
    air = sent / fs
    sig = project(samples, ch.sps)
    con.print(render(sig[: int(ch.sps * 120)], snr_db(sig), len(data) * 8 / air, asm, f"sim: {file.name}"))
    if r := asm.result():
        con.print(f"[green]ok[/] {r[0]} {len(r[1])} B, sha256 verified, {air:.1f}s on air, decode {time.time() - t0:.1f}s")
    else:
        con.print(f"[red]incomplete[/], missing frames {asm.missing}")
        raise typer.Exit(1)


@app.command()
def send(file: Path, port: str = PORT, bitrate: int = BPS):
    """Load a file into the TX loop buffer (max ~4 KiB)."""
    frames = upload(port, file.name, file.read_bytes(), bitrate)
    secs = len(frames) * (FRAME_LEN + 1) * 8 / bitrate
    con.print(f"{len(frames)} frames looping, one pass every {secs:.1f}s")


@app.command()
def receive(port: str = PORT, fs: float = FS, bitrate: int = BPS, out: Path = Path("received")):
    """Listen to the RX board (or replay a CSV) until a whole file is caught."""
    sps = fs / bitrate
    window = int((FRAME_LEN + 1) * 8 * sps * 3)  # three frames of samples
    buf: list[tuple[float, ...]] = []
    asm, t0, fresh = Assembler(), time.time(), 0
    with _samples(port) as s, Live(console=con, refresh_per_second=4) as live:
        while not (r := asm.result()):
            line = s.readline()
            eof = not line and not hasattr(s, "baudrate")  # end of a CSV replay
            try:
                buf.append(tuple(float(v) for v in line.split(b",")))
                fresh += 1
            except ValueError:
                if not eof:
                    continue
            if not eof and (fresh < window // 3 or len(buf) < window):
                continue
            buf, fresh = buf[-window:], 0
            for seq, chunk in demodulate(buf, sps):
                asm.add(seq, chunk)
            sig = project(buf, sps)
            got = sum(len(c) for c in asm.chunks.values()) * 8
            live.update(render(sig, snr_db(sig), got / (time.time() - t0), asm, f"rx {port}"))
            if eof:
                r = asm.result()
                break
    if not r:
        con.print(f"[red]recording ended[/], missing frames {asm.missing}")
        raise typer.Exit(1)
    out.mkdir(exist_ok=True)
    (out / os.path.basename(r[0])).write_bytes(r[1])
    con.print(f"[green]received[/] {r[0]} ({len(r[1])} B) -> {out}/")


@app.command()
def scope(port: str = PORT, fs: float = FS, bitrate: int = BPS):
    """Live view of the raw field, no decoding."""
    sps, buf = fs / bitrate, []
    with _samples(port) as s, Live(console=con, refresh_per_second=8) as live:
        while True:
            try:
                buf.append(tuple(float(v) for v in s.readline().split(b",")))
            except ValueError:
                continue
            if len(buf) % int(fs / 8) == 0 and len(buf) > sps * 8:
                buf = buf[-int(sps * 100):]
                sig = project(buf, sps)
                live.update(render(sig, snr_db(sig), 0, None, f"scope {port}"))


@app.command()
def mount(mountpoint: Path, port: str = PORT, bitrate: int = BPS, rx_dir: Path = Path("received")):
    """FUSE: files copied in are transmitted, received files are listed."""
    from .fuse_mount import mount as fuse_mount

    fuse_mount(str(mountpoint), lambda n, d: upload(port, n, d, bitrate), str(rx_dir))


if __name__ == "__main__":
    app()
