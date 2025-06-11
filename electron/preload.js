const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('electronAPI', {
  // WebSocket related functions
  requestWsData: () => ipcRenderer.invoke('get-ws-data'),
  onWsData: (callback) => ipcRenderer.on('ws', callback),
  onWsError: (callback) => ipcRenderer.on('ws-error', callback),
  
  // General IPC
  sendMessage: (channel, data) => {
    // Whitelist channels for security
    const validChannels = ['ws', 'app-data-request'];
    if (validChannels.includes(channel)) {
      ipcRenderer.send(channel, data);
    }
  },
  
  // Listen for messages from main process
  onMessage: (channel, callback) => {
    const validChannels = ['ws', 'ws-error', 'app-data'];
    if (validChannels.includes(channel)) {
      ipcRenderer.on(channel, callback);
    }
  },
  
  // Remove listeners
  removeAllListeners: (channel) => {
    ipcRenderer.removeAllListeners(channel);
  }
});

// Prevent new window creation for security
window.addEventListener('DOMContentLoaded', () => {
  // Override window.open to prevent popup windows
  window.open = () => {
    console.warn('window.open is disabled for security reasons');
    return null;
  };
});