// pge2py Octave bridge, defined as self.Pge2pyBridge.
//
//   const b = await Pge2pyBridge.load({wasm, loader, worker, packs});
//   const r = await b.run(script, {'/work/x.seq': bytes});
//
// wasm: Uint8Array (octave-cli.wasm); loader, worker: JavaScript source text;
// packs: [{index: JSON text, data: Uint8Array}]. Everything comes from the
// Python package, so the page serves nothing. Every run starts a fresh worker;
// files under /work are kept and passed to the next run.
(function (global) {
  const blobUrl = (text) => URL.createObjectURL(new Blob([text], { type: 'text/javascript' }));

  class Pge2pyBridge {
    static async load({ wasm, loader, worker, packs }) {
      const b = new Pge2pyBridge();
      b.wasmModule = await WebAssembly.compile(wasm);
      b.loaderUrl = blobUrl(loader);
      b.workerUrl = blobUrl(worker);
      b.packs = packs.map(({ index, data }) => ({ index: JSON.parse(index), data }));
      b.work = {};
      return b;
    }

    run(script, files = {}) {
      const t0 = performance.now();
      const all = Object.assign({}, this.work, files);
      const wrapped =
        'try\n' + script + '\ncatch err__\n  disp([\'__PGE_ERROR__ \' err__.message]);\nend\n' +
        "fflush(stdout); disp('__PGE_DONE__');\n";
      return new Promise((resolve) => {
        const w = new Worker(this.workerUrl);
        w.onmessage = (ev) => {
          w.terminate();
          const r = ev.data;
          for (const [p, d] of Object.entries(r.files)) if (p.startsWith('/work/')) this.work[p] = d;
          r.seconds = (performance.now() - t0) / 1000;
          resolve(r);
        };
        w.onerror = (e) => {
          w.terminate();
          resolve({ stdout: '', stderr: String(e.message || e), files: {}, error: 'worker error', seconds: 0 });
        };
        w.postMessage({
          loaderUrl: this.loaderUrl, wasmModule: this.wasmModule, packs: this.packs,
          files: all, script: wrapped, collect: ['/work'],
        });
      });
    }
  }
  global.Pge2pyBridge = Pge2pyBridge;
})(self);
