const { app, BrowserWindow, session, shell, ipcMain, screen, Tray, Menu, nativeImage, globalShortcut } = require('electron');
const path = require('path');
const { spawn, execSync } = require('child_process');
const http = require('http');
const fs = require('fs');
const crypto = require('crypto');


// Generate high-entropy session authentication token
const authToken = crypto.randomBytes(32).toString('hex');
process.env.FRIDAY_AUTH_TOKEN = authToken;

// ── AUMID MUST be set before app.whenReady() ─────────────────────────────────
// This is the single source of truth for Windows taskbar grouping.
// The pinned shortcut's AppUserModelId MUST match this exactly.
const APP_USER_MODEL_ID = 'com.friday.assistant';
app.setAppUserModelId(APP_USER_MODEL_ID);

// ── Repair Windows Taskbar Pinned Shortcut ──────────────────────────────────
// Windows groups taskbar windows by matching the running exe's AUMID against
// the shortcut's AppUserModelId. If either doesn't match, a ghost second button
// appears. This function:
//   1. Finds FRIDAY.lnk in the TaskBar pins folder
//   2. Rewrites its Target to point to the CURRENT running exe
//   3. Sets its AppUserModelId to APP_USER_MODEL_ID
// This is idempotent — safe to call on every startup.
function updateAppShortcuts() {
  if (process.platform !== 'win32') return;

  const execPath = process.execPath; // actual running exe (packaged or electron.exe)

  // All Windows locations that can hold pinned taskbar shortcuts
  const taskbarPinDir = process.env.APPDATA
    ? path.join(process.env.APPDATA, 'Microsoft', 'Internet Explorer', 'Quick Launch', 'User Pinned', 'TaskBar')
    : null;

  const searchDirs = [
    taskbarPinDir,
    process.env.APPDATA ? path.join(process.env.APPDATA, 'Microsoft', 'Windows', 'Start Menu', 'Programs') : null,
    process.env.APPDATA ? path.join(process.env.APPDATA, 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup') : null,
    process.env.USERPROFILE ? path.join(process.env.USERPROFILE, 'Desktop') : null,
    process.env.PUBLIC ? path.join(process.env.PUBLIC, 'Desktop') : null,
  ].filter(Boolean);

  let repaired = 0;

  // Proactively create Start Menu shortcut if missing to ensure proper taskbar grouping
  const startMenuFridayPath = process.env.APPDATA
    ? path.join(process.env.APPDATA, 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'FRIDAY.lnk')
    : null;

  if (startMenuFridayPath && !fs.existsSync(startMenuFridayPath)) {
    try {
      shell.writeShortcutLink(startMenuFridayPath, 'create', {
        target: execPath,
        cwd: path.dirname(execPath),
        appUserModelId: APP_USER_MODEL_ID
      });
      logToFile(`[SHORTCUT] Created missing Start Menu shortcut at ${startMenuFridayPath}`);
      repaired++;
    } catch (err) {
      logToFile(`[SHORTCUT ERROR] Could not create Start Menu shortcut: ${err.message}`);
    }
  }

  searchDirs.forEach(dir => {
    if (!fs.existsSync(dir)) return;
    const files = fs.readdirSync(dir).filter(f => path.extname(f).toLowerCase() === '.lnk');

    files.forEach(file => {
      const shortcutPath = path.join(dir, file);
      try {
        const details = shell.readShortcutLink(shortcutPath);
        const targetLower = (details.target || '').toLowerCase();
        const execLower = execPath.toLowerCase();
        const isFridayShortcut =
          file.toLowerCase().includes('friday') ||
          targetLower.includes('friday');

        if (!isFridayShortcut) return;

        const needsTargetFix = targetLower !== execLower;
        const needsAumidFix  = details.appUserModelId !== APP_USER_MODEL_ID;

        if (needsTargetFix || needsAumidFix) {
          const updatePayload = { appUserModelId: APP_USER_MODEL_ID };
          if (needsTargetFix) {
            updatePayload.target = execPath;
            updatePayload.cwd = path.dirname(execPath);
          }
          shell.writeShortcutLink(shortcutPath, 'update', updatePayload);
          logToFile(
            `[SHORTCUT] Repaired ${path.basename(shortcutPath)}` +
            (needsTargetFix ? ` | target -> ${execPath}` : '') +
            (needsAumidFix  ? ` | AUMID  -> ${APP_USER_MODEL_ID}` : '')
          );
          repaired++;
        } else {
          logToFile(`[SHORTCUT] ${path.basename(shortcutPath)} already correct — no update needed.`);
        }
      } catch (err) {
        logToFile(`[SHORTCUT ERROR] Could not read/write ${shortcutPath}: ${err.message}`);
      }
    });
  });

  if (repaired > 0) {
    logToFile(`[SHORTCUT] ${repaired} shortcut(s) repaired/created for taskbar grouping.`);
  }
}

// ── Single Instance Lock ────────────────────────────────────────────────────
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  console.log('[STARTUP] Another instance of FRIDAY is already running. Exiting.');
  app.quit();
  process.exit(0);
}

