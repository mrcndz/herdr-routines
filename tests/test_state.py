import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import state_dir
from state import append_run, load_state, save_state, update_state


class StateBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = patch.dict(os.environ,
                             {"HERDR_PLUGIN_STATE_DIR": self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)


class TestLoadState(StateBase):
    def test_missing_file_returns_default(self):
        s = load_state()
        self.assertEqual(s, {"last_fire": {}, "tabs": {}, "last_error": {}})

    def test_corrupted_json_returns_default(self):
        (state_dir() / "state.json").write_bytes(b"\x00\x01garbage{not json")
        s = load_state()
        self.assertEqual(s, {"last_fire": {}, "tabs": {}, "last_error": {}})

    def test_missing_keys_in_stored_state_are_not_backfilled(self):
        # load_state only supplies the default dict when the file is
        # absent/unreadable; a valid-but-partial JSON file is returned as-is
        (state_dir() / "state.json").write_text(json.dumps({"tabs": {}}))
        s = load_state()
        self.assertEqual(s, {"tabs": {}})
        self.assertNotIn("last_fire", s)


class TestSaveState(StateBase):
    def test_atomic_write_leaves_no_tmp_file(self):
        save_state({"last_fire": {"a": "x"}, "tabs": {}, "last_error": {}})
        p = state_dir()
        self.assertTrue((p / "state.json").exists())
        self.assertFalse((p / "state.json.tmp").exists())

    def test_round_trip(self):
        state = {"last_fire": {"a": "2026-07-18T09:00:00"}, "tabs": {}, "last_error": {}}
        save_state(state)
        self.assertEqual(load_state(), state)


class TestUpdateState(StateBase):
    def test_mutation_is_visible_after_update(self):
        update_state(lambda s: s["last_fire"].update({"r": "t"}))
        self.assertEqual(load_state()["last_fire"]["r"], "t")

    def test_mutation_persisted_across_calls(self):
        update_state(lambda s: s["tabs"].update({"a": 1}))
        update_state(lambda s: s["tabs"].update({"b": 2}))
        self.assertEqual(load_state()["tabs"], {"a": 1, "b": 2})


class TestAppendRun(StateBase):
    def test_trims_at_exactly_max_log_lines(self):
        settings = {"max_log_lines": 3}
        for i in range(5):
            append_run(settings, {"i": i})
        p = state_dir() / "runs.jsonl"
        lines = [json.loads(l) for l in p.read_text().splitlines()]
        self.assertEqual([l["i"] for l in lines], [2, 3, 4])

    def test_max_log_lines_of_one_keeps_only_latest(self):
        settings = {"max_log_lines": 1}
        for i in range(3):
            append_run(settings, {"i": i})
        p = state_dir() / "runs.jsonl"
        lines = [json.loads(l) for l in p.read_text().splitlines()]
        self.assertEqual([l["i"] for l in lines], [2])

    def test_first_append_creates_file(self):
        settings = {"max_log_lines": 100}
        append_run(settings, {"i": 0})
        p = state_dir() / "runs.jsonl"
        self.assertTrue(p.exists())
        self.assertEqual(json.loads(p.read_text().splitlines()[0]), {"i": 0})


if __name__ == "__main__":
    unittest.main()
