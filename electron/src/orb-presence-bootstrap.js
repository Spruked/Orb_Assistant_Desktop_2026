/* Active-display presence bootstrap.
 * Loaded before orb-renderer.js so passive pointer reports can be converted
 * into autonomous workspace references without changing the renderer body.
 */
(function () {
  'use strict';

  const api = window.electronAPI;
  if (!api || typeof api.onOrbPositionUpdate !== 'function') return;

  const subscribe = api.onOrbPositionUpdate.bind(api);
  const EDGE_MARGIN = 188;
  const CURSOR_EXCLUSION = 520;
  const ACTIVE_RETARGET_MS = 4600;
  const IDLE_RETARGET_MS = 9000;
  const POINTER_CHANGE_TRIGGER = 190;
  const state = {
    active: false,
    idle: false,
    idleSeconds: 0,
    actualCursor: null,
    locus: null,
    lastRetargetAt: 0,
  };

  const clamp = (value, low, high) => Math.min(high, Math.max(low, value));
  const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

  function bounds() {
    const width = Math.max(1, window.innerWidth || 1);
    const height = Math.max(1, window.innerHeight || 1);
    const margin = Math.min(EDGE_MARGIN, Math.max(92, Math.floor(Math.min(width, height) * 0.2)));
    return {
      width,
      height,
      minX: margin,
      maxX: Math.max(margin, width - margin),
      minY: margin,
      maxY: Math.max(margin, height - margin),
    };
  }

  function clampPoint(point, viewport = bounds()) {
    return {
      x: clamp(Number(point?.x) || viewport.width * 0.5, viewport.minX, viewport.maxX),
      y: clamp(Number(point?.y) || viewport.height * 0.5, viewport.minY, viewport.maxY),
    };
  }

  function selectLocus() {
    const viewport = bounds();
    const cursor = state.actualCursor ? clampPoint(state.actualCursor, viewport) : null;
    const current = state.locus ? clampPoint(state.locus, viewport) : null;
    const center = { x: viewport.width * 0.5, y: viewport.height * 0.5 };
    let best = null;
    let bestScore = -Infinity;

    for (let i = 0; i < 28; i += 1) {
      const candidate = {
        x: viewport.minX + Math.random() * Math.max(1, viewport.maxX - viewport.minX),
        y: viewport.minY + Math.random() * Math.max(1, viewport.maxY - viewport.minY),
      };
      const cursorDistance = cursor ? distance(candidate, cursor) : CURSOR_EXCLUSION;
      const travelDistance = current ? distance(candidate, current) : 260;
      const edgeSlack = Math.min(
        candidate.x - viewport.minX,
        viewport.maxX - candidate.x,
        candidate.y - viewport.minY,
        viewport.maxY - candidate.y
      );
      const centerPenalty = Math.max(0, distance(candidate, center) - Math.min(viewport.width, viewport.height) * 0.42) * 0.34;
      const score = Math.min(cursorDistance, 900) * 1.35
        + Math.min(travelDistance, 540) * 0.45
        + edgeSlack * 1.1
        - centerPenalty;

      if (cursor && cursorDistance < CURSOR_EXCLUSION && best) continue;
      if (score > bestScore) {
        best = candidate;
        bestScore = score;
      }
    }

    if (!best) {
      best = clampPoint({
        x: center.x + (cursor && cursor.x > center.x ? -1 : 1) * viewport.width * 0.22,
        y: center.y + (cursor && cursor.y > center.y ? -1 : 1) * viewport.height * 0.16,
      }, viewport);
    }

    state.locus = clampPoint(best, viewport);
    state.lastRetargetAt = Date.now();
    return state.locus;
  }

  function needsRetarget(nextCursor) {
    if (!state.locus) return true;
    if (Date.now() - state.lastRetargetAt >= (state.idle ? IDLE_RETARGET_MS : ACTIVE_RETARGET_MS)) return true;
    if (!state.actualCursor || !nextCursor) return false;
    if (distance(state.actualCursor, nextCursor) >= POINTER_CHANGE_TRIGGER) return true;
    return distance(state.locus, nextCursor) < CURSOR_EXCLUSION;
  }

  function mapPassivePointer(payload) {
    if (!payload || payload.active === false) {
      state.active = false;
      return payload;
    }

    const actual = clampPoint({
      x: payload.x ?? window.innerWidth * 0.5,
      y: payload.y ?? window.innerHeight * 0.5,
    });
    if (needsRetarget(actual)) {
      state.actualCursor = actual;
      selectLocus();
    } else {
      state.actualCursor = actual;
    }

    state.active = true;
    const locus = clampPoint(state.locus || selectLocus());
    return {
      ...payload,
      x: locus.x,
      y: locus.y,
      workspaceMotion: true,
      cursorIsContextOnly: true,
    };
  }

  api.onOrbPositionUpdate = function (callback) {
    return subscribe((event, payload) => callback(event, mapPassivePointer(payload)));
  };

  if (typeof api.onOrbBridgeMessage === 'function') {
    const subscribeBridge = api.onOrbBridgeMessage.bind(api);
    api.onOrbBridgeMessage = function (callback) {
      return subscribeBridge((event, message) => {
        if (message?.type === 'presence_update' || message?.type === 'presence_pulse') {
          const profile = message?.type === 'presence_update' ? message : (message?.data?.presence_profile || {});
          state.idle = Boolean(profile?.is_idle ?? profile?.idle);
          state.idleSeconds = Number(profile?.idle_seconds || 0);
        }
        callback(event, message);
      });
    };
  }

  window.orbWorkspaceMotionPolicy = {
    getStatus: () => ({ ...state }),
    retarget: () => selectLocus(),
    setTaskLocus: (point) => {
      state.locus = clampPoint(point);
      state.lastRetargetAt = Date.now();
      return state.locus;
    },
  };
})();