let notchWindow = null;
let tray = null;
let isListening = false;
let lastHotkeyFireTime = 0;
let backendProcess = null;
let isQuitting = false;
let isBackendReady = false;

// ── Watchdog State Variables ────────────────────────────────────────────────
let pingInterval = null;
let missedPongs = 0;
let isReconnecting = false;
let restartCount = 0;
let lastRestartTime = 0;

// ── App Root Caching & Log system events directly to the runtime log file ───
let cachedPaths = null;
function getAppPaths() {
  if (cachedPaths) return cachedPaths;

  let currentDir = app.isPackaged 
    ? path.dirname(process.execPath)
    : __dirname;

  let foundPython = null;
  let foundBackend = null;

  // Search up to 5 levels high to locate the virtual env and backend root
  for (let i = 0; i < 6; i++) {
    const possibleVenvPy = path.join(currentDir, '.venv', 'Scripts', 'python.exe');
    const possibleBackend = path.join(currentDir, 'backend');

    if (!foundPython && fs.existsSync(possibleVenvPy)) {
      foundPython = possibleVenvPy;
    }
    if (!foundBackend && fs.existsSync(possibleBackend)) {
      foundBackend = possibleBackend;
    }

    if (foundPython && foundBackend) {
      break;
    }

    const parent = path.dirname(currentDir);
    if (parent === currentDir) break; // Reached root
    currentDir = parent;
  }

  // If not found in parent traversal, try default absolute and relative fallbacks
  if (!foundPython) {
    const rootVenvPy = 'C:\\FRIDAY\\.venv\\Scripts\\python.exe';
    if (fs.existsSync(rootVenvPy)) {
      foundPython = rootVenvPy;
    } else {
      foundPython = 'python.exe'; // fallback to path
    }
  }
  if (!foundBackend) {
    const rootBackend = 'C:\\FRIDAY\\backend';
    if (fs.existsSync(rootBackend)) {
      foundBackend = rootBackend;
    } else {
      foundBackend = path.join(__dirname, '..', '..', 'backend'); // best guess
    }
  }

  cachedPaths = { pythonExe: foundPython, backendPath: foundBackend };
  return cachedPaths;
}

// ── Active Timeout Pruning Garbage Collector ──────────────────────────────
let activeTimeouts = [];
function safeSetTimeout(fn, delay) {
  const id = setTimeout(() => {
    activeTimeouts = activeTimeouts.filter(t => t !== id);
    fn();
  }, delay);
  activeTimeouts.push(id);
  return id;
}

function clearAllTimeouts() {
  for (const id of activeTimeouts) {
    clearTimeout(id);
  }
  activeTimeouts = [];
}

function readNotchConfig() {
  try {
    const configPath = path.join(app.getPath('userData'), 'notch_config.json');
    if (fs.existsSync(configPath)) {
      const data = fs.readFileSync(configPath, 'utf8');
      return JSON.parse(data);
    }
  } catch (err) {
    // Fail silently
  }
  return { notchVisible: true };
}

