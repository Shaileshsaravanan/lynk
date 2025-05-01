const { app, BrowserWindow, dialog } = require('electron');
const path = require('path');
const url = require('url');
const http = require('http');

let mainWindow;

function checkFlaskServer(callback) {
  http.get('http://127.0.0.1:5001/health', (res) => {
    if (res.statusCode === 200) {
      callback(true);
    } else {
      callback(false, `Server returned status code ${res.statusCode}`);
    }
  }).on('error', (err) => {
    callback(false, `Could not connect to Flask server: ${err.message}`);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 800,
    height: 600,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    },
    show: false
  });

  checkFlaskServer((isRunning, error) => {
    if (isRunning) {
      mainWindow.loadURL('http://127.0.0.1:5001/')
        .then(() => {
          mainWindow.show();
        })
        .catch((err) => {
          dialog.showErrorBox('Loading Error', `Failed to load Flask app: ${err.message}`);
          mainWindow.show();
        });
    } else {
      mainWindow.loadFile(path.join(__dirname, 'error.html'))
        .then(() => {
          mainWindow.show();
        });
      dialog.showErrorBox('Server Error', `Flask server is not running: ${error}`);
    }
  });

  mainWindow.on('closed', function () {
    mainWindow = null;
  });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', function () {
  if (mainWindow === null) createWindow();
});

app.on('render-process-gone', (event, webContents, details) => {
  console.error('Render process gone:', details.reason);
});

app.on('child-process-gone', (event, details) => {
  console.error('Child process gone:', details.reason);
});