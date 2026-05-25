#!/usr/bin/env python3
"""Final layer validation entry point."""

import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from logic.deductive_validation import DeductiveValidator


def run(verdict_package: dict = None):
    validator = DeductiveValidator(ROOT)

    if verdict_package is None:
        # Test with sample
        verdict_package = {
            "verdict": {
                "type": "cursor_movement",
                "conclusion": "implies_navigation",
                "confidence": 0.95,
                "source": "core_4",
            },
            "context": {"user_id": "test", "session": "abc123"},
        }

    result = validator.validate_verdict(verdict_package)

    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    if not sys.stdin.isatty():
        try:
            input_data = json.load(sys.stdin)
        except:
            input_data = None
    else:
        input_data = None

    run(input_data)
