/*
 * Workspace motion policy for the desktop ORB.
 *
 * This shim is loaded before orb-renderer.js.  It preserves the existing
 * renderer body, visual states, DockStation transition, and display plumbing,
 * but changes the meaning of incoming position updates:
 *
 *   - Electron still tells us which display is active and where the real cursor is.
 *   - The renderer receives a generated workspace locus instead of the real cursor.
 *   - The real cursor is used only to keep that locus out of the operator's path.
 *
 * The result is an ORB that inhabits the active display and roams independently,
 * rather than orbiting the pointer.  Task-directed movement remains a separate
 * concern and must be supplied by an explicit task target, never by passive
 * cursor motion.
 */
(function installWorkspaceMotionPolicy() {
  'use strict';

  const api = window.electronAPI;
  if (!api || typeof api.onOrbPositionUpdate !== 'function') {
    return;
  }

  const originalSubscribe = api.onOrbPositionUpdate.bind(api);
  const MIN_EDGE_MARGIN = 188;
  const CURSOR_EXCLUSION_RADIUS = 520;
  const RETARGET_MS_ACTIVE = 4600;
  const RETARGET_MS_IDLE = 9000;
  const MOVEMENT_TRIGGER_PX = 190;

  const state = {
    active: false,
    actualCursor: null,
    locus: null,
    lastLocus: null,
    lastRetargetAt: 0,
    idle: false,
    idleSeconds: 0,
  };

  function clamp(value, lower, upper) {
    return Math.min(upper, Math.max(lower, value));
  }

  function viewportBounds() {
    const width = Math.max(1, window.innerWidth || 1);
    const height = Math.max(1, window.innerHeight || 1);
    const margin = Math.min(
      MIN_EDGE_MARGIN,
      Math.max(92, Math.floor(Math.min(width, height) * 0.2))
    );
    return {
      width,
      height,
      margin,
      minX: margin,
      maxX: Math.max(margin, width - margin),
      minY: margin,
      maxY: Math.max(margin, height - margin),
    };
  }

  function distance(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  function clampPoint(point, bounds = viewportBounds()) {
    return {
      x: clamp(Number(point?.x) || bounds.width * 0.5, bounds.minX, bounds.maxX),
      y: clamp(Number(point?.y) || bounds.height * 0.5, bounds.minY, bounds.maxY),
    };
  }

  function randomPoint(bounds) {
    return {
      x: bounds.minX + Math.random() * Math.max(1, bounds.maxX - bounds.minX),
      y: bounds.minY + Math.random() * Math.max(1, bounds.maxY - bounds.minY),
    };
  }

  function chooseWorkspaceLocus() {
    const bounds = viewportBounds();
    const cursor = state.actualCursor ? clampPoint(state.actualCursor, bounds) : null;
    const current = state.locus ? clampPoint(state.locus, bounds) : null;
    const viewportCenter = { x: bounds.width * 0.5, y: bounds.height * 0.5 };

    let best = null;
    let bestScore = -Infinity;

    for (let index = 0; index < 28; index += 1) {
      const candidate = randomPoint(bounds);
      const cursorDistance = cursor ? distance(candidate, cursor) : CURSOR_EXCLUSION_RADIUS;
      const currentDistance = current ? distance(candidate, current) : 220;
      const centerDistance = distance(candidate, viewportCenter);
      const edgeSlack = Math.min(
        candidate.x - bounds.minX,
        bounds.maxX - candidate.x,
        candidate.y - bounds.minY,
        bounds.maxY - candidate.y
      );
      const cursorScore = Math.min(cursorDistance, 900) * 1.35;
      const travelScore = Math.min(currentDistance, 540) * 0.45;
      const spaceScore = edgeSlack * 1.1;
      const centerPenalty = Math.max(0, centerDistance - Math.min(bounds.width, bounds.height) * 0.42) * 0.34;
      const score = cursorScore + travelScore + spaceScore - centerPenalty;

      if (cursor && cursorDistance < CURSOR_EXCLUSION_RADIUS && best) {
        continue;
      }
      if (score > bestScore) {
        best = candidate;
        bestScore = score;
      }
    }

    if (!best) {
      const fallback = {
        x: viewportCenter.x + (cursor && cursor.x > viewportCenter.x ? -1 : 1) * bounds.width * 0.22,
        y: viewportCenter.y + (cursor && cursor.y > viewportCenter.y ? -1 : 1) * bounds.height * 0.16,
      };
      best = clampPoint(fallback, bounds);
    }

    state.lastLocus = state.locus;
    state.locus = clampPoint(best, bounds);
    state.lastRetargetAt = Date.now();
    return state.locus;
  }

  function shouldRetarget(nextCursor) {
    if (!state.locus) {
      return true;
    }

    const now = Date.now();
    const interval = state.idle ? RETARGET_MS_IDLE : RETARGET_MS_ACTIVE;
    if (now - state.lastRetargetAt >= interval) {
      return true;
    }

    if (!state.actualCursor || !nextCursor) {
      return false;
    }

    if (distance(state.actualCursor, nextCursor) >= MOVEMENT_TRIGGER_PX) {
      return true;
    }

    return distance(state.locus, nextCursor) < CURSOR_EXCLUSION_RADIUS;
  }

  function normalizeIncoming(payload) {
    if (!payload || payload.active === false) {
      state.active = false;
      return payload;
    }

    const nextCursor = clampPoint({
      x: payload.x ?? window.innerWidth * 0.5,
      y: payload.y ?? window.innerHeight * 0.5,
    });

    if (shouldRetarget(nextCursor)) {
      // Store the real cursor before selecting a new locus so the locus is chosen away from it.
      state.actualCursor = nextCursor;
      chooseWorkspaceLocus();
    } else {
      state.actualCursor = nextCursor;
    }

    state.active = true;
    const locus = clampPoint(state.locus || chooseWorkspaceLocus());

    return {
      ...payload,
      // The renderer treats these as its motion reference.  They are deliberately
      // not the real pointer coordinates.
      x: locus.x,
      y: locus.y,
      workspaceMotion: true,
      cursorIsContextOnly: true,
    };
  }

  // Preserve renderer subscription behavior while replacing passive cursor
  // anchoring with active-display workspace roaming.
  api.onOrbPositionUpdate = function onOrbPositionUpdate(callback) {
    return originalSubscribe((event, payload) => {
      callback(event, normalizeIncoming(payload));
    });
  };

  // Presence events are already emitted by Python.  They only tune the cadence;
  // they never turn ordinary cursor movement into a physical target.
  if (typeof api.onOrbBridgeMessage === 'function') {
    const originalBridgeSubscribe = api.onOrbBridgeMessage.bind(api);
    api.onOrbBridgeMessage = function onOrbBridgeMessage(callback) {
      return originalBridgeSubscribe((event, message) => {
        if (message?.type === 'presence_update' || message?.type === 'presence_pulse') {
          const profile = message?.type === 'presence_update'
            ? message
            : (message?.data?.presence_profile || {});
          state.idle = Boolean(profile?.is_idle ?? profile?.idle);
          state.idleSeconds = Number(profile?.idle_seconds || 0);
        }
        callback(event, message);
      });
    };
  }

  // Reserved explicit interface for future MCP/task choreography.  Nothing in
  // the passive cursor path calls this.  A task runner must call it deliberately.
  window.orbWorkspaceMotionPolicy = {
    getStatus: () => ({
      active: state.active,
      idle: state.idle,
      idleSeconds: state.idleSeconds,
      actualCursor: state.actualCursor,
      workspaceLocus: state.locus,
    }),
    retarget: () => chooseWorkspaceLocus(),
    setTaskLocus: (point) => {
      state.lastLocus = state.locus;
      state.locus = clampPoint(point);
      state.lastRetargetAt = Date.now();
      return state.locus;
    },
  };
})();
