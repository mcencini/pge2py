# Changelog

## 0.1.0

First release.

- The calls of the MATLAB toolboxes, on a pypulseq sequence:
  `pulseg.fromSeq`, `pge2.opts`, `pge2.check`, `pge2.validate`,
  `pge2.serialize` (`import pge2py as pge2; from pge2py import pulseg`), and
  coroutine versions in `pge2py.aio`.
- In the browser (Pyodide, JupyterLite): GNU Octave 10.3 compiled to
  WebAssembly (emscripten-forge) is bundled in the wheel and runs in a Web
  Worker. Calls are synchronous where the browser supports JSPI (tested in
  Chromium); Firefox and Safari not tested yet.
- On the desktop: GNU Octave through oct2py (`pip install pge2py[octave]`).
- Bundled toolboxes: Pulseq `11e459d`, pulseg `ca2a278`, pge2 `9fa76e6`, with
  the changes they need to run in Octave.
