# PRIME_ORB_DOCKSTATION_MONITORING_CONTRACT

This contract defines the canonical monitoring requirements for the Prime Desktop ORB DockStation. Each monitor group below specifies its purpose, monitoring priority, required Python status fields, DockStation display fields, allowed states, error and update requirements, and required DockStation tab/section visibility.

---

## 1. Bridge / IPC
- **Purpose:** Monitor IPC bridge health and event flow between backend and UI.
- **Primary/Secondary:** Primary
- **Python status field:** `bridge_state`, `last_event`
- **DockStation field:** Bridge, Last Event, IPC
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** ACP I/O, Event Feed

## 2. Status response
- **Purpose:** Canonical status payload for all runtime health and state.
- **Primary/Secondary:** Primary
- **Python status field:** `status` (root), `status_response` event
- **DockStation field:** All runtime fields, status bar, panels
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Overview, Runtime, Services

## 3. Runtime snapshot
- **Purpose:** Live system health, controller, presence, and performance.
- **Primary/Secondary:** Primary
- **Python status field:** `runtime_snapshot` (dict)
- **DockStation field:** Core System, Live Runtime, Status Bar
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Overview, Runtime

## 4. CALI/SKG cognition
- **Purpose:** Monitor CALI core and SKG cognition system health.
- **Primary/Secondary:** Primary
- **Python status field:** `active_llm`, `cali_system_root`, `skg_status`
- **DockStation field:** ACTIVE LLM, CALI SYSTEM
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Overview, Memory, Services

## 5. Local LLM / Qwen articulation
- **Purpose:** Monitor local LLM, Ollama, and Qwen articulation endpoints.
- **Primary/Secondary:** Primary
- **Python status field:** `local_llm.*`, `qwen_tts.*`
- **DockStation field:** LLM ROUTE, LLM CONNECTED, MODEL, QWEN TTS READY
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Services, Runtime

## 6. Qwen TTS
- **Purpose:** Monitor Qwen TTS endpoint and voice readiness.
- **Primary/Secondary:** Primary
- **Python status field:** `qwen_tts.*`, `cp3_io.audio_runtime_status.qwen_tts_endpoint`
- **DockStation field:** QWEN TTS READY, VOICE ENDPOINT
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Services, Runtime

## 7. Kokoro fallback
- **Purpose:** Monitor Kokoro fallback LLM/voice system.
- **Primary/Secondary:** Secondary
- **Python status field:** `kokoro_ready`, `kokoro_error`
- **DockStation field:** KOKORO READY
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Runtime, Services

## 8. Audio playback
- **Purpose:** Monitor audio playback/streaming subsystem.
- **Primary/Secondary:** Secondary
- **Python status field:** `audio_playback`, `cp3_io.audio_runtime_status`
- **DockStation field:** (future: AUDIO PLAYBACK)
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** ACP I/O, Runtime

## 9. CP3 / mic / voice runtime
- **Purpose:** Monitor CP3, mic, and voice runtime health.
- **Primary/Secondary:** Primary
- **Python status field:** `cp3_io.*`, `cp3.audio_runtime_status.*`
- **DockStation field:** CP3 VOICE RUNTIME, MIC RUNTIME, VOICE ADAPTER
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** ACP I/O, Services

## 10. Memory / substrate paths
- **Purpose:** Monitor memory, substrate, and cache path health.
- **Primary/Secondary:** Primary
- **Python status field:** `substrate.memory_root`, `..._exists`, `voice_cache_root`, etc.
- **DockStation field:** MEMORY PATH, CALI SYSTEM, VOICE CACHE
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Memory, Services

## 11. Notes
- **Purpose:** Monitor notes path, session, and notepad status.
- **Primary/Secondary:** Secondary
- **Python status field:** `substrate.notes_root`, `notes.*`
- **DockStation field:** NOTES PATH, NOTES, LAST NOTEPAD
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Memory, Services

## 12. Research vault
- **Purpose:** Monitor research vault, logs, and index health.
- **Primary/Secondary:** Secondary
- **Python status field:** `research_vault.*`, `researchVault.*`
- **DockStation field:** VAULT, ACTIVE LOG, INDEX
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Memory

## 13. Skills
- **Purpose:** Monitor skill library, catalog, and active skills.
- **Primary/Secondary:** Secondary
- **Python status field:** `skills.*`
- **DockStation field:** LIBRARY, CATALOG, ACTIVE, DECISIONS
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Skills

## 14. Services
- **Purpose:** Monitor all registered services and their health.
- **Primary/Secondary:** Primary
- **Python status field:** `services`, `serviceItems`
- **DockStation field:** Sites / Services list
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Services

## 15. CRM
- **Purpose:** Monitor CRM app health and connectivity.
- **Primary/Secondary:** Secondary
- **Python status field:** `crm`, `appStatus.crm`
- **DockStation field:** CRM app card
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Apps

## 16. Mail / Spruk_Email
- **Purpose:** Monitor Mail and Spruk_Email app health.
- **Primary/Secondary:** Secondary
- **Python status field:** `mail`, `appStatus.mail`, `appStatus.spruk_email`
- **DockStation field:** Mail, Spruk_Email app cards
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Apps

## 17. Presence / desktop awareness
- **Purpose:** Monitor presence, idle, and desktop awareness state.
- **Primary/Secondary:** Primary
- **Python status field:** `presence_state`, `presenceIdle`, `idleSeconds`
- **DockStation field:** PRESENCE, IDLE SECONDS
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Overview, Status Bar

## 18. MORB / swarm
- **Purpose:** Monitor MORB and swarm spawning status.
- **Primary/Secondary:** Secondary
- **Python status field:** `swarm`, `swarmStatusFeed`
- **DockStation field:** Spawn Research, Spawn Diagnostics, status feed
- **States allowed:** READY, CHECKING, DEGRADED, ERROR, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Orb, Status Feed

## 19. Errors / warnings / last exception
- **Purpose:** Monitor and surface all errors, warnings, and last exceptions.
- **Primary/Secondary:** Primary
- **Python status field:** `last_error`, `error`, `anomalies`, `last_exception`, `last_warning`
- **DockStation field:** ERROR, LAST ERROR, ANOMALIES
- **States allowed:** ERROR, DEGRADED, READY, CHECKING, OFF, UNKNOWN
- **Required last_error field:** Yes
- **Required last_updated field:** Yes
- **Required DockStation tab/section:** Runtime, Event Feed, ACP

---

**All monitor groups must provide:**
- A `last_error` field (string or null)
- A `last_updated` field (ISO timestamp)
- One of the allowed states
- Required visibility in the specified DockStation tab/section

This contract is canonical for all future Prime ORB Desktop DockStation implementations.
