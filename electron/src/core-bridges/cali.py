#!/usr/bin/env python3
"""Standalone CALI bridge process."""

import asyncio
import json
import sys
from pathlib import Path


REPO_ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[3]
SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from cali_skg import CALISKG  # noqa: E402


def _run_async(coro):
    return asyncio.run(coro)


def _emit(payload):
    print(json.dumps(payload), flush=True)


def main() -> None:
    cali = CALISKG(REPO_ROOT)
    _emit({"type": "ready", "bridge": "cali"})

    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except Exception:
            continue

        msg_type = msg.get("type")
        request_id = msg.get("request_id")

        if msg_type == "shutdown":
            cali.close()
            _emit({"type": "shutdown_ack", "request_id": request_id})
            break

        if msg_type == "query":
            text = msg.get("text", "")
            reasoning = cali.reason(text)
            _emit(
                {
                    "type": "query_result",
                    "request_id": request_id,
                    "data": {
                        "echo": text,
                        "response_text": reasoning["recommended_response"],
                        "cali_reasoning": reasoning,
                        "advisory_verdict": reasoning["advisory_verdict"],
                        "voice_package": cali.speak(reasoning["recommended_response"]),
                    },
                }
            )
            continue

        if msg_type == "research":
            query = msg.get("query") or msg.get("text", "")
            domains = msg.get("domains") or []
            research = _run_async(cali.research(query, domains))
            _emit({"type": "research_result", "request_id": request_id, "data": research})
            continue

        if msg_type == "speak":
            text = msg.get("text", "")
            emotion = msg.get("emotion", "thoughtful_warm")
            _emit(
                {
                    "type": "speak_result",
                    "request_id": request_id,
                    "data": cali.speak(text, emotion),
                }
            )
            continue

        if msg_type == "set_orb_state":
            setting = msg.get("setting")
            value = msg.get("value")
            _emit(
                {
                    "type": "orb_state_result",
                    "request_id": request_id,
                    "data": {
                        "ok": cali.set_orb_state(setting, value),
                        "orb_state": cali.get_status().get("orb_state", {}),
                    },
                }
            )
            continue

        if msg_type == "get_status":
            _emit({"type": "status_response", "request_id": request_id, "data": cali.get_status()})


if __name__ == "__main__":
    main()
