"""Config loading and validation, plugin directory resolution."""

import os
import subprocess
import tomllib
from pathlib import Path

from schedule import Cron, parse_every

HERDR = os.environ.get("HERDR_BIN_PATH", "herdr")
PLUGIN_ID = "herdr-routines"

TYPES = ("shell", "pane", "plugin_action")
PANE_ONLY_KEYS = ("workspace", "workspace_id", "workspace_mode", "tab_mode",
                  "focus", "close_when_done")


class ConfigError(Exception):
    pass


def config_dir() -> Path:
    d = os.environ.get("HERDR_PLUGIN_CONFIG_DIR")
    if d:
        return Path(d)
    try:
        out = subprocess.run([HERDR, "plugin", "config-dir", PLUGIN_ID],
                             capture_output=True, text=True, timeout=10)
        line = out.stdout.strip()
        if out.returncode == 0 and line:
            return Path(line)
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.home() / ".config" / "herdr" / "plugins" / "config" / PLUGIN_ID


def state_dir() -> Path:
    d = os.environ.get("HERDR_PLUGIN_STATE_DIR")
    # fallback mirrors the dir Herdr injects as HERDR_PLUGIN_STATE_DIR
    p = Path(d) if d else Path.home() / ".local" / "state" / "herdr" / "plugins" / PLUGIN_ID
    p.mkdir(parents=True, exist_ok=True)
    return p


CONFIG_PATH = config_dir() / "routines.toml"


def load_config(path: Path = CONFIG_PATH):
    """Returns (settings, routines, warnings). Raises ConfigError."""
    if not path.exists():
        raise ConfigError(f"{path}: not found")

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path.name}: {e}") from e

    settings = data.get("settings", {})
    settings.setdefault("shell", os.environ.get("SHELL", "/bin/sh"))
    settings.setdefault("workspace", "routines")
    settings.setdefault("max_log_lines", 1000)

    routines, errors, warnings = [], [], []
    seen = set()

    for r in data.get("routine", []):
        name = r.get("name")
        err = lambda m: errors.append(f'routine "{name or "?"}": {m}')

        if not name:
            err("missing `name`")
            continue

        if name in seen:
            err("duplicate name")
            continue

        seen.add(name)

        if r.get("cron") and r.get("every"):
            err("set either `cron` or `every`, not both")
            continue
        if not r.get("cron") and not r.get("every"):
            err("missing schedule: set `cron` or `every`")
            continue
        try:
            r["_cron"] = Cron(r["cron"]) if r.get("cron") else None
            r["_every"] = parse_every(r["every"]) if r.get("every") else None
        except ValueError as e:
            err(str(e))
            continue

        rtype = r.get("type")

        if not rtype:
            rtype = "plugin_action" if r.get("action") else "pane"
        if rtype not in TYPES:
            err(f"unknown type {rtype!r}")
            continue
        # explicit type must be consistent with the keys present
        if r.get("type") in ("pane", "shell") and r.get("action"):
            err(f'`action` not allowed on type {r["type"]}')
            continue
        if r.get("type") == "plugin_action" and r.get("command"):
            err("`command` not allowed on type plugin_action")
            continue
        if rtype == "plugin_action" and not r.get("action"):
            err("type plugin_action needs `action`")
            continue
        if rtype != "plugin_action" and not r.get("command"):
            err("missing `command`")
            continue
        if rtype in ("shell", "plugin_action"):
            bad = [k for k in PANE_ONLY_KEYS if k in r]
            if bad:
                err(f"keys {bad} not allowed on type {rtype}")
                continue
        if rtype == "pane" and r.get("post"):
            err("`post` not allowed on pane routines; chain `command && post`")
            continue
        if r.get("workspace") and r.get("workspace_id"):
            err("`workspace` and `workspace_id` are exclusive")
            continue
        if r.get("workspace_id"):
            r["workspace_mode"] = "require"
        if r.get("workspace_mode", "reuse") not in ("reuse", "create", "require"):
            err(f'bad workspace_mode {r["workspace_mode"]!r}')
            continue
        if r.get("tab_mode", "reuse") not in ("reuse", "create"):
            err(f'bad tab_mode {r["tab_mode"]!r}')
            continue
        if r.get("catch_up") and r["_every"]:
            warnings.append(f'routine "{name}": `catch_up` is meaningless with `every`')
        r["_type"] = rtype
        # normalize defaults so consumers can use plain indexing
        r.setdefault("workspace_mode", "reuse")
        r.setdefault("tab_mode", "reuse")
        r.setdefault("enabled", True)
        r.setdefault("cwd", "~")
        routines.append(r)

    if errors:
        raise ConfigError("\n".join(f"{path.name}: {e}" for e in errors)
                          + f"\n{len(errors)} error(s), 0 routines loaded")

    return settings, routines, warnings
