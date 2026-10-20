# Orb Weaver Diagnostic Results

This folder is the Desktop ORB ingestion surface for Orb Weaver diagnostic output.

Desktop ORB does not scan the PC from here. Orb Weaver writes complete diagnostic result JSON artifacts into `incoming`, and Desktop ORB reads, validates, and presents accepted summaries.

Contract:

```text
R:\Orb_Assistant_Desktop\docs\ORBWEAVER_DIAGNOSTIC_RESULT_CONTRACT.md
```

Handoff manifest:

```text
R:\Orb_Assistant_Desktop\docs\orbweaver_desktop_handoff.manifest.json
```

JSON schema:

```text
R:\Orb_Assistant_Desktop\docs\orbweaver_diagnostic_result.schema.json
```

Folders:

```text
incoming\     New complete Orb Weaver diagnostic result JSON files.
processed\    Accepted result summaries after Desktop ORB ingestion.
archive\      Operator-approved retained snapshots.
quarantine\   Malformed, unsafe, or personal-domain artifacts.
```

Result files must use:

```json
{
  "schema": "orbweaver.diagnostic_result.v1"
}
```

Never place personal documents, emails, browser history, passwords, encrypted stores, cloud account contents, or financial data in this folder.

Orb Weaver may use the R substrate for research and the orb mesh for shared non-personal operational facts. Desktop ORB only ingests completed result artifacts from `incoming`.
