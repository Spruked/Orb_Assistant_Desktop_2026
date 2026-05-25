import sys
import importlib
import os
from pathlib import Path

# SOVEREIGN CACHE PURGE: ensure fresh engine without stale bytecode
if 'hlsf_geometry.engine' in sys.modules:
    del sys.modules['hlsf_geometry.engine']
if 'hlsf_geometry' in sys.modules:
    del sys.modules['hlsf_geometry']

sys.dont_write_bytecode = True
if os.environ.get("PYTHONHASHSEED") != "0":
    raise SystemExit("Launch with PYTHONHASHSEED=0")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

print("Importing HLSFEngine...")
from hlsf_geometry.engine import HLSFEngine, hlsf_singleton
print("Importing SF_ORB_Controller...")
from orb_controller import SF_ORB_Controller

print(f"DEBUG: Engine ID: {id(hlsf_singleton)}")
print(f"DEBUG: Has max_field_density? {hasattr(hlsf_singleton, 'max_field_density')}")
if hasattr(hlsf_singleton, 'max_field_density'):
    print(f"DEBUG: Threshold = {hlsf_singleton.max_field_density}")
    print(f"DEBUG: Soft cap = {hlsf_singleton.edge_cutter_threshold}")
else:
    print("[STOP] CRITICAL: Running STALE engine without edge-cutter! Restart VS Code.")
    sys.exit(1)

print("Imports successful, controller not initialized.")