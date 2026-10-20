# Offline replay: runs the A.I.M.S. maintenance cycle (the framework's only memory).
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "memory"))
import consolidation  # noqa: E402

if __name__ == "__main__":
    store = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    print(json.dumps(consolidation.consolidate_memory(store), indent=2, default=str))
