import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import ConfigError, load_config


def write(content: str) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


def load(content: str):
    return load_config(write(content))


class TestLoadConfig(unittest.TestCase):
    def test_minimal_routine(self):
        settings, routines, warnings = load("""
            [[routine]]
            name = "tick"
            every = "1h"
            command = "date"
        """)
        self.assertEqual(len(routines), 1)
        self.assertEqual(routines[0]["_type"], "pane")
        self.assertEqual(warnings, [])

    def test_settings_defaults(self):
        settings, _, _ = load("""
            [[routine]]
            name = "t"
            every = "1h"
            command = "date"
        """)
        self.assertEqual(settings["workspace"], "routines")
        self.assertEqual(settings["max_log_lines"], 1000)
        self.assertTrue(settings["shell"])

    def test_type_inference(self):
        _, routines, _ = load("""
            [[routine]]
            name = "a"
            every = "1h"
            command = "date"

            [[routine]]
            name = "b"
            every = "1h"
            action = "x.y"
        """)
        self.assertEqual(routines[0]["_type"], "pane")
        self.assertEqual(routines[1]["_type"], "plugin_action")

    def test_cron_and_every_exclusive(self):
        with self.assertRaisesRegex(ConfigError, "not both"):
            load("""
                [[routine]]
                name = "t"
                cron = "0 9 * * *"
                every = "1h"
                command = "date"
            """)

    def test_neither_cron_nor_every(self):
        with self.assertRaisesRegex(ConfigError, "missing schedule: set `cron` or `every`"):
            load("""
                [[routine]]
                name = "t"
                command = "date"
            """)

    def test_explicit_pane_type_rejects_action(self):
        with self.assertRaisesRegex(ConfigError, "`action` not allowed on type pane"):
            load("""
                [[routine]]
                name = "t"
                type = "pane"
                every = "1h"
                command = "date"
                action = "x.y"
            """)

    def test_explicit_plugin_action_type_rejects_command(self):
        with self.assertRaisesRegex(ConfigError, "`command` not allowed on type plugin_action"):
            load("""
                [[routine]]
                name = "t"
                type = "plugin_action"
                every = "1h"
                action = "x.y"
                command = "date"
            """)

    def test_errors_accumulate_across_routines(self):
        with self.assertRaises(ConfigError) as ctx:
            load("""
                [[routine]]
                name = "a"
                every = "1h"

                [[routine]]
                name = "b"
                command = "date"
            """)
        msg = str(ctx.exception)
        self.assertIn('routine "a": missing `command`', msg)
        self.assertIn('routine "b": missing schedule', msg)

    def test_missing_name(self):
        with self.assertRaisesRegex(ConfigError, "missing `name`"):
            load("""
                [[routine]]
                every = "1h"
                command = "date"
            """)

    def test_duplicate_name(self):
        with self.assertRaisesRegex(ConfigError, "duplicate"):
            load("""
                [[routine]]
                name = "t"
                every = "1h"
                command = "date"

                [[routine]]
                name = "t"
                every = "2h"
                command = "date"
            """)

    def test_missing_command(self):
        with self.assertRaisesRegex(ConfigError, "missing `command`"):
            load("""
                [[routine]]
                name = "t"
                every = "1h"
            """)

    def test_bad_cron_reported(self):
        with self.assertRaisesRegex(ConfigError, "cron needs 5 fields"):
            load("""
                [[routine]]
                name = "t"
                cron = "0 9 * *"
                command = "date"
            """)

    def test_pane_keys_rejected_on_shell(self):
        with self.assertRaisesRegex(ConfigError, "not allowed on type shell"):
            load("""
                [[routine]]
                name = "t"
                type = "shell"
                every = "1h"
                command = "date"
                workspace = "x"
            """)

    def test_post_rejected_on_pane(self):
        with self.assertRaisesRegex(ConfigError, "`post` not allowed"):
            load("""
                [[routine]]
                name = "t"
                every = "1h"
                command = "date"
                post = "echo done"
            """)

    def test_post_allowed_on_shell(self):
        _, routines, _ = load("""
            [[routine]]
            name = "t"
            type = "shell"
            every = "1h"
            command = "date"
            post = "echo done"
        """)
        self.assertEqual(routines[0]["post"], "echo done")

    def test_workspace_and_id_exclusive(self):
        with self.assertRaisesRegex(ConfigError, "exclusive"):
            load("""
                [[routine]]
                name = "t"
                every = "1h"
                command = "date"
                workspace = "x"
                workspace_id = "w3"
            """)

    def test_workspace_id_implies_require(self):
        _, routines, _ = load("""
            [[routine]]
            name = "t"
            every = "1h"
            command = "date"
            workspace_id = "w3"
        """)
        self.assertEqual(routines[0]["workspace_mode"], "require")

    def test_catch_up_with_every_warns(self):
        _, _, warnings = load("""
            [[routine]]
            name = "t"
            every = "1h"
            command = "date"
            catch_up = true
        """)
        self.assertIn("catch_up", warnings[0])

    def test_argv_command_accepted(self):
        _, routines, _ = load("""
            [[routine]]
            name = "t"
            every = "1h"
            command = ["python3", "/x.py"]
        """)
        self.assertEqual(routines[0]["command"], ["python3", "/x.py"])

    def test_missing_file(self):
        with self.assertRaisesRegex(ConfigError, "not found"):
            load_config(Path("/nonexistent/routines.toml"))


if __name__ == "__main__":
    unittest.main()