function writeNotchConfig(config) {
  try {
    const configPath = path.join(app.getPath('userData'), 'notch_config.json');
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2), 'utf8');
  } catch (err) {
    // Fail silently
  }
}

function logToFile(message) {
  if (isQuitting) return; // Immediate teardown guard to prevent destroyed exceptions
  const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
  const logMessage = `[ELECTRON ${timestamp}] ${message}\n`;
  try {
    const { backendPath } = getAppPaths();
    const logPath = path.join(backendPath, 'friday_runtime.log');
    fs.appendFileSync(logPath, logMessage);
  } catch (e) {
    // Fail silently if log path isn't writable yet
  }
}

// ── Kill an entire Windows process tree by PID ──────────────────────────────
function killProcessTree(pid) {
  if (!pid) return;
  try {
    execSync(`taskkill /F /T /PID ${pid}`, { stdio: 'ignore' });
    logToFile(`[SHUTDOWN] Killed process tree for PID ${pid}`);
  } catch (e) {
    logToFile(`[SHUTDOWN] taskkill returned: ${e.message}`);
  }
}

// ── Kill any leftover uvicorn / python processes on port 8001 ───────────────
function killPortProcess(port) {
  try {
    const result = execSync(`netstat -ano | findstr :${port}`, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] });
    const lines = result.split('\n');
    const pids = new Set();
    for (const line of lines) {
      const parts = line.trim().split(/\s+/);
      const lastPart = parts[parts.length - 1];
      if (lastPart && /^\d+$/.test(lastPart) && lastPart !== '0') {
        pids.add(lastPart);
      }
    }
    for (const pid of pids) {
      try {
        execSync(`taskkill /F /T /PID ${pid}`, { stdio: 'ignore' });
        logToFile(`[CLEANUP] Killed PID ${pid} dangling on port ${port}`);
      } catch (e) {
        // already dead
      }
    }
  } catch (e) {
    // netstat found nothing — port free
  }
}

function startBackend() {
  if (isQuitting) return;

  const { pythonExe, backendPath } = getAppPaths();

  let isPacked = app.isPackaged;

  logToFile(`[STARTUP] isPacked     = ${isPacked}`);
  logToFile(`[STARTUP] backendPath  = ${backendPath}`);
  logToFile(`[STARTUP] pythonExe    = ${pythonExe}`);
  logToFile(`[STARTUP] backendExist = ${fs.existsSync(backendPath)}`);
  logToFile(`[STARTUP] pythonExists = ${fs.existsSync(pythonExe)}`);

  if (!fs.existsSync(pythonExe)) {
    logToFile(`[CRITICAL] Python executable not found at ${pythonExe}! Backend will fail to start.`);
    return;
  }

  backendProcess = spawn(pythonExe, ['-m', 'uvicorn', 'api.server:app', '--host', '127.0.0.1', '--port', '8001'], {
    cwd: backendPath,
    shell: false,
    detached: false,
    env: { ...process.env, PYTHONUNBUFFERED: '1' }
  });

  backendProcess.stdout.on('data', (data) => {
    logToFile(`[BACKEND STDOUT] ${data.toString().trim()}`);
  });

  backendProcess.stderr.on('data', (data) => {
    logToFile(`[BACKEND STDERR] ${data.toString().trim()}`);
  });

  backendProcess.on('exit', (code) => {
    logToFile(`[BACKEND EXIT] Process exited with code ${code}`);
    backendProcess = null;
  });
}



