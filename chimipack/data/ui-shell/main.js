// chimiPack converter window (Electron). The Python backend passes its local URL on the command line.
// chimiPack converter window (Electron).
const { app, BrowserWindow, ipcMain, dialog, shell, Menu, nativeTheme, nativeImage } = require("electron");
const path = require("path");

const URL_ARG = "--chimi-url=";
const url = (process.argv.find(a => a.startsWith(URL_ARG)) || "").slice(URL_ARG.length);
app.setPath("userData", path.join(app.getPath("appData"), "chimiPack", "converter"));
app.setAppUserModelId("com.chimi.chimipack");
app.setName("chimiPack");

if (!app.requestSingleInstanceLock()) app.quit();

let win = null;
app.on("second-instance", () => { if (win) { if (win.isMinimized()) win.restore(); win.focus(); } });

const FILTERS = {
  file: [{ name: "Web page or zip", extensions: ["html", "htm", "xhtml", "zip"] }, { name: "All files", extensions: ["*"] }],
  icon: [{ name: "Images", extensions: ["png", "jpg", "jpeg", "ico", "bmp", "gif"] }],
};
const TITLES = { file: "Choose an HTML file (or a .zip of your site)", folder: "Choose the folder with your web app",
  icon: "Choose an icon image", output: "Where should the apps be saved?" };

ipcMain.handle("chimi:pick", async (_e, kind, start) => {
  const dirs = kind === "folder" || kind === "output";
  const r = await dialog.showOpenDialog(win, {
    title: TITLES[kind] || "Choose", defaultPath: start || undefined,
    properties: dirs ? ["openDirectory", "createDirectory"] : ["openFile"], filters: dirs ? undefined : FILTERS[kind],
  });
  return r.canceled ? "" : r.filePaths[0] || "";
});
ipcMain.handle("chimi:theme", (_e, t) => {
  nativeTheme.themeSource = ["light", "dark"].includes(t) ? t : "system";  // title bar + dialogs follow
  if (win) win.setBackgroundColor(nativeTheme.shouldUseDarkColors ? "#141416" : "#f5f5f6");
});
// The logo follows the accent color: title-bar and taskbar icon.
ipcMain.handle("chimi:icon", (_e, dataUrl) => {
  if (!win || typeof dataUrl !== "string" || !dataUrl.startsWith("data:image/png;base64,")) return;
  const img = nativeImage.createFromDataURL(dataUrl);
  if (!img.isEmpty()) win.setIcon(img);
});
ipcMain.handle("chimi:reveal", (_e, p) => { require("fs").statSync(p).isDirectory() ? shell.openPath(p) : shell.showItemInFolder(p); });

app.whenReady().then(() => {
  Menu.setApplicationMenu(null);
  win = new BrowserWindow({
    width: 1180, height: 820, minWidth: 560, minHeight: 500, title: "chimiPack", show: false,
    backgroundColor: nativeTheme.shouldUseDarkColors ? "#141416" : "#f5f5f6", icon: path.join(__dirname, "icon.ico"), autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, "preload.js"), contextIsolation: true, sandbox: true },
  });
  win.once("ready-to-show", () => win.show());
  win.webContents.setWindowOpenHandler(({ url: u }) => { shell.openExternal(u); return { action: "deny" }; });
  win.webContents.on("will-navigate", (e, u) => { if (!u.startsWith(url)) { e.preventDefault(); shell.openExternal(u); } });
  win.webContents.on("before-input-event", (e, i) => {
    if (i.type === "keyDown" && i.control && i.shift && i.key.toLowerCase() === "i") win.webContents.toggleDevTools();
  });
  win.loadURL(url);
});
app.on("window-all-closed", () => app.quit());
