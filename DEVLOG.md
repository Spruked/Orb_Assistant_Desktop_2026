# DEVLOG

## 2026-10-20 | Single memory (A.I.M.S. in the Vault Logic System), audit, trees, docs

### Completed
- Vendored `Spruked/AIMS` (commit d72a3ce) and `Spruked/Vault-Logic-System-Template` (commit 963f621) into this
  repo; removed their `.git` metadata; renamed the framework folder to `vault_logic_system`; installed A.I.M.S. at
  `vault_logic_system/memory/aims`.
- Made A.I.M.S. the single memory authority: `vault_logic_system/memory/provider.py` + `aims_binding.yaml`; removed the
  template's placeholder matrix store and domain files.
- Added `electron/src/orb_memory.py` (short-term cache, background ledger writer, promotion/reinforcement, recall,
  status). Replaced the internals of `VaultManager`, `SystemBehaviorLearner` and `legacy-observer.js` (now a bridge
  forwarder). Added bridge messages `memory_record`, `memory_recall`, `memory_status`; heartbeat runs maintenance;
  `get_status` reports memory.
- Tests: `electron/src/test_orb_memory.py` (20 pass); A.I.M.S. suite 17 pass / 2 skipped.
- ORB relaunched on this desktop; the store was created at `R:\Substrate_Vault_R\vaults\orb_assistant_desktop\aims`.
- Added `scripts/generate_trees.py`; regenerated `tree.txt`; `structure tree.txt` replaced by `structure_tree.txt`.
- Correspondence Engine: fixed the provenance accessor and predicate extraction, added regression and
  characterization tests (21 pass).
- Audit of authorization, endpoints and wiring recorded in `docs/AUDIT_2026-10-20_AUTHORIZATION_AND_WIRING.md`.

- HLSF mirror: verified live data end to end (21 snapshots in 45 s from the running engine). Snapshots now carry
  `live/source/reason/seq/ts` and report 0/0 thresholds when no engine is attached (no more fake 800/650); node hashing is
  stable across processes; added the missing `EpistemicGravityBridge.get_visual_state()`. Tests: `test_hlsf_snapshot.py` (10).
  Open: hash-derived coordinates carry no spatial meaning; density tracks stimulus volume; Dock cannot show a stale feed
  without a bundle rebuild (esbuild not installed).

- Three-runtime wiring (Motion, Communications, Cognition/Governance): `CALIStateMachine.RUNTIMES` and `get_runtime_summary()`
  (independent health, exposed as `runtimes` in status); renderer now reports physical motion (`reportMotionState` ->
  `orb:motion-report` -> `motion_report` -> state machine), main reports `docked`; cursor processing no longer sets a CURSOR motion target.
  Tests: `test_runtimes.py` (18, with contract drift guards). Map and gaps: `docs/THREE_RUNTIMES.md`. `cali_orb_state_machine/` marked superseded.
  Not wired: governance->motion commands, pointer->motion, authorization gate in front of the MCP actuators.

- LLM: switched to llama.cpp + DeepSeek-R1-Distill-Qwen-7B Q4_K_M (auto GPU/CPU fit, ctx 8192). Per-request thinking budget (0 = direct, 512 deep), reasoning stripped before speech, launcher health check and extra-args support, longer timeout. About 8-9 tok/s, 1.6 s direct, about 20 s with thinking. Tests: `test_llm_reasoning.py` (16). `docs/LLM_RUNTIME.md`.
- Skin changer: Dock **Skins** tab, validated skin store (`orb-appearance.js`), sender-checked IPC, 2D gradient skins, 13 presets (from the spruked.com orb). Tests: `orb-appearance.test.js` (13). `docs/ORB_SKINS.md`.
- EGF enabled (`ORB_ENABLE_EGF_TENSOR=1`): the field runs (32^3, about 80 ms per cursor sample on CPU); the Dock EGF panel still only shows status pills.

### Not done / open
- Stores still to migrate into A.I.M.S.: research short-term cache, research event vault, notes, decisions log,
  dock transaction/proof JSONL, Correspondence Engine vault.
