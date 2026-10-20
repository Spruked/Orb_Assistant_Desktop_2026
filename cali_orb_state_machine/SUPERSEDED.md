# Superseded by electron/src

This folder is the original drop-in package for the four-layer state machine. The live implementation is in `electron/src`
(`orb_state_machine.py`, `orb_lifecycle.py`, `orb_command_router.py`, `orb_behavior_runtime.py`) and has diverged from these copies.
Changes made on 2026-10-20 (runtime summaries, physical motion reporting, cursor no longer a motion target, `motion_report`) exist only in
`electron/src`. `FloatingOrb.jsx` and the `*_INTEGRATION.py` / `orb-bridge_UPDATED.js` files here are not used by the running ORB.

Do not edit these copies; see `docs/THREE_RUNTIMES.md`.
