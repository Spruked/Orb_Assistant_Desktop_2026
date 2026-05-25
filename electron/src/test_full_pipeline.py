#!/usr/bin/env python3
"""Full pipeline test simulating Electron IPC."""

import json
import sys
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()


def test_full_pipeline():
    print("Testing full cognitive pipeline with simulated IPC...")

    # Start the Python process
    proc = subprocess.Popen(
        [sys.executable, "floating_assistant_orb.py"],
        cwd=str(Path(__file__).parent),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait for ready signal
        ready_line = proc.stdout.readline().strip()
        ready_msg = json.loads(ready_line)
        if ready_msg.get("type") == "ready":
            print("✓ Python process ready")
        else:
            print(f"✗ Unexpected ready message: {ready_msg}")
            return

        # Send cursor movement
        cursor_msg = {"type": "cursor_move", "x": 500, "y": 300}
        proc.stdin.write(json.dumps(cursor_msg) + "\n")
        proc.stdin.flush()
        print(f"Sent: {cursor_msg}")

        # Read response
        response_line = proc.stdout.readline().strip()
        if response_line:
            response = json.loads(response_line)
            print(f"Received: {response}")
            if response.get("type") == "cognitive_pulse":
                print("✓ Cognitive pulse received from cursor movement")

        # Send query
        query_msg = {"type": "query", "text": "Hello world"}
        proc.stdin.write(json.dumps(query_msg) + "\n")
        proc.stdin.flush()
        print(f"Sent: {query_msg}")

        # Read response
        response_line = proc.stdout.readline().strip()
        if response_line:
            response = json.loads(response_line)
            print(f"Received: {response}")
            if response.get("type") == "query_result":
                print("✓ Query result received")

        # Send get_status
        status_msg = {"type": "get_status"}
        proc.stdin.write(json.dumps(status_msg) + "\n")
        proc.stdin.flush()
        print(f"Sent: {status_msg}")

        # Read response
        response_line = proc.stdout.readline().strip()
        if response_line:
            response = json.loads(response_line)
            print(f"Received: {response}")
            if response.get("type") == "status_response":
                print("✓ Status response received")

        # Send shutdown
        shutdown_msg = {"type": "shutdown"}
        proc.stdin.write(json.dumps(shutdown_msg) + "\n")
        proc.stdin.flush()
        print(f"Sent: {shutdown_msg}")

        # Read shutdown ack
        response_line = proc.stdout.readline().strip()
        if response_line:
            response = json.loads(response_line)
            print(f"Received: {response}")
            if response.get("type") == "shutdown_ack":
                print("✓ Shutdown acknowledged")

        print("✓ Full pipeline test complete")

    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        proc.terminate()
        proc.wait()


if __name__ == "__main__":
    test_full_pipeline()
