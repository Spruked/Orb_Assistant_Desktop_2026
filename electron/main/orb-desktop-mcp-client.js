const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const readline = require('readline');
const { EventEmitter } = require('events');

const defaultRoot = path.resolve(__dirname, '..', '..', 'mcp', 'orb_desktop_mcp');
const mcpRoot = path.resolve(process.env.ORB_DESKTOP_MCP_ROOT || defaultRoot);
const mcpScript = path.resolve(process.env.ORB_DESKTOP_MCP_SCRIPT || path.join(mcpRoot, 'orb_mcp_server.py'));
const requestTimeoutMs = Number(process.env.ORB_DESKTOP_MCP_TIMEOUT_MS || 120000);
const startTimeoutMs = Number(process.env.ORB_DESKTOP_MCP_START_TIMEOUT_MS || 15000);
const events = new EventEmitter();
const DESKTOP_AUTHORITY_TOOLS = new Set([
  'orb_control',
  'orb_click',
  'orb_double_click',
  'orb_scroll',
  'orb_type',
  'orb_hotkey',
  'orb_move_mouse',
  'orb_drag',
  'orb_screenshot',
  'orb_open_app',
  'orb_browser_open',
  'orb_browser_navigate',
  'orb_browser_click',
  'orb_browser_type',
  'orb_browser_scroll',
  'orb_browser_screenshot',
  'orb_clipboard_read',
  'orb_clipboard_write',
  'orb_list_windows',
  'orb_get_display_size',
  'orb_wait',
  'orb_snapshot',
]);

let child = null;
let initialized = false;
let initializing = null;
let nextId = 1;
let stdoutReady = false;
let desktopActionsEnabled = String(process.env.ORB_DESKTOP_MCP_ACTIONS_ENABLED || '0').trim() === '1';
const pending = new Map();
const stderrRing = [];

function resolvePythonPath() {
  if (process.env.ORB_DESKTOP_MCP_PYTHON) {
    return process.env.ORB_DESKTOP_MCP_PYTHON;
  }
  if (process.env.ORB_PYTHON_PATH) {
    return process.env.ORB_PYTHON_PATH;
  }
  if (process.platform === 'win32') {
    const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local');
    const candidates = [
      'R:\\R_Drive_Substrate\\Services\\qwen_tts_312\\Scripts\\python.exe',
      path.join(localAppData, 'Programs', 'Python', 'Python312', 'python.exe'),
      path.join(localAppData, 'Programs', 'Python', 'Python311', 'python.exe'),
      path.join(localAppData, 'Programs', 'Python', 'Python313', 'python.exe'),
    ];
    const match = candidates.find((candidate) => fs.existsSync(candidate));
    if (match) {
      return match;
    }
  }
  return process.platform === 'linux' ? '/usr/bin/python3' : 'python';
}

function getDesktopMcpStatus() {
  return {
    configured: fs.existsSync(mcpScript),
    running: Boolean(child && !child.killed),
    initialized,
    pid: child?.pid || null,
    root: mcpRoot,
    script: mcpScript,
    python: resolvePythonPath(),
    stdout_ready: stdoutReady,
    desktop_actions_enabled: desktopActionsEnabled,
    pending_requests: pending.size,
    stderr_tail: stderrRing.slice(-8),
  };
}

function emit(type, data = {}) {
  events.emit('event', { type, data, status: getDesktopMcpStatus(), timestamp: new Date().toISOString() });
}

function rejectPending(error) {
  for (const [id, request] of pending.entries()) {
    clearTimeout(request.timeoutId);
    request.reject(error);
    pending.delete(id);
  }
}

function handleStdoutLine(line) {
  const text = String(line || '').trim();
  if (!text) {
    return;
  }
  stdoutReady = true;

  let payload;
  try {
    payload = JSON.parse(text);
  } catch (error) {
    emit('stdout_parse_error', { text, error: error?.message || String(error) });
    return;
  }

  if (payload.id !== undefined && pending.has(payload.id)) {
    const request = pending.get(payload.id);
    clearTimeout(request.timeoutId);
    pending.delete(payload.id);
    if (payload.error) {
      request.reject(new Error(payload.error.message || JSON.stringify(payload.error)));
      return;
    }
    request.resolve(payload.result);
    return;
  }

  emit('notification', payload);
}

function handleStderrLine(line) {
  const text = String(line || '').trim();
  if (!text) {
    return;
  }
  stderrRing.push(text);
  if (stderrRing.length > 40) {
    stderrRing.shift();
  }
  emit('stderr', { text });
}

