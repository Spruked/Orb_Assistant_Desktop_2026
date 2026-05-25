const { useEffect, useMemo, useRef, useState } = React;
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');
const CompanionIntent = require('./interface/companion_intent');
const FieldMotion = require('./hlsf_geometry/field_motion');
const rand = (min, max) => Math.random() * (max - min) + min;
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const lerp = (a, b, t) => a + (b - a) * t;
const parseEnvInt = (name, fallback, min = null, max = null) => {
  const raw = process?.env?.[name];
  if (raw === undefined || raw === null || raw === '') {
    return fallback;
  }

  const parsed = Number.parseInt(String(raw), 10);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }

  const boundedMin = min === null ? parsed : Math.max(min, parsed);
  return max === null ? boundedMin : Math.min(max, boundedMin);
};

const parseEnvFloat = (name, fallback, min = null, max = null) => {
  const raw = process?.env?.[name];
  if (raw === undefined || raw === null || raw === '') {
    return fallback;
  }

  const parsed = Number.parseFloat(String(raw));
  if (!Number.isFinite(parsed)) {
    return fallback;
  }

  const boundedMin = min === null ? parsed : Math.max(min, parsed);
  return max === null ? boundedMin : Math.min(max, boundedMin);
};

const ORB_DIAMETER = 112;
const ORB_RADIUS = ORB_DIAMETER / 2;
const ORB_MARGIN = 86;
const ORB_CURSOR_CLEARANCE_EXTRA_PX = parseEnvInt('ORB_CURSOR_CLEARANCE_EXTRA_PX', 0, 0, 400);
const ORB_MIN_CURSOR_CLEARANCE = ORB_RADIUS + 52 + ORB_CURSOR_CLEARANCE_EXTRA_PX;
const ORB_CURSOR_COMFORT_RADIUS = ORB_RADIUS + 138 + ORB_CURSOR_CLEARANCE_EXTRA_PX;
const ORB_CURSOR_PANIC_RADIUS = ORB_MIN_CURSOR_CLEARANCE + 18;
const ORB_AUTONOMOUS_WAYPOINT_MIN_DISTANCE = 150;
const ORB_AUTONOMOUS_WAYPOINT_MAX_DISTANCE = 420;
const ORB_AUTONOMOUS_RETARGET_INTERVAL_MS = 9800;
const ORB_AUTONOMOUS_RETARGET_INTERVAL_IDLE_MAX_MS = 16000;
const ORB_AUTONOMOUS_FORCE_RETARGET_BASE_MS = 7200;
const ORB_AUTONOMOUS_FORCE_RETARGET_IDLE_MS = 11200;
const ORB_CURSOR_REACTION_COOLDOWN_MS = 480;
const ORB_RETARGET_STABILITY_WINDOW_MS = 1400;
const ORB_INTERACTION_RADIUS = 54;
const ORB_SMOOTHING = 0.12;
const ORB_SNAP_DISTANCE = 1.5;
const ORB_DIRECTION_EPSILON = 2;
const ORB_DEFAULT_TRAIL_DIRECTION = { x: -0.9, y: -0.42 };
const ORB_RETARGET_DISTANCE = 36;
const ORB_VISUAL_MODE_LOCK = '';
const ORB_AUTONOMOUS_BASE_SPEED = 0.72;
const ORB_AUTONOMOUS_IDLE_SPEED_BONUS = 0.06;
const ORB_STEER_BLEND = 0.055;
const ORB_CURSOR_REPEL_RADIUS = ORB_CURSOR_COMFORT_RADIUS + 12;
const ORB_CURSOR_LEASH_MIN = ORB_CURSOR_COMFORT_RADIUS - 18;
const ORB_CURSOR_LEASH_MAX = ORB_CURSOR_COMFORT_RADIUS + 116;
const ORB_EDGE_REPEL_DISTANCE = 150;
const ORB_EDGE_REPEL_GAIN = 1.35;
const ORB_CENTER_RECOVERY_GAIN = 0.65;
const ORB_HARD_ESCAPE_CLEARANCE = ORB_MIN_CURSOR_CLEARANCE - 8;
const ORB_MAX_ACCELERATION = 0.065;
const ORB_VELOCITY_DAMPING = 0.986;
const ORB_HOME_X_RATIO = parseEnvFloat('ORB_HOME_X_RATIO', 0.5, 0.1, 0.9);
const ORB_HOME_Y_RATIO = parseEnvFloat('ORB_HOME_Y_RATIO', 0.5, 0.1, 0.9);
const ORB_CALM_SCREEN_ANCHOR = process?.env?.ORB_CALM_SCREEN_ANCHOR !== '0';
const ORB_SCREEN_ANCHOR_X_RATIO = parseEnvFloat('ORB_SCREEN_ANCHOR_X_RATIO', 0.68, 0.15, 0.85);
const ORB_SCREEN_ANCHOR_Y_RATIO = parseEnvFloat('ORB_SCREEN_ANCHOR_Y_RATIO', 0.36, 0.15, 0.85);
const ORB_CURSOR_FOLLOW = process?.env?.ORB_CURSOR_FOLLOW === '1';
const ORB_CURSOR_FOLLOW_OFFSET_X = parseEnvInt('ORB_CURSOR_FOLLOW_OFFSET_X', 120, -500, 500);
const ORB_CURSOR_FOLLOW_OFFSET_Y = parseEnvInt('ORB_CURSOR_FOLLOW_OFFSET_Y', -90, -500, 500);
const ORB_CURSOR_FOLLOW_LERP = parseEnvFloat('ORB_CURSOR_FOLLOW_LERP', 0.026, 0.008, 0.08);
const ORB_CURSOR_REANCHOR_DISTANCE = parseEnvInt('ORB_CURSOR_REANCHOR_DISTANCE', 960, 360, 2600);
const ORB_CURSOR_REANCHOR_SETTLE_DISTANCE = parseEnvInt('ORB_CURSOR_REANCHOR_SETTLE_DISTANCE', 140, 32, 260);
const ORB_COMPANION_MODE = process?.env?.ORB_COMPANION_MODE !== '0';
const ORB_COMPANION_BOND_RADIUS = parseEnvInt('ORB_COMPANION_BOND_RADIUS', 420, 200, 1200);
const ORB_COMPANION_RETURN_DISTANCE = parseEnvInt('ORB_COMPANION_RETURN_DISTANCE', 980, 500, 2600);
const ORB_COMPANION_USER_ACTIVE_MS = parseEnvInt('ORB_COMPANION_USER_ACTIVE_MS', 1800, 400, 10000);
const ORB_PLAYFUL_IDLE_ENABLED = process?.env?.ORB_PLAYFUL_IDLE_ENABLED === '1';
const ORB_MULTI_DISPLAY_PATROL = process?.env?.ORB_MULTI_DISPLAY_PATROL !== '0';
const ORB_MULTI_DISPLAY_PATROL_INTERVAL_MS = parseEnvInt('ORB_MULTI_DISPLAY_PATROL_INTERVAL_MS', 8500, 2500, 60000);
const ORB_MULTI_DISPLAY_PATROL_SPEED_BONUS = parseEnvFloat('ORB_MULTI_DISPLAY_PATROL_SPEED_BONUS', 0.55, 0, 4);
const ORB_DOCK_TRANSITION_TOTAL_MS = 420;
const ORB_DOCK_TRANSITION_ACK_MS = 90;
const ORB_DOCK_TRANSITION_TRAVEL_MS = 220;
const ORB_DOCK_TRANSITION_LOCK_MS = 110;
const ORB_SWARM_HUD_ENABLED = process?.env?.ORB_SWARM_HUD === '1';

// Radial gradients for CSS-config-based skins (used when no image skin is set)
const SKIN_CONFIG_GRADIENTS = {
  cyber:  'radial-gradient(circle at 38% 32%, #c0ffff 0%, #00e5ff 22%, #b829dd 65%, #0e001e 100%)',
  sunset: 'radial-gradient(circle at 38% 32%, #fff4a0 0%, #ff9f43 30%, #ff6b6b 65%, #2e0010 100%)',
  forest: 'radial-gradient(circle at 38% 32%, #b0fff0 0%, #00cec9 30%, #00b894 65%, #002018 100%)',
  neon:   'radial-gradient(circle at 38% 32%, #ffffff 0%, #80ffb0 22%, #ff0080 65%, #120016 100%)',
  cosmic: 'radial-gradient(circle at 38% 32%, #e0d0ff 0%, #8a6cdd 30%, #4169e1 65%, #000820 100%)',
  fire:   'radial-gradient(circle at 38% 32%, #fff0a0 0%, #ff8c00 28%, #ff4500 65%, #180000 100%)',
  ice:    'radial-gradient(circle at 38% 32%, #ffffff 0%, #e8f8ff 30%, #87ceeb 65%, #0e2030 100%)',
  plasma: 'radial-gradient(circle at 38% 32%, #ffffff 0%, #80e8ff 22%, #ff1493 65%, #080010 100%)',
};

const LOGIC_VISUALS = {
  deductive: {
    label: 'Deductive',
    tone: 'Logic guard',
    color: '#67c6ff',
    aura: 'rgba(103, 198, 255, 0.32)',
    hueRotate: 0,
    brightness: 0.96,
  },
  inductive: {
    label: 'Inductive',
    tone: 'Learning drift',
    color: '#63e6a6',
    aura: 'rgba(99, 230, 166, 0.3)',
    hueRotate: 42,
    brightness: 1.02,
  },
  intuitive: {
    label: 'Intuitive',
    tone: 'Pattern lock',
    color: '#f5c96a',
    aura: 'rgba(245, 201, 106, 0.34)',
    hueRotate: -20,
    brightness: 1.08,
  },
};

function modeFromCognitiveMode(cognitiveMode) {
  const mode = String(cognitiveMode || '').toUpperCase();
  if (mode.includes('INTUITION')) return 'intuitive';
  if (mode.includes('HABIT')) return 'inductive';
  return 'deductive';
}

const PRIME_SWARM_COUNTS = [2, 3, 5, 7, 11];

const SWARM_TIMING = {
  // Phase order: out_spin -> out_dart -> in_arc -> in_loop -> ingest.
  phaseMs: {
    out_spin: 150,
    out_dart: 460,
    in_arc: 600,
    in_loop: 220,
    ingest: 300,
  },
  modeMultiplier: {
    research: 1,
    diagnostics: 0.88,
  },
  launchSpacingMs: {
    research: { outbound: 44, inbound: 38 },
    diagnostics: { outbound: 34, inbound: 30 },
  },
};

const SWARM_RIPPLE_MS = 320;
const MICRO_ORB_ASPECT_RATIO = 0.6; // compressed shard sphere look
const MICRO_ORB_BASE_SIZE = 25; // larger deployment visibility
const MICRO_ORB_OUTBOUND_SPIN_SIZE = MICRO_ORB_BASE_SIZE;
const MICRO_ORB_OUTBOUND_DART_SIZE = MICRO_ORB_BASE_SIZE;
const SWARM_OUTBOUND_COLORS = {
  research: '#4cb9ff',
  diagnostics: '#ff4b4b',
};
const SWARM_RESULT_COLORS = {
  success: '#63ef9e',
  warning: '#ffb347',
  fault: '#ff4b4b',
};

let MICRO_ORB_TEXTURE_URL = null;
try {
  const texturePath = path.join(__dirname, '..', '..', 'swarm', 'microorb.jprg.jpg');
  if (fs.existsSync(texturePath)) {
    MICRO_ORB_TEXTURE_URL = pathToFileURL(texturePath).href;
  }
} catch (_error) {
  MICRO_ORB_TEXTURE_URL = null;
}

const easeOutExpo = (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t));
const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);

function normalizeMissionMode(mode = 'research') {
  return String(mode || 'research').toLowerCase() === 'diagnostics' ? 'diagnostics' : 'research';
}

function getSwarmPhaseDurationMs(phase, missionMode = 'research') {
  const normalizedMode = normalizeMissionMode(missionMode);
  const baseMs = SWARM_TIMING.phaseMs[phase] || 160;
  const modeScale = SWARM_TIMING.modeMultiplier[normalizedMode] || 1;
  return Math.max(90, Math.round(baseMs * modeScale));
}

function classifySwarmResult(result = {}) {
  const data = result?.data || result || {};
  const hasFault = Boolean(
    data?.error ||
    data?.status === 'error' ||
    data?.research_synthesis?.error
  );
  if (hasFault) {
    return 'fault';
  }
  const confidence = Number(
    data?.confidence ??
    data?.advisory_verdict?.confidence ??
    data?.cali_reasoning?.advisory_verdict?.confidence ??
    0.95
  );
  const warning = Boolean(
    (Array.isArray(data?.warnings) && data.warnings.length) ||
    data?.advisory_verdict?.tension_detected ||
    confidence < 0.65
  );
  return warning ? 'warning' : 'success';
}

function choosePrimeSwarmCount(complexity = 0.45) {
  const normalized = clamp(Number(complexity) || 0, 0, 1);
  if (normalized < 0.2) return PRIME_SWARM_COUNTS[0];
  if (normalized < 0.4) return PRIME_SWARM_COUNTS[1];
  if (normalized < 0.62) return PRIME_SWARM_COUNTS[2];
  if (normalized < 0.82) return PRIME_SWARM_COUNTS[3];
  return PRIME_SWARM_COUNTS[4];
}

