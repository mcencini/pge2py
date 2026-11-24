"""pge2 (Pulseq on GE) for pypulseq sequences, with the calls of the MATLAB toolboxes.

    import pge2py as pge2
    from pge2py import pulseg

    psq = pulseg.fromSeq(seq)
    sys_ge = pge2.opts(100e-6, 100e-6, 0.25, 5, 20, "xrm")
    params = pge2.check(psq, sys_ge)
    pge2.validate(psq, sys_ge, seq)
    pge2.serialize(psq, "sequence.pge", pislquant=10, params=params)

The official pulseg and pge2 MATLAB toolboxes run in GNU Octave: compiled to
WebAssembly and bundled, in the browser (Pyodide, JupyterLite); the computer's
GNU Octave through oct2py, elsewhere.
"""

__version__ = "0.1.0"

from . import pulseg  # noqa: E402
from ._api import Params, PulSeg, SystemGE, check, opts, serialize, validate  # noqa: E402
from ._report import PGE2Error, Segment  # noqa: E402


def __getattr__(name):
    if name == "last_messages":  # messages printed by the last call
        from . import _api

        return _api.last_messages
    raise AttributeError(name)


__all__ = ["pulseg", "opts", "check", "validate", "serialize",
           "PulSeg", "SystemGE", "Params", "PGE2Error", "Segment", "__version__"]
