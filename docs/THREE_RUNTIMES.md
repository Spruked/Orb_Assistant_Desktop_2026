# The three runtimes

The Desktop ORB has three runtimes. They are managed independently and coordinate through typed events and
the state machine, so a slow LLM cannot freeze movement, a speech problem cannot bypass governance, and one
runtime failing cannot hide another.

| Runtime | Owns | State-machine domains |
|---|---|---|
| **Motion** | what the ORB physically does: window and display placement, cursor avoidance, patrol, multi-monitor movement, docking, the 2D body and its visual state | `motion` |
| **Communications** | how the ORB listens, speaks and communicates: microphone, STT, TTS, playback, captions, speech events | `listening`, `voice` |
| **Cognition / Governance** | how the ORB understands, decides and controls what is authorized: reasoning, memory (A.I.M.S.), the Core Four, TPC, Correspondence, Doctrine, owner authorization, approved actions and the MCP execution arm | `cognition`, `command`, `presence` |

`system` is host bookkeeping and belongs to none of them. `CALIStateMachine.RUNTIMES` encodes this mapping and
`get_runtime_summary()` returns the independent health of each runtime. It appears in `get_status` and
`get_full_status` under `runtimes`.

## Module ownership (live code)

**Motion**
- `electron/src/orb-renderer.js` (movement policy, avoidance, patrol, dock transition, speaking hold),
  `orb-presence-bootstrap.js` (cursor-avoidance policy)
- `electron/main/main.js` (overlay windows, displays, click-through, topmost, dock transitions), `preload.js`
- Python side: the state machine `motion` domain. Requested motion (`set_motion`) is the *desired* layer; what the ORB is actually
  doing is the *runtime* layer, reported by the renderer (see "Motion contract").

**Communications**
- `electron/src/audio_runtime.py`, `tts_client.py`, `voice_payload.py`, `voice_engine_manager.py` (overlaps `tts_client.py`; decide
  which is live), `orb_command_router.py` (`speak`, `listen_once`, `set_listening`), `scripts/Start-OrbVoiceStack.ps1`
- Renderer audio playback and the speech bubble are communications logic that currently sit in `orb-renderer.js`.

**Cognition / Governance**
- `electron/src/cognitive_inference.py` (`AlignmentLayer`), `orb_controller.py` (Core Four, HLSF, EGF), `floating_assistant_orb.py`
  (routing), `cali_skg.py` (creates the state machine), `orb_memory.py` + `vault_logic_system/memory` (A.I.M.S.)
- `mcp/orb_desktop_mcp`: `orb_cognition/tpc_core.py` (action planner), `orb_safety/safety_guard.py`, `orb_morbs/` (verification),
  `orb_substrate/`, `orb_llm/`. The desktop actuators (`orb_desktop/`, `orb_browser/`) are the **execution arm** of governance:
  they are consequential and must only run with owner authorization. `orb_pointer/` resolves targets and hands a pointing request to
  Motion.
- Doctrine, TPC specification and the Correspondence Engine: see `mcp/orb_desktop_mcp/orb_cognition/` and
  `.orb-runtime/correspondence_engine` (not yet wired into the live path).

## Contracts between runtimes

An event may inform another runtime without transferring authority.

| Contract | Producer -> consumer | Status |
|---|---|---|
| `motion_report` (mode, x, y, monitor_id, display_count, docked, speaking_hold) | renderer (or main, when docked) -> `orb:motion-report` IPC -> Python router -> state machine runtime layer | **wired 2026-10-20** |
| speech state (`listening_state`, `speech_pulse`, `speak_result`, `speech_heard`) | Python communications -> bridge -> renderer/Dock | wired |
| command lifecycle (`command_accepted/completed/failed`) | router -> bridge | emitted, **no consumer, not persisted** |
| `memory_record`, `memory_recall`, `memory_status` | Electron/Python -> `OrbMemory` | wired |
| pointing request (`point_at`, `hover_context`) | MCP pointer runtime -> Motion | **not wired** (`orb_pointer` is not imported; nothing consumes pointer actions) |
| authorized action request | Motion/Communications -> governance -> MCP actuators | **not enforced** (see audit) |

## Motion contract (wired)

The renderer owns physical motion. It sends `reportMotionState` (preload) -> `orb:motion-report` (main validates that the sender is an ORB
overlay window and passes only whitelisted scalar fields) -> `motion_report` (Python router, exempt from command lifecycle) ->
`CALIStateMachine.report_physical_motion`. While the ORB is docked there is no overlay, so the main process reports `docked`.

`get_runtime_summary()["motion"]` reports `ok`, `stale` (no report for 10 s), `unreported`, or `disabled`, with mode, position, monitor and
docked/speaking-hold flags. `process_cursor_movement` no longer marks the cursor as the motion target: the cursor is an input to cognition, and
the ORB's motion policy avoids it.

## Cursor input is telemetry, not a command

`cursor_move` (about two per second), `motion_report` and `memory_record` are exempt from the command lifecycle in `OrbCommandRouter`. As commands, cursor samples produced two bridge events each and pushed real commands out of the 100-entry command history within a minute.

## What is not wired yet

* Motion cannot be commanded from governance: `set_motion` only changes the desired layer, and the renderer does not read it.
* Pointer actions do not reach Motion; the pointer runtime is not imported.
* The state machine does not yet gate other runtimes on each other's state (for example holding motion while speaking is done inside the renderer).
* Owner authorization, IPC sender validation (other than the new channel), preload removal from local app windows and the MCP allowlist
  are still open: `docs/AUDIT_2026-10-20_AUTHORIZATION_AND_WIRING.md`.
* Communications playback logic lives in the renderer; moving it behind speech events is a later step.

## The `cali_orb_state_machine/` folder

That folder is the original drop-in package (state machine, lifecycle, router, behavior runtime, integration guides, a `FloatingOrb.jsx`
that is not loaded). The live copies are in `electron/src` and have diverged from it. Treat `electron/src` as the source of truth and the folder
as reference material.

Tests: `electron/src/test_runtimes.py` (18), including drift guards that fail if the renderer, preload, main process and state machine stop agreeing
on the motion contract.
