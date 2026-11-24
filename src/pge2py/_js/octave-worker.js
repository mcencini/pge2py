// One Octave run per worker. The bridge sends:
//   {loaderUrl, wasmModule, packs: [{index, data}], files: {path: Uint8Array},
//    script, collect: [dir]}
// The worker writes the packs and the files into its in-memory filesystem and
// runs `octave-cli --eval script`. The script ends by printing __PGE_DONE__;
// on that line the worker posts back {stdout, stderr, files} (every file under
// the `collect` dirs) and waits to be terminated. Returning to Octave would run
// its shutdown, which crashes in this build and, in Chromium, takes the tab down.

self.onmessage = (ev) => {
  const { loaderUrl, wasmModule, packs, files, script, collect } = ev.data;
  const stdout = [], stderr = [];
  let done = false;

  function finish(error) {
    if (done) return;
    done = true;
    const out = {};
    const walk = (dir) => {
      let names = [];
      try { names = self.FS.readdir(dir); } catch (e) { return; }
      for (const n of names) {
        if (n === '.' || n === '..') continue;
        const p = dir + '/' + n, st = self.FS.stat(p);
        if (self.FS.isDir(st.mode)) walk(p); else out[p] = self.FS.readFile(p);
      }
    };
    try { for (const d of collect) walk(d); } catch (e) {}
    self.postMessage({ stdout: stdout.join('\n'), stderr: stderr.join('\n'), files: out, error });
  }

  self.Module = {
    arguments: ['--no-gui', '--norc', '--no-history', '--eval', script],
    print: (s) => {
      if (s === '__PGE_DONE__') {
        finish(null);
        try { Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0); } catch (e) {}
        for (;;) {}  // until the bridge terminates this worker
      }
      stdout.push(s);
    },
    printErr: (s) => stderr.push(s),
    instantiateWasm: (imports, ok) => {
      WebAssembly.instantiate(wasmModule, imports).then((inst) => ok(inst, wasmModule));
      return {};
    },
    preRun: [() => {
      const FS = self.FS;
      const mk = (p) => { try { FS.mkdirTree(p); } catch (e) {} };
      for (const { index, data } of packs) {
        for (const [path, [off, len]] of Object.entries(index)) {
          mk(path.slice(0, path.lastIndexOf('/')));
          FS.writeFile(path, data.subarray(off, off + len));
        }
      }
      mk('/work');
      for (const [path, data] of Object.entries(files)) {
        mk(path.slice(0, path.lastIndexOf('/')));
        FS.writeFile(path, data);
      }
      mk('/home/user');
      self.ENV.OCTAVE_HOME = '/';
      self.ENV.HOME = '/home/user';
    }],
    onExit: () => finish(null),
    onAbort: () => finish('Octave aborted'),
  };
  self.onerror = (e) => { finish(String(e && e.message || e)); return true; };
  self.addEventListener('unhandledrejection', (e) => finish(String(e.reason)));
  // The wasm instantiates asynchronously: main runs after importScripts returns.
  try {
    importScripts(loaderUrl);
  } catch (e) {
    finish(String(e));
  }
};
