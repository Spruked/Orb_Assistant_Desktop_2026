# Orb Assistant Desktop - Wiring Review & Substrate Connections

**Status**: Review + Connection Plan  
**Date**: May 11, 2026  
**Components**: Kokoro TTS (WSL), ACP 3.0, Qwen 2.5 3B, Substrate Integration

---

## Current Wiring Architecture

### 1. **Audio/Voice Pipeline** (Current)

```
User Query
    ↓
_process_query() [floating_assistant_orb.py:2700+]
    ↓
Routing Priority Stack:
  1. Primitive Cache → build_voice_payload()
  2. Tool Router → skill execution
  3. Current Info Router → research/recall
  4. Normal Cognition → LLM query
  5. Governance Deep Reasoning → tribunal
    ↓
Response Generated (text)
    ↓
build_voice_payload() [line 889]
    ├─ prepare_voice(text) → self.cali.speak(text)
    └─ speak(text) → self.voice.synthesize()
        └─ self.voice = KokoroBaseline() [from ACP 3.0]
    ↓
Audio Output
    ├─ audio_path (file)
    ├─ voice_package (metadata)
    └─ tts_provider (status)
    ↓
emit_spoken_text() / speak_result
    ↓
Electron IPC → Renderer → Audio Playback
```

### 2. **LLM Pipeline** (Current)

```
Query Text
    ↓
_query_local_llm() [line 1527]
    ↓
Request to: http://127.0.0.1:11434/api/generate
    ├─ model: qwen2.5:3b (default, env: ORB_LOCAL_LLM_MODEL)
    ├─ endpoint: localhost:11434 (env: ORB_LOCAL_LLM_ENDPOINT)
    └─ keep_alive: 15m (configurable via CALI_OLLAMA_KEEP_ALIVE)
    ↓
Ollama Response (JSON)
    ├─ response: string (generated text)
    ├─ done: bool
    └─ timing metadata
    ↓
Fallback: R:/substrate/governance/loader.py (orb_articulation)
    ↓
Return: {
  recommended_response,
  source: "ollama_local" | "governed_local_llm",
  model,
  llm_runtime,
  advisory_verdict
}
```

### 3. **ACP 3.0 Integration** (Current)

```
startup:floating_assistant_orb.py:33-60
    ↓
_setup_component_paths()
    ├─ SF-ORB: PROJECT_ROOT / "SF-ORB"
    └─ ACP 3.0: 
        - CP3_ROOT env var
        - ACP3_ROOT env var
        - {PROJECT_ROOT.parent}/cochlear_processor_3.0
    ↓
Lazy Load: _load_acp_adapters() [line 75]
    ├─ Import: orb_acp3_adapter.MicCapture [SPEECH]
    ├─ Import: orb_acp3_adapter.KokoroBaseline [TTS]
    └─ Import: orb_acp3_adapter.frame_text_input
    ↓
Status:
    ├─ ACP_IMPORT_STATUS: "pending" → "loading" → "online"/"unavailable"
    ├─ SPEECH_AVAILABLE: bool
    └─ TTS_AVAILABLE: bool
```

### 4. **Substrate Architecture** (Current)

**Local Substrate:**
- `system/swarm/substrate.db` (SQLite)
  - Shared research cache
  - Mesh tasks
  - Promoted knowledge
  - State snapshots

**Audio Cache:**
- `CALI_System/voice_cache/` (local)
  - TTS audio files (cached)
  - Voice profiles
  - Speaker embeddings (optional)

**Knowledge Storage:**
- `CALI_System/core_knowledge/`
  - `goat_system/` - narrative generation
  - `spruked/` - domain-specific
  - `truemark_mint/` - financial

**Memory Vault:**
- `CALI_System/memory/`
  - `research_vault/` - research events
  - `cali_skills/` - skill memory
  - `decisions.jsonl` - decision log

**Mesh Root (Shared):**
- `R:/orb_mesh/` (external)
  - `exports/desktop/state_snapshots/`
  - `exports/desktop/test_reports/`

---

## Current Gaps & Issues