function createNotchWindow() {
  if (isQuitting || notchWindow) return;

  const primaryDisplay = screen.getPrimaryDisplay();
  const { width: screenWidth } = primaryDisplay.bounds;
  const paddingX = 16;
  const paddingY = 16;
  const initialVisibleWidth = 120;
  const initialVisibleHeight = 26;
  
  const initialWidth = initialVisibleWidth + paddingX * 2;
  const initialHeight = initialVisibleHeight + paddingY * 2;
  const x = Math.round((screenWidth - initialWidth) / 2);
  const y = 8 - paddingY;

  notchWindow = new BrowserWindow({
    width: initialWidth,
    height: initialHeight,
    x: x,
    y: y,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: false,
    skipTaskbar: true,
    focusable: false,
    hasShadow: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.cjs'),
      autoplayPolicy: 'no-user-gesture-required'
    }
  });

  notchWindow.setAlwaysOnTop(true, 'screen-saver');
  notchWindow.setVisibleOnAllWorkspaces(true);
  notchWindow.setIgnoreMouseEvents(true, { forward: true });

  // Capture all notch console messages
  notchWindow.webContents.on('console-message', (event, level, message, line, sourceId) => {
    if (isQuitting || !notchWindow || notchWindow.isDestroyed()) return;
    const levelStr = ['DEBUG', 'INFO', 'WARN', 'ERROR'][level] || 'LOG';
    logToFile(`[NOTCH CONSOLE] [${levelStr}] ${message}`);
  });

  const isDev = process.env.NODE_ENV === 'development';

  if (isDev) {
    waitForVite('localhost', 5173, 30, () => {
      if (isQuitting || !notchWindow || notchWindow.isDestroyed()) return;
      notchWindow.loadURL('http://localhost:5173/?token=' + process.env.FRIDAY_AUTH_TOKEN);
    });
  } else {
    const notchPath = path.join(__dirname, '..', 'dist', 'index.html');
    logToFile(`[NOTCH] Loading index.html from: ${notchPath} (exists=${fs.existsSync(notchPath)})`);
    if (isQuitting || !notchWindow || notchWindow.isDestroyed()) return;
    notchWindow.loadFile(notchPath, { query: { token: process.env.FRIDAY_AUTH_TOKEN } });
  }

  notchWindow.on('closed', () => {
    notchWindow = null;
  });
}

function resizeNotch(visibleWidth, visibleHeight) {
  if (!notchWindow || notchWindow.isDestroyed()) return;
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width: screenWidth } = primaryDisplay.bounds;

  const paddingX = 16;
  const paddingY = 16;

  const windowWidth = visibleWidth + paddingX * 2;
  const windowHeight = visibleHeight + paddingY * 2;

  const x = Math.round((screenWidth - windowWidth) / 2);
  const y = 8 - paddingY;

  notchWindow.setBounds({
    x: x,
    y: y,
    width: windowWidth,
    height: windowHeight
  }, true);
}

function createTray() {
  if (tray) return;

  let trayIcon;
  const iconPath = path.join(__dirname, '../public/tray-icon.png');
  if (fs.existsSync(iconPath)) {
    trayIcon = nativeImage.createFromPath(iconPath);
    logToFile(`[TRAY] Loaded icon from: ${iconPath}`);
  } else {
    // Fallback: valid 16x16 transparent PNG as base64 — Windows requires a real icon for system tray
    const TRANSPARENT_PNG =
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9h' +
      'AAAAC0lEQVQ4y2NgAAIABQAANjN9GQAAAABJRkJggg==';
    trayIcon = nativeImage.createFromDataURL(TRANSPARENT_PNG);
    logToFile('[TRAY WARNING] tray-icon.png not found — using transparent PNG fallback');
  }

  try {
    tray = new Tray(trayIcon);
  } catch (err) {
    logToFile(`[TRAY ERROR] new Tray() threw: ${err.message} — skipping tray, app will continue`);
    return;
  }

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Quit FRIDAY',
      click: () => {
        performShutdown();
      }
    }
  ]);

  tray.setToolTip('FRIDAY AI Assistant');
  tray.setContextMenu(contextMenu);
}

