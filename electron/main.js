const { app, BrowserWindow, dialog, shell } = require('electron');
const path = require('path');
const { startPlannerServer, stopPlannerServer } = require('./server');

let mainWindow = null;
let server = null;

async function createWindow() {
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
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  await mainWindow.loadURL(server.url);

  if (process.env.PIP_PLANNER_ELECTRON_SMOKE === '1') {
    const loaded = await mainWindow.webContents.executeJavaScript(
      `new Promise(resolve => {
        const deadline = Date.now() + 15000;
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
    app.quit();
  });
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
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
