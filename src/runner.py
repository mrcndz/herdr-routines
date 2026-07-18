"""The firing pipeline: Pre → Workspace → Tab → Pane → Command → Post."""

import os
import shlex
import subprocess
from datetime import datetime

from herdr import herdr, resolve_tab, resolve_workspace
from state import append_run, load_state, log, save_state


def _shell_run(routine: dict, settings: dict, cmd, timeout: int):
    shell = routine.get("shell", settings["shell"])
    argv = [shell, "-c", cmd] if isinstance(cmd, str) else cmd
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                          cwd=os.path.expanduser(routine.get("cwd", "~")))


def pane_command_text(cmd):
    # Panes always run through a shell; quote argv exactly.
    return shlex.join(cmd) if isinstance(cmd, list) else cmd


def run_hook(routine: dict, settings: dict, hook: str) -> bool:
    """Run pre/post daemon-side. Returns True on success (exit 0)."""
    cmd = routine.get(hook)
    if not cmd:
        return True
    proc = _shell_run(routine, settings, cmd, timeout=600)
    output = f"{proc.stdout.strip()} {proc.stderr.strip()}".strip()
    if output:
        log(f"[{routine['name']}] {hook}: {output}")
    return proc.returncode == 0


def notify(routine: dict, title: str, body: str = "") -> None:
    if not routine.get("notify"):
        return
    try:
        herdr("notification", "show", title, *(["--body", body] if body else []))
    except RuntimeError as e:
        log(f"[{routine['name']}] notify failed: {e}")


def _set_error(name: str, message):
    state = load_state()
    if message is None:
        state["last_error"].pop(name, None)
    else:
        state["last_error"][name] = message
    save_state(state)


def _launch_shell(routine: dict, settings: dict) -> str:
    proc = _shell_run(routine, settings, routine["command"], timeout=3600)
    outcome = "finished" if proc.returncode == 0 else f"exit {proc.returncode}"
    run_hook(routine, settings, "post")
    return outcome


def _launch_pane(routine: dict, settings: dict, scheduled: datetime) -> str:
    ws_id = resolve_workspace(routine, settings, scheduled)
    pane_id, pane = resolve_tab(routine, ws_id)
    if pane and pane.get("agent_status") == "working":
        log(f"[{routine['name']}] previous run still working; skipping")
        return "overlap-skipped"
    cmd = pane_command_text(routine["command"])
    if routine.get("close_when_done"):
        cmd += "; exit"
    herdr("pane", "run", pane_id, cmd)
    return "started"


def _launch_action(routine: dict, settings: dict) -> str:
    herdr("plugin", "action", "invoke", routine["action"])
    run_hook(routine, settings, "post")
    return "finished"


def fire(routine: dict, settings: dict, scheduled: datetime, late: bool) -> None:
    name = routine["name"]
    outcome = "started"
    try:
        if not run_hook(routine, settings, "pre"):
            outcome = "pre-skipped"
            log(f"[{name}] pre guard failed; skipping")
            _set_error(name, "pre guard failed")
            notify(routine, f"routine skipped: {name}", "pre guard failed")
            return
        rtype = routine["_type"]
        if rtype == "plugin_action":
            outcome = _launch_action(routine, settings)
        elif rtype == "shell":
            outcome = _launch_shell(routine, settings)
        else:  # pane
            outcome = _launch_pane(routine, settings, scheduled)
            if outcome == "overlap-skipped":
                return
        _set_error(name, None)
        notify(routine, f"routine fired: {name}")
        log(f"[{name}] fired ({outcome}{', late' if late else ''})")
    except (RuntimeError, subprocess.SubprocessError, OSError) as e:
        outcome = "error"
        log(f"[{name}] error: {e}")
        _set_error(name, str(e))
        notify(routine, f"routine failed: {name}", str(e))
    finally:
        append_run(settings, {
            "routine": name,
            "scheduled": scheduled.isoformat(timespec="minutes"),
            "started": datetime.now().isoformat(timespec="seconds"),
            "late": late, "outcome": outcome,
        })
