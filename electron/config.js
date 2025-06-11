/**
 * Production configuration for Lynk application
 */

const { app } = require('electron');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execSync } = require('child_process');

// Detect platform
const isWindows = process.platform === 'win32';
const isDevelopment = process.env.NODE_ENV === 'development';
const isProduction = process.env.NODE_ENV === 'production';

const connectionJSONFilePath = app
  ? path.join(app.getPath('userData'), 'data', 'connection.json')
  : path.join(os.homedir(), '.lynk', 'data', 'connection.json');

let websocketHostname;
try {
  const data = fs.readFileSync(connectionJSONFilePath, 'utf-8');
  const json = JSON.parse(data);
  const websocketUrl = json.websocket_url;

  // Extract hostname
  websocketHostname = new URL(websocketUrl).hostname;

  console.log('WebSocket Hostname:', websocketHostname);
} catch (error) {
  console.error('Error reading or parsing connection.json:', error);
}

// Get global Python path (cross-platform)
let globalPython = isWindows ? 'python' : 'python3'; // default fallback

try {
  const cmd = isWindows ? 'where python' : 'which python3';
  const output = execSync(cmd).toString().trim();
  globalPython = output.split(/\r?\n/)[0]; // Use first found path
  console.log(`🐍 Using global Python: ${globalPython}`);
} catch (err) {
  console.warn('⚠️ Could not find global Python. Using fallback:', globalPython);
}

// Config object
const config = {
  // Environment
  isDevelopment,
  isProduction,

  // Application info
  appName: 'Lynk',
  appVersion: require('../package.json').version,

  // Paths
  userDataPath: app ? app.getPath('userData') : path.join(os.homedir(), '.lynk'),
  logsPath: app ? path.join(app.getPath('userData'), 'logs') : path.join(os.homedir(), '.lynk', 'logs'),
  dataPath: app ? path.join(app.getPath('userData'), 'data') : path.join(os.homedir(), '.lynk', 'data'),

  // Server configuration
  flask: {
    host: '127.0.0.1',
    port: 5001,
    startupTimeout: 30000, 
  },

  tracking: {
    host: '127.0.0.1',
    port: 5002,
    startupTimeout: 30000,
  },

  // Window configuration
  mainWindow: {
    width: 900,
    height: 600,
    minWidth: 800,
    minHeight: 500,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false,
      sandbox: false, // Disabled for Flask communication
      webSecurity: true
    }
  },

  wsWindow: {
    width: 800,
    height: 600,
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false,
      sandbox: false,
      webSecurity: true
    }
  },

  // Security settings
  security: {
    allowedHosts: ['127.0.0.1', 'localhost', websocketHostname],
    allowedPorts: [5001, 5002],
    csp: "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
  },

  // Logging configuration
  logging: {
    level: isDevelopment ? 'debug' : 'info',
    maxFiles: 7, // Keep logs for 7 days
    maxSize: '10MB'
  },

  // Default connection settings
  defaultConnection: {
    websocket_url: 'https://lynk-ws-server.onrender.com',
    connection_id: null // Will be generated
  },

  // Python configuration
  python: {
    executable: globalPython,
    flaskExecutable: globalPython,
    trackExecutable: globalPython,
    minVersion: '3.10.0'
  },

  // Update configuration
  updates: {
    checkInterval: 24 * 60 * 60 * 1000, // 24 hours
    autoDownload: false,
    autoInstall: false
  }
};

// Validate configuration
function validateConfig() {
  const errors = [];

  if (!config.flask.host || !config.flask.port) {
    errors.push('Flask configuration is incomplete');
  }

  if (!config.tracking.host || !config.tracking.port) {
    errors.push('Tracking configuration is incomplete');
  }

  if (config.flask.port === config.tracking.port) {
    errors.push('Flask and tracking ports cannot be the same');
  }

  if (errors.length > 0) {
    throw new Error(`Configuration validation failed: ${errors.join(', ')}`);
  }
}

// Initialize configuration
try {
  validateConfig();
} catch (error) {
  console.error('Configuration error:', error.message);
  process.exit(1);
}

module.exports = config;