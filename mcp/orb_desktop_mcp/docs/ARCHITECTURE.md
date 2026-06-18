# ORB Desktop MCP — TPC-First Architecture
**Version 2.0.0 | Pro Prime Series AI**

---

## Folder Structure

```
orb_desktop_mcp/
│
├── orb_mcp_server.py          ← Entry point (stdio JSON-RPC 2.0)
├── requirements.txt
│
├── orb_substrate/             ← R-Substrate: four philosopher nodes + ECM + HLSF
│   ├── __init__.py
│   └── r_substrate.py         ← Locke / Hume / Kant / Spinoza · ECMMatrix · HLSFVector
│
├── orb_cognition/             ← TPC Core: parse → plan → reconcile
│   ├── __init__.py
│   └── tpc_core.py            ← TPCIntentParser · TPCPlanGenerator · TPCReconciler · TPCCore
│
├── orb_controller/            ← MCP Bridge: session state, result carriers
│   ├── __init__.py
│   └── mcp_bridge.py          ← ORBMCPBridge · ORBSession · MCPResult
│
├── orb_desktop/               ← Desktop automation (pyautogui)
│   ├── __init__.py
│   └── desktop_orchestrator.py ← click · scroll · type · screenshot · clipboard · apps
│
├── orb_browser/               ← Browser automation (Playwright)
│   ├── __init__.py
│   └── browser_orchestrator.py ← navigate · click · type · scroll · screenshot
│
├── orb_morbs/                 ← MORB evaluators: action + state
│   ├── __init__.py
│   └── action_morb.py         ← ActionMORB · StateMORB · MORBVerdict
│
├── orb_safety/                ← Safety guard: Kant-backed allow/deny
│   ├── __init__.py
│   └── safety_guard.py        ← ORBSafetyGuard · CoordinateBoundsRule · DestructiveCommandRule …
│
├── orb_llm/                   ← Optional local LLM fallback
│   ├── __init__.py
│   └── local_llm.py           ← LocalLLMClient (Ollama · LM Studio · OpenAI-compat)
│
└── tests/
    └── test_orb_suite.py      ← Full suite: substrate · TPC · safety · MORBs · bridge
```

---

## Execution Flow

```
User command (natural language)
         │
         ▼
  orb_mcp_server.py
  call_tool("orb_control", {command})
         │
         ▼
  _tpc_control_flow()
         │
         ▼
  TPC.parse_intent(command)
  ┌──────────────────────────────────┐
  │  R-Substrate.route(signal)       │
  │  ├─ Locke   (input integrity)    │
  │  ├─ Hume    (causal plausibility)│
  │  ├─ Kant    (duty / safety)      │
  │  └─ Spinoza (determinism)        │
  │       ↓                          │
  │  ECM (weighted confidence)       │
  │  HLSF (3-axis geometry)          │
  └──────────────────────────────────┘
         │
         ├── confidence >= 0.50 → generate_plan() → execute
         ├── confidence >= 0.30 → generate_plan() → execute + WARN
         ├── confidence < 0.30 + use_llm=True → LLM fallback → TPC re-validate
         └── confidence < 0.30 → clarification request
                  │
                  ▼
           _execute_plan()
           for each step:
             ├─ ORBSafetyGuard.evaluate()   ← Kant-backed
             ├─ _execute_single_tool()       ← desktop / browser
             ├─ ActionMORB.evaluate()        ← R-Substrate re-route
             └─ StateMORB.update()
                  │
                  ▼
           TPC.reconcile_execution_result()
           R-Substrate re-route for final confidence calibration
                  │
                  ▼
           _format_response() → MCP result dict
```

---

## R-Substrate Architecture

The R-Substrate is the sovereign cognitive foundation. It is **never** replaced or bypassed.

| Node | Philosopher | Axis | Domain |
|------|-------------|------|--------|
| `locke` | John Locke | Input integrity | Is the input empirically grounded? |
| `hume` | David Hume | Causal plausibility | Does the action have a valid causal chain? |
| `kant` | Immanuel Kant | Duty / safety | Is this universally permissible? |
| `spinoza` | Baruch Spinoza | Determinism | Is the execution chain logically necessary? |

**ECM (Epistemic Convergence Matrix)** — weighted average:
`confidence = 0.30·Locke + 0.25·Hume + 0.20·Kant + 0.25·Spinoza`

**HLSF (Harmonic Logic Spatial Frame)** — 3-axis geometric state:
`axis_1 = Locke | axis_2 = (Hume+Kant)/2 | axis_3 = Spinoza`

---

## Setup

```bash
# 1. Install Python dependencies
pip install pyautogui Pillow pyperclip requests

# 2. Browser control (optional)
pip install playwright && playwright install

# 3. Run the MCP server
python orb_mcp_server.py

# 4. Run tests (no display required)
pytest tests/ -v
```

---

## Critical Architectural Rules

1. **TPC is primary.** The LLM is an optional articulation layer only. It never governs.
2. **R-Substrate is always wired.** Every signal routes through all four philosopher nodes.
3. **Safety before execution.** The ORBSafetyGuard runs before every single tool call.
4. **LLM output re-validates through TPC.** LLM confidence is capped at 0.70.
5. **`gyroscopic` and `harmanizer` naming is frozen.** Never rename these.
6. **No governance doctrine reaches the LLM.** The LLM articulates; it does not decide.
