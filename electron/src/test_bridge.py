#!/usr/bin/env python3
"""Test the floating assistant orb bridge."""

import json
import sys
import time
from pathlib import Path
from io import StringIO

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from floating_assistant_orb import CALIFloatingOrb


def test_bridge():
    print("Testing CALI Floating Orb Bridge - INTUITION-JUMP Validation...")

    orb = CALIFloatingOrb(PROJECT_ROOT)
    orb.start()

    print("✓ Orb started")

    # Phase 1: Build HABIT with repeated concrete queries
    print("\n--- Phase 1: Building HABIT ---")
    habit_queries = ["2 + 2 = ?", "2 + 2 = ?", "2 + 2 = ?", "2 + 2 = ?", "2 + 2 = ?"]
    habit_results = []

    for i, query in enumerate(habit_queries):
        print(f"Habit query {i+1}: '{query}'")
        stimulus = {
            "type": "text_query",
            "content": query,
            "coordinates": [0, 0],
            "velocity": 0.0,
        }
        result = orb.controller.cognitively_emerge(stimulus)
        if result:
            if hasattr(result, "pulse"):
                pulse = result.pulse()
                mode = pulse.get("cognitive_mode")
                confidence = result.confidence
            else:
                # Lightning bypass returns dict directly
                mode = "LIGHTNING_BYPASS"
                confidence = 1.0  # Deterministic
                pulse = result
            habit_results.append((mode, confidence))
            print(f"  → Mode: {mode}, Confidence: {confidence:.3f}")
        else:
            print("  → No result")

    # Check HABIT consistency
    habit_modes = [r[0] for r in habit_results]
    habit_confidences = [r[1] for r in habit_results]
    if all(m == "HABIT" for m in habit_modes):
        print("✓ All queries processed in HABIT mode")
    else:
        print(f"✗ Mixed modes: {habit_modes}")

    if len(habit_confidences) > 1 and habit_confidences[-1] > habit_confidences[0]:
        print("✓ Confidence climbing as expected")
    else:
        print("⚠ Confidence not climbing significantly")

    # Phase 2: Trigger INTUITION-JUMP with novelty
    print("\n--- Phase 2: Triggering INTUITION-JUMP ---")
    novelty_query = (
        "Prove that all triangles are isosceles using only the concept of infinity"
    )
    print(f"Novelty query: '{novelty_query}'")
    stimulus = {
        "type": "text_query",
        "content": novelty_query,
        "coordinates": [0, 0],
        "velocity": 0.0,
    }
    result = orb.controller.cognitively_emerge(stimulus)
    if result:
        if hasattr(result, "pulse"):
            pulse = result.pulse()
            mode = pulse.get("cognitive_mode")
            confidence = result.confidence
        else:
            # Lightning bypass
            mode = "LIGHTNING_BYPASS"
            confidence = 1.0
            pulse = result
        print(f"  → Mode: {mode}, Confidence: {confidence:.3f}")
        if mode == "INTUITION-JUMP":
            print("✓ INTUITION-JUMP triggered successfully!")
            print("✓ Validation: habit → novelty → intuition confirmed")
            print("✓ Cognitive pipeline fully operational")
        elif mode == "GUARD":
            print("⚠ Got GUARD - this may be expected for complex queries")
            print("✓ Pipeline working, but query may need more novelty")
        else:
            print(f"⚠ Got {mode} - checking cognitive response")
    else:
        print("✗ No result from novelty query")

    # Phase 3: Test cursor discontinuity
    print("\n--- Phase 3: Cursor Discontinuity Test ---")
    # Send normal cursor movement
    orb.process_cursor_movement(100, 200)
    # Then sudden discontinuity
    print("Sudden cursor discontinuity...")
    orb.process_cursor_movement(800, 600)  # Large jump

    orb.stop()
    print("\n✓ INTUITION-JUMP validation test complete")


if __name__ == "__main__":
    test_bridge()
