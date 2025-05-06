const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const http = require('http');
const fs = require('fs');

let mainWindow;
let peerWindow;

const connectionFilePath = path.join(__dirname, 'data/connection.json');
const defaultConnectionData = {
  websocket_url: null,
  port: null,
  path: null,
  auth_token: "your_auth_token_here",
  connection_id: "your_connection_id_here"
};

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
    width: 900,
    height: 600,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    },
    show: true,
    backgroundColor: '#ffffff'
  });

  mainWindow.loadFile(path.join(__dirname, 'initializing.html'));
  mainWindow.on('closed', function () {
    mainWindow = null;
  });
}

function fetchConnectionJSON() {
  if (fs.existsSync(connectionFilePath)) {
    const data = JSON.parse(fs.readFileSync(connectionFilePath, 'utf-8'));
    return data;
  } else {
    return null;
  }
}

function createPeerWindow() {
  peerWindow = new BrowserWindow({
    show: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false
    }
  });

  peerWindow.loadFile(path.join(__dirname, 'peer.html'));

  peerWindow.webContents.on('did-finish-load', () => {
    const connectionData = fetchConnectionJSON();
    if (connectionData) {
      peerWindow.webContents.send('set-data', connectionData);
    }
  });

  peerWindow.on('closed', () => {
    peerWindow = null;
  });
}

function restartPeerWindow() {
  if (peerWindow) {
    peerWindow.close();
    peerWindow = null;
  }
  createPeerWindow();
}

function createConnectionFileIfNotExists() {
  if (!fs.existsSync(connectionFilePath)) {
    fs.writeFileSync(connectionFilePath, JSON.stringify(defaultConnectionData, null, 2), 'utf-8');
  }
}

const server = http.createServer((req, res) => {
  if (req.url === '/restart-peer' && req.method === 'GET') {
    restartPeerWindow();
    res.writeHead(200, { 'Content-Type': 'text/plain' });
    res.end('Peer window restarted');
  } else {
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('Not Found');
  }
});

server.listen(5003);

ipcMain.on('peer-log', (event, message) => {
  console.log('Peer log:', message);
});

ipcMain.on('background-log', (event, message) => {
  console.log('Background log:', message);
});

app.whenReady().then(() => {
  createConnectionFileIfNotExists();
  createWindow();
  createPeerWindow();

  app.on('activate', () => {
    if (mainWindow === null) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('render-process-gone', (event, webContents, details) => {
  console.error('Render process gone:', details.reason);
});

app.on('child-process-gone', (event, details) => {
  console.error('Child process gone:', details.reason);
});