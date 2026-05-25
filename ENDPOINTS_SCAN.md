# Orb Assistant Desktop - Endpoints & Communication Scan

**Date**: May 11, 2026  
**Scan Type**: Complete endpoint discovery and verification

---

## HTTP REST Endpoints

### FastAPI Backend (`api/main.py`)

**Server**: `0.0.0.0:8000`  
**Status**: Active

#### Endpoints Found:

| Method | Path | Description | Status |
|--------|------|-------------|--------|
| `POST` | `/api/v1/tribunal` | Four-Mind Tribunal consensus query | ✅ Implemented |
| `GET` | `/api/v1/health` | Health check / readiness probe | ✅ Implemented |

**Request/Response Details:**

**POST `/api/v1/tribunal`**
```json
Request:
{
  "prompt": "string",
  "context": { "key": "value" }  // optional
}

Response (200):
{
  "status": "success",
  "response": "string",
  "metadata": {
    "leading_mind": "spinoza|hume|locke|kant",
    "confidence": 0.0-1.0,
    "shadows": { "spinoza": {...}, "hume": {...}, ... },
    "vault_update": "pending|done"
  }
}

Response (500):
{
  "detail": "error message"
}
```

**GET `/api/v1/health`**
```json
Response (200):
{
  "status": "ORB System Operational",
  "layer": "FastAPI Core"
}
```

**Routers Included:**
- `/abby/*` → `substrate.learning_modules.abby_protocol.core.router`
- `/legacy/*` → `substrate.spruk_legacy_orb.core.presence_router`

---

## WebSocket Endpoints

### UCM WebSocket (React Orb Path)

**Endpoint**: `ws://localhost:8000/ws/orb_assistant`  
**Server**: Mock server (planned in `electron/src/ucm_server.py` - **NOT YET IMPLEMENTED**)  
**Status**: ⚠️ Stub only

**Handshake Message:**
```json
{
  "type": "ORB_HANDSHAKE",
  "orb_id": "desktop",
  "capabilities": ["motion", "hud", "drift"]
}
```

**Expected Messages from Server:**
```json
{
  "type": "lerp_optimization",
  "data": { "speed": 0.5, "smoothness": 0.8 }
}

{
  "type": "drift_preference",
  "data": { "x_offset": 10, "y_offset": 20 }
}
```

**Known Issue**: 
- Endpoint not yet implemented in mock server
- React FloatingOrb.jsx attempts connection but currently fails
- Performance HTTP polling also not implemented

### WS Stub (Local Dev)

**Endpoint**: `ws://localhost:${ORB_WS_PORT}` (default `9876`)  
**Server**: `electron/ws-stub.js`  
**Status**: ✅ Available (dev only)

**Run Command**: `npm run ws:stub` (from `electron/`)

**Behavior**: Echoes status and query responses for UI testing

---

## HTTP Performance Polling

**Endpoint**: `http://localhost:8000/api/orb/performance`  
**Server**: Mock server (planned - **NOT YET IMPLEMENTED**)  
**Status**: ⚠️ Stub only

**Polling Interval**: Every 5 seconds (from `electron/src/components/FloatingOrb.jsx`)

**Expected Response:**
```json
{
  "fps": 60,
  "cpu_usage": 0.15,
  "memory_mb": 250,
  "network_latency_ms": 5
}
```

---

## Ollama LLM API

**Endpoint**: `http://127.0.0.1:11434`  
**Status**: ✅ Installed in WSL (systemd managed)  
**Model**: `qwen2.5:3b` (pulled successfully)

**Storage Configuration**:
- Primary model store: `/mnt/r/ollama/.ollama/models` (R substrate)
- Fallback model store: `/home/bryan/.ollama/models` (WSL local, kept as backup)
- Ollama config: `/home/bryan/.ollama/ollama` (systemd service root)

**Startup Chain**:
1. Windows mounts `R_SUBSTRATE.vhdx` as `R:`
2. WSL starts with `/mnt/r` available
3. Ollama systemd service starts with `OLLAMA_MODELS=/mnt/r/ollama/.ollama/models`
4. Qwen model loads from R (primary) or WSL (fallback)

### Endpoints Used:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/tags` | List available models |
| `POST` | `/api/generate` | Generate response from prompt |

**Generate Request:**
```json
{
  "model": "qwen2.5:3b",
  "prompt": "your prompt here",
  "stream": false,
  "keep_alive": "15m",
  "temperature": 0.7,
  "top_p": 0.9,
  "options": {
    "num_gpu": 1  // optional
  }
}
```

