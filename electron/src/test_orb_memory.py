"""
Tests for the ORB's single memory: OrbMemory -> Vault Logic System provider -> A.I.M.S.

Run from electron/src:   python -B -m unittest test_orb_memory -v
Every test uses its own temporary store; nothing touches the real vault.
"""

import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from orb_memory import OrbMemory, stable_key  # noqa: E402
from vault_system.manager import VaultManager  # noqa: E402


def make_memory(directory):
    return OrbMemory(store_path=Path(directory), maintain_interval_s=0)


class MemoryTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="orb_memory_test_")
        self.memory = make_memory(self.dir)
        self.assertTrue(self.memory.available, self.memory.degraded_reason)

    def tearDown(self):
        self.memory.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def reopen(self):
        self.memory.close()
        self.memory = make_memory(self.dir)
        self.assertTrue(self.memory.available, self.memory.degraded_reason)
        return self.memory


class SingleSourceTests(MemoryTestCase):
    def test_wired_through_the_vault_logic_system_provider(self):
        import vls_memory_provider as provider

        self.assertEqual(Path(self.memory.store_path), Path(self.dir))
        self.assertIs(self.memory.mem, provider.get_memory(Path(self.dir)))
        self.assertTrue((Path(__file__).resolve().parents[2] / "vault_logic_system" / "memory" / "aims" / "memory_core").is_dir())

    def test_provider_refuses_a_second_store(self):
        import vls_memory_provider as provider

        other = tempfile.mkdtemp(prefix="orb_memory_other_")
        try:
            with self.assertRaises(RuntimeError):
                provider.get_memory(Path(other))
        finally:
            shutil.rmtree(other, ignore_errors=True)

    def test_template_placeholder_stores_are_gone(self):
        memory_dir = Path(__file__).resolve().parents[2] / "vault_logic_system" / "memory"
        self.assertFalse((memory_dir / "matrix_store.yaml").exists())
        self.assertFalse((memory_dir / "domains").exists())
        self.assertTrue((memory_dir / "aims_binding.yaml").exists())


class TiersTests(MemoryTestCase):
    def test_pending_turn_stays_short_term_completed_turn_is_committed(self):
        before = self.memory.mem.long_term.total_entries
        self.memory.interaction("hello cali", "", "desktop_chat", {"phase": "user_input"}, request_id="r1")
        self.assertEqual(self.memory.mem.long_term.total_entries, before)
        self.memory.interaction("hello cali", "hello bryan", "desktop_chat", {"phase": "round_trip"}, request_id="r1")
        self.assertTrue(self.memory.flush())
        self.assertEqual(self.memory.mem.long_term.total_entries, before + 1)
        ok, corrupted = self.memory.mem.long_term.verify_chain()
        self.assertTrue(ok, corrupted)

    def test_observations_never_reach_the_ledger(self):
        before = self.memory.mem.long_term.total_entries
        for i in range(50):
            self.memory.observe("status_response", {"n": i}, tags=["status"])
        self.assertEqual(self.memory.mem.long_term.total_entries, before)
        self.assertEqual(len(self.memory.recent(limit=100, kind="status_response")), 50)

    def test_keyed_observation_updates_in_place(self):
        a = self.memory.observe("pattern", {"v": 1}, key="k1")
        b = self.memory.observe("pattern", {"v": 2}, key="k1")
        self.assertEqual(a, b)
        item = self.memory.mem.short_term.get(a)
        self.assertEqual(item.content["content"], {"v": 2})
        self.assertEqual(item.touch_count, 2)

    def test_recall_finds_completed_conversations(self):
        self.memory.interaction("remember the blue notebook", "noted", "desktop_chat", request_id="r2")
        self.assertTrue(self.memory.flush())
        result = self.memory.recall("notebook")
        self.assertTrue(result["available"])
        self.assertEqual(len(result["episodes"]), 1)
        self.assertIn("notebook", result["episodes"][0]["content"]["user_text"])

    def test_remember_creates_a_vault_atom_with_provenance(self):
        atom_id = self.memory.remember("The owner prefers short answers", {"source": "test"}, key="pref:short")
        trace = self.memory.mem.trace(atom_id)
        self.assertEqual(trace["atom"]["statement"], "The owner prefers short answers")
        self.assertEqual(len(trace["primary_entries"]), 1)


