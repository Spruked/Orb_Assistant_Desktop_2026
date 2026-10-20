# Orb skins (2D)

The orb's appearance is data. Pick a preset, or make your own, from the Dock's **Skins** tab; the change appears on the
orb immediately and is remembered across restarts. The orb is the original 2D body: the 3D scene was removed on
2026-10-20 because it loaded the GPU and CPU too heavily on the target machine (RTX 3050 6 GB, i5-3470).

## Using it
* Click a preset card: Default (the live gradient), Brilliant Blue, Spruked, Cyber, Sunset, Forest, Neon, Cosmic, Fire,
  Ice, Plasma, Obsidian, Rose Gold (13 in all).
* Or use the custom editor: four color pickers (core, mid, edge, deep) and Apply. Reset returns to the default.

## How it works
| Piece | File |
| --- | --- |
| Presets (data) | `electron/src/skins/orb-skins.json` |
| Validation + persistence | `electron/main/orb-appearance.js` (`<userData>/skins/appearance.json`) |
| IPC (sender-checked) | `electron/main/main.js`: `orb:skins-list`, `orb:skin-current`, `orb:skin-apply`, `orb:skin-custom`, `orb:skin-reset`; broadcast `orb:appearance-changed` |
| Bridge | `electron/main/preload.js` |
| 2D application | `electron/src/orb-renderer.js`: `customSkinGradient(colors)`, `setSkinConfig({colorScheme:'custom', colors})` |
| Dock UI | `electron/src/ui/orb-dock-station-substrate.js` (Skins tab) |

A skin is `{id, name, description, gradient: {core, mid, edge, deep}}`; `gradient` is null only for `default`. Colors
must be `#rrggbb`; they are validated in the main process and again in the renderer (`HEX_COLOR`) so no CSS can be injected.
A corrupt settings file falls back to the default.

## Tests
`cd electron && node --test main/orb-appearance.test.js main/cpu-budget.test.js` (16 pass), including a guard that no
Three.js code or file remains.

## Not verified
* Each preset's look on screen; the Dock bundle itself still logs `setActiveOrbSkinUrl is not defined` (pre-existing, bundle cannot be rebuilt: esbuild missing).
