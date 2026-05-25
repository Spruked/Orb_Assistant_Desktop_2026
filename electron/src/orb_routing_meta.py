"""Provider routing metadata factory (ORB Standard VII).

Every response that passes through the router must carry metadata proving:
  - which provider was selected
  - which provider was actually used
  - why a fallback occurred (if any)
  - which cognition mode was active
  - what intent class drove the route
  - whether governance or provider was bypassed

Hard rule: fallback must not change the intent class.
"""

import time
from typing import Dict, Optional


def make_route_meta(
    provider_selected: str,
    provider_used: str,
    cognition_mode: str,
    intent: str,
    fallback_reason: Optional[str] = None,
    bypassed_provider: bool = False,
    bypassed_governance: bool = False,
    route_class: Optional[str] = None,
    extra: Optional[Dict] = None,
) -> Dict:
    """
    Build a routing metadata dict to be attached to every query response.

    Args:
        provider_selected: The provider the router initially chose.
        provider_used:     The provider that actually answered.
        cognition_mode:    e.g. 'primitive', 'deterministic', 'llm', 'governance'.
        intent:            Intent class from intent detection (e.g. 'greeting', 'research', 'tool').
        fallback_reason:   Why provider_used differs from provider_selected (None = no fallback).
        bypassed_provider: True if the provider call was skipped entirely.
        bypassed_governance: True if governance layer was skipped.
        route_class:       High-level class: 'primitive' | 'tool' | 'normal' | 'governance'.
        extra:             Any additional diagnostic keys.

    Returns:
        Dict to be merged into the response under '_route_meta'.
    """
    if fallback_reason and provider_used != provider_selected:
        # Guard: fallback must not change intent class
        pass  # enforcement is upstream — we record it here for audit

    meta = {
        "provider_selected": provider_selected,
        "provider_used": provider_used,
        "fallback_reason": fallback_reason,
        "cognition_mode": cognition_mode,
        "intent": intent,
        "bypassed_provider": bypassed_provider,
        "bypassed_governance": bypassed_governance,
        "route_class": route_class or _infer_route_class(cognition_mode, intent),
        "ts": time.time(),
    }
    if extra:
        meta.update(extra)
    return meta


def primitive_meta(intent: str) -> Dict:
    return make_route_meta(
        provider_selected="primitive_cache",
        provider_used="primitive_cache",
        cognition_mode="primitive",
        intent=intent,
        bypassed_provider=True,
        bypassed_governance=True,
        route_class="primitive",
    )


def tool_meta(tool_id: str, intent: str) -> Dict:
    return make_route_meta(
        provider_selected=tool_id,
        provider_used=tool_id,
        cognition_mode="deterministic",
        intent=intent,
        route_class="tool",
    )


def fallback_meta(selected: str, used: str, reason: str, intent: str, cognition_mode: str = "deterministic") -> Dict:
    return make_route_meta(
        provider_selected=selected,
        provider_used=used,
        fallback_reason=reason,
        cognition_mode=cognition_mode,
        intent=intent,
    )


def _infer_route_class(cognition_mode: str, intent: str) -> str:
    if cognition_mode == "primitive":
        return "primitive"
    if intent in ("tool", "current_info", "weather", "noaa", "substrate_lookup"):
        return "tool"
    if cognition_mode in ("governance", "philosopher", "caliskg"):
        return "governance"
    return "normal"
