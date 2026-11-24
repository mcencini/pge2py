"""pulseg.fromSeq, pge2.opts, pge2.check, pge2.validate, pge2.serialize, as in MATLAB.

Every call runs the official MATLAB function in GNU Octave. The MATLAB values
that pass from one call to the next (the PulSeg object ``psq``, the ``params``
returned by check) are Python objects that carry the Octave data with them.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ._octave import IN_BROWSER
from ._report import PGE2Error, Segment, SegmentReport, check_instance_lengths, trid_instances

_PRELUDE = """
addpath('{tb}/pge2'); addpath('{tb}/pulseg/third_party'); addpath('{tb}/pulseg');
addpath('{tb}/pulseq'); addpath('{tb}/overlay');
for f__ = {{'DataHash', 'rmse', 'MException', 'throw'}}
  if ~exist(f__{{1}}), addpath(['{tb}/shims/' f__{{1}}]); end
end
warning('off', 'Octave:possible-matlab-short-circuit-operator');
warning('off', 'Octave:language-extension');
"""

_SYS_GE = "sys_ge = pge2.opts({psd_rf_wait!r}, {psd_grd_wait!r}, {b1_max!r}, {g_max!r}, {slew_max!r}, '{coil}');\n"

_FROM_SEQ = """
psq = pulseg.fromSeq('{work}/sequence.seq');
save('-binary', '{work}/psq.mat', 'psq');
fprintf('PGE2PY_NMAX %d\\nPGE2PY_NBASE %d\\n', psq.nMax, psq.nParentBlocks);
for i__ = 1:psq.nSegments
  fprintf('PGE2PY_SEG %d %s\\n', psq.segments(i__).TRID, mat2str(psq.segments(i__).blockIDs(:)'));
end
"""

_CHECK = """
load('{work}/psq.mat');
params = pge2.check(psq, sys_ge, 'PNSwt', [{pns}]);
save('-binary', '{work}/params.mat', 'params');
fprintf('PGE2PY_PARAMS %.17g %.17g %.17g\\n', params.b1max, params.gmax, params.smax);
"""

_VALIDATE = """
load('{work}/psq.mat');
seq_ref = mr.Sequence(); seq_ref.read('{work}/reference.seq');
ok = pge2.validate(psq, sys_ge, seq_ref, [], 'row', {row}, 'plot', false);
fprintf('PGE2PY_OK %d\\n', ok);
"""

_SERIALIZE = """
load('{work}/psq.mat');
{load_params}
pge2.serialize(psq, '{work}/out.pge', 'pislquant', {pislquant}{params_arg}, 'checkHash', false);
fprintf('PGE2PY_SERIALIZED\\n');
"""

_PROGRESS = re.compile(r"\d+(\.\d+)?%\s*\[[ .*]*\]")

#: Messages (warnings, mismatches) printed by the last call.
last_messages: list[str] = []


# -- values passed between calls ----------------------------------------------
@dataclass
class PulSeg(SegmentReport):
    """What ``pulseg.fromSeq`` returns: the PulSeg object ``psq``.

    Shows as the list of virtual segments and their block layout; pass it to
    :func:`check`, :func:`validate` and :func:`serialize`.
    """

    _mat: bytes = field(default=b"", repr=False)
    _seq: bytes = field(default=b"", repr=False)

    @property
    def nSegments(self) -> int:  # noqa: N802 (MATLAB name)
        return len(self.segments)


@dataclass(frozen=True)
class SystemGE:
    """What ``pge2.opts`` returns: the scanner description ``sys_ge``."""

    psd_rf_wait: float = 100e-6
    psd_grd_wait: float = 100e-6
    b1_max: float = 0.25
    g_max: float = 5.0
    slew_max: float = 20.0
    coil: str = "xrm"


class Params(dict):
    """What ``pge2.check`` returns: ``params`` (peak B1 in G, peak gradient in
    G/cm, peak slew rate in G/cm/ms over the scan), to pass to :func:`serialize`."""

    _mat: bytes = b""


# -- running Octave ----------------------------------------------------------
_runner = None


def _get_runner():
    global _runner
    if _runner is None:
        if IN_BROWSER:
            from ._octave import BrowserOctave

            _runner = BrowserOctave()
        else:
            from ._octave import DesktopOctave

            _runner = DesktopOctave()
    return _runner


def _parse(stdout: str, stderr: str) -> list[str]:
    global last_messages
    text = _PROGRESS.sub("", stdout.replace("\b", ""))
    lines = [l.strip() for l in (text + "\n" + stderr).splitlines() if l.strip()]
    for l in lines:
        if l.startswith("__PGE_ERROR__"):
            raise PGE2Error(l[len("__PGE_ERROR__"):].strip())
    last_messages = [l for l in lines if not l.startswith("PGE2PY_")]
    return lines


def _call(script: str, files: dict):
    runner = _get_runner()
    if IN_BROWSER:
        from pyodide.ffi import can_run_sync, run_sync

        if not can_run_sync():
            raise RuntimeError(
                "this browser cannot wait for Octave synchronously; use the coroutines "
                "in pge2py.aio, e.g. `await aio.check(psq, sys_ge)`"
            )
        out, err, files_out = run_sync(runner.arun(script, files))
    else:
        out, err, files_out = runner.run(script, files)
    return _parse(out, err), files_out


async def _acall(script: str, files: dict):
    runner = _get_runner()
    if IN_BROWSER:
        out, err, files_out = await runner.arun(script, files)
    else:
        out, err, files_out = runner.run(script, files)
    return _parse(out, err), files_out


def _seq_bytes(seq) -> bytes:
    """A pypulseq Sequence, or the path of a .seq file, as .seq file content."""
    if isinstance(seq, (str, os.PathLike)):
        return Path(seq).read_bytes()
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "sequence.seq")
        seq.write(path)
        return Path(path).read_bytes()


def _as_seq_object(seq):
    if isinstance(seq, (str, os.PathLike)):
        import pypulseq as pp

        s = pp.Sequence()
        s.read(str(seq))
        return s
    return seq


# -- the calls, each in a "plan" (script, files, finish) used sync and async ---
def _from_seq_plan(seq):
    obj = _as_seq_object(seq)
    if not trid_instances(obj):
        raise PGE2Error("no TRID label in the sequence: pulseg needs one on the first block of every segment")
    check_instance_lengths(obj)
    data = _seq_bytes(seq)
    r = _get_runner()

    def finish(lines, files):
        trids = trid_instances(obj)
        segs, nmax, nbase = [], 0, 0
        for l in lines:
            if l.startswith("PGE2PY_SEG "):
                _, trid, ids = l.split(" ", 2)
                ids = [int(x) for x in ids.strip("[]").replace(";", " ").split()]
                segs.append(Segment(trid=int(trid), block_ids=ids, n_instances=trids.get(int(trid), 0)))
            elif l.startswith("PGE2PY_NMAX "):
                nmax = int(l.split()[1])
            elif l.startswith("PGE2PY_NBASE "):
                nbase = int(l.split()[1])
        warnings = [m for m in last_messages if m.lower().startswith("warning")]
        return PulSeg(segments=segs, n_base_blocks=nbase, n_blocks=nmax, warnings=warnings,
                      _mat=files["psq.mat"], _seq=data)

    return (_PRELUDE + _FROM_SEQ).format(work=r.work, tb=r.tb), {"sequence.seq": data}, finish


def _need_psq(psq):
    if not isinstance(psq, PulSeg):
        raise TypeError("psq must be the result of pulseg.fromSeq(seq)")


def _check_plan(psq, sys_ge, PNSwt):  # noqa: N803
    _need_psq(psq)
    r = _get_runner()
    script = (_PRELUDE + _SYS_GE.format(**sys_ge.__dict__) + _CHECK).format(
        work=r.work, tb=r.tb, pns=" ".join(repr(float(w)) for w in PNSwt))

    def finish(lines, files):
        vals = next(l for l in lines if l.startswith("PGE2PY_PARAMS ")).split()[1:]
        p = Params(zip(("b1max", "gmax", "smax"), map(float, vals)))
        p._mat = files["params.mat"]
        return p

    return script, {"psq.mat": psq._mat}, finish


def _validate_plan(psq, sys_ge, seq, row):
    _need_psq(psq)
    r = _get_runner()
    ref = psq._seq if seq is None else _seq_bytes(seq)
    script = (_PRELUDE + _SYS_GE.format(**sys_ge.__dict__) + _VALIDATE).format(
        work=r.work, tb=r.tb, row="[]" if row is None else int(row))

    def finish(lines, files):
        return next(l for l in lines if l.startswith("PGE2PY_OK ")).split()[1] == "1"

    return script, {"psq.mat": psq._mat, "reference.seq": ref}, finish


def _serialize_plan(psq, filename, pislquant, params):
    _need_psq(psq)
    r = _get_runner()
    files = {"psq.mat": psq._mat}
    if params is not None:
        files["params.mat"] = params._mat
    script = (_PRELUDE + _SERIALIZE).format(
        work=r.work, tb=r.tb, pislquant=int(pislquant),
        load_params=f"load('{r.work}/params.mat');" if params is not None else "",
        params_arg=", 'params', params" if params is not None else "")

    def finish(lines, files_out):
        path = Path(filename).resolve()
        path.write_bytes(files_out["out.pge"])
        return path

    return script, files, finish


# -- public API ----------------------------------------------------------------
def fromSeq(seq) -> PulSeg:  # noqa: N802 (MATLAB name)
    """``pulseg.fromSeq``: convert a sequence to the PulSeg representation.

    Parameters
    ----------
    seq : pypulseq.Sequence or path
        The sequence, or its ``.seq`` file.

    Returns
    -------
    PulSeg
        ``psq``: the virtual segments, their block layout and any warnings.

    Raises
    ------
    PGE2Error
        If the sequence has no TRID label, if the instances of a segment differ
        in number of blocks, or if ``pulseg.fromSeq`` stops.
    """
    script, files, finish = _from_seq_plan(seq)
    return finish(*_call(script, files))


def opts(psd_rf_wait=100e-6, psd_grd_wait=100e-6, b1_max=0.25, g_max=5.0, slew_max=20.0, coil="xrm") -> SystemGE:
    """``pge2.opts``: the scanner description, with the arguments of the MATLAB function.

    Parameters
    ----------
    psd_rf_wait, psd_grd_wait : float
        RF-gradient and ADC-gradient delays (s), scanner specific.
    b1_max : float
        Peak B1 (G).
    g_max : float
        Peak gradient (G/cm).
    slew_max : float
        Peak slew rate (G/cm/ms).
    coil : str
        Gradient coil, see ``pge2.opts``: 'xrm' (MR750), 'hrmw' (Premier), 'magnus', ...
    """
    return SystemGE(float(psd_rf_wait), float(psd_grd_wait), float(b1_max), float(g_max), float(slew_max), str(coil))


def check(psq: PulSeg, sys_ge: SystemGE, PNSwt=(1, 1, 1)) -> Params:  # noqa: N803 (MATLAB name)
    """``pge2.check``: timing, PNS, peak B1 and gradient limits.

    Returns
    -------
    Params
        ``params``: ``b1max`` (G), ``gmax`` (G/cm), ``smax`` (G/cm/ms).

    Raises
    ------
    PGE2Error
        If a block or segment instance breaks a hardware rule.
    """
    script, files, finish = _check_plan(psq, sys_ge, PNSwt)
    return finish(*_call(script, files))


def validate(psq: PulSeg, sys_ge: SystemGE, seq=None, row=None) -> bool:
    """``pge2.validate``: replay every segment instance and compare with the sequence.

    Parameters
    ----------
    seq : pypulseq.Sequence or path, optional
        Reference sequence; by default the one given to ``pulseg.fromSeq``.
    row : int, optional
        Check only segments starting at or after this block (MATLAB 'row').

    Returns
    -------
    bool
        True if every instance matches. Mismatches are in ``pge2py.last_messages``.
    """
    script, files, finish = _validate_plan(psq, sys_ge, seq, row)
    return finish(*_call(script, files))


def serialize(psq: PulSeg, filename, pislquant: int = 10, params: Params | None = None) -> Path:
    """``pge2.serialize``: write the ``.pge`` file for the scanner.

    Parameters
    ----------
    filename : path
        Output ``.pge`` file.
    pislquant : int
        Number of ADC events Auto Prescan uses to set the receive gain.
    params : Params, optional
        The result of :func:`check`.
    """
    script, files, finish = _serialize_plan(psq, filename, pislquant, params)
    return finish(*_call(script, files))
