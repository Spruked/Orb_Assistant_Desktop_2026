import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactDOM from "react-dom/client";

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const toJulianDate = (epochMs) => epochMs / 86400000 + 2440587.5;
const toClock = (epochMs) => new Date(epochMs).toTimeString().slice(0, 8);
const toNumberOr = (value, fallback) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
};
const truncate = (value, max = 26) => {
  const text = String(value ?? "unknown");
  return text.length > max ? `${text.slice(0, max)}...` : text;
};
const PRIME_SWARM_COUNTS = [2, 3, 5, 7, 11];
const normalizeRequestedPrimeCount = (value, fallback = PRIME_SWARM_COUNTS[2]) => {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  const candidate = Math.max(2, Math.trunc(n));
  const resolved = PRIME_SWARM_COUNTS.find((p) => p >= candidate);
  return resolved || PRIME_SWARM_COUNTS[PRIME_SWARM_COUNTS.length - 1];
};
const computePrimeSetForQuery = (query, mode) => {
  const words = String(query || "").trim().split(/\s+/).filter(Boolean).length;
  const modeBoost = String(mode || "research").toLowerCase() === "diagnostics" ? 0.12 : 0.04;
  const score = clamp(words / 22 + modeBoost, 0, 1);
  if (score < 0.2) return PRIME_SWARM_COUNTS[0];
  if (score < 0.4) return PRIME_SWARM_COUNTS[1];
  if (score < 0.62) return PRIME_SWARM_COUNTS[2];
  if (score < 0.82) return PRIME_SWARM_COUNTS[3];
  return PRIME_SWARM_COUNTS[4];
};
const STATION_CONFIG_KEY = "orb.dock.station.config.v1";
const safeReadJson = (key, fallback) => {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : fallback;
  } catch (_error) {
    return fallback;
  }
};

const INITIAL_HLSF_SNAPSHOT = {
  position: [0, 0],
  active_dims: [],
  hysteresis: { trigger: 800, release: 650, active: false, density_ratio: 0 },
  field_density: 0,
  semantic_tag: "idle",
};

const INITIAL_TELEMETRY = {
  systemHealth: 0,
  coreIntegrity: 0,
  uptimeSeconds: 0,
  epochTime: Date.now(),
  julianDate: toJulianDate(Date.now()),
  activeLLM: "unknown",
  llmLatency: 0,
  llmSuccessRate: 0,
  governanceIntegrity: 0,
  complianceScore: 0,
  confidenceWeight: 0,
  consensusIndex: 0,
  driftLevel: 0,
  anomalies: 0,
  responseSpeed: 0,
  throughput: 0,
  efficiency: 0,
  memUsage: 0,
  cpuLoad: 0,
  networkActivity: 0,
  instanceId: "unknown",
  controllerStatus: "unknown",
  listeningEnabled: false,
  autoListen: false,
  presenceRunning: false,
  presenceIdle: false,
  idleSeconds: 0,
  activeWindow: "unknown",
  activeProcess: "unknown",
  lastEvent: "boot",
  cognitiveMode: "UNKNOWN",
  autonomyLevel: 0,
  confidenceState: 0,
  presenceSchemaVersion: "n/a",
  presenceTs: 0,
  device: "unknown",
  vramGb: 0,
  encoderBackend: "unknown",
  knowledgeGraphNodes: 0,
  knowledgeGraphEdges: 0,
  interactionCount: 0,
  projectRoot: "n/a",
  systemRoot: "n/a",
  sharedMeshRoot: "n/a",
  swarmRunning: false,
  orbRuntimeActive: false,
  dockChannelConnected: false,
  llmConnected: false,
  voiceProviderReady: false,
  voiceProvider: "unknown",
  orbVisible: false,
  orbDocked: true,
  orbReadinessOk: false,
  orbApiUrl: "http://127.0.0.1:21100/api/v1",
  statusReason: "",
  fourMind: { caleon: 0.5, kaygee: 0.5, cali_x_one: 0.5, empirical: 0.5 },
  fieldDensity: 0,
  epistemicAlignment: 0,
  spatialCoord: null,
  driftDetected: false,
  hlsfSnapshot: INITIAL_HLSF_SNAPSHOT,
  egfState: { ok: false, mode: "unknown", error: "" },
  siteOrbStatus: {},
  events: [],
};

