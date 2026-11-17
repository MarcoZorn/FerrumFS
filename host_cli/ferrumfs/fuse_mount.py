"""Mount the coil as a folder: `cp foto.png /mnt/magflux/` transmits it,
files decoded by `ferrum receive` (written to rx_dir) show up read-only."""

import errno
import os
import stat
import time

from fuse import FUSE, FuseOSError, Operations


class MagFS(Operations):
    def __init__(self, send, rx_dir: str):
        self.send, self.rx_dir = send, rx_dir
        self.files: dict[str, bytearray] = {}
        self.dirty: set[str] = set()

    def _rx(self, name: str) -> str | None:
        p = os.path.join(self.rx_dir, name)
        return p if name and os.path.isfile(p) else None

    def getattr(self, path, fh=None):
        name, now = path.lstrip("/"), time.time()
        base = dict(st_atime=now, st_mtime=now, st_ctime=now, st_uid=os.getuid(), st_gid=os.getgid())
        if path == "/":
            return dict(base, st_mode=stat.S_IFDIR | 0o755, st_nlink=2)
        if name in self.files:
            return dict(base, st_mode=stat.S_IFREG | 0o644, st_nlink=1, st_size=len(self.files[name]))
        if p := self._rx(name):
            return dict(base, st_mode=stat.S_IFREG | 0o444, st_nlink=1, st_size=os.path.getsize(p))
        raise FuseOSError(errno.ENOENT)

    def readdir(self, path, fh):
        rx = os.listdir(self.rx_dir) if os.path.isdir(self.rx_dir) else []
        return [".", ".."] + sorted(set(self.files) | set(rx))

    def create(self, path, mode, fi=None):
        self.files[path.lstrip("/")] = bytearray()
        return 0

    def open(self, path, flags):
        return 0

    def truncate(self, path, length, fh=None):
        name = path.lstrip("/")
        self.files.setdefault(name, bytearray())[length:] = b""
        self.dirty.add(name)

    def write(self, path, data, offset, fh):
        buf = self.files[path.lstrip("/")]
        buf[offset:offset + len(data)] = data
        self.dirty.add(path.lstrip("/"))
        return len(data)

    def read(self, path, size, offset, fh):
        name = path.lstrip("/")
        if name in self.files:
            return bytes(self.files[name][offset:offset + size])
        with open(self._rx(name) or "/dev/null", "rb") as f:
            f.seek(offset)
            return f.read(size)

    def release(self, path, fh):
        name = path.lstrip("/")
        if name in self.dirty:
            self.dirty.discard(name)
            try:
                self.send(name, bytes(self.files[name]))
            except ValueError:  # blob > 4 KiB
                raise FuseOSError(errno.EFBIG)
        return 0


def mount(mountpoint: str, send, rx_dir: str):
    FUSE(MagFS(send, rx_dir), mountpoint, foreground=True, nothreads=True)
