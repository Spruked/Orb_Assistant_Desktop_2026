# Performance pass - 2026-10-20

Symptom: GPU about 3%, CPU about 99% on an i5-3470 (4 cores, no AVX2). Findings and changes:

| Cause | Change |
| --- | --- |
| 3D overlay (Three.js canvas spanning the whole virtual desktop) | **Removed**; back to the 2D orb. `orb-three-scene.js` and `electron/src/vendor/` deleted |
| Cursor forwarded about 60 times a second | Sent only when it moved, at most about 8 per second (`ORB_CURSOR_PYTHON_MIN_INTERVAL_MS` 125), 2 s idle refresh |
| EGF tensor field stepped per cursor sample (about 80 ms CPU per step) | Throttled to one step per 500 ms (`ORB_EGF_MIN_STEP_MS`) |
| Presence ran a full cognition pass every 2.8 s | Emits only on a meaningful change, plus a 30 s heartbeat |
| `cursor_move` flooded command history | Exempt from lifecycle recording |

Measured afterwards: Electron about 0.5% CPU. The Python ORB process is still about 22% of all cores at idle
(cali_skg retrieval and learning loop, HTTP health probes, startup imports) - **open**.

Guards: `electron/main/cpu-budget.test.js`, `electron/src/test_presence_budget.py`.