function normalizeToApprovedPrimeSet(value, fallback = PRIME_SWARM_COUNTS[2]) {
  const n = Number(value);
  if (!Number.isFinite(n)) {
    return fallback;
  }
  const candidate = Math.max(2, Math.trunc(n));
  const resolved = PRIME_SWARM_COUNTS.find((p) => p >= candidate);
  return resolved || PRIME_SWARM_COUNTS[PRIME_SWARM_COUNTS.length - 1];
}

function normalizePrimeCount(value, fallback = PRIME_SWARM_COUNTS[2]) {
  return normalizeToApprovedPrimeSet(value, fallback);
}

function resolvePrimeSwarmLineage(requestedCount, fallback = PRIME_SWARM_COUNTS[2]) {
  const resolvedCount = normalizePrimeCount(requestedCount, fallback);
  const requestedNumeric = Number(requestedCount);
  const requestedFinite = Number.isFinite(requestedNumeric);
  const requestedPrime = requestedFinite && PRIME_SWARM_COUNTS.includes(Math.trunc(requestedNumeric));
  const normalized = !requestedPrime || requestedNumeric !== resolvedCount;
  const canonicalPrimeSet = PRIME_SWARM_COUNTS.slice();
  return {
    requestedCount: requestedFinite ? requestedNumeric : null,
    resolvedCount,
    requestedPrime,
    normalized,
    canonicalPrimeSet,
    lineageToken: `prime-swarm:${resolvedCount}`,
  };
}

function queryComplexityScore(query = '', mode = 'research') {
  const words = String(query || '').trim().split(/\s+/).filter(Boolean).length;
  const base = clamp(words / 22, 0, 1);
  const modeBoost = String(mode || '').toLowerCase() === 'diagnostics' ? 0.12 : 0.04;
  return clamp(base + modeBoost, 0, 1);
}

function extractRequestedSwarmCountFromQuery(query = '') {
  const text = String(query || '');
  const match = text.match(/\b(\d{1,7})\b/);
  if (!match) return null;
  const parsed = Number(match[1]);
  if (!Number.isFinite(parsed)) return null;
  return Math.max(2, Math.trunc(parsed));
}

const DIAGNOSTIC_INTENT_TERMS = [
  'diagnose', 'diagnostic', 'debug', 'status', 'health', 'repair', 'fix',
  'error', 'fault', 'failure', 'broken', 'not starting', 'not responding',
  'not working', 'why is', 'slow', 'check if', 'check status', 'check why',
  'service', 'process', 'port', 'log', 'env', 'path', 'boot', 'runtime',
  'import', 'endpoint', 'container', 'docker', 'wsl', 'mount', 'fail',
  'scan logs', 'scan ports', 'scan service',
];

const DIAGNOSTIC_FAILURE_TERMS = [
  'why is', 'not working', 'not responding', 'not starting', 'slow',
  'error', 'fault', 'failure', 'fail', 'failed', 'failing', 'broken',
  'repair', 'fix', 'broke',
];

const RESEARCH_INTENT_TERMS = [
  'research', 'find', 'compare', 'verify', 'investigate', 'summarize',
  'look up', 'search', 'docs', 'documentation', 'repo', 'sources',
  'what changed', 'analyze files', 'summarize docs',
];

function countIntentTerms(query = '', terms = []) {
  const text = String(query || '').toLowerCase();
  return terms.reduce((score, term) => (text.includes(term) ? score + 1 : score), 0);
}

function classifySwarmMission({ query = '', requestedMode = '', complexity = null } = {}) {
  const normalizedMode = String(requestedMode || '').trim().toLowerCase();
  const text = String(query || '').trim();
  const lower = text.toLowerCase();
  const failureScore = countIntentTerms(lower, DIAGNOSTIC_FAILURE_TERMS);

  let missionMode = null;
  // Precedence rule: any failure/repair language forces diagnostics.
  if (failureScore >= 1) {
    missionMode = 'diagnostics';
  } else if (normalizedMode === 'research' || normalizedMode === 'diagnostics') {
    missionMode = normalizedMode;
  } else {
    const diagnosticScore = countIntentTerms(lower, DIAGNOSTIC_INTENT_TERMS);
    const researchScore = countIntentTerms(lower, RESEARCH_INTENT_TERMS);
    if (diagnosticScore >= 1) {
      missionMode = 'diagnostics';
    } else if (researchScore >= 1) {
      missionMode = 'research';
    }
  }

  if (!missionMode) {
    return {
      deploy: false,
      missionMode: null,
      complexity: 0,
      swarmCount: null,
    };
  }

  const inferredComplexity = queryComplexityScore(text, missionMode);
  const normalizedComplexity = Number.isFinite(Number(complexity))
    ? clamp(Number(complexity), 0, 1)
    : inferredComplexity;

  return {
    deploy: true,
    missionMode,
    complexity: normalizedComplexity,
    swarmCount: choosePrimeSwarmCount(normalizedComplexity),
  };
}

function getDeployZoneCenterAngle(zone = 'around') {
  switch (String(zone || 'around').toLowerCase()) {
    case 'left': return Math.PI;
    case 'right': return 0;
    case 'top': return -Math.PI / 2;
    case 'bottom': return Math.PI / 2;
    default: return null;
  }
}

function getSpreadAngle(index, count, zone = 'around') {
  const n = Math.max(1, Number(count) || 1);
  const z = String(zone || 'around').toLowerCase();
  if (z === 'around') {
    return ((index / n) * Math.PI * 2) + rand(-0.12, 0.12);
  }
  const center = getDeployZoneCenterAngle(z);
  const spread = Math.PI / 3; // 60deg fan
  const t = n <= 1 ? 0.5 : (index / (n - 1));
  const offset = (t - 0.5) * spread;
  return center + offset + rand(-0.05, 0.05);
}

function makeOutboundSwarmNodes(count = PRIME_SWARM_COUNTS[2], mission = {}, egf = {}) {
  const now = Date.now();
  const normalizedCount = normalizePrimeCount(count);
  const missionMode = normalizeMissionMode(mission.mode);
  const color = mission.color || SWARM_OUTBOUND_COLORS[missionMode];
  const centerEntropy = clamp(Number(egf?.center_entropy || 0), 0, 2);
  const spinBase = getSwarmPhaseDurationMs('out_spin', missionMode);
  const spinDurationMs = clamp(Math.round(spinBase - centerEntropy * 25), 120, spinBase);
  const launchSpacingMs = SWARM_TIMING.launchSpacingMs[missionMode]?.outbound || 44;

  return Array.from({ length: normalizedCount }, (_, index) => {
    const angle = getSpreadAngle(index, normalizedCount, mission.deployZone || 'around');
    const outboundDistance = 200 + Math.random() * 120;
    return {
      id: `${now}-${index}-${Math.random().toString(16).slice(2)}`,
      phase: 'out_spin',
      progress: 0,
      phaseStartedAt: now,
      launchDelayMs: index * launchSpacingMs,
      dynamicPhaseMs: {
        out_spin: spinDurationMs,
      },
      routeAngle: angle,
      outboundDistance,
      arcAmplitude: 6 + Math.random() * 8,
      missionMode,
      resultState: 'pending',
      color,
      returning: false,
      arcDirection: 1,
      egf: {
        outerEntropy: clamp(Number(egf?.outer_entropy || 0), 0, 2),
        renewalPressure: clamp(Number(egf?.renewal_pressure || 0), 0, 1),
      },
    };
  });
}

function makeInboundSwarmNodes(count = PRIME_SWARM_COUNTS[2], mission = {}, resultState = 'success', egf = {}) {
  const now = Date.now();
  const normalizedCount = normalizePrimeCount(count);
  const missionMode = normalizeMissionMode(mission.mode);
  const launchSpacingMs = SWARM_TIMING.launchSpacingMs[missionMode]?.inbound || 38;
  const color = mission.color || SWARM_RESULT_COLORS[resultState] || SWARM_RESULT_COLORS.success;
  return Array.from({ length: normalizedCount }, (_, index) => ({
    id: `${now}-return-${index}-${Math.random().toString(16).slice(2)}`,
    phase: 'in_arc',
    progress: 0,
    phaseStartedAt: now,
    launchDelayMs: index * launchSpacingMs,
    routeAngle: getSpreadAngle(index, normalizedCount, mission.deployZone || 'around'),
    outboundDistance: 210 + Math.random() * 90,
    arcAmplitude: 30 + Math.random() * 30,
    loopRadius: 10 + Math.random() * 6,
    missionMode,
    resultState,
    color,
    returning: true,
    arcDirection: index % 2 === 0 ? 1 : -1,
    egf: {
      outerEntropy: clamp(Number(egf?.outer_entropy || 0), 0, 2),
      renewalPressure: clamp(Number(egf?.renewal_pressure || 0), 0, 1),
    },
  }));
}

function nodeVector(node) {
  const unitX = Math.cos(node.routeAngle);
  const unitY = Math.sin(node.routeAngle);
  const nearRadius = 14;
  const farRadius = node.outboundDistance;
  const loopRadius = node.loopRadius;
  const p = clamp(node.progress, 0, 1);
  const color = node.color || SWARM_OUTBOUND_COLORS.research;
  const modeColor = node.resultState && node.resultState !== 'pending'
    ? (SWARM_RESULT_COLORS[node.resultState] || color)
    : color;
  const outerEntropy = clamp(Number(node?.egf?.outerEntropy || 0), 0, 2);
  const renewalPressure = clamp(Number(node?.egf?.renewalPressure || 0), 0, 1);

  if (node.phase === 'out_spin') {
    const theta = p * Math.PI * 2 + node.routeAngle;
    const radius = nearRadius;
    return {
      x: Math.cos(theta) * radius,
      y: Math.sin(theta) * radius,
      size: MICRO_ORB_OUTBOUND_SPIN_SIZE,
      opacity: 0.95,
      color: modeColor,
      trailOpacity: 0.32,
      trailLength: ORB_DIAMETER * rand(0.4, 0.7),
    };
  }

  if (node.phase === 'out_dart') {
    const eased = easeOutExpo(p);
    const x = lerp(unitX * nearRadius, farRadius, eased);
    const y = lerp(unitY * nearRadius, unitY * node.arcAmplitude, eased * 0.45);
    return {
      x,
      y,
      size: MICRO_ORB_OUTBOUND_DART_SIZE,
      opacity: 0.92,
      color: modeColor,
      trailOpacity: 0.42,
      trailLength: ORB_DIAMETER * rand(0.45, 0.7),
    };
  }

  if (node.phase === 'in_arc') {
    const eased = easeOutCubic(p);
    const baseX = lerp(-farRadius, nearRadius * 0.92, eased);
    const arc = node.arcDirection * node.arcAmplitude * Math.sin((1 - p) * Math.PI);
    const wobbleBase = (node.resultState === 'warning' ? 1.1 : node.resultState === 'fault' ? 2.2 : 0.2);
    const wobbleGain = 1 + outerEntropy * 0.8;
    const wobble = Math.sin(Date.now() / 26 + node.routeAngle * 8) * wobbleBase * wobbleGain;
    const faultJitter = node.resultState === 'fault' ? rand(-2.6, 2.6) : 0;
    return {
      x: baseX,
      y: arc + wobble + faultJitter,
      size: MICRO_ORB_BASE_SIZE,
      opacity: 0.95,
      color: modeColor,
      trailOpacity: 0.28,
      trailLength: ORB_DIAMETER * rand(0.2, 0.4),
      tetherPulse: 0.15 + renewalPressure * 0.1,
    };
  }

  if (node.phase === 'in_loop') {
    const theta = p * Math.PI * 2;
    const cx = nearRadius * 0.7;
    const cy = 0;
    return {
      x: cx + Math.cos(theta) * (loopRadius * 0.92),
      y: cy + Math.sin(theta) * (loopRadius * 0.92),
      size: MICRO_ORB_BASE_SIZE,
      opacity: 0.98,
      color: modeColor,
      trailOpacity: 0.22,
      trailLength: ORB_DIAMETER * 0.24,
    };
  }

  const ingestRadius = nearRadius * (1 - easeOutCubic(p));
  return {
    x: ingestRadius,
    y: 0,
    size: MICRO_ORB_BASE_SIZE * (1 - p),
    opacity: 1 - p,
    color: modeColor,
    trailOpacity: 0.16,
    trailLength: ORB_DIAMETER * 0.2,
  };
}

function advanceSwarmNode(node, now) {
  const phaseDelay = node.launchDelayMs || 0;
  if (phaseDelay > 0 && now < node.phaseStartedAt + phaseDelay) {
    return node;
  }

  const age = now - (node.phaseStartedAt + phaseDelay);
  const phaseDuration = node?.dynamicPhaseMs?.[node.phase] || getSwarmPhaseDurationMs(node.phase, node.missionMode);
  const progress = clamp(age / phaseDuration, 0, 1);

  if (progress < 1) {
    return { ...node, progress };
  }

  const nextAt = now;
  if (node.phase === 'out_spin') return { ...node, phase: 'out_dart', progress: 0, phaseStartedAt: nextAt, launchDelayMs: 0 };
  if (node.phase === 'out_dart') return null;
  if (node.phase === 'in_arc') return { ...node, phase: 'in_loop', progress: 0, phaseStartedAt: nextAt, launchDelayMs: 0 };
  if (node.phase === 'in_loop') return { ...node, phase: 'ingest', progress: 0, phaseStartedAt: nextAt, launchDelayMs: 0 };

  return null;
}

function getHomePosition() {
  return clampOrbPosition(
    window.innerWidth * ORB_HOME_X_RATIO,
    window.innerHeight * ORB_HOME_Y_RATIO
  );
}

