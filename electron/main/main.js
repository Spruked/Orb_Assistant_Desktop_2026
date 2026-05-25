const { app, BrowserWindow, ipcMain, screen, protocol, Tray, Menu, nativeImage, shell, globalShortcut } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');
const https = require('https');
const { spawn } = require('child_process');
const { recordInteraction, recordObservation } = require('./legacy-observer');
const {
  startOrb,
  sendCursorMove,
  queryOrb,
  researchOrb,
  speakOrb,
  listenOnce,
  setListening,
  getOrbStatus,
  setOrbState,
  serviceOrb,
  shutdownOrb,
  onOrbMessage,
} = require('./orb-bridge');

const instanceId = process.env.ORB_INSTANCE_ID || 'wsl';
const productName = process.env.ORB_PRODUCT_NAME || `Orb Assistant ${instanceId.toUpperCase()}`;
const appId = process.env.ORB_APP_ID || `com.orbassistant.${instanceId}`;
const localStateDirName =
  process.env.ORB_USER_DATA_DIR ||
  process.env.ORB_LOCAL_STATE_DIR ||
  (instanceId === 'wsl' ? '.orb-assistant' : `.orb-assistant-${instanceId}`);
const userDataPath = path.resolve(__dirname, '..', localStateDirName);
const singleInstanceEnabled = process.env.ORB_SINGLE_INSTANCE !== '0';

app.setName(productName);
app.setPath('userData', userDataPath);
if (process.platform === 'win32' && app.setAppUserModelId) {
  app.setAppUserModelId(appId);
}

function resolvePythonPath() {
  if (process.env.ORB_PYTHON_PATH) {
    return process.env.ORB_PYTHON_PATH;
  }
  if (process.platform === 'win32') {
    const localAppData = process.env.LOCALAPPDATA || path.join(process.env.USERPROFILE || '', 'AppData', 'Local');
    const candidates = [
      path.join(localAppData, 'Programs', 'Python', 'Python311', 'python.exe'),
      path.join(localAppData, 'Programs', 'Python', 'Python312', 'python.exe'),
      path.join(localAppData, 'Programs', 'Python', 'Python313', 'python.exe'),
    ];
    const match = candidates.find((candidate) => fs.existsSync(candidate));
    if (match) {
      return match;
    }
  }
  return process.platform === 'linux' ? '/usr/bin/python3' : 'python';
}

const pythonPath = resolvePythonPath();
const skinIngestScript = path.join(__dirname, '../src/ingest_skin.py');
const singleInstanceLock = singleInstanceEnabled ? app.requestSingleInstanceLock() : true;
const IS_LINUX = process.platform === 'linux';

if (process.env.ORB_IGNORE_GPU_BLOCKLIST === '1') {
  app.commandLine.appendSwitch('ignore-gpu-blocklist');
}
if (process.env.ORB_ENABLE_GPU_RASTERIZATION === '1') {
  app.commandLine.appendSwitch('enable-gpu-rasterization');
}
if (process.env.ORB_DISABLE_GPU_SANDBOX === '1') {
  app.commandLine.appendSwitch('disable-gpu-sandbox');
}
if (process.env.ORB_USE_GL) {
  app.commandLine.appendSwitch('use-gl', process.env.ORB_USE_GL);
}
if (process.env.ORB_USE_ANGLE) {
  app.commandLine.appendSwitch('use-angle', process.env.ORB_USE_ANGLE);
}

// Default NVIDIA-friendly GPU boosts unless explicitly disabled.
// SurfaceControl is Android/ChromeOS-only and crashes the GPU process on Windows.
// CanvasOopRasterization conflicts with transparent frameless windows on D3D11.
// enable-zero-copy is unstable on some NVIDIA/Windows configurations.
if (process.platform === 'win32' && process.env.ORB_DISABLE_GPU_DEFAULTS !== '1') {
  app.commandLine.appendSwitch('ignore-gpu-blocklist');
  app.commandLine.appendSwitch('enable-gpu-rasterization');
  app.commandLine.appendSwitch('enable-accelerated-video-decode');
  app.commandLine.appendSwitch('enable-accelerated-video-encode');
  app.commandLine.appendSwitch('use-angle', 'd3d11');
  app.commandLine.appendSwitch('enable-features', 'UseSkiaRenderer');
}

if (!singleInstanceLock) {
  app.quit();
}

const orbWindows = new Map();
const appWindows = new Map();
let dockStationWindow = null;
let studioWindow = null;
let orbMessageListenerAttached = false;
let topmostWatchdogInterval = null;
let desktopCursorInterval = null;
let currentOrbSkin = null;
let currentOrbSkinConfig = null;
let skinVaultDir = null;
let skinMetadataDir = null;
let tray = null;
let orbVisible = true;
let lastTopmostRefreshAt = 0;
let activeDisplayId = null;
const DOCK_TRANSITION_MS = 420;
const DOCK_ACK_MS = 90;
const DOCK_TRAVEL_MS = 220;
const DOCK_LOCK_MS = 110;
let dockTransitionActive = false;
let dockTransitionPending = new Set();
let dockTransitionTimeout = null;
const renderDiagnosticsPath = path.join(__dirname, '..', '..', 'orb-render-diagnostics.log');

function parsePositiveIntEnv(name, fallback, minValue = 1) {
  const raw = process.env[name];
  if (raw === undefined || raw === null || raw === '') {
    return fallback;
  }

  const parsed = Number.parseInt(String(raw), 10);
  if (!Number.isFinite(parsed) || parsed < minValue) {
    return fallback;
  }
  return parsed;
}

function normalizeEndpoint(endpoint) {
  const value = String(endpoint || '').trim().replace(/\/+$/, '');
  return value || null;
}

function uniqueValues(values) {
  return [...new Set(values.filter(Boolean))];
}

function getOllamaEndpointCandidates(extra = []) {
  return uniqueValues([
    normalizeEndpoint(process.env.ORB_LOCAL_LLM_ENDPOINT),
    ...extra.map(normalizeEndpoint),
    'http://wsl.localhost:11434',
    'http://127.0.0.1:11434',
    'http://localhost:11434',
    'http://wsl.localhost:11435',
    'http://127.0.0.1:11435',
    'http://localhost:11435',
  ]);
}

function choosePreferredLocalModel(models = []) {
  const names = models
    .map((model) => String(model?.name || model?.model || '').trim())
    .filter(Boolean);
  const preferred = [
    'qwen2.5:3b',
    'qwen:latest',
  ];
  return preferred.find((name) => names.includes(name)) || names[0] || '';
}

async function probeOllamaEndpoint(endpoint) {
  return new Promise((resolve) => {
    let url;
    try {
      url = new URL('/api/tags', endpoint);
    } catch (error) {
      resolve({ endpoint, ok: false, error: error?.message || String(error), models: [] });
      return;
    }

    const transport = url.protocol === 'https:' ? https : http;
    const req = transport.request(
      url,
      { method: 'GET', timeout: 1800 },
      (res) => {
        let body = '';
        res.setEncoding('utf8');
        res.on('data', (chunk) => {
          body += chunk;
          if (body.length > 1024 * 1024) {
            req.destroy(new Error('response too large'));
          }
        });
        res.on('end', () => {
          if (res.statusCode < 200 || res.statusCode >= 300) {
            resolve({ endpoint, ok: false, error: `HTTP ${res.statusCode}`, models: [] });
            return;
          }
          try {
            const payload = JSON.parse(body);
            const models = Array.isArray(payload?.models) ? payload.models : [];
            resolve({ endpoint, ok: true, models });
          } catch (error) {
            resolve({ endpoint, ok: false, error: error?.message || String(error), models: [] });
          }
        });
      }
    );

    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.on('error', (error) => {
      resolve({ endpoint, ok: false, error: error?.message || String(error), models: [] });
    });
    req.end();
  });
}

async function discoverLocalLlm(extraEndpoints = []) {
  const candidates = getOllamaEndpointCandidates(extraEndpoints);
  const probes = [];
  for (const endpoint of candidates) {
    const result = await probeOllamaEndpoint(endpoint);
    probes.push(result);
    if (result.ok && result.models.length) {
      return {
        ok: true,
        endpoint: result.endpoint,
        model: choosePreferredLocalModel(result.models),
        models: result.models,
        probes,
      };
    }
  }
  return { ok: false, endpoint: '', model: '', models: [], probes };
}

