"""
ORB Local MCP Server — TPC-First Architecture
R-Substrate wired. NO hardcoded LLM. NO cloud. TPC reasons first.

Entry point:
  python orb_mcp_server.py

MCP clients connect via stdio (JSON-RPC 2.0).
"""

from __future__ import annotations
import asyncio
import json
import sys
import os
import time
import traceback
from typing import Any, Dict, List, Optional

# ── Path setup ────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orb_cognition.tpc_core import get_tpc_core, ParsedIntent, ExecutionPlan
from orb_controller.mcp_bridge import get_mcp_bridge, MCPResult
from orb_desktop.desktop_orchestrator import ORBDesktopController
from orb_browser.browser_orchestrator import ORBLocalBrowser
from orb_morbs.action_morb import ActionMORB, StateMORB
from orb_safety.safety_guard import ORBSafetyGuard


# ──────────────────────────────────────────────────────────────────────────────
# Server
# ──────────────────────────────────────────────────────────────────────────────

class ORBTPCFirstMCPServer:
    """
    MCP server where TPC cognition is PRIMARY.
    All requests flow through TPC + R-Substrate first.
    LLM only engaged if TPC explicitly requests it (user-configured).

    Execution flow:
      orb_control command
        → TPC parse_intent()         [R-Substrate: all four philosophers]
        → TPC generate_plan()        [deterministic step generation]
        → _execute_plan()            [safety check → tool call → MORB verdict]
        → TPC reconcile()            [R-Substrate re-route for final calibration]
        → _format_response()         [structured output]

    Direct tool calls (orb_click, orb_type, etc.) skip TPC parsing
    but still go through safety + MORB.
    """

    def __init__(self):
        self.tpc         = get_tpc_core()
        self.bridge      = get_mcp_bridge()
        self.desktop     = ORBDesktopController()
        self.browser: Optional[ORBLocalBrowser] = None
        self.action_morb = ActionMORB()
        self.state_morb  = StateMORB()
        self.safety      = ORBSafetyGuard()

        self._llm_available = False
        self._llm_client    = None

    # ── LLM availability check (optional) ────────────────────────────────────

    def _check_llm_availability(self) -> None:
        """
        Optional. If a local LLM is running (Ollama, LM Studio, etc.)
        and the user sends use_llm=True, it will be used as a fallback
        articulation layer ONLY.
        """
        try:
            from orb_llm.local_llm import LocalLLMClient
            client = LocalLLMClient()
            if client.available:
                self._llm_available = True
                self._llm_client    = client
                self._log(f"Local LLM detected: {client.backend} / {client.model}")
        except Exception:
            pass

    # ── Tool registry ─────────────────────────────────────────────────────────

    def get_tools(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "orb_cognition_review",
                "description": (
                    "Non-executing Triple Predicate Cubed / R-Substrate review. "
                    "Parses a command or utterance, returns confidence, substrate state, "
                    "and the deterministic plan that would be considered. This tool never "
                    "moves the mouse, types, launches apps, opens browsers, or changes desktop state."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Text, command, or utterance to review through TPC."
                        },
                        "source": {
                            "type": "string",
                            "default": "orb_assistant_desktop",
                            "description": "Calling ORB or subsystem name."
                        },
                        "context": {
                            "type": "object",
                            "description": "Optional caller context. Stored only in the review result."
                        }
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "orb_control",
                "description": (
                    "Primary ORB control interface — natural language desktop automation. "
                    "TPC cognition (backed by R-Substrate four-philosopher engine) processes "
                    "your request deterministically. "
                    "Examples: 'click at 500 300', 'type \"hello world\"', "
                    "'open chrome', 'navigate to example.com', "
                    "'scroll down 5', 'take screenshot', 'snapshot'"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Natural language command for TPC to parse and execute"
                        },
                        "use_llm": {
                            "type": "boolean",
                            "default": False,
                            "description": (
                                "ONLY if TPC confidence < 0.30, escalate to local LLM "
                                "(requires a running local LLM — Ollama, LM Studio, etc.). "
                                "LLM output is always re-validated through TPC before execution."
                            )
                        }
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "orb_click",
                "description": "Click at exact screen coordinates",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "x":      {"type": "integer", "description": "X coordinate"},
                        "y":      {"type": "integer", "description": "Y coordinate"},
                        "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"}
                    },
                    "required": ["x", "y"]
                }
            },
            {
                "name": "orb_double_click",
                "description": "Double-click at exact screen coordinates",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"}
                    },
                    "required": ["x", "y"]
                }
            },
            {
                "name": "orb_scroll",
                "description": "Scroll at screen coordinates",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "x":         {"type": "integer"},
                        "y":         {"type": "integer"},
                        "direction": {"type": "string", "enum": ["up", "down", "left", "right"], "default": "down"},
                        "amount":    {"type": "integer", "default": 5, "description": "Number of scroll clicks"}
                    },
                    "required": ["x", "y"]
                }
            },
            {
                "name": "orb_type",
                "description": "Type text at the current cursor position",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text":        {"type": "string"},
                        "press_enter": {"type": "boolean", "default": False}
                    },
                    "required": ["text"]
                }
            },
            {
                "name": "orb_hotkey",
                "description": "Press a keyboard shortcut (e.g. ctrl+c, cmd+v, alt+tab)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "keys": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Keys to hold simultaneously, e.g. ['ctrl', 'c']"
                        }
                    },
                    "required": ["keys"]
                }
            },
            {
                "name": "orb_move_mouse",
                "description": "Move cursor to coordinates without clicking",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"}
                    },
                    "required": ["x", "y"]
                }
            },
            {
                "name": "orb_drag",
                "description": "Click and drag from one position to another",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "x1": {"type": "integer", "description": "Start X"},
                        "y1": {"type": "integer", "description": "Start Y"},
                        "x2": {"type": "integer", "description": "End X"},
                        "y2": {"type": "integer", "description": "End Y"},
                        "duration": {"type": "number", "default": 0.3}
                    },
                    "required": ["x1", "y1", "x2", "y2"]
                }
            },
            {
                "name": "orb_screenshot",
                "description": "Take a screenshot of the full desktop",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "width": {"type": "integer", "default": 1024, "description": "Max output width in px"}
                    }
                }
            },
            {
                "name": "orb_open_app",
                "description": "Open an application by bundle ID or name",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "bundle_id": {
                            "type": "string",
                            "description": "Bundle ID (e.g. com.google.Chrome) or app name"
                        }
                    },
                    "required": ["bundle_id"]
                }
            },
            {
                "name": "orb_browser_open",
                "description": "Open a local browser via Playwright",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "browser": {
                            "type": "string",
                            "enum": ["chrome", "chromium", "firefox", "webkit"],
                            "default": "chrome"
                        }
                    }
                }
            },
            {
                "name": "orb_browser_navigate",
                "description": "Navigate the browser to a URL",
                "inputSchema": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"]
                }
            },
            {
                "name": "orb_browser_click",
                "description": "Click at coordinates in the browser window",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"}
                    },
                    "required": ["x", "y"]
                }
            },
            {
                "name": "orb_browser_type",
                "description": "Type text in the browser",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text":        {"type": "string"},
                        "press_enter": {"type": "boolean", "default": False}
                    },
                    "required": ["text"]
                }
            },
            {
                "name": "orb_browser_scroll",
                "description": "Scroll the browser page",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "direction": {"type": "string", "enum": ["up", "down"], "default": "down"},
                        "amount":    {"type": "integer", "default": 5}
                    }
                }
            },
            {
                "name": "orb_browser_screenshot",
                "description": "Take a screenshot of the browser window",
                "inputSchema": {"type": "object", "properties": {}}
            },
            {
                "name": "orb_clipboard_read",
                "description": "Read the system clipboard contents",
                "inputSchema": {"type": "object", "properties": {}}
            },
            {
                "name": "orb_clipboard_write",
                "description": "Write text to the system clipboard",
                "inputSchema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"]
                }
            },
            {
                "name": "orb_list_windows",
                "description": "List all visible windows on the desktop",
                "inputSchema": {"type": "object", "properties": {}}
            },
            {
                "name": "orb_get_display_size",
                "description": "Get the current screen dimensions",
                "inputSchema": {"type": "object", "properties": {}}
            },
            {
                "name": "orb_wait",
                "description": "Pause execution for N seconds",
                "inputSchema": {
                    "type": "object",
                    "properties": {"seconds": {"type": "number", "minimum": 0.1, "maximum": 30}},
                    "required": ["seconds"]
                }
            },
            {
                "name": "orb_snapshot",
                "description": "Full desktop snapshot: screenshot + window list + display info",
                "inputSchema": {
                    "type": "object",
                    "properties": {"use_vision": {"type": "boolean", "default": True}}
                }
            },
            {
                "name": "orb_substrate_status",
                "description": "Return R-Substrate diagnostics: philosopher node scores, ECM state, round-trip ms",
                "inputSchema": {"type": "object", "properties": {}}
            },
            {
                "name": "orb_session_status",
                "description": "Return session stats: total calls, success rate, tool usage counts",
                "inputSchema": {"type": "object", "properties": {}}
            },
        ]

    # ── Tool dispatch ─────────────────────────────────────────────────────────

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        t_start = time.perf_counter()
        try:
            if name == "orb_cognition_review":
                result = await self._cognition_review(arguments)
            elif name == "orb_control":
                result = await self._tpc_control_flow(arguments)
            else:
                result = await self._direct_tool_call(name, arguments)

            elapsed = (time.perf_counter() - t_start) * 1000
            return self.bridge.wrap_call(name, result, elapsed)

        except Exception as e:
            return {
                "content": [{"type": "text", "text": f"Unhandled error in {name}:\n{traceback.format_exc()}"}],
                "isError": True
            }

    # ── TPC Control Flow ──────────────────────────────────────────────────────

    async def _cognition_review(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Return a TPC/R-Substrate review without executing any desktop tools."""
        command = str(arguments.get("command", "")).strip()
        if not command:
            return {
                "content": [{"type": "text", "text": "No command provided."}],
                "isError": True,
            }

        intent = self.tpc.parse_intent(command)
        plan = self.tpc.generate_plan(intent) if intent.action else None
        review = {
            "review_type": "redundant_cognition",
            "execution_allowed": False,
            "source": str(arguments.get("source") or "orb_assistant_desktop"),
            "command": command,
            "action": intent.action,
            "target": intent.target,
            "coordinates": intent.coordinates,
            "parameters": intent.parameters,
            "confidence": intent.confidence,
            "requires_clarification": intent.requires_clarification,
            "substrate_state": intent.substrate_state,
            "signal_hash": intent.signal_hash,
            "warnings": intent.warnings,
            "plan": {
                "intent_summary": plan.intent_summary if plan else "",
                "estimated_confidence": plan.estimated_confidence if plan else 0.0,
                "steps": plan.steps if plan else [],
                "fallback_steps": plan.fallback_steps if plan else [],
            },
            "context": arguments.get("context") if isinstance(arguments.get("context"), dict) else {},
            "recommendation": "review_only",
        }
        return {
            "content": [{"type": "text", "text": json.dumps(review, separators=(",", ":"))}],
            "isError": False,
        }

    async def _tpc_control_flow(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        PRIMARY execution path — all natural language commands flow here.

        Stages:
          1. TPC parse_intent()   — R-Substrate philosopher fire
          2. Confidence gate      — route or escalate
          3. LLM fallback         — only if user requested + local LLM available
          4. Clarification        — if TPC still can't resolve
        """
        command         = arguments.get("command", "").strip()
        use_llm_fallback = arguments.get("use_llm", False)
        if use_llm_fallback and not self._llm_client:
            self._check_llm_availability()

        if not command:
            return {
                "content": [{"type": "text", "text": "No command provided."}],
                "isError": True
            }

        # ── Stage 1: TPC parse ──────────────────────────────
        intent = self.tpc.parse_intent(command)

        # High confidence: execute directly
        if intent.confidence >= 0.50 and not intent.requires_clarification:
            plan = self.tpc.generate_plan(intent)
            return await self._execute_plan(plan, intent)

        # Medium confidence: execute with warning
        if intent.confidence >= 0.30:
            plan   = self.tpc.generate_plan(intent)
            result = await self._execute_plan(plan, intent)
            for item in result.get("content", []):
                if item.get("type") == "text":
                    item["text"] += (
                        f"\n\n⚠ TPC confidence: {intent.confidence:.2f} "
                        f"(substrate: {intent.substrate_state}). Verify result."
                    )
            return result

        # ── Stage 2: LLM fallback (optional, explicit) ──────
        if use_llm_fallback and self._llm_available and self._llm_client:
            llm_result = self._try_llm_fallback(command)
            if llm_result:
                return llm_result

        # ── Stage 3: Clarification request ──────────────────
        clarification = self.tpc.get_clarification_request(intent)
        return {
            "content": [{"type": "text", "text": clarification}],
            "isError": False
        }

    def _try_llm_fallback(self, command: str) -> Optional[Dict[str, Any]]:
        """
        Route to local LLM, re-validate output through TPC.
        Returns result dict or None if fallback fails.
        """
        try:
            import json
            prompt = (
                f"Desktop automation command: \"{command}\"\n"
                f"The deterministic TPC parser could not parse this.\n"
                f"Restate as ONE of: click, scroll, type, move_mouse, screenshot, open_app, navigate, wait.\n"
                f"Respond ONLY in this JSON format (no extra text):\n"
                f'{{"action": "verb", "target": "details", "parameters": {{}}, "confidence": 0.8}}'
            )
            llm_out = self._llm_client.generate(prompt, max_tokens=128, temperature=0.1)
            if not llm_out.success or not llm_out.text:
                return None

            # Strip any markdown fences
            raw = llm_out.text.strip().lstrip("```json").rstrip("```").strip()
            parsed = json.loads(raw)

            # Re-inject structured command through TPC
            structured = f"{parsed.get('action', '')} {parsed.get('target', '')}".strip()
            intent = self.tpc.parse_intent(structured)
            intent.raw_input = command  # preserve original
            # Cap LLM-derived confidence — LLM is articulation only
            intent.confidence = min(parsed.get("confidence", 0.5), 0.70)

            plan   = self.tpc.generate_plan(intent)
            result = asyncio.get_event_loop().run_until_complete(
                self._execute_plan(plan, intent)
            )
            for item in result.get("content", []):
                if item.get("type") == "text":
                    item["text"] = f"[LLM-assisted → TPC-validated]\n{item['text']}"
            return result

        except Exception as e:
            return None

    # ── Plan Execution ────────────────────────────────────────────────────────

    async def _execute_plan(
        self, plan: ExecutionPlan, intent: ParsedIntent
    ) -> Dict[str, Any]:
        """Execute each step in the plan with safety checks + MORB evaluation."""
        executed_steps: List[Dict[str, Any]] = []
        morb_verdicts:  List[Any]            = []
        all_screenshots: List[Dict[str, Any]] = []

        for i, step in enumerate(plan.steps):
            tool_name = step["tool"]
            tool_args = step["args"]

            # ── Safety gate ─────────────────────────────────
            allowed, reason = self.safety.evaluate(tool_name, tool_args)
            if not allowed:
                morb_verdicts.append(type("V", (), {
                    "verdict": "FAIL",
                    "confidence": 1.0,
                    "reason": f"Safety blocked: {reason}",
                })())
                break

            # ── Execute ─────────────────────────────────────
            result = await self._execute_single_tool(tool_name, tool_args)
            executed_steps.append(step)

            # ── MORB evaluation ─────────────────────────────
            verdict = self.action_morb.evaluate(result, tool_name)
            self.state_morb.update(verdict)
            morb_verdicts.append(verdict)

            # ── Collect screenshots ─────────────────────────
            content = getattr(result, "content", [])
            for item in content:
                if isinstance(item, dict) and item.get("type") == "image":
                    all_screenshots.append(item)

            # ── Fallback on failure ─────────────────────────
            if verdict.verdict == "FAIL":
                if i < len(plan.fallback_steps):
                    fb     = plan.fallback_steps[i]
                    fb_res = await self._execute_single_tool(fb["tool"], fb["args"])
                    executed_steps.append(fb)
                    fb_verdict = self.action_morb.evaluate(fb_res, fb["tool"])
                    self.state_morb.update(fb_verdict)
                    morb_verdicts.append(fb_verdict)
                    for item in getattr(fb_res, "content", []):
                        if isinstance(item, dict) and item.get("type") == "image":
                            all_screenshots.append(item)
                else:
                    break  # no fallback — stop plan

        # ── Reconciliation ──────────────────────────────────
        reconciliation = self.tpc.reconcile_execution_result(
            plan, executed_steps, morb_verdicts
        )

        response_text = self._format_response(
            intent, plan, executed_steps, morb_verdicts, reconciliation
        )
        content = [{"type": "text", "text": response_text}]
        content.extend(all_screenshots)

        return {
            "content": content,
            "isError": not reconciliation["usable"],
        }

    # ── Single Tool Execution ─────────────────────────────────────────────────

    async def _execute_single_tool(self, tool_name: str, args: Dict[str, Any]) -> Any:
        """Route to the correct executor. All return ORBResult-compatible objects."""
        import json

        # ── Desktop ──────────────────────────────────────────
        if tool_name == "orb_click":
            return self.desktop.click(
                args["x"], args["y"], args.get("button", "left")
            )

        elif tool_name == "orb_double_click":
            return self.desktop.double_click(args["x"], args["y"])

        elif tool_name == "orb_scroll":
            return self.desktop.scroll(
                args.get("x", 500), args.get("y", 400),
                args.get("direction", "down"),
                args.get("amount", 5),
            )

        elif tool_name == "orb_type":
            return self.desktop.type_text(
                args["text"],
                press_enter=args.get("press_enter", False),
            )

        elif tool_name == "orb_hotkey":
            keys = args.get("keys", [])
            return self.desktop.hotkey(*keys)

        elif tool_name == "orb_move_mouse":
            return self.desktop.move_mouse(args["x"], args["y"])

        elif tool_name == "orb_drag":
            return self.desktop.drag(
                args["x1"], args["y1"], args["x2"], args["y2"],
                args.get("duration", 0.3),
            )

        elif tool_name == "orb_screenshot":
            return self.desktop.screenshot(args.get("width", 1024))

        elif tool_name == "orb_open_app":
            return self.desktop.open_app(args["bundle_id"])

        elif tool_name == "orb_clipboard_read":
            text = self.desktop.read_clipboard()
            from orb_desktop.desktop_orchestrator import ORBResult
            return ORBResult.ok(text)

        elif tool_name == "orb_clipboard_write":
            self.desktop.write_clipboard(args["text"])
            from orb_desktop.desktop_orchestrator import ORBResult
            return ORBResult.ok("Clipboard updated")

        elif tool_name == "orb_list_windows":
            return self.desktop.list_windows()

        elif tool_name == "orb_get_display_size":
            size = self.desktop.get_display_size()
            from orb_desktop.desktop_orchestrator import ORBResult
            return ORBResult.ok(json.dumps({"width": size[0], "height": size[1]}))

        elif tool_name == "orb_wait":
            self.desktop.wait(args["seconds"])
            from orb_desktop.desktop_orchestrator import ORBResult
            return ORBResult.ok(f"Waited {args['seconds']}s")

        elif tool_name == "orb_snapshot":
            data = self.desktop.snapshot(args.get("use_vision", True))
            from orb_desktop.desktop_orchestrator import ORBResult
            return ORBResult.ok(json.dumps(data, indent=2))

        # ── Browser ──────────────────────────────────────────
        elif tool_name == "orb_browser_open":
            self.browser = ORBLocalBrowser(args.get("browser", "chrome"))
            ok = self.browser.open()
            from orb_desktop.desktop_orchestrator import ORBResult
            return ORBResult.ok("Browser opened") if ok else ORBResult.fail("Failed to open browser")

        elif tool_name == "orb_browser_navigate":
            from orb_desktop.desktop_orchestrator import ORBResult
            if not self.browser or not self.browser.is_ready:
                return ORBResult.fail("Browser not open — call orb_browser_open first")
            ok = self.browser.navigate(args["url"])
            return ORBResult.ok(f"Navigated to {args['url']}") if ok else ORBResult.fail("Navigation failed")

        elif tool_name == "orb_browser_click":
            from orb_desktop.desktop_orchestrator import ORBResult
            if not self.browser or not self.browser.is_ready:
                return ORBResult.fail("Browser not open")
            ok = self.browser.click_at(args["x"], args["y"])
            return ORBResult.ok("Browser click done") if ok else ORBResult.fail("Browser click failed")

        elif tool_name == "orb_browser_type":
            from orb_desktop.desktop_orchestrator import ORBResult
            if not self.browser or not self.browser.is_ready:
                return ORBResult.fail("Browser not open")
            self.browser.type_text(args["text"], press_enter=args.get("press_enter", False))
            return ORBResult.ok("Typed in browser")

        elif tool_name == "orb_browser_scroll":
            from orb_desktop.desktop_orchestrator import ORBResult
            if not self.browser or not self.browser.is_ready:
                return ORBResult.fail("Browser not open")
            self.browser.scroll_page(args.get("direction", "down"), args.get("amount", 5))
            return ORBResult.ok("Browser scrolled")

        elif tool_name == "orb_browser_screenshot":
            from orb_desktop.desktop_orchestrator import ORBResult
            if not self.browser or not self.browser.is_ready:
                return ORBResult.fail("Browser not open")
            b64 = self.browser.screenshot()
            if b64:
                return ORBResult.image_ok(b64, "Browser screenshot")
            return ORBResult.fail("Browser screenshot failed")

        # ── Diagnostics ──────────────────────────────────────
        elif tool_name == "orb_substrate_status":
            from orb_desktop.desktop_orchestrator import ORBResult
            status = self.tpc.substrate_status()
            return ORBResult.ok(json.dumps(status, indent=2))

        elif tool_name == "orb_session_status":
            from orb_desktop.desktop_orchestrator import ORBResult
            summary = self.bridge.session.summary()
            summary["morb_pass_rate"] = round(self.action_morb.pass_rate(), 4)
            summary["state_morb"]     = {
                "consecutive_fails": self.state_morb.consecutive_fails,
                "total_actions":     self.state_morb.total_actions,
            }
            return ORBResult.ok(json.dumps(summary, indent=2))

        # ── Unknown ──────────────────────────────────────────
        from orb_desktop.desktop_orchestrator import ORBResult
        return ORBResult.fail(f"Unknown tool: {tool_name}")

    # ── Direct Tool Call (no TPC parsing) ────────────────────────────────────

    async def _direct_tool_call(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a named tool directly — safety + MORB still applied."""
        allowed, reason = self.safety.evaluate(name, arguments)
        if not allowed:
            return {
                "content": [{"type": "text", "text": f"Safety blocked: {reason}"}],
                "isError": True,
            }

        result  = await self._execute_single_tool(name, arguments)
        verdict = self.action_morb.evaluate(result, name)
        self.state_morb.update(verdict)

        content = list(getattr(result, "content", [{"type": "text", "text": str(result)}]))
        return {
            "content": content,
            "isError": not getattr(result, "success", False),
        }

    # ── Response Formatter ────────────────────────────────────────────────────

    def _format_response(
        self,
        intent:         ParsedIntent,
        plan:           ExecutionPlan,
        executed:       List[Dict[str, Any]],
        verdicts:       List[Any],
        reconciliation: Dict[str, Any],
    ) -> str:
        lines = [
            "═══ ORB Control Result ═══",
            f"Command:   {intent.raw_input}",
            f"Action:    {intent.action or '(unknown)'}",
            f"Target:    {intent.target or '(none)'}",
            f"Confidence: {intent.confidence:.2f}  |  Substrate: {intent.substrate_state}",
        ]

        if intent.warnings:
            lines.append(f"Warnings:  {', '.join(intent.warnings)}")

        lines += ["", f"Plan ({len(plan.steps)} steps → {len(executed)} executed):"]

        for i, step in enumerate(executed):
            verb    = step["tool"].replace("orb_", "").replace("_", " ")
            verdict = verdicts[i] if i < len(verdicts) else None
            status  = getattr(verdict, "verdict", "?")
            reason  = getattr(verdict, "reason", "")
            icon    = "✓" if status == "PASS" else ("⚠" if status == "WARN" else "✗")
            lines.append(f"  {icon} {i+1}. {verb}  →  {status}  ({reason})")

        calib = reconciliation.get("axis_3_calibration", {})
        lines += [
            "",
            "Reconciliation:",
            f"  Usable:         {reconciliation.get('usable', False)}",
            f"  Pass rate:      {reconciliation.get('pass_rate', 0):.0%}",
            f"  Confidence:     {calib.get('capped_confidence', 0):.2f}",
            f"  Recommendation: {calib.get('recommendation', '?')}",
            f"  Substrate:      {calib.get('substrate_state', '?')}",
        ]

        if reconciliation.get("fallbacks_used"):
            lines.append("  Note: Fallback steps were used")
        if reconciliation.get("warnings"):
            lines.append(f"  Warnings: {', '.join(reconciliation['warnings'])}")

        return "\n".join(lines)

    # ── Static helper ─────────────────────────────────────────────────────────

    @staticmethod
    def _log(msg: str) -> None:
        print(f"[ORB] {msg}", file=sys.stderr, flush=True)


# ──────────────────────────────────────────────────────────────────────────────
# stdio MCP Server Loop
# ──────────────────────────────────────────────────────────────────────────────

def _make_response(req_id: Any, result: Any) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result})

def _make_error(req_id: Any, code: int, message: str) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def main():
    server = ORBTPCFirstMCPServer()
    bridge = server.bridge
    bridge.start()
    tools = server.get_tools()

    # ── Initial handshake ──────────────────────────────────
    # ── Main request loop ──────────────────────────────────
    for raw_line in sys.stdin:
        request: Dict[str, Any] = {}
        try:
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            request = json.loads(raw_line)
            method  = request.get("method", "")
            req_id  = request.get("id", -1)

            if method == "initialize":
                print(_make_response(req_id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities":    {"tools": {}},
                    "serverInfo":      {"name": "orb-tpc-first-control", "version": "2.0.0"},
                }), flush=True)

            elif method == "tools/list":
                print(_make_response(req_id, {"tools": tools}), flush=True)

            elif method == "tools/call":
                tool_name = request["params"]["name"]
                arguments = request["params"].get("arguments", {})
                result    = asyncio.run(server.call_tool(tool_name, arguments))
                print(_make_response(req_id, result), flush=True)

            elif method in ("notifications/initialized", "initialized"):
                pass  # no response for notifications

            elif method == "ping":
                print(_make_response(req_id, {}), flush=True)

            else:
                print(_make_error(req_id, -32601, f"Method not found: {method}"), flush=True)

        except json.JSONDecodeError:
            print(_make_error(-1, -32700, "Parse error: invalid JSON"), flush=True)

        except KeyError as e:
            print(_make_error(
                request.get("id", -1), -32602,
                f"Invalid params: missing field {e}"
            ), flush=True)

        except Exception as e:
            print(_make_error(
                request.get("id", -1), -32603,
                f"Internal error: {e}\n{traceback.format_exc()}"
            ), flush=True)


if __name__ == "__main__":
    main()
