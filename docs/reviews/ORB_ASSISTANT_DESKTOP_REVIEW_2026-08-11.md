# Orb Assistant Desktop Review - 2026-08-11

## Scope

- Folder reviewed: `R:\Orb_Assistant_Desktop`
- Canonical substrate vault reference: `R:\Substrate_Vault_R`
- CRM/Mail work was not touched.

## Vault Consolidation

Canonical Orb vault home:

- `R:\Substrate_Vault_R\vaults\orb_assistant_desktop`

Moved data vaults:

- `R:\Orb_Assistant_Desktop\vault_system` -> `R:\Substrate_Vault_R\vaults\orb_assistant_desktop\root_vault_system`
- `R:\Orb_Assistant_Desktop\Vault_System_1.0` -> `R:\Substrate_Vault_R\vaults\orb_assistant_desktop\legacy_template_vault_system_1_0`
- `R:\Orb_Assistant_Desktop\system\vault_system` -> `R:\Substrate_Vault_R\vaults\orb_assistant_desktop\system_vault_system`
- `R:\Orb_Assistant_Desktop\electron\vault_system` -> `R:\Substrate_Vault_R\vaults\orb_assistant_desktop\electron_runtime_vault_system`
- `R:\Orb_Assistant_Desktop\CALI_System\memory\research_vault` -> `R:\Substrate_Vault_R\vaults\orb_assistant_desktop\cali_memory_research_vault`
- `R:\Orb_Assistant_Desktop\electron\CALI_System\memory\research_vault` -> `R:\Substrate_Vault_R\vaults\orb_assistant_desktop\electron_cali_memory_research_vault`
- `R:\Orb_Assistant_Desktop\electron\src\logic_seeds\deductive_validator\vault\observation_log.jsonl` -> `R:\Substrate_Vault_R\vaults\orb_assistant_desktop\logic_seed_deductive_validator_vault\observation_log.jsonl`

Manifest:

- `R:\Substrate_Vault_R\vaults\orb_assistant_desktop\ORB_ASSISTANT_VAULT_MIGRATION_MANIFEST.csv`
- `R:\Substrate_Vault_R\vaults\orb_assistant_desktop\ORB_ASSISTANT_EXTRA_VAULT_DATA_MIGRATION.csv`

The temporary compatibility junctions were removed after the active runtime paths and fallback paths were rewritten to resolve directly to Substrate Vault R. The former Orb-local vault paths are no longer present as directories or junctions.

## Path Rewrites

- `orb-instance.local.ps1` now sets `ORB_SUBSTRATE_VAULT_ROOT`, `ORB_WORKSPACE_VAULT_ROOT`, `ORB_VAULT_ROOT`, `ORB_RESEARCH_VAULT_ROOT`, and `ORB_PRESENCE_DB` to the Substrate Vault R authority.
- `electron/src/floating_assistant_orb.py` now reads `ORB_RESEARCH_VAULT_ROOT` for research events and resolves presence memory from `ORB_VAULT_ROOT` / `ORB_PRESENCE_DB`.
- `electron/src/cali_swarm_extension/research/swarm_research_orchestrator.py` now reads `ORB_RESEARCH_VAULT_ROOT`.
- `electron/src/caleon_presence/core/memory_learner.py` and `desktop_presence.py` now allow env-driven vault database resolution.
- `electron/src/vault_system/manager.py` now defaults to the canonical Substrate Vault R `system_vault_system` path when no explicit base path is supplied.
- `system/protected_paths.json` now protects the canonical Substrate Vault R memory vault directly and no longer treats `system\vault_system` as a local authority.

## Organization Changes

- Moved loose review file `WIRING_REVIEW_AND_SUBSTRATE_CONNECTIONS.md` to `docs\reviews\`.
- Moved root artifacts into `_archive\Archive\root_artifacts_20260811\` with a `MOVE_MANIFEST.csv`.
- Refreshed `tree.txt`, `structure tree.txt`, and `folder_tree.txt`.

## Checks

- `npm.cmd run check:dock` passed.
- `npm.cmd run check:runtime` passed.
- Direct Python compile check passed for modified Python files.
- Endpoint probe: `http://127.0.0.1:40343/v1/models` returned 200; Orb API `21100`, realtime TTS `9880`, and Ollama fallback `11455` were not listening during this pass.

## Service Consolidation

- `R:\Services` is the only active drive-level service authority.
- The newer Desktop MCP implementation was promoted to `R:\Services\orb_desktop_mcp` after the previous root copy was backed up under `R:\_ops\substrate_audit\service_merge_20260811\premerge_root_orb_desktop_mcp`.
- Qwen Code moved from the legacy substrate vault tree to `R:\Services\qwen-code-main`.
- Active ORB launch, Electron bridge, MCP, Qwen Code, Qwen TTS, Qwen engine, Kokoro, and CosyVoice paths now resolve through `R:\Services`.
- The redundant `R:\Orb_Assistant_Desktop\Services` directory was removed from the application tree. Its rollback copy is temporarily retained at `R:\_ops\substrate_audit\service_merge_20260811\retired_orb_local_services` pending final disposal.

## Pointer Doctrine And OCR

- The supplied website doctrine was adapted into the Desktop MCP pointer runtime without replacing the existing desktop pointer interfaces.
- Resolution order is semantic locator, content fingerprint, accessibility role, then targeted Tesseract visual verification.
- Runtime order remains confidence, resolve, recover, point, ping, ploop.
- Human escalation remains explicit-only; frustration offers a handoff but does not confirm one, and suppression stays scoped to the escalated issue.
- Locator promotion requires three matching correction observations.
- Native Tesseract `5.5.0` is configured through `ORB_TESSERACT_BIN` and `TESSDATA_PREFIX`.
- MCP tool `orb_ocr_image` accepts explicit local images and can return text or TSV regions for pointer recovery.
- Synthetic-image proof read `OPEN SETTINGS`; the pointer visual matcher resolved the `SETTINGS` region with `0.97` OCR confidence.

## Final Verification

- Canonical MCP tests: `33 passed`.
- Pointer schema, desktop scene extraction, and promotion threshold tests passed.
- Adapted TypeScript files passed Node TypeScript syntax checks.
- `npm.cmd run check:dock` passed.
- `npm.cmd run check:runtime` passed.
- Qwen TTS Python environment resolves to `R:\Services\qwen_tts_312`.
- Qwen Code at the canonical path reported version `0.21.0`.
- `http://127.0.0.1:40343/v1/models` returned 200. Realtime TTS `9880` and Orb API `21100` were not listening during the final probe; this is runtime state, not a missing path declaration.

## Remaining Notes

- Source/template folders that merely contain the word `vault` were not moved: `electron/src/vault_system`, `electron/src/logic_seeds/deductive_validator/vault`, and `cali_skills/library/security_skill/vault`.
- The remaining `electron/src/vault_system` directory is a Python source package containing `VaultManager`, not a vault data authority.
- If any older external script still expects an Orb-local vault path, rewrite that script to the canonical Substrate Vault R path instead of recreating a local vault.
