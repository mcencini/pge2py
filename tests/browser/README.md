# Browser test (JupyterLite, headless Chromium)

Runs `tests/browser/cells.json` in the JupyterLite console: install the pge2py
wheel with piplite, build `gre2d.py` (the reference 2D GRE of the Pulseq on GE
course), then fromSeq, check, validate and serialize with plain (synchronous)
calls.

```bash
python tools/build_assets.py && python -m build --wheel
pip install jupyterlite-core jupyterlite-pyodide-kernel jupyter-server
mkdir -p build/lite/files build/lite/pypi
cp dist/pge2py-*.whl build/lite/pypi/
pip download --no-deps pypulseq==1.5.0.post1 comm -d build/lite/pypi
cp tests/browser/gre2d.py build/lite/files/
(cd build/lite && jupyter lite build --output-dir dist)
(cd build/lite/dist && python -m http.server 8767) &
CELLS=tests/browser/cells.json node tests/browser/drive_lite.js http://localhost:8767
```

`comm` is needed by the Pyodide kernel and is not in the Pyodide distribution;
with it and pypulseq bundled, the site needs no PyPI at run time.

Last run (Chromium 147, Pyodide 314): fromSeq 5.7 s, check 5.7 s,
validate + serialize 7.4 s; results identical to desktop Octave.
