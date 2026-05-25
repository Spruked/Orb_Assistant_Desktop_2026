#!/usr/bin/env python3
"""Test script to verify SF-ORB cognitive pipeline instantiation."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from orb_controller import SF_ORB_Controller

    print("✓ SF_ORB_Controller imported successfully")

    controller = SF_ORB_Controller()
    print("✓ SF_ORB_Controller instantiated successfully")

    # Test basic cognitive emergence
    test_stimulus = {
        "type": "cursor_movement",
        "coordinates": [100, 200],
        "velocity": 5.0,
        "intent": "navigation",
    }

    result = controller.cognitively_emerge(test_stimulus)
    if result:
        print("✓ Cognitive emergence successful")
        print(f"  - Confidence: {result.confidence}")
        print(f"  - Mode: {result.pulse().get('cognitive_mode')}")
    else:
        print("✗ Cognitive emergence returned None")

    print("✓ Cognitive pipeline verification complete")

except Exception as e:
    print(f"✗ Error: {e}")
    import traceback

    traceback.print_exc()
