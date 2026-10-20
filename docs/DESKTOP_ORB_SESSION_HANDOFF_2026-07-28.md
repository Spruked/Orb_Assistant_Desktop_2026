# Desktop ORB Session Handoff - 2026-07-28

## Scope

Active checkout:

```text
R:\Orb_Assistant_Desktop
```

Current target architecture:

```text
VS Code -> Desktop ORB -> Windows llama.cpp -> CUDA RTX 3050 -> Qwen2.5-1.5B-Instruct Q4_K_M
```

The Desktop ORB remains local-first. OpenAI or other external APIs are optional only. Qwen Code is allowed as a local tool worker for diagnostics, repair planning, verification, and MORB jobs, not as the shipped Desktop ORB conversation runtime.

## Confirmed Runtime Anchors

- Windows llama.cpp server path:
  `C:\Users\bryan\Downloads\llama-b10107-bin-win-cuda-13.3-x64\llama-server.exe`
- Windows llama.cpp endpoint:
  `http://127.0.0.1:40343`
- Working model endpoint:
  `http://127.0.0.1:40343/v1/models`
- Working chat endpoint:
  `http://127.0.0.1:40343/v1/chat/completions`
- Model:
  `Qwen/Qwen2.5-1.5B-Instruct-GGUF:Q4_K_M`
- Primary TTS:
  `http://127.0.0.1:9880`
- Primary TTS policy:
  Qwen TTS first, Kokoro only as backup, never Browser ORB TTS.

## Completed Today

### Local llama.cpp / Qwen Runtime

- Preserved the Windows CUDA llama.cpp route.
- Did not switch to WSL llama.cpp, Docker, Ollama, OpenAI, or another model runtime.
- Preserved the confirmed local model identity and endpoint contract.

### Qwen TTS / Voice Direction

- Confirmed Qwen TTS service anchor:
  `http://127.0.0.1:9880`.
- Established policy that startup greeting should warm up the voice system for later conversation.
- Established policy that Qwen TTS is primary and Kokoro is fallback only.
- Remaining proof needed: full Desktop ORB `TTSClient.speak()` path with measured latency, fallback state, and render state while speaking.

### Docking / Deployment / Activation

- DockStation flow direction was corrected:
  Desktop ORB should start docked.
- Deployment and activation belong to DockStation buttons.
- The dock should contain the real orb, not a silver placeholder replacement.
- When the orb is deployed out of the dock, the dock block should no longer show a duplicate orb.
- Remaining proof needed: visual/startup verification that the real orb is docked, deploys from DockStation, activates, and does not show a duplicate placeholder.

### Motion Behavior

- Motion doctrine established:
  slow, deliberate, periodic movement.
- ORB should rest in a spot between moves.
- ORB must stop moving while speaking.
- ORB should not be cursor-tethered.
- ORB should prefer the monitor where the cursor is currently located, while still being able to traverse all three monitors.
- Added renderer motion telemetry in `electron/src/orb-renderer.js` for proof:
  logs current x/y, monitor id, display count, and motion state.
- Remaining proof needed: visual multi-monitor confirmation after DockStation deployment/activation.

### Listening / Wake Behavior

- Expected wake name:
  `Cali`.
- ORB must respond to being called.
- ORB must also remain clickable as a fallback when speech recognition is unavailable.
- DockStation listening indicator was corrected so transient mic-idle events do not force the DockStation to show listening as off.
- Remaining proof needed: live speech recognition capture, wake-name response, and clickable fallback test.

### OCR / Tesseract

- Confirmed no usable R-drive Tesseract install was wired before this pass.
- Copied existing Windows Tesseract into the Desktop ORB repo-local tool area:
  `R:\Orb_Assistant_Desktop\tools\tesseract`
- Wired:
  `ORB_TESSERACT_BIN`
  and
  `TESSDATA_PREFIX`
  in `orb-instance.local.ps1`.
