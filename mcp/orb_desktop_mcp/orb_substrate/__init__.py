"""
ORB R-Substrate — Sovereign Cognitive Foundation
Exposes the four philosopher nodes, HLSF geometry engine, and ECM.
All ORB modules draw from this substrate.
"""

from .r_substrate import (
    RSubstrate,
    get_r_substrate,
    PhilosopherNode,
    ECMMatrix,
    HLSFVector,
    SubstrateVerdict,
)

__all__ = [
    "RSubstrate",
    "get_r_substrate",
    "PhilosopherNode",
    "ECMMatrix",
    "HLSFVector",
    "SubstrateVerdict",
]
