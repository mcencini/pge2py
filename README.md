# pge2py

The official [pulseg](https://github.com/HarmonizedMRI/pulseg) and
[pge2](https://github.com/HarmonizedMRI/pge2) MATLAB toolboxes (Pulseq on GE),
called from Python on a [pypulseq](https://github.com/imr-framework/pypulseq)
sequence:

```python
import pge2py

ge = pge2py.GE()
print(ge.from_seq(seq))          # pulseg.fromSeq: segments and base blocks
print(ge.check())                # pge2.opts + pge2.check
print(ge.validate())             # pge2.validate against the .seq file
ge.serialize("sequence.pge")     # pge2.serialize
```

The toolboxes run in GNU Octave:

- **In the browser** (Pyodide, JupyterLite): GNU Octave 10.3 compiled to
  WebAssembly is bundled in the wheel and runs in a Web Worker. Nothing to
  install: `%pip install pge2py` in a JupyterLite notebook.
- **On the desktop**: the GNU Octave installed on the computer, through
  oct2py: `pip install pge2py[octave]`.

The toolboxes are bundled at pinned commits (see `pge2py/_assets/MANIFEST.json`),
with the small changes they need to run in Octave.

## Scanner settings

`GE(scanner={...})` overrides the arguments of `pge2.opts`; the defaults are
those of the HarmonizedMRI pge2 2DGRE demo:

```python
pge2py.DEFAULT_SCANNER
# {'psd_rf_wait': 0.0001, 'psd_grd_wait': 0.0001, 'b1_max': 0.25,
#  'g_max': 5.0, 'slew_max': 20.0, 'coil': 'xrm'}
```

## In the browser

Calls block until Octave is done where the browser lets Python wait for
JavaScript (WebAssembly JSPI, e.g. Chrome). Every call also has a coroutine:

```python
await ge.afrom_seq(seq)
await ge.acheck()
await ge.avalidate()
await ge.aserialize("sequence.pge")
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
