"""Herdr CLI wrapper and workspace/tab resolution."""

import json
import os
import subprocess
from datetime import datetime

from config import HERDR
from state import load_state, update_state


def herdr(*args, timeout=30):
    """Run a herdr CLI command; return the parsed JSON `result` object."""
    proc = subprocess.run([HERDR, *args], capture_output=True, text=True,
                          timeout=timeout)
    out = proc.stdout.strip()
    if proc.returncode != 0:
        raise RuntimeError(f"herdr {' '.join(args)} failed: {out or proc.stderr.strip()}")
    for line in out.splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "result" in data:
            return data["result"]
    return {}


def find_workspace(label: str):
    for ws in herdr("workspace", "list").get("workspaces", []):
        if ws.get("label") == label:
            return ws["workspace_id"]
    return None


def resolve_workspace(routine: dict, settings: dict, now: datetime) -> str:
    mode = routine["workspace_mode"]
    if routine.get("workspace_id"):
        ids = [w["workspace_id"]
               for w in herdr("workspace", "list").get("workspaces", [])]
        if routine["workspace_id"] not in ids:
            raise RuntimeError(f'workspace {routine["workspace_id"]} not found')
        return routine["workspace_id"]
    label = routine.get("workspace", settings["workspace"])
    if mode == "create":
        label = f"{label}-{now.strftime('%Y%m%d-%H%M')}"
        return herdr("workspace", "create", "--label", label)["workspace"]["workspace_id"]
    ws_id = find_workspace(label)
    if ws_id:
        return ws_id
    if mode == "require":
        raise RuntimeError(f'workspace "{label}" not found (mode=require)')
    return herdr("workspace", "create", "--label", label)["workspace"]["workspace_id"]


def resolve_tab(routine: dict, ws_id: str):
    """Find-or-create the routine's tab; returns (pane_id, pane_info|None)."""
    name = routine["name"]
    if routine["tab_mode"] == "reuse":
        known = load_state()["tabs"].get(name)
        if known:
            try:
                pane = herdr("pane", "get", known["pane_id"]).get("pane")
                if pane and pane["workspace_id"] == ws_id:
                    if not pane.get("agent"):
                        return known["pane_id"], pane
                    if pane.get("agent_status") == "working":
                        return known["pane_id"], pane
                    # finished agent occupies the pane: typing a command
                    # would go into its prompt box — recreate the tab
                    herdr("tab", "close", known["tab_id"])
            except RuntimeError:
                pass
        label = name
    else:
        label = f"{name}-{datetime.now().strftime('%H%M')}"
    focus = "--focus" if routine.get("focus") else "--no-focus"
    res = herdr("tab", "create", "--workspace", ws_id, "--label", label, focus,
                "--cwd", os.path.expanduser(routine["cwd"]))
    pane_id = res["root_pane"]["pane_id"]
    update_state(lambda s: s["tabs"].update(
        {name: {"pane_id": pane_id, "tab_id": res["tab"]["tab_id"]}}))
    return pane_id, None