function clampOrbPosition(x, y) {
  const width = window.innerWidth;
  const height = window.innerHeight;

  return {
    x: Math.min(width - ORB_MARGIN, Math.max(ORB_MARGIN, x)),
    y: Math.min(height - ORB_MARGIN, Math.max(ORB_MARGIN, y)),
  };
}

function normalizeMonitorRects(rects) {
  if (!Array.isArray(rects)) {
    return [];
  }

  return rects
    .map((rect, index) => ({
      id: rect.id ?? index,
      index,
      x: Number(rect.x),
      y: Number(rect.y),
      width: Number(rect.width),
      height: Number(rect.height),
    }))
    .filter((rect) =>
      Number.isFinite(rect.x) &&
      Number.isFinite(rect.y) &&
      Number.isFinite(rect.width) &&
      Number.isFinite(rect.height) &&
      rect.width > ORB_MARGIN * 2 &&
      rect.height > ORB_MARGIN * 2
    );
}

function getMonitorRectForPoint(point, rects) {
  if (!point || !Array.isArray(rects) || !rects.length) {
    return null;
  }

  return rects.find((rect) =>
    point.x >= rect.x &&
    point.x < rect.x + rect.width &&
    point.y >= rect.y &&
    point.y < rect.y + rect.height
  ) || null;
}

function clampPositionToRect(position, rect) {
  if (!position || !rect) {
    return clampOrbPosition(position?.x ?? window.innerWidth * 0.5, position?.y ?? window.innerHeight * 0.5);
  }

  const marginX = Math.min(ORB_MARGIN, Math.max(24, rect.width * 0.2));
  const marginY = Math.min(ORB_MARGIN, Math.max(24, rect.height * 0.2));
  return clampOrbPosition(
    Math.min(rect.x + rect.width - marginX, Math.max(rect.x + marginX, position.x)),
    Math.min(rect.y + rect.height - marginY, Math.max(rect.y + marginY, position.y))
  );
}

function constrainPositionToCursorDisplay(position, cursor, rects) {
  const cursorRect = getMonitorRectForPoint(cursor, rects);
  return cursorRect ? clampPositionToRect(position, cursorRect) : clampOrbPosition(position.x, position.y);
}

function isPositionInRect(position, rect) {
  return Boolean(
    position &&
    rect &&
    position.x >= rect.x + ORB_MARGIN &&
    position.x <= rect.x + rect.width - ORB_MARGIN &&
    position.y >= rect.y + ORB_MARGIN &&
    position.y <= rect.y + rect.height - ORB_MARGIN
  );
}

function getMotionBounds(cursor, rects) {
  const rect = getMonitorRectForPoint(cursor, rects);
  if (rect) {
    return {
      left: rect.x + ORB_MARGIN,
      right: rect.x + rect.width - ORB_MARGIN,
      top: rect.y + ORB_MARGIN,
      bottom: rect.y + rect.height - ORB_MARGIN,
    };
  }

  return {
    left: ORB_MARGIN,
    right: window.innerWidth - ORB_MARGIN,
    top: ORB_MARGIN,
    bottom: window.innerHeight - ORB_MARGIN,
  };
}

function getCursorDisplayAnchor(cursor, rects) {
  const rect = getMonitorRectForPoint(cursor, rects);
  if (!rect) {
    return getCursorFollowTarget(cursor, rects);
  }

  return clampPositionToRect({
    x: rect.x + rect.width * ORB_SCREEN_ANCHOR_X_RATIO,
    y: rect.y + rect.height * ORB_SCREEN_ANCHOR_Y_RATIO,
  }, rect);
}

function choosePlayfulIdleTarget(current, cursor, rects) {
  const anchor = getCursorDisplayAnchor(cursor, rects);
  const dx = rand(-110, 110);
  const dy = rand(-80, 80);
  const playful = { x: anchor.x + dx, y: anchor.y + dy };
  return constrainPositionToCursorDisplay(playful, cursor, rects);
}

function chooseMultiDisplayPatrolTarget(rects, patrolIndex) {
  if (!rects.length) {
    return getHomePosition();
  }

  const rect = rects[patrolIndex % rects.length];
  const insetX = Math.min(ORB_MARGIN + 36, rect.width * 0.22);
  const insetY = Math.min(ORB_MARGIN + 24, rect.height * 0.22);
  const sweep = Math.floor(patrolIndex / rects.length) % 4;
  const anchors = [
    { x: rect.x + insetX, y: rect.y + insetY },
    { x: rect.x + rect.width - insetX, y: rect.y + insetY },
    { x: rect.x + rect.width - insetX, y: rect.y + rect.height - insetY },
    { x: rect.x + insetX, y: rect.y + rect.height - insetY },
  ];

  return clampOrbPosition(anchors[sweep].x, anchors[sweep].y);
}

function normalizeDirection(dx, dy, fallback = ORB_DEFAULT_TRAIL_DIRECTION) {
  const magnitude = Math.hypot(dx, dy);
  if (magnitude < ORB_DIRECTION_EPSILON) {
    return fallback;
  }

  return {
    x: dx / magnitude,
    y: dy / magnitude,
  };
}

function computeEdgeSlack(position) {
  return Math.min(
    position.x - ORB_MARGIN,
    window.innerWidth - ORB_MARGIN - position.x,
    position.y - ORB_MARGIN,
    window.innerHeight - ORB_MARGIN - position.y
  );
}

function chooseAutonomousDriftTarget(current, cursor, driftHeading, presenceProfile = null) {
  const autonomyLevel = clamp(
    Number(presenceProfile?.autonomy_level ?? 0.82),
    0.45,
    1
  );

  const homePos = getHomePosition();
  const centerBias = normalizeDirection(
    homePos.x - current.x,
    homePos.y - current.y,
    ORB_DEFAULT_TRAIL_DIRECTION
  );
  const maxCenterDistance = Math.min(window.innerWidth, window.innerHeight) * 0.75;
  const heading = normalizeDirection(
    driftHeading.x,
    driftHeading.y,
    ORB_DEFAULT_TRAIL_DIRECTION
  );
  const minDistanceFromCursor = ORB_RADIUS + 68 + autonomyLevel * 20;
  const attempts = 12;
  let bestCandidate = null;
  let bestScore = -Infinity;

  for (let i = 0; i < attempts; i += 1) {
    const jitteredDirection = normalizeDirection(
      heading.x + centerBias.x * 0.55 + rand(-0.9, 0.9),
      heading.y + centerBias.y * 0.55 + rand(-0.9, 0.9),
      heading
    );
    const travelDistance = rand(
      ORB_AUTONOMOUS_WAYPOINT_MIN_DISTANCE,
      ORB_AUTONOMOUS_WAYPOINT_MAX_DISTANCE
    );
    const candidate = clampOrbPosition(
      current.x + jitteredDirection.x * travelDistance,
      current.y + jitteredDirection.y * travelDistance
    );

    const edgeSlack = computeEdgeSlack(candidate);
    const cursorDistance = cursor
      ? Math.hypot(candidate.x - cursor.x, candidate.y - cursor.y)
      : Number.POSITIVE_INFINITY;
    const centerDistance = Math.hypot(
      candidate.x - homePos.x,
      candidate.y - homePos.y
    );
    const centerPenalty = centerDistance > maxCenterDistance
      ? (centerDistance - maxCenterDistance) * 0.65
      : 0;
    const safeCursorScore = Math.min(400, cursorDistance) * 0.45;
    const openSpaceScore = edgeSlack * 1.65;
    const momentumScore =
      (jitteredDirection.x * heading.x + jitteredDirection.y * heading.y) * 55;
    const score = safeCursorScore + openSpaceScore + momentumScore - centerPenalty;

    if (cursorDistance >= minDistanceFromCursor && score > bestScore) {
      bestCandidate = candidate;
      bestScore = score;
    } else if (!bestCandidate && score > bestScore) {
      bestCandidate = candidate;
      bestScore = score;
    }
  }

  const fallback = bestCandidate
    || clampOrbPosition(
      current.x + heading.x * ORB_AUTONOMOUS_WAYPOINT_MIN_DISTANCE,
      current.y + heading.y * ORB_AUTONOMOUS_WAYPOINT_MIN_DISTANCE
    );
  const fallbackSlack = computeEdgeSlack(fallback);
  const correctedFallback = fallbackSlack < 42
    ? clampOrbPosition(
      current.x + centerBias.x * ORB_AUTONOMOUS_WAYPOINT_MIN_DISTANCE,
      current.y + centerBias.y * ORB_AUTONOMOUS_WAYPOINT_MIN_DISTANCE
    )
    : fallback;
  return ensureCursorClearance(correctedFallback, cursor, heading);
}

function ensureCursorClearance(position, cursor, driftHeading) {
  if (!position) {
    return position;
  }
  return clampOrbPosition(position.x, position.y);
}

function getCursorFollowTarget(cursor, rects = []) {
  if (!cursor) {
    return getHomePosition();
  }

  return constrainPositionToCursorDisplay({
    x: cursor.x + ORB_CURSOR_FOLLOW_OFFSET_X,
    y: cursor.y + ORB_CURSOR_FOLLOW_OFFSET_Y,
  }, cursor, rects);
}

function shouldRetargetDrift(current, target, cursor, lastRetargetAt, presenceProfile = null) {
  const idleSeconds = Number(presenceProfile?.idle_seconds ?? 0);
  const intervalBoost = clamp(idleSeconds * 65, 0, ORB_AUTONOMOUS_RETARGET_INTERVAL_IDLE_MAX_MS - ORB_AUTONOMOUS_RETARGET_INTERVAL_MS);
  const dynamicRetargetIntervalMs = ORB_AUTONOMOUS_RETARGET_INTERVAL_MS + intervalBoost;

  if (!current || !target) {
    return true;
  }

  if (Date.now() - lastRetargetAt < ORB_RETARGET_STABILITY_WINDOW_MS) {
    return false;
  }

  const distanceToTarget = Math.hypot(target.x - current.x, target.y - current.y);
  const reachedTarget = distanceToTarget <= ORB_RETARGET_DISTANCE;

  if (computeEdgeSlack(target) < 28) {
    return true;
  }

  if (cursor && Math.hypot(target.x - cursor.x, target.y - cursor.y) < ORB_RADIUS + 50) {
    return true;
  }

  if (reachedTarget && Date.now() - lastRetargetAt > dynamicRetargetIntervalMs * 0.45) {
    return true;
  }

  return Date.now() - lastRetargetAt > dynamicRetargetIntervalMs;
}

function buildSteeringVector(current, target, cursor, presenceProfile, fallbackDirection) {
  const autonomyLevel = clamp(
    Number(presenceProfile?.autonomy_level ?? 0.82),
    0.45,
    1
  );
  const targetDirection = normalizeDirection(
    target.x - current.x,
    target.y - current.y,
    fallbackDirection
  );
  let sx = targetDirection.x;
  let sy = targetDirection.y;

  const homePos = getHomePosition();
  const centerDirection = normalizeDirection(
    homePos.x - current.x,
    homePos.y - current.y,
    targetDirection
  );
  const edgeSlack = computeEdgeSlack(current);
  if (edgeSlack < ORB_EDGE_REPEL_DISTANCE * 0.8) {
    sx += centerDirection.x * ORB_CENTER_RECOVERY_GAIN;
    sy += centerDirection.y * ORB_CENTER_RECOVERY_GAIN;
  }

  const leftDistance = current.x - ORB_MARGIN;
  const rightDistance = window.innerWidth - ORB_MARGIN - current.x;
  const topDistance = current.y - ORB_MARGIN;
  const bottomDistance = window.innerHeight - ORB_MARGIN - current.y;

  if (leftDistance < ORB_EDGE_REPEL_DISTANCE) {
    sx += (1 - leftDistance / ORB_EDGE_REPEL_DISTANCE) * ORB_EDGE_REPEL_GAIN;
  }
  if (rightDistance < ORB_EDGE_REPEL_DISTANCE) {
    sx -= (1 - rightDistance / ORB_EDGE_REPEL_DISTANCE) * ORB_EDGE_REPEL_GAIN;
  }
  if (topDistance < ORB_EDGE_REPEL_DISTANCE) {
    sy += (1 - topDistance / ORB_EDGE_REPEL_DISTANCE) * ORB_EDGE_REPEL_GAIN;
  }
  if (bottomDistance < ORB_EDGE_REPEL_DISTANCE) {
    sy -= (1 - bottomDistance / ORB_EDGE_REPEL_DISTANCE) * ORB_EDGE_REPEL_GAIN;
  }

  return normalizeDirection(sx, sy, targetDirection);
}

function toPlayableAudioUrl(audioPath) {
  if (!audioPath || typeof audioPath !== 'string') {
    return null;
  }

  if (/^(file|https?):/i.test(audioPath)) {
    return audioPath;
  }

  try {
    return pathToFileURL(audioPath).href;
  } catch (_error) {
    return null;
  }
}

