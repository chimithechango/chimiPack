const { contextBridge, ipcRenderer, webUtils } = require("electron");

contextBridge.exposeInMainWorld("chimi", {
  pick: (kind, start) => ipcRenderer.invoke("chimi:pick", kind, start),
  reveal: (p) => ipcRenderer.invoke("chimi:reveal", p),
  setTheme: (t) => ipcRenderer.invoke("chimi:theme", t),
  setIcon: (dataUrl) => ipcRenderer.invoke("chimi:icon", dataUrl),
  pathFor: (file) => { try { return webUtils.getPathForFile(file) || ""; } catch { return ""; } },
});
