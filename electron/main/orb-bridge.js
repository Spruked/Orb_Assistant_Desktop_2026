const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const readline = require('readline');
const { EventEmitter } = require('events');
const { SKGWorker } = require('./skg-worker');

function resolvePythonPath() {
    if (process.env.ORB_PYTHON_PATH) {
        return process.env.ORB_PYTHON_PATH;
    }
    if (process.platform === 'win32') {
        const localAppData = process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local');
        const knownVenv = 'R:\\R_Drive_Substrate\\Services\\qwen_tts_312\\Scripts\\python.exe';
        const candidates = [
            knownVenv,
            path.join(localAppData, 'Programs', 'Python', 'Python312', 'python.exe'),
            path.join(localAppData, 'Programs', 'Python', 'Python311', 'python.exe'),
            path.join(localAppData, 'Programs', 'Python', 'Python313', 'python.exe'),
        ];
        const match = candidates.find((candidate) => fs.existsSync(candidate));
        if (match) {
            return match;
        }
    }
    return "python";
}

const pythonPath = resolvePythonPath();
const scriptPath = process.env.ORB_PYTHON_SCRIPT || path.join(__dirname, '../src/floating_assistant_orb.py');
const instanceId = process.env.ORB_INSTANCE_ID || (process.platform === 'win32' ? 'desktop' : 'wsl');
const defaultCp3Root = process.platform === 'win32' ? 'R:\\cochlear_processor_3.0' : '/mnt/r/cochlear_processor_3.0';
let orbProcess = null;
const orbEvents = new EventEmitter();
const pendingRequests = new Map();
let nextRequestId = 1;
const verboseBridgeLogging = process.env.ORB_BRIDGE_LOGGING === '1';
const useSKGWorker = process.env.ORB_USE_SKG_WORKER === '1';
let processStreamGuardsInstalled = false;
let skgWorker = null;
const stderrRing = [];
const STDERR_RING_LIMIT = 40;