function setupGlobalShortcut() {
  const shortcutString = 'Ctrl+Alt+Z';
  logToFile(`[HOTKEY] Attempting to register global shortcut: ${shortcutString}`);

  try {
    // Unregister any prior attempt before re-registering
    globalShortcut.unregister(shortcutString);

    const registered = globalShortcut.register(shortcutString, () => {
      const now = Date.now();
      const gap = now - lastHotkeyFireTime;
      lastHotkeyFireTime = now;
      if (gap < 250) {
        return;
      }

      logToFile(`[HOTKEY] *** SHORTCUT FIRED: ${shortcutString} ***`);

      if (!isBackendReady) {
        logToFile('[HOTKEY] Backend is not ready yet — ignoring hotkey press during boot');
        return;
      }

      if (!notchWindow || notchWindow.isDestroyed()) {
        logToFile('[HOTKEY] notchWindow is null or destroyed — cannot send IPC');
        return;
      }

      if (isListening) {
        logToFile('[HOTKEY] Already listening — ignoring repeat press trigger');
        return;
      }

      // Key pressed fresh — activate mic
      logToFile('[HOTKEY] Sending hotkey-mic-on to notch renderer');
      notchWindow.webContents.send('hotkey-mic-on');
      isListening = true;
    });

    if (registered) {
      logToFile(`[HOTKEY] SUCCESS: Global shortcut registered: ${shortcutString}`);
    } else {
      logToFile(`[HOTKEY] FAILED: globalShortcut.register returned false for '${shortcutString}' — combo may be taken by another app`);
    }
  } catch (err) {
    logToFile(`[HOTKEY CRITICAL ERROR] Global shortcut '${shortcutString}' threw registration exception: ${err.message}`);
  }
}

function setupBackendWatchdog() {
  if (isQuitting) return;

  if (pingInterval) {
    clearInterval(pingInterval);
    pingInterval = null;
  }

  logToFile('[WATCHDOG] Initializing HTTP health check watchdog...');
  missedPongs = 0;

  pingInterval = setInterval(() => {
    if (isQuitting) {
      if (pingInterval) {
        clearInterval(pingInterval);
        pingInterval = null;
      }
      return;
    }

    const req = http.request({
      host: '127.0.0.1',
      port: 8001,
      path: '/api/health',
      method: 'GET',
      timeout: 2000
    }, (res) => {
      if (isQuitting) return;
      if (res.statusCode === 200) {
        missedPongs = 0;
      } else {
        logToFile(`[WATCHDOG WARNING] Health check returned status: ${res.statusCode}`);
        missedPongs++;
        if (missedPongs >= 6) {
          logToFile(`[WATCHDOG CRITICAL] 6 consecutive health checks failed!`);
          handleBackendFailure();
        }
      }
    });

    req.on('error', (err) => {
      if (isQuitting) return;
      logToFile(`[WATCHDOG ERROR] Health check failed: ${err.message}`);
      missedPongs++;
      if (missedPongs >= 6) {
        logToFile(`[WATCHDOG CRITICAL] 6 consecutive health checks failed!`);
        handleBackendFailure();
      }
    });

    req.on('timeout', () => {
      req.destroy();
    });

    req.end();
  }, 5000);
}

function handleBackendFailure() {
  if (isQuitting) return;

  logToFile('[WATCHDOG CRITICAL] Backend process hang or crash detected!');

  const now = Date.now();
  if (now - lastRestartTime < 60000) {
    restartCount++;
  } else {
    restartCount = 1;
  }
  lastRestartTime = now;

  if (restartCount > 5) {
    logToFile('[WATCHDOG DEGRADED] Too many backend restarts in a short time. Switching to degraded offline mode to preserve Electron UI.');
    if (pingInterval) {
      clearInterval(pingInterval);
      pingInterval = null;
    }
    if (notchWindow && !notchWindow.isDestroyed()) {
      try {
        notchWindow.webContents.send('backend-status', { status: 'degraded', reason: 'too_many_restarts' });
      } catch (e) {
        // fail silently if ipc not ready
      }
    }
    return;
  }

  if (pingInterval) {
    clearInterval(pingInterval);
    pingInterval = null;
  }

  logToFile('[WATCHDOG] Restarting backend...');
  
  if (backendProcess && backendProcess.pid) {
    killProcessTree(backendProcess.pid);
    backendProcess = null;
  }
  
  killPortProcess(8001);
  startBackend();

  safeSetTimeout(() => {
    if (isQuitting) return;
    waitForBackend('127.0.0.1', 8001, 180, () => {
      if (isQuitting) return;
      setupBackendWatchdog();
    });
  }, 2000);
}

