const { app, BrowserWindow, ipcMain, session } = require('electron');
const path = require('path');
const http = require('http');
const os = require('os');
const crypto = require('crypto');
const fs = require('fs');
const { spawn } = require('child_process');
const logger = require('./logger');
const config = require('./electron/config');

let mainWindow;
let wsInstance;
let flaskProcess;
let trackProcess;

const pythonExecutable = config.python.executable || 'python3';

const logPythonPath = spawn(pythonExecutable, ['-c', 'import sys; print(sys.executable)']);

logPythonPath.stdout.on('data', (data) => {
  console.log(`🐍 Python interpreter in use: ${data.toString().trim()}`);
});

logPythonPath.stderr.on('data', (data) => {
  console.error(`❌ Error logging Python path: ${data.toString()}`);
});

const prefix = crypto.createHash('sha1').update(os.hostname()).digest('hex').slice(0, 8);
let counter = 0;

const userDataPath = config.userDataPath;
const dataDir = config.dataPath;
console.log('-->',dataDir)

function generateTrulyUniqueId() {
  const timestamp = Date.now();
  const tzOffset = new Date().getTimezoneOffset();
  const id = `${timestamp}-${tzOffset}-${prefix}-${counter++}`;
  return id;
}

function ensureDataDirectory() {
  try {
    if (!fs.existsSync(dataDir)) {
      fs.mkdirSync(dataDir, { recursive: true });
    }
  } catch (error) {
    logger.error('Failed to create data directory', { error: error.message });
  }
}

function initializeConnectionData() {
  const connectionDataPath = path.join(dataDir, 'connection.json');
  try {
    if (!fs.existsSync(connectionDataPath)) {
      ensureDataDirectory();
      const defaultData = {
        websocket_url: config.defaultConnection.websocket_url,
        connection_id: generateTrulyUniqueId()
      };
      fs.writeFileSync(connectionDataPath, JSON.stringify(defaultData, null, 2));
    }
  } catch (error) {
    logger.error('Failed to initialize connection data', { error: error.message });
  }
}

function getConnectionData() {
  const configPath = path.join(dataDir, 'connection.json');
  try {
    if (!fs.existsSync(configPath)) {
      logger.error('Missing connection.json');
      return null;
    }
    return JSON.parse(fs.readFileSync(configPath, 'utf8'));
  } catch (error) {
    logger.error('Failed to read connection data', { error: error.message });
    return null;
  }
}

function createWsInstance() {
  wsInstance = new BrowserWindow({
    width: 800,
    height: 600,
    show: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      enableRemoteModule: false,
      preload: path.join(__dirname, 'preload.js')
    },
    backgroundColor: '#ffffff'
  });

  wsInstance.loadFile(path.join(__dirname, 'ws.html'));

  wsInstance.on('closed', () => {
    wsInstance = null;
  });

  ipcMain.handle('get-ws-data', async () => {
    return getConnectionData();
  });

  ipcMain.on('ws', (event, message) => {
    console.log('Received from ws.html:', message);
    const connectionData = getConnectionData();
    if (connectionData) {
      event.sender.send('ws', connectionData);
    } else {
      event.sender.send('ws-error', 'Failed to load connection data');
    }
  });
}

function startFlaskServer() {
  try{
    return new Promise((resolve, reject) => {
      const flaskPythonExecutable = config.python.flaskExecutable;
      const appPath = app.isPackaged 
        ? path.join(process.resourcesPath + 'app/', 'app.py')
        : path.join(__dirname, 'app.py');

      const flaskEnv = {
        LYNK_DATA_DIR: dataDir,
        PYTHONPATH: app.isPackaged ? process.resourcesPath : __dirname,
        NODE_ENV: app.isPackaged ? 'production' : 'development'
      };
      console.log('Flask Python Executable:', flaskEnv, '-->', process.resourcesPath);
      flaskProcess = spawn(flaskPythonExecutable, [appPath], {
        cwd: path.dirname(appPath),
        env: flaskEnv,
        stdio: ['ignore', 'pipe', 'pipe'],
        detached: true
      });

      console.log('==>', flaskPythonExecutable, [appPath])

      flaskProcess.stdout.on('data', (data) => {
        logger.info(`Flask stdout: ${data.toString().trim()}`, null, 'flask');
        if (data.toString().includes('Running on')) {
          resolve();
        }
      });

      flaskProcess.stderr.on('data', (data) => {
        logger.error(`Flask stderr: ${data.toString().trim()}`, null, 'flask');
      });

      flaskProcess.on('error', (error) => {
        logger.error('Failed to start Flask server', { error: error.message }, 'flask');
        reject(error);
      });

      flaskProcess.on('close', (code) => {
        logger.info(`Flask process exited with code ${code}`, null, 'flask');
      });

      setTimeout(() => {
        reject(new Error('Flask server startup timeout'));
      }, config.flask.startupTimeout);
    });
  } catch (error){
    const ffilePath = path.join(__dirname, 'flask.txt');
    fs.writeFile(ffilePath, error, (err) => {
      if (err) {
        console.error('Failed to write file:', err);
      } else {
        console.log('File written to', ffilePath);
      }
    });
  }
}

