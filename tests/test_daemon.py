import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import daemon as daemon_mod
from daemon import Daemon
from schedule import Cron, parse_every
from state import load_state

VALID_TOML = """
[[routine]]
name = "tick"
type = "shell"
every = "1h"
command = "true"
"""


def routine(**kw):
    r = {"name": "t", "_cron": None, "_every": None, "enabled": True}
    if "cron" in kw:
        r["_cron"] = Cron(kw.pop("cron"))
    if "every" in kw:
        r["_every"] = parse_every(kw.pop("every"))
    r.update(kw)
    return r


class DaemonBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = patch.dict(os.environ,
                             {"HERDR_PLUGIN_STATE_DIR": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)


class TestConfigReload(DaemonBase):
    def test_invalid_edit_keeps_last_good(self):
        cfg = Path(self.tmp.name) / "routines.toml"
        cfg.write_text(VALID_TOML)
        with patch.object(daemon_mod, "CONFIG_PATH", cfg), \
                patch.object(daemon_mod, "fire"):
            d = Daemon()
            d.tick()
            self.assertEqual(len(d.routines), 1)
            good = d.routines
            cfg.write_text("[[routine]\nbroken =")
            os.utime(cfg, (0, 0))  # force a different mtime
            d.tick()
            self.assertIs(d.routines, good)


class TestFireIfDue(DaemonBase):
    def test_last_fire_persisted_before_fire_runs(self):
        d = Daemon()
        d.settings = {"max_log_lines": 1000}
        r = routine(cron="0 9 * * *")
        now = datetime(2026, 7, 18, 9, 0, 10)
        with patch.object(daemon_mod, "fire", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                d.fire_if_due(r, now)
        # last_fire was persisted despite fire() crashing: no double-fire
        self.assertEqual(load_state()["last_fire"]["t"], "2026-07-18T09:00:00")

    def test_not_due_does_not_fire(self):
        d = Daemon()
        r = routine(cron="0 9 * * *")
        with patch.object(daemon_mod, "fire") as fire:
            d.fire_if_due(r, datetime(2026, 7, 18, 9, 1))
        fire.assert_not_called()


class TestSeedCountdown(DaemonBase):
    def test_first_sight_seeds_without_firing(self):
        d = Daemon()
        d.settings = {"max_log_lines": 1000}
        d.routines = [routine(every="30m")]
        now = datetime(2026, 7, 18, 9, 0)
        with patch.object(daemon_mod, "fire") as fire:
            self.assertTrue(d.seed_countdown(d.routines[0], now))
        fire.assert_not_called()
        self.assertEqual(load_state()["last_fire"]["t"], now.isoformat())

    def test_second_sight_does_not_reseed(self):
        d = Daemon()
        r = routine(every="30m")
        now = datetime(2026, 7, 18, 9, 0)
        self.assertTrue(d.seed_countdown(r, now))
        self.assertFalse(d.seed_countdown(r, datetime(2026, 7, 18, 9, 5)))
        self.assertEqual(load_state()["last_fire"]["t"], now.isoformat())


if __name__ == "__main__":
    unittest.main()
