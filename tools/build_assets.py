"""Build the files bundled in the pge2py wheel, into src/pge2py/_assets/.

- GNU Octave compiled to WebAssembly (emscripten-forge), pinned by URL and
  sha256: the octave-cli program and Octave's own script library.
- The Pulseq, pulseg and pge2 MATLAB toolboxes, pinned by commit, with the
  changes they need to run in GNU Octave.

Usage: python tools/build_assets.py [--cache DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "pge2py" / "_assets"

OCTAVE = {
    "version": "10.3.0",
    "url": "https://prefix.dev/emscripten-forge-4x/emscripten-wasm32/octave-10.3.0-pl5321h996e327_3.tar.bz2",
    "sha256": "51226adc11c3216878a3e3dd34cafaa5ae50844fe5707ad06ce30fd1739ee1bb",
    "license": "GPL-3.0-or-later",
    "source": "https://github.com/emscripten-forge/recipes (recipes/recipes_emscripten/octave), "
              "https://ftp.gnu.org/gnu/octave/octave-10.3.0.tar.gz",
}

TOOLBOXES = {
    "pulseq": ("https://github.com/pulseq/pulseq", "11e459d9b6b426aa6ea57a01153fb9afea332f6f"),
    "pulseg": ("https://github.com/HarmonizedMRI/pulseg", "ca2a278a4160f859f1009812dcda86b783a3f3a1"),
    "pge2": ("https://github.com/HarmonizedMRI/pge2", "9fa76e60e65a92325e51a0c98f0302e3a805d960"),
}

# Parts of Octave's script library that the toolboxes never use.
OCTAVE_SKIP = ("doc", "fonts", "imagelib")

# Stand-ins for MATLAB functions the toolboxes call; the Octave code adds each
# to the path only when Octave lacks it.
SHIMS = {
    "DataHash.m": """function h = DataHash(x, varargin)
% MD5 of the text serialisation of x (stand-in for the Java-based DataHash).
f = [tempname() '.txt'];
save('-text', f, 'x');
s = fileread(f); delete(f);
s = regexprep(s, '# Created by Octave[^\\n]*\\n', '');
h = hash('md5', s);
end
""",
    "rmse.m": """function e = rmse(a, b, varargin)
% Root-mean-square error (stand-in for the Statistics Toolbox function).
e = sqrt(mean(abs(a - b).^2, varargin{:}));
end
""",
    "MException.m": """function ME = MException(id, msg, varargin)
% Error description (stand-in where Octave has no MException constructor).
ME = struct('identifier', id, 'message', sprintf(msg, varargin{:}));
end
""",
    "throw.m": """function throw(ME)
