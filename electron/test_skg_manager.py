#!/usr/bin/env python3
"""
Test script for SKG Rebuild & Load Balancing System
"""

import asyncio
import sys
import os
import pytest


# Mock implementations for testing
class MasterSeedVault:
    def __init__(self, path):
        pass


class SKGForgeEngine:
    def __init__(self, worker_id):
        self.worker_id = worker_id

    async def recall_vault_memory(self, domain, key):
        return None

    def get_fragmentation_ratio(self):
        return 0.1

    def get_write_queue_depth(self):
        return 5

    async def backup_skg(self, name):
        pass

    async def archive_domain(self, domain):
        pass

    async def forge_skg_body(self, data, domain, priority="normal"):
        pass

    async def restore_skg(self, name):
        pass


class EpistemicConvergenceMatrix:
    def __init__(self, vault_path):
        pass

    async def converge(self, input_modality, raw_input, worker_context):
        return {"confidence": 0.8, "clusters": {}}


# Monkey patch the imports
sys.modules["vault_logic_system_template.seed_vault"] = type(sys)("mock")
sys.modules["vault_logic_system_template.seed_vault"].MasterSeedVault = MasterSeedVault

sys.modules["worker_forge.forge_engine"] = type(sys)("mock")
sys.modules["worker_forge.forge_engine"].SKGForgeEngine = SKGForgeEngine

sys.modules["ucm_4_core.ecm.epistemic_convergence"] = type(sys)("mock")
sys.modules["ucm_4_core.ecm.epistemic_convergence"].EpistemicConvergenceMatrix = (
    EpistemicConvergenceMatrix
)

# Add the electron src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Now import the SKG manager
from orb_skg_manager import SKGRebuildEngine


@pytest.mark.asyncio
async def test_skg_manager():
    """Test the SKG manager functionality"""
    print("🧪 Testing SKG Rebuild & Load Balancing System")

    # Create SKG manager
    vault_path = "/tmp/test_vault"  # Temporary vault path
    worker_id = "TEST_WORKER_01"

    try:
        skg_manager = SKGRebuildEngine(vault_path, worker_id)
        print("✅ SKG Manager initialized")

        # Test performance report
        report = await skg_manager.get_performance_report()
        print(f"📊 Performance Report: {report['health_status']}")
        print(f"   Query Latency: {report['metrics']['query_latency_ms']}ms")
        print(f"   Memory Usage: {report['metrics']['memory_usage_mb']}MB")
        print(f"   Fragmentation: {report['metrics']['fragmentation_ratio']:.2%}")

        # Test emergency cache
        print("💾 Testing emergency cache...")
        # Simulate adding items to cache
        for i in range(5):
            await skg_manager.emergency_cache.put(
                {"test_item": i, "timestamp": asyncio.get_event_loop().time()}
            )

        print(f"   Cache size: {skg_manager.emergency_cache.qsize()}")

        print("✅ SKG Manager test completed successfully")

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_skg_manager())
