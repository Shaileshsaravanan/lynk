const { spawn } = require('child_process');
const { platform } = require('os');
const { join } = require('path');
const http = require('http');

const isWin = platform() === 'win32';

// Start Electron immediately
const electronProcess = spawn(
  isWin ? 'npx.cmd' : 'npx',
  ['electron', '.'],
  { 
    stdio: 'inherit',
    shell: true
  }
);

// Start Flask in the background
const flaskProcess = spawn(
  isWin ? 'python' : 'python3', 
  ['app.py'], 
  { 
    stdio: 'inherit',
    shell: true
  }
);

// Handle Electron process events
electronProcess.on('close', (code) => {
  console.log('Electron process closed with code:', code);
  flaskProcess.kill();
  process.exit();
});

electronProcess.on('error', (err) => {
  console.error('Electron process error:', err);
  flaskProcess.kill();
  process.exit(1);
});

// Handle Flask process events
flaskProcess.on('error', (err) => {
  console.error('Flask process error:', err);
});

flaskProcess.on('close', (code) => {
  console.log('Flask process closed with code:', code);
  // If Flask closes unexpectedly, kill Electron too
  if (code !== 0) {
    electronProcess.kill();
    process.exit(1);
  }
});

process.on('SIGINT', () => {
  flaskProcess.kill();
  process.exit();
});