% Raise the error described by ME (pairs with the MException stand-in).
error(ME.identifier, '%s', ME.message);
end
""",
}

# Pulseq's InputParserCompat fails in Octave when an optional argument is added
# after parameters (struct array vs struct of structs).
INPUTPARSER_OLD = "          this.Parameter(end+1)=this.Optional{i};"
INPUTPARSER_NEW = """          o=this.Optional{i};
          if isfield(this.Parameter,'name') || isempty(fieldnames(this.Parameter))
            this.Parameter(end+1)=o;
          else
            this.Parameter.(o.name)=struct('def',o.def,'val',o.val);
          end"""


def download_octave(cache: Path) -> Path:
    """Download and unpack the pinned Octave WebAssembly package."""
    dest = cache / f"octave-{OCTAVE['version']}"
    if (dest / ".complete").exists():
        return dest
    print("downloading", OCTAVE["url"])
    req = urllib.request.Request(OCTAVE["url"], headers={"User-Agent": "pge2py-build"})
    data = urllib.request.urlopen(req).read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != OCTAVE["sha256"]:
        raise SystemExit(f"sha256 mismatch for the Octave package: {digest}")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:bz2") as tar:
        members = [m for m in tar.getmembers()
                   if m.name.startswith(("bin/octave-cli", "share/octave/")) and not m.issym()]
        tar.extractall(dest, members=members, filter="data")
    (dest / ".complete").write_text("")
    return dest


def fetch_toolbox(url: str, commit: str, dest: Path) -> None:
    if (dest / ".git").exists():
        return
    dest.mkdir(parents=True, exist_ok=True)
    run = lambda *cmd: subprocess.run(cmd, cwd=dest, check=True, stdout=subprocess.DEVNULL)  # noqa: E731
    run("git", "init", "-q")
    run("git", "fetch", "-q", "--depth", "1", url, commit)
    run("git", "checkout", "-q", "FETCH_HEAD")


def prepare_toolboxes(cache: Path) -> dict[str, Path]:
    """Fetch the pinned toolboxes and lay them out as they are packed:
    {mount point under /tb: folder}."""
    for name, (url, commit) in TOOLBOXES.items():
        fetch_toolbox(url, commit, cache / name)

    compat = cache / "pulseq/matlab/+mr/+aux/@InputParserCompat/InputParserCompat.m"
    text = compat.read_bytes().decode()
    eol = "\r\n" if "\r\n" in text else "\n"
    if INPUTPARSER_OLD in text:
        compat.write_bytes(text.replace(INPUTPARSER_OLD, INPUTPARSER_NEW.replace("\n", eol)).encode())

    # Octave does not find functions in private/ folders of packages: put them
    # on the path. vararg_pair uses `import`, which Octave rejects.
    overlay = cache / "octave-overlay"
    shutil.rmtree(overlay, ignore_errors=True)
    overlay.mkdir()
    for private in (cache / "pulseg/matlab/+pulseg/private", cache / "pge2/matlab/+pge2/private"):
        for f in private.glob("*.m"):
            shutil.copy(f, overlay / f.name)
    vararg = (cache / "pulseg/matlab/third_party/vararg_pair.m").read_text()
    (overlay / "vararg_pair.m").write_text(re.sub(r"(?m)^import ", "% import ", vararg))

    shims = cache / "octave-shims"
    shutil.rmtree(shims, ignore_errors=True)
    for name, body in SHIMS.items():
        d = shims / Path(name).stem
        d.mkdir(parents=True)
        (d / name).write_text(body)

    return {
        "pulseq/+mr": cache / "pulseq/matlab/+mr",
        "pulseg": cache / "pulseg/matlab",
        "pge2": cache / "pge2/matlab",
        "overlay": overlay,
        "shims": shims,
    }


def pack(mounts: dict[str, Path], name: str, skip=()) -> None:
    """Concatenate folder trees into {name}.pack with an index {name}.json:
    {virtual path: [offset, length]}."""
    index, off = {}, 0
    with open(ASSETS / f"{name}.pack", "wb") as f:
        for virt, host in mounts.items():
            for p in sorted(host.rglob("*")):
                rel = p.relative_to(host)
                if p.is_dir() or ".git" in rel.parts or any(s in rel.parts for s in skip):
                    continue
                data = p.read_bytes()
                index[f"{virt}/{rel.as_posix()}"] = [off, len(data)]
                f.write(data)
                off += len(data)
    (ASSETS / f"{name}.json").write_text(json.dumps(index))
    print(f"{name}.pack: {len(index)} files, {off / 1e6:.1f} MB")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cache", type=Path, default=ROOT / "build" / "assets-cache")
    args = ap.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)

    octave = download_octave(args.cache)
    shutil.copy(octave / f"bin/octave-cli-{OCTAVE['version']}", ASSETS / "octave-cli.js")
    shutil.copy(octave / "bin/octave-cli.wasm", ASSETS / "octave-cli.wasm")
    pack({"/share/octave": octave / "share/octave"}, "share", skip=OCTAVE_SKIP)

    tb = prepare_toolboxes(args.cache / "toolboxes")
    pack({f"/tb/{k}": v for k, v in tb.items()}, "toolboxes")

    (ASSETS / "MANIFEST.json").write_text(json.dumps({
        "octave": OCTAVE,
        "toolboxes": {k: {"url": u, "commit": c} for k, (u, c) in TOOLBOXES.items()},
    }, indent=2))
    print("assets in", ASSETS)


if __name__ == "__main__":
    main()
