# Caleon cognition-memory engine for local deterministic behavior learning.

import math
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional


class VaultCompactor(threading.Thread):
    def __init__(self, learner, interval_s: int = 300):
        super().__init__(daemon=True)
        self.learner = learner
        self.interval = max(30, int(interval_s))
        self._stop_event = threading.Event()

    def run(self):
        while not self._stop_event.is_set():
            try:
                self.learner.compact_memory()
            except Exception:
                pass
            self._stop_event.wait(self.interval)

    def stop(self):
        self._stop_event.set()
        self.join(timeout=2.0)


class SystemBehaviorLearner:
    PATTERN_WEIGHTS = {
        "daily_rhythm": 0.018,
        "window_dominance": 0.035,
        "browser_domain": 0.042,
        "cursor_style": 0.085,
        "default": 0.055,
    }

    LEARNING_RATES = {"HIGH": 0.22, "MEDIUM": 0.14, "LOW": 0.07}

    def __init__(self, db_path: str = "vault_system/behavior_learner.db"):
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=20)
        self.db_lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="CaleonDB")
        self._init_tables()
        self.compactor = VaultCompactor(self)
        self.compactor.start()

    def _init_tables(self):
        with self.db_lock:
            with self.conn:
                self.conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS transitions (
                        id INTEGER PRIMARY KEY,
                        timestamp REAL,
                        event_type TEXT,
                        from_value TEXT,
                        to_value TEXT,
                        duration REAL,
                        day_of_week INTEGER,
                        hour_of_day INTEGER,
                        priority TEXT
                    );

                    CREATE TABLE IF NOT EXISTS behavior_patterns (
                        id INTEGER PRIMARY KEY,
                        pattern_type TEXT,
                        key TEXT,
                        value REAL,
                        confidence REAL DEFAULT 0.4,
                        observation_count INTEGER DEFAULT 1,
                        last_reinforced REAL,
                        days_since_reinforcement INTEGER DEFAULT 0,
                        pattern_weight REAL DEFAULT 1.0,
                        archived INTEGER DEFAULT 0
                    );

                    CREATE TABLE IF NOT EXISTS pattern_challenges (
                        id INTEGER PRIMARY KEY,
                        pattern_type TEXT,
                        key TEXT,
                        challenged_pattern_id INTEGER,
                        timestamp REAL,
                        count INTEGER DEFAULT 1
                    );

                    CREATE TABLE IF NOT EXISTS pattern_revisions (
                        id INTEGER PRIMARY KEY,
                        pattern_type TEXT,
                        key TEXT,
                        previous_confidence REAL,
                        new_confidence REAL,
                        reason TEXT,
                        timestamp REAL
                    );
                    """
                )

    def _get_pattern_weight(self, pattern_type: str) -> float:
        return self.PATTERN_WEIGHTS.get(pattern_type, self.PATTERN_WEIGHTS["default"])

    def _priority_for_event(self, event_type: str) -> str:
        if "window" in event_type or "idle" in event_type:
            return "HIGH"
        if "domain" in event_type or "app" in event_type:
            return "MEDIUM"
        return "LOW"

    def apply_decay(self):
        now = time.time()
        with self.db_lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT id, confidence, last_reinforced, pattern_type FROM behavior_patterns WHERE archived=0"
            )
            rows = cur.fetchall()
            with self.conn:
                for row_id, conf, last_reinf, ptype in rows:
                    days = max(0.0, (now - (last_reinf or now)) / 86400.0)
                    decay_rate = self._get_pattern_weight(ptype)
                    new_conf = conf * math.exp(-decay_rate * days)
                    new_conf = max(new_conf, 0.05)
                    self.conn.execute(
                        "UPDATE behavior_patterns SET confidence=?, days_since_reinforcement=? WHERE id=?",
                        (new_conf, int(days), row_id),
                    )

    def reinforce_pattern(
        self, pattern_type: str, key: str, value: float, priority: str = "MEDIUM"
    ):
        learning_rate = self.LEARNING_RATES.get(priority, 0.07)
        now = time.time()

        def _task():
            with self.db_lock:
                cur = self.conn.cursor()
                week_ago = now - 7 * 86400
                cur.execute(
                    "SELECT COUNT(*), GROUP_CONCAT(hour_of_day) FROM transitions WHERE timestamp>? AND to_value=?",
                    (week_ago, key),
                )
                rc = cur.fetchone() or (0, None)
                recent_count = rc[0] or 0
                hours_concat = rc[1]

                hours_std = None
                if hours_concat:
                    try:
                        hours = [float(h) for h in hours_concat.split(",") if h is not None]
                        if len(hours) > 1:
                            mean_h = sum(hours) / len(hours)
                            var = sum((h - mean_h) ** 2 for h in hours) / len(hours)
                            hours_std = math.sqrt(var)
                    except Exception:
                        hours_std = None

                cur.execute(
                    "SELECT id, confidence, observation_count FROM behavior_patterns WHERE pattern_type=? AND key=?",
                    (pattern_type, key),
                )
                row = cur.fetchone()

                with self.conn:
                    if row:
                        pid, conf, obs = row
                        delta = learning_rate * (1.0 - conf)
                        if recent_count >= 3:
                            delta *= 1.35
                        bonus = 0.09 if (hours_std is not None and hours_std < 2.5) else 0.0
                        new_conf = min(0.999, conf + delta + bonus)
                        new_conf = max(new_conf, 0.05)
                        self.conn.execute(
                            "UPDATE behavior_patterns SET value=?, confidence=?, observation_count=?, last_reinforced=? WHERE id=?",
                            (value, new_conf, (obs or 0) + 1, now, pid),
                        )

                        if priority == "HIGH" and new_conf >= 0.6:
                            cur2 = self.conn.execute(
                                "SELECT id, key, confidence FROM behavior_patterns WHERE pattern_type=? AND id<>? AND archived=0",
                                (pattern_type, pid),
                            )
                            for oid, okey, oconf in cur2.fetchall():
                                reduced = max(0.05, oconf * 0.6)
                                self.conn.execute(
                                    "UPDATE behavior_patterns SET confidence=? WHERE id=?",
                                    (reduced, oid),
                                )
                                self.conn.execute(
                                    "INSERT INTO pattern_challenges (pattern_type, key, challenged_pattern_id, timestamp, count) VALUES (?,?,?,?,1)",
                                    (pattern_type, okey, oid, now),
                                )
                    else:
                        base_conf = 0.4
                        delta = learning_rate * (1.0 - base_conf)
                        if recent_count >= 3:
                            delta *= 1.35
                        bonus = 0.09 if (hours_std is not None and hours_std < 2.5) else 0.0
                        new_conf = min(0.999, base_conf + delta + bonus)
                        new_conf = max(new_conf, 0.05)
                        self.conn.execute(
                            "INSERT INTO behavior_patterns (pattern_type, key, value, confidence, observation_count, last_reinforced, pattern_weight) VALUES (?,?,?,?,?,?,?)",
                            (
                                pattern_type,
                                key,
                                value,
                                new_conf,
                                1,
                                now,
                                self._get_pattern_weight(pattern_type),
                            ),
                        )

        self.executor.submit(_task)

    def record_transition(
        self, event_type: str, from_val: str, to_val: str, duration: Optional[float] = None
    ):
        dt = datetime.now()
        priority = self._priority_for_event(event_type)

        def _insert():
            with self.db_lock:
                with self.conn:
                    self.conn.execute(
                        "INSERT INTO transitions (timestamp, event_type, from_value, to_value, duration, day_of_week, hour_of_day, priority) VALUES (?,?,?,?,?,?,?,?)",
                        (time.time(), event_type, from_val, to_val, duration, dt.weekday(), dt.hour, priority),
                    )

        self.executor.submit(_insert)

    def promote_patterns(self):
        now = time.time()
        week_ago = now - 7 * 86400
        with self.db_lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT to_value, COUNT(*) FROM transitions WHERE timestamp>? AND event_type='window_focus_change' GROUP BY to_value",
                (week_ago,),
            )
            window_rows = cur.fetchall()

        for app, cnt in window_rows:
            self.reinforce_pattern("window_dominance", app, float(cnt), priority="HIGH")
            with self.db_lock:
                with self.conn:
                    cur2 = self.conn.execute(
                        "SELECT challenged_pattern_id, COUNT(*) as c FROM pattern_challenges WHERE pattern_type='window_dominance' AND key=? GROUP BY challenged_pattern_id",
                        (app,),
                    )
                    for challenged_id, c in cur2.fetchall():
                        if c >= 3:
                            old = self.conn.execute(
                                "SELECT confidence, key FROM behavior_patterns WHERE id=?",
                                (challenged_id,),
                            ).fetchone()
                            if old:
                                prev_conf, prev_key = old
                                new_conf = prev_conf * 0.4
                                self.conn.execute(
                                    "UPDATE behavior_patterns SET confidence=?, archived=1 WHERE id=?",
                                    (new_conf, challenged_id),
                                )
                                self.conn.execute(
                                    "INSERT INTO pattern_revisions (pattern_type, key, previous_confidence, new_confidence, reason, timestamp) VALUES (?,?,?,?,?,?)",
                                    (
                                        "window_dominance",
                                        prev_key,
                                        prev_conf,
                                        new_conf,
                                        "persistent_conflict",
                                        now,
                                    ),
                                )

    def resolve_contradictions(self):
        with self.db_lock:
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE behavior_patterns
                    SET archived=1
                    WHERE archived=0
                      AND confidence < 0.25
                      AND observation_count <= 2
                    """
                )

    def get_vault_truth(self, min_confidence: float = 0.85, limit: int = 50):
        with self.db_lock:
            cur = self.conn.cursor()
            cur.execute(
                "SELECT pattern_type, key, value, confidence, observation_count FROM behavior_patterns WHERE confidence>=? AND archived=0 ORDER BY confidence DESC, observation_count DESC LIMIT ?",
                (min_confidence, limit),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_consolidated_patterns(self):
        with self.db_lock:
            cur = self.conn.cursor()
            cur.execute("SELECT * FROM behavior_patterns WHERE confidence >= 0.65 AND archived=0")
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def compact_memory(self):
        self.apply_decay()
        self.promote_patterns()
        with self.db_lock:
            with self.conn:
                self.conn.execute(
                    "UPDATE behavior_patterns SET archived=1 WHERE confidence<? OR days_since_reinforcement>45",
                    (0.35,),
                )

    def shutdown(self):
        try:
            if hasattr(self, "compactor") and self.compactor:
                self.compactor.stop()
        except Exception:
            pass
        try:
            self.executor.shutdown(wait=True, cancel_futures=False)
        except Exception:
            pass
        try:
            with self.db_lock:
                self.conn.close()
        except Exception:
            pass