const TOPMOST_WATCHDOG_MS = parsePositiveIntEnv('ORB_TOPMOST_WATCHDOG_MS', 250, 50);
const TOPMOST_REFRESH_MS = parsePositiveIntEnv('ORB_TOPMOST_REFRESH_MS', 2500, 250);
const CURSOR_SAMPLE_MS = parsePositiveIntEnv('ORB_CURSOR_SAMPLE_MS', 16, 8);
const PRIMARY_DISPLAY_ONLY = process.env.ORB_PRIMARY_DISPLAY_ONLY === '1';
const SINGLE_ORB_MULTI_DISPLAY = process.env.ORB_SINGLE_ORB_MULTI_DISPLAY !== '0';
const VIRTUAL_DISPLAY_ID = '__orb_virtual_display__';
const INTEGRATION_TIMEOUT_MS = parsePositiveIntEnv('ORB_INTEGRATION_TIMEOUT_MS', 15000, 1000);
const CALI_API_BASE = String(process.env.CALI_API_URL || process.env.CALI_CRM_API_URL || 'http://127.0.0.1:21000').trim().replace(/\/+$/, '');
const CALI_ADMIN_TOKEN = String(process.env.CALI_ADMIN_TOKEN || process.env.ADMIN_ACCESS_TOKEN || '').trim();
const SPRUK_EMAIL_API_BASE = String(process.env.SPRUK_EMAIL_API_URL || 'http://127.0.0.1:19000/api').trim().replace(/\/+$/, '');
const CALI_CRM_PROJECT_ROOT = String(
  process.env.CALI_CRM_PROJECT_ROOT ||
  (process.platform === 'win32' ? 'R:\\SPRUKED_CRM_MASTER_2026-05-05' : '/mnt/r/SPRUKED_CRM_MASTER_2026-05-05')
).trim();
const LOCAL_APP_REGISTRY = {
  mail: {
    id: 'mail',
    title: 'R-Drive Mail',
    url: String(process.env.ORB_MAIL_URL || 'http://127.0.0.1:19000').trim(),
  },
  spruk_email: {
    id: 'spruk_email',
    title: 'Spruk_Email',
    url: String(process.env.ORB_SPRUK_EMAIL_URL || 'http://127.0.0.1:19000').trim(),
  },
  crm: {
    id: 'crm',
    title: 'Spruked CRM',
    url: String(process.env.ORB_CRM_URL || 'http://127.0.0.1:21001').trim(),
  },
};

function buildQueryString(query = {}) {
  const params = new URLSearchParams();
  Object.entries(query || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return;
    }
    params.append(String(key), String(value));
  });
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

async function requestJson(url, { method = 'GET', headers = {}, body, timeoutMs = INTEGRATION_TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });

    const rawText = await response.text();
    let payload = null;
    if (rawText) {
      try {
        payload = JSON.parse(rawText);
      } catch (_error) {
        payload = { raw: rawText };
      }
    } else {
      payload = {};
    }

    if (!response.ok) {
      const detail = payload?.detail || payload?.message || payload?.error || response.statusText || 'request_failed';
      const err = new Error(String(detail));
      err.status = response.status;
      err.payload = payload;
      throw err;
    }

    return payload;
  } finally {
    clearTimeout(timeout);
  }
}

async function requestCali(pathname, { method = 'GET', query, body } = {}) {
  if (!CALI_ADMIN_TOKEN) {
    throw new Error('CALI admin token is not configured');
  }
  const normalizedPath = String(pathname || '').startsWith('/') ? String(pathname) : `/${String(pathname || '')}`;
  const url = `${CALI_API_BASE}${normalizedPath}${buildQueryString(query)}`;
  return requestJson(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${CALI_ADMIN_TOKEN}`,
    },
    body,
  });
}

async function requestSprukEmail(pathname, { method = 'GET', query, body } = {}) {
  const normalizedPath = String(pathname || '').startsWith('/') ? String(pathname) : `/${String(pathname || '')}`;
  const url = `${SPRUK_EMAIL_API_BASE}${normalizedPath}${buildQueryString(query)}`;
  return requestJson(url, {
    method,
    headers: {
      'Content-Type': 'application/json',
    },
    body,
  });
}

function summarizeIntegrationResult(result) {
  if (!result || typeof result !== 'object') {
    return String(result || 'ok');
  }
  if (result.response) {
    return String(result.response);
  }
  if (Array.isArray(result.emails)) {
    return `Loaded ${result.emails.length} emails.`;
  }
  if (result.crm_pipeline?.total !== undefined) {
    return `CRM pipeline loaded (${result.crm_pipeline.total} leads).`;
  }
  if (result.processed !== undefined && result.linked !== undefined) {
    return `Email sync processed ${result.processed}; linked ${result.linked}; created contacts ${result.created_contacts || 0}.`;
  }
  try {
    return JSON.stringify(result, null, 2).slice(0, 1200);
  } catch (_error) {
    return 'Integration request completed.';
  }
}

function writeConversationProofRecord({
  prompt = '',
  response = '',
  responseData = {},
  status = 'failed',
  error = '',
} = {}) {
  try {
    const projectRoot = path.resolve(__dirname, '..', '..');
    const memoryDir = path.join(projectRoot, 'CALI_System', 'memory', 'conversation_tests');
    const notesDir = path.join(projectRoot, 'CALI_System', 'notes', 'conversation_tests');
    fs.mkdirSync(memoryDir, { recursive: true });
    fs.mkdirSync(notesDir, { recursive: true });

    const ts = new Date();
    const stamp = ts.toISOString().replace(/[:.]/g, '-');
    const llmRuntime = responseData?.cali_reasoning?.llm_runtime || {};
    const llmProvider =
      llmRuntime?.provider ||
      responseData?.cali_reasoning?.source ||
      responseData?.source ||
      'unknown';
    const llmModel =
      llmRuntime?.model ||
      responseData?.cali_reasoning?.model ||
      responseData?.model ||
      'unknown';
    const audioPath = responseData?.audio_path || '';
    const audioPlayed = responseData?.audio_played === true;
    const displayedText = Boolean(String(response || '').trim());

    const payload = {
      timestamp: ts.toISOString(),
      test_type: 'conversation_proof',
      status,
      user_prompt: String(prompt || ''),
      llm_response: String(response || ''),
      displayed_text: displayedText,
      llm_provider: llmProvider,
      llm_model: llmModel,
      cp3_invoked: Boolean(responseData?.cp3_invoked),
      tts_provider: String(responseData?.tts_provider || ''),
      tts_fallback_used: Boolean(responseData?.tts_fallback_used),
      tts_primary_error: String(
        responseData?.tts_primary_error ||
        (responseData?.tts_fallback_used ? 'qwen_primary_failed' : '')
      ),
      qwen_tts_endpoint: String(responseData?.qwen_tts_endpoint || ''),
      audio_path: audioPath || '',
      audio_played: audioPlayed,
      llm_runtime: llmRuntime,
      error: error ? String(error) : '',
    };

    const jsonPath = path.join(memoryDir, `${stamp}-conversation-proof.json`);
    fs.writeFileSync(jsonPath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');

    const mdPath = path.join(notesDir, `${stamp}-conversation-proof.md`);
    const md = [
      '# Conversation Proof',
      '',
      `- timestamp: ${payload.timestamp}`,
      `- test_type: ${payload.test_type}`,
      `- status: ${payload.status}`,
      `- llm_provider: ${payload.llm_provider}`,
      `- llm_model: ${payload.llm_model}`,
      `- displayed_text: ${payload.displayed_text}`,
      `- cp3_invoked: ${payload.cp3_invoked}`,
      `- tts_provider: ${payload.tts_provider}`,
      `- tts_fallback_used: ${payload.tts_fallback_used}`,
      `- tts_primary_error: ${payload.tts_primary_error || '(none)'}`,
      `- qwen_tts_endpoint: ${payload.qwen_tts_endpoint}`,
      `- audio_path: ${payload.audio_path || '(none)'}`,
      `- audio_played: ${payload.audio_played}`,
      '',
      '## Prompt',
      payload.user_prompt,
      '',
      '## Response',
      payload.llm_response || '(empty)',
      '',
      payload.error ? `## Error\n${payload.error}` : '',
    ].filter(Boolean).join('\n');
    fs.writeFileSync(mdPath, `${md}\n`, 'utf8');

    return { ok: true, jsonPath, mdPath };
  } catch (writeError) {
    return { ok: false, error: writeError?.message || String(writeError) };
  }
}

function writeDockTransactionRecord(record = {}) {
  try {
    const projectRoot = path.resolve(__dirname, '..', '..');
    const logDir = path.join(projectRoot, 'CALI_System', 'runtime_logs');
    const logPath = path.join(logDir, 'dock_transactions.jsonl');
    fs.mkdirSync(logDir, { recursive: true });
    const payload = {
      timestamp: new Date().toISOString(),
      user_text_received: '',
      text_reply_produced: false,
      llm_endpoint_used: '',
      governance_wrapper_used: false,
      ucm_enabled: String(process.env.ORB_ENABLE_UCM_STATUS_CHECK || '0').trim().toLowerCase() === '1',
      ucm_valid: false,
      ucm_degraded: false,
      ucm_skipped: true,
      qwen_called: false,
      qwen_status: '',
      qwen_error: '',
      qwen_audio_path: '',
      kokoro_fallback_used: false,
      playback_success: false,
      playback_failure: '',
      final_operator_visible_status: 'unknown',
      ...record,
    };
    fs.appendFileSync(logPath, `${JSON.stringify(payload)}\n`, 'utf8');
    return { ok: true, logPath, payload };
  } catch (error) {
    return { ok: false, error: error?.message || String(error) };
  }
}