function FloatingOrb() {
  const [logicMode, setLogicMode] = useState('deductive');
  const [bridgeStatus, setBridgeStatus] = useState('Bridge booting');
  const [tone, setTone] = useState('Observing');
  const [bloomLevel, setBloomLevel] = useState(0.22);
  const [orbScale, setOrbScale] = useState(1);
  const [skinUrl, setSkinUrl] = useState(null);
  const [skinConfig, setSkinConfig] = useState(null);
  const [commandOpen, setCommandOpen] = useState(false);
  const [commandText, setCommandText] = useState('');
  const [lastResponseText, setLastResponseText] = useState('');
  const [speechBubbleText, setSpeechBubbleText] = useState('');
  const [speechBubbleMode, setSpeechBubbleMode] = useState('response');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [nodOffset, setNodOffset] = useState({ x: 0, y: 0 });
  const [socketHint, setSocketHint] = useState('Base frame');
  const [egfState, setEgfState] = useState({ ok: false, mode: 'unavailable' });
  const [orbVisible, setOrbVisible] = useState(true);
  const [dockTransitionOffset, setDockTransitionOffset] = useState({ x: 0, y: 0 });
  const [dockTransitionScale, setDockTransitionScale] = useState(1);
  const [dockTransitionOpacity, setDockTransitionOpacity] = useState(1);
  const [displayActive, setDisplayActive] = useState(true);
  const [hasPositionUpdate, setHasPositionUpdate] = useState(false);
  const [swarmPendingCount, setSwarmPendingCount] = useState(0);
  const [swarmHudMissionMode, setSwarmHudMissionMode] = useState('idle');
  const [swarmHudLastResult, setSwarmHudLastResult] = useState('none');
  const [swarmNodes, setSwarmNodes] = useState([]);
  const [ingestRipples, setIngestRipples] = useState([]);
  const [cursorPosition, setCursorPosition] = useState({
    x: Math.round(window.innerWidth * ORB_HOME_X_RATIO),
    y: Math.round(window.innerHeight * ORB_HOME_Y_RATIO),
  });
  const swarmPhaseTimerRef = useRef(null);
  const cursorPositionRef = useRef(cursorPosition);
  const displayActiveRef = useRef(displayActive);
  const targetCursorPositionRef = useRef(cursorPosition);
  const animationFrameRef = useRef(null);
  const draggingRef = useRef(false);
  const dragOffsetRef = useRef({ x: 0, y: 0 });
  const mousePassthroughRef = useRef(true);
  const nodTimerRef = useRef(null);
  const lastCursorPointRef = useRef({
    x: Math.round(window.innerWidth * ORB_HOME_X_RATIO),
    y: Math.round(window.innerHeight * ORB_HOME_Y_RATIO),
  });
  const driftHeadingRef = useRef(ORB_DEFAULT_TRAIL_DIRECTION);
  const lastRetargetAtRef = useRef(0);
  const lastPointerRef = useRef({
    x: Math.round(window.innerWidth * ORB_HOME_X_RATIO),
    y: Math.round(window.innerHeight * ORB_HOME_Y_RATIO),
  });
  const lastKnownCursorRef = useRef({
    x: Math.round(window.innerWidth * ORB_HOME_X_RATIO),
    y: Math.round(window.innerHeight * ORB_HOME_Y_RATIO),
  });
  const activeAudioRef = useRef(null);
  const speechBubbleTimerRef = useRef(null);
  const dockTransitionTimersRef = useRef([]);
  const dockingInProgressRef = useRef(false);
  const presenceProfileRef = useRef({
    is_idle: false,
    idle_seconds: 0,
    autonomy_level: 0.82,
    movement_intent: 'free_float',
    cursor_influence: 'low',
  });
  const velocityRef = useRef({
    x: ORB_DEFAULT_TRAIL_DIRECTION.x * ORB_AUTONOMOUS_BASE_SPEED,
    y: ORB_DEFAULT_TRAIL_DIRECTION.y * ORB_AUTONOMOUS_BASE_SPEED,
  });
  const lastForcedRetargetAtRef = useRef(0);
  const lastCursorAvoidAtRef = useRef(0);
  const monitorRectsRef = useRef([]);
  const patrolIndexRef = useRef(0);
  const lastPatrolAtRef = useRef(0);
  const pendingSwarmMissionsRef = useRef([]);
  const lastUserInputAtRef = useRef(Date.now());
  const companionIntentRef = useRef(new CompanionIntent({ playfulnessEnabled: ORB_PLAYFUL_IDLE_ENABLED }));
  const fieldMotionRef = useRef(new FieldMotion());

  const visualMode = ORB_VISUAL_MODE_LOCK || logicMode;
  const visual = useMemo(() => LOGIC_VISUALS[visualMode], [visualMode]);
  const egfRenewalPressure = clamp(Number(egfState?.renewal_pressure || 0), 0, 1);
  const egfActivationLevel = clamp(Number(egfState?.activation_peak || 0) / 2.0, 0, 1);
  const egfCenterEntropy = clamp(Number(egfState?.center_entropy || 0), 0, 2);
  const egfOuterEntropy = clamp(Number(egfState?.outer_entropy || 0), 0, 2);
  const egfFault = egfState?.ok === false && egfState?.mode === 'fault';
  const egfUnavailable = egfState?.ok === false && egfState?.mode === 'unavailable';
  const egfPulseBoost = clamp(egfCenterEntropy * 0.22 + egfActivationLevel * 0.4, 0, 0.5);
  const egfTurbulenceBoost = clamp(egfOuterEntropy * 0.14, 0, 0.3);
  const pulseAccent = visualMode === 'deductive'
    ? '#63e6a6'
    : visualMode === 'inductive'
      ? '#f5c96a'
      : '#67c6ff';
  const swarmHudSnapshot = useMemo(() => {
    const phaseCounts = {
      out_spin: 0,
      out_dart: 0,
      in_arc: 0,
      in_loop: 0,
      ingest: 0,
    };
    swarmNodes.forEach((node) => {
      if (phaseCounts[node.phase] !== undefined) {
        phaseCounts[node.phase] += 1;
      }
    });

    const outbound = phaseCounts.out_spin + phaseCounts.out_dart;
    const inbound = phaseCounts.in_arc + phaseCounts.in_loop + phaseCounts.ingest;
    const activePhase = phaseCounts.out_spin > 0
      ? 'out_spin'
      : phaseCounts.out_dart > 0
        ? 'out_dart'
        : phaseCounts.in_arc > 0
          ? 'in_arc'
          : phaseCounts.in_loop > 0
            ? 'in_loop'
            : phaseCounts.ingest > 0
              ? 'ingest'
              : 'idle';

    return {
      activePhase,
      outbound,
      inbound,
      total: swarmNodes.length,
      phaseCounts,
    };
  }, [swarmNodes]);
  const swarmHudHasActiveMission = swarmPendingCount > 0 || swarmHudSnapshot.total > 0;
  const swarmHudMissionColor = swarmHudMissionMode === 'diagnostics'
    ? '#ffbf3f'
    : swarmHudMissionMode === 'research'
      ? '#4cb9ff'
      : 'rgba(216,242,255,0.62)';
  const swarmHudResultColor = swarmHudLastResult === 'fault'
    ? '#ff4b4b'
    : swarmHudLastResult === 'warning'
      ? '#ffb347'
      : swarmHudLastResult === 'success'
        ? '#63ef9e'
        : swarmHudLastResult === 'pending'
          ? '#67c6ff'
          : 'rgba(216,242,255,0.62)';

  const showSpeechBubble = (text, options = {}) => {
    const normalized = String(text || '').trim();
    if (!normalized) {
      return;
    }
    const mode = typeof options === 'string' ? options : options.mode || 'response';
    const persistMs =
      typeof options === 'number'
        ? options
        : options.persistMs ||
          (mode === 'state'
            ? 1200
            : Math.min(9000, Math.max(700, normalized.length * 45)));
    if (speechBubbleTimerRef.current) {
      clearTimeout(speechBubbleTimerRef.current);
    }
    setSpeechBubbleMode(mode);
    setSpeechBubbleText(normalized.length > 120 ? `${normalized.slice(0, 117)}...` : normalized);
    speechBubbleTimerRef.current = setTimeout(() => {
      setSpeechBubbleText('');
      speechBubbleTimerRef.current = null;
    }, Math.min(Math.max(Number(persistMs) || 4200, 700), 9000));
  };

  useEffect(() => {
    const decay = setInterval(() => {
      setBloomLevel((current) => Math.max(0.16, current - 0.045));
    }, 130);
    return () => clearInterval(decay);
  }, []);

  useEffect(() => {
    if (!swarmNodes.length) {
      return undefined;
    }

    const interval = setInterval(() => {
      const now = Date.now();
      const absorbedStates = [];

      setSwarmNodes((current) => {
        const next = current
          .map((node) => {
            const advanced = advanceSwarmNode(node, now);
            if (!advanced && node.phase === 'ingest') {
              absorbedStates.push(node.resultState || 'success');
            }
            return advanced;
          })
          .filter(Boolean);

        if (current.length && !next.length) {
          setTone('Payload ingested');
          setBridgeStatus('Prime verdict ready');
        }
        return next;
      });

      if (absorbedStates.length > 0) {
        setIngestRipples((current) => {
          const additions = absorbedStates.map((state) => ({
            id: `${now}-${Math.random().toString(16).slice(2)}`,
            startedAt: now,
            resultState: state,
          }));
          return [...current, ...additions].slice(-10);
        });
        setBloomLevel((current) => Math.max(current, 0.94));
        setOrbScale(1.08);
        setTimeout(() => setOrbScale(1), 220);
      }
    }, 16);

    return () => clearInterval(interval);
  }, [swarmNodes.length]);

  useEffect(() => {
    if (!ingestRipples.length) {
      return undefined;
    }

    const interval = setInterval(() => {
      const now = Date.now();
      setIngestRipples((current) =>
        current.filter((ripple) => now - ripple.startedAt < SWARM_RIPPLE_MS)
      );
    }, 42);

    return () => clearInterval(interval);
  }, [ingestRipples.length]);

  useEffect(() => () => {
    if (swarmPhaseTimerRef.current) {
      clearTimeout(swarmPhaseTimerRef.current);
    }
  }, []);

  useEffect(() => {
    cursorPositionRef.current = cursorPosition;
  }, [cursorPosition]);

  useEffect(() => {
    displayActiveRef.current = displayActive;
  }, [displayActive]);

  useEffect(() => {
    if (commandOpen) {
      window.electronAPI?.setIgnoreMouseEvents(false);
    }
  }, [commandOpen]);

  useEffect(() => () => {
    if (activeAudioRef.current) {
      activeAudioRef.current.pause();
      activeAudioRef.current = null;
    }
    if (speechBubbleTimerRef.current) {
      clearTimeout(speechBubbleTimerRef.current);
      speechBubbleTimerRef.current = null;
    }
    if (dockTransitionTimersRef.current?.length) {
      dockTransitionTimersRef.current.forEach((id) => clearTimeout(id));
      dockTransitionTimersRef.current = [];
    }
    if (nodTimerRef.current) {
      nodTimerRef.current.forEach((id) => clearTimeout(id));
      nodTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    const animateOrb = () => {
      try {
        if (!draggingRef.current) {
          const current = cursorPositionRef.current;
          const now = Date.now();
          const profile = presenceProfileRef.current || {};
          const forceIntervalMs = profile?.is_idle
            ? ORB_AUTONOMOUS_FORCE_RETARGET_IDLE_MS
            : ORB_AUTONOMOUS_FORCE_RETARGET_BASE_MS;
          const monitorRects = monitorRectsRef.current;
          const cursor = lastKnownCursorRef.current;
          const cursorDistance = cursor
            ? Math.hypot(current.x - cursor.x, current.y - cursor.y)
            : 0;
          const isUserActive = (now - lastUserInputAtRef.current) <= ORB_COMPANION_USER_ACTIVE_MS;
          const bridgeFault = String(bridgeStatus || '').toLowerCase().includes('error');
          const intent = companionIntentRef.current.update({
            displayActive: displayActiveRef.current,
            bridgeFault,
            isSubmitting,
            swarmPendingCount,
            isUserActive,
            presenceProfile: profile,
            cursorDistance,
            returnDistance: ORB_COMPANION_RETURN_DISTANCE,
          });

          if (
            ORB_MULTI_DISPLAY_PATROL &&
            monitorRects.length > 1 &&
            now - lastPatrolAtRef.current >= ORB_MULTI_DISPLAY_PATROL_INTERVAL_MS
          ) {
            targetCursorPositionRef.current = chooseMultiDisplayPatrolTarget(
              monitorRects,
              patrolIndexRef.current
            );
            patrolIndexRef.current = (patrolIndexRef.current + 1) % (monitorRects.length * 4);
            lastPatrolAtRef.current = now;
            lastForcedRetargetAtRef.current = now;
            lastRetargetAtRef.current = now;
          }

          if (now - lastForcedRetargetAtRef.current >= forceIntervalMs) {
            targetCursorPositionRef.current = chooseAutonomousDriftTarget(
              current,
              lastKnownCursorRef.current,
              driftHeadingRef.current,
              profile
            );
            lastForcedRetargetAtRef.current = now;
            lastRetargetAtRef.current = now;
          }

          if (
            shouldRetargetDrift(
              current,
              targetCursorPositionRef.current,
              lastKnownCursorRef.current,
              lastRetargetAtRef.current,
              profile
            )
          ) {
            targetCursorPositionRef.current = chooseAutonomousDriftTarget(
              current,
              lastKnownCursorRef.current,
              driftHeadingRef.current,
              profile
            );
            lastRetargetAtRef.current = now;
          }

          if (ORB_CURSOR_FOLLOW && intent.intent === 'returning' && cursor) {
            targetCursorPositionRef.current = getCursorDisplayAnchor(cursor, monitorRects);
          }

          if (displayActiveRef.current && cursor && monitorRects.length) {
            targetCursorPositionRef.current = constrainPositionToCursorDisplay(
              targetCursorPositionRef.current,
              cursor,
              monitorRects
            );
          }

          const target = targetCursorPositionRef.current;
          const motionBounds = getMotionBounds(cursor, monitorRects);
          const motionStep = fieldMotionRef.current.update({
            currentPosition: current,
            targetZone: target,
            intentProfile: intent.motionProfile,
            screenBounds: motionBounds,
            maxAcceleration: ORB_MAX_ACCELERATION,
          });
          velocityRef.current = motionStep.velocity;

          const safePosition = ensureCursorClearance(
            motionStep.position,
            lastKnownCursorRef.current,
            driftHeadingRef.current
          );
          const displaySafePosition = displayActiveRef.current && cursor && monitorRects.length
            ? constrainPositionToCursorDisplay(safePosition, cursor, monitorRects)
            : safePosition;
          const moved = Math.hypot(
            displaySafePosition.x - current.x,
            displaySafePosition.y - current.y
          );
          if (moved < 0.16 && computeEdgeSlack(displaySafePosition) < 18) {
            const home = getHomePosition();
          const centerRecovery = clampOrbPosition(
              home.x + rand(-140, 140),
              home.y + rand(-95, 95)
            );
            targetCursorPositionRef.current = centerRecovery;
            lastRetargetAtRef.current = now;
          }

          driftHeadingRef.current = normalizeDirection(
            velocityRef.current.x,
            velocityRef.current.y,
            driftHeadingRef.current
          );
          cursorPositionRef.current = displaySafePosition;
          setCursorPosition(displaySafePosition);
        }
      } catch (error) {
        console.warn('Orb animation loop error:', error);
      }

      animationFrameRef.current = window.requestAnimationFrame(animateOrb);
    };

    animationFrameRef.current = window.requestAnimationFrame(animateOrb);

    return () => {
      if (animationFrameRef.current) {
        window.cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, []);

  useEffect(() => {
    const setMousePassthrough = (ignore) => {
      if (mousePassthroughRef.current === ignore) {
        return;
      }
      mousePassthroughRef.current = ignore;
      window.electronAPI?.setIgnoreMouseEvents(ignore, ignore ? { forward: true } : undefined);
    };

    const isPointerOverOrb = (x, y) => {
      const dx = x - cursorPositionRef.current.x;
      const dy = y - cursorPositionRef.current.y;
      return Math.hypot(dx, dy) <= ORB_INTERACTION_RADIUS;
    };

    const handleMouseMove = (event) => {
      lastUserInputAtRef.current = Date.now();
      const pointer = { x: event.clientX, y: event.clientY };
      lastPointerRef.current = pointer;

      if (draggingRef.current) {
        const nextPosition = clampOrbPosition(
          pointer.x - dragOffsetRef.current.x,
          pointer.y - dragOffsetRef.current.y
        );
        velocityRef.current = { x: 0, y: 0 };
        targetCursorPositionRef.current = nextPosition;
        cursorPositionRef.current = nextPosition;
        setCursorPosition(nextPosition);
        setMousePassthrough(false);
        return;
      }

      const hoveringOrb = isPointerOverOrb(pointer.x, pointer.y);
      setMousePassthrough(!(hoveringOrb && event.shiftKey));
    };

    const handleMouseUp = () => {
      if (!draggingRef.current) {
        return;
      }

      draggingRef.current = false;
      const releasedPosition = ensureCursorClearance(
        cursorPositionRef.current,
        lastKnownCursorRef.current,
        driftHeadingRef.current
      );
      cursorPositionRef.current = releasedPosition;
      driftHeadingRef.current = normalizeDirection(
        releasedPosition.x - lastKnownCursorRef.current.x,
        releasedPosition.y - lastKnownCursorRef.current.y,
        driftHeadingRef.current
      );
      targetCursorPositionRef.current = chooseAutonomousDriftTarget(
        releasedPosition,
        lastKnownCursorRef.current,
        driftHeadingRef.current,
        presenceProfileRef.current
      );
      velocityRef.current = {
        x: driftHeadingRef.current.x * ORB_AUTONOMOUS_BASE_SPEED,
        y: driftHeadingRef.current.y * ORB_AUTONOMOUS_BASE_SPEED,
      };
      lastRetargetAtRef.current = Date.now();
      setCursorPosition(releasedPosition);
      setMousePassthrough(true);
    };

    const handleKeyDown = () => {
      lastUserInputAtRef.current = Date.now();
    };

    const handleMouseDown = () => {
      lastUserInputAtRef.current = Date.now();
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('mousedown', handleMouseDown);

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('mousedown', handleMouseDown);
    };
  }, []);

  useEffect(() => {
    if (!window.electronAPI) {
      return undefined;
    }

    const playOrbAudio = (audioPath) => {
      const audioUrl = toPlayableAudioUrl(audioPath);
      if (!audioUrl) {
        return;
      }

      if (activeAudioRef.current) {
        activeAudioRef.current.pause();
        activeAudioRef.current = null;
      }

      const audio = new Audio(audioUrl);
      audio.preload = 'auto';
      audio.volume = 1;
      activeAudioRef.current = audio;

      const clearIfCurrent = () => {
        if (activeAudioRef.current === audio) {
          activeAudioRef.current = null;
        }
      };

      audio.addEventListener('ended', clearIfCurrent, { once: true });
      audio.addEventListener('error', clearIfCurrent, { once: true });

      audio.play().catch((error) => {
        console.warn('Orb audio playback failed:', error);
        clearIfCurrent();
      });
    };

    const applyPulse = (pulse) => {
      const payload = pulse?.data?.predicate || pulse;
      const nextMode = modeFromCognitiveMode(payload?.cognitive_mode);
      setLogicMode(nextMode);
      const recalledFromPosteriori = pulse?.source === 'POSTERIORI';
      const recalledFromApriori = pulse?.source === 'APRIORI';
      setTone(
        recalledFromPosteriori
          ? 'Remembering'
          : recalledFromApriori
            ? 'Law recall'
            : LOGIC_VISUALS[nextMode].tone
      );
      setBridgeStatus(
        recalledFromPosteriori
          ? 'Posteriori recall'
          : recalledFromApriori
            ? 'Apriori recall'
            : `${LOGIC_VISUALS[nextMode].label} channel live`
      );
      setBloomLevel(
        Math.max(
          recalledFromPosteriori || recalledFromApriori ? 0.62 : 0.45,
          Math.min(1, payload?.glow_intensity ?? 0.5)
        )
      );

      if (payload?.egf_state && typeof payload.egf_state === 'object') {
        setEgfState(payload.egf_state);
      }
    };

    const applyEGFState = (nextState) => {
      if (!nextState || typeof nextState !== 'object') {
        return;
      }
      setEgfState(nextState);

      if (nextState.ok === false) {
        if (nextState.mode === 'fault') {
          setTone('EGF fault');
          setBridgeStatus(nextState.error || 'EGF stats unavailable');
          setBloomLevel(0.96);
        } else if (nextState.mode === 'unavailable') {
          setTone('EGF offline');
          setBridgeStatus('Cognition core dimmed');
          setBloomLevel(0.34);
        }
      }
    };

    const unsubscribers = [
      window.electronAPI.onOrbPositionUpdate((_event, payload) => {
        if (draggingRef.current) {
          return;
        }

        setHasPositionUpdate(true);
        const isActiveDisplay = payload?.active !== false;
        if (!isActiveDisplay) {
          draggingRef.current = false;
          displayActiveRef.current = false;
          setDisplayActive(false);
          return;
        }

        const cursorPoint = {
          x: payload?.x ?? window.innerWidth / 2,
          y: payload?.y ?? window.innerHeight / 2,
        };
        const nextMonitorRects = normalizeMonitorRects(payload?.displayRects);
        if (nextMonitorRects.length) {
          monitorRectsRef.current = nextMonitorRects;
        }
        lastKnownCursorRef.current = cursorPoint;
        const previousCursorPoint = lastCursorPointRef.current;
        const movement = {
          x: cursorPoint.x - previousCursorPoint.x,
          y: cursorPoint.y - previousCursorPoint.y,
        };
        if (Math.hypot(movement.x, movement.y) > ORB_DIRECTION_EPSILON) {
          lastUserInputAtRef.current = Date.now();
          driftHeadingRef.current = normalizeDirection(
            driftHeadingRef.current.x * 0.985 + movement.x * 0.015,
            driftHeadingRef.current.y * 0.985 + movement.y * 0.015,
            driftHeadingRef.current
          );
        }
        lastCursorPointRef.current = cursorPoint;
        if (!displayActiveRef.current) {
          const resetPosition = ensureCursorClearance(
            cursorPositionRef.current,
            cursorPoint,
            driftHeadingRef.current
          );
          cursorPositionRef.current = resetPosition;
          setCursorPosition(resetPosition);
        }
        displayActiveRef.current = true;
        setDisplayActive(true);
      }),
      window.electronAPI.onCognitivePulse((_event, pulse) => applyPulse(pulse)),
      window.electronAPI.onSpeechPulse((_event, message) => {
        applyPulse(message?.data || {});
        setTone('Responding');
        setBridgeStatus(message?.response_text || message?.transcription || 'Voice response ready');
        setBloomLevel(0.82);
        setOrbScale(1.08);
        setTimeout(() => setOrbScale(1), 260);
      }),
      window.electronAPI.onHysteresis((_event, data) => {
        setTone('Bloom threshold');
        setBridgeStatus(`Hysteresis ${data.triggerThreshold} -> ${data.releaseThreshold}`);
        setBloomLevel(1);
        setOrbScale(1.06);
        setTimeout(() => setOrbScale(1), 260);
      }),
      window.electronAPI.onOrbSkinUpdated((_event, payload) => {
        const nextSkinUrl = payload?.imageUrl || null;
        setSkinUrl(nextSkinUrl);
        setSocketHint(nextSkinUrl ? 'Socket engaged' : 'Base frame');
      }),
      window.electronAPI.onSkinConfigUpdated && window.electronAPI.onSkinConfigUpdated((_event, config) => {
        setSkinConfig(config || null);
        setSocketHint(config ? `Skin: ${config.name || config.colorScheme || 'Custom'}` : 'Base frame');
      }),
      window.electronAPI.onOrbBridgeMessage((_event, message) => {
        const payload = message?.data || {};
        const audioPath = payload?.audio_path || message?.audio_path;
        if (audioPath) {
          playOrbAudio(audioPath);
        }

        if (message?.type === 'ready') {
          setBridgeStatus('Python bridge ready');
          setTone('Present');
          setBloomLevel(0.72);
        }
        if (message?.type === 'bridge_exit') {
          setBridgeStatus('Bridge offline');
          setTone('Sleeping');
        }
        if (message?.type === 'listening_state') {
          const active = Boolean(message?.data?.listening);
          const mode = message?.data?.mode === 'oneshot' ? 'Voice capture' : 'Listening';
          setTone(active ? mode : 'Present');
          setBridgeStatus(active ? `${mode} armed` : 'Awaiting gesture');
          setBloomLevel(active ? 0.95 : 0.42);
          setOrbScale(active ? 1.08 : 1);
        }
        if (message?.type === 'listen_once_ack' && !message?.data?.accepted) {
          setTone('Voice busy');
          setBridgeStatus('Voice capture unavailable');
          setBloomLevel(0.68);
        }
        if (message?.type === 'presence_update' || message?.type === 'presence_pulse') {
          const profile = message?.type === 'presence_update'
            ? {
              is_idle: Boolean(message?.idle),
              idle_seconds: Number(message?.idle_seconds || 0),
              autonomy_level: Number(message?.autonomy_level || 0.82),
              movement_intent: message?.movement_intent || 'free_float',
              cursor_influence: message?.cursor_influence || 'low',
              active_window: message?.active_window,
              active_process: message?.active_process,
              quadrant: message?.quadrant,
            }
            : (message?.data?.presence_profile || {});
          presenceProfileRef.current = {
            ...presenceProfileRef.current,
            ...profile,
          };
          const autonomy = Number(
            profile.autonomy_level ?? presenceProfileRef.current.autonomy_level ?? 0.82
          );
          const idleSeconds = Number(
            profile.idle_seconds ?? presenceProfileRef.current.idle_seconds ?? 0
          );
          setTone(profile.is_idle ? 'Ambient presence' : 'Autonomous drift');
          setBridgeStatus(
            `Presence autonomy ${autonomy.toFixed(2)} | idle ${Math.round(idleSeconds)}s`
          );
          setBloomLevel((current) => Math.max(current, profile.is_idle ? 0.58 : 0.46));
        }
        if (message?.type === 'egf_state') {
          applyEGFState(message?.data || message);
        }
        if (message?.type === 'query_result') {
          setTone('Responding');
          const text = message?.data?.response_text || message?.data?.text || 'Response ready';
          const query = message?.data?.query_text || message?.data?.query || '';
          setBridgeStatus(text);
          setLastResponseText(text);
          showSpeechBubble(text);
          setBloomLevel(1);
          setOrbScale(1.1);
          setTimeout(() => setOrbScale(1), 260);
          triggerSwarmReturn({
            mode: 'diagnostics',
            query,
            resultState: classifySwarmResult(message),
          });
        }
        if (message?.type === 'research_result') {
          setTone('Research ready');
          const query = message?.data?.query || message?.data?.query_text || '';
          const text = message?.data?.voice_response || message?.data?.response_text || message?.data?.summary || 'Research response ready';
          setBridgeStatus(text);
          setLastResponseText(text);
          showSpeechBubble(text, { persistMs: 5600 });
          setBloomLevel(0.96);
          setOrbScale(1.08);
          setTimeout(() => setOrbScale(1), 260);
          triggerSwarmReturn({
            mode: 'research',
            query,
            resultState: classifySwarmResult(message),
          });
        }
        if (message?.type === 'cali:state') {
          const phase = message?.data?.phase || 'processing';
          const text =
            message?.data?.text ||
            {
              planning: 'Working with you on this.',
              searching: 'Looking through the available memory and sources.',
              verifying: 'Checking the source picture.',
              synthesizing: 'Pulling the answer together.',
              speaking: 'Ready.',
            }[phase] ||
            '';
          const prefix = {
            planning: '*',
            searching: '~',
            verifying: '+',
            synthesizing: '=',
            speaking: 'o',
          }[phase] || '*';
          if (text) {
            setTone(`CALI ${phase}`);
            setBridgeStatus(text);
            showSpeechBubble(`${prefix} ${text}`, { mode: 'state' });
          }
        }
        if (message?.type === 'speech_pulse') {
          const text = message?.response_text || message?.data?.response_text || message?.research?.response_text || '';
          if (text) {
            showSpeechBubble(text);
          }
        }
        if (message?.type === 'speak_result') {
          setTone('Speaking');
          const text = message?.data?.text || 'Voice response ready';
          setBridgeStatus(text);
          setLastResponseText(text);
          showSpeechBubble(text);
          setBloomLevel(0.88);
          setOrbScale(1.08);
          setTimeout(() => setOrbScale(1), 260);
        }
        if (message?.type === 'note_result') {
          setTone('Taking notes');
          const text = message?.data?.response_text || 'Note saved';
          setBridgeStatus(text);
          showSpeechBubble(text, { persistMs: 2600 });
          setBloomLevel(0.82);
        }
        if (message?.type === 'research_vault_result') {
          setTone('Research memory');
          const text = message?.data?.response_text || 'Research memory updated';
          setBridgeStatus(text);
          showSpeechBubble(text, { persistMs: 3200 });
          setBloomLevel(0.84);
        }
        if (message?.type === 'core_knowledge_result') {
          setTone('Core knowledge');
          const text = message?.data?.response_text || 'Core knowledge ready';
          setBridgeStatus(text);
          showSpeechBubble(text, { persistMs: 4200 });
          setBloomLevel(0.86);
        }
        if (message?.type === 'skill_result') {
          setTone('CALI skill');
          const text = message?.data?.response_text || 'Skill result ready';
          setBridgeStatus(text);
          showSpeechBubble(text, { persistMs: 4200 });
          setBloomLevel(0.86);
        }
      }),
      window.electronAPI.onPrimeOrbCommand?.((_event, command) => {
        const action = String(command?.command || '').toLowerCase();
        if (!action) {
          return;
        }

        if (action === 'activate') {
          setTone('Prime active');
          setBridgeStatus('Dock Station activate command received');
          pulseOrb(0.9, 1.08, 240);
          return;
        }

        if (action === 'spawn_micro_orb') {
          triggerSwarmDispatch({
            count: normalizePrimeCount(command?.count, PRIME_SWARM_COUNTS[0]),
            mode: command?.mode,
            query: command?.query || '',
            deployZone: command?.deployZone || command?.deploy_zone || 'around',
          });
          return;
        }

        if (action === 'deploy_swarm') {
          const mode = String(command?.mode || '').toLowerCase();
          const query = String(command?.query || '').trim();
          const deployed = triggerSwarmDispatch({
            count: command?.count,
            mode,
            query,
            complexity: command?.complexity,
            deployZone: command?.deployZone || command?.deploy_zone || 'around',
          });
          if (deployed && query) {
            const deploymentLabel = mode === 'diagnostics'
              ? 'Diagnostics'
              : mode === 'research'
                ? 'Research'
                : 'Mission';
            showSpeechBubble(
              `${deploymentLabel} deployment: ${query}`,
              { mode: 'state', persistMs: 2400 }
            );
          }
        }
      }),
      window.electronAPI.onOrbStatusChange((_event, status) => {
        if (status?.controller_status) {
          setBridgeStatus(`Brain ${status.controller_status}`);
        }
        if (status?.egf_state) {
          applyEGFState(status.egf_state);
        }
      }),
      window.electronAPI.onEGFState?.((_event, nextState) => applyEGFState(nextState)),
      window.electronAPI.onOrbVisibilityChanged((_event, payload) => {
        const visible = payload?.visible !== false;
        setOrbVisible(visible);
        setTone(visible ? 'Present' : 'Docked');
        setBridgeStatus(visible ? 'Orb deployed' : 'Tray docked');
        if (visible) {
          cancelDockTransition();
          setBloomLevel(0.9);
          setOrbScale(1.08);
          setTimeout(() => setOrbScale(1), 260);
        }
      }),
      window.electronAPI.onDockTransition?.((_event, payload) => {
        if (payload?.phase === 'cancel') {
          cancelDockTransition();
          setTone('Present');
          setBridgeStatus('Dock canceled');
          return;
        }
        if (payload?.phase === 'start') {
          startDockTransition(payload);
        }
      }),
    ];

    window.electronAPI.getOrbStatus?.().catch(() => {});

    return () => {
      unsubscribers.forEach((unsubscribe) => {
        if (typeof unsubscribe === 'function') unsubscribe();
      });
    };
  }, []);

  const handleCommandSubmit = async (mode) => {
    if (!commandText.trim()) return;
    setIsSubmitting(true);
    const text = commandText.trim();
    try {
      if (mode === 'ask') {
        setTone('Querying');
        setBridgeStatus(text);
        pulseOrb(0.92, 1.08, 240);
        triggerSwarmDispatch({ query: text });
        const result = await window.electronAPI?.orbQuery?.(text);
        const responseText = result?.response_text || result?.text || 'Response ready';
        setLastResponseText(responseText);
        setBridgeStatus(responseText);
        showSpeechBubble(responseText);
      } else if (mode === 'search') {
        setTone('Researching');
        setBridgeStatus(text);
        pulseOrb(0.96, 1.08, 260);
        triggerSwarmDispatch({ mode: 'research', query: text });
        const result = await window.electronAPI?.orbResearch?.(text, []);
        const responseText = result?.voice_response || result?.response_text || result?.summary || 'Research response ready';
        setLastResponseText(responseText);
        setBridgeStatus(responseText);
        showSpeechBubble(responseText, { persistMs: 5600 });
      } else if (mode === 'shop') {
        await window.electronAPI?.openSearch?.(text, 'shopping');
        setBridgeStatus(`Opened shopping for "${text}"`);
        setLastResponseText(`Shopping: ${text}`);
        pulseOrb(0.82, 1.04, 200);
      }
    } catch (error) {
      setBridgeStatus('Command failed');
      setLastResponseText(`Error: ${error.message || error}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  const playNod = (direction = 'yes') => {
    if (nodTimerRef.current) {
      nodTimerRef.current.forEach((id) => clearTimeout(id));
    }
    setNodOffset({ x: 0, y: 0 });
    setTone(direction === 'no' ? 'Declined' : 'Acknowledged');
    setBloomLevel(direction === 'no' ? 0.82 : 0.9);
    setOrbScale(direction === 'no' ? 1.035 : 1.055);
    const timers = [
      setTimeout(() => setOrbScale(0.992), 120),
      setTimeout(() => setOrbScale(1.035), 240),
      setTimeout(() => setOrbScale(1), 420),
    ];
    nodTimerRef.current = timers;
  };

  const clearDockTransitionTimers = () => {
    if (!dockTransitionTimersRef.current?.length) {
      return;
    }
    dockTransitionTimersRef.current.forEach((id) => clearTimeout(id));
    dockTransitionTimersRef.current = [];
  };

  const cancelDockTransition = () => {
    clearDockTransitionTimers();
    dockingInProgressRef.current = false;
    setDockTransitionOffset({ x: 0, y: 0 });
    setDockTransitionScale(1);
    setDockTransitionOpacity(1);
  };

  const startDockTransition = async (spec = {}) => {
    if (dockingInProgressRef.current) {
      return;
    }

    dockingInProgressRef.current = true;
    clearDockTransitionTimers();

    const ackMs = Number(spec?.ackMs) || ORB_DOCK_TRANSITION_ACK_MS;
    const travelMs = Number(spec?.travelMs) || ORB_DOCK_TRANSITION_TRAVEL_MS;
    const lockMs = Number(spec?.lockMs) || ORB_DOCK_TRANSITION_LOCK_MS;
    const totalMs = Number(spec?.totalMs) || ORB_DOCK_TRANSITION_TOTAL_MS;

    const current = cursorPositionRef.current;
    const dockAnchor = {
      x: Math.round(window.innerWidth * 0.5),
      y: Math.max(110, window.innerHeight - 110),
    };
    const dockVector = {
      x: dockAnchor.x - current.x,
      y: dockAnchor.y - current.y,
    };

    setTone('Docking');
    setBridgeStatus('Dock acknowledge');
    setBloomLevel(0.94);
    setDockTransitionScale(1.03);

    dockTransitionTimersRef.current.push(
      setTimeout(() => {
        setBridgeStatus('Dock trajectory');
        setDockTransitionOffset(dockVector);
        setDockTransitionScale(1.04);
        setDockTransitionOpacity(0.96);
      }, ackMs),
      setTimeout(() => {
        setBridgeStatus('Dock lock');
        setDockTransitionScale(0.97);
        setDockTransitionOpacity(0.86);
      }, ackMs + travelMs),
      setTimeout(() => {
        setDockTransitionScale(1);
      }, ackMs + travelMs + Math.max(50, Math.floor(lockMs * 0.6))),
      setTimeout(async () => {
        setTone('Docked');
        setBridgeStatus('Docked');
        setBloomLevel(0.58);
        try {
          await window.electronAPI?.completeDockTransition?.();
        } catch (_error) {}
        cancelDockTransition();
      }, totalMs + 20)
    );
  };

  const orbStyle = {
    position: 'absolute',
    left: `${cursorPosition.x}px`,
    top: `${cursorPosition.y}px`,
    minWidth: `${ORB_DIAMETER}px`,
    maxWidth: `${ORB_DIAMETER}px`,
    minHeight: `${ORB_DIAMETER}px`,
    maxHeight: `${ORB_DIAMETER}px`,
    width: `${ORB_DIAMETER}px`,
    height: `${ORB_DIAMETER}px`,
    aspectRatio: '1 / 1',
    boxSizing: 'border-box',
    flex: '0 0 auto',
    pointerEvents: 'auto',
    cursor: draggingRef.current ? 'grabbing' : 'grab',
    transform: `translate(-50%, -50%) translate(${nodOffset.x + dockTransitionOffset.x}px, ${nodOffset.y + dockTransitionOffset.y}px) scale(${(orbScale + bloomLevel * 0.08) * dockTransitionScale})`,
    opacity: dockTransitionOpacity,
    transition: 'transform 220ms cubic-bezier(0.22, 0.8, 0.2, 1), opacity 180ms ease',
    willChange: 'left, top, transform',
    WebkitAppRegion: 'no-drag',
  };

  const commandPanelStyle = {
    position: 'absolute',
    left: '54%',
    top: '-12px',
    minWidth: '240px',
    maxWidth: '360px',
    padding: '12px 14px',
    borderRadius: '18px',
    background: 'rgba(12,18,31,0.9)',
    color: '#e8f0ff',
    boxShadow: '0 8px 28px rgba(0,0,0,0.32)',
    border: '1px solid rgba(103,198,255,0.32)',
    display: commandOpen ? 'block' : 'none',
    pointerEvents: 'auto',
    transform: 'translateY(-50%)',
    backdropFilter: 'blur(10px)',
    zIndex: 3,
  };

  const buttonRowStyle = {
    display: 'flex',
    gap: '8px',
    marginTop: '8px',
  };

  const auraStyle = {
    position: 'absolute',
    inset: '-18px',
    borderRadius: '50%',
    background: `radial-gradient(circle, ${visual.aura} 0%, rgba(255,255,255,0.06) 45%, rgba(255,255,255,0) 72%)`,
    opacity: clamp(0.34 + bloomLevel * 0.56 + egfPulseBoost * 0.4, 0.15, 1),
    filter: `blur(${10 + bloomLevel * 12}px)`,
    transform: `scale(${1 + bloomLevel * 0.18})`,
    transition: 'all 160ms ease',
  };

  const pulseLayerBaseStyle = {
    position: 'absolute',
    inset: '2px',
    borderRadius: '50%',
    pointerEvents: 'none',
    mixBlendMode: 'screen',
    zIndex: 0,
  };

  const primaryPulseLayerStyle = {
    ...pulseLayerBaseStyle,
    inset: '-10px',
    border: `1px solid ${visual.color}`,
    boxShadow: `0 0 32px ${visual.color}`,
    opacity: clamp(0.3 + bloomLevel * 0.28 + egfPulseBoost * 0.25, 0.12, 1),
    animation: 'orbPulsePrimary 2600ms ease-in-out infinite',
  };

  const secondaryPulseLayerStyle = {
    ...pulseLayerBaseStyle,
    inset: '-26px',
    border: `1px solid ${pulseAccent}`,
    boxShadow: `0 0 42px ${pulseAccent}`,
    opacity: clamp(0.18 + bloomLevel * 0.22 + egfTurbulenceBoost * 0.45, 0.08, 1),
    animation: 'orbPulseSecondary 3600ms ease-in-out infinite',
  };

  // Determine inner content gradient from config skin or cognitive visual
  const innerContentBackground = skinUrl
    ? 'transparent'
    : egfFault
      ? 'radial-gradient(circle at 36% 30%, rgba(255,220,190,0.95), rgba(255,120,40,0.65) 28%, rgba(90,0,0,0.98) 75%)'
      : egfUnavailable
        ? 'radial-gradient(circle at 36% 30%, rgba(190,200,215,0.82), rgba(95,110,130,0.5) 32%, rgba(9,12,20,0.98) 75%)'
    : skinConfig && SKIN_CONFIG_GRADIENTS[skinConfig.colorScheme]
      ? SKIN_CONFIG_GRADIENTS[skinConfig.colorScheme]
      : `radial-gradient(circle at 36% 30%, rgba(255,255,255,0.92), ${visual.color} 28%, rgba(8,12,24,0.98) 75%)`;

  // Glass outer shell — the encasing sphere
  const glassShellStyle = {
    position: 'absolute',
    inset: '10px',
    borderRadius: '50%',
    // Glass rim material: clear center, increasingly opaque glassy edges
    background: `radial-gradient(circle at 50% 50%,
      transparent 52%,
      rgba(180, 220, 255, 0.03) 62%,
      rgba(180, 220, 255, 0.10) 74%,
      rgba(200, 235, 255, 0.20) 86%,
      rgba(230, 245, 255, 0.26) 93%,
      rgba(255, 255, 255, 0.12) 100%)`,
    boxShadow: [
      `inset 0 0 0 1.5px rgba(210, 235, 255, 0.32)`,
      `inset 0 10px 28px rgba(255,255,255,0.09)`,
      `inset 0 -8px 20px rgba(0, 0, 20, 0.28)`,
      `0 0 ${38 + bloomLevel * 65}px ${visual.color}`,
      `0 0 ${10 + bloomLevel * 14}px rgba(0,0,0,0.55)`,
    ].join(', '),
    overflow: 'hidden',
    opacity: 0.80 + bloomLevel * 0.16,
    isolation: 'isolate',
  };

  // Inner content layer — the skin lives here, enclosed by the glass
  const innerVolumeStyle = {
    position: 'absolute',
    inset: '7%',
    borderRadius: '50%',
    background: innerContentBackground,
    overflow: 'hidden',
    filter: skinConfig
      ? `saturate(${1.05 + bloomLevel * 0.2}) brightness(${0.92 + bloomLevel * 0.12})`
      : undefined,
    transition: 'background 0.4s ease, filter 0.3s ease',
  };

  // Image skin rendered inside inner volume
  const skinImageStyle = {
    position: 'absolute',
    inset: 0,
    borderRadius: '50%',
    backgroundImage: `url("${skinUrl}")`,
    backgroundSize: 'cover',
    backgroundPosition: 'center',
    filter: `hue-rotate(${visual.hueRotate}deg) saturate(${1.04 + bloomLevel * 0.2}) brightness(${visual.brightness + bloomLevel * 0.1})`,
    transform: `scale(${1 + bloomLevel * 0.04})`,
    transition: 'transform 160ms ease, filter 160ms ease',
  };

  // Glass caustic refraction ring — subtle light bending at inner glass edge
  const glassCausticStyle = {
    position: 'absolute',
    inset: 0,
    borderRadius: '50%',
    background: `radial-gradient(circle at 50% 50%,
      transparent 50%,
      rgba(${visual.color.startsWith('#') ? '100,180,255' : '100,180,255'}, 0.07) 57%,
      rgba(200, 230, 255, 0.13) 63%,
      transparent 68%)`,
    mixBlendMode: 'screen',
    pointerEvents: 'none',
  };

  // Primary glass specular — the bright highlight where light hits the glass surface
  const glassSpecularStyle = {
    position: 'absolute',
    inset: 0,
    borderRadius: '50%',
    background: `radial-gradient(ellipse 48% 38% at 34% 22%,
      rgba(255,255,255,0.88) 0%,
      rgba(255,255,255,0.50) 18%,
      rgba(255,255,255,0.18) 34%,
      transparent 52%)`,
    mixBlendMode: 'screen',
    pointerEvents: 'none',
  };

  // Secondary glass reflection — dim environmental reflection at lower right
  const glassReflectionStyle = {
    position: 'absolute',
    inset: 0,
    borderRadius: '50%',
    background: `radial-gradient(ellipse 28% 22% at 68% 76%,
      rgba(200, 225, 255, 0.22) 0%,
      rgba(200, 225, 255, 0.08) 45%,
      transparent 72%)`,
    mixBlendMode: 'screen',
    pointerEvents: 'none',
  };

  const pulseOrb = (nextBloom = 0.74, nextScale = 1.05, settleMs = 180) => {
    setBloomLevel(nextBloom);
    setOrbScale(nextScale);
    setTimeout(() => setOrbScale(1), settleMs);
  };

  const triggerSwarmDispatch = (spec = {}) => {
    const mission = typeof spec === 'number'
      ? { count: spec }
      : (spec && typeof spec === 'object' ? spec : {});
    const missionQuery = String(mission.query || '').trim();
    const classification = classifySwarmMission({
      query: missionQuery,
      requestedMode: mission.mode,
      complexity: mission.complexity,
    });
    if (!classification.deploy) {
      return false;
    }

    const missionMode = classification.missionMode;
    const deployZone = String(mission.deployZone || mission.deploy_zone || 'around').toLowerCase();
    const complexity = classification.complexity;
    const queryRequestedCount = extractRequestedSwarmCountFromQuery(missionQuery);
    const requestedCount = mission.count ?? queryRequestedCount;
    const lineage = resolvePrimeSwarmLineage(
      requestedCount,
      classification.swarmCount || choosePrimeSwarmCount(complexity)
    );
    const count = lineage.resolvedCount;

    if (swarmPhaseTimerRef.current) {
      clearTimeout(swarmPhaseTimerRef.current);
    }

    const missionId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    pendingSwarmMissionsRef.current.push({
      missionId,
      mode: missionMode,
      count,
      query: missionQuery,
      deployZone,
      lineage,
      at: Date.now(),
    });
    pendingSwarmMissionsRef.current = pendingSwarmMissionsRef.current.slice(-12);
    setSwarmPendingCount(pendingSwarmMissionsRef.current.length);
    setSwarmHudMissionMode(missionMode);
    setSwarmHudLastResult('pending');

    setTone(missionMode === 'diagnostics' ? 'Diagnostic dispatch' : 'Research dispatch');
    if (lineage.normalized && lineage.requestedCount !== null) {
      setBridgeStatus(`Dispatching ${count} Morbs (normalized from ${lineage.requestedCount})`);
      showSpeechBubble(
        `Prime normalization: requested ${lineage.requestedCount}, resolved ${count}`,
        { mode: 'state', persistMs: 2400 }
      );
    } else {
      setBridgeStatus(`Dispatching ${count} Morbs`);
    }
    if (globalThis?.ORB_DEBUG) {
      console.log('[SWARM_LINEAGE]', {
        phase: 'dispatch',
        missionId,
        missionMode,
        query: missionQuery,
        deployZone,
        requestedCount: lineage.requestedCount,
        resolvedCount: lineage.resolvedCount,
        requestedPrime: lineage.requestedPrime,
        normalized: lineage.normalized,
        lineageToken: lineage.lineageToken,
      });
    }
    setSwarmNodes((current) => [
      ...current.filter((node) => !String(node.phase || '').startsWith('out_')),
      ...makeOutboundSwarmNodes(count, { mode: missionMode, color: visual.color, deployZone }, egfState),
    ]);
    setBloomLevel(0.78);
    setOrbScale(1.06);
    setTimeout(() => setOrbScale(1), 210);
    return true;
  };

  const triggerSwarmReturn = ({ mode = 'research', query = '', resultState = 'success', count = null } = {}) => {
    const missionMode = normalizeMissionMode(mode);
    const pendingIndex = pendingSwarmMissionsRef.current.findIndex(
      (m) => m.mode === missionMode && (!query || !m.query || m.query === query)
    );
    const pending = pendingIndex >= 0 ? pendingSwarmMissionsRef.current.splice(pendingIndex, 1)[0] : null;
      setSwarmPendingCount(pendingSwarmMissionsRef.current.length);
    if (!pending && count === null) {
      return false;
    }

    const returnLineage = resolvePrimeSwarmLineage(
      count ?? pending?.count,
      choosePrimeSwarmCount(queryComplexityScore(query || pending?.query || '', missionMode))
    );
    const returnCount = returnLineage.resolvedCount;

    setTone(resultState === 'fault' ? 'Fault return' : resultState === 'warning' ? 'Warning return' : 'Success return');
      setSwarmHudMissionMode(missionMode);
      setSwarmHudLastResult(resultState);
    setBridgeStatus(`Returning ${returnCount} Morbs`);
    if (globalThis?.ORB_DEBUG) {
      console.log('[SWARM_LINEAGE]', {
        phase: 'return',
        missionId: pending?.missionId || null,
        missionMode,
        query: query || pending?.query || '',
        deployZone: pending?.deployZone || 'around',
        requestedCount: returnLineage.requestedCount,
        resolvedCount: returnLineage.resolvedCount,
        requestedPrime: returnLineage.requestedPrime,
        normalized: returnLineage.normalized,
        lineageToken: (pending?.lineage?.lineageToken || returnLineage.lineageToken),
      });
    }
    setSwarmNodes((current) => [
      ...current.filter((node) => !String(node.phase || '').startsWith('out_')),
      ...makeInboundSwarmNodes(returnCount, { mode: missionMode, color: visual.color, deployZone: pending?.deployZone || 'around' }, resultState, egfState),
    ]);
    setBloomLevel(resultState === 'fault' ? 0.95 : resultState === 'warning' ? 0.88 : 0.84);
    setOrbScale(1.06);
    setTimeout(() => setOrbScale(1), 210);
    return true;
  };

  return React.createElement(
    'div',
    {
        style: {
          position: 'fixed',
          inset: 0,
          background: 'transparent',
          pointerEvents: 'none',
          opacity: orbVisible ? 1 : 0,
          transition: 'opacity 220ms ease',
        },
      },
    React.createElement(
      'style',
      null,
      `
        @keyframes orbPulsePrimary {
          0%, 100% { transform: scale(0.96); opacity: 0.18; }
          45% { transform: scale(1.12); opacity: 0.5; }
          70% { transform: scale(1.2); opacity: 0.12; }
        }
        @keyframes orbPulseSecondary {
          0%, 100% { transform: scale(1.02); opacity: 0.08; }
          38% { transform: scale(1.22); opacity: 0.34; }
          82% { transform: scale(1.36); opacity: 0.04; }
        }
      `
    ),
    speechBubbleText
      ? React.createElement(
          'div',
          {
            style: {
              position: 'fixed',
              left: `${cursorPosition.x + 20}px`,
              top: `${cursorPosition.y - 64}px`,
              background:
                speechBubbleMode === 'state'
                  ? 'rgba(18,32,34,0.88)'
                  : 'rgba(20,20,30,0.92)',
              backdropFilter: 'blur(8px)',
              color: '#e2e8f0',
              padding: '8px 16px',
              borderRadius: '999px',
              fontSize: '13px',
              fontWeight: 500,
              maxWidth: '280px',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              boxShadow: '0 2px 12px rgba(0,0,0,0.4)',
              pointerEvents: 'none',
              zIndex: 9999,
              transition: 'opacity 0.2s ease, transform 0.2s ease',
              transform: speechBubbleMode === 'state' ? 'translateY(-2px)' : 'translateY(0)',
            },
          },
          speechBubbleText
        )
      : null,
    React.createElement(
      'div',
      {
        style: orbStyle,
        onMouseEnter: (event) => {
          if (event.shiftKey) {
            window.electronAPI?.setIgnoreMouseEvents(false);
          }
        },
        onMouseLeave: () => {
          if (!draggingRef.current) {
            window.electronAPI?.setIgnoreMouseEvents(true, { forward: true });
          }
        },
        onMouseDown: (event) => {
          if (event.button !== 0) {
            return;
          }

          event.preventDefault();
          setCommandOpen(true);
          window.electronAPI?.setIgnoreMouseEvents(false);
          draggingRef.current = true;
          dragOffsetRef.current = {
            x: event.clientX - cursorPositionRef.current.x,
            y: event.clientY - cursorPositionRef.current.y,
          };
          window.electronAPI?.setIgnoreMouseEvents(false);
        },
        onClick: () => {
          if (!draggingRef.current) {
            pulseOrb();
          }
        },
        onContextMenu: async (event) => {
          event.preventDefault();
          window.electronAPI?.setIgnoreMouseEvents(false);
          const text = window.prompt('Ask the orb', '');
          if (text === null) {
            return;
          }

          const trimmed = text.trim();
          if (!trimmed) {
            return;
          }

          setTone('Querying');
          setBridgeStatus(trimmed);
          pulseOrb(0.92, 1.08, 240);
          triggerSwarmDispatch({ query: trimmed });
          await window.electronAPI?.orbQuery?.(trimmed);
        },
        onDragOver: (event) => {
          event.preventDefault();
          setSocketHint('Release to socket');
          setBloomLevel(0.92);
        },
        onDragLeave: () => {
          setSocketHint(skinUrl ? 'Socket engaged' : 'Base frame');
        },
        onDrop: async (event) => {
          event.preventDefault();
          const droppedFilePath = event.dataTransfer?.files?.[0]?.path || '';
          const droppedUrl = event.dataTransfer?.getData('text/uri-list')
            || event.dataTransfer?.getData('text/plain')
            || '';

          if (droppedFilePath && window.electronAPI?.ingestOrbSkin) {
            const result = await window.electronAPI.ingestOrbSkin(droppedFilePath);
            setSkinUrl(result?.imageUrl || null);
            setSocketHint(result?.imageUrl ? 'Vaulted locally' : 'Base frame');
            triggerSwarmDispatch({ mode: 'research', query: 'skin ingest', count: 5 });
            return;
          }

          if (!droppedUrl || !window.electronAPI?.setOrbSkin) {
            setSocketHint(skinUrl ? 'Socket engaged' : 'Base frame');
            return;
          }
          const result = await window.electronAPI.setOrbSkin(droppedUrl);
          setSkinUrl(result?.imageUrl || null);
          setSocketHint(result?.imageUrl ? 'Socket engaged' : 'Base frame');
          triggerSwarmDispatch({ mode: 'research', query: 'skin set', count: 5 });
        },
        onDoubleClick: async (event) => {
          event.preventDefault();

          if (event.altKey) {
            if (!window.electronAPI?.setOrbSkin || !window.electronAPI?.ingestOrbSkin) {
              return;
            }
            const source = window.prompt('Set Orb skin source: local file path or direct image URL', skinUrl || '');
            if (source === null) {
              return;
            }
            const trimmed = source.trim();
            const isLocalPath = trimmed.startsWith('/') || /^[A-Za-z]:[\\/]/.test(trimmed);
            const result = isLocalPath
              ? await window.electronAPI.ingestOrbSkin(trimmed)
              : await window.electronAPI.setOrbSkin(trimmed);
            setSkinUrl(result?.imageUrl || null);
            setSocketHint(result?.imageUrl ? (isLocalPath ? 'Vaulted locally' : 'Socket engaged') : 'Base frame');
            triggerSwarmDispatch({ mode: 'research', query: 'skin update', count: 5 });
            return;
          }

          setTone('Voice capture');
          setBridgeStatus('Listening for speech');
          pulseOrb(1, 1.1, 300);
          const accepted = await window.electronAPI?.listenOnce?.();
          if (!accepted) {
            setTone('Voice busy');
            setBridgeStatus('Try again in a moment');
            setBloomLevel(0.62);
          }
        },
      },
      React.createElement(
        'div',
        { style: commandPanelStyle },
        React.createElement(
          'div',
          { style: { fontSize: '13px', marginBottom: '6px', opacity: 0.78 } },
          'Local CALI SKG - CP3 framed input'
        ),
        React.createElement('input', {
          type: 'text',
          value: commandText,
          onChange: (e) => setCommandText(e.target.value),
          placeholder: 'Ask, research, or shop...',
          style: {
            width: '100%',
            padding: '8px 10px',
            borderRadius: '10px',
            border: '1px solid rgba(103,198,255,0.5)',
            background: 'rgba(18,26,42,0.8)',
            color: '#e8f0ff',
            outline: 'none',
          },
          onFocus: () => window.electronAPI?.setIgnoreMouseEvents(false),
        }),
        React.createElement(
          'div',
          { style: buttonRowStyle },
          React.createElement(
            'button',
            {
              disabled: isSubmitting || !commandText.trim(),
              onClick: () => handleCommandSubmit('ask'),
              style: {
                flex: 1,
                padding: '8px 10px',
                borderRadius: '10px',
                border: '1px solid #63e6a6',
                background: '#0f1d2c',
                color: '#63e6a6',
                cursor: 'pointer',
              },
            },
            'Ask'
          ),
          React.createElement(
            'button',
            {
              disabled: isSubmitting || !commandText.trim(),
              onClick: () => handleCommandSubmit('search'),
              style: {
                flex: 1,
                padding: '8px 10px',
                borderRadius: '10px',
                border: '1px solid #67c6ff',
                background: '#0f1d2c',
                color: '#67c6ff',
                cursor: 'pointer',
              },
            },
            'Research'
          ),
          React.createElement(
            'button',
            {
              disabled: isSubmitting || !commandText.trim(),
              onClick: () => handleCommandSubmit('shop'),
              style: {
                flex: 1,
                padding: '8px 10px',
                borderRadius: '10px',
                border: '1px solid #f5c96a',
                background: '#0f1d2c',
                color: '#f5c96a',
                cursor: 'pointer',
              },
            },
            'Shop'
          )
        ),
        React.createElement(
          'div',
          { style: { display: 'flex', gap: '8px', marginTop: '8px' } },
          React.createElement(
            'button',
            {
              onClick: () => playNod('yes'),
              style: {
                flex: 1,
                padding: '6px 8px',
                borderRadius: '10px',
                border: '1px solid #63e6a6',
                background: '#0f1d2c',
                color: '#63e6a6',
                cursor: 'pointer',
              },
            },
            'Yes Nod'
          ),
          React.createElement(
            'button',
            {
              onClick: () => playNod('no'),
              style: {
                flex: 1,
                padding: '6px 8px',
                borderRadius: '10px',
                border: '1px solid #f5c96a',
                background: '#0f1d2c',
                color: '#f5c96a',
                cursor: 'pointer',
              },
            },
            'No Nod'
          )
        ),
        lastResponseText &&
          React.createElement(
            'div',
            {
              style: {
                marginTop: '10px',
                padding: '8px 10px',
                borderRadius: '10px',
                background: 'rgba(255,255,255,0.06)',
                color: '#dce7ff',
                fontSize: '12px',
                lineHeight: 1.45,
                maxHeight: '110px',
                overflow: 'auto',
              },
            },
            lastResponseText
          ),
        React.createElement(
          'div',
          {
            style: {
              marginTop: '8px',
              fontSize: '11px',
              color: '#8aa3c2',
              cursor: 'pointer',
              textAlign: 'right',
            },
            onClick: () => setCommandOpen(false),
          },
          'Hide'
        )
      ),
      ORB_SWARM_HUD_ENABLED
        ? React.createElement(
          'div',
          {
            style: {
              position: 'fixed',
              right: '16px',
              top: '14px',
              width: '280px',
              padding: '8px 10px',
              borderRadius: '8px',
              border: '1px solid rgba(103,198,255,0.28)',
              background: 'rgba(8,14,24,0.72)',
              color: '#d8f2ff',
              fontFamily: 'monospace',
              fontSize: '10px',
              lineHeight: 1.4,
              letterSpacing: '0.3px',
              pointerEvents: 'none',
              zIndex: 10000,
              backdropFilter: 'blur(6px)',
              boxShadow: '0 6px 22px rgba(0,0,0,0.35)',
              opacity: swarmHudHasActiveMission ? 1 : 0.46,
              transition: 'opacity 160ms ease',
            },
          },
          React.createElement('div', { style: { color: '#67c6ff', marginBottom: '4px' } }, 'SWARM HUD (DEV)'),
          React.createElement('div', { style: { color: swarmHudMissionColor } }, `mission: ${swarmHudMissionMode}`),
          React.createElement('div', null, `phase: ${swarmHudSnapshot.activePhase}`),
          React.createElement('div', null, `outbound: ${swarmHudSnapshot.outbound} | inbound: ${swarmHudSnapshot.inbound} | total: ${swarmHudSnapshot.total}`),
          React.createElement('div', { style: { color: swarmHudResultColor } }, `pending: ${swarmPendingCount} | last: ${swarmHudLastResult}`),
          React.createElement('div', null, `timing(ms): o_spin ${SWARM_TIMING.phaseMs.out_spin}, o_dart ${SWARM_TIMING.phaseMs.out_dart}, i_arc ${SWARM_TIMING.phaseMs.in_arc}, i_loop ${SWARM_TIMING.phaseMs.in_loop}, ingest ${SWARM_TIMING.phaseMs.ingest}`),
          React.createElement('div', null, `diag x${SWARM_TIMING.modeMultiplier.diagnostics.toFixed(2)} | egf c:${egfCenterEntropy.toFixed(2)} a:${egfActivationLevel.toFixed(2)} o:${egfOuterEntropy.toFixed(2)} r:${egfRenewalPressure.toFixed(2)}`)
        )
        : null,
      ingestRipples.map((ripple) => {
        const age = Date.now() - ripple.startedAt;
        const progress = clamp(age / SWARM_RIPPLE_MS, 0, 1);
        const radius = 28 + progress * 66;
        const opacity = 0.56 * (1 - progress);
        const color = SWARM_RESULT_COLORS[ripple.resultState] || SWARM_RESULT_COLORS.success;
        const thickness = 1 + clamp(egfCenterEntropy * 0.6, 0, 1.4);
        const glow = 0.35 + egfActivationLevel * 0.45;
        return React.createElement('div', {
          key: ripple.id,
          style: {
            position: 'absolute',
            left: '50%',
            top: '46%',
            width: `${radius}px`,
            height: `${radius}px`,
            borderRadius: '50%',
            border: `${thickness}px solid ${color}`,
            boxShadow: `0 0 ${18 + egfActivationLevel * 18}px ${color}`,
            transform: 'translate(-50%, -50%)',
            opacity: opacity * glow,
            pointerEvents: 'none',
          },
        });
      }),
      swarmNodes.map((node) => {
        const vector = nodeVector(node);
        const radius = Math.hypot(vector.x, vector.y);
        const tetherOpacity = node.phase === 'in_arc' || node.phase === 'in_loop'
          ? 0.15 + egfRenewalPressure * 0.1
          : 0;
        const lineAngle = Math.atan2(vector.y, vector.x) * (180 / Math.PI);
        const trailLength = Math.max(8, Number(vector.trailLength || 10));
        const trailOpacity = clamp(Number(vector.trailOpacity || 0.2), 0.08, 0.5);
        const nodeSize = Math.max(1, vector.size);
        const nodeHeight = Math.max(1, nodeSize * MICRO_ORB_ASPECT_RATIO);

        return React.createElement(
          React.Fragment,
          { key: node.id },
          tetherOpacity > 0
            ? React.createElement('div', {
              style: {
                position: 'absolute',
                left: '50%',
                top: '46%',
                width: `${radius}px`,
                height: '1px',
                background: vector.color,
                transformOrigin: '0 50%',
                transform: `translate(-50%, -50%) rotate(${lineAngle}deg)`,
                opacity: tetherOpacity,
                boxShadow: `0 0 ${8 + egfRenewalPressure * 8}px ${vector.color}`,
                pointerEvents: 'none',
              },
            })
            : null,
          React.createElement('div', {
            style: {
              position: 'absolute',
              left: '50%',
              top: '46%',
              width: `${trailLength}px`,
              height: `${Math.max(1, nodeHeight * 0.5)}px`,
              borderRadius: '999px',
              background: `linear-gradient(90deg, transparent, ${vector.color})`,
              transform: `translate(calc(-50% + ${vector.x - trailLength * 0.55}px), calc(-50% + ${vector.y}px))`,
              opacity: trailOpacity,
              filter: 'blur(1px)',
              pointerEvents: 'none',
            },
          }),
          React.createElement(
            'div',
            {
              style: {
                position: 'absolute',
                left: '50%',
                top: '46%',
                width: `${nodeSize}px`,
                height: `${nodeHeight}px`,
                borderRadius: '50%',
                background: MICRO_ORB_TEXTURE_URL
                  ? `radial-gradient(circle at 35% 25%, rgba(255,255,255,0.85), ${vector.color} 32%, rgba(16,18,28,0.98) 88%), url("${MICRO_ORB_TEXTURE_URL}")`
                  : `radial-gradient(circle at 35% 25%, rgba(255,255,255,0.85), ${vector.color} 32%, rgba(16,18,28,0.98) 88%)`,
                backgroundSize: 'cover',
                backgroundBlendMode: 'screen',
                boxShadow: `0 0 20px ${vector.color}`,
                border: `1px solid rgba(255,255,255,0.28)`,
                transform: `translate(calc(-50% + ${vector.x}px), calc(-50% + ${vector.y}px))`,
                opacity: vector.opacity,
                transition: 'transform 16ms linear, opacity 16ms linear',
                pointerEvents: 'none',
              },
            },
            React.createElement('div', {
              style: {
                position: 'absolute',
                inset: '18% 22%',
                borderRadius: '50%',
                boxShadow: `0 0 10px ${vector.color}`,
                background: `radial-gradient(circle, rgba(255,255,255,0.75), ${vector.color} 60%, transparent 80%)`,
                opacity: 0.85,
              },
            }),
            React.createElement('div', {
              style: {
                position: 'absolute',
                inset: '8%',
                borderRadius: '50%',
                border: `1px solid ${vector.color}`,
                opacity: node.phase === 'out_spin' || node.phase === 'out_dart' ? 0.88 : 0.52,
                transform: `rotate(${(Date.now() / (node.phase === 'out_spin' ? 4.2 : 9.5)) % 360}deg)`,
              },
            })
          )
        );
      }),
      React.createElement('div', { style: secondaryPulseLayerStyle }),
      React.createElement('div', { style: primaryPulseLayerStyle }),
      React.createElement('div', { style: auraStyle }),
      // Glass casing — outer glass shell encases the inner skin/content
      React.createElement(
        'div',
        { style: glassShellStyle },
        // Inner volume — the skin lives here, protected by the glass
        React.createElement(
          'div',
          { style: innerVolumeStyle },
          skinUrl && React.createElement('div', { style: skinImageStyle })
        ),
        // Caustic refraction ring at inner glass edge
        React.createElement('div', { style: glassCausticStyle }),
        // Primary specular highlight (top-left, main light source)
        React.createElement('div', { style: glassSpecularStyle }),
        // Secondary environmental reflection (bottom-right)
        React.createElement('div', { style: glassReflectionStyle })
      )
    )
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(React.createElement(FloatingOrb));
