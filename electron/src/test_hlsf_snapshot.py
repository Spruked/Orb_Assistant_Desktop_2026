"""
Tests that the Dock's HLSF mirror receives real engine data and never presents defaults as live readings.

Run from electron/src:   python -B -m unittest test_hlsf_snapshot -v
"""

import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))

from hlsf_geometry.engine import HLSFEngine  # noqa: E402
from orb_lifecycle import OrbLifecycle  # noqa: E402


def lifecycle(controller=None, presence=None):
    lc = OrbLifecycle.__new__(OrbLifecycle)
    lc.orb = SimpleNamespace(controller=controller, latest_presence_update=presence)
    return lc


def cursor(x, y, velocity=3.0):
    return {"type": "cursor_movement", "coordinates": [x, y], "velocity": velocity, "intent": "navigation"}


class SnapshotProvenanceTests(unittest.TestCase):
    def test_without_an_engine_nothing_is_presented_as_live(self):
        snap = lifecycle(controller=None)._build_hlsf_snapshot()
        self.assertFalse(snap["live"])
        self.assertEqual(snap["source"], "unavailable")
        self.assertEqual(snap["field_density"], 0)
        # The engine's configured 800/650 must not appear when there is no engine behind them.
        self.assertEqual((snap["hysteresis"]["trigger"], snap["hysteresis"]["release"]), (0, 0))
        self.assertEqual(snap["active_dims"], [])

    def test_with_an_engine_every_number_comes_from_that_engine(self):
        engine = HLSFEngine()
        for i in range(12):
            engine.map_adjacency(cursor(100 + i * 40, 200 + i * 15, velocity=1.0 + i))
        snap = lifecycle(SimpleNamespace(engine=engine), {"cognitive_mode": "HABITUATION"})._build_hlsf_snapshot()
        self.assertTrue(snap["live"])
        self.assertEqual(snap["source"], "hlsf_engine")
        self.assertEqual(snap["field_density"], len(engine.field_map))
        self.assertEqual(snap["hysteresis"]["trigger"], engine.purge_trigger_threshold)
        self.assertEqual(snap["hysteresis"]["release"], engine.purge_release_threshold)
        self.assertEqual(snap["hysteresis"]["active"], bool(engine.edge_cutter_active))
        self.assertEqual(snap["semantic_tag"], "habituating")

    def test_active_dims_are_the_engines_highest_load_nodes(self):
        engine = HLSFEngine()
        for i in range(9):
            engine.map_adjacency(cursor(50 * i, 30 * i, velocity=0.5 + i))
        snap = lifecycle(SimpleNamespace(engine=engine))._build_hlsf_snapshot()
        expected = sorted(engine.field_map.values(), key=lambda n: n.cognitive_load, reverse=True)[:3]
        self.assertEqual([(d["n"], d["k"]) for d in snap["active_dims"]], [(n.n, n.k) for n in expected])
        for dim, node in zip(snap["active_dims"], expected):
            self.assertAlmostEqual(dim["energy"], round(min(node.cognitive_load / 10.0, 1.0), 3))

    def test_density_follows_the_engine_as_it_changes(self):
        engine = HLSFEngine()
        lc = lifecycle(SimpleNamespace(engine=engine))
        before = lc._build_hlsf_snapshot()["field_density"]
        for i in range(5):
            engine.map_adjacency(cursor(10 + i, 20 + i, velocity=2.0 + i))
        self.assertEqual(lc._build_hlsf_snapshot()["field_density"], before + 5)

    def test_sequence_and_timestamp_let_the_dock_detect_a_stale_feed(self):
        lc = lifecycle(SimpleNamespace(engine=HLSFEngine()))
        first, second = lc._build_hlsf_snapshot(), lc._build_hlsf_snapshot()
        self.assertEqual(second["seq"], first["seq"] + 1)
        self.assertLess(abs(time.time() - second["ts"]), 5)

    def test_a_failing_engine_reports_the_error_instead_of_stale_numbers(self):
        class Broken:
            @property
            def field_map(self):
                raise RuntimeError("field map unavailable")

        snap = lifecycle(SimpleNamespace(engine=Broken()))._build_hlsf_snapshot()
        self.assertFalse(snap["live"])
        self.assertEqual(snap["source"], "error")
        self.assertIn("field map unavailable", snap["reason"])


