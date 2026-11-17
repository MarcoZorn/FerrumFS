"""Terminal scope: waveform sparkline, SNR, bitrate, packet map."""

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

BARS = " ▁▂▃▄▅▆▇█"


def sparkline(sig: list[float], width: int = 56) -> str:
    """Point-sampled (not averaged): averaging would smear Manchester to mush."""
    if not sig:
        return ""
    pts = sig[::max(1, len(sig) // width)][-width:]
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1.0
    return "".join(BARS[int((p - lo) / span * (len(BARS) - 1))] for p in pts)


def packet_map(asm) -> Text:
    total = asm.total or 0
    t = Text(overflow="fold")  # wrap long maps instead of eliding
    for i in range(total):
        t.append("■", style="green" if i in asm.chunks else "grey35")
    return t


def render(sig: list[float], snr: float, bps: float, asm=None, title: str = "FerrumFS") -> Panel:
    grid = Table.grid(padding=(0, 2))
    grid.add_row("|ΔB| along PCA axis", Text(sparkline(sig), style="cyan"))
    grid.add_row("SNR", f"{snr:5.1f} dB")
    grid.add_row("goodput", f"{bps:7.1f} bit/s")
    if asm is not None and asm.total:
        grid.add_row("packets", f"{len(asm.chunks)}/{asm.total}")
        grid.add_row("", packet_map(asm))
    return Panel(grid, title=title)