**Generate Response:**
```json
{
  "response": "generated text",
  "done": true,
  "model": "qwen2.5:3b",
  ...
}
```

**Configuration Sources:**
- `ORB_LOCAL_LLM_ENDPOINT` (env) → `http://127.0.0.1:11434`
- `ORB_LOCAL_LLM_MODEL` (env) → `qwen2.5:3b`
- `CALI_OLLAMA_KEEP_ALIVE` (env) → `15m` (default)
- `CALI_OLLAMA_NUM_GPU` (env) → GPU layer count

---

## Kokoro TTS Endpoints (WSL)

**Endpoint**: `http://127.0.0.1:8888` (default, configurable)  
**Status**: ⚠️ External (requires Kokoro running in WSL)

**Configuration Source:**
- `KOKORO_WSL_ENDPOINT` (env) → `http://127.0.0.1:8888`

### Endpoints (Expected):

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Health check |
| `POST` | `/synthesize` | Generate speech |

**Synthesize Request:**
```json
{
  "text": "Hello world",
  "voice": "af_sky",
  "emotion": "neutral",
  "lang": "en"
}
```

**Synthesize Response:**
- Binary WAV audio data

---

## ACP 3.0 Interfaces

**Type**: Python module (in-process)  
**Endpoints**: None (direct function calls via IPC)  
**Status**: ✅ Adapter available (if ACP 3.0 installed)

**Path Search:**
1. `$CP3_ROOT` environment variable
2. `$ACP3_ROOT` environment variable
3. `{PROJECT_ROOT.parent}/cochlear_processor_3.0`

**Adapter Modules** (from `orb_acp3_adapter`):
- `MicCapture` - Speech recognition
- `KokoroBaseline` - TTS synthesis
- `frame_text_input` - Text processing

---

## Electron IPC Channels

**Type**: Inter-process communication (Electron)  
**Transport**: JSON messages over IPC  
**Bridged To**: Python via `python-shell` stdin/stdout

### Channels:

| Channel | Direction | Purpose |
|---------|-----------|---------|
| `orb:cursor-move` | Renderer → Main | Position update |
| `orb:get-status` | Renderer ↔ Main | Status query |
| `orb:cognitive-pulse` | Renderer ↔ Main | Query/response |
| `orb:speak-result` | Python → Renderer | Audio playback signal |

**Message Format:**
```json
{
  "type": "speak_result|cognitive-pulse|...",

---

## Swarm Mission Routing (Renderer)

**Implementation**: `electron/src/orb-renderer.js`  
**Status**: ✅ Active

### Deployment Rules

- Micro-orbs deploy only for `research` and `diagnostics` missions.
- Greetings/basic chat/non-task responses do not deploy swarm visuals.
- Inbound return swarm is gated by pending outbound mission tracking.

### Classifier Priority (Current)

1. diagnostics when failure/repair terms are present
2. research when research terms are present
3. no swarm otherwise

### Precedence Example

- `research why Ollama is failing` -> diagnostics route

### Visual Semantics

- Research outbound: blue
- Diagnostics outbound: amber
- Return success: green
- Return warning: amber
- Return fault: red

### Timing Model

- Phase order: `out_spin -> out_dart -> in_arc -> in_loop -> ingest`
- Prime shard counts remain constrained to: `2, 3, 5, 7, 11`

### Dev Observability

- Dev-only swarm HUD is enabled with `ORB_SWARM_HUD=1`.
- HUD reports mission mode, active phase, outbound/inbound/total nodes, pending count, last result state, timing windows, and EGF snapshot.

---
  "request_id": "uuid",
  "data": { ... }
}
```

---

## Substrate Database Endpoints

**Type**: Local SQLite  
**Path**: `system/swarm/substrate.db`  
**Status**: ✅ Active

**Tables with API-like access:**
- `audio_vault` - Cached TTS audio
- `audio_vault_cleanup` - Cleanup history
- Research event storage
- Task queues

**Access Method**: Python `sqlite3` module (from `audio_manager.py`)

---

## File System Endpoints & R Substrate Authority

**Windows → WSL Path Mapping (System-of-Record)**