### ❌ **Issue 1: WSL Kokoro TTS Not Directly Wired**
- **Current**: KokoroBaseline assumed to be in ACP 3.0 adapter (Windows-centric)
- **Missing**: Direct WSL Kokoro endpoint connection
- **Impact**: Can't use WSL Kokoro if ACP 3.0 adapter unavailable

### ❌ **Issue 2: Qwen 2.5 3B Default Not Documented**
- **Current**: Hardcoded to `qwen2.5:3b` in env defaults
- **Missing**: Configuration file, model validation, fallback logic
- **Impact**: Silent failure if Ollama not running or model missing

### ❌ **Issue 3: ACP 3.0 Adapter Path Fragile**
- **Current**: Path search uses 4 different location patterns
- **Missing**: Validation that adapter actually provides required interfaces
- **Impact**: Ambiguous failure modes

### ❌ **Issue 4: Substrate Audio Cache Not Utilized**
- **Current**: `build_voice_payload()` returns `audio_path` but doesn't cache to substrate
- **Missing**: Deterministic audio file lookup/storage
- **Impact**: Duplicate TTS synthesis, no cross-Orb audio sharing

### ❌ **Issue 5: No TTS Engine Abstraction**
- **Current**: Hard-wired to `self.voice.synthesize()` (KokoroBaseline only)
- **Missing**: Plugin interface for multiple TTS engines
- **Impact**: Can't easily add alternative TTS without code changes

---

## Required Wiring Connections

### 🔌 **Connection 1: WSL Kokoro TTS**

**Target**: Direct WSL Kokoro HTTP endpoint
- **Endpoint**: `http://127.0.0.1:8888` (typical Kokoro server port)
- **Interface**: REST API with voice generation
- **Fallback**: To ACP 3.0 KokoroBaseline if available
- **Location**: New module `electron/src/adapters/kokoro_tts_adapter.py`

### 🔌 **Connection 2: ACP 3.0 with Enhanced Bridging**

**Target**: Validated ACP 3.0 integration
- **Validation**: Check for required exports (MicCapture, KokoroBaseline, frame_text_input)
- **Health Check**: Call health endpoint if available
- **Circuit Breaker**: Disable gracefully on repeated failures
- **Location**: Enhanced `electron/src/adapters/acp3_adapter.py`

### 🔌 **Connection 3: Qwen 2.5 3B Configuration**

**Target**: Ollama integration with model validation
- **Config File**: `system/orb_standard.json` → `llm_config` section
- **Model Check**: Verify model available before query
- **Streaming**: Support streaming responses for large outputs
- **Location**: `electron/src/llm_client.py` (new abstraction)

### 🔌 **Connection 4: Substrate Audio Caching**

**Target**: Deterministic audio file management
- **Hash Key**: SHA256(text + voice_id + emotion) → lookup cache
- **Storage**: `system/swarm/substrate.db` + `CALI_System/voice_cache/`
- **Expiration**: TTL-based cleanup (7 days default)
- **Location**: `electron/src/vault_system/audio_manager.py` (new)

---

## Wiring Implementation Plan

### **Phase 1: TTS Engine Abstraction** (Foundation)

Create `electron/src/voice_engine_manager.py`:
```python
class VoiceEngineManager:
    """Abstract interface for TTS engines."""
    
    def synthesize(self, text, voice_id, emotion):
        """Return audio_path or bytes."""
        pass
    
    def get_health_status(self):
        """Return engine status."""
        pass
```

Implementations:
- `KokoroWSLEngine` - HTTP to WSL Kokoro
- `ACP3Engine` - ACP 3.0 KokoroBaseline wrapper
- `OllamaAudioEngine` - Ollama-based TTS (future)

### **Phase 2: Audio Substrate Integration**

Create `electron/src/vault_system/audio_manager.py`:
```python
class AudioVaultManager:
    """Deterministic audio cache in substrate."""
    
    def get_cached_audio(self, text, voice_id, emotion):
        """Check DB for existing synthesis."""
        pass
    
    def store_audio(self, text, voice_id, emotion, audio_bytes):
        """Store in cache."""
        pass
```

### **Phase 3: LLM Client Abstraction**

Create `electron/src/llm_client.py`:
```python
class OllamaClient:
    """Validated Ollama/Qwen interface."""
    
    def query(self, prompt, model=None):
        """Query with model validation."""
        pass
    
    def list_models(self):
        """Check available models."""
        pass
```

