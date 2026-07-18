import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import runner
from state import load_state

SETTINGS = {"shell": "/bin/sh", "workspace": "routines", "max_log_lines": 1000}


def routine(**kw):
    r = {"name": "t", "_type": "pane", "_cron": None, "_every": None,
         "workspace_mode": "reuse", "tab_mode": "reuse", "cwd": "~"}
    r.update(kw)
    return r


class RunnerBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = patch.dict(os.environ,
                             {"HERDR_PLUGIN_STATE_DIR": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.now = datetime(2026, 7, 18, 9, 0)

    def runs(self):
        p = Path(self.tmp.name) / "runs.jsonl"
        if not p.exists():
            return []
        return [json.loads(l) for l in p.read_text().splitlines()]


class TestPaneRoutine(RunnerBase):
    @patch("runner.resolve_tab", return_value=("p1", None))
    @patch("runner.resolve_workspace", return_value="w1")
    @patch("runner.herdr")
    def test_close_when_done_appends_exit(self, herdr, *_):
        r = routine(command="echo hi", close_when_done=True)
        runner.fire(r, SETTINGS, self.now, False)
        herdr.assert_called_once_with("pane", "run", "p1", "echo hi; exit")

    @patch("runner.resolve_tab", return_value=("p1", None))
    @patch("runner.resolve_workspace", return_value="w1")
    @patch("runner.herdr")
    def test_argv_command_is_shlex_quoted(self, herdr, *_):
        r = routine(command=["python3", "script.py", "two words"])
        runner.fire(r, SETTINGS, self.now, False)
        sent = herdr.call_args[0][3]
        self.assertEqual(sent, "python3 script.py 'two words'")

    @patch("runner.resolve_tab",
           return_value=("p1", {"agent_status": "working"}))
    @patch("runner.resolve_workspace", return_value="w1")
    @patch("runner.herdr")
    def test_overlap_skipped(self, herdr, *_):
        r = routine(command="claude x")
        runner.fire(r, SETTINGS, self.now, False)
        herdr.assert_not_called()
        self.assertEqual(self.runs()[-1]["outcome"], "overlap-skipped")


class TestPreGuard(RunnerBase):
    @patch("runner.notify")
    @patch("runner.resolve_workspace")
    @patch("runner.herdr")
    def test_pre_failure_aborts_and_notifies(self, herdr, resolve_ws, notify):
        r = routine(command="echo hi", pre="exit 1", notify=True)
        runner.fire(r, SETTINGS, self.now, False)
        resolve_ws.assert_not_called()
        herdr.assert_not_called()
        notify.assert_called_once_with(r, "routine skipped: t",
                                       "pre guard failed")
        self.assertEqual(self.runs()[-1]["outcome"], "pre-skipped")
        self.assertEqual(load_state()["last_error"]["t"], "pre guard failed")


class TestShellRoutine(RunnerBase):
    def test_exit_zero_is_finished_and_post_runs(self):
        marker = Path(self.tmp.name) / "post-ran"
        r = routine(_type="shell", command="true", post=f"touch {marker}")
        runner.fire(r, SETTINGS, self.now, False)
        self.assertEqual(self.runs()[-1]["outcome"], "finished")
        self.assertTrue(marker.exists())

    def test_nonzero_exit_recorded(self):
        r = routine(_type="shell", command="exit 3")
        runner.fire(r, SETTINGS, self.now, False)
        self.assertEqual(self.runs()[-1]["outcome"], "exit 3")


class TestErrorPath(RunnerBase):
    @patch("runner.resolve_workspace",
           side_effect=RuntimeError("workspace w3 not found"))
    def test_error_sets_last_error(self, _):
        r = routine(command="echo hi")
        runner.fire(r, SETTINGS, self.now, False)
        self.assertEqual(self.runs()[-1]["outcome"], "error")
        self.assertEqual(load_state()["last_error"]["t"],
                         "workspace w3 not found")


class TestRunLog(RunnerBase):
    @patch("runner.resolve_tab", return_value=("p1", None))
    @patch("runner.resolve_workspace", return_value="w1")
    @patch("runner.herdr")
    def test_entry_has_required_fields(self, *_):
        r = routine(command="echo hi")
        runner.fire(r, SETTINGS, self.now, True)
        entry = self.runs()[-1]
        self.assertEqual(entry["routine"], "t")
        self.assertEqual(entry["scheduled"], "2026-07-18T09:00")
        self.assertTrue(entry["late"])
        self.assertEqual(entry["outcome"], "started")


if __name__ == "__main__":
    unittest.main()
