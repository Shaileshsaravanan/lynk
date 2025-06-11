const { spawn } = require('child_process');
const { platform } = require('os');
const fs = require('fs');
const path = require('path');

/**
 * Production setup script for Lynk application
 * Handles Python environment setup and dependency installation
 */

const isWin = platform() === 'win32';
const pythonExecutable = isWin ? 'python' : 'python3';

function checkPythonInstallation() {
  return new Promise((resolve, reject) => {
    const python = spawn(pythonExecutable, ['--version'], { stdio: 'pipe' });
    
    python.on('close', (code) => {
      if (code === 0) {
        resolve(true);
      } else {
        reject(new Error('Python not found'));
      }
    });
    
    python.on('error', (error) => {
      reject(error);
    });
  });
}

function installPythonDependencies() {
  return new Promise((resolve, reject) => {
    const requirementsPath = path.join(__dirname, 'requirements.txt');
    
    if (!fs.existsSync(requirementsPath)) {
      console.log('No requirements.txt found, skipping dependency installation');
      resolve();
      return;
    }
    
    console.log('Installing Python dependencies...');
    const pip = spawn(pythonExecutable, ['-m', 'pip', 'install', '-r', requirementsPath], {
      stdio: 'inherit'
    });
    
    pip.on('close', (code) => {
      if (code === 0) {
        console.log('Python dependencies installed successfully');
        resolve();
      } else {
        reject(new Error(`pip install failed with code ${code}`));
      }
    });
    
    pip.on('error', (error) => {
      reject(error);
    });
  });
}

async function setup() {
  try {
    console.log('Checking Python installation...');
    await checkPythonInstallation();
    console.log('Python found');
    
    await installPythonDependencies();
    console.log('Setup completed successfully');
    
  } catch (error) {
    console.error('Setup failed:', error.message);
    console.error('Please ensure Python 3.10+ is installed and accessible via PATH');
    process.exit(1);
  }
}

if (require.main === module) {
  setup();
}

module.exports = { setup, checkPythonInstallation, installPythonDependencies };