function performShutdown() {
  if (isQuitting) return;
  isQuitting = true;
  clearAllTimeouts(); // Cleanly prune all active pending setTimeout tasks
  logToFile('[SHUTDOWN] Initiating full process teardown...');

  // Unregister all global keyboard shortcuts
  try {
    globalShortcut.unregisterAll();
    logToFile('[SHUTDOWN] Unregistered all global shortcuts.');
  } catch (err) {
    logToFile(`[SHUTDOWN WARNING] Failed to unregister shortcuts: ${err.message}`);
  }

  if (pingInterval) {
    clearInterval(pingInterval);
    pingInterval = null;
  }

  if (backendProcess && backendProcess.pid) {
    logToFile(`[SHUTDOWN] Killing backend process tree (PID ${backendProcess.pid})`);
    killProcessTree(backendProcess.pid);
    backendProcess = null;
  }

  killPortProcess(8001);
  logToFile('[SHUTDOWN] All backend processes terminated. Quitting Electron.');

  // Cleanly dismiss window references


  if (notchWindow) {
    if (!notchWindow.isDestroyed()) {
      notchWindow.destroy();
    }
    notchWindow = null;
  }

  if (tray) {
    try {
      tray.destroy();
    } catch (e) {}
    tray = null;
  }

  app.quit();
}

function waitForVite(host, port, retriesLeft, onReady) {
  if (isQuitting) return;

  const req = http.request({ host, port, path: '/', method: 'GET', timeout: 1000 }, () => {
    if (isQuitting) return;
    onReady();
  });
  req.on('error', () => {
    if (isQuitting) return;
    if (retriesLeft <= 0) {
      console.error('Vite dev server never started. Run "npm run dev" in the frontend folder.');
      return;
    }
    safeSetTimeout(() => {
      if (isQuitting) return;
      waitForVite(host, port, retriesLeft - 1, onReady);
    }, 1000);
  });
  req.on('timeout', () => req.destroy());
  req.end();
}

function waitForBackend(host, port, retriesLeft, onReady) {
  if (isQuitting) return;

  const req = http.request({ host, port, path: '/api/health', method: 'GET', timeout: 1500 }, (res) => {
    if (isQuitting) return;
    logToFile(`[STARTUP] Backend health check: HTTP ${res.statusCode}`);
    onReady();
  });
  req.on('error', () => {
    if (isQuitting) return;
    if (retriesLeft <= 0) {
      logToFile('[STARTUP] Backend never started after max retries. Opening window anyway...');
      onReady();
      return;
    }
    safeSetTimeout(() => {
      if (isQuitting) return;
      waitForBackend(host, port, retriesLeft - 1, onReady);
    }, 1000);
  });
  req.on('timeout', () => { req.destroy(); });
  req.end();
}

ipcMain.on('set-notch-state', (event, { state, connected }) => {
  if (isQuitting) return;
  if (!connected) {
    isListening = false;
    resizeNotch(120, 26);
    return;
  }
  
  // Keep isListening synced with FSM state
  if (state === 'IDLE' || state === 'REFLECTING') {
    isListening = false;
    resizeNotch(100, 26);
  } else {
    if (state === 'LISTENING' || state === 'PERCEIVING') {
      isListening = true;
    }
    resizeNotch(120, 26);
  }
});

ipcMain.on('set-ignore-mouse-events', (event, { ignore, forward }) => {
  if (isQuitting || !notchWindow || notchWindow.isDestroyed()) return;
  if (forward) {
    notchWindow.setIgnoreMouseEvents(ignore, { forward: true });
  } else {
    notchWindow.setIgnoreMouseEvents(ignore);
  }
});



