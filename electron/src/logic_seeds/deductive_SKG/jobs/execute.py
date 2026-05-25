#!/usr/bin/env python3
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from logic.deductive_logic import DeductiveEngine


def run(stimulus_input: dict = None, idle_mode: bool = False):
    engine = DeductiveEngine(ROOT)

    if idle_mode:
        # Idle processing for recursive improvement
        result = engine.process_idle_feedback()
        return result

    if stimulus_input is None:
        stimulus_input = {
            "type": "cursor_movement",
            "coordinates": [100, 200],
            "hlsf_node": {"density": 10, "recursion": 1},
        }

    advisory = engine.advise_orb(
        stimulus_type=stimulus_input.get("type", "unknown"),
        hlsf_node_data=stimulus_input.get("hlsf_node", {}),
    )

    status = engine.get_cognitive_status()

    output = {
        "worker": "deductive_reasoner",
        "advisory": advisory,
        "cognitive_status": status,
        "timestamp": __import__("time").time(),
    }

    print(json.dumps(output, indent=2))
    return output


def validate(verdict_id: str, was_correct: bool):
    """External validation entry point."""
    engine = DeductiveEngine(ROOT)
    engine.validate_verdict(verdict_id, was_correct)
    print(json.dumps({"status": "validated", "verdict_id": verdict_id}))


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--idle" in args:
        result = run(idle_mode=True)
        print(json.dumps(result, indent=2))
    elif "--validate" in args:
        # Format: --validate <verdict_id> <true/false>
        idx = args.index("--validate")
        if len(args) >= idx + 3:
            validate(args[idx + 1], args[idx + 2].lower() == "true")
    else:
        if not sys.stdin.isatty():
            try:
                input_data = json.load(sys.stdin)
            except:
                input_data = None
        else:
            input_data = None

        run(input_data)
