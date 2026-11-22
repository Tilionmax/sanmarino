let pyodide = null;
let ready = null;

async function boot() {
  const pins = await (await fetch("https://rhiever.github.io/fmsave/app/pins.json", {cache:"no-cache"})).json();
  const pyodideUrl = "https://cdn.jsdelivr.net/pyodide/v" + pins.pyodide + "/full/";
  const {loadPyodide} = await import(pyodideUrl + "pyodide.mjs");
  pyodide = await loadPyodide({indexURL:pyodideUrl});
  await pyodide.loadPackage("micropip");
  await pyodide.runPythonAsync("import micropip; await micropip.install('fmsave==0.14.3')");
  const readerResponse = await fetch("naturalisation-reader.py");
  if (!readerResponse.ok) throw new Error("Impossible de charger le lecteur de sauvegarde.");
  pyodide.FS.writeFile("/home/pyodide/naturalisation_reader.py", await readerResponse.text());
  await pyodide.runPythonAsync("import sys; sys.path.insert(0, '/home/pyodide'); import naturalisation_reader");
  return {pyodide:pyodide.version, fmsave:"0.14.3"};
}

self.onmessage = async (event) => {
  const data = event.data || {};
  try {
    if (data.type === "boot") {
      ready = boot();
      const versions = await ready;
      self.postMessage({type:"ready", ...versions});
      return;
    }
    if (data.type !== "read") return;
    await ready;
    pyodide.FS.mkdirTree("/save");
    try { pyodide.FS.unmount("/save"); } catch {}
    pyodide.FS.mount(pyodide.FS.filesystems.WORKERFS, {files:[data.file]}, "/save");
    try {
      const tracked = JSON.stringify(data.trackedClubs || []);
      const code = "naturalisation_reader.analyze_save('/save/" +
        data.file.name.replace(/\\/g, "").replace(/'/g, "\\'") +
        "', " + JSON.stringify(tracked) + ")";
      const result = await pyodide.runPythonAsync(code);
      self.postMessage({type:"result", data:JSON.parse(result)});
    } finally {
      try { pyodide.FS.unmount("/save"); } catch {}
    }
  } catch (error) {
    self.postMessage({type:"error", message:String(error && error.message || error)});
  }
};
