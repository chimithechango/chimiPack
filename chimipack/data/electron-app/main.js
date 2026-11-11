// chimiPack - Electron main process for generated apps.
// Web files live in ./www and are served through a private app:// protocol, so fetch(),
// ES modules, WebAssembly, localStorage and IndexedDB all work like a real website.
const { app, BrowserWindow, protocol, net, shell, Menu } = require("electron");
const path = require("path");
const { pathToFileURL } = require("url");
const cfg = require("./chimipack.json");

const WWW = path.join(__dirname, "www");
const ORIGIN = "app://local";

const DATA_DIR = path.join(app.getPath("appData"), "chimiPack", cfg.id);
// Keep saved data (localStorage, IndexedDB...) from builds made before the chimiPack rebrand.
const OLD_DATA_DIR = path.join(app.getPath("appData"), "HTML2App", cfg.id);
try {
  const fs = require("fs");
  if (fs.existsSync(OLD_DATA_DIR) && !fs.existsSync(DATA_DIR)) {
    fs.mkdirSync(path.dirname(DATA_DIR), { recursive: true });
    fs.renameSync(OLD_DATA_DIR, DATA_DIR);
  }
} catch { /* data stays where it was; the app still starts */ }
app.setPath("userData", DATA_DIR);
app.setAppUserModelId(cfg.id);
app.setName(cfg.name);

protocol.registerSchemesAsPrivileged([{
  scheme: "app",
  privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true, codeCache: true },
}]);

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  let win = null;
  app.on("second-instance", () => {
    if (win) { if (win.isMinimized()) win.restore(); win.focus(); }
  });

  app.whenReady().then(() => {
    protocol.handle("app", async (req) => {
      let p = decodeURIComponent(new URL(req.url).pathname);
      if (p === "/" || p === "") p = "/" + cfg.entry;
      if (p.endsWith("/")) p += "index.html";
      const file = path.normalize(path.join(WWW, p));
      if (!file.startsWith(WWW + path.sep)) return new Response("Forbidden", { status: 403 });
      try {
        return await net.fetch(pathToFileURL(file).toString());
      } catch {
        return new Response("Not found: " + p, { status: 404, headers: { "content-type": "text/plain" } });
      }
    });

    Menu.setApplicationMenu(null);
    win = new BrowserWindow({
      width: cfg.width, height: cfg.height, title: cfg.name, show: false,
      backgroundColor: "#ffffff", fullscreen: !!cfg.fullscreen, autoHideMenuBar: true,
      icon: path.join(__dirname, process.platform === "win32" ? "icon.ico" : "icon.png"),
      webPreferences: { contextIsolation: true, sandbox: true, spellcheck: false },
    });
    win.once("ready-to-show", () => win.show());

    // Links to other websites open in the user's normal browser.
    const external = (url) => !url.startsWith(ORIGIN);
    win.webContents.setWindowOpenHandler(({ url }) => {
      if (external(url)) { shell.openExternal(url); return { action: "deny" }; }
      return { action: "allow", overrideBrowserWindowOptions: { autoHideMenuBar: true } };
    });
    win.webContents.on("will-navigate", (e, url) => {
      if (external(url)) { e.preventDefault(); shell.openExternal(url); }
    });

    // Handy keys: F11 fullscreen, F5/Ctrl+R reload, Ctrl +/-/0 zoom, Ctrl+Shift+I dev tools.
    win.webContents.on("before-input-event", (e, i) => {
      if (i.type !== "keyDown") return;
      const wc = win.webContents, ctrl = i.control || i.meta;
      if (i.key === "F11") { win.setFullScreen(!win.isFullScreen()); e.preventDefault(); }
      else if (i.key === "Escape" && win.isFullScreen() && !cfg.fullscreen) win.setFullScreen(false);
      else if (i.key === "F5" || (ctrl && i.key.toLowerCase() === "r")) { wc.reload(); e.preventDefault(); }
      else if (ctrl && (i.key === "=" || i.key === "+")) { wc.setZoomLevel(wc.getZoomLevel() + 0.5); e.preventDefault(); }
      else if (ctrl && i.key === "-") { wc.setZoomLevel(wc.getZoomLevel() - 0.5); e.preventDefault(); }
      else if (ctrl && i.key === "0") { wc.setZoomLevel(0); e.preventDefault(); }
      else if (ctrl && i.shift && i.key.toLowerCase() === "i") { wc.toggleDevTools(); e.preventDefault(); }
    });

    win.loadURL(ORIGIN + "/" + cfg.entry.split("/").map(encodeURIComponent).join("/"));
  });

  app.on("window-all-closed", () => app.quit());
}