function startTrackServer() {
  logger.info('Initializing startTrackServer()', null, 'track');

  try {
    return new Promise((resolve, reject) => {
      logger.info('Preparing to launch track.py...', null, 'track');

      const trackPythonExecutable = config.python.trackExecutable;
      const trackPath = app.isPackaged
        ? path.join(process.resourcesPath + 'app/', 'track.py')
        : path.join(__dirname, 'track.py');

      const trackEnv = {
        ...process.env,  // Inherit existing environment
        LYNK_DATA_DIR: dataDir,
        PYTHONPATH: config.python.trackExecutable,
        NODE_ENV: app.isPackaged ? 'production' : 'development'
      };

      logger.info(`trackPythonExecutable: ${trackPythonExecutable}`, null, 'track');
      logger.info(`trackPath: ${trackPath}`, null, 'track');
      logger.info(`trackEnv: ${JSON.stringify(trackEnv)}`, null, 'track');

      try {
        trackProcess = spawn(trackPythonExecutable, [trackPath], {
          cwd: path.dirname(trackPath),
          env: trackEnv,
          stdio: ['ignore', 'pipe', 'pipe'],
          detached: true
        });

        logger.info('track.py process spawned successfully.', null, 'track');

        // Log every line from stdout
        trackProcess.stdout.setEncoding('utf8');
        trackProcess.stdout.on('data', (data) => {
          data.toString().split(/\r?\n/).forEach(line => {
            if (line.trim()) {
              logger.info(`[track.py stdout] ${line}`, null, 'track');
              if (line.includes('Tracking initialized')) {
                logger.info('Tracking successfully initialized. Resolving startTrackServer()', null, 'track');
                resolve();
              }
            }
          });
        });

        // Log every line from stderr
        trackProcess.stderr.setEncoding('utf8');
        trackProcess.stderr.on('data', (data) => {
          data.toString().split(/\r?\n/).forEach(line => {
            if (line.trim()) {
              logger.error(`[track.py stderr] ${line}`, null, 'track');
            }
          });
        });

        trackProcess.on('error', (error) => {
          logger.error('Error event from track.py process', { error: error.message }, 'track');
          reject(error);
        });

        trackProcess.on('close', (code) => {
          logger.info(`Track process exited with code ${code}`, null, 'track');
        });

      } catch (err) {
        logger.error('Exception while spawning track.py process', { error: err.message }, 'track');
        reject(err);
      }
    });
  } catch (error){
    const tfilePath = path.join(__dirname, 'track.txt');
    fs.writeFile(tfilePath, error, (err) => {
      if (err) {
        console.error('Failed to write file:', err);
      } else {
        console.log('File written to', tfilePath);
      }
      }
    )
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    ...config.mainWindow,
    webPreferences: {
      ...config.mainWindow.webPreferences,
      preload: path.join(__dirname, 'preload.js')
    },
    show: true,
    backgroundColor: '#ffffff'
  });

  mainWindow.loadFile(path.join(__dirname, 'initializing.html'));
  startTrackServer();
  startFlaskServer();

  mainWindow.on('closed', function () {
    mainWindow = null;
  });
}

function cleanup() {
  logger.info('Starting cleanup process...');

  [flaskProcess, trackProcess].forEach(proc => {
    if (proc && !proc.killed) {
      try {
        logger.info(`Terminating process group: ${proc.pid}`);
        process.kill(-proc.pid, 'SIGTERM'); // Kill process group

        setTimeout(() => {
          try {
            process.kill(-proc.pid, 'SIGKILL');
          } catch (e) {
            logger.warn('Process already terminated or not found');
          }
        }, 3000);
      } catch (error) {
        logger.error('Error terminating process group', { error: error.message });
      }
    }
  });
}

const connectionJSONFilePath = dataDir + '/connection.json';

let websocketHostname;
let websocketHostnameWS;
try {
  const data = fs.readFileSync(connectionJSONFilePath, 'utf-8');
  const json = JSON.parse(data);
  const websocketUrl = json.websocket_url;

  websocketHostname = new URL(websocketUrl);
  websocketHostnameWS = 'wss://' + new URL(websocketUrl).hostname;

  console.log('WebSocket Hostname:', websocketHostname);
} catch (error) {
  console.error('Error reading or parsing connection.json:', error);
}


app.whenReady().then(() => {
  session.defaultSession.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [
          `default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self' ${websocketHostname} ${websocketHostnameWS} http://localhost:5001 http://127.0.0.1:5001 http://localhost:5002 http://127.0.0.1:5002 ws://localhost:5001 ws://127.0.0.1:5001 ws://localhost:5002 ws://127.0.0.1:5002;`
        ]
      }
    });
  });

  initializeConnectionData();
  createWindow();
  createWsInstance();

  app.on('activate', () => {
    if (mainWindow === null) createWindow();
    if (wsInstance === null) createWsInstance();
  });
});

app.on('before-quit', () => {
  cleanup();
});

app.on('window-all-closed', () => {
  cleanup();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('render-process-gone', (event, webContents, details) => {
  logger.error('Render process gone', { reason: details.reason });
  if (webContents === mainWindow?.webContents) {
    setTimeout(() => {
      if (mainWindow === null) {
        logger.info('Restarting main window after crash');
        createWindow();
      }
    }, 1000);
  }
});

app.on('child-process-gone', (event, details) => {
  logger.error('Child process gone', { reason: details.reason });
});

process.on('uncaughtException', (error) => {
  logger.error('Uncaught Exception', { error: error.message, stack: error.stack });
  cleanup();
  process.exit(1);
});

process.on('unhandledRejection', (reason, promise) => {
  logger.error('Unhandled Rejection', {
    reason: reason instanceof Error ? reason.message : JSON.stringify(reason),
    stack: reason instanceof Error ? reason.stack : undefined,
    promise
  });
});