class EngineGeometryTests(unittest.TestCase):
    def test_same_stimulus_maps_to_the_same_node(self):
        engine = HLSFEngine()
        first = engine.map_adjacency(cursor(500, 300))
        count = len(engine.field_map)
        again = engine.map_adjacency(cursor(500, 300))
        self.assertIs(first, again)
        self.assertEqual(len(engine.field_map), count)

    def test_coordinates_are_reproducible_across_processes(self):
        probe = (
            "import sys; sys.path.insert(0, r'%s'); "
            "from hlsf_geometry.engine import HLSFEngine; "
            "n = HLSFEngine().map_adjacency({'type':'cursor_movement','coordinates':[500,300],'velocity':3.0,'intent':'navigation'}); "
            "print(n.n, n.k, [round(c, 6) for c in n.coordinates[:4]])" % SRC
        )
        outputs = set()
        for seed in ("1", "2", "random"):
            env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONDONTWRITEBYTECODE": "1"}
            result = subprocess.run([sys.executable, "-B", "-c", probe], capture_output=True, text=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.add(result.stdout.strip().splitlines()[-1])
        self.assertEqual(len(outputs), 1, f"coordinates differ between processes: {outputs}")


class EgfStateTests(unittest.TestCase):
    def test_inactive_bridge_reports_unavailable_not_an_attribute_error(self):
        from orb_controller import EpistemicGravityBridge

        bridge = EpistemicGravityBridge.__new__(EpistemicGravityBridge)
        bridge.active, bridge.field, bridge.dim = False, None, 32
        state = bridge.get_visual_state()
        self.assertFalse(state["ok"])
        self.assertEqual(state["mode"], "unavailable")
        self.assertTrue(state["error"])

    def test_active_bridge_reports_live_field_stats(self):
        from orb_controller import EpistemicGravityBridge

        bridge = EpistemicGravityBridge.__new__(EpistemicGravityBridge)
        bridge.active, bridge.dim = True, 16
        bridge.field = SimpleNamespace(get_field_stats=lambda: {"energy": 1.5})
        state = bridge.get_visual_state()
        self.assertTrue(state["ok"])
        self.assertEqual(state["mode"], "live")
        self.assertEqual(state["stats"], {"energy": 1.5})


class EgfThrottleTests(unittest.TestCase):
    """The EGF tensor step costs about 80 ms on CPU; cursor samples must not run it every time."""

    def make_bridge(self, interval_ms):
        from orb_controller import EpistemicGravityBridge

        steps = []
        bridge = EpistemicGravityBridge.__new__(EpistemicGravityBridge)
        bridge.active, bridge.dim = True, 8
        bridge.min_step_interval_s = interval_ms / 1000.0
        bridge._last_step_at, bridge._last_stats = 0.0, {}
        bridge.field = SimpleNamespace(
            step=lambda: steps.append(1),
            broadcast_to_field=lambda signal: None,
            get_field_stats=lambda: {"steps": len(steps)},
        )
        return bridge, steps

    def test_a_burst_of_cursor_samples_runs_one_tensor_step(self):
        try:
            import torch  # noqa: F401
        except ImportError:
            self.skipTest("torch not installed")
        bridge, steps = self.make_bridge(interval_ms=500)
        stimulus = {"type": "cursor_movement", "coordinates": [100, 100], "velocity": 2.0}
        results = [bridge.process_stimulus(stimulus) for _ in range(50)]
        self.assertEqual(len(steps), 1)
        self.assertEqual(results[-1], {"steps": 1})  # later calls reuse the last stats

    def test_the_field_steps_again_after_the_interval(self):
        try:
            import torch  # noqa: F401
        except ImportError:
            self.skipTest("torch not installed")
        bridge, steps = self.make_bridge(interval_ms=20)
        stimulus = {"type": "cursor_movement", "coordinates": [100, 100], "velocity": 2.0}
        bridge.process_stimulus(stimulus)
        time.sleep(0.05)
        bridge.process_stimulus(stimulus)
        self.assertEqual(len(steps), 2)

    def test_a_zero_interval_disables_the_throttle(self):
        try:
            import torch  # noqa: F401
        except ImportError:
            self.skipTest("torch not installed")
        bridge, steps = self.make_bridge(interval_ms=0)
        for _ in range(5):
            bridge.process_stimulus({"type": "cursor_movement", "coordinates": [1, 1], "velocity": 1.0})
        self.assertEqual(len(steps), 5)


if __name__ == "__main__":
    unittest.main()
