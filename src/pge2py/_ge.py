"""The pulseg + pge2 check chain for a pypulseq sequence."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from ._octave import IN_BROWSER
from ._report import PGE2Error, Segment, SegmentReport, check_instance_lengths, trid_instances

#: Scanner description passed to ``pge2.opts``, from the HarmonizedMRI pge2
#: 2DGRE demo: psd_rf_wait and psd_grd_wait in s, b1_max in G, g_max in G/cm,
#: slew_max in G/cm/ms, and the gradient coil name.
DEFAULT_SCANNER = {
    "psd_rf_wait": 100e-6,
    "psd_grd_wait": 100e-6,
    "b1_max": 0.25,
    "g_max": 5.0,
    "slew_max": 20.0,
    "coil": "xrm",
}

_PRELUDE = """
addpath('{tb}/pge2'); addpath('{tb}/pulseg/third_party'); addpath('{tb}/pulseg');
addpath('{tb}/pulseq'); addpath('{tb}/overlay');
for f__ = {{'DataHash', 'rmse', 'MException', 'throw'}}
  if ~exist(f__{{1}}), addpath(['{tb}/shims/' f__{{1}}]); end
end
warning('off', 'Octave:possible-matlab-short-circuit-operator');
warning('off', 'Octave:language-extension');
"""

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
sys_ge = pge2.opts({psd_rf_wait!r}, {psd_grd_wait!r}, {b1_max!r}, {g_max!r}, {slew_max!r}, '{coil}');
params = pge2.check(psq, sys_ge, 'PNSwt', [{pns}]);
save('-binary', '{work}/params.mat', 'params', 'sys_ge');
fprintf('PGE2PY_PARAMS %.17g %.17g %.17g\\n', params.b1max, params.gmax, params.smax);
"""

_VALIDATE = """
load('{work}/psq.mat'); load('{work}/params.mat');
seq_ref = mr.Sequence(); seq_ref.read('{work}/sequence.seq');
ok = pge2.validate(psq, sys_ge, seq_ref, [], 'row', [], 'plot', false);
fprintf('PGE2PY_OK %d\\n', ok);
"""

_SERIALIZE = """
load('{work}/psq.mat'); load('{work}/params.mat');
pge2.serialize(psq, '{work}/out.pge', 'pislquant', {pislquant}, 'params', params, 'checkHash', false);
fprintf('PGE2PY_SERIALIZED\\n');
"""

_PROGRESS = re.compile(r"\d+(\.\d+)?%\s*\[[ .*]*\]")


