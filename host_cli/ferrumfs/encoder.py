"""File -> frames -> Manchester half-bit levels.

Frame (28 B):
  PREAMBLE AA AA | SYNC 2D D4 | SEQ 1 | LEN 1 | PAYLOAD 16 | RS 4 | CRC16 2

RS(22,18) protects SEQ+LEN+PAYLOAD (fixes 2 bad bytes per frame).
CRC16 is computed over the same 18 bytes and checked *after* RS repair.

The file travels as one "blob" sliced into 16 B payloads:
  size u32 | name_len u8 | name | sha256 32 | data
SEQ is 1 byte, so a blob is capped at 256 * 16 = 4096 B.
"""

import hashlib
import struct

from reedsolo import RSCodec

PREAMBLE = b"\xaa\xaa"
SYNC = b"\x2d\xd4"
PAYLOAD = 16
ECC = 4
FRAME_LEN = len(PREAMBLE) + len(SYNC) + 2 + PAYLOAD + ECC + 2
MAX_FRAMES = 256
MAX_BLOB = MAX_FRAMES * PAYLOAD

rs = RSCodec(ECC)


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


def build_frame(seq: int, chunk: bytes) -> bytes:
    body = bytes([seq, len(chunk)]) + chunk.ljust(PAYLOAD, b"\0")
    return PREAMBLE + SYNC + bytes(rs.encode(body)) + struct.pack(">H", crc16(body))


def make_blob(name: str, data: bytes) -> bytes:
    n = name.encode()[:255]
    blob = struct.pack(">IB", len(data), len(n)) + n + hashlib.sha256(data).digest() + data
    if len(blob) > MAX_BLOB:
        raise ValueError(f"file too big: blob {len(blob)} B > {MAX_BLOB} B")
    return blob


def encode_file(name: str, data: bytes) -> list[bytes]:
    blob = make_blob(name, data)
    return [build_frame(i, blob[o:o + PAYLOAD]) for i, o in enumerate(range(0, len(blob), PAYLOAD))]


def manchester(frame: bytes) -> list[int]:
    """Bytes -> half-bit levels, MSB first. 0 = high->low, 1 = low->high."""
    out = []
    for byte in frame:
        for i in range(7, -1, -1):
            out += (0, 1) if (byte >> i) & 1 else (1, 0)
    return out
