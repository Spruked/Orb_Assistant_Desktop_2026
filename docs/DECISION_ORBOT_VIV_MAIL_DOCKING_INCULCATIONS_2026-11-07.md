# Decision: Cali / Orbot docking across VIV and Prime Mail

Status: ACCEPTED ARCHITECTURAL DECISION — 2026-11-07
Scope: Desktop Orbot, VIV (Vector Intelligence Vault), Prime Mail / VIV Communications

## Binding product decision

- Cali remains the assistant identity across the experience. Orbot is the floating desktop embodiment of Cali, not a competing assistant identity.
- Orbot can dock inside VIV when needed and dock inside the email client when needed.
- Every docking location has its own inculcation doctrine applicable to that system. When systems are combined, the combined operational scope is governed by the applicable inculcations together.
- The inculcations already exist in the runtime. Preserve them; do not overwrite, bypass, replace, or flatten them into a generic prompt.
- Docking changes context, available tools, permissions, and governing doctrine for the location; it does not require treating Cali as a new assistant or replacing her identity.
- Existing boundaries for identity, intelligence, authority, execution, and verification remain explicit. A dock does not grant execution rights by itself.
- Preserve functioning inference, memory, voice and docking integrations. Do not restart or reconfigure services as part of recording this decision.

## Verification before implementation changes

1. Inspect the actual deployed Tauri Orbot, VIV and email-client runtimes, including their existing inculcation loading paths.
2. Determine which doctrines govern each host and how the active combined scope is selected when docked.
3. Confirm the same Cali identity is presented while location-specific authorization remains separate.
4. Verify that docking into and leaving each location preserves intended assistant continuity.
5. Treat observed behavior and documented configuration separately; report gaps without inventing behavior.

This commit records an existing owner decision. It does not assert that the currently running applications have completed every integration or that runtime files were committed from the user's PC.