async function handleIntegrationServiceControl(serviceId, action = 'status', payload = {}) {
  const sid = String(serviceId || '').trim().toLowerCase();
  const act = String(action || 'status').trim().toLowerCase();
  if (sid === 'crm') {
    if (act === 'root' || act === 'project_root') {
      return {
        project_root: CALI_CRM_PROJECT_ROOT,
        exists: fs.existsSync(CALI_CRM_PROJECT_ROOT),
        api_base: CALI_API_BASE,
      };
    }
    if (act === 'request' || act === 'req') {
      const rawPath = String(payload?.path || '/cali/crm/unified/status').trim();
      const method = String(payload?.method || 'GET').trim().toUpperCase();
      const normalizedPath = rawPath.startsWith('/cali/') ? rawPath : `/cali/${rawPath.replace(/^\/+/, '')}`;
      return requestCali(normalizedPath, {
        method,
        query: payload?.query || undefined,
        body: payload?.body || undefined,
      });
    }
    if (act === 'status') return requestCali('/cali/crm/unified/status');
    if (act === 'pipeline') return requestCali('/cali/crm/pipeline');
    if (act === 'contacts') return requestCali('/cali/contacts', { query: payload || undefined });
    if (act === 'query') return requestCali('/cali/query', { method: 'POST', body: payload || {} });
    if (act === 'lead_stage_update') return requestCali('/cali/crm/leads/stage', { method: 'PATCH', body: payload || {} });
    if (act === 'appointment_create') return requestCali('/cali/crm/appointments', { method: 'POST', body: payload || {} });
    if (act === 'activity_log') return requestCali('/cali/crm/activities', { method: 'POST', body: payload || {} });
    if (act === 'activity_list') {
      const contactId = String(payload?.contact_id || '').trim();
      if (!contactId) throw new Error('crm activity_list requires payload.contact_id');
      const query = payload?.query || { limit: payload?.limit || 40 };
      return requestCali(`/cali/crm/activities/${encodeURIComponent(contactId)}`, { query });
    }
    if (act === 'email_connect') return requestCali('/cali/crm/email/connect', { method: 'POST', body: payload || {} });
    if (act === 'email_status') return requestCali('/cali/crm/email/status');
    if (act === 'email_poll') return requestCali('/cali/crm/email/poll', { method: 'POST', body: payload || {} });
    if (act === 'external_email_health') return requestCali('/cali/crm/external-email/health');
    if (act === 'external_email_stats') return requestCali('/cali/crm/external-email/stats');
    if (act === 'external_email_messages') return requestCali('/cali/crm/external-email/messages', { query: payload || undefined });
    if (act === 'external_email_send') return requestCali('/cali/crm/external-email/send', { method: 'POST', body: payload || {} });
    if (act === 'external_email_sync') return requestCali('/cali/crm/external-email/sync', { method: 'POST', body: payload || {} });
    throw new Error(`Unsupported crm action: ${act}`);
  }

  if (sid === 'email' || sid === 'spruk_email' || sid === 'spruk-email') {
    if (act === 'request' || act === 'req') {
      const rawPath = String(payload?.path || '/emails').trim();
      const method = String(payload?.method || 'GET').trim().toUpperCase();
      const normalizedPath = rawPath.startsWith('/') ? rawPath : `/${rawPath}`;
      return requestSprukEmail(normalizedPath, {
        method,
        query: payload?.query || undefined,
        body: payload?.body || undefined,
      });
    }
    if (act === 'status' || act === 'health') return requestSprukEmail('/health');
    if (act === 'stats') return requestSprukEmail('/stats');
    if (act === 'list' || act === 'inbox') return requestSprukEmail('/emails', { query: payload || {} });
    if (act === 'open') {
      const emailId = Number(payload?.email_id || payload?.id || 0);
      if (!Number.isFinite(emailId) || emailId <= 0) throw new Error('email open requires payload.email_id');
      return requestSprukEmail(`/emails/${emailId}`);
    }
    if (act === 'update') {
      const emailId = Number(payload?.email_id || payload?.id || 0);
      if (!Number.isFinite(emailId) || emailId <= 0) throw new Error('email update requires payload.email_id');
      const updates = payload?.updates || payload?.body || {};
      return requestSprukEmail(`/emails/${emailId}`, { method: 'PATCH', body: updates });
    }
    if (act === 'delete') {
      const emailId = Number(payload?.email_id || payload?.id || 0);
      if (!Number.isFinite(emailId) || emailId <= 0) throw new Error('email delete requires payload.email_id');
      return requestSprukEmail(`/emails/${emailId}`, { method: 'DELETE' });
    }
    if (act === 'send') return requestSprukEmail('/emails/send', { method: 'POST', body: payload || {} });
    throw new Error(`Unsupported email action: ${act}`);
  }

  return null;
}

async function runIntegrationChatCommand(text) {
  const trimmed = String(text || '').trim();
  if (!trimmed.startsWith('/')) {
    return null;
  }

  const lower = trimmed.toLowerCase();
  if (lower.startsWith('/crm status')) {
    const result = await requestCali('/cali/crm/unified/status');
    return { ok: true, result, responseText: summarizeIntegrationResult(result) };
  }
  if (lower.startsWith('/crm root')) {
    const result = {
      project_root: CALI_CRM_PROJECT_ROOT,
      exists: fs.existsSync(CALI_CRM_PROJECT_ROOT),
      api_base: CALI_API_BASE,
    };
    return { ok: true, result, responseText: summarizeIntegrationResult(result) };
  }
  if (lower.startsWith('/crm pipeline')) {
    const result = await requestCali('/cali/crm/pipeline');
    return { ok: true, result, responseText: summarizeIntegrationResult(result) };
  }
  if (lower.startsWith('/crm contacts')) {
    const result = await requestCali('/cali/contacts', { query: { query: '' } });
    return { ok: true, result, responseText: summarizeIntegrationResult(result) };
  }
  if (lower.startsWith('/crm email poll')) {
    const result = await requestCali('/cali/crm/email/poll', {
      method: 'POST',
      body: { mailbox: 'INBOX', limit: 25, since_hours: 72, unseen_only: true },
    });
    return { ok: true, result, responseText: summarizeIntegrationResult(result) };
  }
  if (lower.startsWith('/crm email sync')) {
    const result = await requestCali('/cali/crm/external-email/sync', {
      method: 'POST',
      body: { folder: 'inbox', limit: 50, unread_only: false },
    });
    return { ok: true, result, responseText: summarizeIntegrationResult(result) };
  }
  if (lower.startsWith('/email status')) {
    const result = await requestSprukEmail('/health');
    return { ok: true, result, responseText: summarizeIntegrationResult(result) };
  }
  if (lower.startsWith('/email inbox')) {
    const result = await requestSprukEmail('/emails', {
      query: { folder: 'inbox', limit: 20 },
    });
    return { ok: true, result, responseText: summarizeIntegrationResult(result) };
  }
  if (lower.startsWith('/crm req ')) {
    const raw = trimmed.slice('/crm req '.length).trim();
    const match = raw.match(/^(GET|POST|PATCH|DELETE)\s+(\S+)(?:\s+(.*))?$/i);
    if (!match) {
      throw new Error('Usage: /crm req <GET|POST|PATCH|DELETE> <path> [json_body]');
    }
    const method = String(match[1]).toUpperCase();
    const pathValue = String(match[2]);
    const bodyRaw = String(match[3] || '').trim();
    const body = bodyRaw ? JSON.parse(bodyRaw) : undefined;
    const normalized = pathValue.startsWith('/cali/') ? pathValue : `/cali/${pathValue.replace(/^\/+/, '')}`;
    const result = await requestCali(normalized, { method, body });
    return { ok: true, result, responseText: summarizeIntegrationResult(result) };
  }
  if (lower.startsWith('/email req ')) {
    const raw = trimmed.slice('/email req '.length).trim();
    const match = raw.match(/^(GET|POST|PATCH|DELETE)\s+(\S+)(?:\s+(.*))?$/i);
    if (!match) {
      throw new Error('Usage: /email req <GET|POST|PATCH|DELETE> <path> [json_body]');
    }
    const method = String(match[1]).toUpperCase();
    const pathValue = String(match[2]);
    const bodyRaw = String(match[3] || '').trim();
    const body = bodyRaw ? JSON.parse(bodyRaw) : undefined;
    const normalized = pathValue.startsWith('/') ? pathValue : `/${pathValue}`;
    const result = await requestSprukEmail(normalized, { method, body });
    return { ok: true, result, responseText: summarizeIntegrationResult(result) };
  }

  return null;
}

function normalizeVirtualDisplayRects(displays, originX, originY) {
  return displays.map((display, index) => {
    const b = display.bounds;
    return {
      id: display.id,
      index,
      x: b.x - originX,
      y: b.y - originY,
      width: b.width,
      height: b.height,
    };
  });
}

function isBrokenPipeError(error) {
  return Boolean(
    error &&
      (
        error.code === 'EPIPE' ||
        error.errno === 'EPIPE' ||
        /broken pipe/i.test(String(error.message || ''))
      )
  );
}

function canWriteToConsole(method) {
  const stream = method === 'warn' || method === 'error'
    ? process.stderr
    : process.stdout;

  return Boolean(
    stream &&
    typeof stream.write === 'function' &&
    !stream.destroyed &&
    stream.writable !== false
  );
}

function safeMainConsole(method, ...args) {
  if (!canWriteToConsole(method)) {
    return;
  }

  try {
    const fn = console[method] || console.log;
    fn(...args);
  } catch (error) {
    if (!isBrokenPipeError(error)) {
      throw error;
    }
  }
}

function writeRenderDiagnostic(scope, message) {
  const line = `[${new Date().toISOString()}] [${scope}] ${message}\n`;
  try {
    fs.appendFileSync(renderDiagnosticsPath, line);
  } catch (_error) {}
}

