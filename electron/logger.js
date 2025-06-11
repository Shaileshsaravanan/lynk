const fs = require('fs');
const path = require('path');
const { app } = require('electron');

/**
 * Production logging utility for Lynk application
 */

class Logger {
  constructor() {
    this.logDir = app ? path.join(app.getPath('userData'), 'logs') : path.join(__dirname, 'logs');
    this.ensureLogDirectory();
  }

  ensureLogDirectory() {
    try {
      if (!fs.existsSync(this.logDir)) {
        fs.mkdirSync(this.logDir, { recursive: true });
      }
    } catch (error) {
      console.error('Failed to create log directory:', error);
    }
  }

  getLogFilePath(type = 'main') {
    const date = new Date().toISOString().split('T')[0];
    return path.join(this.logDir, `${type}-${date}.log`);
  }

  formatMessage(level, message, data = null) {
    const timestamp = new Date().toISOString();
    const dataStr = data ? ` | Data: ${JSON.stringify(data)}` : '';
    return `[${timestamp}] [${level.toUpperCase()}] ${message}${dataStr}\n`;
  }

  writeLog(level, message, data = null, type = 'main') {
    try {
      const logPath = this.getLogFilePath(type);
      const formattedMessage = this.formatMessage(level, message, data);
      
      // Also log to console in development
      if (process.env.NODE_ENV !== 'production') {
        console.log(formattedMessage.trim());
      }
      
      fs.appendFileSync(logPath, formattedMessage);
    } catch (error) {
      console.error('Failed to write log:', error);
    }
  }

  info(message, data = null, type = 'main') {
    this.writeLog('info', message, data, type);
  }

  warn(message, data = null, type = 'main') {
    this.writeLog('warn', message, data, type);
  }

  error(message, data = null, type = 'main') {
    this.writeLog('error', message, data, type);
  }

  debug(message, data = null, type = 'main') {
    if (process.env.NODE_ENV !== 'production') {
      this.writeLog('debug', message, data, type);
    }
  }

  // Clean up old log files (keep last 7 days)
  cleanupOldLogs() {
    try {
      const files = fs.readdirSync(this.logDir);
      const cutoffDate = new Date();
      cutoffDate.setDate(cutoffDate.getDate() - 7);

      files.forEach(file => {
        const filePath = path.join(this.logDir, file);
        const stats = fs.statSync(filePath);
        
        if (stats.mtime < cutoffDate) {
          fs.unlinkSync(filePath);
          this.info(`Cleaned up old log file: ${file}`);
        }
      });
    } catch (error) {
      this.error('Failed to cleanup old logs', { error: error.message });
    }
  }
}

// Create singleton instance
const logger = new Logger();

// Cleanup old logs on startup
logger.cleanupOldLogs();

module.exports = logger;