- Updated `mcp\orb_desktop_mcp\orb_desktop\desktop_orchestrator.py` so OCR prefers native Windows Tesseract before WSL fallback.
- Verified native Tesseract version and `eng.traineddata`.
- Verified actual OCR against a generated proof image:
  `ORB OCR PROOF 40343`
- Important Git note:
  `tools\tesseract\` contains binaries and should not be committed to GitHub unless explicitly approved.
- Product packaging note:
  Tesseract is a necessary Desktop ORB perception dependency. It should stay out of normal source commits, but a future shipped Desktop ORB download or installer should include or provision a known-good Windows Tesseract package, language data, and environment wiring in a controlled form.

### MORB Deployment

- MORB deployment cardinality now follows the prime-number invariant:
  allowed counts are `2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31`.
- Never deploy one MORB.
- Never deploy a non-prime MORB count.
- Runtime normalizes:
  `1 -> 2`, composite counts upward to the next supported prime, above max to `31`.
- DockStation MORB selector was aligned to prime counts.
- MORBs are reserved for research, diagnostics, scan work, repair planning, and verification.

### Orb Weaver / Diagnostics Boundary

- Desktop ORB should not perform the heavy diagnostic scans itself.
- Orb Weaver performs scans and writes results into Desktop ORB result surfaces.
- Desktop ORB presents, gates, supervises, and can deploy MORBs.
- Added/updated result and deployment contracts:
  - `docs\MORB_RESEARCH_DIAGNOSTIC_DEPLOYMENT_CONTRACT.md`
  - `docs\orbweaver_desktop_handoff.manifest.json`
  - `docs\orbweaver_diagnostic_result.schema.json`

### Vault / Mesh Direction

- One vault per repo.
- One shared source-of-truth vault in the R-drive substrate.
- Orb Mesh is where ORBs write non-personal operational facts.
- Desktop ORB should not duplicate the R-substrate shared truth vault.

### Pointer / TAMP Foundation

- Desktop pointer logic is on-demand TAMP, not sitemap navigation.
- Added/updated:
  - `docs\TAMP_ON_DEMAND_POINTER_CONTRACT.md`
  - `mcp\orb_desktop_mcp\orb_pointer\README.md`
- Pointer actions allowed automatically:
  `observe`, `hover_context`, `point_at`, `explain`, `dismiss`.
- Side-effect actions require operator review:
  `select`, `open`, `operator_override`.
- Pointer runtime must prefer virtual desktop coordinates.
- Pointer must not click, type, submit, purchase, delete, open, or select without explicit approval.

### Baseline Reference Maps

- Added:
  `docs\BASELINE_REFERENCE_MAPS_CONTRACT.md`
- Added schema:
  `mcp\orb_desktop_mcp\orb_pointer\baseline_map.schema.json`
- Added seed maps:
  `mcp\orb_desktop_mcp\orb_pointer\baseline_maps\windows_baseline_reference_maps.json`
- Baseline maps cover:
  browsers, File Explorer, Settings, common Windows dialogs.
- Baseline maps are recovery scaffolds only.
- They are not action plans and cannot override failed live observation.

### Desktop Scene Sweep / Virtual LiDAR Sweep

- Added:
  `docs\DESKTOP_SCENE_SWEEP_PERCEPTION_CONTRACT.md`
- Added schema:
  `mcp\orb_desktop_mcp\orb_pointer\observation_snapshot.schema.json`
- Defined Desktop Scene Sweep as the software perception pass:

```text
screen capture
-> monitor/window geometry
-> UI Automation
-> browser DOM when available
-> targeted Tesseract OCR
-> visual object recognition
-> scene understanding
-> TAMP planning
```

- Defined `VisualSceneRecognizer` as the component that classifies visible objects and controls.
- Defined `ObservationSnapshot` as the temporary task-scoped scene map.
- Confirmed physical LiDAR is not required for Desktop ORB screen navigation.

### Camera Perception Doctrine

- Camera is a separate sensor from desktop observation.
- Camera access requires explicit permission.
- No camera activation at startup.
- No hidden/background recording.
- Visible camera-active indicator is required.
- Camera capture should stop when the approved task ends.
- No saving images/video or face identification unless separately approved.

## Validation Completed

- `node --check electron/src/orb-renderer.js`
- `node --check electron/src/ui/orb-dock-station.bundle.js`
- `python -m py_compile electron/src/floating_assistant_orb.py electron/src/audio_runtime.py`
- Native Tesseract version check passed.
- Native Tesseract language data check passed.
- Native OCR proof returned expected text:
  `ORB OCR PROOF 40343`
- Baseline map JSON validation passed.

## Still Left To Prove

### Startup / DockStation

- Launch from the VS Code integrated PowerShell terminal.
- Confirm ORB starts docked.
- Confirm DockStation deploy button releases the real orb.
- Confirm activation button activates the orb.
- Confirm no duplicate silver placeholder remains after deployment.

### Voice

- Confirm greeting plays at startup.
- Confirm greeting warms up voice path without blocking rendering.
- Measure Qwen TTS startup and response latency.
- Confirm Qwen TTS primary path is used.
- Confirm Kokoro fallback does not trigger during normal Qwen success.
- Confirm speaking state stops ORB motion.
- Confirm renderer remains visible while speaking.

### Hearing

- Confirm microphone pipeline is active.
- Confirm DockStation listening indicator reflects actual availability.
- Confirm wake name `Cali` works.
- Confirm click fallback works when voice recognition fails.

### Three-Monitor Motion

- Visually confirm traversal across all three monitors.
- Confirm movement is slow and deliberate.
- Confirm ORB rests between moves.
- Confirm ORB follows the monitor where the cursor is located without being tethered to the cursor.
- Confirm ORB stops immediately while speaking.

### Pointer / TAMP Runtime

- Implement live `DesktopSceneSweep` execution.
- Implement `VisualSceneRecognizer`.
- Implement `ObservationSnapshot` generation.
- Implement `PointerTargetResolver` over OCR, UI Automation, DOM, visual object candidates, and baseline map recovery.
- Implement safe pointer pathing around blocked regions and ORB self-obstruction.
- Verify point-at behavior in:
  Chrome, Edge, Firefox, File Explorer, Settings, common Windows dialogs.

### Orb Weaver / MORB Integration

- Pull the Orb Weaver repository changes into the relevant checkout.
- Align Orb Weaver diagnostic output with:
  `docs\orbweaver_diagnostic_result.schema.json`
- Wire deployed MORBs to write results into Desktop ORB result surfaces.
- Verify MORB deployment uses prime counts only.
- Verify Qwen Code can be invoked as a local diagnostic/repair planning tool for MORBs.

### Git / Repository Hygiene

- Review current uncommitted changes.
- Avoid committing `.orb-assistant-desktop\` runtime cache files.
- Avoid committing `tools\tesseract\` binaries unless explicitly approved.
- Commit source/contracts/schemas only after validation.
- Push Desktop ORB changes to GitHub only after the runtime proof pass or explicit approval to push contract work first.

## High-Priority Next Command Set

```powershell
cd R:\Orb_Assistant_Desktop
python -m json.tool mcp\orb_desktop_mcp\orb_pointer\observation_snapshot.schema.json > $null
python -m json.tool mcp\orb_desktop_mcp\orb_pointer\baseline_map.schema.json > $null
python -m json.tool mcp\orb_desktop_mcp\orb_pointer\baseline_maps\windows_baseline_reference_maps.json > $null
python -m json.tool docs\orbweaver_desktop_handoff.manifest.json > $null
node --check electron\src\orb-renderer.js
node --check electron\src\ui\orb-dock-station.bundle.js
```

Then run:

```powershell
.\launch_desktop_orb.ps1
```

Production proof should capture:

- `/v1/models` response from `40343`.
- `/v1/chat/completions` response from `40343`.
- Qwen TTS WAV/RIFF response from `9880`.
- Docked startup.
- Deploy and activate from DockStation.
- Greeting playback.
- Wake-name response to `Cali`.
- Multi-monitor motion telemetry and visual confirmation.
- Stop-motion-while-speaking confirmation.