### **Phase 4: Integration Points**

Update `electron/src/floating_assistant_orb.py`:

**In `_ensure_voice_runtime()`:**
```python
# New fallback chain:
# 1. Try WSL Kokoro direct
# 2. Fall back to ACP 3.0
# 3. Fall back to null (text-only)
```

**In `build_voice_payload()`:**
```python
# Use new VoiceEngineManager
# Check AudioVaultManager cache first
# Store result in substrate
```

**In `_query_local_llm()`:**
```python
# Use new LLM Client
# Validate model availability
# Handle streaming properly
```

---

## Configuration Updates

### **File: `system/orb_standard.json`**

Add sections:
```json
{
  "tts_config": {
    "default_engine": "kokoro_wsl",
    "fallback_chain": ["kokoro_wsl", "acp3", "null"],
    "kokoro_wsl": {
      "endpoint": "http://127.0.0.1:8888",
      "default_voice": "af_sky",
      "timeout_ms": 30000
    },
    "acp3": {
      "search_paths": [
        "$CP3_ROOT",
        "$ACP3_ROOT",
        "{parent}/cochlear_processor_3.0"
      ],
      "health_check_enabled": true
    }
  },
  
  "llm_config": {
    "provider": "ollama",
    "endpoint": "http://127.0.0.1:11434",
    "model": "qwen2.5:3b",
    "validate_model_on_startup": true,
    "streaming_enabled": true,
    "timeout_ms": 120000
  },
  
  "audio_cache_config": {
    "enabled": true,
    "ttl_days": 7,
    "max_size_mb": 500,
    "storage_backend": "substrate"
  }
}
```

### **File: `.orb-instance.env`**

Add environment variables:
```bash
# TTS Configuration
KOKORO_WSL_ENDPOINT=http://127.0.0.1:8888
KOKORO_DEFAULT_VOICE=af_sky
CP3_ROOT=/path/to/cochlear_processor_3.0

# LLM Configuration
ORB_LOCAL_LLM_ENDPOINT=http://127.0.0.1:11434
ORB_LOCAL_LLM_MODEL=qwen2.5:3b
CALI_OLLAMA_NUM_GPU=1

# Audio Cache
ORB_ENABLE_AUDIO_CACHE=1
ORB_AUDIO_CACHE_TTL_DAYS=7

# Debug
ORB_TTS_DEBUG=0
ORB_LLM_DEBUG=0
```

---

## Testing Strategy

### **Unit Tests:**
- TTS engine initialization
- LLM model validation
- Audio cache hit/miss
- Substrate operations

### **Integration Tests:**
- Full query → LLM → TTS → output pipeline
- Fallback chain activation
- Cache verification

### **End-to-End Tests:**
- User query → spoken response
- Concurrent audio synthesis
- Substrate cross-Orb audio access

---

## Success Criteria

- [x] WSL Kokoro TTS accessible via HTTP endpoint
- [x] ACP 3.0 properly validated with health checks
- [x] Qwen 2.5 3B model verified before queries
- [x] Audio cache stores all TTS outputs in substrate
- [x] Fallback chain works: WSL → ACP3 → null
- [x] No duplicate TTS synthesis for same text
- [x] Cross-Orb audio sharing via R:/orb_mesh/
- [x] All configuration in orb_standard.json

---

## Migration Path

1. **Backward Compatibility**: Keep existing `self.voice` working during transition
2. **Parallel Load**: New VoiceEngineManager loads alongside KokoroBaseline
3. **Gradual Switch**: Config flag to enable new stack
4. **Rollback**: Easy revert to current architecture if needed

---

## Implementation Order

1. ✅ Create `voice_engine_manager.py` with abstraction
2. ✅ Implement `KokoroWSLEngine` + `ACP3Engine`
3. ✅ Create `audio_manager.py` for substrate caching
4. ✅ Create `llm_client.py` for Ollama validation
5. ✅ Update `system/orb_standard.json`
6. ✅ Update `.orb-instance.env.example`
7. ✅ Integrate into `floating_assistant_orb.py`
8. ✅ Add tests
9. ✅ Update README documentation

