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


class TestTickNoConfig(DaemonBase):
    def test_tick_with_no_config_file_does_nothing(self):
        d = Daemon()
        with patch.object(daemon_mod, "CONFIG_PATH", Path(self.tmp.name) / "nope.toml"), \
                patch.object(daemon_mod, "fire") as fire:
            d.tick()
        self.assertIsNone(d.routines)
        fire.assert_not_called()

    def test_config_appearing_later_is_picked_up(self):
        cfg = Path(self.tmp.name) / "routines.toml"
        d = Daemon()
        with patch.object(daemon_mod, "CONFIG_PATH", cfg), patch.object(daemon_mod, "fire"):
            d.tick()
            self.assertIsNone(d.routines)
            cfg.write_text(VALID_TOML)
            d.tick()
            self.assertEqual(len(d.routines), 1)


class TestOrphanLastFire(DaemonBase):
    def test_routine_removed_mid_run_keeps_orphan_last_fire(self):
        # once a routine disappears from config, its last_fire entry is
        # simply never touched again; it lingers in state.json forever
        d = Daemon()
        d.settings = {"max_log_lines": 1000}
        r = routine(cron="0 9 * * *")
        with patch.object(daemon_mod, "fire"):
            d.fire_if_due(r, datetime(2026, 7, 18, 9, 0))
        self.assertIn("t", load_state()["last_fire"])
        # routine "t" removed from config; ticking with the empty list
        # never touches last_fire["t"] again, so it remains as an orphan
        d.routines = []
        with patch.object(daemon_mod, "CONFIG_PATH", Path(self.tmp.name) / "nope.toml"):
            d.tick()
        self.assertIn("t", load_state()["last_fire"])


class TestTrimLog(DaemonBase):
    def test_trim_log_noop_under_threshold(self):
        p = Path(self.tmp.name) / "daemon.log"
        p.write_text("small\n")
        daemon_mod._trim_log(p, max_bytes=1000, keep_lines=10)
        self.assertEqual(p.read_text(), "small\n")

    def test_trim_log_trims_over_threshold(self):
        p = Path(self.tmp.name) / "daemon.log"
        p.write_text("\n".join(f"line{i}" for i in range(100)) + "\n")
        daemon_mod._trim_log(p, max_bytes=10, keep_lines=5)
        lines = p.read_text().splitlines()
        self.assertEqual(lines, [f"line{i}" for i in range(95, 100)])

    def test_trim_log_missing_file_noop(self):
        p = Path(self.tmp.name) / "missing.log"
        daemon_mod._trim_log(p)  # must not raise


class TestClaimPidfile(DaemonBase):
    def test_stale_pidfile_is_reclaimed(self):
        pidfile = Path(self.tmp.name) / "daemon.pid"
        pidfile.write_text("999999999")  # bogus pid, cannot exist
        with patch.object(daemon_mod, "state_dir", return_value=Path(self.tmp.name)):
            self.assertTrue(daemon_mod._claim_pidfile(pidfile))
        self.assertEqual(pidfile.read_text(), str(os.getpid()))

    def test_live_our_daemon_pidfile_blocks_claim(self):
        pidfile = Path(self.tmp.name) / "daemon.pid"
        pidfile.write_text(str(os.getpid()))
        with patch.object(daemon_mod, "daemon_pid", return_value=os.getpid()):
            self.assertFalse(daemon_mod._claim_pidfile(pidfile))


class TestDaemonPid(DaemonBase):
    def test_pid_le_1_in_file_is_never_trusted(self):
        pidfile = Path(self.tmp.name) / "daemon.pid"
        pidfile.write_text("1")
        with patch.object(daemon_mod, "state_dir", return_value=Path(self.tmp.name)):
            self.assertIsNone(daemon_mod.daemon_pid())

    def test_pid_zero_in_file_is_never_trusted(self):
        pidfile = Path(self.tmp.name) / "daemon.pid"
        pidfile.write_text("0")
        with patch.object(daemon_mod, "state_dir", return_value=Path(self.tmp.name)):
            self.assertIsNone(daemon_mod.daemon_pid())

    def test_no_pidfile_returns_none(self):
        with patch.object(daemon_mod, "state_dir", return_value=Path(self.tmp.name)):
            self.assertIsNone(daemon_mod.daemon_pid())


if __name__ == "__main__":
    unittest.main()
