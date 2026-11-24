"""Where Octave runs: in the browser (WebAssembly worker) or on the desktop (oct2py).

Both runners take an Octave script with ``{work}`` and ``{tb}`` placeholders
(working folder, toolbox folder) and a dict of input files by name, and return
(stdout, stderr, output files by name). Files written to ``{work}`` are kept
for the next script.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from importlib.resources import files as _resources
from pathlib import Path

from . import __version__

IN_BROWSER = sys.platform == "emscripten"

_ASSETS = _resources("pge2py") / "_assets"
_JS = _resources("pge2py") / "_js"


def _asset(name: str) -> bytes:
    p = _ASSETS / name
    if not p.is_file():
        raise RuntimeError(
            f"pge2py asset {name} is missing: this is a source checkout without built "
            "assets. Run `python tools/build_assets.py`, or install pge2py from PyPI."
        )
    return p.read_bytes()


class BrowserOctave:
    """Octave 10.3 compiled to WebAssembly, one Web Worker per script."""

    work, tb = "/work", "/tb"

    def __init__(self):
        self._bridge = None

    async def _load(self):
        import js
        from pyodide.code import run_js
        from pyodide.ffi import to_js

        if not hasattr(js, "Pge2pyBridge"):
            run_js((_JS / "bridge.js").read_text())
        packs = [
            {"index": _asset(f"{name}.json").decode(), "data": to_js(_asset(f"{name}.pack"))}
            for name in ("share", "toolboxes")
        ]
        spec = {
            "wasm": to_js(_asset("octave-cli.wasm")),
            "loader": _asset("octave-cli.js").decode(),
            "worker": (_JS / "octave-worker.js").read_text(),
            "packs": packs,
        }
        self._bridge = await js.Pge2pyBridge.load(to_js(spec, dict_converter=js.Object.fromEntries))

    async def arun(self, script: str, files: dict[str, bytes]):
        import js
        from pyodide.ffi import to_js

        if self._bridge is None:
            await self._load()
        js_files = to_js({f"{self.work}/{k}": to_js(v) for k, v in files.items()}, dict_converter=js.Object.fromEntries)
        r = await self._bridge.run(script, js_files)
        out_files = {}
        for entry in js.Object.entries(r.files):
            path, data = entry[0], entry[1]
            if path.startswith(self.work + "/"):
                out_files[path[len(self.work) + 1:]] = data.to_bytes()
        if r.error:
            # a failure outside Octave (worker crashed): show it as an Octave error
            return "__PGE_ERROR__ " + str(r.error) + "\n" + str(r.stdout), str(r.stderr), out_files
        return str(r.stdout), str(r.stderr), out_files


class DesktopOctave:
    """GNU Octave on this computer, through oct2py."""

    def __init__(self, cache: str | os.PathLike | None = None):
        if shutil.which("octave-cli") and "OCTAVE_EXECUTABLE" not in os.environ:
            os.environ["OCTAVE_EXECUTABLE"] = shutil.which("octave-cli")
        try:
            from oct2py import Oct2Py
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("pge2py needs oct2py and GNU Octave outside the browser: pip install pge2py[octave]") from e
        root = Path(cache or os.environ.get("PGE2PY_CACHE", Path.home() / ".cache" / "pge2py")) / __version__
        self.tb = str(_unpack_toolboxes(root / "tb"))
        self.work = tempfile.mkdtemp(prefix="pge2py-")
        self._oc = Oct2Py()

    def run(self, script: str, files: dict[str, bytes]):
        for name, data in files.items():
            Path(self.work, name).write_bytes(data)
        out: list[str] = []
        try:
            self._oc.eval(script, stream_handler=out.append)
        except Exception as e:  # Oct2PyError: report as the browser does
            msg = str(e).split("error: ", 1)[-1].split("error: called from")[0].strip()
            out.append("__PGE_ERROR__ " + msg)
        collected = {p.name: p.read_bytes() for p in Path(self.work).iterdir() if p.is_file()}
        return "\n".join(out), "", collected


def _unpack_toolboxes(dest: Path) -> Path:
    """Write the toolboxes bundled in the package to ``dest`` (once)."""
    marker = dest / ".complete"
    if marker.exists():
        return dest
    index = json.loads(_asset("toolboxes.json"))
    data = _asset("toolboxes.pack")
    for path, (off, length) in index.items():
        target = dest / path.removeprefix("/tb/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data[off:off + length])
    marker.write_text("")
    return dest