function useTelemetry() {
  const bootRef = useRef(Date.now());
  const nextId = useRef(1);
  const statsRef = useRef({ total: 0, ok: 0, err: 0 });
  const lastIdleRef = useRef(null);
  const lastRunningRef = useRef(null);
  const lastControllerRef = useRef(null);
  const lastHlsfEdgeRef = useRef(null);
  const [t, setT] = useState(() => ({
    ...INITIAL_TELEMETRY,
    events: [
      {
        id: 0,
        time: toClock(Date.now()),
        type: "INFO",
        msg: "Dock station connected. Awaiting bridge telemetry.",
      },
    ],
  }));

  const pushEvent = useCallback((type, msg) => {
    setT((prev) => {
      const events = [
        {
          id: nextId.current++,
          time: toClock(Date.now()),
          type,
          msg,
        },
        ...prev.events,
      ].slice(0, 20);
      return { ...prev, events };
    });
  }, []);

  const applyReliability = useCallback(() => {
    setT((prev) => {
      const total = Math.max(0, statsRef.current.total);
      const success = total > 0 ? (statsRef.current.ok / total) * 100 : 0;
      return {
        ...prev,
        llmSuccessRate: clamp(success, 0, 100),
        anomalies: statsRef.current.err,
        efficiency: clamp(success, 0, 100),
      };
    });
  }, []);

  const markSuccess = useCallback(() => {
    statsRef.current.total += 1;
    statsRef.current.ok += 1;
    applyReliability();
  }, [applyReliability]);

  const markError = useCallback(() => {
    statsRef.current.total += 1;
    statsRef.current.err += 1;
    applyReliability();
  }, [applyReliability]);

  const applyStatus = useCallback(
    (status, source = "status_sync") => {
      if (!status || typeof status !== "object") {
        return;
      }

      const runtimeSnapshot =
        status.runtime_snapshot && typeof status.runtime_snapshot === "object"
          ? status.runtime_snapshot
          : null;
      if (status.pending && !runtimeSnapshot) {
        setT((prev) => ({
          ...prev,
          dockChannelConnected: false,
          lastEvent: String(status.error || "backend status pending"),
        }));
        pushEvent("WARN", "Backend status pending");
        return;
      }

      const presence = status.desktop_presence || {};
      const presenceSnapshot =
        status.presence_update && typeof status.presence_update === "object"
          ? status.presence_update
          : null;

      const snapshotControllerState = String(runtimeSnapshot?.controller_state || "").toLowerCase();
      const running = runtimeSnapshot
        ? ["starting", "ready", "degraded"].includes(snapshotControllerState)
        : Boolean(status.running);
      const controllerStatus = String(
        runtimeSnapshot?.controller_state || status.controller_status || "unknown"
      );
      const controllerReady = ["active", "ready"].includes(
        controllerStatus.toLowerCase()
      );

      const snapshotIdle = runtimeSnapshot
        ? String(runtimeSnapshot.presence_state || "").toLowerCase() === "idle"
        : presenceSnapshot
        ? Boolean(presenceSnapshot.idle)
        : Boolean(presence.is_idle);
      const snapshotIdleSeconds = presenceSnapshot
        ? Math.max(0, toNumberOr(presenceSnapshot.idle_seconds, 0))
        : Math.max(0, toNumberOr(presence.idle_seconds, 0));
      const caliStatus = status.cali_status || {};
      const localLlm = status.local_llm || {};
      const activeModel =
        runtimeSnapshot?.active_llm ||
        localLlm.model ||
        caliStatus?.orb_state?.llm_local_model ||
        status.active_llm ||
        "unknown";
      const llmRuntime = localLlm.last_runtime || {};
      const llmRoute = String(localLlm.route || "").toLowerCase();
      const localLlmHealthy = runtimeSnapshot
        ? Boolean(runtimeSnapshot.llm_connected)
        : Boolean(localLlm.connected === true || localLlm.ready === true);
      const cp3Audio = status?.cp3_io?.audio_runtime_status || {};
      const qwenTts = status?.qwen_tts || {};
      const voiceProvider = String(
        runtimeSnapshot
          ? (runtimeSnapshot.qwen_tts_ready ? "qwen" : runtimeSnapshot.qwen_last_provider || "unknown")
          : (
              cp3Audio.tts_provider ||
              (qwenTts.endpoint ? "qwen" : null) ||
              cp3Audio.voice_provider ||
              (status?.cp3_io?.voice_runtime_ready ? "cp3" : "unknown")
            )
      );
      const qwenHealthy = Boolean(qwenTts.ready === true);
      const cp3VoiceReady = Boolean(
        status?.cp3_io?.voice_runtime_ready ||
        ["online", "ready", "active"].includes(String(cp3Audio.voice || "").toLowerCase())
      );
      const voiceProviderReady = runtimeSnapshot
        ? Boolean(runtimeSnapshot.voice_ready)
        : Boolean(qwenHealthy || cp3VoiceReady);
      const confidenceRaw = runtimeSnapshot
        ? toNumberOr(runtimeSnapshot.confidence, 0)
        : presenceSnapshot
        ? toNumberOr(presenceSnapshot.confidence_state, 0)
        : 0;
      const autonomyRaw = presenceSnapshot
        ? toNumberOr(presenceSnapshot.autonomy_level, 0)
        : 0;
      const listeningActive = Boolean(
        runtimeSnapshot?.listening ||
        status?.listening_enabled ||
        status?.cp3_io?.listening_enabled
      );

      setT((prev) => ({
        ...prev,
        systemHealth: running ? (controllerReady ? 100 : 72) : 0,
        coreIntegrity: controllerReady ? 100 : running ? 70 : 0,
        activeLLM: String(activeModel),
        orbRuntimeActive: running,
        dockChannelConnected: Boolean(runtimeSnapshot?.dock_channel_connected ?? false),
        llmConnected:
          runtimeSnapshot
            ? Boolean(runtimeSnapshot.llm_connected)
            : llmRoute === "local"
            ? localLlmHealthy
            : Boolean(status.active_llm && String(status.active_llm).toLowerCase() !== "unknown"),
        voiceProviderReady,
        voiceProvider,
        governanceIntegrity:
          runtimeSnapshot
            ? (String(runtimeSnapshot.governance_wrapper || "").toLowerCase() === "on" ? 100 : 0)
            : running && controllerReady ? 100 : 0,
        complianceScore: running ? 100 : 0,
        driftLevel: 0,
        throughput: toNumberOr(runtimeSnapshot?.interactions, toNumberOr(caliStatus.interaction_count, prev.throughput)),
        responseSpeed: prev.responseSpeed,
        networkActivity: prev.networkActivity,
        instanceId: String(status.instance_id || prev.instanceId || "unknown"),
        controllerStatus,
        listeningEnabled: listeningActive,
        autoListen: Boolean(runtimeSnapshot?.auto_listen ?? status.auto_listen),
        presenceRunning: runtimeSnapshot
          ? String(runtimeSnapshot.presence_state || "").toLowerCase() !== "offline"
          : Boolean(presence.running),
        presenceIdle: snapshotIdle,
        idleSeconds: Math.round(snapshotIdleSeconds),
        activeWindow: presenceSnapshot
          ? String(presenceSnapshot.active_window || prev.activeWindow || "unknown")
          : prev.activeWindow,
        activeProcess: presenceSnapshot
          ? String(presenceSnapshot.active_process || prev.activeProcess || "unknown")
          : prev.activeProcess,
        lastEvent: presenceSnapshot
          ? String(presenceSnapshot.last_event || prev.lastEvent || "presence")
          : prev.lastEvent,
        cognitiveMode: presenceSnapshot
          ? String(presenceSnapshot.cognitive_mode || prev.cognitiveMode || "DEDUCTIVE")
          : prev.cognitiveMode,
        autonomyLevel: clamp(
          presenceSnapshot ? autonomyRaw : prev.autonomyLevel,
          0,
          1
        ),
        confidenceState: clamp(
          runtimeSnapshot || presenceSnapshot ? confidenceRaw : prev.confidenceState,
          0,
          1
        ),
        presenceSchemaVersion: presenceSnapshot
          ? String(presenceSnapshot.schema_version || prev.presenceSchemaVersion || "1.0")
          : prev.presenceSchemaVersion,
        presenceTs: presenceSnapshot
          ? toNumberOr(presenceSnapshot.ts, prev.presenceTs)
          : prev.presenceTs,
        cpuLoad: presenceSnapshot
          ? clamp(toNumberOr(presenceSnapshot.cpu, prev.cpuLoad / 100) * 100, 0, 100)
          : prev.cpuLoad,
        memUsage: presenceSnapshot
          ? clamp(toNumberOr(presenceSnapshot.memory, prev.memUsage / 100) * 100, 0, 100)
          : prev.memUsage,
        device: String(caliStatus.device || prev.device || "unknown"),
        vramGb: Math.max(0, toNumberOr(caliStatus.vram_gb, prev.vramGb)),
        encoderBackend: String(
          runtimeSnapshot?.encoder || caliStatus.encoder_backend || prev.encoderBackend || "unknown"
        ),
        knowledgeGraphNodes: Math.max(
          0,
          toNumberOr(caliStatus.knowledge_graph_nodes, prev.knowledgeGraphNodes)
        ),
        knowledgeGraphEdges: Math.max(
          0,
          toNumberOr(caliStatus.knowledge_graph_edges, prev.knowledgeGraphEdges)
        ),
        interactionCount: Math.max(
          0,
          toNumberOr(runtimeSnapshot?.interactions, toNumberOr(caliStatus.interaction_count, prev.interactionCount))
        ),
        anomalies: Math.max(0, toNumberOr(runtimeSnapshot?.anomalies, prev.anomalies)),
        llmSuccessRate: clamp(toNumberOr(runtimeSnapshot?.success_rate, prev.llmSuccessRate), 0, 1),
        projectRoot: String(status.project_root || prev.projectRoot || "n/a"),
        systemRoot: String(status.system_root || prev.systemRoot || "n/a"),
        sharedMeshRoot: String(
          status.shared_mesh_root || prev.sharedMeshRoot || "n/a"
        ),
        swarmRunning: Boolean(status?.swarm_extension?.running),
        egfState:
          status?.egf_state && typeof status.egf_state === "object"
            ? {
                ok: status.egf_state.ok !== false,
                mode: String(status.egf_state.mode || "active"),
                error: String(status.egf_state.error || ""),
              }
            : prev.egfState,
        siteOrbStatus:
          status?.site_orb_status && typeof status.site_orb_status === "object"
            ? status.site_orb_status
            : prev.siteOrbStatus,
        statusReason: String(status.error || ""),
      }));

      if (lastRunningRef.current === null || lastRunningRef.current !== running) {
        pushEvent("INFO", `Runtime ${running ? "running" : "stopped"}`);
      } else if (
        lastControllerRef.current === null ||
        lastControllerRef.current !== controllerStatus
      ) {
        pushEvent("INFO", `Controller ${controllerStatus}`);
      } else if (lastIdleRef.current === null || lastIdleRef.current !== snapshotIdle) {
        pushEvent("INFO", `Presence ${snapshotIdle ? "idle" : "active"} (${Math.round(snapshotIdleSeconds)}s idle)`);
      } else if (source === "poll") {
        pushEvent("PASS", "Status sync complete");
      }
      lastRunningRef.current = running;
      lastControllerRef.current = controllerStatus;
      lastIdleRef.current = snapshotIdle;
    },
    [pushEvent]
  );

  const applyCognitivePulse = useCallback(
    (pulse, source = "cognitive") => {
      if (!pulse || typeof pulse !== "object") {
        return;
      }
      const advisory = pulse.advisory_verdict || {};
      const confidence = clamp(
        toNumberOr(advisory.confidence, toNumberOr(pulse.confidence, 0.82)),
        0,
        1
      );
      const mode = String(pulse.cognitive_mode || pulse.mode || "DEDUCTIVE");
      const tension = Boolean(advisory.tension_detected);
      const activeModel = pulse.active_llm || pulse.model || pulse.model_name || null;
      const modeLabel = mode.toUpperCase().includes("INTUITION")
        ? "INTUITION"
        : mode.toUpperCase().includes("HABIT")
          ? "HABIT"
          : "DEDUCTIVE";

      const fourMind = pulse.four_mind && typeof pulse.four_mind === "object"
        ? pulse.four_mind : null;
      const fieldDensity = toNumberOr(pulse.field_density, -1);
      const epistemicAlignment = clamp(toNumberOr(pulse.epistemic_alignment, -1), 0, 1);
      const spatialCoord = pulse.spatial_coordinate !== undefined
        ? pulse.spatial_coordinate : undefined;
      const driftDetected = Boolean(pulse.drift_detected);
      const egfState =
        pulse.egf_state && typeof pulse.egf_state === "object"
          ? {
              ok: pulse.egf_state.ok !== false,
              mode: String(pulse.egf_state.mode || "active"),
              error: String(pulse.egf_state.error || ""),
            }
          : null;

      setT((prev) => ({
        ...prev,
        activeLLM: activeModel || prev.activeLLM,
        confidenceWeight: confidence,
        consensusIndex: confidence,
        driftLevel: tension ? 1 : 0,
        cognitiveMode: modeLabel,
        driftDetected,
        ...(fourMind ? { fourMind: { ...prev.fourMind, ...fourMind } } : {}),
        ...(fieldDensity >= 0 ? { fieldDensity } : {}),
        ...(epistemicAlignment >= 0 ? { epistemicAlignment } : {}),
        ...(spatialCoord !== undefined ? { spatialCoord } : {}),
        ...(egfState ? { egfState } : {}),
      }));
      pushEvent(
        tension ? "WARN" : "PASS",
        `${source} pulse -> ${modeLabel} conf:${confidence.toFixed(2)} density:${fieldDensity >= 0 ? fieldDensity : "–"}`
      );
    },
    [pushEvent]
  );

  const applyHLSFSnapshot = useCallback(
    (snapshot, source = "hlsf") => {
      if (!snapshot || typeof snapshot !== "object") {
        return;
      }

      const position = Array.isArray(snapshot.position)
        ? snapshot.position.slice(0, 2).map((value) => clamp(toNumberOr(value, 0), -1, 1))
        : INITIAL_HLSF_SNAPSHOT.position;
      const fieldDensity = Math.max(0, toNumberOr(snapshot.field_density, 0));
      const hysteresisRaw = snapshot.hysteresis && typeof snapshot.hysteresis === "object"
        ? snapshot.hysteresis
        : INITIAL_HLSF_SNAPSHOT.hysteresis;
      const hysteresis = {
        trigger: Math.max(0, toNumberOr(hysteresisRaw.trigger, 800)),
        release: Math.max(0, toNumberOr(hysteresisRaw.release, 650)),
        active: Boolean(hysteresisRaw.active),
        density_ratio: clamp(toNumberOr(hysteresisRaw.density_ratio, 0), 0, 2),
      };
      const activeDims = Array.isArray(snapshot.active_dims)
        ? snapshot.active_dims.slice(0, 3).map((dim, index) => ({
          id: `${dim?.n ?? "n"}-${dim?.k ?? "k"}-${index}`,
          n: Math.max(0, Math.round(toNumberOr(dim?.n, 0))),
          k: Math.max(0, Math.round(toNumberOr(dim?.k, 0))),
          energy: clamp(toNumberOr(dim?.energy, 0), 0, 1),
          x: clamp(toNumberOr(dim?.x, 0), -1, 1),
          y: clamp(toNumberOr(dim?.y, 0), -1, 1),
        }))
        : [];
      const semanticTag = String(snapshot.semantic_tag || "idle").trim() || "idle";

      setT((prev) => ({
        ...prev,
        fieldDensity,
        spatialCoord: position,
        driftDetected: hysteresis.active,
        hlsfSnapshot: {
          position,
          active_dims: activeDims,
          hysteresis,
          field_density: fieldDensity,
          semantic_tag: semanticTag,
        },
      }));

      if (lastHlsfEdgeRef.current !== hysteresis.active) {
        pushEvent(
          hysteresis.active ? "WARN" : "INFO",
          hysteresis.active
            ? `${source} edge-cutter active @ ${fieldDensity}/${hysteresis.trigger}`
            : `${source} edge-cutter released @ ${fieldDensity}/${hysteresis.release}`
        );
        lastHlsfEdgeRef.current = hysteresis.active;
      }
    },
    [pushEvent]
  );

  const applyPresenceUpdate = useCallback(
    (message) => {
      if (!message || typeof message !== "object") {
        return;
      }

      const isSchemaV1 = String(message?.type || "").toLowerCase() === "presence_update";
      const payload = message?.data || {};
      const profile = payload.presence_profile || {};
      const isIdle = isSchemaV1 ? Boolean(message?.idle) : Boolean(profile.is_idle);
      const idleSeconds = Math.max(
        0,
        toNumberOr(isSchemaV1 ? message?.idle_seconds : profile.idle_seconds, 0)
      );
      const autonomy = clamp(
        toNumberOr(isSchemaV1 ? message?.autonomy_level : profile.autonomy_level, 0.82),
        0.45,
        1
      );
      const confidence = clamp(
        toNumberOr(
          isSchemaV1
            ? message?.confidence_state
            : payload?.cognitive?.advisory_verdict?.confidence,
          autonomy
        ),
        0,
        1
      );

      setT((prev) => ({
        ...prev,
        responseSpeed: prev.responseSpeed,
        consensusIndex: autonomy,
        confidenceWeight: confidence,
        driftLevel: 0,
        networkActivity: prev.networkActivity + 1,
        presenceRunning: true,
        presenceIdle: isIdle,
        idleSeconds: Math.round(idleSeconds),
        activeWindow: String(
          isSchemaV1 ? (message?.active_window || "unknown") : (profile.active_window || "unknown")
        ),
        activeProcess: String(
          isSchemaV1 ? (message?.active_process || "unknown") : (profile.active_process || "unknown")
        ),
        lastEvent: String(
          isSchemaV1 ? (message?.last_event || "presence") : (payload?.stimulus_type || "presence_pulse")
        ),
        cognitiveMode: String(
          isSchemaV1
            ? (message?.cognitive_mode || prev.cognitiveMode || "DEDUCTIVE")
            : (payload?.cognitive?.cognitive_mode || prev.cognitiveMode || "DEDUCTIVE")
        ),
        autonomyLevel: autonomy,
        confidenceState: confidence,
        presenceSchemaVersion: isSchemaV1
          ? String(message?.schema_version || "1.0")
          : prev.presenceSchemaVersion,
        presenceTs: toNumberOr(isSchemaV1 ? message?.ts : Date.now() / 1000, prev.presenceTs),
        cpuLoad: isSchemaV1
          ? clamp(toNumberOr(message?.cpu, prev.cpuLoad / 100) * 100, 0, 100)
          : prev.cpuLoad,
        memUsage: isSchemaV1
          ? clamp(toNumberOr(message?.memory, prev.memUsage / 100) * 100, 0, 100)
          : prev.memUsage,
      }));

      if (lastIdleRef.current === null || lastIdleRef.current !== isIdle) {
        pushEvent(
          "INFO",
          `Presence ${isIdle ? "idle" : "active"} | autonomy ${autonomy.toFixed(2)} | idle ${Math.round(idleSeconds)}s`
        );
      } else if (isSchemaV1 && String(message?.last_event || "") !== "context_update") {
        pushEvent("PASS", `Presence update ${String(message?.last_event || "presence")}`);
      }
      lastIdleRef.current = isIdle;

      if (!isSchemaV1 && payload.cognitive && typeof payload.cognitive === "object") {
        applyCognitivePulse(payload.cognitive, "presence");
      }
    },
    [applyCognitivePulse, pushEvent]
  );

  const handleBridgeMessage = useCallback(
    (message) => {
      if (!message || typeof message !== "object") {
        return;
      }

      const type = String(message.type || "").toLowerCase();
      if (!type) {
        return;
      }

      if (type === "ready") {
        setT((prev) => ({ ...prev, orbRuntimeActive: true, dockChannelConnected: true, statusReason: "" }));
        pushEvent("PASS", "Python bridge ready");
        return;
      }
      if (type === "status_response") {
        applyStatus(message.data, "status_response");
        return;
      }
      if (type === "presence_update" || type === "presence_pulse") {
        setT((prev) => ({ ...prev, orbRuntimeActive: true, dockChannelConnected: true, statusReason: "" }));
        applyPresenceUpdate(message);
        return;
      }
      if (type === "cognitive_pulse") {
        applyCognitivePulse(message.data || {}, "cognitive");
        return;
      }
      if (type === "hlsf_snapshot") {
        setT((prev) => ({ ...prev, orbRuntimeActive: true, dockChannelConnected: true, statusReason: "" }));
        applyHLSFSnapshot(message.data || {}, "hlsf");
        return;
      }
      if (type === "speech_pulse") {
        applyCognitivePulse(message.data || {}, "speech");
        pushEvent("INFO", `Speech heard: ${message.transcription || "voice input processed"}`);
        return;
      }
      if (type === "query_result" || type === "research_result" || type === "speak_result") {
        markSuccess();
        const data = message?.data && typeof message.data === "object" ? message.data : {};
        const hasAudio = Boolean(data.audio_url || data.audio_path);
        const playbackConfirmed = data.audio_played === true;
        const provider = String(data.tts_provider || "").toLowerCase() || null;
        const providerReady =
          playbackConfirmed ||
          hasAudio ||
          provider === "qwen" ||
          provider === "kokoro";
        const reportedLatency = toNumberOr(
          data.latency_ms,
          toNumberOr(data.latency, NaN)
        );
        setT((prev) => ({
          ...prev,
          llmLatency: clamp(
            Number.isFinite(reportedLatency) ? reportedLatency : prev.llmLatency,
            40,
            1200
          ),
          networkActivity: prev.networkActivity + 1,
          voiceProvider: provider || prev.voiceProvider,
          voiceProviderReady: providerReady || prev.voiceProviderReady,
          lastEvent: playbackConfirmed
            ? "voice playback confirmed"
            : hasAudio
            ? "voice payload ready"
            : data.audio_error
            ? `voice pending: ${String(data.audio_error)}`
            : prev.lastEvent,
        }));
        if (data.audio_error) {
          pushEvent("WARN", `Voice path: ${String(data.audio_error)}`);
        }
        pushEvent("PASS", `${type.replace("_", " ")} received`);
        return;
      }
      if (type === "listening_mode") {
        const enabled = Boolean(message?.data?.enabled);
        setT((prev) => ({ ...prev, listeningEnabled: enabled }));
        pushEvent("INFO", `Listening ${enabled ? "enabled" : "disabled"}`);
        return;
      }
      if (type === "listening_state") {
        const listening = Boolean(message?.data?.listening);
        setT((prev) => ({ ...prev, listeningEnabled: listening }));
        pushEvent("INFO", listening ? "Microphone listening" : "Microphone idle");
        return;
      }
      if (type === "listen_once_ack") {
        pushEvent(message?.data?.accepted ? "PASS" : "WARN", `Listen once ${message?.data?.accepted ? "accepted" : "rejected"}`);
        return;
      }
      if (type === "orb_state_result" && message?.data?.state) {
        applyStatus(message.data.state, "orb_state_result");
        return;
      }
      if (type === "bridge_spawn_error" || type === "bridge_write_failed" || type === "bridge_stream_warning" || type === "bridge_exit") {
        markError();
        pushEvent("ERR", `${type}: ${message?.data?.message || "bridge runtime issue"}`);
        return;
      }
      if (type === "stderr") {
        pushEvent("WARN", message?.data?.text || "stderr event");
        return;
      }
      if (type === "stdout") {
        pushEvent("INFO", message?.data?.text || "stdout event");
      }
    },
    [applyCognitivePulse, applyHLSFSnapshot, applyPresenceUpdate, applyStatus, markError, markSuccess, pushEvent]
  );

  useEffect(() => {
    const tick = setInterval(() => {
      const now = Date.now();
      setT((prev) => ({
        ...prev,
        epochTime: now,
        julianDate: toJulianDate(now),
        uptimeSeconds: Math.max(0, Math.floor((now - bootRef.current) / 1000)),
      }));
    }, 1000);
    return () => clearInterval(tick);
  }, []);

  useEffect(() => {
    const api = window.electronAPI;
    if (!api) {
      pushEvent("WARN", "electronAPI unavailable - live telemetry offline");
      return undefined;
    }

    let active = true;
    let resolvedOrbApiUrl = "http://127.0.0.1:21100/api/v1";
    const resolveOrbApiUrl = async () => {
      try {
        if (typeof api.getMeshRegistry === "function") {
          const mesh = await api.getMeshRegistry();
          const meshUrl = String(mesh?.services?.desktop_orb?.api_url || "").trim();
          if (meshUrl) {
            resolvedOrbApiUrl = meshUrl.replace(/\/+$/, "");
          }
        }
      } catch (_error) {}
      if (active) {
        setT((prev) => ({ ...prev, orbApiUrl: resolvedOrbApiUrl }));
      }
      return resolvedOrbApiUrl;
    };
    const checkReadiness = async () => {
      const base = await resolveOrbApiUrl();
      const url = `${base}/readiness`;
      try {
        const res = await fetch(url, { method: "GET" });
        const ok = Boolean(res?.ok);
        if (active) {
          setT((prev) => ({
            ...prev,
            orbReadinessOk: ok,
            orbRuntimeActive: ok ? true : prev.orbRuntimeActive,
          }));
        }
      } catch (_error) {
        if (active) {
          setT((prev) => ({ ...prev, orbReadinessOk: false }));
        }
      }
    };
    const refreshStatus = async (source = "poll") => {
      try {
        const status = await api.getOrbStatus();
        if (active) {
          applyStatus(status, source);
        }
        await checkReadiness();
        if (typeof api.getOrbVisibility === "function") {
          const visibility = await api.getOrbVisibility();
          if (active) {
            const visible = Boolean(visibility?.visible);
            setT((prev) => ({ ...prev, orbVisible: visible, orbDocked: !visible }));
          }
        }
      } catch (error) {
        if (active) {
          markError();
          pushEvent("ERR", `Status poll failed: ${error?.message || String(error)}`);
        }
      }
    };

    refreshStatus("initial");
    if (typeof api.getOrbVisibility === "function") {
      api.getOrbVisibility()
        .then((state) => {
          if (!active) return;
          const visible = Boolean(state?.visible);
          setT((prev) => ({ ...prev, orbVisible: visible, orbDocked: !visible }));
          pushEvent("INFO", visible ? "Orb launched" : "Orb docked");
        })
        .catch(() => {});
    }
    if (typeof api.getOrbDockedState === "function") {
      api.getOrbDockedState()
        .then((state) => {
          if (!active) return;
          const docked = Boolean(state?.docked);
          setT((prev) => ({ ...prev, orbDocked: docked, orbVisible: docked ? false : prev.orbVisible }));
          pushEvent("INFO", docked ? "Docked state confirmed." : "Dock released.");
        })
        .catch(() => {});
    }
    const statusPoll = setInterval(() => refreshStatus("poll"), 5000);

    const unsubs = [
      api.onOrbBridgeMessage((_event, message) => handleBridgeMessage(message)),
      api.onOrbStatusChange((_event, status) => applyStatus(status, "status_change")),
      api.onOrbVisibilityChanged((_event, payload) => {
        const visible = Boolean(payload?.visible);
        setT((prev) => ({ ...prev, orbVisible: visible, orbDocked: !visible }));
        pushEvent("INFO", visible ? "Orb launched" : "Orb docked");
      }),
      api.onOrbDockedState?.((_event, payload) => {
        const docked = Boolean(payload?.docked);
        setT((prev) => ({ ...prev, orbDocked: docked }));
        pushEvent("INFO", docked ? "Docked state confirmed." : "Dock released.");
      }),
      api.onHysteresis((_event, data) => {
        pushEvent("WARN", `Hysteresis ${data?.triggerThreshold} -> ${data?.releaseThreshold}`);
      }),
      api.onOrbSkinUpdated((_event, payload) => {
        if (payload?.imageUrl) {
          pushEvent("INFO", "Skin socket updated");
        }
      }),
    ];

    return () => {
      active = false;
      clearInterval(statusPoll);
      unsubs.forEach((fn) => {
        try {
          if (typeof fn === "function") fn();
        } catch (_error) {}
      });
    };
  }, [applyStatus, handleBridgeMessage, markError, pushEvent]);

  return t;
}

