"""
Memory consolidation for the Vault Logic System.

The template's placeholder matrix consolidation was removed: A.I.M.S. is the
single memory authority (see memory/aims_binding.yaml). Consolidation is the
A.I.M.S. maintenance cycle: sweep short-term memory, evaluate the SKG, rebuild
derived indexes. The vault ledger itself is never rewritten.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import provider  # noqa: E402  (sibling module; path set above)


def consolidate_memory(store: Optional[Path] = None, self_eval_passes: int = 3) -> Dict[str, Any]:
    """Run one A.I.M.S. maintenance cycle and return its summary."""
    return provider.get_memory(store).run_maintenance_cycle(self_eval_passes=self_eval_passes)


def memory_status(store: Optional[Path] = None) -> Dict[str, Any]:
    return provider.get_memory(store).full_status()


if __name__ == "__main__":
    print(json.dumps(consolidate_memory(Path(sys.argv[1]) if len(sys.argv) > 1 else None), indent=2, default=str))
