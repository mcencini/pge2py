"""What pulseg.fromSeq made of a sequence, and checks done before calling it."""

from __future__ import annotations

from dataclasses import dataclass, field


class PGE2Error(RuntimeError):
    """Raised when pulseg or pge2 rejects a sequence."""


@dataclass
class Segment:
    """One virtual segment found by ``pulseg.fromSeq``."""

    trid: int
    block_ids: list[int]
    n_instances: int

    @property
    def layout(self) -> str:
        """Blocks of the segment as letters: one letter per base block,
        ``d`` for a fixed pure delay and ``v`` for a variable pure delay."""
        out = []
        for b in self.block_ids:
            if b == 0:
                out.append("d")
            elif b == -1:
                out.append("v")
            else:
                out.append(_letter(b))
        return "".join(out)


@dataclass(repr=False)
class SegmentReport:
    """What ``pulseg.fromSeq`` made of a sequence."""

    segments: list[Segment]
    n_base_blocks: int
    n_blocks: int
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [
            f"{self.n_blocks} blocks -> {len(self.segments)} virtual segment(s), "
            f"{self.n_base_blocks} base block(s)",
            "",
            f"  {'TRID':>6}  {'instances':>9}  {'blocks':>6}  layout",
        ]
        for s in self.segments:
            layout = s.layout if len(s.layout) <= 60 else s.layout[:57] + "..."
            lines.append(f"  {s.trid:>6}  {s.n_instances:>9}  {len(s.block_ids):>6}  {layout}")
        if self.warnings:
            lines += ["", f"pulseg.fromSeq printed {len(self.warnings)} warning(s); the first one:"]
            lines.append("  " + self.warnings[0].replace("\n", "\n  "))
        return "\n".join(lines)

    def __repr__(self) -> str:
        return str(self)

    def _repr_pretty_(self, p, cycle):
        p.text(str(self))


def _letter(i: int) -> str:
    s = ""
    while i > 0:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def trid_instances(seq) -> dict[int, int]:
    """Number of segment instances per TRID, counted from the labels."""
    counts: dict[int, int] = {}
    for n in seq.block_events:
        for lab in (seq.get_block(n).label or {}).values():
            if lab.label == "TRID":
                counts[int(lab.value)] = counts.get(int(lab.value), 0) + 1
    return counts


def check_instance_lengths(seq) -> None:
    """Refuse segments whose instances have different numbers of blocks.

    pulseg takes a segment's length from its first instance and does not check
    the others; in Octave a longer instance stops it with an unrelated error.
    """
    first: dict[int, tuple[int, int]] = {}  # TRID -> (length, start block)
    trid, start, length = None, None, 0

    def close():
        if trid is None:
            return
        if trid not in first:
            first[trid] = (length, start)
        elif first[trid][0] != length:
            raise PGE2Error(
                f"segment instances of TRID {trid} have different numbers of blocks: "
                f"{first[trid][0]} in the first instance (block {first[trid][1]}), "
                f"{length} in the instance starting at block {start}. Every instance of a "
                "segment must have the same blocks; give the extra blocks their own TRID."
            )

    for n in seq.block_events:
        new = [int(lab.value) for lab in (seq.get_block(n).label or {}).values() if lab.label == "TRID"]
        if new:
            close()
            trid, start, length = new[0], n, 0
        length += 1
    close()