function getSKGWorker() {
    if (!skgWorker) {
        skgWorker = new SKGWorker();
    }
    return skgWorker;
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

function safeConsole(method, ...args) {
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

function bridgeLog(method, ...args) {
    if (!verboseBridgeLogging) {
        return;
    }
    safeConsole(method, ...args);
}

function attachStreamGuard(stream, label, onBrokenPipe = null) {
    if (!stream || typeof stream.on !== 'function') {
        return;
    }
    stream.on('error', (error) => {
        if (isBrokenPipeError(error)) {
            if (typeof onBrokenPipe === 'function') {
                try {
                    onBrokenPipe(error);
                } catch (_) {
                    // Never let telemetry about a broken pipe crash the app.
                }
            }
            return;
        }
        bridgeLog('error', `Orb Bridge stream error [${label}]:`, error);
    });
}

function installProcessStreamGuards() {
    if (processStreamGuardsInstalled) {
        return;
    }

    attachStreamGuard(process.stdout, 'process_stdout', (error) => {
        emitStructuredMessage({
            type: 'bridge_stream_warning',
            data: {
                label: 'process_stdout',
                code: error.code || 'EPIPE',
                message: error.message || 'Broken pipe detected'
            }
        });
    });

    attachStreamGuard(process.stderr, 'process_stderr', (error) => {
        emitStructuredMessage({
            type: 'bridge_stream_warning',
            data: {
                label: 'process_stderr',
                code: error.code || 'EPIPE',
                message: error.message || 'Broken pipe detected'
            }
        });
    });

    processStreamGuardsInstalled = true;
}

installProcessStreamGuards();

function emitStructuredMessage(payload) {
    orbEvents.emit('message', payload);
}

function createRequestId(prefix = 'orb') {
    const requestId = `${instanceId}-${prefix}-${Date.now()}-${nextRequestId}`;
    nextRequestId += 1;
    return requestId;
}

function rejectPendingRequests(error) {
    for (const [requestId, pending] of pendingRequests.entries()) {
        clearTimeout(pending.timeoutId);
        pending.reject(error);
        pendingRequests.delete(requestId);
    }
}

function resolvePendingRequest(message) {
    const requestId = message?.request_id;
    if (!requestId || !pendingRequests.has(requestId)) {
        return false;
    }

    const pending = pendingRequests.get(requestId);
    if (pending.responseType && pending.responseType !== message.type) {
        return false;
    }

    clearTimeout(pending.timeoutId);
    pendingRequests.delete(requestId);
    pending.resolve(message.data ?? message);
    return true;
}

function handlePythonStdout(line) {
    const text = line.trim();
    if (!text) {
        return;
    }

    bridgeLog('log', `Python: ${text}`);

    try {
        const payload = JSON.parse(text);
        emitStructuredMessage(payload);
        resolvePendingRequest(payload);
        return;
    } catch (error) {
        emitStructuredMessage({ type: 'stdout', data: { text } });
    }
}

function handlePythonStderr(line) {
    const text = line.trim();
    if (!text) {
        return;
    }
    stderrRing.push(text);
    if (stderrRing.length > STDERR_RING_LIMIT) {
        stderrRing.shift();
    }

    bridgeLog('warn', `Python Error: ${text}`);

    const hysteresisMatch = text.match(/Hysteresis active: trigger (\d+) -> release (\d+)/i);
    if (hysteresisMatch) {
        emitStructuredMessage({
            type: 'hysteresis',
            data: {
                triggerThreshold: Number(hysteresisMatch[1]),
                releaseThreshold: Number(hysteresisMatch[2]),
                raw: text
            }
        });
        return;
    }

    emitStructuredMessage({ type: 'stderr', data: { text } });
}

function wirePythonProcessIO(childProcess) {
    attachStreamGuard(childProcess.stdin, 'stdin', (error) => {
        emitStructuredMessage({
            type: 'bridge_stream_warning',
            data: {
                label: 'stdin',
                code: error.code || 'EPIPE',
                message: error.message || 'Broken pipe detected'
            }
        });
    });
    attachStreamGuard(childProcess.stdout, 'stdout', (error) => {
        emitStructuredMessage({
            type: 'bridge_stream_warning',
            data: {
                label: 'stdout',
                code: error.code || 'EPIPE',
                message: error.message || 'Broken pipe detected'
            }
        });
    });
    attachStreamGuard(childProcess.stderr, 'stderr', (error) => {
        emitStructuredMessage({
            type: 'bridge_stream_warning',
            data: {
                label: 'stderr',
                code: error.code || 'EPIPE',
                message: error.message || 'Broken pipe detected'
            }
        });
    });
    readline.createInterface({ input: childProcess.stdout }).on('line', handlePythonStdout);
    readline.createInterface({ input: childProcess.stderr }).on('line', handlePythonStderr);
}

function sendOrbCommand(message) {
    startOrb();

    if (!orbProcess || orbProcess.killed) {
        bridgeLog('warn', 'Orb Bridge: Cannot send command, orb process is not running');
        return false;
    }

    if (!orbProcess.stdin || orbProcess.stdin.destroyed) {
        bridgeLog('warn', 'Orb Bridge: Cannot send command, orb stdin is unavailable');
        return false;
    }

    try {
        orbProcess.stdin.write(`${JSON.stringify(message)}\n`);
        return true;
    } catch (error) {
        if (isBrokenPipeError(error)) {
            emitStructuredMessage({
                type: 'bridge_write_failed',
                data: {
                    code: error.code || 'EPIPE',
                    message: error.message || 'Broken pipe while writing to orb stdin'
                }
            });
            return false;
        }
        throw error;
    }
}

function sendOrbRequest(message, responseType, timeoutMs = 15000) {
    const requestId = createRequestId(message?.type || 'orb');
    const payload = { ...message, request_id: requestId };

    return new Promise((resolve, reject) => {
        const timeoutId = setTimeout(() => {
            pendingRequests.delete(requestId);
            reject(new Error(`Timed out waiting for ${responseType}`));
        }, timeoutMs);

        pendingRequests.set(requestId, { resolve, reject, responseType, timeoutId });

        if (!sendOrbCommand(payload)) {
            clearTimeout(timeoutId);
            pendingRequests.delete(requestId);
            reject(new Error('Orb process is not running'));
        }
    });
}

function toWSLPath(winPath) {
    return winPath
        .replace(/^([A-Za-z]):[\\\/]/, (_, d) => `/mnt/${d.toLowerCase()}/`)
        .replace(/\\/g, '/');
}

function resolveSpawnTarget(pyPath, sPath) {
    if (process.platform === 'win32' && pyPath.startsWith('/')) {
        return { exe: 'wsl.exe', args: ['env', ...getWslBridgeEnvArgs(), pyPath, '-u', toWSLPath(sPath)] };
    }
    return { exe: pyPath, args: ['-u', sPath] };
}

function getWslBridgeEnvArgs() {
    const prefixes = [
        'ORB_',
        'CP3_',
        'KOKORO_',
        'ONNX_',
    ];
    const exact = new Set([
        'OMP_NUM_THREADS',
        'MKL_NUM_THREADS',
        'OPENBLAS_NUM_THREADS',
        'NUMEXPR_MAX_THREADS',
        'UV_THREADPOOL_SIZE',
        'CALI_UCM_ENABLED',
    ]);
    return Object.entries(process.env)
        .filter(([key, value]) => value !== undefined && value !== null && value !== '')
        .filter(([key]) => exact.has(key) || prefixes.some((prefix) => key.startsWith(prefix)))
        .map(([key, value]) => `${key}=${value}`);
}

function startOrb() {
    if (orbProcess && !orbProcess.killed) {
        return orbProcess;
    }

    const { exe, args } = resolveSpawnTarget(pythonPath, scriptPath);
    bridgeLog('log', 'Orb Bridge: Spawning:', exe, args[0]);
    bridgeLog('log', 'Orb Bridge: Instance:', instanceId);

    orbProcess = spawn(exe, args, {
        // Python reads JSON-line commands from stdin, so stdin must stay piped.
        stdio: ['pipe', 'pipe', 'pipe'],
        cwd: path.join(__dirname, '../src'),
        env: {
            ...process.env,
            ORB_INSTANCE_ID: instanceId,
            CP3_ROOT: process.env.CP3_ROOT || defaultCp3Root,
        }
    });

    wirePythonProcessIO(orbProcess);

    orbProcess.on('error', (error) => {
        bridgeLog('error', 'Orb Bridge: Python process failed to start:', error);
        rejectPendingRequests(error);
        emitStructuredMessage({
            type: 'bridge_spawn_error',
            data: {
                code: error.code || 'SPAWN_ERROR',
                message: error.message || String(error)
            }
        });
        orbProcess = null;
    });

    orbProcess.on('close', (code, signal) => {
        bridgeLog('log', `Orb Bridge: Python process exited (code=${code}, signal=${signal})`);
        const tail = stderrRing.slice(-8);
        const reasonSuffix = tail.length ? ` | stderr_tail=${tail.join(' || ')}` : '';
        rejectPendingRequests(new Error(`Orb process exited (code=${code}, signal=${signal})${reasonSuffix}`));
        emitStructuredMessage({ type: 'bridge_exit', data: { code, signal } });
        orbProcess = null;
    });

    return orbProcess;
}

function sendCursorMove(x, y) {
    return sendOrbCommand({ type: 'cursor_move', x, y });
}

function queryOrb(text) {
    if (useSKGWorker) {
        return getSKGWorker()
            .query({ query: text, text })
            .catch((error) => {
                bridgeLog('warn', `SKG worker query failed, falling back to orb bridge: ${error.message}`);
                return sendOrbRequest({ type: 'query', text }, 'query_result', 90000);
            });
    }
    return sendOrbRequest({ type: 'query', text }, 'query_result', 90000);
}

function listenOnce() {
    return sendOrbRequest({ type: 'listen_once' }, 'listen_once_ack', Number(process.env.ORB_LISTEN_ONCE_TIMEOUT_MS || 60000));
}

function setListening(enabled) {
    return sendOrbRequest(
        { type: 'set_listening', enabled: Boolean(enabled) },
        'listening_mode',
        15000
    );
}

function getOrbStatus() {
    // Cold starts can exceed 20s when CUDA/voice/presence subsystems initialize.
    return sendOrbRequest({ type: 'get_status' }, 'status_response', 180000);
}

function researchOrb(query, domains = []) {
    return sendOrbRequest({ type: 'research', query, domains }, 'research_result', 60000);
}

function serviceOrb(serviceId, action = 'status') {
    return sendOrbRequest(
        { type: 'service_control', service_id: serviceId, action },
        'service_result',
        20000
    );
}

function speakOrb(text, emotion = 'thoughtful_warm') {
    return sendOrbRequest({ type: 'speak', text, emotion }, 'speak_result', Number(process.env.ORB_SPEAK_TIMEOUT_MS || 120000));
}

function setOrbState(setting, value) {
    return sendOrbRequest(
        { type: 'set_orb_state', setting, value },
        'orb_state_result',
        15000
    );
}

function shutdownOrb() {
    return sendOrbCommand({ type: 'shutdown' });
}

function onOrbMessage(handler) {
    orbEvents.on('message', handler);
}

function offOrbMessage(handler) {
    orbEvents.off('message', handler);
}

module.exports = {
    startOrb,
    sendOrbCommand,
    sendCursorMove,
    queryOrb,
    listenOnce,
    setListening,
    getOrbStatus,
    researchOrb,
    serviceOrb,
    speakOrb,
    setOrbState,
    shutdownOrb,
    onOrbMessage,
    offOrbMessage
};
