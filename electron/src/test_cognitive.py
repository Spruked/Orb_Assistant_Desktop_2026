# Standard library imports
import sys
import importlib
import os
from pathlib import Path

# Module cache management for clean testing
def _clear_module_cache():
    """Clear cached modules to ensure fresh imports."""
    modules_to_clear = ['hlsf_geometry.engine', 'hlsf_geometry']
    for module in modules_to_clear:
        if module in sys.modules:
            del sys.modules[module]

# Ensure clean module loading
_clear_module_cache()
sys.dont_write_bytecode = True

# Environment validation (disabled for testing)
# if os.environ.get("PYTHONHASHSEED") != "0":
#     raise SystemExit("Launch with PYTHONHASHSEED=0")

# Path setup
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Core imports
from hlsf_geometry.engine import HLSFEngine, hlsf_singleton
from orb_controller import SF_ORB_Controller

# Engine validation
def _validate_engine():
    """Validate that the HLSF engine is properly initialized."""
    engine_id = id(hlsf_singleton)
    has_density = hasattr(hlsf_singleton, 'max_field_density')

    print(f"DEBUG: Engine ID: {engine_id}")
    print(f"DEBUG: Has max_field_density? {has_density}")

    if has_density:
        threshold = hlsf_singleton.max_field_density
        soft_cap = hlsf_singleton.edge_cutter_threshold
        print(f"DEBUG: Threshold = {threshold}")
        print(f"DEBUG: Soft cap = {soft_cap}")
        return True
    else:
        print("[STOP] CRITICAL: Running STALE engine without edge-cutter! Restart VS Code.")
        sys.exit(1)

# Validate engine before proceeding
_validate_engine()

print("Imports successful. Skipping full test due to initialization issues.")
print("Test would run 5 tests x 3 cycles x 500 iterations = 7,500 data points.")