```
R:\                          Windows substrate root (must mount first)
/mnt/r                       WSL-mounted substrate root
/substrate                   Linux stable symlink (recommended: ln -sfn /mnt/r /substrate)
/mnt/r/orb_mesh              Shared ORB mesh data
/mnt/r/ollama/.ollama/models Ollama model storage (primary)
/mnt/r/cochlear_processor_3.0 CP 3.0 root
/mnt/r/Orb_Assistant_Desktop ORB instance root (shared via mount)
```

**Storage Locations (all resolve to R substrate):**
- `CALI_System/voice_cache/` → `/mnt/r/Orb_Assistant_Desktop/CALI_System/voice_cache/`
- `CALI_System/memory/` → `/mnt/r/Orb_Assistant_Desktop/CALI_System/memory/`
- `CALI_System/notes/` → `/mnt/r/Orb_Assistant_Desktop/CALI_System/notes/`
- `system/swarm/substrate.db` → `/mnt/r/Orb_Assistant_Desktop/system/swarm/substrate.db`

---

## Required Environment Variables (WSL Baseline)

**Critical: R Substrate Authority**
```bash
# MUST be set before any ORB/Ollama/CP3.0 service starts
R_SUBSTRATE=/mnt/r
SUBSTRATE_ROOT=/mnt/r
ORB_SUBSTRATE=/mnt/r
```

**Component Paths (all point to R substrate)**
```bash
CP3_ROOT=/mnt/r/cochlear_processor_3.0
ACP3_ROOT=/mnt/r/cochlear_processor_3.0
OLLAMA_MODELS=/mnt/r/ollama/.ollama/models
KOKORO_ROOT=/mnt/r/kokoro
```

**LLM Configuration**
```bash
ORB_LOCAL_LLM_ENDPOINT=http://127.0.0.1:11434
ORB_LOCAL_LLM_MODEL=qwen2.5:3b
ORB_LLM_TIMEOUT_SECONDS=120
CALI_OLLAMA_KEEP_ALIVE=15m
CALI_OLLAMA_NUM_GPU=1
```

**TTS Configuration**
```bash
KOKORO_WSL_ENDPOINT=http://127.0.0.1:8888
KOKORO_DEFAULT_VOICE=af_sky
```

**Audio Cache Configuration**
```bash
ORB_ENABLE_AUDIO_CACHE=1
ORB_AUDIO_CACHE_TTL_DAYS=7
```

**WebSocket Configuration**
```bash
ORB_WS_PORT=9876  # Dev stub port
ORB_SWARM_HUD=0   # Renderer swarm HUD (set to 1 for dev/operator diagnostics)
```

**Debugging**
```bash
ORB_TTS_DEBUG=0
ORB_LLM_DEBUG=0
ORB_DEBUG_TORCH=0
```

**Epistemic Gravity Field Wiring**
```bash
ORB_ENABLE_EGF_TENSOR=1
ORB_EGF_ROOT=/mnt/r/Orb_Assistant_Desktop/modules/Epistemic_Gravity_Field
```

**Recommended Addition to `~/.bashrc`**
```bash
# R Substrate authority
export R_SUBSTRATE=/mnt/r
export SUBSTRATE_ROOT=/mnt/r
export ORB_SUBSTRATE=/mnt/r

# Component paths
export CP3_ROOT=/mnt/r/cochlear_processor_3.0
export OLLAMA_MODELS=/mnt/r/ollama/.ollama/models

# LLM
export ORB_LOCAL_LLM_ENDPOINT=http://127.0.0.1:11434
export ORB_LOCAL_LLM_MODEL=qwen2.5:3b
```

---

## Boot-Order Warning ⚠️

**Critical**: R substrate must mount BEFORE WSL starts, otherwise `/mnt/r` will be unavailable or stale.

**Required Boot Sequence**:
```
1. Windows boot
2. Mount R_SUBSTRATE.vhdx as R:
3. Assign drive letter and verify accessibility
4. Start WSL (ensures /mnt/r is available)
5. Start Docker daemon (if needed)
6. Start Ollama with OLLAMA_MODELS=/mnt/r/ollama/.ollama/models
7. Start cloudflared tunnel (if enabled)
8. Start ORB services (Desktop and/or server)
```

**If /mnt/r is missing or stale**:
- WSL will use fallback paths
- Ollama will use `/home/bryan/.ollama/models`
- CP 3.0 paths will fail
- ORB will not find substrate database
- **Result**: Degraded mode or complete failure

---

## Missing/Stubbed Endpoints

