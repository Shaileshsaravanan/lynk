const { spawn } = require('child_process');
const { platform } = require('os');
const { join } = require('path');
const http = require('http');

const isWin = platform() === 'win32';

const flaskProcess = spawn(
  isWin ? 'python' : 'python3', 
  ['app.py'], 
  { 
    stdio: 'inherit',
    shell: true
  }
);

const checkFlaskServer = (retries = 0, maxRetries = 30) => {
  if (retries >= maxRetries) {
    flaskProcess.kill();
    process.exit(1);
    return;
  }
  
  http.get('http://127.0.0.1:5001/health', (res) => {
    if (res.statusCode === 200) {
      startElectron();
    } else {
      setTimeout(() => checkFlaskServer(retries + 1, maxRetries), 1000);
    }
  }).on('error', (err) => {
    setTimeout(() => checkFlaskServer(retries + 1, maxRetries), 1000);
  });
};

const startElectron = () => {
  const electronProcess = spawn(
    isWin ? 'npx.cmd' : 'npx',
    ['electron', '.'],
    { 
      stdio: 'inherit',
      shell: true
    }
  );

  electronProcess.on('close', (code) => {
    flaskProcess.kill();
    process.exit();
  });

  electronProcess.on('error', (err) => {
    flaskProcess.kill();
    process.exit(1);
  });
};

setTimeout(() => {
  checkFlaskServer();
}, 3000);

process.on('SIGINT', () => {
  flaskProcess.kill();
  process.exit();
});