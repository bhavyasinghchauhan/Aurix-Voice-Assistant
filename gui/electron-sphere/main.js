const { app, BrowserWindow, ipcMain, screen } = require('electron');
const path = require('path');
const WebSocket = require('ws');

let mainWindow;
let wsServer;
let pythonSocket = null;

const WS_PORT = 9734;

function createWindow() {
  const display = screen.getPrimaryDisplay();
  const { width: screenW, height: screenH } = display.workAreaSize;

  mainWindow = new BrowserWindow({
    width: 350,
    height: 350,
    x: 50,
    y: screenH - 400,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: false,
    resizable: false,
    hasShadow: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  });

  mainWindow.loadFile('index.html');
  mainWindow.setMenuBarVisibility(false);
  mainWindow.setAlwaysOnTop(true, 'screen-saver');
}

function startWebSocketServer() {
  wsServer = new WebSocket.Server({ port: WS_PORT });
  console.log(`AURIX sphere WebSocket listening on ws://localhost:${WS_PORT}`);

  wsServer.on('connection', (ws) => {
    console.log('AURIX Python controller connected');
    pythonSocket = ws;

    ws.on('message', (data) => {
      try {
        const msg = JSON.parse(data.toString());

        if (msg.type === 'state') {
          if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('aurix-state', msg.state);
          }
        } else if (msg.type === 'audio') {
          if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('aurix-audio', msg);
          }
        } else if (msg.type === 'goodbye') {
          if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('aurix-goodbye');
          }
          setTimeout(() => app.quit(), 3000);
        } else if (msg.type === 'quit') {
          app.quit();
        }
      } catch (e) {
        console.error('Invalid message:', e);
      }
    });

    ws.on('close', () => {
      console.log('AURIX Python controller disconnected');
      pythonSocket = null;
    });
  });
}

// Forward click events from renderer to Python
ipcMain.on('sphere-clicked', () => {
  if (pythonSocket && pythonSocket.readyState === WebSocket.OPEN) {
    pythonSocket.send(JSON.stringify({ type: 'click' }));
  }
});

app.whenReady().then(() => {
  createWindow();
  startWebSocketServer();

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', function () {
  if (wsServer) {
    wsServer.close();
  }
  if (process.platform !== 'darwin') app.quit();
});

ipcMain.on('set-ignore-mouse', (event, ignore) => {
  if (mainWindow) {
    mainWindow.setIgnoreMouseEvents(ignore, { forward: true });
  }
});
