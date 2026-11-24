# pge2py

The official [pulseg](https://github.com/HarmonizedMRI/pulseg) and
[pge2](https://github.com/HarmonizedMRI/pge2) MATLAB toolboxes (Pulseq on GE),
called from Python on a [pypulseq](https://github.com/imr-framework/pypulseq)
sequence, with the same calls as in MATLAB:

```python
import pge2py as pge2
from pge2py import pulseg

psq = pulseg.fromSeq(seq)                                # a pypulseq Sequence, or a .seq file
sys_ge = pge2.opts(100e-6, 100e-6, 0.25, 5, 20, "xrm")   # psd_rf_wait, psd_grd_wait, b1_max, g_max, slew_max, coil
params = pge2.check(psq, sys_ge, PNSwt=(1, 1, 1))
pge2.validate(psq, sys_ge, seq)
pge2.serialize(psq, "sequence.pge", pislquant=10, params=params)
```

`psq` shows as the list of virtual segments and their block layout; `params`
is a dict (`b1max`, `gmax`, `smax`). Errors raise `pge2py.PGE2Error` with the
toolbox's message; warnings and validate mismatches are in
`pge2py.last_messages`.

The toolboxes run in GNU Octave:

- **In the browser** (Pyodide, JupyterLite): GNU Octave 10.3 compiled to
  WebAssembly is bundled in the wheel and runs in a Web Worker, on the user's
  own computer. Nothing to install: `%pip install pge2py` in a JupyterLite
  notebook.
- **On the desktop**: the GNU Octave installed on the computer, through
  oct2py: `pip install pge2py[octave]`.

The toolboxes are bundled at pinned commits (see `pge2py/_assets/MANIFEST.json`),
with the small changes they need to run in Octave.

## In the browser

The calls block until Octave is done where the browser lets Python wait for
JavaScript (WebAssembly JSPI, e.g. Chrome). Elsewhere, use the coroutines:

```python
from pge2py import aio

psq = await aio.fromSeq(seq)
params = await aio.check(psq, sys_ge)
await aio.validate(psq, sys_ge, seq)
await aio.serialize(psq, "sequence.pge", params=params)
```

Each call starts a fresh Octave (about 0.5 s); `fromSeq`, `check` and
`validate` take a few seconds each on a 790-block 2D GRE.

## Building from source

```bash
python tools/build_assets.py      # Octave wasm + toolboxes -> src/pge2py/_assets
python -m build --wheel
```

## Licences

pge2py is MIT licensed. The wheel bundles GNU Octave (GPL-3.0-or-later) and
the Pulseq, pulseg and pge2 toolboxes (MIT); see `LICENSES/`.

## Releases

Versions follow `pge2py.__version__`. A release is cut by adding its section
to `CHANGELOG.md`, setting `__version__`, and creating the tag `vX.Y.Z` on that
commit, by pushing it or by creating the release in the GitHub web interface:
`.github/workflows/release.yml` builds the wheel, publishes it to PyPI and
attaches the files to the GitHub release.
