# MORB Research and Diagnostic Deployment Contract

This document reserves the Desktop ORB architecture surface for deployed MORBs.

MORBs are the execution units for Desktop ORB research, diagnostics, scanning, and repair planning. Desktop ORB should not become the scanner or repair engine itself. It should deploy, supervise, receive, and present MORB work products.

## Core Rule

Desktop ORB uses deployed MORBs for:

- research
- diagnostics
- system scan tasks
- repair investigation
- repair planning
- post-action verification

MORBs may use Qwen Code as a local tool for diagnostics, code inspection, repair planning, and verification. Qwen Code is a tool/worker capability, not the shipped conversational runtime.

Desktop ORB owns:

- operator interaction
- voice and DockStation presentation
- launch/supervision
- ingestion of MORB results
- approval gates for repair actions

Orb Weaver owns:

- heavier diagnostic preparation
- navigation and pointer planning support
- scan pipeline design
- emitting compatible result artifacts

## Existing MORB Runtime

Current Desktop MCP MORB module:

```text
R:\Orb_Assistant_Desktop\mcp\orb_desktop_mcp\orb_morbs
```

Current role:

- `ActionMORB`: evaluates tool/action results.
- `StateMORB`: evaluates session health.

Required future role:

- Deployed MORBs as task workers for research and diagnostics.
- MORB job manifests.
- MORB result envelopes.
- MORB repair plans gated by operator approval.
- Qwen Code tool calls for local code diagnostics and repair planning.

## Deployment Surface

Reserved root:

```text
R:\Orb_Assistant_Desktop\CALI_System\diagnostics\morb_deployments
```

Reserved folders:

```text
jobs\        MORB job manifests waiting to run.
active\      Running MORB deployment state.
results\     Completed MORB result artifacts.
archive\     Operator-approved retained MORB runs.
quarantine\  Rejected, malformed, or unsafe MORB outputs.
```

## Prime Set Cardinality

MORBs are always deployed in prime-number sets.

Allowed deployment counts:

```text
2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, ...
```

Hard rules:

- Never deploy exactly `1` MORB.
- Never deploy a non-prime number of MORBs.
- Any requested count below `2` must normalize to `2`.
- Any requested composite count must normalize upward to the next supported prime.
- DockStation launch/deploy controls must expose prime counts only.
- Main-process dispatch must enforce prime counts even if a caller bypasses the DockStation UI.

## MORB Job Manifest

Canonical job shape:

```json
{
  "schema": "desktop_orb.morb_job.v1",
  "job_id": "morb-job-2026-07-28T08-40-00Z-001",
  "created_at": "2026-07-28T08:40:00Z",
  "requested_by": "desktop_orb",
  "morb_type": "diagnostic",
  "morb_count": 5,
  "cardinality_policy": "prime_only",
  "purpose": "Investigate local llama.cpp latency",
  "scope": {
    "allowed_domains": ["llm_runtime_state", "gpu_metrics", "process_table"],
    "excluded_domains": [
      "personal_documents",
      "emails",
      "browser_history",
      "passwords",
      "encrypted_stores",
      "cloud_accounts",
      "financial_data"
    ]
  },
  "inputs": {
    "diagnostic_context_ref": null,
    "pointer_context_ref": null,
    "orbweaver_result_ref": null,
    "qwen_code_context_ref": null
  },
  "tools": {
    "qwen_code_allowed": true,
    "qwen_code_mode": "diagnostic_repair_planning"
  },
  "operator_policy": {
    "may_scan_system_domain": true,
    "may_research": true,
    "may_plan_repairs": true,
    "may_execute_repairs": false,
    "requires_operator_approval_for_side_effects": true
  }
}
```

Allowed `morb_type` values:

- `research`
- `diagnostic`
- `scan`
- `repair_plan`
- `verification`

## MORB Result Envelope

Canonical result shape:

```json
{
  "schema": "desktop_orb.morb_result.v1",
  "job_id": "morb-job-2026-07-28T08-40-00Z-001",
  "morb_id": "morb-diagnostic-001",
  "created_at": "2026-07-28T08:42:00Z",
  "state": "READY",
  "severity": "INFO",
  "summary": "Short operator-facing result",
  "findings": [],
  "research": [],
  "repair_plan": null,
  "verification": null,
  "privacy": {
    "personal_domain_excluded": true,
    "contains_personal_documents": false,
    "contains_email_content": false,
    "contains_browser_history": false,
    "contains_password_or_secret_material": false,
    "contains_encrypted_store_content": false,
    "contains_cloud_account_content": false,
    "contains_financial_data": false
  }
}
```

## Repair Boundary

MORBs may recommend repairs. They must not execute repair actions by default.

Repair execution requires:

1. explicit operator approval
2. action manifest
3. rollback note or verification plan
4. post-action verification MORB

Examples of repair-side effects:

- stopping or starting services
- changing registry keys
- modifying drivers
- deleting files
- editing launchers
- changing firewall rules
- installing packages

## Research Boundary

MORBs may use the R substrate for research.

They may write mesh-safe, non-personal operational facts to:

```text
R:\mesh
```

They must not create a second shared truth store inside Desktop ORB.

Vault remains:

- one Vault per repository
- one shared source-of-truth Vault in the R substrate

## Qwen Code Tool Boundary

Qwen Code may be invoked by deployed MORBs for:

- repository diagnostics
- code navigation
- repair planning
- patch explanation
- verification planning

Qwen Code must not become:

- the Desktop ORB conversational runtime
- a cloud dependency
- a replacement for the local llama.cpp Qwen model
- an automatic repair executor without operator approval

Configured Qwen Code source:

```text
R:\Services\qwen-code-main\qwen-code-main
```

## Desktop ORB Presentation

Desktop ORB may present:

- active MORB jobs
- completed MORB summaries
- findings and severity
- repair plans awaiting approval
- verification status

Desktop ORB must not present raw personal-domain data.