function attachWindowDiagnostics(win, label) {
  if (!win || win.isDestroyed() || win.__orbDiagnosticsAttached) {
    return;
  }

  win.__orbDiagnosticsAttached = true;
  win.webContents.on('did-finish-load', () => {
    writeRenderDiagnostic(label, `did-finish-load ${win.webContents.getURL()}`);
  });
  win.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    writeRenderDiagnostic(label, `did-fail-load ${errorCode} ${errorDescription} ${validatedURL}`);
  });
  win.webContents.on('render-process-gone', (_event, details) => {
    writeRenderDiagnostic(label, `render-process-gone ${JSON.stringify(details)}`);
  });
  win.webContents.on('unresponsive', () => {
    writeRenderDiagnostic(label, 'unresponsive');
  });
  win.webContents.on('console-message', (_event, level, message, line, sourceId) => {
    writeRenderDiagnostic(label, `console level=${level} ${sourceId}:${line} ${message}`);
  });
}

function installMainProcessPipeGuards() {
  const guard = (error) => {
    if (!isBrokenPipeError(error)) {
      throw error;
    }
  };

  if (process.stdout && typeof process.stdout.on === 'function') {
    process.stdout.on('error', guard);
  }

  if (process.stderr && typeof process.stderr.on === 'function') {
    process.stderr.on('error', guard);
  }

  process.on('uncaughtException', (error) => {
    if (isBrokenPipeError(error)) {
      return;
    }

    safeMainConsole('error', 'Uncaught exception in Electron main process:', error);
    app.exit(1);
  });

  process.on('unhandledRejection', (reason) => {
    if (isBrokenPipeError(reason)) {
      return;
    }

    safeMainConsole('error', 'Unhandled rejection in Electron main process:', reason);
  });
}

installMainProcessPipeGuards();

function logGpuStatus(stage) {
  try {
    safeMainConsole('log', `[GPU:${stage}]`, app.getGPUFeatureStatus());
  } catch (error) {
    safeMainConsole('warn', `[GPU:${stage}] failed to read GPU feature status:`, error.message);
  }
}

function getOrbWindows() {
  return Array.from(orbWindows.values()).filter((win) => win && !win.isDestroyed());
}

function forEachOrbWindow(callback) {
  getOrbWindows().forEach(callback);
}

function getPrimaryOrbWindow() {
  const primaryDisplay = screen.getPrimaryDisplay();
  return orbWindows.get(primaryDisplay.id) || getOrbWindows()[0] || null;
}

function getWindowDisplayId(win) {
  return win && !win.isDestroyed() ? win.__orbDisplayId : null;
}

function getEventWindow(event) {
  return BrowserWindow.fromWebContents(event.sender) || getPrimaryOrbWindow();
}

function ensureSkinVault() {
  if (skinVaultDir && skinMetadataDir) {
    return;
  }

  skinVaultDir = path.join(app.getPath('userData'), 'skins');
  skinMetadataDir = path.join(skinVaultDir, 'metadata');
  fs.mkdirSync(skinVaultDir, { recursive: true });
  fs.mkdirSync(skinMetadataDir, { recursive: true });
}

function registerSkinProtocol() {
  protocol.registerFileProtocol('orb-skin', (request, callback) => {
    try {
      ensureSkinVault();
      const relativePath = decodeURIComponent(request.url.replace('orb-skin://', ''));
      const resolvedPath = path.resolve(skinVaultDir, relativePath);

      if (!resolvedPath.startsWith(skinVaultDir)) {
        callback({ error: -10 });
        return;
      }

      callback(resolvedPath);
    } catch (error) {
      callback({ error: -2 });
    }
  });
}

function toSkinUrl(filename) {
  return filename ? `orb-skin://${encodeURIComponent(filename)}` : null;
}

function ingestSkinWithPython(sourcePath) {
  ensureSkinVault();

  return new Promise((resolve, reject) => {
    const proc = spawn(
      pythonPath,
      ['-u', skinIngestScript, '--source', sourcePath, '--skins-dir', skinVaultDir],
      { stdio: ['ignore', 'pipe', 'pipe'] }
    );

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });

    proc.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });

    proc.on('close', (code) => {
      if (code !== 0) {
        reject(new Error(stderr.trim() || `Skin ingest failed with code ${code}`));
        return;
      }

      try {
        resolve(JSON.parse(stdout.trim()));
      } catch (error) {
        reject(new Error(`Invalid ingest response: ${stdout.trim()}`));
      }
    });
  });
}

function ensureTopmost(forceRefresh = false) {
  const windows = getOrbWindows();
  if (!windows.length || !orbVisible) {
    return;
  }

  const now = Date.now();
  const shouldRefresh = forceRefresh || now - lastTopmostRefreshAt >= TOPMOST_REFRESH_MS;

  if (shouldRefresh) {
    windows.forEach((win) => {
      win.setAlwaysOnTop(false);
    });
    lastTopmostRefreshAt = now;
  }

  windows.forEach((win) => {
    win.setAlwaysOnTop(true, 'screen-saver', 1);
    win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    if (!win.isVisible() && orbVisible) {
      win.showInactive();
    }
    win.moveTop();
  });

  if (dockStationWindow && !dockStationWindow.isDestroyed() && dockStationWindow.isVisible()) {
    dockStationWindow.setAlwaysOnTop(true, 'screen-saver', 2);
    dockStationWindow.moveTop();
  }
}

function setOrbMousePassthroughForWindow(win, ignore, options) {
  if (!win || win.isDestroyed()) {
    return;
  }

  const shouldIgnore = Boolean(ignore);

  if (IS_LINUX) {
    const shouldBeFocusable = !shouldIgnore && orbVisible;
    if (win.isFocusable() !== shouldBeFocusable) {
      win.setFocusable(shouldBeFocusable);
    }
    if (!shouldBeFocusable) {
      win.blur();
    }
  }

  win.setIgnoreMouseEvents(shouldIgnore, shouldIgnore ? (options || { forward: true }) : undefined);
  ensureTopmost(!shouldIgnore);
}

function broadcastCursorPosition(cursor) {
  const windows = getOrbWindows();
  if (!windows.length || !orbVisible) {
    return;
  }

  const previousActiveDisplayId = activeDisplayId;

  const windowStates = windows.map((win) => {
    const bounds = win.getBounds();
    const containsCursor =
      cursor.x >= bounds.x &&
      cursor.x < bounds.x + bounds.width &&
      cursor.y >= bounds.y &&
      cursor.y < bounds.y + bounds.height;

    const dx =
      cursor.x < bounds.x
        ? bounds.x - cursor.x
        : cursor.x > bounds.x + bounds.width
          ? cursor.x - (bounds.x + bounds.width)
          : 0;
    const dy =
      cursor.y < bounds.y
        ? bounds.y - cursor.y
        : cursor.y > bounds.y + bounds.height
          ? cursor.y - (bounds.y + bounds.height)
          : 0;
    const distanceToBounds = Math.hypot(dx, dy);

    return {
      win,
      bounds,
      containsCursor,
      distanceToBounds,
      displayId: getWindowDisplayId(win),
    };
  });

  let activeWindowState = windowStates.find((state) => state.containsCursor) || null;
  if (!activeWindowState) {
    activeWindowState = windowStates
      .slice()
      .sort((a, b) => a.distanceToBounds - b.distanceToBounds)[0] || null;
  }

  activeDisplayId = activeWindowState?.displayId ?? null;

  windowStates.forEach((state) => {
    const isActiveDisplay = activeWindowState && state.win === activeWindowState.win;

    if (!isActiveDisplay && previousActiveDisplayId !== activeDisplayId) {
      setOrbMousePassthroughForWindow(state.win, true, { forward: true });
    }

    state.win.webContents.send(
      'orb:position-update',
      isActiveDisplay
        ? {
            active: true,
            x: cursor.x - state.bounds.x,
            y: cursor.y - state.bounds.y,
            globalX: cursor.x,
            globalY: cursor.y,
            overlayX: state.bounds.x,
            overlayY: state.bounds.y,
            overlayWidth: state.bounds.width,
            overlayHeight: state.bounds.height,
            virtualDesktop: state.displayId === VIRTUAL_DISPLAY_ID,
            displayRects: state.win.__orbDisplayRects || null,
          }
        : { active: false }
    );
  });
}

function sampleDesktopCursor() {
  if (!getOrbWindows().length || !orbVisible) {
    return;
  }

  const cursor = screen.getCursorScreenPoint();
  sendCursorMove(cursor.x, cursor.y);
  broadcastCursorPosition(cursor);
}

function startWindowTracking() {
  if (topmostWatchdogInterval || desktopCursorInterval) {
    return;
  }

  ensureTopmost();
  sampleDesktopCursor();
  desktopCursorInterval = setInterval(sampleDesktopCursor, CURSOR_SAMPLE_MS);
  topmostWatchdogInterval = setInterval(() => ensureTopmost(false), TOPMOST_WATCHDOG_MS);
}

function stopWindowTracking() {
  if (topmostWatchdogInterval) {
    clearInterval(topmostWatchdogInterval);
    topmostWatchdogInterval = null;
  }

  if (desktopCursorInterval) {
    clearInterval(desktopCursorInterval);
    desktopCursorInterval = null;
  }
}

