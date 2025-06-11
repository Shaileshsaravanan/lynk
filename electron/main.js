const { app, BrowserWindow, ipcMain, session } = require('electron');
const path = require('path');
const os = require('os');
const crypto = require('crypto');
const fs = require('fs');
const { spawn } = require('child_process');
const logger = require('./logger');
const config = require('./config');

let mainWindow;
let wsInstance;
let fastApiProcess;
let trackProcess;

const prefix = crypto.createHash('sha1').update(os.hostname()).digest('hex').slice(0, 8);
let counter = 0;

const userDataPath = config.userDataPath;
const dataDir = config.dataPath;

function generateTrulyUniqueId() {
  const timestamp = Date.now();
  const tzOffset = new Date().getTimezoneOffset();
  return `${timestamp}-${tzOffset}-${prefix}-${counter++}`;
}

function ensureDataDirectory() {
  if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });
}

function initializeConnectionData() {
  const connectionDataPath = path.join(dataDir, 'connection.json');
  if (!fs.existsSync(connectionDataPath)) {
    ensureDataDirectory();
    const defaultData = {
      websocket_url: config.defaultConnection.websocket_url,
      connection_id: generateTrulyUniqueId()
    };
    fs.writeFileSync(connectionDataPath, JSON.stringify(defaultData, null, 2));
  }
}

function getConnectionData() {
  try {
    const configPath = path.join(dataDir, 'connection.json');
    return fs.existsSync(configPath) ? JSON.parse(fs.readFileSync(configPath, 'utf8')) : null;
  } catch (err) {
    logger.error('Error reading connection data', { error: err.message });
    return null;
  }
}

function getBinaryPath(binaryName) {
  const platform = process.platform === 'win32' ? 'win' : process.platform === 'darwin' ? 'mac' : 'linux';
  const extension = process.platform === 'win32' ? '.exe' : '';
  const basePath = app.isPackaged
    ? path.join(process.resourcesPath + '/app/', 'binaries', platform)
    : path.join(__dirname, 'binaries', platform);
  return path.join(basePath, binaryName + extension);
}

function startFastApiServer() {
  return new Promise((resolve, reject) => {
    const fastApiPath = getBinaryPath('app');

    const fastApiEnv = {
      ...process.env,
      LYNK_DATA_DIR: dataDir,
      NODE_ENV: app.isPackaged ? 'production' : 'development'
    };

    fastApiProcess = spawn(fastApiPath, [], {
      cwd: path.dirname(fastApiPath),
      env: fastApiEnv,
      stdio: ['ignore', 'pipe', 'pipe'],
      detached: true
    });

    fastApiProcess.stdout.on('data', (data) => {
      const text = data.toString().trim();
      logger.info(`FastAPI stdout: ${text}`, null, 'fastapi');
      if (text.includes('Uvicorn running on') || text.includes('Application startup complete')) {
        resolve();
      }
    });

    fastApiProcess.stderr.on('data', (data) => {
      logger.error(`FastAPI stderr: ${data.toString().trim()}`, null, 'fastapi');
    });

    fastApiProcess.on('error', (error) => {
      logger.error('FastAPI server failed to start', { error: error.message }, 'fastapi');
      reject(error);
    });

    fastApiProcess.on('close', (code) => {
      logger.info(`FastAPI process exited with code ${code}`, null, 'fastapi');
    });

    setTimeout(() => reject(new Error('FastAPI server timeout')), config.fastapi.startupTimeout || 15000);
  });
}

function startTrackServer() {
  return new Promise((resolve, reject) => {
    const trackPath = getBinaryPath('track');

    const trackEnv = {
      ...process.env,
      LYNK_DATA_DIR: dataDir,
      NODE_ENV: app.isPackaged ? 'production' : 'development'
    };

    trackProcess = spawn(trackPath, [], {
      cwd: path.dirname(trackPath),
      env: trackEnv,
      stdio: ['ignore', 'pipe', 'pipe'],
      detached: true
    });

    trackProcess.stdout.on('data', (data) => {
      const text = data.toString();
      text.split(/\r?\n/).forEach(line => {
        if (line.includes('Tracking initialized')) resolve();
        if (line.trim()) logger.info(`[track.py stdout] ${line}`, null, 'track');
      });
    });

    trackProcess.stderr.on('data', (data) => {
      const text = data.toString();
      text.split(/\r?\n/).forEach(line => {
        if (line.trim()) logger.error(`[track.py stderr] ${line}`, null, 'track');
      });
    });

    trackProcess.on('error', (error) => {
      logger.error('Track server failed to start', { error: error.message }, 'track');
      reject(error);
    });

    trackProcess.on('close', (code) => {
      logger.info(`Track process exited with code ${code}`, null, 'track');
    });

    setTimeout(() => reject(new Error('Track server timeout')), config.track?.startupTimeout || 15000);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    ...config.mainWindow,
    webPreferences: {
      ...config.mainWindow.webPreferences,
      preload: path.join(__dirname, 'preload.js')
    },
    backgroundColor: '#ffffff'
  });

  mainWindow.loadFile(path.join(__dirname, 'initializing.html'));

  startTrackServer().catch(err => logger.error('Track failed', { error: err.message }));
  startFastApiServer().catch(err => logger.error('FastAPI failed', { error: err.message }));

  mainWindow.on('closed', () => (mainWindow = null));
}

function createWsInstance() {
  wsInstance = new BrowserWindow({
    width: 800,
    height: 600,
    show: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      preload: path.join(__dirname, 'preload.js')
    },
    backgroundColor: '#ffffff'
  });

  wsInstance.loadFile(path.join(__dirname, 'ws.html'));

  wsInstance.on('closed', () => (wsInstance = null));

  ipcMain.handle('get-ws-data', async () => getConnectionData());
  ipcMain.on('ws', (event) => {
    const connectionData = getConnectionData();
    if (connectionData) {
      event.sender.send('ws', connectionData);
    } else {
      event.sender.send('ws-error', 'Failed to load connection data');
    }
  });
}

function cleanup() {
  [fastApiProcess, trackProcess].forEach(proc => {
    if (proc && !proc.killed) {
      try {
        process.kill(-proc.pid, 'SIGTERM');
        setTimeout(() => {
          try {
            process.kill(-proc.pid, 'SIGKILL');
          } catch {}
        }, 3000);
      } catch (e) {
        logger.warn('Cleanup failed', { error: e.message });
      }
    }
  });
}

app.whenReady().then(() => {
  const connectionJSONPath = path.join(dataDir, 'connection.json');
  let websocketHostname = '';
  let websocketHostnameWS = '';

  try {
    const json = JSON.parse(fs.readFileSync(connectionJSONPath, 'utf-8'));
    const wsUrl = new URL(json.websocket_url);
    websocketHostname = wsUrl.hostname;
    websocketHostnameWS = 'wss://' + wsUrl.hostname;
  } catch (e) {
    console.error('Invalid connection.json', e);
  }

  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    const csp = `
      default-src 'self'; 
      script-src 'self' 'unsafe-inline'; 
      style-src 'self' 'unsafe-inline'; 
      img-src 'self' data:; 
      connect-src 'self' ${websocketHostname} ${websocketHostnameWS} http://localhost:5001 http://127.0.0.1:5001 ws://localhost:5001 http://localhost:5002 http://127.0.0.1:5002 ws://localhost:5002;
    `;

    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [
          csp
        ]
      }
    });
  });

  initializeConnectionData();
  createWindow();
  createWsInstance();
});

app.on('before-quit', cleanup);
app.on('window-all-closed', () => {
  cleanup();
  if (process.platform !== 'darwin') app.quit();
});