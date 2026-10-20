# Orb Weaver Diagnostic Result Contract

This document defines the Desktop ORB boundary for machine diagnostics.

Desktop ORB does not perform broad PC scans. Orb Weaver owns observation and scan execution. Desktop ORB owns receiving approved diagnostic result artifacts, interpreting their summary fields, and presenting them through the DockStation, voice, and local cognition layer.

## Ownership

| Concern | Owner | Desktop ORB Role |
| --- | --- | --- |
| Scan execution | Orb Weaver | None |
| Hardware/system observation | Orb Weaver | Read result summaries only |
| External research | Orb Weaver using the R substrate and approved research tools | Read citations/summaries only |
| Deployed MORB research/diagnostics | MORB deployments | Deploy, supervise, ingest summaries, present repair plans |
| Diagnostic result inbox | Desktop ORB | Store incoming result artifacts |
| Shared ORB knowledge | Orb mesh | Read/write shared ORB facts through mesh contracts |
| Repo-local memory | Each repository Vault | Keep local repo memory only |
| System source of truth | R substrate Vault | Treat as the single shared source of truth |
| Operator presentation | Desktop ORB | Explain status, severity, next steps |
| Personal-domain data | Nobody by default | Must not ingest |

## Architecture Boundary

This follows the same principle as the Website ORB, adapted for a PC:

- Orb Weaver owns diagnostic traversal, observation, pointer/navigation preparation, and scan execution.
- Desktop ORB owns local presence, voice, DockStation presentation, and result ingestion.
- Deployed MORBs are the execution units for Desktop ORB research, diagnostics, scanning, repair planning, and verification.
- The R substrate is the shared research and source-of-truth layer.
- The orb mesh is the shared write/read channel where ORBs exchange non-personal operational facts.
- Vault is scoped as one Vault per repository plus one shared Vault in the R substrate.
- Desktop ORB must not create a second shared truth store inside this repository.

The API manifest can be used for path discovery and handoff configuration:

```text
R:\Orb_Assistant_Desktop\instance.manifest.json
```

Current Windows-side handoff manifest:

```text
R:\Orb_Assistant_Desktop\docs\orbweaver_desktop_handoff.manifest.json
```

MORB deployment contract:

```text
R:\Orb_Assistant_Desktop\docs\MORB_RESEARCH_DIAGNOSTIC_DEPLOYMENT_CONTRACT.md
```

## Local Result Surface

Canonical Desktop ORB result root:

```text
R:\Orb_Assistant_Desktop\CALI_System\diagnostics\orbweaver_results
```

Subdirectories:

```text
incoming\     Orb Weaver writes complete result JSON files here.
processed\    Desktop ORB may move/record accepted result summaries here.
archive\      Operator-approved retained result snapshots.
quarantine\   Rejected or malformed result artifacts.
```

Desktop ORB should treat this folder as an ingestion surface, not a scan surface.

## MORB Deployment Surface

Desktop ORB must leave room for deployed MORBs. MORBs are how Desktop ORB performs research and diagnostics when the task requires active investigation, scanning, repair planning, or verification.

Canonical deployment root:

```text
R:\Orb_Assistant_Desktop\CALI_System\diagnostics\morb_deployments
```

Subdirectories:

```text
jobs\        MORB job manifests waiting to run.
active\      Running MORB deployment state.
results\     Completed MORB result artifacts.
archive\     Operator-approved retained MORB runs.
quarantine\  Rejected, malformed, or unsafe MORB outputs.
```

Desktop ORB may deploy and supervise MORBs, but repair execution remains operator-gated. MORBs may research, scan, diagnose, prepare repair plans, and verify outcomes.

MORB deployments must always use prime-number sets. DockStation and main-process dispatch must never deploy `1` MORB or a non-prime count. Composite requests normalize upward to the next supported prime.

## Shared Data Rules

Orb Weaver may use the R substrate for research and diagnostics context, but Desktop ORB should only ingest:

- Final diagnostic result JSON files.
- Non-personal findings and metrics.
- Research summaries with source references.
- Mesh-safe operational facts.

Desktop ORB should not ingest:

- Raw research caches.
- Raw scan dumps.
- Repo-external Vault snapshots.
- Personal-domain material.
- Any second copy of the R substrate source-of-truth Vault.

## Required Result Envelope

Each Orb Weaver diagnostic result should be a JSON object with this shape:

