# Third-party components in the pge2py wheel

The pge2py code (`src/pge2py/*.py`, `src/pge2py/_js/*.js`, `tools/`) is MIT
licensed, see `../LICENSE`. The wheel also bundles, in `pge2py/_assets/`:

| Component | Files | Licence | Source |
|---|---|---|---|
| GNU Octave 10.3.0, compiled to WebAssembly by emscripten-forge | `octave-cli.js`, `octave-cli.wasm`, `share.pack` | GPL-3.0-or-later (`GPL-3.0-or-later.txt`) | https://ftp.gnu.org/gnu/octave/octave-10.3.0.tar.gz; build recipe: https://github.com/emscripten-forge/recipes (`recipes/recipes_emscripten/octave`); package: see `MANIFEST.json` (URL and sha256) |
| Pulseq MATLAB toolbox (`+mr`) | `toolboxes.pack` | MIT (`MIT-pulseq.txt`) | https://github.com/pulseq/pulseq, commit in `MANIFEST.json` |
| pulseg | `toolboxes.pack` | MIT (`MIT-pulseg.txt`) | https://github.com/HarmonizedMRI/pulseg, commit in `MANIFEST.json` |
| pge2 | `toolboxes.pack` | MIT (`MIT-pge2.txt`) | https://github.com/HarmonizedMRI/pge2, commit in `MANIFEST.json` |

The toolboxes are bundled with small changes so that they run in GNU Octave
(see `tools/build_assets.py`): a fix to Pulseq's `InputParserCompat`, the
`private/` functions of pulseg and pge2 copied onto the path, `import`
commented out in `vararg_pair.m`, and stand-ins for `DataHash`, `rmse`,
`MException` and `throw`.