function spawnServer() {
  if (!fs.existsSync(mcpScript)) {
    throw new Error(`ORB desktop MCP server not found: ${mcpScript}`);
  }
  if (child && !child.killed) {
    return child;
  }

  child = spawn(resolvePythonPath(), ['-u', mcpScript], {
    cwd: mcpRoot,
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      ORB_DESKTOP_MCP_ROOT: mcpRoot,
    },
  });
  initialized = false;
  stdoutReady = false;

  readline.createInterface({ input: child.stdout }).on('line', handleStdoutLine);
  readline.createInterface({ input: child.stderr }).on('line', handleStderrLine);

  child.on('error', (error) => {
    emit('process_error', { error: error?.message || String(error) });
    rejectPending(error);
  });
  child.on('exit', (code, signal) => {
    emit('process_exit', { code, signal });
    initialized = false;
    initializing = null;
    rejectPending(new Error(`ORB desktop MCP exited (${code ?? signal ?? 'unknown'})`));
    child = null;
  });

  emit('process_started', { pid: child.pid });
  return child;
}

function request(method, params = {}, timeoutMs = requestTimeoutMs) {
  spawnServer();
  const id = nextId++;
  const payload = { jsonrpc: '2.0', id, method, params };

  return new Promise((resolve, reject) => {
    const timeoutId = setTimeout(() => {
      pending.delete(id);
      reject(new Error(`Timed out waiting for MCP ${method}`));
    }, timeoutMs);

    pending.set(id, { resolve, reject, timeoutId, method });
    try {
      child.stdin.write(`${JSON.stringify(payload)}\n`);
    } catch (error) {
      clearTimeout(timeoutId);
      pending.delete(id);
      reject(error);
    }
  });
}

function notify(method, params = {}) {
  spawnServer();
  child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', method, params })}\n`);
}

async function startDesktopMcp() {
  if (initialized) {
    return getDesktopMcpStatus();
  }
  if (initializing) {
    await initializing;
    return getDesktopMcpStatus();
  }

  initializing = (async () => {
    const result = await request(
      'initialize',
      {
        protocolVersion: '2024-11-05',
        capabilities: {},
        clientInfo: { name: 'orb-assistant-desktop', version: '1.0.0' },
      },
      startTimeoutMs
    );
    initialized = true;
    notify('notifications/initialized');
    emit('initialized', result);
    return result;
  })();

  try {
    await initializing;
    return getDesktopMcpStatus();
  } finally {
    initializing = null;
  }
}

async function listDesktopMcpTools() {
  await startDesktopMcp();
  return request('tools/list', {});
}

async function callDesktopMcpTool(name, args = {}) {
  if (!name || typeof name !== 'string') {
    throw new Error('MCP tool name is required');
  }
  if (DESKTOP_AUTHORITY_TOOLS.has(name) && !desktopActionsEnabled) {
    return {
      content: [{
        type: 'text',
        text: `Desktop MCP actions are disabled in DockStation. Enable Desktop Actions to call ${name}.`,
      }],
      isError: true,
      blocked: true,
      reason: 'desktop_actions_disabled',
      tool: name,
    };
  }
  await startDesktopMcp();
  return request('tools/call', { name, arguments: args || {} });
}

function parseToolTextJson(result) {
  const text = (result?.content || []).find((item) => item?.type === 'text')?.text;
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch (_error) {
    return { raw: text };
  }
}

async function reviewDesktopCognition(command, context = {}) {
  const trimmed = String(command || '').trim();
  if (!trimmed) {
    return { ok: false, error: 'empty_command' };
  }
  try {
    await startDesktopMcp();
    const result = await request(
      'tools/call',
      {
        name: 'orb_cognition_review',
        arguments: {
          command: trimmed,
          source: 'orb_assistant_desktop',
          context: context && typeof context === 'object' ? context : {},
        },
      },
      Number(process.env.ORB_DESKTOP_MCP_REVIEW_TIMEOUT_MS || 8000)
    );
    return {
      ok: !result?.isError,
      tool: 'orb_cognition_review',
      review: parseToolTextJson(result),
      mcp_status: getDesktopMcpStatus(),
    };
  } catch (error) {
    return {
      ok: false,
      tool: 'orb_cognition_review',
      error: error?.message || String(error),
      mcp_status: getDesktopMcpStatus(),
    };
  }
}

function stopDesktopMcp() {
  if (!child || child.killed) {
    return false;
  }
  rejectPending(new Error('ORB desktop MCP stopped'));
  child.kill();
  child = null;
  initialized = false;
  initializing = null;
  return true;
}

function setDesktopMcpActionsEnabled(enabled) {
  desktopActionsEnabled = Boolean(enabled);
  emit('desktop_actions_toggle', { enabled: desktopActionsEnabled });
  return getDesktopMcpStatus();
}

function onDesktopMcpEvent(handler) {
  events.on('event', handler);
}

module.exports = {
  startDesktopMcp,
  listDesktopMcpTools,
  callDesktopMcpTool,
  reviewDesktopCognition,
  getDesktopMcpStatus,
  setDesktopMcpActionsEnabled,
  stopDesktopMcp,
  onDesktopMcpEvent,
};