function createTrayIcon() {
  const trayIconPath = path.join(__dirname, '..', 'CALIOrb512.png');
  if (fs.existsSync(trayIconPath)) {
    const iconImage = nativeImage.createFromPath(trayIconPath);
    if (!iconImage.isEmpty()) {
      // Windows tray icons render best when explicitly sized small.
      return iconImage.resize({ width: 20, height: 20 });
    }
  }

  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">
      <defs>
        <radialGradient id="g" cx="35%" cy="30%" r="65%">
          <stop offset="0%" stop-color="#ffffff" stop-opacity="0.95" />
          <stop offset="28%" stop-color="#67c6ff" stop-opacity="0.98" />
          <stop offset="100%" stop-color="#08111f" stop-opacity="1" />
        </radialGradient>
      </defs>
      <circle cx="32" cy="32" r="23" fill="url(#g)" />
      <circle cx="24" cy="22" r="8" fill="#ffffff" fill-opacity="0.28" />
    </svg>
  `;
  return nativeImage.createFromDataURL(`data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`);
}

function updateTrayMenu() {
  if (!tray) {
    return;
  }

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Talk to Orb',
      click: () => openDockStationWindow(),
    },
    {
      label: 'Open Dock Station',
      click: () => openDockStationWindow(),
    },
    { type: 'separator' },
    {
      label: orbVisible ? 'Dock Orb' : 'Launch Orb',
      click: () => toggleOrbVisibility(),
    },
    {
      label: 'Quit',
      click: () => app.quit(),
    },
  ]);

  tray.setContextMenu(contextMenu);
  tray.setToolTip(orbVisible ? `${productName}: Active` : `${productName}: Docked`);
}

function clearDockTransitionState() {
  dockTransitionActive = false;
  dockTransitionPending.clear();
  if (dockTransitionTimeout) {
    clearTimeout(dockTransitionTimeout);
    dockTransitionTimeout = null;
  }
}

function hideOrbImmediately() {
  const windows = getOrbWindows();
  if (!windows.length) {
    return;
  }

  orbVisible = false;
  stopWindowTracking();
  windows.forEach((win) => {
    setOrbMousePassthroughForWindow(win, true, { forward: true });
    win.webContents.send('orb:visibility-changed', { visible: false });
    win.hide();
  });
  if (dockStationWindow && !dockStationWindow.isDestroyed()) {
    dockStationWindow.webContents.send('orb:visibility-changed', { visible: false });
  }
  updateTrayMenu();
}

function beginDockTransition() {
  const windows = getOrbWindows();
  if (!windows.length) {
    hideOrbImmediately();
    return;
  }

  clearDockTransitionState();
  dockTransitionActive = true;
  dockTransitionPending = new Set(windows.map((win) => win.webContents.id));

  windows.forEach((win) => {
    win.webContents.send('orb:dock-transition', {
      phase: 'start',
      totalMs: DOCK_TRANSITION_MS,
      ackMs: DOCK_ACK_MS,
      travelMs: DOCK_TRAVEL_MS,
      lockMs: DOCK_LOCK_MS,
    });
  });

  dockTransitionTimeout = setTimeout(() => {
    clearDockTransitionState();
    hideOrbImmediately();
  }, DOCK_TRANSITION_MS + 380);
}

function completeDockTransitionForSender(webContentsId) {
  if (!dockTransitionActive) {
    return;
  }

  dockTransitionPending.delete(webContentsId);
  if (dockTransitionPending.size > 0) {
    return;
  }

  clearDockTransitionState();
  hideOrbImmediately();
}

function openDockStationWindow() {
  writeRenderDiagnostic('dock', 'openDockStationWindow invoked');
  if (dockStationWindow && !dockStationWindow.isDestroyed()) {
    writeRenderDiagnostic('dock', 'reusing existing dock window');
    dockStationWindow.setSkipTaskbar(false);
    dockStationWindow.show();
    dockStationWindow.focus();
    return dockStationWindow;
  }

  const tier = parseInt(process.env.ORB_DOCK_TIER || '2', 10);
  const cursorDisplay = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());
  const workArea = cursorDisplay?.workArea || screen.getPrimaryDisplay().workArea;
  const maxW = Math.max(900, Math.floor(workArea.width * 0.92));
  const maxH = Math.max(700, Math.floor(workArea.height * 0.92));
  const requestedW = tier === 1 ? 620 : 1120;
  const requestedH = tier === 1 ? 860 : 980;
  const minW = tier === 1 ? 560 : 920;
  const minH = tier === 1 ? 700 : 720;
  const w = Math.min(maxW, requestedW);
  const h = Math.min(maxH, requestedH);
  const dockX = Math.round(workArea.x + Math.max(20, (workArea.width - w) / 2));
  const dockY = Math.round(workArea.y + Math.max(20, (workArea.height - h) / 2));

  dockStationWindow = new BrowserWindow({
    x: dockX,
    y: dockY,
    width: w,
    height: h,
    minWidth: minW,
    minHeight: minH,
    show: true,
    title: `${productName} - Dock Station`,
    backgroundColor: '#020712',
    autoHideMenuBar: true,
    movable: true,
    resizable: true,
    minimizable: true,
    maximizable: true,
    alwaysOnTop: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  writeRenderDiagnostic('dock', 'BrowserWindow created');
  attachWindowDiagnostics(dockStationWindow, 'dock');
  dockStationWindow.setAlwaysOnTop(true, 'screen-saver', 2);
  dockStationWindow.setSkipTaskbar(false);
  dockStationWindow.show();
  dockStationWindow.focus();

  // Minimize-to-tray behavior for smooth desktop UX.
  dockStationWindow.on('minimize', (event) => {
    event.preventDefault();
    if (!dockStationWindow || dockStationWindow.isDestroyed()) {
      return;
    }
    dockStationWindow.hide();
    dockStationWindow.setSkipTaskbar(true);
  });

  dockStationWindow.on('show', () => {
    if (!dockStationWindow || dockStationWindow.isDestroyed()) {
      return;
    }
    dockStationWindow.setAlwaysOnTop(true, 'screen-saver', 2);
    dockStationWindow.moveTop();
    dockStationWindow.setSkipTaskbar(false);
  });
  dockStationWindow.on('focus', () => dockStationWindow && !dockStationWindow.isDestroyed() && dockStationWindow.moveTop());
  dockStationWindow.on('move', () => dockStationWindow && !dockStationWindow.isDestroyed() && dockStationWindow.moveTop());
  dockStationWindow.on('resize', () => dockStationWindow && !dockStationWindow.isDestroyed() && dockStationWindow.moveTop());

  writeRenderDiagnostic('dock', 'calling loadFile');
  dockStationWindow.loadFile(
    path.join(__dirname, '../src/ui/orb-dock-station.html'),
    { query: { tier: String(tier) } }
  );
  writeRenderDiagnostic('dock', 'loadFile returned');

  dockStationWindow.webContents.on('did-finish-load', () => {
    if (!dockStationWindow || dockStationWindow.isDestroyed()) {
      return;
    }
    dockStationWindow.show();
    dockStationWindow.focus();
    dockStationWindow.webContents.send('orb:visibility-changed', { visible: orbVisible });
  });

  dockStationWindow.once('ready-to-show', () => {
    if (!dockStationWindow || dockStationWindow.isDestroyed()) {
      return;
    }
    dockStationWindow.show();
    dockStationWindow.focus();
    dockStationWindow.webContents.send('orb:visibility-changed', { visible: orbVisible });
  });

  setTimeout(() => {
    if (!dockStationWindow || dockStationWindow.isDestroyed()) {
      return;
    }
    dockStationWindow.show();
    dockStationWindow.focus();
  }, 1800);

  dockStationWindow.on('closed', () => {
    dockStationWindow = null;
  });

  return dockStationWindow;
}

function openStudioWindow() {
  if (studioWindow && !studioWindow.isDestroyed()) {
    studioWindow.show();
    studioWindow.focus();
    return studioWindow;
  }

  studioWindow = new BrowserWindow({
    width: 1280,
    height: 900,
    minWidth: 800,
    minHeight: 600,
    show: false,
    title: `${productName} - Studio`,
    backgroundColor: '#020712',
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });
  attachWindowDiagnostics(studioWindow, 'studio');

  studioWindow.loadFile(
    path.join(__dirname, '../src/ui/orb-dock-station.html'),
    { query: { view: 'studio' } }
  );

  studioWindow.webContents.on('did-finish-load', () => {
    if (!studioWindow || studioWindow.isDestroyed()) return;
    studioWindow.show();
    studioWindow.focus();
  });

  studioWindow.once('ready-to-show', () => {
    if (!studioWindow || studioWindow.isDestroyed()) return;
    studioWindow.show();
    studioWindow.focus();
    if (dockStationWindow && !dockStationWindow.isDestroyed()) {
      dockStationWindow.webContents.send('orb:studio-connected');
    }
  });

  setTimeout(() => {
    if (!studioWindow || studioWindow.isDestroyed()) {
      return;
    }
    studioWindow.show();
    studioWindow.focus();
  }, 1800);

  studioWindow.on('closed', () => {
    studioWindow = null;
    if (dockStationWindow && !dockStationWindow.isDestroyed()) {
      dockStationWindow.webContents.send('orb:studio-closed');
    }
  });

  return studioWindow;
}

function openLocalAppWindow(appId) {
  const appInfo = LOCAL_APP_REGISTRY[String(appId || '').trim().toLowerCase()];
  if (!appInfo) {
    throw new Error(`Unknown local app: ${appId}`);
  }

  const existing = appWindows.get(appInfo.id);
  if (existing && !existing.isDestroyed()) {
    existing.show();
    existing.focus();
    return { id: appInfo.id, title: appInfo.title, url: appInfo.url };
  }

  const win = new BrowserWindow({
    width: 1320,
    height: 900,
    minWidth: 960,
    minHeight: 640,
    show: true,
    title: `${productName} - ${appInfo.title}`,
    backgroundColor: '#020712',
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  appWindows.set(appInfo.id, win);
  attachWindowDiagnostics(win, `local-app:${appInfo.id}`);
  win.loadURL(appInfo.url);
  win.on('closed', () => {
    appWindows.delete(appInfo.id);
  });

  return { id: appInfo.id, title: appInfo.title, url: appInfo.url };
}

function showOrb() {
  const windows = getOrbWindows();
  if (!windows.length) {
    return;
  }

  if (dockTransitionActive) {
    windows.forEach((win) => {
      win.webContents.send('orb:dock-transition', { phase: 'cancel' });
    });
    clearDockTransitionState();
  }

  orbVisible = true;
  windows.forEach((win) => {
    win.showInactive();
    setOrbMousePassthroughForWindow(win, true, { forward: true });
    win.webContents.send('orb:visibility-changed', { visible: true });
  });
  if (dockStationWindow && !dockStationWindow.isDestroyed()) {
    dockStationWindow.webContents.send('orb:visibility-changed', { visible: true });
  }
  ensureTopmost(true);
  startWindowTracking();
  sampleDesktopCursor();
  updateTrayMenu();
}

function hideOrb({ immediate = false } = {}) {
  if (immediate || process.env.ORB_DISABLE_DOCK_TRANSITION === '1') {
    clearDockTransitionState();
    hideOrbImmediately();
    return;
  }

  if (dockTransitionActive) {
    return;
  }

  beginDockTransition();
}

function toggleOrbVisibility(forceVisible) {
  const nextVisible = typeof forceVisible === 'boolean' ? forceVisible : !orbVisible;
  if (nextVisible) {
    showOrb();
  } else {
    hideOrb();
  }
}

function dispatchPrimeOrbCommand(command = {}) {
  const payload = command && typeof command === 'object'
    ? command
    : { command: String(command || '').trim() };
  const windows = getOrbWindows();
  if (!windows.length) {
    return { ok: false, delivered: 0, error: 'No active ORB windows' };
  }

  windows.forEach((win) => {
    win.webContents.send('orb:prime-command', payload);
  });

  return {
    ok: true,
    delivered: windows.length,
    command: String(payload.command || 'unknown'),
  };
}

function createTray() {
  if (tray) {
    return;
  }

  tray = new Tray(createTrayIcon());
  tray.on('double-click', () => openDockStationWindow());
  tray.on('click', () => openDockStationWindow());
  updateTrayMenu();
}

function buildSearchUrl(query, mode = 'web') {
  const trimmed = String(query || '').trim();
  if (!trimmed) {
    return null;
  }

  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed;
  }

  if (/^[a-z0-9-]+\.[a-z]{2,}(\/.*)?$/i.test(trimmed)) {
    return `https://${trimmed}`;
  }

  const encoded = encodeURIComponent(trimmed);
  if (mode === 'shopping') {
    return `https://www.google.com/search?tbm=shop&q=${encoded}`;
  }

  return `https://www.google.com/search?q=${encoded}`;
}