- No push: this folder is not a git repository yet and no target repo was chosen.
- Owner authorization, IPC sender validation, preload removal from local app windows, MCP allowlist: not applied.
- Live overlay inspection pending (ORB starts docked; Launch from the Dock deploys it).
- A.I.M.S. re-verifies the full ledger on each write; write cost grows with ledger length.

- 3D removed; back to the 2D orb (GPU/CPU load). Skin changer retargeted to 2D gradients (13 presets, four-color editor).
- CPU fixes: cursor 60 Hz to <=8 Hz and only when moved, EGF step 500 ms, presence gated on change + 30 s heartbeat, cursor_move not recorded.
  Python ORB still ~22% idle CPU (open). See docs/PERFORMANCE_2026-10-20.md.
- LLM profiles: default qwen1.5b (shares GPU with voice), deepseek7b on demand. Voice deferred to the other machine.
- Tests: test_orb_memory 20, test_hlsf_snapshot 13, test_runtimes 18, test_llm_reasoning 19, test_presence_budget 7, node 16, AIMS 17 (+2 skipped), Correspondence 21.
- Pushed to Spruked/Orb_Assistant_Desktop_2026 (large local assets, archive and private runtime data are git-ignored).


## 2026-06-19/20 | ORB voice, MCP, MORBS, motion, DockStation routing

### Completed
- Wired desktop MCP to moved service path: `R:\R_Drive_Substrate\Services\orb_desktop_mcp`.
- Added Services-first MCP resolver in `electron/main/orb-desktop-mcp-client.js`.
- Added DockStation MCP/MORBS status and controls.
- Verified Electron MCP client:
  - initialized from Services MCP path
  - 24 tools listed
  - MORB/session/substrate tools working
  - local LLM detected as `ollama / llama3.2:1b`
- Patched MCP local LLM adapter to prefer configured `llama3.2:1b`.
- Rewired WSL voice/ears:
  - Qwen TTS: `http://127.0.0.1:9880/speak`
  - faster-whisper STT: `http://127.0.0.1:9000/stt`
- Verified Qwen generated WAV audio and faster-whisper returned a transcript.
- Updated voice stack startup script for WSL Qwen/faster-whisper service ports.
- Updated DockStation service registry to match live enabled endpoints.
- Patched ORB motion env and renderer defaults so cursor-follow is default-on and assist-only is default-off.
- Added deterministic chat routing in `electron/main/main.js`:
  - `/mcp status`
  - `/mcp tools`
  - `/mcp enable`
  - `/mcp disable`
  - `/mcp call <tool> [json_args]`
  - `/research <query>`
  - natural desktop/browser commands route to MCP `orb_control`
  - natural research commands route to existing ORB research bridge

### Verified
- `node --check electron/main/main.js`
- `node --check electron/main/orb-desktop-mcp-client.js`
- `node --check electron/src/orb-renderer.js`
- `node --check electron/src/ui/orb-dock-station.bundle.js`
- Python compile for audio runtime and MCP LLM/MORB surfaces.
- HTTP probes:
  - `21100/api/v1/readiness` 200
  - `19000/api/health` 200
  - `21000/health` 200
  - `11434/api/tags` 200
  - `9880/health` 200
  - `9000/docs` 200

### Files Changed
- `orb-instance.local.ps1`
- `scripts/Start-OrbVoiceStack.ps1`
- `electron/main/main.js`
- `electron/main/orb-desktop-mcp-client.js`
- `electron/src/audio_runtime.py`
- `electron/src/orb-renderer.js`
- `electron/src/ui/orb-dock-station.jsx`
- `electron/src/ui/orb-dock-station.bundle.js`
- `electron/CALI_System/core_knowledge/spruked/services.json`
- `R:\R_Drive_Substrate\Services\orb_desktop_mcp\orb_llm\local_llm.py`

### Still Left
- Restart ORB and verify renderer motion patch in live logs.
- Runtime-test Dock chat routing:
  - `/mcp status`
  - `/mcp tools`
  - `/mcp enable`
  - `open chrome`
  - `/research <query>`
- Resolve Prime Mail mismatch: desktop opens sparse `R:/email_client/emails.db` client instead of the full built mail client.
- Resolve degraded readiness if needed by restoring shared mesh manifests under `R:\R_Drive_Substrate\orb_mesh\manifests`.