class VaultManagerTests(MemoryTestCase):
    def test_crystallize_and_lightning_query_use_short_term_first(self):
        vault = VaultManager(base_path=self.dir, memory=self.memory)
        self.assertIsNone(vault.lightning_query({"type": "cursor_movement", "coordinates": [1, 2]}))
        vault.crystallize({"type": "cursor_movement", "coordinates": [1, 2]}, {"quadrant": "NW"})
        hit = vault.lightning_query({"type": "cursor_movement", "coordinates": [1, 2]})
        self.assertEqual(hit["source"], "POSTERIORI_CACHE")
        self.assertEqual(hit["data"], {"quadrant": "NW"})

    def test_posteriori_cache_view_matches_habit_tracker_usage(self):
        vault = VaultManager(base_path=self.dir, memory=self.memory)
        vault.crystallize("habit_NW_NE_SE", {"predicted_next": "SE", "frequency": 0.3})
        self.assertEqual(vault.posteriori_cache.get("habit_NW_NE_SE")["predicted_next"], "SE")
        self.assertIsNone(vault.posteriori_cache.get("habit_missing"))

    def test_hot_path_writes_do_not_grow_the_ledger(self):
        vault = VaultManager(base_path=self.dir, memory=self.memory)
        before = self.memory.mem.long_term.total_entries
        for i in range(200):
            vault.crystallize(f"habit_{i % 7}", {"frequency": i})
        self.assertEqual(self.memory.mem.long_term.total_entries, before)

    def test_recurring_key_is_promoted_and_survives_restart(self):
        vault = VaultManager(base_path=self.dir, memory=self.memory)
        for i in range(4):
            vault.crystallize("habit_NW_NE_SE", {"predicted_next": "SE", "frequency": 0.4})
        self.memory.maintain(force=True)
        ref = self.memory._atoms_by_key.get(f"vault:{stable_key('habit_NW_NE_SE')}")
        self.assertIsNotNone(ref, "recurring key should be promoted to a vault atom")

        memory = self.reopen()
        vault = VaultManager(base_path=self.dir, memory=memory)
        hit = vault.lightning_query("habit_NW_NE_SE")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["source"], "POSTERIORI")
        self.assertEqual(hit["data"]["predicted_next"], "SE")

    def test_canonical_truths_seed_apriori_atoms_once(self):
        seed = Path(self.dir) / "apriori_core.json"
        seed.write_text('{"canonical_truths": [{"id": "OWNER_PRIVACY", "predicate": "private"}]}', encoding="utf-8")
        VaultManager(base_path=self.dir, memory=self.memory)
        VaultManager(base_path=self.dir, memory=self.memory)
        atoms = [a for a in self.memory.mem.vault.all_atoms() if (a.metadata or {}).get("orb_key") == "apriori:OWNER_PRIVACY"]
        self.assertEqual(len(atoms), 1)
        vault = VaultManager(base_path=self.dir, memory=self.memory)
        self.assertEqual(vault.lightning_query("check owner_privacy now")["source"], "APRIORI")


class PresenceLearnerTests(MemoryTestCase):
    def test_transitions_are_recent_and_sustained_recurrence_builds_trust(self):
        from caleon_presence.core.memory_learner import SystemBehaviorLearner

        learner = SystemBehaviorLearner(memory=self.memory)
        learner.record_transition("window_focus_change", "Code", "Excel", 4.0)
        recent = learner.recent_transitions()
        self.assertEqual((recent[0]["from_value"], recent[0]["to_value"]), ("Code", "Excel"))
        self.assertEqual(learner.get_vault_truth(min_confidence=0.6), [])

        for _ in range(8):  # the habit keeps recurring across maintenance cycles
            learner.record_transition("window_focus_change", "Code", "Excel", 4.0)
            time.sleep(0.03)
            learner.promote_patterns()
            self.memory.maintain(force=True)
        truths = learner.get_vault_truth(min_confidence=0.6)
        self.assertEqual(len(truths), 1)
        self.assertEqual(truths[0]["pattern_type"], "window_focus_change")
        self.assertGreaterEqual(truths[0]["observation_count"], 3)

    def test_low_priority_events_are_filtered_like_the_old_query(self):
        from caleon_presence.core.memory_learner import SystemBehaviorLearner

        learner = SystemBehaviorLearner(memory=self.memory)
        learner.record_transition("cursor_style", "a", "b")
        learner.record_transition("browser_domain_change", "x.com", "y.com")
        events = {row["event_type"] for row in learner.recent_transitions()}
        self.assertEqual(events, {"browser_domain_change"})


