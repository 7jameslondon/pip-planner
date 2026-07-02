const { app, BrowserWindow, dialog, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const { startPlannerServer, stopPlannerServer } = require('./server');

const appIconPath = path.join(__dirname, '..', 'assets', 'icons', 'icon.ico');
let mainWindow = null;
let splashWindow = null;
let server = null;
let startupPromise = null;
const isSmokeRun = process.env.PIP_PLANNER_ELECTRON_SMOKE === '1';

const SPLASH_HTML = `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    * { box-sizing: border-box; }
    html, body {
      width: 100%;
      height: 100%;
      margin: 0;
      background: #ffffff;
      color: #111111;
      font-family: Arial, Helvetica, sans-serif;
      overflow: hidden;
    }
    body {
      display: grid;
      place-items: center;
      border: 1px solid #111111;
    }
    .shell {
      width: 100%;
      padding: 30px 34px 28px;
    }
    h1 {
      margin: 0 0 6px;
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 34px;
      line-height: 1;
      letter-spacing: 0;
    }
    .rule {
      width: 154px;
      height: 3px;
      background: #111111;
      margin: 0 0 28px;
    }
    .status {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 13px;
      color: #333333;
    }
    .spinner {
      width: 18px;
      height: 18px;
      border: 2px solid #d0d0d0;
      border-top-color: #111111;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      flex: none;
    }
    .symbols {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-top: 28px;
    }
    .line {
      width: 38px;
      height: 4px;
      background: #111111;
    }
    .im, .py, .hp {
      width: 24px;
      height: 24px;
      border: 3px solid #111111;
      border-radius: 50%;
      display: grid;
      place-items: center;
      font-family: Georgia, 'Times New Roman', serif;
      font-weight: 700;
      font-size: 15px;
      line-height: 1;
    }
    .im { background: #111111; }
    .py, .hp { background: #ffffff; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="shell">
    <h1>PIP Planner</h1>
    <div class="rule"></div>
    <div class="status">
      <div class="spinner"></div>
      <div>Starting chemistry engine...</div>
    </div>
    <div class="symbols" aria-hidden="true">
      <div class="im"></div><div class="line"></div><div class="py"></div><div class="line"></div><div class="hp">H</div>
    </div>
  </div>
</body>
</html>`;

if (isSmokeRun) {
  const smokeUserData = path.join(process.cwd(), 'output', 'electron-smoke-user-data');
  fs.mkdirSync(smokeUserData, { recursive: true });
  app.setPath('userData', smokeUserData);
  app.disableHardwareAcceleration();
  [
    'disable-gpu',
    'disable-gpu-compositing',
    'disable-gpu-sandbox',
    'disable-software-rasterizer',
    'in-process-gpu',
    'no-sandbox'
  ].forEach((name) => app.commandLine.appendSwitch(name));
}

async function createWindow() {
  if (startupPromise) return startupPromise;

  startupPromise = createWindowAfterSplash();
  return startupPromise;
}

function createSplashWindow() {
  if (splashWindow && !splashWindow.isDestroyed()) return;

  splashWindow = new BrowserWindow({
    width: 420,
    height: 260,
    resizable: false,
    maximizable: false,
    minimizable: false,
    frame: false,
    center: true,
    show: true,
    title: 'PIP Planner',
    icon: appIconPath,
    backgroundColor: '#ffffff',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  splashWindow.on('closed', () => {
    splashWindow = null;
  });

  splashWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(SPLASH_HTML)}`);
  if (isSmokeRun) {
    console.log('electron-splash-created=true');
  }
}

async function createWindowAfterSplash() {
  createSplashWindow();

  server = await startPlannerServer({
    outDir: app.isPackaged
      ? path.join(app.getPath('userData'), 'generated')
      : path.join('output', 'electron')
  });

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 900,
    minWidth: 900,
    minHeight: 650,
    title: 'PIP Planner',
    icon: appIconPath,
    backgroundColor: '#f5f7fa',
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close();
      splashWindow = null;
    }
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  await mainWindow.loadURL(server.url);

  if (isSmokeRun) {
    const loaded = await mainWindow.webContents.executeJavaScript(
      `new Promise(resolve => {
        const deadline = Date.now() + 60000;
        function check() {
          const loaded = Boolean(document.querySelector('#design-form') && document.querySelector('#preview svg'));
          if (loaded || Date.now() > deadline) {
            resolve(loaded);
            return;
          }
          setTimeout(check, 150);
        }
        check();
      })`
    );
    console.log(`electron-smoke-loaded=${loaded}`);
    if (!loaded) process.exitCode = 1;
    app.quit();
  }
}

app.whenReady().then(() => {
  createWindow().catch(error => {
    dialog.showErrorBox('PIP Planner failed to start', error.stack || error.message);
    if (splashWindow && !splashWindow.isDestroyed()) {
      splashWindow.close();
      splashWindow = null;
    }
    app.quit();
  });
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    startupPromise = null;
    createWindow().catch(error => {
      dialog.showErrorBox('PIP Planner failed to start', error.stack || error.message);
      app.quit();
    });
  }
});

app.on('before-quit', () => {
  if (server) {
    stopPlannerServer(server.child);
    server = null;
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
