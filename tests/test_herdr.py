import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import herdr as herdr_mod
from herdr import resolve_tab, resolve_workspace
from state import save_state

SETTINGS = {"workspace": "routines"}
NOW = datetime(2026, 7, 18, 9, 0)


def routine(**kw):
    r = {"name": "t", "workspace_mode": "reuse"}
    r.update(kw)
    return r


def fake_herdr(existing_labels):
    """Stub of the herdr CLI: workspace list/create only."""
    def _call(*args, **kw):
        if args[:2] == ("workspace", "list"):
            return {"workspaces": [
                {"workspace_id": f"w{i}", "label": lbl}
                for i, lbl in enumerate(existing_labels, 1)]}
        if args[:2] == ("workspace", "create"):
            label = args[args.index("--label") + 1]
            return {"workspace": {"workspace_id": f"new:{label}"}}
        raise AssertionError(f"unexpected herdr call: {args}")
    return _call


class TestResolveWorkspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = patch.dict(os.environ,
                             {"HERDR_PLUGIN_STATE_DIR": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def resolve(self, r, labels):
        with patch.object(herdr_mod, "herdr", side_effect=fake_herdr(labels)):
            return resolve_workspace(r, SETTINGS, NOW)

    def test_reuse_exists_returns_id(self):
        r = routine(workspace="routines")
        self.assertEqual(self.resolve(r, ["routines"]), "w1")

    def test_reuse_missing_creates(self):
        r = routine(workspace="routines")
        self.assertEqual(self.resolve(r, []), "new:routines")

    def test_create_always_creates_with_timestamped_label(self):
        r = routine(workspace="exp", workspace_mode="create")
        self.assertEqual(self.resolve(r, ["exp"]), "new:exp-20260718-0900")

    def test_require_exists_returns_id(self):
        r = routine(workspace="maint", workspace_mode="require")
        self.assertEqual(self.resolve(r, ["maint"]), "w1")

    def test_require_missing_raises(self):
        r = routine(workspace="maint", workspace_mode="require")
        with self.assertRaises(RuntimeError):
            self.resolve(r, [])

    def test_workspace_id_listed_returns_id(self):
        r = routine(workspace_id="w2", workspace_mode="require")
        self.assertEqual(self.resolve(r, ["a", "b"]), "w2")

    def test_workspace_id_missing_raises(self):
        r = routine(workspace_id="w9", workspace_mode="require")
        with self.assertRaises(RuntimeError):
            self.resolve(r, ["a", "b"])


def fake_herdr_tabs(pane, calls):
    """Stub for resolve_tab: pane get, tab close, tab create."""
    def _call(*args, **kw):
        calls.append(args)
        if args[:2] == ("pane", "get"):
            return {"pane": pane}
        if args[:2] == ("tab", "close"):
            return {}
        if args[:2] == ("tab", "create"):
            return {"root_pane": {"pane_id": "wT:pNew"},
                    "tab": {"tab_id": "wT:tNew"}}
        raise AssertionError(f"unexpected herdr call: {args}")
    return _call


class TestResolveTab(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = patch.dict(os.environ,
                             {"HERDR_PLUGIN_STATE_DIR": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        save_state({"last_fire": {}, "last_error": {},
                    "tabs": {"t": {"pane_id": "wT:p1", "tab_id": "wT:t1"}}})

    def resolve(self, pane):
        calls = []
        r = {"name": "t", "tab_mode": "reuse", "cwd": "~"}
        with patch.object(herdr_mod, "herdr",
                          side_effect=fake_herdr_tabs(pane, calls)):
            result = resolve_tab(r, "wT")
        return result, calls

    def test_reuse_plain_shell_pane(self):
        (pane_id, _), calls = self.resolve(
            {"workspace_id": "wT", "agent": None, "agent_status": "unknown"})
        self.assertEqual(pane_id, "wT:p1")
        self.assertNotIn(("tab", "close", "wT:t1"), calls)

    def test_reuse_working_agent_returned_for_overlap_check(self):
        (pane_id, pane), _ = self.resolve(
            {"workspace_id": "wT", "agent": "claude", "agent_status": "working"})
        self.assertEqual(pane_id, "wT:p1")
        self.assertEqual(pane["agent_status"], "working")

    def test_reuse_finished_agent_recreates_tab(self):
        (pane_id, _), calls = self.resolve(
            {"workspace_id": "wT", "agent": "claude", "agent_status": "idle"})
        self.assertEqual(pane_id, "wT:pNew")
        self.assertIn(("tab", "close", "wT:t1"), calls)


if __name__ == "__main__":
    unittest.main()