function Sparkline({ value, color = "#00e5ff", points = 28 }) {
  const initial = toNumberOr(value, 0);
  const history = useRef(Array(points).fill(initial));
  useEffect(() => {
    history.current = [...history.current.slice(1), toNumberOr(value, 0)];
  }, [value]);
  const h = history.current;
  const min = Math.min(...h);
  const max = Math.max(...h);
  const w = 78;
  const hh = 24;
  const pts = h
    .map((v, i) => `${(i / (points - 1)) * w},${hh - ((v - min) / (max - min || 1)) * hh}`)
    .join(" ");
  const lastY = hh - ((h[h.length - 1] - min) / (max - min || 1)) * hh;
  return (
    <svg width={w} height={hh}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.4" opacity="0.9" />
      <circle cx={w} cy={lastY} r="2.4" fill={color} />
    </svg>
  );
}

function Gauge({ value, max = 100, label, color = "#00e5ff", size = 72 }) {
  const numericValue = toNumberOr(value, 0);
  const pct = numericValue / max;
  const r = size / 2 - 6;
  const c = 2 * Math.PI * r;
  const dash = pct * c * 0.75;
  const off = c * 0.125;
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="rgba(255,255,255,0.08)"
          strokeWidth="4"
          strokeDasharray={`${c * 0.75} ${c}`}
          strokeDashoffset={-off}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`}
          strokeDashoffset={-off}
          style={{ transition: "stroke-dasharray .7s ease", filter: `drop-shadow(0 0 5px ${color})` }}
        />
        <text
          x={size / 2}
          y={size / 2}
          textAnchor="middle"
          dominantBaseline="middle"
          fill={color}
          fontSize="11"
          fontFamily="monospace"
          fontWeight="bold"
        >
          {numericValue < 10 ? numericValue.toFixed(2) : Math.round(numericValue)}
        </text>
      </svg>
      <div style={{ position: "absolute", bottom: 1, width: "100%", textAlign: "center", fontSize: 8, color: "rgba(255,255,255,.45)", letterSpacing: 1, fontFamily: "monospace" }}>
        {label}
      </div>
    </div>
  );
}

function Pill({ label, value, ok = true }) {
  return (
    <div
      style={{
        display: "flex",
        gap: 6,
        alignItems: "center",
        fontFamily: "monospace",
        padding: "6px 9px",
        borderRadius: 4,
        border: `1px solid ${ok ? "rgba(139,223,240,.24)" : "rgba(255,125,125,.35)"}`,
        background: "rgba(255,255,255,.045)",
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: ok ? "#5af2a5" : "#ffcc66",
          boxShadow: ok ? "0 0 6px #5af2a5" : "0 0 6px #ffcc66",
        }}
      />
      <span style={{ fontSize: 12, color: "rgba(211,236,243,.66)", letterSpacing: 0.2 }}>{label}</span>
      <span style={{ marginLeft: "auto", color: ok ? "#edfaff" : "#ffcc66", fontSize: 13, fontWeight: "bold", textAlign: "right" }}>{value}</span>
    </div>
  );
}

function Panel({ title, accent = "#00e5ff", children, badge }) {
  return (
    <div
      style={{
        background: "linear-gradient(145deg, rgba(9,24,35,.9), rgba(3,10,17,.96))",
        borderRadius: 8,
        border: "1px solid rgba(174,220,232,.18)",
        borderTop: `2px solid ${accent}55`,
        padding: "12px 14px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", marginBottom: 10, gap: 7 }}>
        <div style={{ width: 4, height: 4, borderRadius: "50%", background: accent, boxShadow: `0 0 6px ${accent}` }} />
        <span style={{ fontSize: 15, letterSpacing: 0.8, textTransform: "uppercase", color: "#edfaff", fontFamily: "monospace", fontWeight: 800 }}>{title}</span>
        {badge ? (
          <span style={{ marginLeft: "auto", fontSize: 11, color: "#5af2a5", border: "1px solid rgba(90,242,165,.34)", background: "rgba(90,242,165,.12)", borderRadius: 3, padding: "2px 7px", fontFamily: "monospace", fontWeight: 700 }}>
            {badge}
          </span>
        ) : null}
      </div>
      {children}
    </div>
  );
}

function OrbDiagram({ telemetry, accent = "#00e5ff" }) {
  const ref = useRef(null);
  const telemetryRef = useRef(telemetry);

  useEffect(() => {
    telemetryRef.current = telemetry;
  }, [telemetry]);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h / 2;
    let frame = 0;
    let raf = 0;
    const draw = () => {
      const live = telemetryRef.current || {};
      const confidence = clamp(toNumberOr(live.confidenceState, 0.3), 0, 1);
      const cpuRatio = clamp(toNumberOr(live.cpuLoad, 0) / 100, 0, 1);
      const isIdle = Boolean(live.presenceIdle);
      const speed = isIdle ? 0.0035 : 0.0075 + confidence * 0.01;
      frame += speed;

      ctx.clearRect(0, 0, w, h);
      const outerR = 118 + confidence * 14;
      ctx.beginPath();
      ctx.arc(cx, cy, outerR, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(0,229,255,${0.22 + cpuRatio * 0.5})`;
      ctx.lineWidth = 2;
      ctx.stroke();
      [0.56, 0.72, 0.88].forEach((rf, idx) => {
        const r = outerR * rf;
        const phase = frame * (0.35 + idx * 0.2 + confidence * 0.15) * (idx % 2 ? -1 : 1);
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(phase);
        ctx.beginPath();
        ctx.ellipse(0, 0, r, r * 0.34, 0, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(0,${145 + idx * 30},${220 + idx * 10},${0.22 + idx * 0.05})`;
        ctx.setLineDash([4, 8]);
        ctx.stroke();
        ctx.setLineDash([]);
        const nx = Math.cos(phase * 2) * r;
        const ny = Math.sin(phase * 2) * r * 0.34;
        ctx.beginPath();
        ctx.arc(nx, ny, 3, 0, Math.PI * 2);
        ctx.fillStyle = [accent, "#7c4dff", "#00e676"][idx];
        ctx.shadowColor = ctx.fillStyle;
        ctx.shadowBlur = 8;
        ctx.fill();
        ctx.shadowBlur = 0;
        ctx.restore();
      });
      ctx.fillStyle = accent;
      ctx.font = "bold 12px monospace";
      ctx.textAlign = "center";
      ctx.fillText(isIdle ? "IDLE" : "LIVE", cx, cy + 4);
      ctx.fillStyle = "rgba(0,229,255,.75)";
      ctx.font = "7px monospace";
      ctx.fillText(String(live.cognitiveMode || "UNKNOWN").slice(0, 14), cx, cy + 16);
      ctx.fillStyle = "rgba(255,255,255,.52)";
      ctx.fillText(`CPU ${Math.round(toNumberOr(live.cpuLoad, 0))}%`, cx, cy + 27);
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [accent]);
  return <canvas ref={ref} width={300} height={300} style={{ display: "block" }} />;
}

function DockedOrbMirror({ telemetry, accent = "#00e5ff" }) {
  const confidence = clamp(toNumberOr(telemetry?.confidenceState, 0.6), 0, 1);
  const cpu = clamp(toNumberOr(telemetry?.cpuLoad, 0), 0, 100);
  const mode = String(telemetry?.cognitiveMode || "UNKNOWN");
  const docked = Boolean(telemetry?.orbDocked);
  const orbActive = Boolean(telemetry?.orbRuntimeActive);
  const ringColor = docked ? accent : "rgba(255,255,255,.45)";
  return (
    <div
      style={{
        marginTop: 8,
        border: `1px solid ${accent}44`,
        borderRadius: 8,
        padding: "10px 12px",
        background: "linear-gradient(160deg, rgba(0,20,40,.7), rgba(0,8,24,.85))",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div
          style={{
            width: 44,
            height: 44,
            borderRadius: "50%",
            background: `radial-gradient(circle at 35% 30%, #ffffffcc 0%, ${ringColor} 35%, #05101f 100%)`,
            border: `1px solid ${ringColor}`,
            boxShadow: `0 0 ${8 + confidence * 12}px ${ringColor}`,
          }}
        />
        <div style={{ display: "grid", gap: 2, flex: 1 }}>
          <span style={{ fontSize: 10, color: accent }}>DOCKED ORB MIRROR</span>
          <span style={{ fontSize: 9, color: "rgba(255,255,255,.7)" }}>
            {docked ? "DOCKED" : "NOT DOCKED"} | Runtime {orbActive ? "ACTIVE" : "OFFLINE"} | Mode {mode} | Confidence {(confidence * 100).toFixed(0)}% | CPU {cpu.toFixed(0)}%
          </span>
        </div>
      </div>
    </div>
  );
}

function DockedOrbStage({ telemetry, accent = "#00e5ff", isDocked = false }) {
  const mode = String(telemetry?.cognitiveMode || "DEDUCTIVE").toUpperCase();
  const confidence = clamp(toNumberOr(telemetry?.confidenceState, 0.6), 0, 1);
  const liveSize = Math.round(140 + confidence * 48);
  const modeColor = mode.includes("INTUITION")
    ? "#f5c96a"
    : mode.includes("HABIT")
      ? "#63e6a6"
      : "#67c6ff";
  const pulseColor = isDocked ? modeColor : "rgba(255,255,255,.45)";
  const orbNodeStyle = {
    width: liveSize,
    height: liveSize,
    borderRadius: "50%",
    background: `radial-gradient(circle at 35% 30%, #ffffffc2 0%, ${pulseColor} 35%, #021022 100%)`,
    border: `1px solid ${pulseColor}`,
    boxShadow: `0 0 ${20 + confidence * 24}px ${pulseColor}`,
    position: "relative",
    animation: "orbDockBreathNode 3200ms ease-in-out infinite",
    flexShrink: 0,
  };

  return (
    <div style={{
      border: "1px solid rgba(174,220,232,.2)",
      borderRadius: 8,
      padding: 10,
      minHeight: 460,
      background: "rgba(2,10,18,.55)",
      display: "grid",
      gridTemplateRows: "auto 1fr",
      gap: 10,
    }}>
      <style>{`
        @keyframes orbDockBreathNode {
          0%, 100% { transform: scale(0.985); opacity: 0.88; }
          50% { transform: scale(1.03); opacity: 1; }
        }
      `}</style>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
        <Pill label="DOCK STATE" value={isDocked ? "DOCKED" : "LAUNCHED"} ok={isDocked} />
        <Pill label="RUNTIME" value={telemetry?.orbRuntimeActive ? "ACTIVE" : "INACTIVE"} ok={telemetry?.orbRuntimeActive} />
        <Pill label="MODE" value={mode} ok={true} />
        <Pill label="LLM" value={telemetry?.llmConnected ? "CONNECTED" : "OFFLINE"} ok={telemetry?.llmConnected} />
      </div>
      <div style={{ display: "grid", placeItems: "center", overflow: "hidden" }}>
        <div style={orbNodeStyle}>
          <div style={{
            position: "absolute", inset: -14, borderRadius: "50%",
            border: `1px solid ${pulseColor}`, borderRightColor: "transparent",
            boxShadow: `0 0 26px ${pulseColor}`, transform: "rotate(24deg)",
          }} />
          <div style={{
            position: "absolute", inset: -28, borderRadius: "50%",
            border: "1px solid rgba(103,198,255,.32)", borderLeftColor: "transparent",
            transform: "rotate(-36deg)",
          }} />
        </div>
      </div>
    </div>
  );
}

function HLSFMirrorPanel({ telemetry, accent = "#00e5ff" }) {
  const hlsfTag = String(telemetry?.hlsfSnapshot?.semantic_tag || "idle").toUpperCase();
  const hlsfDensity = Math.round(toNumberOr(telemetry?.hlsfSnapshot?.field_density, toNumberOr(telemetry?.fieldDensity, 0)));
  const hlsfEdgeActive = Boolean(telemetry?.hlsfSnapshot?.hysteresis?.active);
  const trigger = toNumberOr(telemetry?.hlsfSnapshot?.hysteresis?.trigger, 0);
  const release = toNumberOr(telemetry?.hlsfSnapshot?.hysteresis?.release, 0);
  return (
    <div style={{ border: "1px solid rgba(174,220,232,.2)", borderRadius: 8, padding: 10, background: "rgba(2,10,18,.55)", minHeight: 460, display: "grid", gridTemplateRows: "auto 1fr", gap: 10 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
        <Pill label="HLSF DENSITY" value={hlsfDensity} ok={hlsfDensity > 0} />
        <Pill label="HLSF EDGE" value={hlsfEdgeActive ? "ACTIVE" : "CLEAR"} ok={!hlsfEdgeActive} />
        <Pill label="HLSF TAG" value={hlsfTag} ok={hlsfTag !== "IDLE"} />
        <Pill label="REL/TRIG" value={`${release}/${trigger}`} ok={trigger > 0 || release > 0} />
      </div>
      <div style={{ display: "grid", placeItems: "center", overflow: "hidden" }}>
        <HLSFFieldView telemetry={telemetry} accent={accent} />
      </div>
    </div>
  );
}

function EGFMirrorPanel({ telemetry }) {
  const egfMode = String(telemetry?.egfState?.mode || "unknown").toUpperCase();
  const egfOk = telemetry?.egfState?.ok !== false;
  const egfError = String(telemetry?.egfState?.error || "");
  return (
    <div style={{ border: "1px solid rgba(174,220,232,.2)", borderRadius: 8, padding: 10, background: "rgba(2,10,18,.55)", minHeight: 460, display: "grid", gridTemplateRows: "auto 1fr", gap: 10 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 6 }}>
        <Pill label="EGF STATUS" value={egfMode} ok={egfOk} />
        <Pill label="EGF AVAIL" value={egfOk ? "AVAILABLE" : "UNAVAILABLE"} ok={egfOk} />
        <Pill label="EGF ERROR" value={egfError || "NONE"} ok={!egfError} />
      </div>
      <div style={{ display: "grid", placeItems: "center", overflow: "hidden" }}>
        <div style={{
          width: 250,
          height: 250,
          borderRadius: "50%",
          border: `1px solid ${egfOk ? "rgba(99,239,158,.72)" : "rgba(255,191,71,.65)"}`,
          boxShadow: `0 0 26px ${egfOk ? "rgba(99,239,158,.45)" : "rgba(255,191,71,.35)"}`,
          background: egfOk
            ? "radial-gradient(circle at 34% 28%, rgba(255,255,255,.88), rgba(99,239,158,.44) 38%, rgba(2,20,16,.95) 100%)"
            : "radial-gradient(circle at 34% 28%, rgba(255,255,255,.6), rgba(255,191,71,.28) 38%, rgba(20,10,2,.95) 100%)",
          display: "grid",
          placeItems: "center",
          color: egfOk ? "#63ef9e" : "#ffbf47",
          fontSize: 12,
          fontFamily: "monospace",
          letterSpacing: 0.8,
        }}>
          {egfOk ? "EGF ACTIVE" : "EGF UNAVAILABLE"}
        </div>
      </div>
    </div>
  );
}

function HLSFFieldView({ telemetry, accent = "#00e5ff" }) {
  const ref = useRef(null);
  const telRef = useRef(telemetry);
  useEffect(() => { telRef.current = telemetry; }, [telemetry]);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;
    const cx = w / 2;
    const cy = h / 2;
    let frame = 0;
    let raf = 0;

    const draw = () => {
      const live = telRef.current || {};
      const snapshot = live.hlsfSnapshot || INITIAL_HLSF_SNAPSHOT;
      const density = Math.min(toNumberOr(snapshot.field_density, live.fieldDensity), 2000);
      const hysteresis = snapshot.hysteresis || INITIAL_HLSF_SNAPSHOT.hysteresis;
      const drift = Boolean(hysteresis.active);
      const densityRatio = clamp(toNumberOr(hysteresis.density_ratio, 0), 0, 1.5);
      const semanticTag = String(snapshot.semantic_tag || live.cognitiveMode || "idle").toUpperCase();
      const activeDims = Array.isArray(snapshot.active_dims) ? snapshot.active_dims : [];
      const position = Array.isArray(snapshot.position) ? snapshot.position : live.spatialCoord;
      frame += 0.012;

      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = "rgba(2,7,18,0.22)";
      ctx.fillRect(0, 0, w, h);

      // Field frame
      ctx.beginPath();
      ctx.arc(cx, cy, 108, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(255,255,255,0.06)";
      ctx.lineWidth = 1;
      ctx.stroke();

      // Projection guides
      ctx.beginPath();
      ctx.moveTo(cx - 96, cy);
      ctx.lineTo(cx + 96, cy);
      ctx.moveTo(cx, cy - 96);
      ctx.lineTo(cx, cy + 96);
      ctx.strokeStyle = "rgba(255,255,255,0.08)";
      ctx.lineWidth = 1;
      ctx.stroke();

      // Hysteresis boundary ring
      ctx.beginPath();
      ctx.setLineDash([5, 5]);
      ctx.arc(cx, cy, 84, 0, Math.PI * 2);
      ctx.strokeStyle = drift ? "rgba(255,80,80,0.75)" : `rgba(0,229,255,${0.18 + densityRatio * 0.18})`;
      ctx.lineWidth = 1.5;
      ctx.stroke();
      ctx.setLineDash([]);

      // Density envelope
      ctx.beginPath();
      ctx.arc(cx, cy, 92 + Math.sin(frame * 2) * 2.5, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(0,229,255,${0.06 + Math.min(density / 800, 1) * 0.2})`;
      ctx.lineWidth = 2 + densityRatio * 2;
      ctx.stroke();

      activeDims.forEach((dim, idx) => {
        const color = ["#00e5ff", "#00e676", "#ffd740"][idx] || accent;
        const px = cx + clamp(toNumberOr(dim.x, 0), -1, 1) * 72;
        const py = cy + clamp(toNumberOr(dim.y, 0), -1, 1) * 72;
        const energy = clamp(toNumberOr(dim.energy, 0), 0, 1);
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(px, py);
        ctx.strokeStyle = color;
        ctx.globalAlpha = 0.3 + energy * 0.55;
        ctx.lineWidth = 1.5 + energy * 2;
        ctx.stroke();
        ctx.globalAlpha = 1;

        ctx.beginPath();
        ctx.arc(px, py, 3 + energy * 4, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.shadowColor = color;
        ctx.shadowBlur = 6 + energy * 10;
        ctx.fill();
        ctx.shadowBlur = 0;

        ctx.fillStyle = color;
        ctx.font = "bold 9px monospace";
        ctx.textAlign = px >= cx ? "left" : "right";
        ctx.textBaseline = "middle";
        ctx.fillText(`N${dim.n} K${dim.k}`, px + (px >= cx ? 8 : -8), py - 5);
        ctx.fillStyle = "rgba(255,255,255,.55)";
        ctx.font = "8px monospace";
        ctx.fillText(`${Math.round(energy * 100)}%`, px + (px >= cx ? 8 : -8), py + 5);
      });

      // Center core
      const coreR = 12 + densityRatio * 4;
      const grad = ctx.createRadialGradient(cx - 3, cy - 3, 1, cx, cy, coreR);
      grad.addColorStop(0, "#ffffff");
      grad.addColorStop(0.4, `${accent}ee`);
      grad.addColorStop(1, `${accent}22`);
      ctx.beginPath();
      ctx.arc(cx, cy, coreR, 0, Math.PI * 2);
      ctx.fillStyle = grad;
      ctx.shadowColor = drift ? "#ff5050" : accent;
      ctx.shadowBlur = 12 + densityRatio * 12;
      ctx.fill();
      ctx.shadowBlur = 0;

      // Semantic tag
      ctx.fillStyle = accent;
      ctx.font = "bold 10px monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(semanticTag.slice(0, 12), cx, cy);

      // HLSF position marker
      if (position !== null && position !== undefined) {
        const coords = Array.isArray(position) ? position : [position];
        const sx = clamp(toNumberOr(coords[0], 0), -1, 1);
        const sy = clamp(toNumberOr(coords[1], 0), -1, 1);
        const dotX = cx + sx * 84;
        const dotY = cy + sy * 84;
        ctx.beginPath();
        ctx.arc(dotX, dotY, 5, 0, Math.PI * 2);
        ctx.fillStyle = "#ffd740";
        ctx.shadowColor = "#ffd740";
        ctx.shadowBlur = 10;
        ctx.fill();
        ctx.shadowBlur = 0;
      }

      if (!activeDims.length) {
        ctx.fillStyle = "rgba(255,255,255,.3)";
        ctx.font = "9px monospace";
        ctx.textAlign = "center";
        ctx.fillText("NO ACTIVE DIMENSIONS", cx, cy + 52);
      }

      // Readout
      ctx.fillStyle = "rgba(255,255,255,.35)";
      ctx.font = "8px monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "top";
      ctx.fillText(`DENSITY ${density}`, 6, 6);
      ctx.fillText(`TRIGGER ${Math.round(toNumberOr(hysteresis.trigger, 0))}`, 6, 15);
      ctx.fillText(`RELEASE ${Math.round(toNumberOr(hysteresis.release, 0))}`, 6, 24);
      if (drift) {
        ctx.fillStyle = "#ff5050";
        ctx.fillText("EDGE CUTTER ACTIVE", 6, 33);
      }

      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [accent]);

  return <canvas ref={ref} width={300} height={300} style={{ display: "block" }} />;
}

function OrbRegistryPanel({ accent = "#00e5ff", activeInstanceId = null }) {
  const [registry, setRegistry] = useState({ orbs: [], loaded: false, error: null });
  const [activeOrb, setActiveOrb] = useState(null);

  useEffect(() => {
    const api = window.electronAPI;
    if (!api || typeof api.getMeshRegistry !== "function") {
      setRegistry({ orbs: [], loaded: true, error: "getMeshRegistry not available" });
      return;
    }
    let mounted = true;
    const load = () => {
      api.getMeshRegistry().then((result) => {
        if (!mounted) return;
        setRegistry({ orbs: result.orbs || [], loaded: true, error: result.error || null });
      }).catch((e) => {
        if (!mounted) return;
        setRegistry({ orbs: [], loaded: true, error: String(e.message || e) });
      });
    };
    load();
    const interval = setInterval(load, 15000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (activeInstanceId && !activeOrb) {
      setActiveOrb(activeInstanceId);
    }
  }, [activeInstanceId, activeOrb]);

  if (!registry.loaded) {
    return (
      <div style={{ padding: "8px 0", fontSize: 9, color: "rgba(255,255,255,.4)", fontFamily: "monospace" }}>
        Loading Orb registry…
      </div>
    );
  }

  if (!registry.orbs.length) {
    return (
      <div style={{ padding: "8px 0", fontSize: 9, color: "rgba(255,255,255,.35)", fontFamily: "monospace" }}>
        {registry.error ? `Registry error: ${registry.error}` : "No Orbs registered in mesh."}
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      {registry.orbs.map((orb) => {
        const isActive = (activeOrb || activeInstanceId) === orb.instance_id;
        const color = orb.online ? "#00e676" : "rgba(255,255,255,.3)";
        return (
          <div key={orb.instance_id} style={{
            display: "flex", alignItems: "center", gap: 8, padding: "6px 10px",
            borderRadius: 5, cursor: "pointer",
            border: `1px solid ${isActive ? accent + "88" : "rgba(255,255,255,.1)"}`,
            background: isActive ? `${accent}11` : "rgba(255,255,255,.03)",
          }} onClick={() => setActiveOrb(orb.instance_id)}>
            <div style={{ width: 7, height: 7, borderRadius: "50%", background: color,
              boxShadow: orb.online ? `0 0 6px ${color}` : "none", flexShrink: 0 }} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 10, color: isActive ? accent : "#e0f7fa", fontFamily: "monospace", fontWeight: "bold" }}>
                {String(orb.instance_id).toUpperCase()}
              </div>
              <div style={{ fontSize: 8, color: "rgba(255,255,255,.4)", fontFamily: "monospace" }}>
                {String(orb.role || "–")}
              </div>
            </div>
            <span style={{ fontSize: 8, color, fontFamily: "monospace", letterSpacing: 0.5 }}>
              {orb.online ? "ONLINE" : "OFFLINE"}
            </span>
            {isActive && (
              <span style={{ fontSize: 7, color: accent, fontFamily: "monospace", letterSpacing: 1 }}>● ACTIVE</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

const SKINS = [
  { id: "deep-space", label: "Deep Space", accent: "#00e5ff" },
  { id: "solar-flare", label: "Solar Flare", accent: "#ff9d00" },
  { id: "bio-pulse", label: "Bio Pulse", accent: "#00e676" },
  { id: "quantum", label: "Quantum", accent: "#e040fb" },
];

const ORB_SKIN_STUDIO_ROOT_URL = "file:///R:/Orb_Skin_Studio";
const ORB_SKIN_STUDIO_TABS = [
  { id: "studio", label: "Studio", file: "orb_skin_gen.html" },
  { id: "gallery", label: "Gallery", file: "gallery.html" },
  { id: "cart", label: "Cart", file: "cart.html" },
  { id: "checkout", label: "Checkout", file: "checkout.html" },
  { id: "upload", label: "Upload", file: "upload.html" },
  { id: "account", label: "Account", file: "account.html" },
  { id: "admin", label: "Admin", file: "admin.html" },
  { id: "pricing", label: "Pricing", file: "pricing.html" },
  { id: "login", label: "Login", file: "login.html" },
  { id: "contact", label: "Contact", file: "contact.html" },
];

function toSkinStudioUrl(file) {
  return `${ORB_SKIN_STUDIO_ROOT_URL}/${encodeURIComponent(file)}`;
}

const EVENT_COLOR = { INFO: "#00b4d8", PASS: "#00e676", WARN: "#ffd740", ERR: "#ff5050" };

function ChatPanel({ accent = "#00e5ff" }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [listening, setListening] = useState(false);
  const bottomRef = useRef(null);
  const lastMessageKeyRef = useRef("");
  const lastAudioPathRef = useRef("");

  const playAudioNow = useCallback((audioPath) => {
    const path = String(audioPath || "").trim();
    if (!path) return;
    if (lastAudioPathRef.current === path) return;
    lastAudioPathRef.current = path;
    try {
      const audio = new Audio(path);
      audio.play().catch(() => {});
    } catch (_error) {}
  }, []);

  useEffect(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  useEffect(() => {
    const api = window.electronAPI;
    if (!api || typeof api.onChatMessage !== "function") return undefined;
    const unsub = api.onChatMessage((_event, msg) => {
      const key = `${msg.role || ""}|${msg.text || ""}|${msg.audioPath || ""}|${msg.audioUrl || ""}`;
      if (lastMessageKeyRef.current === key) return;
      lastMessageKeyRef.current = key;
      window.setTimeout(() => {
        if (lastMessageKeyRef.current === key) lastMessageKeyRef.current = "";
      }, 1200);
      setMessages((prev) => [...prev, msg]);
      const orbAudio = msg.audioUrl || msg.audioPath || null;
      if (msg.role === "orb" && orbAudio) {
        playAudioNow(orbAudio);
      }
    });
    return () => {
      if (typeof unsub === "function") unsub();
    };
  }, [playAudioNow]);

  useEffect(() => {
    const api = window.electronAPI;
    if (!api || typeof api.onOrbBridgeMessage !== "function") return undefined;
    const unsub = api.onOrbBridgeMessage((_event, message) => {
      if (!message || message.type !== "speak_result") return;
      const audioSource = message?.data?.audio_url || message?.data?.audio_path || null;
      if (audioSource) {
        playAudioNow(audioSource);
      }
    });
    return () => {
      if (typeof unsub === "function") unsub();
    };
  }, [playAudioNow]);

  useEffect(() => {
    const api = window.electronAPI;
    if (!api || typeof api.onSpeechPulse !== "function") return undefined;
    const unsub = api.onSpeechPulse((_event, payload) => {
      const transcript = String(
        payload?.data?.transcription ||
        payload?.transcription ||
        payload?.data?.transcript ||
        payload?.transcript ||
        ""
      ).trim();
      if (!transcript) return;
      setInput(transcript);
    });
    return () => {
      if (typeof unsub === "function") unsub();
    };
  }, []);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setSending(true);
    try {
      await window.electronAPI?.orbChat?.(text);
    } finally {
      setSending(false);
    }
  }, [input, sending]);

  const handleKey = useCallback(
    (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    },
    [send]
  );

  const triggerListen = useCallback(async () => {
    if (listening || sending) return;
    setListening(true);
    try {
      await window.electronAPI?.listenOnce?.();
    } finally {
      setListening(false);
    }
  }, [listening, sending]);

  return (
    <Panel title="Talk to Orb" accent={accent} badge="LIVE CHANNEL">
      <div
        style={{
          height: 178,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          gap: 8,
          padding: "4px 0",
          marginBottom: 10,
        }}
      >
        {messages.length === 0 ? (
          <div style={{ color: "rgba(211,236,243,.56)", fontSize: 13, padding: "8px 0", fontFamily: "monospace", lineHeight: 1.45 }}>
            No messages yet. Type below to talk to Orb.
          </div>
        ) : (
          messages.map((msg, i) => (
            <div
              key={i}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: msg.role === "user" ? "flex-end" : "flex-start",
              }}
            >
              <div
                style={{
                  maxWidth: "80%",
                  padding: "8px 11px",
                  borderRadius: 8,
                  fontSize: 14,
                  lineHeight: 1.55,
                  background: msg.role === "user" ? "rgba(139,223,240,.12)" : "rgba(255,255,255,.07)",
                  border: `1px solid ${msg.role === "user" ? "rgba(139,223,240,.34)" : "rgba(255,255,255,.12)"}`,
                  color: msg.role === "user" ? "#edfaff" : "#edfaff",
                  fontFamily: "monospace",
                  wordBreak: "break-word",
                  whiteSpace: "pre-wrap",
                }}
              >
                {msg.text}
              </div>
              <span style={{ fontSize: 10, color: "rgba(211,236,243,.42)", marginTop: 3, fontFamily: "monospace" }}>
                {msg.role === "orb" ? ((msg.audioUrl || msg.audioPath) ? "ORB VOICE" : "ORB") : "YOU"} · {msg.time}
              </span>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
      <div style={{ display: "flex", gap: 6 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Message Orb..."
          disabled={sending}
          style={{
            flex: 1,
            background: "rgba(255,255,255,.045)",
            border: "1px solid rgba(174,220,232,.28)",
            borderRadius: 4,
            color: "#edfaff",
            padding: "9px 11px",
            fontSize: 14,
            fontFamily: "monospace",
            outline: "none",
          }}
        />
        <button
          onClick={send}
          disabled={!input.trim() || sending}
          style={{
            padding: "9px 16px",
            borderRadius: 4,
            border: "1px solid rgba(139,223,240,.38)",
            background: "rgba(139,223,240,.12)",
            color: "#edfaff",
            fontSize: 13,
            fontWeight: 700,
            fontFamily: "monospace",
            cursor: !input.trim() || sending ? "not-allowed" : "pointer",
            opacity: !input.trim() || sending ? 0.45 : 1,
            letterSpacing: 0.5,
          }}
        >
          {sending ? "..." : "Send"}
        </button>
        <button
          onClick={triggerListen}
          disabled={listening || sending}
          title={listening ? "Listening…" : "Speak to Orb"}
          style={{
            padding: "9px 11px",
            borderRadius: 4,
            border: `1px solid ${listening ? "#ff5f57" : accent}66`,
            background: listening ? "rgba(255,95,87,0.18)" : `${accent}11`,
            color: listening ? "#ff5f57" : accent,
            fontSize: 13,
            cursor: listening || sending ? "not-allowed" : "pointer",
            opacity: listening || sending ? 0.7 : 1,
            transition: "all 0.2s",
          }}
        >
          {listening ? "⏺" : "🎤"}
        </button>
      </div>
    </Panel>
  );
}

function OrbDockStation() {
  const tier = parseInt(new URLSearchParams(window.location.search).get("tier") || "2", 10);
  const tel = useTelemetry();
  const [activeTab, setActiveTab] = useState("orb");
  const [stationConfig, setStationConfig] = useState(() => {
    const persisted = safeReadJson(STATION_CONFIG_KEY, {});
    return {
      skinId: persisted.skinId || "deep-space",
      llmRoute: persisted.llmRoute || "local",
      apiBase: persisted.apiBase || "",
      apiModel: persisted.apiModel || "",
      apiKey: persisted.apiKey || "",
      localEndpoint: persisted.localEndpoint || "http://127.0.0.1:11434",
      localModel: persisted.localModel || "llama3.2:1b",
      governanceWrapper: false,
      retainVoice: persisted.retainVoice !== false,
      startOnBoot: persisted.startOnBoot !== false,
      showStartupSplash: persisted.showStartupSplash !== false,
      startDocked: persisted.startDocked === true,
      startupVoiceGreeting: persisted.startupVoiceGreeting === true,
      desktopMcpActionsEnabled: persisted.desktopMcpActionsEnabled === true,
    };
  });
  const [skinId, setSkinId] = useState(stationConfig.skinId);
  const [savingLlmConfig, setSavingLlmConfig] = useState(false);
  const [discoveringLlm, setDiscoveringLlm] = useState(false);
  const [ollamaDiscovery, setOllamaDiscovery] = useState(null);
  const [studioConnected, setStudioConnected] = useState(false);
  const [manualQuery, setManualQuery] = useState("");
  const [manualContext, setManualContext] = useState("");
  const [manualMorbCount, setManualMorbCount] = useState(5);
  const [manualDeployZone, setManualDeployZone] = useState("around");
  const [bootPhase, setBootPhase] = useState("login");
  const [loginUser, setLoginUser] = useState("");
  const [loginPass, setLoginPass] = useState("");
  const [loginError, setLoginError] = useState("");
  const [privacyAccepted, setPrivacyAccepted] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [latestOrbOutput, setLatestOrbOutput] = useState("");
  const [orbConversation, setOrbConversation] = useState([]);
  const [deployingSwarm, setDeployingSwarm] = useState(false);
  const startupConnectRef = useRef(false);
  const listeningBootstrapRef = useRef({ lastTryAt: 0 });
  const [swarmStatusFeed, setSwarmStatusFeed] = useState(() => [
    { id: 0, text: "Prime ORB idle.", level: "INFO" },
  ]);
  const skin = useMemo(() => SKINS.find((s) => s.id === skinId) || SKINS[0], [skinId]);
  const accent = skin.accent;
  const isDocked = Boolean(tel.orbDocked);
  const isDockReady = bootPhase === "ready";
  const governanceEnabled = stationConfig.governanceWrapper;
  const desktopMcpActionsEnabled = stationConfig.desktopMcpActionsEnabled === true;
  const llm =
    (tel.activeLLM && String(tel.activeLLM).trim() && String(tel.activeLLM).toLowerCase() !== "unknown")
      ? String(tel.activeLLM)
      :
    stationConfig.llmRoute === "api"
      ? (stationConfig.apiModel || "API (unset)")
      : stationConfig.llmRoute === "local"
      ? (stationConfig.localModel || "Local (unset)")
      : "CALI";

  useEffect(() => {
    const api = window.electronAPI;
    if (!api) return undefined;
    const unsubs = [];
    if (typeof api.onChatMessage === "function") {
      unsubs.push(
        api.onChatMessage((_event, msg) => {
          if (msg?.role === "orb" && String(msg?.text || "").trim()) {
            const text = String(msg.text).trim();
            setLatestOrbOutput(text);
            setOrbConversation((prev) => {
              const next = [...prev, { text, time: msg?.time || new Date().toTimeString().slice(0, 8) }];
              return next.slice(-24);
            });
          }
        })
      );
    }
    if (typeof api.onOrbBridgeMessage === "function") {
      unsubs.push(
        api.onOrbBridgeMessage((_event, message) => {
          const text = String(
            message?.data?.response_text ||
            message?.data?.text ||
            message?.response_text ||
            ""
          ).trim();
          if (text) {
            setLatestOrbOutput(text);
            setOrbConversation((prev) => {
              const next = [...prev, { text, time: new Date().toTimeString().slice(0, 8) }];
              return next.slice(-24);
            });
          }
        })
      );
    }
    return () => unsubs.forEach((fn) => typeof fn === "function" && fn());
  }, []);
  const discoveredLocalModels = useMemo(() => {
    const models = Array.isArray(ollamaDiscovery?.models) ? ollamaDiscovery.models : [];
    return models
      .map((model) => String(model?.name || model?.model || "").trim())
      .filter(Boolean);
  }, [ollamaDiscovery]);
  const uptime = `${Math.floor(tel.uptimeSeconds / 86400)}d ${Math.floor((tel.uptimeSeconds % 86400) / 3600)}h ${Math.floor((tel.uptimeSeconds % 3600) / 60)}m`;
  const cognitiveModeLabel = String(tel.cognitiveMode || "DEDUCTIVE").toUpperCase();
  const TABS = [
    { id: "orb", label: "ORB" },
    ...(tier >= 2 ? [{ id: "runtime", label: "RUNTIME" }, { id: "skills", label: "SKILLS" }, { id: "settings", label: "SETTINGS" }] : []),
  ];

  useEffect(() => {
    const api = window.electronAPI;
    if (!api || typeof api.setOrbVisibility !== "function") return;
    if (bootPhase === "ready") return;
    api.setOrbVisibility(false).catch(() => {});
  }, [bootPhase]);

  useEffect(() => {
    setStationConfig((prev) => {
      if (prev.skinId === skinId) return prev;
      const next = { ...prev, skinId };
      window.localStorage.setItem(STATION_CONFIG_KEY, JSON.stringify(next));
      return next;
    });
  }, [skinId]);

  useEffect(() => {
    const api = window.electronAPI;
    if (!api) return;
    const unsubs = [];
    if (typeof api.onStudioConnected === "function") unsubs.push(api.onStudioConnected(() => setStudioConnected(true)));
    if (typeof api.onStudioClosed === "function") unsubs.push(api.onStudioClosed(() => setStudioConnected(false)));
    return () => unsubs.forEach((fn) => typeof fn === "function" && fn());
  }, []);

  const persistConfig = useCallback((next) => {
    setStationConfig(next);
    window.localStorage.setItem(STATION_CONFIG_KEY, JSON.stringify(next));
  }, []);

  const pushSwarmStatus = useCallback((text, level = "INFO") => {
    setSwarmStatusFeed((prev) => {
      const next = [
        { id: Date.now() + Math.floor(Math.random() * 1000), text, level },
        ...prev,
      ];
      return next.slice(0, 8);
    });
  }, []);

  useEffect(() => {
    const api = window.electronAPI;
    if (!api || typeof api.setDesktopMcpActionsEnabled !== "function") return;
    api.setDesktopMcpActionsEnabled(desktopMcpActionsEnabled).catch(() => {});
  }, [desktopMcpActionsEnabled]);

  const discoverLocalLlm = useCallback(async ({ autoApply = false } = {}) => {
    const api = window.electronAPI;
    if (!api || typeof api.discoverLocalLlm !== "function") {
      pushSwarmStatus("Local LLM discovery unavailable.", "ERR");
      return null;
    }

    setDiscoveringLlm(true);
    try {
      const discovery = await api.discoverLocalLlm([
        stationConfig.localEndpoint,
        "http://wsl.localhost:11434",
        "http://127.0.0.1:11434",
      ]);
      setOllamaDiscovery(discovery);

      if (!discovery?.ok || !discovery.model || !discovery.endpoint) {
        pushSwarmStatus("No local Ollama model found.", "ERR");
        return discovery;
      }

      const next = {
        ...stationConfig,
        llmRoute: "local",
        localEndpoint: discovery.endpoint,
        localModel: discovery.model,
      };
      persistConfig(next);
      pushSwarmStatus(`Ollama model selected: ${discovery.model}`, "PASS");

      if (autoApply && typeof api.setOrbState === "function") {
        await Promise.allSettled([
          api.setOrbState("llm_route", "local"),
          api.setOrbState("llm_local_endpoint", discovery.endpoint),
          api.setOrbState("llm_local_model", discovery.model),
          api.setOrbState("llm_governance_wrapper", false),
          api.setOrbState("llm_retain_voice", Boolean(next.retainVoice)),
        ]);
        pushSwarmStatus("Local LLM route applied.", "PASS");
      }

      return discovery;
    } catch (error) {
      pushSwarmStatus(`Ollama scan failed: ${error?.message || String(error)}`, "ERR");
      return null;
    } finally {
      setDiscoveringLlm(false);
    }
  }, [persistConfig, pushSwarmStatus, stationConfig]);

  useEffect(() => {
    if (stationConfig.llmRoute !== "local" || ollamaDiscovery) {
      return;
    }
    discoverLocalLlm({ autoApply: true });
  }, [discoverLocalLlm, ollamaDiscovery, stationConfig.llmRoute]);

  const applyLlmConfig = useCallback(async () => {
    const api = window.electronAPI;
    if (!api || typeof api.setOrbState !== "function") return;
    setSavingLlmConfig(true);
    try {
      const writes = [
        api.setOrbState("llm_route", stationConfig.llmRoute),
        api.setOrbState("llm_api_base", stationConfig.apiBase || ""),
        api.setOrbState("llm_api_model", stationConfig.apiModel || ""),
        api.setOrbState("llm_api_key", stationConfig.apiKey || ""),
        api.setOrbState("llm_local_endpoint", stationConfig.localEndpoint || ""),
        api.setOrbState("llm_local_model", stationConfig.localModel || ""),
        api.setOrbState("llm_governance_wrapper", false),
        api.setOrbState("llm_retain_voice", Boolean(stationConfig.retainVoice)),
      ];
      const results = await Promise.allSettled(writes);
      const rejected = results.filter((r) => r.status === "rejected");
      const failedWrites = results
        .filter((r) => r.status === "fulfilled" && r.value?.data?.ok === false);
      if (rejected.length || failedWrites.length) {
        pushSwarmStatus(
          `LLM apply incomplete (reject:${rejected.length}, failed:${failedWrites.length}).`,
          "ERR"
        );
      } else {
        pushSwarmStatus("LLM routing applied.", "PASS");
      }
    } finally {
      setSavingLlmConfig(false);
    }
  }, [governanceEnabled, pushSwarmStatus, stationConfig]);

  const ensureRealtimeListening = useCallback(async (reason = "startup", attempts = 6, delayMs = 1200) => {
    const api = window.electronAPI;
    if (!api || typeof api.setListening !== "function") return false;
    for (let i = 0; i < attempts; i += 1) {
      if (i > 0) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
      try {
        const response = await api.setListening(true);
        const enabled = Boolean(
          response?.data?.enabled ??
          response?.enabled ??
          response?.data?.ok ??
          response?.ok
        );
        if (enabled) {
          pushSwarmStatus(`Realtime listening armed (${reason}).`, "PASS");
          return true;
        }
      } catch (_error) {
        // Runtime may still be initializing mic/voice; retry until attempts exhausted.
      }
    }
    pushSwarmStatus(`Listening arm pending (${reason}).`, "INFO");
    return false;
  }, [pushSwarmStatus]);

  const handleActivatePrimeOrb = useCallback(async () => {
    if (!isDockReady) return;
    const api = window.electronAPI;
    if (!api) return;
    let launched = false;
    const notes = [];
    if (typeof api.launchOrbFromDock === "function") {
      try {
        const result = await api.launchOrbFromDock();
        launched = Boolean(result?.visible ?? true);
      } catch (error) {
        notes.push(`launch:${error?.message || String(error)}`);
      }
    }
    if (typeof api.dispatchPrimeOrbCommand === "function") {
      try {
        const result = await api.dispatchPrimeOrbCommand({ command: "activate", source: "dock_station" });
        if (result?.ok === false) {
          notes.push(`dispatch:${result?.error || "not delivered"}`);
        }
      } catch (error) {
        notes.push(`dispatch:${error?.message || String(error)}`);
      }
    }
    try {
      await ensureRealtimeListening("activate");
    } catch (error) {
      notes.push(`listening:${error?.message || String(error)}`);
    }
    try {
      await applyLlmConfig();
    } catch (error) {
      notes.push(`routing:${error?.message || String(error)}`);
    }
    if (stationConfig.llmRoute === "local") {
      try {
        await discoverLocalLlm({ autoApply: true });
      } catch (error) {
        notes.push(`llm:${error?.message || String(error)}`);
      }
    } else if (stationConfig.llmRoute === "cali") {
      pushSwarmStatus("CALI local cognitive core routing active.", "PASS");
    }
    if (launched) {
      pushSwarmStatus("Prime ORB activated.", "PASS");
      if (notes.length) {
        pushSwarmStatus(`Activate degraded: ${notes.join(" | ")}`, "INFO");
      }
    } else {
      pushSwarmStatus(`Activate failed: ${notes.join(" | ") || "unable to set visibility"}`, "ERR");
    }
  }, [applyLlmConfig, discoverLocalLlm, ensureRealtimeListening, isDockReady, pushSwarmStatus, stationConfig.llmRoute]);

  const handleDockLogin = useCallback(() => {
    const user = String(loginUser || "").trim();
    const pass = String(loginPass || "").trim();
    if (!user || !pass) {
      setLoginError("Enter username and password.");
      return;
    }
    if (!privacyAccepted || !termsAccepted) {
      setLoginError("Accept Privacy Notice and Terms of Service to continue.");
      return;
    }
    setLoginError("");
    setBootPhase("ready");
    pushSwarmStatus("DockStation authenticated. Activate ORB to launch.", "PASS");
  }, [loginPass, loginUser, privacyAccepted, termsAccepted, pushSwarmStatus]);

  useEffect(() => {
    if (startupConnectRef.current) return;
    startupConnectRef.current = true;
    const api = window.electronAPI;
    if (!api) return;
    (async () => {
      try {
        await ensureRealtimeListening("startup");
        await applyLlmConfig();
        if (stationConfig.llmRoute === "local") {
          await discoverLocalLlm({ autoApply: true });
        } else if (stationConfig.llmRoute === "cali") {
          pushSwarmStatus("Startup CALI cognitive core routing applied.", "PASS");
        }
        pushSwarmStatus("Startup connect complete (docked standby).", "PASS");
      } catch (error) {
        pushSwarmStatus(`Startup connect failed: ${error?.message || String(error)}`, "ERR");
      }
    })();
  }, [applyLlmConfig, discoverLocalLlm, ensureRealtimeListening, pushSwarmStatus, stationConfig.llmRoute]);

  useEffect(() => {
    if (!tel.dockChannelConnected || tel.listeningEnabled) {
      return;
    }
    const now = Date.now();
    if (now - listeningBootstrapRef.current.lastTryAt < 8000) {
      return;
    }
    listeningBootstrapRef.current.lastTryAt = now;
    ensureRealtimeListening("reconnect", 4, 1500);
  }, [ensureRealtimeListening, tel.dockChannelConnected, tel.listeningEnabled]);

  const handleDockPrimeOrb = useCallback(async () => {
    const api = window.electronAPI;
    if (!api || typeof api.setOrbVisibility !== "function") return;
    try {
      await api.setOrbVisibility(false);
      pushSwarmStatus("Prime ORB docked.", "INFO");
    } catch (error) {
      pushSwarmStatus(`Dock failed: ${error?.message || String(error)}`, "ERR");
    }
  }, [pushSwarmStatus]);

  const handleLaunchPrimeOrb = useCallback(async () => {
    const api = window.electronAPI;
    if (!api || typeof api.launchOrbFromDock !== "function") return;
    try {
      await api.launchOrbFromDock();
      pushSwarmStatus("Prime ORB launched.", "PASS");
    } catch (error) {
      pushSwarmStatus(`Launch failed: ${error?.message || String(error)}`, "ERR");
    }
  }, [pushSwarmStatus]);

  const handleSpawnMicroOrb = useCallback(async () => {
    const api = window.electronAPI;
    if (!api || typeof api.dispatchPrimeOrbCommand !== "function") return;
    try {
      const count = PRIME_SWARM_COUNTS[0];
      pushSwarmStatus(`Spawning ${count} Morbs...`, "INFO");
      await api.dispatchPrimeOrbCommand({
        command: "spawn_micro_orb",
        count,
        mode: "research",
        source: "dock_station",
      });
      pushSwarmStatus("Swarm deployed.", "PASS");
    } catch (error) {
      pushSwarmStatus(`Spawn failed: ${error?.message || String(error)}`, "ERR");
    }
  }, [pushSwarmStatus]);

  const handleDeployManualSwarm = useCallback(async (mode = "research") => {
    const api = window.electronAPI;
    const query = manualQuery.trim();
    const context = manualContext.trim();
    if (!api || !query) return;

    const missionMode = String(mode || "research").toLowerCase() === "diagnostics" ? "diagnostics" : "research";
    const inferredCount = computePrimeSetForQuery(query, missionMode);
    const primeCount = normalizeRequestedPrimeCount(manualMorbCount, inferredCount);
    const prompt = context ? `${query}\n\nContext:\n${context}` : query;
    setDeployingSwarm(true);
    try {
      pushSwarmStatus(`Spawning ${primeCount} ${missionMode} Morbs (${manualDeployZone})...`, "INFO");
      if (typeof api.dispatchPrimeOrbCommand === "function") {
        await api.dispatchPrimeOrbCommand({
          command: "deploy_swarm",
          mode: missionMode,
          query,
          context,
          count: primeCount,
          deployZone: manualDeployZone,
          source: "dock_station_manual",
        });
      }
      pushSwarmStatus("Swarm deployed.", "PASS");
      pushSwarmStatus("Awaiting return...", "INFO");

      if (missionMode === "diagnostics") {
        await api.orbQuery?.(prompt);
      } else {
        await api.orbResearch?.(prompt, []);
      }
      pushSwarmStatus("Prime verdict ready.", "PASS");
    } catch (error) {
      pushSwarmStatus(`Deployment failed: ${error?.message || String(error)}`, "ERR");
    } finally {
      setDeployingSwarm(false);
    }
  }, [manualContext, manualDeployZone, manualMorbCount, manualQuery, pushSwarmStatus]);

  const voiceStateLabel = tel.voiceProviderReady
    ? (String(tel.voiceProvider || "").toLowerCase() === "qwen"
      ? "QWEN ACTIVE"
      : String(tel.voiceProvider || "").toLowerCase() === "kokoro"
        ? "KOKORO FALLBACK"
        : "VOICE READY")
    : (String(tel.voiceProvider || "").toLowerCase() === "degraded" ? "VOICE DEGRADED" : "NO VOICE");
  const channelStateLabel = tel.dockChannelConnected
    ? (tel.listeningEnabled ? "CHANNEL CONNECTED / LISTENING" : "CHANNEL CONNECTED / LISTENING OFF")
    : "CHANNEL DISCONNECTED";
  const hlsfTag = String(tel?.hlsfSnapshot?.semantic_tag || "idle").toUpperCase();
  const hlsfDensity = Math.round(toNumberOr(tel?.hlsfSnapshot?.field_density, toNumberOr(tel.fieldDensity, 0)));
  const hlsfEdgeActive = Boolean(tel?.hlsfSnapshot?.hysteresis?.active);
  const egfMode = String(tel?.egfState?.mode || "unknown").toUpperCase();
  const egfOk = tel?.egfState?.ok !== false;
  const egfError = String(tel?.egfState?.error || "");
  const siteStatusEntries = Object.entries(tel?.siteOrbStatus || {});

  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100%", overflow: "hidden",
      position: "relative",
      background: "radial-gradient(ellipse at 30% 20%, rgba(9,24,35,1) 0%, rgba(4,12,20,1) 58%, rgba(2,6,12,1) 100%)",
      color: "#edfaff", fontFamily: "'Courier New', monospace",
    }}>
      <style>{`
        @keyframes pulse-ring{0%{box-shadow:0 0 0 0 rgba(0,229,255,.62)}100%{box-shadow:0 0 0 24px rgba(0,229,255,0)}}
        ::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:rgba(0,229,255,.28);border-radius:2px}
      `}</style>
      {/* ── Header ── */}
      <div style={{
        flex: "0 0 auto", display: "flex", alignItems: "center", padding: "0 16px",
        minHeight: 102, borderBottom: "1px solid rgba(174,220,232,.18)",
        background: "linear-gradient(90deg, rgba(6,18,28,.98), rgba(9,26,36,.94))",
        gap: 12,
      }}>
        <div style={{ width: 28, height: 28, borderRadius: "50%", border: `2px solid ${accent}66`,
          background: `radial-gradient(circle, ${accent}88, ${accent}33)`, animation: "pulse-ring 3.4s ease-out infinite", flexShrink: 0 }} />
        <div style={{ flexShrink: 0 }}>
          <div style={{ fontSize: 15, letterSpacing: 1.4, color: "#edfaff", fontWeight: "bold" }}>ORB DOCK</div>
          <div style={{ fontSize: 11, color: "rgba(211,236,243,.5)", letterSpacing: 0.8 }}>TIER {tier}</div>
        </div>
        <div style={{ display: "flex", gap: 4, marginLeft: 8 }}>
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
              padding: "6px 12px", fontSize: 12, letterSpacing: 0.8, cursor: "pointer",
              borderRadius: 4, fontFamily: "monospace",
              background: activeTab === t.id ? "rgba(90,242,165,.14)" : "transparent",
              border: `1px solid ${activeTab === t.id ? "rgba(90,242,165,.7)" : "rgba(174,220,232,.18)"}`,
              color: activeTab === t.id ? "#5af2a5" : "rgba(211,236,243,.66)",
            }}>{t.label}</button>
          ))}
        </div>
        <div style={{ marginLeft: "auto", display: "grid", gap: 6, minWidth: 0, width: "100%", maxWidth: 980 }}>
          <div style={{ display: "flex", gap: 6, justifyContent: "flex-end", alignItems: "center", flexWrap: "wrap" }}>
            <span
              style={{
                padding: "6px 10px",
                borderRadius: 4,
                fontSize: 11,
                fontFamily: "monospace",
                letterSpacing: 0.8,
                border: `1px solid ${isDocked ? "rgba(0,230,118,.6)" : "rgba(0,229,255,.45)"}`,
                background: isDocked ? "rgba(0,230,118,.14)" : "rgba(0,229,255,.12)",
                color: isDocked ? "#00e676" : "#00e5ff",
              }}
            >
              {isDocked ? "DOCKED" : "LAUNCHED"}
            </span>
            {tier >= 3 && (
              <button
                onClick={() => window.electronAPI?.openStudio?.()}
                style={{
                  padding: "6px 10px", borderRadius: 4, fontSize: 12, fontFamily: "monospace", cursor: "pointer",
                  border: `1px solid ${studioConnected ? "#00e676" : "rgba(255,255,255,.2)"}`,
                  background: studioConnected ? "rgba(0,230,118,.15)" : "rgba(255,255,255,.06)",
                  color: studioConnected ? "#00e676" : "rgba(255,255,255,.55)", letterSpacing: 1,
                }}
              >{studioConnected ? "● STUDIO" : "STUDIO"}</button>
            )}
            <button
              onClick={handleActivatePrimeOrb}
              style={{
                padding: "6px 10px", borderRadius: 4, fontSize: 12, fontFamily: "monospace", cursor: "pointer",
                border: "1px solid rgba(0,230,118,.6)",
                background: "rgba(0,230,118,.16)",
                color: "#00e676", letterSpacing: 0.8,
              }}
            >{isDocked ? "Activate / Launch ORB" : "Activate ORB"}</button>
            <button
              onClick={isDocked ? handleLaunchPrimeOrb : handleDockPrimeOrb}
              style={{
                padding: "6px 10px", borderRadius: 4, fontSize: 12, fontFamily: "monospace", cursor: "pointer",
                border: isDocked ? "1px solid rgba(0,230,118,.6)" : "1px solid rgba(179,136,255,.55)",
                background: isDocked ? "rgba(0,230,118,.16)" : "rgba(179,136,255,.16)",
                color: isDocked ? "#00e676" : "#d1b2ff", letterSpacing: 0.8,
              }}
            >{isDocked ? "Launch ORB" : "Dock ORB"}</button>
            <button
              onClick={handleSpawnMicroOrb}
              style={{
                padding: "6px 10px", borderRadius: 4, fontSize: 12, fontFamily: "monospace", cursor: "pointer",
                border: "1px solid rgba(0,229,255,.5)",
                background: "rgba(0,229,255,.14)",
                color: "#00e5ff", letterSpacing: 0.8,
              }}
            >Spawn Morbs</button>
            <span style={{ fontSize: 12, color: "rgba(211,236,243,.72)" }}>{new Date(tel.epochTime).toTimeString().slice(0, 8)}</span>
          </div>
          <div style={{ display: "flex", gap: 6, justifyContent: "flex-end", alignItems: "center", flexWrap: "wrap" }}>
            <input
              value={manualQuery}
              onChange={(e) => setManualQuery(e.target.value)}
              placeholder="Swarm query"
              style={{
                flex: 1,
                minWidth: 150,
                maxWidth: 260,
                background: "rgba(255,255,255,.06)",
                border: "1px solid rgba(174,220,232,.28)",
                borderRadius: 4,
                color: "#edfaff",
                padding: "6px 8px",
                fontSize: 11,
                fontFamily: "monospace",
                outline: "none",
              }}
            />
            <input
              value={manualContext}
              onChange={(e) => setManualContext(e.target.value)}
              placeholder="Context (optional)"
              style={{
                flex: 1,
                minWidth: 150,
                maxWidth: 260,
                background: "rgba(255,255,255,.08)",
                border: "1px solid rgba(174,220,232,.28)",
                borderRadius: 4,
                color: "#edfaff",
                padding: "6px 8px",
                fontSize: 11,
                fontFamily: "monospace",
                outline: "none",
              }}
            />
            <input
              type="number"
              min={2}
              step={1}
              value={String(manualMorbCount)}
              onChange={(e) => setManualMorbCount(Number(e.target.value || 2))}
              placeholder="Morb count"
              style={{
                background: "rgba(255,255,255,.08)",
                border: "1px solid rgba(174,220,232,.28)",
                borderRadius: 4,
                color: "#edfaff",
                padding: "6px 8px",
                fontSize: 11,
                fontFamily: "monospace",
                outline: "none",
                minWidth: 110,
              }}
            />
            <select
              value={manualDeployZone}
              onChange={(e) => setManualDeployZone(e.target.value)}
              style={{
                background: "rgba(255,255,255,.08)",
                border: "1px solid rgba(174,220,232,.28)",
                borderRadius: 4,
                color: "#edfaff",
                padding: "6px 8px",
                fontSize: 11,
                fontFamily: "monospace",
                outline: "none",
                minWidth: 112,
              }}
            >
              <option value="around">Around</option>
              <option value="left">Left</option>
              <option value="right">Right</option>
              <option value="top">Top</option>
              <option value="bottom">Bottom</option>
            </select>
            <button
              onClick={() => handleDeployManualSwarm("research")}
              disabled={deployingSwarm || !manualQuery.trim()}
              style={{
                padding: "6px 10px", borderRadius: 4, fontSize: 12, fontFamily: "monospace", cursor: deployingSwarm || !manualQuery.trim() ? "not-allowed" : "pointer",
                border: "1px solid rgba(0,229,255,.66)",
                background: "rgba(0,229,255,.16)",
                color: "#00e5ff", letterSpacing: 0.8,
                opacity: deployingSwarm || !manualQuery.trim() ? 0.55 : 1,
              }}
            >{deployingSwarm ? "Deploying..." : "Spawn Research"}</button>
            <button
              onClick={() => handleDeployManualSwarm("diagnostics")}
              disabled={deployingSwarm || !manualQuery.trim()}
              style={{
                padding: "6px 10px", borderRadius: 4, fontSize: 12, fontFamily: "monospace", cursor: deployingSwarm || !manualQuery.trim() ? "not-allowed" : "pointer",
                border: "1px solid rgba(125,211,255,.66)",
                background: "rgba(125,211,255,.16)",
                color: "#7dd3ff", letterSpacing: 0.8,
                opacity: deployingSwarm || !manualQuery.trim() ? 0.55 : 1,
              }}
            >{deployingSwarm ? "Deploying..." : "Spawn Diagnostics"}</button>
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <div style={{ width: "100%", maxWidth: 420, padding: "5px 8px", borderRadius: 4, border: "1px solid rgba(174,220,232,.18)", background: "rgba(2,8,14,.55)", fontSize: 10, fontFamily: "monospace", color: "rgba(211,236,243,.84)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {swarmStatusFeed[0]?.text || "Prime ORB idle."}
            </div>
          </div>
        </div>
      </div>

      {/* ── Tab Content ── */}
      <div style={{ flex: 1, overflowY: "auto", padding: "14px 16px", display: "flex", flexDirection: "column", gap: 12 }}>

        {activeTab === "orb" && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(320px, 1fr))", gap: 12, minHeight: 0, alignItems: "stretch" }}>
            <Panel title="HLSF Mirror" accent={accent} badge="LEFT">
              <HLSFMirrorPanel telemetry={tel} accent={accent} />
            </Panel>
            <Panel title="Docked ORB" accent={accent} badge={isDocked ? "DOCKED" : "LAUNCHED"}>
              <DockedOrbStage telemetry={tel} accent={accent} isDocked={isDocked} />
              <div style={{ display: "flex", justifyContent: "center", paddingTop: 10 }}>
                <button
                  onClick={isDocked ? handleLaunchPrimeOrb : handleDockPrimeOrb}
                  style={{
                    padding: "7px 14px",
                    borderRadius: 4,
                    border: isDocked ? "1px solid rgba(0,230,118,.65)" : "1px solid rgba(125,211,255,.65)",
                    background: isDocked ? "rgba(0,230,118,.16)" : "rgba(125,211,255,.16)",
                    color: isDocked ? "#00e676" : "#7dd3ff",
                    cursor: "pointer",
                    fontSize: 11,
                    fontFamily: "monospace",
                    letterSpacing: 0.8,
                  }}
                >
                  {isDocked ? "Launch ORB" : "Dock ORB"}
                </button>
              </div>
            </Panel>
            <Panel title="EGF Mirror" accent={accent} badge="RIGHT">
              <EGFMirrorPanel telemetry={tel} />
            </Panel>
          </div>
        )}
{activeTab === "skills" && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 12, minHeight: 0 }}>
            <Panel title="Talk To Orb" accent={accent} badge="SKILLS">
              <ChatPanel accent={accent} />
            </Panel>
          </div>
        )}

        {activeTab === "runtime" && (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <Panel title="Core System" accent={accent}>
                <div style={{ display: "flex", justifyContent: "center", marginBottom: 8 }}>
                  <Gauge value={tel.systemHealth} label="HEALTH" color={accent} size={84} />
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <Pill label="CORE INTEGRITY" value={`${tel.coreIntegrity.toFixed(1)}%`} />
                  <Pill label="UPTIME" value={uptime} />
                  <Pill label="CONTROLLER" value={String(tel.controllerStatus || "–").toUpperCase()} ok={["active","ready"].includes(String(tel.controllerStatus||"").toLowerCase())} />
                  <Pill label="PRESENCE" value={tel.presenceIdle ? "IDLE" : "ACTIVE"} ok={tel.presenceRunning} />
                  <Pill label="IDLE SECONDS" value={`${Math.round(tel.idleSeconds || 0)}s`} />
                  <Pill label="INSTANCE" value={String(tel.instanceId || "–")} />
                  <Pill label="MESH ROOT" value={String(tel.sharedMeshRoot || "–")} />
                </div>
              </Panel>
              <Panel title="Orb Stats" accent={accent}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 8 }}>
                  <Gauge value={tel.cpuLoad} label="CPU" color="#00e5ff" size={62} />
                  <Gauge value={tel.memUsage} label="MEM" color="#ffd740" size={62} />
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
                  <div style={{ textAlign: "center", border: "1px solid rgba(255,215,64,.2)", background: "rgba(255,215,64,.08)", borderRadius: 4, padding: 4 }}>
                    <div style={{ fontSize: 7, color: "rgba(255,255,255,.5)" }}>KG NODES</div>
                    <div style={{ fontSize: 11, color: "#ffd740", fontWeight: "bold" }}>{Math.round(toNumberOr(tel.knowledgeGraphNodes, 0))}</div>
                  </div>
                  <div style={{ textAlign: "center", border: "1px solid rgba(0,230,118,.2)", background: "rgba(0,230,118,.08)", borderRadius: 4, padding: 4 }}>
                    <div style={{ fontSize: 7, color: "rgba(255,255,255,.5)" }}>KG EDGES</div>
                    <div style={{ fontSize: 11, color: "#00e676", fontWeight: "bold" }}>{Math.round(toNumberOr(tel.knowledgeGraphEdges, 0))}</div>
                  </div>
                </div>
              </Panel>
            </div>
            <Panel title="Live Runtime" accent="#7c4dff">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
                <Pill label="ACTIVE LLM" value={llm} />
                <Pill label="GOV WRAPPER" value={governanceEnabled ? "ON" : "OFF"} ok={governanceEnabled || stationConfig.llmRoute === "cali"} />
                <Pill label="COGNITION DEVICE" value={String(tel.device || "unknown")} />
                <Pill label="ENCODER" value={String(tel.encoderBackend || "unknown")} />
                <Pill label="ANOMALIES" value={tel.anomalies} ok={tel.anomalies === 0} />
                <Pill label="INTERACTIONS" value={Math.round(toNumberOr(tel.interactionCount, 0))} />
                <Pill label="LISTENING" value={tel.listeningEnabled ? "ON" : "OFF"} ok={tel.listeningEnabled} />
                <Pill label="AUTO LISTEN" value={tel.autoListen ? "ON" : "OFF"} ok={tel.autoListen} />
                <Pill label="COGNITIVE MODE" value={cognitiveModeLabel} />
                <Pill label="AUTONOMY" value={tel.autonomyLevel.toFixed(2)} />
                <Pill label="CONFIDENCE" value={tel.confidenceState.toFixed(2)} />
                <Pill label="SUCCESS RATE" value={`${tel.llmSuccessRate.toFixed(1)}%`} />
              </div>
              <div style={{ marginTop: 8, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 9, color: "rgba(255,255,255,.45)" }}>LATENCY TREND</span>
                <Sparkline value={tel.llmLatency} color="#7c4dff" />
              </div>
            </Panel>
            <Panel title="Event Feed" accent="#4dd0e1" badge="STREAM">
              <div style={{ maxHeight: 200, overflowY: "auto" }}>
                {tel.events.map((ev) => (
                  <div key={ev.id} style={{ display: "flex", gap: 8, padding: "3px 0", borderBottom: "1px solid rgba(255,255,255,.05)" }}>
                    <span style={{ fontSize: 8, color: "rgba(255,255,255,.35)", width: 58 }}>{ev.time}</span>
                    <span style={{ fontSize: 8, width: 34, color: EVENT_COLOR[ev.type] || "#aaa" }}>[{ev.type}]</span>
                    <span style={{ fontSize: 9, color: "rgba(255,255,255,.7)" }}>{ev.msg}</span>
                  </div>
                ))}
              </div>
            </Panel>
          </>
        )}

        {activeTab === "settings" && (
          <>
            <Panel title="LLM Connector" accent="#b388ff">
              <select
                value={stationConfig.llmRoute}
                onChange={(e) => {
                  const nextRoute = e.target.value;
                  persistConfig({
                    ...stationConfig,
                    llmRoute: nextRoute,
                    governanceWrapper: false,
                  });
                }}
                style={{ background: "rgba(0,0,0,.35)", color: "#e0f7fa", border: "1px solid rgba(255,255,255,.2)", borderRadius: 4, padding: "4px 6px", fontSize: 10, marginBottom: 6, width: "100%" }}
              >
                <option value="cali">CALI (local cognitive core)</option>
                <option value="api">External API LLM</option>
                <option value="local">Local model endpoint</option>
              </select>
              {stationConfig.llmRoute === "api" && (
                <>
                  <input placeholder="API Base URL" value={stationConfig.apiBase}
                    onChange={(e) => persistConfig({ ...stationConfig, apiBase: e.target.value })}
                    style={{ background: "rgba(0,0,0,.35)", color: "#e0f7fa", border: "1px solid rgba(255,255,255,.2)", borderRadius: 4, padding: "4px 6px", fontSize: 10, marginBottom: 6, width: "100%" }} />
                  <input placeholder="API Model" value={stationConfig.apiModel}
                    onChange={(e) => persistConfig({ ...stationConfig, apiModel: e.target.value })}
                    style={{ background: "rgba(0,0,0,.35)", color: "#e0f7fa", border: "1px solid rgba(255,255,255,.2)", borderRadius: 4, padding: "4px 6px", fontSize: 10, marginBottom: 6, width: "100%" }} />
                  <input placeholder="API Key" type="password" value={stationConfig.apiKey}
                    onChange={(e) => persistConfig({ ...stationConfig, apiKey: e.target.value })}
                    style={{ background: "rgba(0,0,0,.35)", color: "#e0f7fa", border: "1px solid rgba(255,255,255,.2)", borderRadius: 4, padding: "4px 6px", fontSize: 10, marginBottom: 6, width: "100%" }} />
                </>
              )}
              {stationConfig.llmRoute === "local" && (
                <>
                  <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
                    <input placeholder="Local Endpoint" value={stationConfig.localEndpoint}
                    onChange={(e) => persistConfig({ ...stationConfig, localEndpoint: e.target.value })}
                      style={{ flex: 1, background: "rgba(0,0,0,.35)", color: "#e0f7fa", border: "1px solid rgba(255,255,255,.2)", borderRadius: 4, padding: "4px 6px", fontSize: 10 }} />
                    <button disabled={discoveringLlm} onClick={() => discoverLocalLlm({ autoApply: true })}
                      style={{ padding: "5px 10px", borderRadius: 4, border: "1px solid rgba(0,229,255,.55)", background: "rgba(0,229,255,.14)", color: "#00e5ff", cursor: "pointer", fontSize: 10, fontFamily: "monospace", whiteSpace: "nowrap" }}>
                      {discoveringLlm ? "Scanning..." : "Scan Ollama"}
                    </button>
                  </div>
                  {discoveredLocalModels.length > 0 ? (
                    <select value={stationConfig.localModel}
                      onChange={(e) => persistConfig({ ...stationConfig, llmRoute: "local", localModel: e.target.value })}
                      style={{ background: "rgba(0,0,0,.35)", color: "#e0f7fa", border: "1px solid rgba(255,255,255,.2)", borderRadius: 4, padding: "4px 6px", fontSize: 10, marginBottom: 6, width: "100%" }}>
                      {discoveredLocalModels.map((name) => (
                        <option key={name} value={name}>{name}</option>
                      ))}
                    </select>
                  ) : (
                    <input placeholder="Local Model" value={stationConfig.localModel}
                      onChange={(e) => persistConfig({ ...stationConfig, localModel: e.target.value })}
                      style={{ background: "rgba(0,0,0,.35)", color: "#e0f7fa", border: "1px solid rgba(255,255,255,.2)", borderRadius: 4, padding: "4px 6px", fontSize: 10, marginBottom: 6, width: "100%" }} />
                  )}
                  <div style={{ fontSize: 9, color: ollamaDiscovery?.ok ? "#63ef9e" : "rgba(255,255,255,.5)", marginBottom: 6 }}>
                    {ollamaDiscovery?.ok
                      ? `Ollama: ${ollamaDiscovery.endpoint} | ${discoveredLocalModels.length} model(s)`
                      : "Ollama scan will replace stale local model values."}
                  </div>
                </>
              )}
              <label style={{ fontSize: 9, color: "rgba(255,255,255,.75)", display: "flex", gap: 6, alignItems: "center", marginBottom: 8 }}>
                <input type="checkbox" checked={stationConfig.retainVoice}
                  onChange={(e) => persistConfig({ ...stationConfig, retainVoice: e.target.checked })} />
                Retain Orb voice in governance wrapper
              </label>
              <button disabled={savingLlmConfig} onClick={applyLlmConfig}
                style={{ padding: "5px 12px", borderRadius: 4, border: "1px solid rgba(179,136,255,.6)",
                  background: "rgba(179,136,255,.2)", color: "#d1b2ff", cursor: "pointer",
                  fontSize: 10, fontFamily: "monospace" }}>
                {savingLlmConfig ? "Applying..." : "Apply LLM Routing"}
              </button>
            </Panel>

            <Panel title="Desktop MCP" accent="#ffcc66">
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <Pill
                  label="DESKTOP ACTIONS"
                  value={desktopMcpActionsEnabled ? "ENABLED" : "DISABLED"}
                  ok={desktopMcpActionsEnabled}
                />
                <label style={{ fontSize: 10, color: "rgba(255,255,255,.82)", display: "flex", gap: 6, alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={desktopMcpActionsEnabled}
                    onChange={(e) => persistConfig({ ...stationConfig, desktopMcpActionsEnabled: e.target.checked })}
                  />
                  Desktop actions
                </label>
              </div>
            </Panel>

            <Panel title="Orb Skin" accent={accent}>
              <div style={{ display: "grid", gap: 4 }}>
                {SKINS.map((s) => (
                  <button key={s.id}
                    onClick={async () => {
                      setSkinId(s.id);
                      persistConfig({ ...stationConfig, skinId: s.id });
                      const api = window.electronAPI;
                      if (api && typeof api.setOrbState === "function") await api.setOrbState("skin", s.id);
                    }}
                    style={{
                      padding: "6px 10px", borderRadius: 4, textAlign: "left", fontFamily: "monospace", fontSize: 10, cursor: "pointer",
                      border: `1px solid ${skinId === s.id ? s.accent + "66" : "rgba(255,255,255,.12)"}`,
                      background: skinId === s.id ? `${s.accent}22` : "transparent",
                      color: skinId === s.id ? s.accent : "rgba(255,255,255,.6)",
                    }}>{s.label}</button>
                ))}
              </div>
            </Panel>

            <Panel title="Voice" accent="#00e676">
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <Pill label="LISTENING" value={tel.listeningEnabled ? "ON" : "OFF"} ok={tel.listeningEnabled} />
                <Pill label="AUTO LISTEN" value={tel.autoListen ? "ON" : "OFF"} ok={tel.autoListen} />
                <button
                  onClick={async () => {
                    const api = window.electronAPI;
                    if (!api || typeof api.setListening !== "function") return;
                    await api.setListening(!tel.listeningEnabled);
                  }}
                  style={{ padding: "5px 12px", borderRadius: 4, border: "1px solid rgba(0,230,118,.5)",
                    background: tel.listeningEnabled ? "rgba(0,230,118,.2)" : "rgba(255,80,80,.12)",
                    color: tel.listeningEnabled ? "#00e676" : "#ff6060", cursor: "pointer",
                    fontSize: 10, fontFamily: "monospace" }}>
                  {tel.listeningEnabled ? "Disable Listening" : "Enable Listening"}
                </button>
              </div>
            </Panel>

            <Panel title="Startup" accent="#4dd0e1">
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <label style={{ fontSize: 10, color: "rgba(255,255,255,.82)", display: "flex", gap: 6, alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={stationConfig.startOnBoot}
                    onChange={(e) => persistConfig({ ...stationConfig, startOnBoot: e.target.checked })}
                  />
                  Start CALI ORB when Windows starts
                </label>
                <label style={{ fontSize: 10, color: "rgba(255,255,255,.82)", display: "flex", gap: 6, alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={stationConfig.showStartupSplash}
                    onChange={(e) => persistConfig({ ...stationConfig, showStartupSplash: e.target.checked })}
                  />
                  Show startup animation
                </label>
                <label style={{ fontSize: 10, color: "rgba(255,255,255,.82)", display: "flex", gap: 6, alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={stationConfig.startDocked}
                    onChange={(e) => persistConfig({ ...stationConfig, startDocked: e.target.checked })}
                  />
                  Start minimized/docked
                </label>
                <label style={{ fontSize: 10, color: "rgba(255,255,255,.82)", display: "flex", gap: 6, alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={stationConfig.startupVoiceGreeting}
                    onChange={(e) => persistConfig({ ...stationConfig, startupVoiceGreeting: e.target.checked })}
                  />
                  Startup voice greeting
                </label>
                <div style={{ fontSize: 9, color: "rgba(255,255,255,.52)", marginTop: 4 }}>
                  Startup preferences saved locally. Env/runtime startup flags remain authoritative.
                </div>
              </div>
            </Panel>
          </>
        )}
      </div>

      {bootPhase !== "ready" && (
        <div style={{
          position: "absolute",
          inset: 0,
          background: "rgba(2,10,18,.68)",
          backdropFilter: "blur(1px)",
          display: "grid",
          placeItems: "center",
          zIndex: 9999,
        }}>
          <div style={{
            width: 420,
            border: "1px solid rgba(139,223,240,.34)",
            borderRadius: 8,
            background: "rgba(4,18,30,.94)",
            padding: 18,
            color: "#edfaff",
            fontFamily: "monospace",
            display: "grid",
            gap: 10,
          }}>
            <div style={{ fontSize: 18, letterSpacing: 1 }}>DockStation Login</div>
            <input
              value={loginUser}
              onChange={(e) => setLoginUser(e.target.value)}
              placeholder="Username"
              style={{ background: "rgba(0,0,0,.35)", color: "#e0f7fa", border: "1px solid rgba(255,255,255,.22)", borderRadius: 4, padding: "8px 10px", fontSize: 12 }}
            />
            <input
              type="password"
              value={loginPass}
              onChange={(e) => setLoginPass(e.target.value)}
              placeholder="Password"
              style={{ background: "rgba(0,0,0,.35)", color: "#e0f7fa", border: "1px solid rgba(255,255,255,.22)", borderRadius: 4, padding: "8px 10px", fontSize: 12 }}
            />
            <label style={{ fontSize: 11, color: "rgba(220,245,255,.9)", display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={privacyAccepted}
                onChange={(e) => setPrivacyAccepted(e.target.checked)}
              />
              I agree to the Privacy Notice.
            </label>
            <label style={{ fontSize: 11, color: "rgba(220,245,255,.9)", display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={termsAccepted}
                onChange={(e) => setTermsAccepted(e.target.checked)}
              />
              I agree to the Terms of Service.
            </label>
            {loginError ? <div style={{ color: "#ff9f9f", fontSize: 11 }}>{loginError}</div> : null}
            <button
              onClick={handleDockLogin}
              style={{ padding: "8px 10px", borderRadius: 4, border: "1px solid rgba(0,230,118,.65)", background: "rgba(0,230,118,.16)", color: "#00e676", fontSize: 12, cursor: "pointer" }}
            >
              Login & Continue
            </button>
          </div>
        </div>
      )}

      {/* ── Status Bar ── */}
      <div style={{
        flex: "0 0 auto", height: 32, display: "flex", alignItems: "center", gap: 16, padding: "0 16px",
        borderTop: "1px solid rgba(174,220,232,.18)", background: "rgba(3,10,17,.94)",
        fontSize: 12, fontFamily: "monospace",
      }}>
        <span style={{ color: tel.device && tel.device !== "unknown" ? "#5af2a5" : "#ffcc66" }}>
          COGNITION: {String(tel.device || "unknown").toUpperCase()}
        </span>
        <span style={{ color: "rgba(211,236,243,.62)" }}>LATENCY: {tel.llmLatency > 0 ? `${Math.round(tel.llmLatency)}ms` : "n/a"}</span>
        <span style={{ color: tel.anomalies === 0 ? "rgba(211,236,243,.62)" : "#ff7d7d" }}>ANOMALIES: {tel.anomalies}</span>
        <span style={{ color: "rgba(211,236,243,.62)" }}>INTERACTIONS: {Math.round(toNumberOr(tel.interactionCount, 0))}</span>
        <button
          onClick={async () => {
            const api = window.electronAPI;
            if (!api || typeof api.setListening !== "function") return;
            await api.setListening(!tel.listeningEnabled);
          }}
          style={{
            marginLeft: "auto", padding: "4px 9px", borderRadius: 3, fontSize: 11, fontFamily: "monospace", cursor: "pointer",
            border: `1px solid ${tel.dockChannelConnected ? "rgba(0,230,118,.5)" : "rgba(255,255,255,.2)"}`,
            background: tel.dockChannelConnected ? "rgba(0,230,118,.15)" : "transparent",
            color: tel.dockChannelConnected ? "#00e676" : "rgba(255,255,255,.4)",
          }}
        >{tel.dockChannelConnected ? `● ${channelStateLabel}` : "○ CHANNEL DISCONNECTED"}</button>
      </div>
    </div>
  );
}

function OrbStudio() {
  const [studioTab, setStudioTab] = useState(ORB_SKIN_STUDIO_TABS[0]);
  const [frameNonce, setFrameNonce] = useState(0);
  const [frameState, setFrameState] = useState("loading");
  const displayTabs = ORB_SKIN_STUDIO_TABS.slice(0, 6);

  return (
    <div style={{
      display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden",
      background: "radial-gradient(ellipse at 30% 20%, rgba(0,20,50,1) 0%, rgba(0,5,15,1) 60%, rgba(0,0,8,1) 100%)",
      color: "#e0f7fa", fontFamily: "'Courier New', monospace",
    }}>
      <style>{`
        @keyframes pulse-ring-g{0%{box-shadow:0 0 0 0 rgba(0,230,118,.4)}100%{box-shadow:0 0 0 20px rgba(0,230,118,0)}}
        ::-webkit-scrollbar{width:4px}::-webkit-scrollbar-thumb{background:rgba(0,230,118,.28);border-radius:2px}
      `}</style>
      <div style={{
        flex: "0 0 auto", display: "flex", alignItems: "center", padding: "0 16px",
        height: 52, borderBottom: "1px solid rgba(0,230,118,.22)",
        background: "linear-gradient(90deg, rgba(0,10,20,.97), rgba(0,25,15,.92))",
        gap: 12,
      }}>
        <div style={{ width: 28, height: 28, borderRadius: "50%", border: "2px solid rgba(0,230,118,.66)",
          background: "radial-gradient(circle, rgba(0,230,118,.44), rgba(0,230,118,.11))",
          animation: "pulse-ring-g 2s infinite", flexShrink: 0 }} />
        <div style={{ flexShrink: 0 }}>
          <div style={{ fontSize: 12, letterSpacing: 3, color: "#00e676", fontWeight: "bold" }}>ORB STUDIO</div>
          <div style={{ fontSize: 7, color: "rgba(255,255,255,.35)", letterSpacing: 1.5 }}>SKIN &amp; CUSTOMIZATION</div>
        </div>
        <div style={{ display: "flex", gap: 4, marginLeft: 8, flexWrap: "wrap" }}>
          {displayTabs.map((tab) => (
            <button key={tab.id} onClick={() => { setStudioTab(tab); setFrameState("loading"); }} style={{
              padding: "4px 10px", fontSize: 9, letterSpacing: 1, cursor: "pointer",
              borderRadius: 4, fontFamily: "monospace",
              background: studioTab.id === tab.id ? "rgba(0,230,118,.2)" : "transparent",
              border: `1px solid ${studioTab.id === tab.id ? "rgba(0,230,118,.6)" : "rgba(255,255,255,.15)"}`,
              color: studioTab.id === tab.id ? "#00e676" : "rgba(255,255,255,.45)",
            }}>{tab.label}</button>
          ))}
        </div>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8, alignItems: "center" }}>
          <button onClick={() => { setFrameNonce((v) => v + 1); setFrameState("loading"); }}
            style={{ padding: "4px 10px", borderRadius: 4, fontSize: 9, fontFamily: "monospace", cursor: "pointer",
              border: "1px solid rgba(0,229,255,.4)", background: "rgba(0,229,255,.1)", color: "#00e5ff" }}>
            Reload
          </button>
          <span style={{ fontSize: 9, color: frameState === "ready" ? "#00e676" : "#ffd740" }}>
            {frameState.toUpperCase()}
          </span>
        </div>
      </div>
      <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
        <iframe
          key={`${studioTab.id}-${frameNonce}`}
          title={`Orb Studio - ${studioTab.label}`}
          src={toSkinStudioUrl(studioTab.file)}
          onLoad={() => setFrameState("ready")}
          style={{ width: "100%", height: "100%", border: "none", background: "#0a0a0f" }}
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals allow-downloads"
        />
      </div>
      <div style={{
        flex: "0 0 auto", height: 28, display: "flex", alignItems: "center", padding: "0 16px", gap: 12,
        borderTop: "1px solid rgba(0,230,118,.22)", background: "rgba(0,5,15,.9)",
        fontSize: 9, fontFamily: "monospace",
      }}>
        <span style={{ color: "#00e676" }}>● STUDIO ACTIVE</span>
        <span style={{ color: "rgba(255,255,255,.4)" }}>Source: R:\Orb_Skin_Studio\{studioTab.file}</span>
      </div>
    </div>
  );
}

const rootEl = document.getElementById("root");
if (rootEl) {
  const root = ReactDOM.createRoot(rootEl);
  const params = new URLSearchParams(window.location.search);
  root.render(params.get("view") === "studio" ? <OrbStudio /> : <OrbDockStation />);
}