| Endpoint | Location | Status | Impact | Priority |
|----------|----------|--------|--------|----------|
| `/api/orb/performance` | `localhost:8000` | ❌ Missing | React FloatingOrb performance HUD fails | Later |
| `/ws/orb_assistant` | `ws://localhost:8000` | ⚠️ Stub | UCM-driven motion disabled | Later |
| Kokoro TTS | `http://127.0.0.1:8888` | ⚠️ External | TTS fallback to ACP 3.0 only | Later |
| UCM Core ECM | Various | ⚠️ Stub | Bridge returns "not_configured" | Later |

---

## Port Usage Summary

| Port | Service | Type | Status |
|------|---------|------|--------|
| `8000` | FastAPI (tribunal, health, WS stub) | HTTP/WS | ✅ Active |
| `8888` | Kokoro TTS (WSL) | HTTP | ⚠️ External |
| `11434` | Ollama LLM | HTTP | ⚠️ External |
| `9876` | WS Dev Stub | WebSocket | ✅ Available |

---

## Next Steps: Path Authority Reconnection

**Phase 1: Symlink & Environment (Immediate)**
```bash
# Create stable Linux path to R substrate
sudo ln -sfn /mnt/r /substrate

# Add to ~/.bashrc
export R_SUBSTRATE=/mnt/r
export SUBSTRATE_ROOT=/mnt/r
export CP3_ROOT=/mnt/r/cochlear_processor_3.0
export OLLAMA_MODELS=/mnt/r/ollama/.ollama/models

# Verify
ls -la /substrate/
echo $R_SUBSTRATE
```

**Phase 2: Service Configuration (In Progress)**
- Update Desktop ORB config to use `/mnt/r` paths
- Update Ollama systemd service to lock model path
- Update CP 3.0 initialization to use env-based path discovery

**Phase 3: Boot-Order Verification (Before Next Session)**
- Confirm R: mounts before WSL starts
- Test clean WSL restart with all paths available
- Verify Ollama loads model from `/mnt/r` (primary)

---

## Communication Flow

```
User Query (Screen/Voice)
    ↓
Electron Renderer (simple-orb.js)
    ↓
IPC Channel: orb:cognitive-pulse
    ↓
Electron Main (orb-bridge.js)
    ↓
Python stdin/stdout (python-shell)
    ↓
FloatingAssistantOrb._process_query()
    ├─ Check primitive_cache
    ├─ Route through tribunal (IPC to Core-4)
    ├─ Query Ollama LLM (http://127.0.0.1:11434/api/generate)
    ├─ Generate response text
    └─ Synthesize audio (Kokoro WSL or ACP 3.0)
    ↓
build_voice_payload()
    ├─ Voice audio generation
    ├─ Audio vault storage (substrate.db)
    └─ Metadata packaging
    ↓
emit_spoken_text() → IPC: speak_result
    ↓
Electron Renderer
    ↓
Audio playback + UI update
```

---

---

## Current Runtime Status

| Component | Status | Action Required |
|-----------|--------|------------------|
| R substrate | ✅ Back online | Ensure mounted before WSL |
| WSL | ✅ Healthy | Add env vars to `~/.bashrc` |
| Docker | ✅ Working | Later: confirm auto-start |
| Cloudflare tunnel | ✅ Working | Later: make systemd persistent |
| Ollama | ✅ Working in WSL | Lock primary to `/mnt/r`, keep fallback |
| Qwen 2.5 3B | ✅ Installed | Confirm runtime uses `/mnt/r` copy |
| CP 3.0 | 🔧 Path-dependent | Set `CP3_ROOT=/mnt/r/cochlear_processor_3.0` |
| Desktop ORB | 🔧 Needs path reconnection | Point mesh/cache/vault paths to `/mnt/r` |
| WebSocket/perf endpoints | ⚠️ Stubbed | Leave for later (not critical) |

---

## Verification Status

✅ **Verified Endpoints:**
- POST /api/v1/tribunal
- GET /api/v1/health
- Ollama /api/tags
- Ollama /api/generate

⚠️ **Stubbed/Planned (Not Critical Now):**
- WS /ws/orb_assistant (mock server planned)
- HTTP /api/orb/performance (not implemented)
- Kokoro TTS endpoints (external, handled by fallback)

✅ **Working Infrastructure:**
- Electron IPC channels
- Python bridge stdin/stdout
- Substrate SQLite database
- Audio vault caching
- R substrate remount
- Ollama model persistence