class GE:
    """pulseg and pge2 (the official MATLAB toolboxes) for pypulseq sequences.

    In the browser (Pyodide, JupyterLite) they run in GNU Octave compiled to
    WebAssembly, bundled with this package. Elsewhere they run in the GNU
    Octave installed on the computer, through oct2py (``pip install
    pge2py[octave]``).

    The calls follow the pge2 workflow::

        ge = GE()
        ge.from_seq(seq)   # pulseg.fromSeq
        ge.check()         # pge2.opts + pge2.check
        ge.validate()      # pge2.validate against the .seq file
        ge.serialize("sequence.pge")

    Each call has an ``a``-prefixed coroutine (``await ge.acheck()``), for
    browsers where Python cannot wait for JavaScript synchronously.

    Parameters
    ----------
    scanner : dict, optional
        Overrides of :data:`DEFAULT_SCANNER` (the arguments of ``pge2.opts``).
    """

    def __init__(self, scanner: dict | None = None):
        self.scanner = {**DEFAULT_SCANNER, **(scanner or {})}
        self._runner = None
        self._seq = None
        self.last_messages: list[str] = []

    # -- runners -------------------------------------------------------------
    def _get_runner(self):
        if self._runner is None:
            if IN_BROWSER:
                from ._octave import BrowserOctave

                self._runner = BrowserOctave()
            else:
                from ._octave import DesktopOctave

                self._runner = DesktopOctave()
        return self._runner

    def _script(self, body: str, **kw) -> str:
        r = self._get_runner()
        return (_PRELUDE + body).format(work=r.work, tb=r.tb, **kw)

    def _parse(self, stdout: str, stderr: str) -> list[str]:
        text = _PROGRESS.sub("", stdout.replace("\b", ""))
        lines = [l.strip() for l in (text + "\n" + stderr).splitlines() if l.strip()]
        for l in lines:
            if l.startswith("__PGE_ERROR__"):
                raise PGE2Error(l[len("__PGE_ERROR__"):].strip())
        self.last_messages = [l for l in lines if not l.startswith("PGE2PY_")]
        return lines

    def _call(self, script: str, files: dict | None = None) -> list[str]:
        runner = self._get_runner()
        if IN_BROWSER:
            from pyodide.ffi import can_run_sync, run_sync

            if not can_run_sync():
                raise RuntimeError(
                    "this browser cannot wait for Octave synchronously; use the coroutines, "
                    "e.g. `await ge.acheck()` instead of `ge.check()`"
                )
            out, err, self._files = run_sync(runner.arun(script, files or {}))
        else:
            out, err, self._files = runner.run(script, files or {})
        return self._parse(out, err)

    async def _acall(self, script: str, files: dict | None = None) -> list[str]:
        runner = self._get_runner()
        if IN_BROWSER:
            out, err, self._files = await runner.arun(script, files or {})
        else:
            out, err, self._files = runner.run(script, files or {})
        return self._parse(out, err)

    # -- fromSeq --------------------------------------------------------------
    def _from_seq_args(self, seq):
        if not trid_instances(seq):
            raise PGE2Error("no TRID label in the sequence: pulseg needs one on the first block of every segment")
        check_instance_lengths(seq)
        self._seq = seq
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "sequence.seq")
            seq.write(path)
            data = Path(path).read_bytes()
        return self._script(_FROM_SEQ), {"sequence.seq": data}

    def _from_seq_result(self, lines) -> SegmentReport:
        trids = trid_instances(self._seq)
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
        warnings = [m for m in self.last_messages if m.lower().startswith("warning")]
        return SegmentReport(segments=segs, n_base_blocks=nbase, n_blocks=nmax, warnings=warnings)

    def from_seq(self, seq) -> SegmentReport:
        """Convert a sequence to the PulSeg representation (``pulseg.fromSeq``).

        Parameters
        ----------
        seq : pypulseq.Sequence

        Returns
        -------
        SegmentReport
            The virtual segments, their block layout and any warnings.

        Raises
        ------
        PGE2Error
            If the sequence has no TRID label, if the instances of a segment
            differ in number of blocks, or if ``pulseg.fromSeq`` stops.
        """
        script, files = self._from_seq_args(seq)
        return self._from_seq_result(self._call(script, files))

    async def afrom_seq(self, seq) -> SegmentReport:
        """Coroutine version of :meth:`from_seq`."""
        script, files = self._from_seq_args(seq)
        return self._from_seq_result(await self._acall(script, files))

    # -- check --------------------------------------------------------------
    def _check_args(self, pns_weights):
        self._need_seq()
        return self._script(_CHECK, pns=" ".join(repr(float(w)) for w in pns_weights), **self.scanner)

    @staticmethod
    def _check_result(lines) -> dict:
        vals = next(l for l in lines if l.startswith("PGE2PY_PARAMS ")).split()[1:]
        return dict(zip(("b1max", "gmax", "smax"), map(float, vals)))

    def check(self, pns_weights=(1, 1, 1)) -> dict:
        """Check the sequence against the scanner (``pge2.opts``, ``pge2.check``).

        Parameters
        ----------
        pns_weights : tuple of float
            Directional PNS weights, see ``pge2.pns``.

        Returns
        -------
        dict
            Peak B1 (G), peak gradient (G/cm) and peak slew rate (G/cm/ms)
            over the scan: keys ``b1max``, ``gmax``, ``smax``.

        Raises
        ------
        PGE2Error
            If a block or segment instance breaks a hardware rule.
        """
        return self._check_result(self._call(self._check_args(pns_weights)))

    async def acheck(self, pns_weights=(1, 1, 1)) -> dict:
        """Coroutine version of :meth:`check`."""
        return self._check_result(await self._acall(self._check_args(pns_weights)))

    # -- validate -----------------------------------------------------------
    @staticmethod
    def _validate_result(lines) -> bool:
        return next(l for l in lines if l.startswith("PGE2PY_OK ")).split()[1] == "1"

    def validate(self) -> bool:
        """Compare the PulSeg representation with the ``.seq`` file (``pge2.validate``).

        Run :meth:`check` first. Mismatches are listed in ``last_messages``.

        Returns
        -------
        bool
            True if every segment instance matches the ``.seq`` file.
        """
        self._need_seq()
        return self._validate_result(self._call(self._script(_VALIDATE)))

    async def avalidate(self) -> bool:
        """Coroutine version of :meth:`validate`."""
        self._need_seq()
        return self._validate_result(await self._acall(self._script(_VALIDATE)))

    # -- serialize ----------------------------------------------------------
    def _serialize_result(self, path) -> Path:
        path = Path(path).resolve()
        path.write_bytes(self._files["out.pge"])
        return path

    def serialize(self, path: str | os.PathLike, pislquant: int = 10) -> Path:
        """Write the ``.pge`` file for the scanner (``pge2.serialize``).

        Run :meth:`check` first.

        Parameters
        ----------
        path : path
            Output file.
        pislquant : int
            Number of ADC events Auto Prescan uses to set the receive gain.

        Returns
        -------
        Path
            The file written.
        """
        self._need_seq()
        self._call(self._script(_SERIALIZE, pislquant=int(pislquant)))
        return self._serialize_result(path)

    async def aserialize(self, path: str | os.PathLike, pislquant: int = 10) -> Path:
        """Coroutine version of :meth:`serialize`."""
        self._need_seq()
        await self._acall(self._script(_SERIALIZE, pislquant=int(pislquant)))
        return self._serialize_result(path)

    def _need_seq(self):
        if self._seq is None:
            raise PGE2Error("no sequence: call from_seq(seq) first")
