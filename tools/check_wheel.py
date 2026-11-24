"""Fail if a wheel lacks the bundled assets or the licence files."""
import sys
import zipfile

REQUIRED = [
    "pge2py/_assets/octave-cli.wasm", "pge2py/_assets/octave-cli.js",
    "pge2py/_assets/share.pack", "pge2py/_assets/share.json",
    "pge2py/_assets/toolboxes.pack", "pge2py/_assets/toolboxes.json",
    "pge2py/_assets/MANIFEST.json", "pge2py/_js/bridge.js", "pge2py/_js/octave-worker.js",
]
for whl in sys.argv[1:]:
    names = zipfile.ZipFile(whl).namelist()
    missing = [r for r in REQUIRED if r not in names]
    lic = [n for n in names if "licenses/" in n.lower()]
    print(f"{whl}: {len(names)} files, licence files {len(lic)}")
    if missing or len(lic) < 5:
        sys.exit(f"missing: {missing}, licence files: {lic}")
