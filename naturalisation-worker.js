let pyodide = null;
let ready = null;

async function boot() {
  self.postMessage({type:"progress", message:"ÉTAPE 1/5 — Récupération des versions du lecteur fmsave…"});
  const pinsResponse = await fetch("https://rhiever.github.io/fmsave/app/pins.json", {cache:"no-cache"});
  if (!pinsResponse.ok) throw new Error("Impossible de récupérer la configuration du lecteur (HTTP " + pinsResponse.status + ").");
  const pins = await pinsResponse.json();
  const pyodideUrl = "https://cdn.jsdelivr.net/pyodide/v" + pins.pyodide + "/full/";
  self.postMessage({type:"progress", message:"ÉTAPE 2/5 — Téléchargement et démarrage du moteur Python (Pyodide)…"});
  const {loadPyodide} = await import(pyodideUrl + "pyodide.mjs");
  pyodide = await loadPyodide({indexURL:pyodideUrl});
  self.postMessage({type:"progress", message:"ÉTAPE 3/5 — Préparation du gestionnaire de paquets Python…"});
  await pyodide.loadPackage("micropip");
  self.postMessage({type:"progress", message:"ÉTAPE 4/5 — Installation de fmsave 0.14.3 (cela peut prendre plusieurs minutes)…"});
  await pyodide.runPythonAsync("import micropip; await micropip.install('fmsave==0.14.3')");
  self.postMessage({type:"progress", message:"ÉTAPE 5/5 — Chargement du module d’analyse de sauvegarde…"});
  const readerResponse = await fetch("naturalisation-reader.py?v=nation-map-audit-20261122", {cache:"no-store"});
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
      const history = JSON.stringify(data.trackedPlayerHistory || {});
      const code = "naturalisation_reader.analyze_save('/save/" +
        data.file.name.replace(/\\/g, "").replace(/'/g, "\\'") +
        "', " + JSON.stringify(tracked) + ", " + JSON.stringify(history) + ")";
      const result = await pyodide.runPythonAsync(code);
      self.postMessage({type:"result", data:JSON.parse(result)});
    } finally {
      try { pyodide.FS.unmount("/save"); } catch {}
    }
  } catch (error) {
    self.postMessage({type:"error", message:String(error && error.message || error)});
  }
};