let startupGreetingDone = false;

function broadcastChatMessage(text, role = 'orb', extra = {}) {
  const targets = [...getOrbWindows()];
  if (dockStationWindow && !dockStationWindow.isDestroyed()) {
    targets.push(dockStationWindow);
  }
  const payload = { role, text, time: new Date().toTimeString().slice(0, 8), ...extra };
  targets.forEach((win) => {
    win.webContents.send('orb:chat-message', payload);
  });
}

function forwardOrbMessage(message) {
  try {
    if (message && (message.type === 'verbal_command' || message.type === 'speech_pulse' || message.type === 'status_response')) {
      recordObservation(message.type, JSON.stringify(message.data || message), {
        source: 'orb_bridge',
        command: message.command || null,
      });
    }
  } catch (_error) {}

  // Route voice I/O into the shared chat channel so the dock ChatPanel shows it
  if (message?.type === 'speech_heard') {
    const transcript = message.data?.transcript || '';
    if (transcript) {
      broadcastChatMessage(transcript, 'user');
      const targets = [...getOrbWindows()];
      if (dockStationWindow && !dockStationWindow.isDestroyed()) {
        targets.push(dockStationWindow);
      }
      targets.forEach((win) => {
        win.webContents.send('orb:speech-pulse', {
          type: 'speech_heard',
          data: { transcript, transcription: transcript },
          transcript,
          transcription: transcript,
        });
      });
    }
  } else if (['query_result', 'skill_result', 'core_knowledge_result', 'research_vault_result'].includes(message?.type)) {
    const text = message.data?.response_text || message.data?.text || '';
    if (text) {
      message.data._chat_forwarded = true;
      broadcastChatMessage(text, 'orb', {
        audioPath: message.data?.audio_path || null,
        voicePackage: message.data?.voice_package || null,
        llmRuntime: message.data?.cali_reasoning?.llm_runtime || null,
      });
    }
  }

  const orbWindowsList = getOrbWindows();
  const targets = [...orbWindowsList];
  if (dockStationWindow && !dockStationWindow.isDestroyed()) {
    targets.push(dockStationWindow);
  }

  if (!targets.length) {
    return;
  }

  targets.forEach((win) => {
    win.webContents.send('orb:bridge-message', message);

    if (message.type === 'cognitive_pulse') {
      win.webContents.send('orb:cognitive-pulse', message.data);
    } else if (message.type === 'egf_state') {
      win.webContents.send('orb:egf-state', message.data);
    } else if (message.type === 'hlsf_snapshot') {
      win.webContents.send('orb:hlsf-snapshot', message.data);
    } else if (message.type === 'speech_pulse') {
      win.webContents.send('orb:speech-pulse', message);
    } else if (message.type === 'verbal_command') {
      win.webContents.send('orb:verbal-command', message);
    } else if (message.type === 'status_response') {
      win.webContents.send('orb:status-change', message.data);
    } else if (message.type === 'ready') {
      win.webContents.send('orb:status-change', {
        running: true,
        controller_status: 'ready',
      });
    } else if (message.type === 'hysteresis') {
      win.webContents.send('orb:hysteresis', message.data);
    } else if (message.type === 'heartbeat') {
      // ORB Standard XI — forward lifecycle heartbeat to all shells
      win.webContents.send('orb:heartbeat', message.data);
    }
  });

  if (message.type === 'verbal_command') {
    if (message.command === 'show_orb') {
      showOrb();
    } else if (message.command === 'dock_orb') {
      hideOrb();
    } else if (message.command === 'toggle_visibility') {
      toggleOrbVisibility();
    }
  }

  if (message.type === 'ready' && !startupGreetingDone) {
    startupGreetingDone = true;
    const greetingText = "Hello Bryan, I'm online and ready to assist.";
    speakOrb(greetingText, 'thoughtful_warm').catch(() => {});
    // Give the bridge a moment to initialize before showing the greeting
    setTimeout(() => broadcastChatMessage(greetingText, 'orb'), 800);
  }
}

function forwardOrbSkin() {
  const targets = getOrbWindows();
  if (dockStationWindow && !dockStationWindow.isDestroyed()) {
    targets.push(dockStationWindow);
  }

  targets.forEach((win) => {
    win.webContents.send('orb:skin-updated', {
      imageUrl: currentOrbSkin,
    });
  });
}

function forwardOrbSkinConfig() {
  const targets = getOrbWindows();
  if (dockStationWindow && !dockStationWindow.isDestroyed()) {
    targets.push(dockStationWindow);
  }
  targets.forEach((win) => {
    win.webContents.send('orb:skin-config-updated', currentOrbSkinConfig);
  });
}

// Watch orb mesh for skin apply requests written by the gallery
const MESH_SKIN_APPLY_PATH = path.join(
  process.env.ORB_SHARED_MESH_ROOT || path.join('R:', 'orb_mesh'),
  'tasks', 'broadcast', 'skin_apply_pending.json'
);
let meshSkinApplyMtime = null;
setInterval(() => {
  try {
    const stat = fs.statSync(MESH_SKIN_APPLY_PATH);
    if (meshSkinApplyMtime === null || stat.mtimeMs > meshSkinApplyMtime) {
      meshSkinApplyMtime = stat.mtimeMs;
      const raw = fs.readFileSync(MESH_SKIN_APPLY_PATH, 'utf8');
      const config = JSON.parse(raw);
      if (config && (config.colorScheme || config.name)) {
        currentOrbSkinConfig = config;
        forwardOrbSkinConfig();
        safeMainConsole('log', `[Skin] Applied from mesh: ${config.name || config.colorScheme}`);
      }
    }
  } catch (_e) {
    // File doesn't exist yet — that's expected until gallery writes one
  }
}, 2000);

function ensureOrbListeners() {
  if (orbMessageListenerAttached) {
    return;
  }

  onOrbMessage(forwardOrbMessage);
  orbMessageListenerAttached = true;
}

