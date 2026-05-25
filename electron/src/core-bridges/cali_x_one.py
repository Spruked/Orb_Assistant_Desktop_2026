#!/usr/bin/env python3
import sys
import json
from pathlib import Path

REPO_ROOT = (
    Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent.parent
)

print("READY: Cali_X_One", flush=True)

for line in sys.stdin:
    try:
        msg = json.loads(line)
    except Exception:
        continue
    if msg.get("type") == "query":
        result = {
            "type": "result",
            "data": {
                "status": "not_configured",
                "bridge": "cali_x_one",
                "text": "Cali_X_One bridge is online, but no live core adapter is configured.",
                "confidence": 0.0,
                "reasoning_path": ["bridge_not_configured"],
            },
        }
        print(json.dumps(result), flush=True)