class DegradedModeTests(unittest.TestCase):
    def test_unavailable_memory_never_raises_and_reports_it(self):
        saved = os.environ.get("ORB_VLS_ROOT")
        import orb_memory

        original_root = orb_memory.VLS_ROOT
        orb_memory.VLS_ROOT = Path(tempfile.gettempdir()) / "does_not_exist_vls"
        sys.modules.pop("vls_memory_provider", None)
        try:
            memory = OrbMemory(store_path=Path(tempfile.gettempdir()) / "unused_store")
            self.assertFalse(memory.available)
            self.assertTrue(memory.degraded_reason)
            memory.observe("x", {"a": 1}, key="k")
            memory.vault_store("abc", {"v": 1})
            self.assertEqual(memory.vault_lookup("abc")["data"], {"v": 1})
            self.assertIsNone(memory.interaction("hi", "there"))
            self.assertFalse(memory.status()["available"])
            self.assertEqual(memory.recall("x")["episodes"], [])
        finally:
            orb_memory.VLS_ROOT = original_root
            sys.modules.pop("vls_memory_provider", None)
            if saved is not None:
                os.environ["ORB_VLS_ROOT"] = saved


class RouterTests(MemoryTestCase):
    def test_memory_record_messages_reach_the_single_memory(self):
        from orb_command_router import OrbCommandRouter

        router = OrbCommandRouter.__new__(OrbCommandRouter)
        router.orb = SimpleNamespace(memory=self.memory)
        router._handle_memory_record({"type": "memory_record", "kind": "interaction", "user_text": "ping", "orb_text": "pong", "channel": "orb_query", "metadata": {"phase": "round_trip"}})
        router._handle_memory_record({"type": "memory_record", "kind": "observation", "observation_type": "verbal_command", "content": "wake", "metadata": {}})
        self.assertTrue(self.memory.flush())
        self.assertEqual(len(self.memory.recall("ping")["episodes"]), 1)
        self.assertEqual(len(self.memory.recent(kind="verbal_command")), 1)
        self.assertIn("memory_record", OrbCommandRouter._LIFECYCLE_EXEMPT)


class ScaleTests(MemoryTestCase):
    def test_ledger_write_cost_is_recorded_not_assumed(self):
        """A.I.M.S. re-verifies the whole ledger on every write. Measure it so the cost is known."""
        call_times = []
        for i in range(200):
            start = time.perf_counter()
            self.memory.interaction(f"question {i}", f"answer {i}", "desktop_chat", request_id=f"s{i}")
            call_times.append(time.perf_counter() - start)
        flush_start = time.perf_counter()
        self.assertTrue(self.memory.flush(timeout=120))
        drain = time.perf_counter() - flush_start
        entries = self.memory.mem.long_term.total_entries
        print(f"\n  caller latency avg {sum(call_times) / len(call_times) * 1000:.2f} ms; "
              f"background drain of 200 commits {drain:.1f} s ({drain / 200 * 1000:.0f} ms each, entries={entries})")
        self.assertLess(sum(call_times) / len(call_times), 0.01)
        self.assertEqual(entries, 201)  # genesis + 200

    def test_slow_ledger_does_not_stall_the_hot_path(self):
        original = self.memory.mem.commit

        def slow_commit(*args, **kwargs):
            time.sleep(1.0)
            return original(*args, **kwargs)

        self.memory.mem.commit = slow_commit
        self.memory.interaction("slow one", "reply", "desktop_chat", request_id="slow")
        time.sleep(0.1)  # the writer is now inside the slow commit
        start = time.perf_counter()
        for i in range(200):
            self.memory.observe("cursor", {"i": i}, key=f"cursor:{i % 5}")
            self.memory.vault_store(f"habit_{i % 5}", {"f": i})
            self.memory.vault_lookup(f"habit_{i % 5}")
        elapsed = time.perf_counter() - start
        self.memory.mem.commit = original
        self.assertTrue(self.memory.flush(timeout=30))
        self.assertLess(elapsed, 0.5, f"hot path took {elapsed:.2f}s while a commit was in flight")

    def test_status_reports_the_write_queue(self):
        self.memory.interaction("a", "b", "desktop_chat", request_id="q1")
        status = self.memory.status()
        self.assertIn("write_queue", status)
        self.assertEqual(status["authority"], "aims")
        self.assertTrue(self.memory.flush())


if __name__ == "__main__":
    unittest.main()
