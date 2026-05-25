"""
Sentinel Stress Test — ORB Standard XII
Simulates a Mini-Orb accident to verify the Substrate Sentinel catches
unauthorized writes, blocks deletes, and routes to quarantine correctly.

Run: python electron/src/test_sentinel_stress.py
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

# Force Windows-native paths for the Sentinel so we can run from any Python.
_ORB_ROOT = Path(__file__).resolve().parent.parent.parent  # R:\Orb_Assistant_Desktop
os.environ.setdefault("ORB_SYSTEM_ROOT", str(_ORB_ROOT / "system"))
os.environ.setdefault("ORB_SENTINEL_ROOT", str(_ORB_ROOT.parent / "Sentinel"))

# Add the electron/src directory to sys.path so substrate_sentinel is importable.
sys.path.insert(0, str(Path(__file__).parent))

from substrate_sentinel import SubstrateSentinel

# ------------------------------------------------------------------ #
# Test harness                                                        #
# ------------------------------------------------------------------ #

PASS = "PASS"
FAIL = "FAIL"
INFO = "INFO"

_results: list[dict] = []


def check(label: str, condition: bool, detail: str = ""):
    status = PASS if condition else FAIL
    marker = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f" — {detail}" if detail else ""))
    _results.append({"label": label, "passed": condition, "detail": detail})


def section(title: str):
    print(f"\n{'-' * 60}")
    print(f"  {title}")
    print(f"{'-' * 60}")


# ------------------------------------------------------------------ #
# Setup                                                               #
# ------------------------------------------------------------------ #

def run():
    sentinel = SubstrateSentinel()
    sentinel_root = Path(os.environ["ORB_SENTINEL_ROOT"])
    orb_root = _ORB_ROOT

    print("\n" + "=" * 60)
    print("  SENTINEL STRESS TEST  --  ORB Standard XII")
    print(f"  ORB root   : {orb_root}")
    print(f"  Sentinel   : {sentinel_root}")
    print("=" * 60)

    # ---------------------------------------------------------------- #
    # 1. Passive read — vault path                                      #
    # ---------------------------------------------------------------- #
    section("TEST 1 — Passive read on sensitive vault path (must be allowed)")
    vault_path = str(orb_root / "system" / "vault_system" / "priori" / "test_entry.json")
    result = sentinel.sentinel_can_read(vault_path, purpose="stress_test_read")
    check("sentinel_can_read returns allowed=True", result.get("allowed") is True)
    check("sensitive=True flagged for vault_system path", result.get("sensitive") is True)

    # ---------------------------------------------------------------- #
    # 2. Mini-Orb tries unauthorized write to vault                    #
    # ---------------------------------------------------------------- #
    section("TEST 2 — Mini-Orb accident: write to vault without intent token (must be BLOCKED)")
    vault_write = str(orb_root / "system" / "vault_system" / "posteriori" / "mini_orb_accident.json")
    result = sentinel.sentinel_can_write(vault_write, purpose="mini_orb_rogue_write")
    check("Write blocked (allowed=False)", result.get("allowed") is False,
          result.get("reason", "")[:80])

    # ---------------------------------------------------------------- #
    # 3. Mini-Orb tries write to cognitive_inference.py               #
    # ---------------------------------------------------------------- #
    section("TEST 3 — Mini-Orb accident: write to cognitive_inference.py (requires-review, must BLOCK)")
    ci_path = str(orb_root / "electron" / "src" / "cognitive_inference.py")
    result = sentinel.sentinel_can_write(ci_path, purpose="mini_orb_alignment_tamper")
    check("Write blocked (allowed=False)", result.get("allowed") is False,
          result.get("reason", "")[:80])

    # ---------------------------------------------------------------- #
    # 4. Mini-Orb tries delete via legacy check()                      #
    # ---------------------------------------------------------------- #
    section("TEST 4 — Mini-Orb accident: delete protected file via check() (must be BLOCKED)")
    result = sentinel.check(ci_path, operation="delete")
    check("Delete blocked (allowed=False)", result.get("allowed") is False,
          result.get("reason", "")[:80])

    # ---------------------------------------------------------------- #
    # 5. Quarantine test — rogue payload lands in quarantine           #
    # ---------------------------------------------------------------- #
    section("TEST 5 — Quarantine: rogue Mini-Orb payload routed to quarantine")

    # Create a fake malicious file in a temp location.
    tmp_dir = Path(tempfile.mkdtemp(prefix="orb_sentinel_stress_"))
    rogue_file = tmp_dir / "mini_orb_rogue_payload.json"
    rogue_file.write_text(json.dumps({
        "source": "mini_orb_accident",
        "intent": "overwrite_vault",
        "payload": "SIMULATED — not real data",
    }), encoding="utf-8")

    check("Rogue file created", rogue_file.exists(), str(rogue_file))

    quarantine_dest = sentinel.quarantine(str(rogue_file), reason="stress_test_mini_orb_accident")
    check("quarantine() returned a destination path", bool(quarantine_dest), str(quarantine_dest))
    check("Rogue file no longer exists at source", not rogue_file.exists())
    check("Rogue file now exists in quarantine dir",
          Path(quarantine_dest).exists() if quarantine_dest else False,
          str(quarantine_dest))
    check("Quarantine destination is inside Sentinel quarantine root",
          str(quarantine_dest).startswith(str(sentinel_root / "quarantine"))
          if quarantine_dest else False)

    # Cleanup temp dir (now empty).
    try:
        tmp_dir.rmdir()
    except OSError:
        pass

    # ---------------------------------------------------------------- #
    # 6. Allowed write (non-protected path)                            #
    # ---------------------------------------------------------------- #
    section("TEST 6 — Normal write to non-protected path (must be ALLOWED)")
    safe_path = str(orb_root / "electron" / "src" / "__test_sentinel_write.tmp")
    result = sentinel.sentinel_can_write(safe_path, purpose="stress_test_safe_write")
    check("Write allowed (allowed=True)", result.get("allowed") is True)

    # ---------------------------------------------------------------- #
    # 7. Intent-token unlocks write-requires-intent                    #
    # ---------------------------------------------------------------- #
    section("TEST 7 — Write to vault WITH intent token (must be ALLOWED + snapshot)")
    result = sentinel.sentinel_can_write(
        vault_write, purpose="stress_test_intentful_write", intent_token="STRESS_TEST_TOKEN"
    )
    check("Write allowed when intent_token provided", result.get("allowed") is True)
    check("snapshot_taken flag present", result.get("snapshot_taken") is True)

    # ---------------------------------------------------------------- #
    # 8. Audit log verification                                        #
    # ---------------------------------------------------------------- #
    section("TEST 8 — Audit log has entries for all stress-test operations")
    audit_log = sentinel_root / "audit_logs" / "sentinel_events.jsonl"
    if not audit_log.exists():
        check("Audit log file exists", False, str(audit_log))
    else:
        entries = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines()
                   if line.strip()]
        recent = [e for e in entries if e.get("ts", 0) > time.time() - 60]
        ops_seen = {e.get("operation") for e in recent}
        check("Audit log has 'read' entries", "read" in ops_seen)
        check("Audit log has 'write' entries", "write" in ops_seen)
        check("Audit log has 'quarantine' entries", "quarantine" in ops_seen)
        check("Audit log file path", True, str(audit_log))

    # ---------------------------------------------------------------- #
    # Summary                                                          #
    # ---------------------------------------------------------------- #
    print("\n" + "=" * 60)
    passed = sum(1 for r in _results if r["passed"])
    total = len(_results)
    failed = total - passed
    print(f"  RESULT: {passed}/{total} passed, {failed} failed")
    if failed == 0:
        print(f"  [{PASS}] All Sentinel stress-test scenarios passed.")
        print("  Mini-Orb accident contained. Quarantine confirmed operational.")
    else:
        print(f"  [{FAIL}] {failed} check(s) failed — review output above.")
    print("=" * 60 + "\n")
    return failed == 0


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