```json
{
  "schema": "orbweaver.diagnostic_result.v1",
  "result_id": "2026-07-28T08-00-00Z-hostname-shortid",
  "created_at": "2026-07-28T08:00:00Z",
  "producer": {
    "name": "Orb Weaver",
    "version": "0.0.0",
    "checkout": "path-or-repo-id",
    "host": "local-machine-name"
  },
  "scope": {
    "mode": "system_diagnostics",
    "allowed_domains": [],
    "excluded_domains": []
  },
  "summary": {
    "state": "READY",
    "severity": "INFO",
    "headline": "Short operator-facing result",
    "details": "Short technical summary",
    "recommended_next_action": "Short action or null"
  },
  "findings": [],
  "metrics": {},
  "research": [],
  "raw_refs": [],
  "privacy": {
    "personal_domain_excluded": true,
    "contains_personal_documents": false,
    "contains_email_content": false,
    "contains_browser_history": false,
    "contains_password_or_secret_material": false
  }
}
```

Allowed `summary.state` values:

- `READY`
- `CHECKING`
- `DEGRADED`
- `ERROR`
- `OFF`
- `UNKNOWN`

Allowed `summary.severity` values:

- `INFO`
- `LOW`
- `MEDIUM`
- `HIGH`
- `CRITICAL`

## Diagnostic Knowledge Domains

Desktop ORB may interpret results in these domains only when they arrive from Orb Weaver:

- `system_state_model`: CPU, RAM, GPU, disk, processes, threads, I/O load
- `os_health_signals`: event logs, crashes, hangs, warnings
- `driver_stack`: GPU, audio, USB, HID
- `network_model`: DNS, routing, latency, packet loss, interface health
- `security_posture`: firewall state, AV state, suspicious processes
- `storage_integrity`: SMART, file system errors, fragmentation
- `thermal_model`: CPU/GPU temperature, throttling, fan behavior
- `power_model`: battery, PSU, sleep/wake behavior
- `app_behavior`: resource usage, crashes, update status
- `llm_runtime_state`: Qwen load, VRAM usage, model health
- `orb_subsystems`: perception, motion, voice, cognition, Vault

## Allowed Scan Result Categories

Orb Weaver may provide Desktop ORB result summaries for:

- `cpu_metrics`
- `gpu_metrics`
- `ram_usage`
- `disk_health`
- `motherboard_sensors`
- `peripheral_status`
- `event_logs`
- `process_table`
- `startup_items`
- `services_state`
- `driver_versions`
- `registry_health`
- `interface_status`
- `latency_profile`
- `dns_resolution`
- `firewall_rules`
- `suspicious_processes`
- `av_status`
- `port_activity`
- `credential_health`
- `crash_reports`
- `update_status`
- `resource_usage`
- `model_load`
- `audio_pipeline`
- `motion_engine`
- `voice_pipeline`
- `vault_integrity`

## Research Categories

Desktop ORB may present research summaries from Orb Weaver for:

- `driver_updates`
- `known_issues`
- `security_advisories`
- `performance_tuning`
- `llm_runtime_best_practices`
- `hardware_specs`
- `thermal_solutions`
- `network_troubleshooting`

Research entries should include:

```json
{
  "category": "known_issues",
  "query": "short query",
  "summary": "short finding",
  "sources": [
    {
      "title": "source title",
      "url": "https://example.invalid",
      "publisher": "publisher",
      "retrieved_at": "2026-07-28T08:00:00Z"
    }
  ]
}
```

## Never-Ingest Domains

Desktop ORB must reject or quarantine diagnostic artifacts that include:

- Personal documents
- Emails
- Browser history
- Passwords
- Encrypted stores
- Cloud account contents
- Financial data

The result envelope must explicitly state the personal-domain exclusions in `privacy`.

## Finding Object

Each finding should be compact and operator-facing:

```json
{
  "id": "gpu_vram_pressure_001",
  "category": "gpu_metrics",
  "state": "DEGRADED",
  "severity": "MEDIUM",
  "title": "GPU VRAM pressure elevated",
  "evidence": [
    "RTX 3050 VRAM usage reached 92 percent while llama.cpp was loaded"
  ],
  "interpretation": "The local model may slow down other GPU workloads.",
  "recommended_action": "Close unused GPU-heavy apps or lower model context.",
  "requires_operator_approval": false
}
```

## Desktop ORB Ingestion Rules

1. Accept only JSON files with `schema = orbweaver.diagnostic_result.v1`.
2. Reject artifacts that do not include the `privacy` block.
3. Quarantine artifacts where any never-ingest flag is true.
4. Do not execute commands described in findings.
5. Do not scan outside the result file to enrich it.
6. Present summaries, severity, evidence, and recommended actions.
7. Keep raw personal data out of DockStation, voice, logs, and Vault.

## Implementation Notes

The first Desktop ORB integration should be result-reader only:

- Watch or poll `incoming`.
- Validate the envelope.
- Copy accepted summaries into Desktop ORB state.
- Surface current state in DockStation.
- Let voice answer questions from accepted summaries.

Any future remediation action must be a separate operator-approved action path.