function createOrbWindowForDisplay(display) {
  const { x, y, width, height } = display.bounds;

  const orbWindow = new BrowserWindow({
    x,
    y,
    width,
    height,
    show: false,
    transparent: true,
    backgroundColor: '#00000000',
    frame: false,
    alwaysOnTop: true,
    hasShadow: false,
    resizable: false,
    skipTaskbar: true,
    focusable: !IS_LINUX,
    fullscreenable: false,
    maximizable: false,
    minimizable: false,
    ...(IS_LINUX ? { type: 'toolbar' } : {}),
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  orbWindow.__orbDisplayId = display.id;
  orbWindow.__orbDisplayRects = display.displayRects || null;
  attachWindowDiagnostics(orbWindow, `orb:${display.id}`);
  orbWindow.setAlwaysOnTop(true, 'screen-saver', 1);
  orbWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  orbWindow.loadFile(path.join(__dirname, '../src/orb-shell.html'));

  orbWindow.webContents.on('did-finish-load', () => {
    if (orbVisible && !orbWindow.isDestroyed()) {
      orbWindow.showInactive();
      setOrbMousePassthroughForWindow(orbWindow, true, { forward: true });
      ensureTopmost(true);
    }
  });

  orbWindow.once('ready-to-show', () => {
    if (orbVisible) {
      orbWindow.showInactive();
    }
    setOrbMousePassthroughForWindow(orbWindow, true, { forward: true });
    orbWindow.setHasShadow(false);
    orbWindow.webContents.send('orb:visibility-changed', { visible: orbVisible });
    ensureTopmost(true);
    startWindowTracking();
    forwardOrbSkin();
    updateTrayMenu();
    sampleDesktopCursor();
  });

  setTimeout(() => {
    if (orbVisible && !orbWindow.isDestroyed()) {
      orbWindow.showInactive();
      setOrbMousePassthroughForWindow(orbWindow, true, { forward: true });
      ensureTopmost(true);
    }
  }, 1800);

  orbWindow.on('blur', () => ensureTopmost(true));
  orbWindow.on('show', () => ensureTopmost(true));
  orbWindow.on('restore', () => ensureTopmost(true));
  orbWindow.on('focus', () => ensureTopmost(true));
  orbWindow.on('move', () => ensureTopmost(false));
  orbWindow.on('resize', () => ensureTopmost(false));

  orbWindow.on('closed', () => {
    orbWindows.delete(display.id);
    if (!getOrbWindows().length) {
      stopWindowTracking();
    }
  });

  orbWindows.set(display.id, orbWindow);
  return orbWindow;
}

function getVirtualDisplayDescriptor() {
  const displays = screen.getAllDisplays();
  if (!displays.length) {
    const primary = screen.getPrimaryDisplay();
    return {
      id: VIRTUAL_DISPLAY_ID,
      bounds: primary ? primary.bounds : { x: 0, y: 0, width: 1920, height: 1080 },
      displayRects: primary ? normalizeVirtualDisplayRects([primary], primary.bounds.x, primary.bounds.y) : [],
    };
  }

  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;

  displays.forEach((display) => {
    const b = display.bounds;
    minX = Math.min(minX, b.x);
    minY = Math.min(minY, b.y);
    maxX = Math.max(maxX, b.x + b.width);
    maxY = Math.max(maxY, b.y + b.height);
  });

  return {
    id: VIRTUAL_DISPLAY_ID,
    bounds: {
      x: minX,
      y: minY,
      width: Math.max(1, maxX - minX),
      height: Math.max(1, maxY - minY),
    },
    displayRects: normalizeVirtualDisplayRects(displays, minX, minY),
  };
}

function getTargetDisplays() {
  if (SINGLE_ORB_MULTI_DISPLAY) {
    return [getVirtualDisplayDescriptor()];
  }

  const displays = screen.getAllDisplays();
  if (!PRIMARY_DISPLAY_ONLY) {
    return displays;
  }

  const primary = screen.getPrimaryDisplay();
  return primary ? [primary] : displays.slice(0, 1);
}

function syncOrbWindowsToDisplays() {
  const displays = getTargetDisplays();
  const activeIds = new Set(displays.map((display) => display.id));

  displays.forEach((display) => {
    const existing = orbWindows.get(display.id);
    if (existing && !existing.isDestroyed()) {
      existing.__orbDisplayId = display.id;
      existing.__orbDisplayRects = display.displayRects || null;
      existing.setBounds(display.bounds);
      if (!orbVisible && existing.isVisible()) {
        existing.hide();
      }
      return;
    }

    createOrbWindowForDisplay(display);
  });

  for (const [displayId, win] of orbWindows.entries()) {
    if (!activeIds.has(displayId)) {
      orbWindows.delete(displayId);
      if (win && !win.isDestroyed()) {
        win.close();
      }
    }
  }

  if (!activeDisplayId || !activeIds.has(activeDisplayId)) {
    const firstActiveId = displays[0]?.id ?? null;
    activeDisplayId = firstActiveId;
  }
}

function createWindows() {
  syncOrbWindowsToDisplays();
  ensureOrbListeners();
  startOrb();
  setTimeout(() => {
    writeRenderDiagnostic('main', 'opening dock station on startup');
    try {
      openDockStationWindow();
    } catch (error) {
      writeRenderDiagnostic('main', `open dock failed: ${error?.stack || error?.message || String(error)}`);
    }
    writeRenderDiagnostic('main', 'Orb window sync complete');
  }, 700);
}

ipcMain.handle('orb:cursor-move', async (_event, x, y) => sendCursorMove(x, y));
ipcMain.handle('orb-query', async (_event, text) => {
  const trimmed = String(text || '').trim();
  if (trimmed) {
    try {
      recordInteraction(trimmed, '', 'orb_query', { phase: 'user_input' });
    } catch (_error) {}
  }
  const result = await queryOrb(text);
  const responseText =
    (result && (result.response || (result.data && (result.data.response || result.data.text)) || result.text)) || '';
  if (trimmed && responseText) {
    try {
      recordInteraction(trimmed, responseText, 'orb_query', { phase: 'round_trip' });
    } catch (_error) {}
  }
  return result;
});
ipcMain.handle('orb:research', async (_event, query, domains = []) => researchOrb(query, domains));
ipcMain.handle('orb:service-control', async (_event, serviceId, action = 'status', payload = {}) => {
  const local = await handleIntegrationServiceControl(serviceId, action, payload);
  if (local !== null) {
    return local;
  }
  return serviceOrb(serviceId, action);
});
ipcMain.handle('orb:speak', async (_event, text, emotion) => speakOrb(text, emotion));
ipcMain.handle('orb:open-search', async (_event, query, mode = 'web') => {
  const url = buildSearchUrl(query, mode);
  if (!url) {
    return { ok: false, error: 'Missing query' };
  }

  await shell.openExternal(url);
  return { ok: true, url, mode };
});
ipcMain.handle('orb:dispatch-command', async (_event, command = {}) => dispatchPrimeOrbCommand(command));
ipcMain.handle('orb:listen-once', async () => listenOnce());
ipcMain.handle('orb:set-listening', async (_event, enabled) => setListening(Boolean(enabled)));
ipcMain.handle('orb:get-status', async () => {
  try {
    return await getOrbStatus();
  } catch (error) {
    return {
      ready: false,
      pending: true,
      controller_status: 'starting',
      instance_id: instanceId,
      user_data_path: userDataPath,
      error: error?.message || String(error),
    };
  }
});
ipcMain.handle('orb:discover-local-llm', async (_event, extraEndpoints = []) => discoverLocalLlm(extraEndpoints));
ipcMain.handle('orb:set-state', async (_event, setting, value) => setOrbState(setting, value));
ipcMain.handle('orb:dock-transition-complete', async (event) => {
  completeDockTransitionForSender(event.sender.id);
  return { ok: true };
});
ipcMain.handle('orb:get-visibility', async () => ({ visible: orbVisible }));
ipcMain.handle('orb:set-visibility', async (_event, visible) => {
  toggleOrbVisibility(Boolean(visible));
  return { visible: orbVisible };
});
ipcMain.handle('orb:set-skin', async (_event, imageUrl) => {
  const trimmed = typeof imageUrl === 'string' ? imageUrl.trim() : '';
  currentOrbSkin = trimmed || null;
  forwardOrbSkin();
  return { ok: true, imageUrl: currentOrbSkin };
});
ipcMain.handle('orb:set-skin-config', async (_event, config) => {
  currentOrbSkinConfig = (config && typeof config === 'object') ? config : null;
  forwardOrbSkinConfig();
  return { ok: true, config: currentOrbSkinConfig };
});
ipcMain.handle('orb:ingest-skin', async (_event, sourcePath) => {
  const trimmed = typeof sourcePath === 'string' ? sourcePath.trim() : '';
  if (!trimmed) {
    return { ok: false, error: 'Missing source path' };
  }

  const metadata = await ingestSkinWithPython(trimmed);
  currentOrbSkin = toSkinUrl(metadata.filename);
  forwardOrbSkin();

  return {
    ok: true,
    imageUrl: currentOrbSkin,
    metadata,
  };
});
ipcMain.handle('window:minimize', async (event) => {
  const orbWindow = getEventWindow(event);
  if (orbWindow && !orbWindow.isDestroyed()) {
    orbWindow.minimize();
    return true;
  }
  return false;
});
ipcMain.handle('window:close', async () => {
  const windows = getOrbWindows();
  if (!windows.length) {
    return false;
  }

  windows.forEach((win) => win.close());
  return true;
});
ipcMain.handle('window:set-ignore-mouse-events', async (event, ignore, options) => {
  const orbWindow = getEventWindow(event);
  if (orbWindow && !orbWindow.isDestroyed()) {
    setOrbMousePassthroughForWindow(orbWindow, Boolean(ignore), options || undefined);
    return true;
  }
  return false;
});
ipcMain.handle('dock-station:open', async () => {
  openDockStationWindow();
  return { ok: true };
});
ipcMain.handle('orb:open-studio', async () => {
  openStudioWindow();
  return { ok: true };
});
ipcMain.handle('orb:open-local-app', async (_event, appId) => {
  const appInfo = openLocalAppWindow(appId);
  return { ok: true, ...appInfo };
});
ipcMain.handle('orb:mesh-registry', async () => {
  const meshRoot = process.env.ORB_SHARED_MESH_ROOT;
  if (!meshRoot) return { orbs: [], error: 'ORB_SHARED_MESH_ROOT not set' };
  const toWinPath = (p) => {
    if (!p) return null;
    if (p.startsWith('/mnt/')) {
      return p.replace(/^\/mnt\/([a-z])\//i, (_, d) => `${d.toUpperCase()}:\\`).replace(/\//g, '\\');
    }
    return p;
  };
  const winMeshRoot = toWinPath(meshRoot) || meshRoot;
  const registryPath = path.join(winMeshRoot, 'manifests', 'orb_registry.json');
  try {
    const raw = fs.readFileSync(registryPath, 'utf-8');
    const registry = JSON.parse(raw);
    const orbs = (registry.orbs || []).map((orb) => {
      const exportsWin = toWinPath(orb.exports_root);
      let online = false;
      if (exportsWin) {
        try {
          const stat = fs.statSync(path.join(exportsWin, 'state_snapshots', 'heartbeat.json'));
          online = (Date.now() - stat.mtimeMs) < 5 * 60 * 1000;
        } catch (_) { online = false; }
      }
      return { instance_id: orb.instance_id, role: orb.role, online };
    });
    return { orbs };
  } catch (e) {
    return { orbs: [], error: e.message };
  }
});

ipcMain.handle('orb:crm-request', async (_event, payload = {}) => {
  const method = String(payload.method || 'GET').toUpperCase();
  const pathInput = String(payload.path || '/cali/crm/unified/status');
  const normalized = pathInput.startsWith('/cali/') ? pathInput : `/cali/${pathInput.replace(/^\/+/, '')}`;
  return requestCali(normalized, {
    method,
    query: payload.query || undefined,
    body: payload.body || undefined,
  });
});

ipcMain.handle('orb:email-request', async (_event, payload = {}) => {
  const method = String(payload.method || 'GET').toUpperCase();
  const pathInput = String(payload.path || '/emails');
  const normalized = pathInput.startsWith('/') ? pathInput : `/${pathInput}`;
  return requestSprukEmail(normalized, {
    method,
    query: payload.query || undefined,
    body: payload.body || undefined,
  });
});

ipcMain.handle('orb:chat', async (_event, text) => {
  const trimmed = String(text || '').trim();
  if (!trimmed) {
    return { ok: false, error: 'Empty message' };
  }
  const txBase = {
    timestamp: new Date().toISOString(),
    user_text_received: trimmed,
    ucm_enabled: String(process.env.ORB_ENABLE_UCM_STATUS_CHECK || '0').trim().toLowerCase() === '1',
    ucm_valid: false,
    ucm_degraded: false,
    ucm_skipped: String(process.env.ORB_ENABLE_UCM_STATUS_CHECK || '0').trim().toLowerCase() !== '1',
  };
  broadcastChatMessage(trimmed, 'user');
  try {
    recordInteraction(trimmed, '', 'desktop_chat', { phase: 'user_input' });
  } catch (_error) {}
  try {
    const integration = await runIntegrationChatCommand(trimmed);
    if (integration) {
      broadcastChatMessage(integration.responseText, 'orb');
      writeConversationProofRecord({
        prompt: trimmed,
        response: integration.responseText,
        responseData: integration?.result || {},
        status: integration?.responseText ? 'partial_success_text_only' : 'failed',
        error: integration?.responseText ? 'integration_path_no_audio_contract' : 'integration_empty_response',
      });
      writeDockTransactionRecord({
        ...txBase,
        text_reply_produced: Boolean(String(integration.responseText || '').trim()),
        governance_wrapper_used: false,
        qwen_called: false,
        kokoro_fallback_used: false,
        final_operator_visible_status: integration?.responseText ? 'text_only_integration_path' : 'failed_empty_integration_response',
      });
      try {
        recordInteraction(trimmed, integration.responseText, 'desktop_chat', { phase: 'integration_round_trip' });
      } catch (_error) {}
      return { ok: true, response: integration.responseText, data: integration.result, integration: true };
    }

    const result = await queryOrb(trimmed);
    const responseText =
      (result && (
        result.response_text ||
        result.response ||
        (result.data && (result.data.response_text || result.data.response || result.data.text)) ||
        result.text
      )) || '';
    const responseData = result?.data && typeof result.data === 'object' ? result.data : result;
    const audioPath = responseData?.audio_path || null;
    const llmRuntime = responseData?.cali_reasoning?.llm_runtime || {};
    const qwenCalled = Boolean(
      responseData?.qwen_tts_endpoint ||
      String(responseData?.tts_provider || '').toLowerCase() === 'qwen' ||
      String(responseData?.voice_package?.provider || '').toLowerCase() === 'qwen'
    );
    const kokoroFallbackUsed = Boolean(
      responseData?.tts_fallback_used ||
      String(responseData?.tts_provider || '').toLowerCase() === 'kokoro' ||
      String(responseData?.backup_engine || '').toLowerCase() === 'kokoro'
    );
    if (responseText && !responseData?._chat_forwarded) {
      broadcastChatMessage(responseText, 'orb', {
        audioPath,
        voicePackage: responseData?.voice_package || null,
        llmRuntime: llmRuntime || null,
      });
      try {
        recordInteraction(trimmed, responseText, 'desktop_chat', { phase: 'round_trip' });
      } catch (_error) {}
    }
    if (responseText && !audioPath) {
      speakOrb(responseText, 'thoughtful_warm').catch(() => {});
    }
    const hasText = Boolean(String(responseText || '').trim());
    const hasAudioPath = Boolean(responseData?.audio_path);
    const hasAudioPlayed = responseData?.audio_played === true;
    const status = hasText
      ? (hasAudioPath && hasAudioPlayed ? 'passed_text_and_audio' : 'partial_success_text_only')
      : 'failed';
    writeConversationProofRecord({
      prompt: trimmed,
      response: responseText,
      responseData,
      status,
      error: hasText ? ((hasAudioPath && hasAudioPlayed) ? '' : (responseData?.audio_error || 'audio_not_confirmed_played')) : 'empty_response',
    });
    writeDockTransactionRecord({
      ...txBase,
      text_reply_produced: hasText,
      llm_endpoint_used: String(llmRuntime.endpoint || responseData?.llm_endpoint || ''),
      governance_wrapper_used: Boolean(llmRuntime.governance_wrapper ?? responseData?.governance_wrapper_used),
      qwen_called: qwenCalled,
      qwen_status: qwenCalled ? (hasAudioPath && !kokoroFallbackUsed ? 'ok' : 'failed_or_fallback') : 'not_called',
      qwen_error: qwenCalled && (!hasAudioPath || kokoroFallbackUsed)
        ? String(responseData?.tts_primary_error || responseData?.audio_error || '')
        : '',
      qwen_audio_path: qwenCalled && !kokoroFallbackUsed ? String(audioPath || '') : '',
      kokoro_fallback_used: kokoroFallbackUsed,
      playback_success: hasAudioPlayed,
      playback_failure: hasAudioPlayed ? '' : String(responseData?.audio_error || (hasAudioPath ? 'audio_not_confirmed_played' : 'no_audio_path')),
      final_operator_visible_status: status,
    });
    return { ok: true, response: responseText, audioPath };
  } catch (error) {
    broadcastChatMessage('Sorry Bryan, I ran into an issue with that.', 'orb');
    writeConversationProofRecord({
      prompt: trimmed,
      response: '',
      responseData: {},
      status: 'failed',
      error: error?.message || String(error),
    });
    writeDockTransactionRecord({
      ...txBase,
      text_reply_produced: false,
      qwen_called: false,
      kokoro_fallback_used: false,
      playback_success: false,
      playback_failure: error?.message || String(error),
      final_operator_visible_status: 'failed',
    });
    return { ok: false, error: error?.message || String(error) };
  }
});

app.on('ready', createWindows);

app.on('gpu-info-update', () => {
  logGpuStatus('gpu-info-update');
});

app.whenReady().then(() => {
  logGpuStatus('when-ready');
  ensureSkinVault();
  registerSkinProtocol();
  createTray();
  globalShortcut.register('CommandOrControl+Shift+Space', () => {
    listenOnce().catch(() => {});
  });
  screen.on('display-metrics-changed', () => {
    syncOrbWindowsToDisplays();
    ensureTopmost(true);
    sampleDesktopCursor();
  });
  screen.on('display-added', () => {
    syncOrbWindowsToDisplays();
    ensureTopmost(true);
    sampleDesktopCursor();
  });
  screen.on('display-removed', () => {
    syncOrbWindowsToDisplays();
    ensureTopmost(true);
    sampleDesktopCursor();
  });
});

app.on('second-instance', () => {
  const primaryOrbWindow = getPrimaryOrbWindow();
  if (!primaryOrbWindow || primaryOrbWindow.isDestroyed()) {
    return;
  }

  showOrb();
  if (process.env.ORB_OPEN_DOCK_ON_START === '1') {
    openDockStationWindow();
  }
  if (primaryOrbWindow.isMinimized()) {
    primaryOrbWindow.restore();
  }
  ensureTopmost(true);
});

app.on('browser-window-blur', () => {
  ensureTopmost(true);
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  globalShortcut.unregisterAll();
  stopWindowTracking();
  shutdownOrb();
});

app.on('activate', function () {
  if (!getOrbWindows().length) {
    createWindows();
  }
});
