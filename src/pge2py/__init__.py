"""pulseg and pge2 for pypulseq sequences, in the browser or on the desktop.

    import pge2py
    ge = pge2py.GE()
    ge.from_seq(seq)
    ge.check()
    ge.validate()
    ge.serialize("sequence.pge")
"""

__version__ = "0.1.0"

from ._ge import DEFAULT_SCANNER, GE  # noqa: E402
from ._report import PGE2Error, Segment, SegmentReport  # noqa: E402

__all__ = ["GE", "PGE2Error", "Segment", "SegmentReport", "DEFAULT_SCANNER", "__version__"]