ipcMain.on('toggle-notch-visibility', (event, { visible }) => {
  if (isQuitting) return;
  logToFile(`[IPC] Received toggle-notch-visibility: ${visible}`);
  
  const config = readNotchConfig();
  config.notchVisible = visible;
  writeNotchConfig(config);

  if (visible) {
    if (!notchWindow) {
      createNotchWindow();
    } else {
      notchWindow.show();
    }
  } else {
    if (notchWindow) {
      notchWindow.hide();
    }
  }
});

ipcMain.handle('get-notch-config', () => {
  if (isQuitting) return { notchVisible: true };
  return readNotchConfig();
});

ipcMain.handle('is-backend-ready', () => {
  if (isQuitting) return false;
  return isBackendReady;
});

ipcMain.on('show-notch-context-menu', () => {
  if (isQuitting) return;
  logToFile('[IPC] Received show-notch-context-menu request');
  const menu = Menu.buildFromTemplate([
    {
      label: 'Restart',
      click: () => {
        logToFile('[CONTEXT MENU] Restart selected — relaunching app');
        app.relaunch();
        performShutdown();
      }
    },
    {
      label: 'End',
      click: () => {
        logToFile('[CONTEXT MENU] End selected — shutting down');
        performShutdown();
      }
    }
  ]);
  menu.popup({ window: notchWindow || undefined });
});

app.on('second-instance', (event, commandLine, workingDirectory) => {
  logToFile('[STARTUP] Second instance launched. Showing notch window...');
  if (notchWindow && !notchWindow.isDestroyed()) {
    notchWindow.show();
  }
});

app.whenReady().then(() => {
  logToFile('[STARTUP] Electron app ready. Cleaning up port 8001 to prevent stale backends...');
  killPortProcess(8001);
  
  // Update Windows taskbar pinned shortcuts to prevent separate taskbar icons
  updateAppShortcuts();

  // Idempotent login item setting to ensure autostart on boot
  try {
    app.setLoginItemSettings({ openAtLogin: true, path: app.getPath('exe') });
    logToFile('[STARTUP] OpenAtLogin setting applied successfully.');
  } catch (err) {
    logToFile(`[STARTUP WARNING] Failed to set OpenAtLogin setting: ${err.message}`);
  }

  // Create and display the notch window IMMEDIATELY on boot
  const config = readNotchConfig();
  if (config.notchVisible !== false) {
    logToFile('[STARTUP] Creating notch window immediately on boot...');
    createNotchWindow();
  } else {
    logToFile('[STARTUP] Notch is disabled in settings. Skipping window creation.');
  }
  
  logToFile('[STARTUP] Port cleaned up. Waiting 600ms for OS sockets and PortAudio endpoints to release...');
  safeSetTimeout(() => {
    if (isQuitting) return;
    logToFile('[STARTUP] Starting backend server...');
    startBackend();
    
    logToFile('[STARTUP] Waiting for backend to be ready...');
    waitForBackend('127.0.0.1', 8001, 180, () => {
      if (isQuitting) return;
      logToFile('[STARTUP] Backend ready. Initializing Hotkey, Watchdog, and sending backend-ready event...');
      
      isBackendReady = true;

      if (notchWindow && !notchWindow.isDestroyed()) {
        logToFile('[STARTUP] Sending backend-ready event to notch window.');
        notchWindow.webContents.send('backend-ready');
      } else {
        logToFile('[STARTUP WARNING] Notch window not available to receive backend-ready event.');
      }
      
      setupGlobalShortcut();
      setupBackendWatchdog();
    });
  }, 600);

  app.on('activate', () => {
    const config = readNotchConfig();
    if (config.notchVisible !== false && (!notchWindow || notchWindow.isDestroyed())) {
      createNotchWindow();
    }
  });
});

app.on('window-all-closed', () => {
  // Intentionally empty - app stays alive via the notch window only
});

app.on('before-quit', () => {
  if (!isQuitting) {
    performShutdown();
  }
});
