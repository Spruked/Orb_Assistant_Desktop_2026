# Memory Architecture - single source of truth

Status: integrated 2026-10-20. Verified by `electron/src/test_orb_memory.py` (20 tests) and the A.I.M.S.
suite (17 tests, 2 skipped for the optional GraphQLite backend). The live 3D overlay was not yet inspected
when this was written (the ORB starts docked; see "Verification state").

## The rule

The Desktop ORB has exactly one memory: **A.I.M.S.**, installed inside the **Vault Logic System** framework.
Nothing else in the ORB persists memory. A second copy of memory is a defect.

```text
Desktop ORB (Electron + Python)
  electron/main/legacy-observer.js   forwards record/observe calls over the bridge (no files written)
  electron/src/orb_memory.py         OrbMemory: the ORB's one memory interface
  electron/src/vault_system/manager.py            VaultManager facade (same interface, AIMS-backed)
  electron/src/caleon_presence/core/memory_learner.py   SystemBehaviorLearner (AIMS-backed)
        |
        v
vault_logic_system/memory/provider.py       get_memory(): one instance, one store path per process
vault_logic_system/memory/aims_binding.yaml binding + tier mapping
        |
        v
vault_logic_system/memory/aims/             A.I.M.S. (vendored from github.com/Spruked/AIMS, commit d72a3ce)
```

Persistent data lives outside the repository: `ORB_AIMS_STORE_PATH`
(`R:\Substrate_Vault_R\vaults\orb_assistant_desktop\aims`, set in `orb-instance.local.ps1`).

## Tiers and what goes where

| Tier | Holds | Properties |
|---|---|---|
| Short-term cache | cursor/presence habits, vault hot-path writes, pending user turns, voice and status observations | volatile, vivacity-decayed, capacity-capped, never written to the ledger |
| Long-term ledger | completed interactions, promoted material | append-only, SHA-256 hash chain, Glyph chain, tri-timestamped, single-writer lock |
| Vault / SKG | A Priori and A Posteriori atoms distilled from ledger entries | rebuilt by replay; reinforcement and retirement are recorded as events |

Promotion: a short-term item touched 3+ times while still vivid is a candidate. `OrbMemory.maintain()` (run by
the lifecycle heartbeat, rate-limited) commits candidates to the ledger and creates a vault atom. While the
pattern stays active the atom is reinforced; sustained recurrence makes it ACTIVE (trusted). Stale items simply
decay. This replaces the old behaviour-learner decay/promotion code.

## What was replaced

| Old store | Replaced by |
|---|---|
| `electron/main/legacy-observer.js` JSONL + node files under `R:\substrate\spruk_legacy_orb\memory_graph` | forwarder to `OrbMemory` (old data left in place, no longer read or written) |
| `VaultManager` file-per-hash store (`posteriori/*.json`) | `VaultManager` facade over `OrbMemory` (old files left in place, ignored) |
| `SystemBehaviorLearner` sqlite (`behavior_learner.db`) | AIMS-backed learner with the same public methods (old db left in place, ignored) |
| `record_runtime_voice_observation` (legacy substrate module) | short-term voice observations |
| Vault Logic System template placeholders (`memory/matrix_store.yaml`, `memory/domains/*.json`) | removed; `aims_binding.yaml` |

## Still to migrate (other stores that exist today)

These were not part of this pass and remain separate stores until moved:
`ShortTermResearchCache` (`CALI_System/memory/short_term_cache.db`), `ResearchEventVault`
(`ORB_RESEARCH_VAULT_ROOT`), `CaliNotes` (`CALI_System/notes`), `CALI_System/memory/decisions.jsonl`,
the dock transaction and conversation proof JSONL writers in `electron/main/main.js`,
and the Correspondence Engine's in-memory vault (`.orb-runtime/correspondence_engine`).

## Responsiveness

* Cursor and presence hot paths take only the short-term lock.
* A.I.M.S. re-verifies the whole ledger on every write (about 21 ms at the start, about 59 ms at 200 entries,
  growing linearly), so completed interactions are committed by a background writer thread.
  A test proves a 1 s ledger stall does not slow the hot path.
* Memory failure never raises into cognition: `OrbMemory` degrades to a bounded in-process fallback and reports
  `available: false` (visible in `get_status` under `memory`).

## Bridge messages

`memory_record` (Electron to Python, fire-and-forget, no lifecycle events), `memory_recall`, `memory_status`.
Results come back as `memory_recall_result` and `memory_status_result`.

## Known limits

* Security mode is `visual` (zero-secret hash chain: detects corruption, not a determined forger) until an
  authenticated keyring is configured (`AIMS_GLYPH_KEYS_FILE` / `AIMS_GLYPH_KEY_ID`).
* One process may write the store (cross-process writer lock). A second ORB Python process degrades to fallback.
* The ledger write cost grows with ledger length; consider incremental verification in A.I.M.S. before the
  ledger reaches thousands of entries (see `vault_logic_system/memory/aims/HARDENING_CONTRACT.md`).
* No persistence of short-term memory across restarts (by design).

## Verification state

* `python -B -m unittest test_orb_memory -v` from `electron/src`: 20 passed.
* A.I.M.S. tests from `vault_logic_system/memory/aims`: 17 passed, 2 skipped.
* ORB launched 2026-10-20 02:30 local: the Python ORB created the store at the path above (ledgers, indexes,
  retrieval ledger) and ran a maintenance cycle with no errors in the launcher output.
* Not yet verified: the 2D overlay after Launch from the Dock, interactions flowing through `memory_record`
  during a live chat, and memory behaviour over a long session.
