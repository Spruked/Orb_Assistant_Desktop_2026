from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

LEDGER_PATH = Path(r"R:\CALI_SUBSTRATE\domain_knowledge\research_layer\research_api_validation_ledger.csv")
REGISTRY_PATH = Path(r"R:\CALI_SUBSTRATE\domain_knowledge\research_layer\research_api_registry.csv")

SAFETY_THRESHOLD = 0.90
RELIABILITY_THRESHOLD = 0.90


def _to_float(v: str) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _parse_utc(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def load_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def is_https(url: Optional[str]) -> bool:
    return isinstance(url, str) and url.startswith("https://")


def _cooldown_active(value: Optional[str]) -> bool:
    cooldown_until = _parse_utc(value)
    if cooldown_until is None:
        return False
    return cooldown_until > datetime.now(timezone.utc)


def select_api_for_category(category: str) -> Dict:
    ledger = load_csv(LEDGER_PATH)
    registry = load_csv(REGISTRY_PATH)

    reg_candidates = [r for r in registry if r.get("category") == category]
    ledger_map = {r["api_id"]: r for r in ledger if r.get("api_id")}

    scored_candidates = []
    rejected = []

    for reg in reg_candidates:
        api_id = reg["api_id"]
        led = ledger_map.get(api_id)

        if not led:
            rejected.append({"api_id": api_id, "reason": "missing_ledger_row"})
            continue

        status = led.get("status", "")
        rec = led.get("recommended_action", "")
        safety = _to_float(led.get("safety_score", "0"))
        reliability = _to_float(led.get("reliability_score", "0"))
        schema_valid = led.get("schema_valid", "false").lower() == "true"
        endpoint = led.get("endpoint")
        cooldown_until = led.get("cooldown_until", "")
        last_failure_reason = led.get("last_failure_reason", "")

        if rec == "block":
            rejected.append({"api_id": api_id, "reason": "explicit_block"})
            continue
        if _cooldown_active(cooldown_until):
            rejected.append({"api_id": api_id, "reason": "cooldown_active"})
            continue
        if safety < SAFETY_THRESHOLD:
            rejected.append({"api_id": api_id, "reason": "safety_below_threshold"})
            continue
        if not schema_valid:
            rejected.append({"api_id": api_id, "reason": "schema_invalid"})
            continue
        if endpoint and not is_https(endpoint):
            rejected.append({"api_id": api_id, "reason": "non_https_endpoint"})
            continue

        score = (
            safety * 0.5
            + reliability * 0.4
            + (1.0 if status == "healthy" else 0.5) * 0.1
        )

        scored_candidates.append(
            {
                "api_id": api_id,
                "score": score,
                "status": status,
                "recommended_action": rec,
                "endpoint": endpoint,
                "mirror_path": reg.get("mirror_path"),
                "fallback_endpoint": reg.get("fallback_endpoint"),
                "safety": safety,
                "reliability": reliability,
                "last_failure_reason": last_failure_reason,
                "cooldown_until": cooldown_until,
            }
        )

    if not scored_candidates:
        return {
            "action": "block",
            "reason": "no_safe_api_available",
            "trace": {
                "category": category,
                "considered": len(reg_candidates),
                "rejected": rejected,
            },
        }

    best = sorted(scored_candidates, key=lambda x: x["score"], reverse=True)[0]

    if best["status"] == "healthy" and best["reliability"] >= RELIABILITY_THRESHOLD:
        action = "use_primary"
        endpoint = best["endpoint"]
    elif best["status"] in ("unstable", "rate_limited") and best["mirror_path"]:
        action = "use_mirror"
        endpoint = best["mirror_path"]
    elif best["fallback_endpoint"] and is_https(best["fallback_endpoint"]):
        action = "use_fallback"
        endpoint = best["fallback_endpoint"]
    elif best["mirror_path"]:
        action = "use_mirror"
        endpoint = best["mirror_path"]
    else:
        return {
            "action": "block",
            "reason": "no_viable_route",
            "trace": {
                "category": category,
                "api_id": best["api_id"],
                "status": best["status"],
                "safety": best["safety"],
                "reliability": best["reliability"],
                "score": best["score"],
                "last_failure_reason": best["last_failure_reason"],
                "cooldown_until": best["cooldown_until"],
            },
        }

    return {
        "action": action,
        "api_id": best["api_id"],
        "endpoint": endpoint,
        "trace": {
            "status": best["status"],
            "safety": best["safety"],
            "reliability": best["reliability"],
            "score": best["score"],
            "last_failure_reason": best["last_failure_reason"],
            "cooldown_until": best["cooldown_until"],
        },
    }
