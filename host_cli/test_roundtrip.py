"""Run: python test_roundtrip.py (or pytest)."""

import os
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from ferrumfs.channel import Channel
from ferrumfs.cli import app
from ferrumfs.decoder import Assembler, demodulate, parse_frame
from ferrumfs.encoder import FRAME_LEN, encode_file


def receive(ch, frames, loops):
    asm = Assembler()
    for seq, chunk in demodulate(ch.transmit(frames, loops), ch.sps):
        asm.add(seq, chunk)
    return asm


def test_frame_fec():
    f = bytearray(encode_file("a", b"hello")[0])
    assert len(f) == FRAME_LEN
    f[6] ^= 0xFF
    f[20] ^= 0x01  # two byte errors: RS fixes both
    assert parse_frame(bytes(f[4:])) is not None
    f[10] ^= 0x10
    f[12] ^= 0x10
    f[14] ^= 0x10  # five: rejected, never silently wrong
    assert parse_frame(bytes(f[4:])) is None


def test_noisy_channel():
    data = os.urandom(300)
    frames = encode_file("blob.bin", data)
    asm = receive(Channel(seed=1), frames, loops=2)
    assert asm.result() == ("blob.bin", data), f"missing {asm.missing}"


def test_slow_magnetometer():
    # QMC5883L-ish: 200 Hz ODR, 25 bps, weaker coil, more noise
    data = b"magnets!" * 10
    frames = encode_file("m.txt", data)
    asm = receive(Channel(fs=200, bitrate=25, amp=4, noise=0.6, seed=2), frames, loops=3)
    assert asm.result() == ("m.txt", data), f"missing {asm.missing}"


def test_cli_replay():
    # simulate -> CSV capture -> streaming receive, same path as live hardware
    with tempfile.TemporaryDirectory() as d:
        src = Path(d, "note.txt")
        src.write_bytes(b"hello through the desk")
        r = CliRunner()
        assert r.invoke(app, ["simulate", str(src), "--dump", f"{d}/cap.csv", "--loops", "2"]).exit_code == 0
        res = r.invoke(app, ["receive", "--port", f"{d}/cap.csv", "--out", f"{d}/rx"])
        assert res.exit_code == 0, res.output
        assert Path(d, "rx", "note.txt").read_bytes() == src.read_bytes()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
