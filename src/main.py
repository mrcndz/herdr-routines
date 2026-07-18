#!/usr/bin/env python3
"""herdr-routines: cron for commands inside Herdr. See README.md.

Usage: main.py <daemon|start|stop|status|validate|list|run <name>>
"""

import sys

if sys.version_info < (3, 11):  # tomllib
    sys.exit(f"herdr-routines needs Python 3.11+ "
             f"(found {sys.version_info.major}.{sys.version_info.minor})")

from datetime import datetime

import daemon
from config import CONFIG_PATH, ConfigError, load_config
from runner import fire
from state import load_state


def schedule_text(r) -> str:
    return r.get("cron") or f'every {r["every"]}'


def cmd_status() -> int:
    pid = daemon.daemon_pid()
    print(f"daemon: {f'running (pid {pid})' if pid else 'stopped'}")
    try:
        _, routines, _ = load_config(CONFIG_PATH)
    except ConfigError as e:
        print(f"config: INVALID\n{e}")
        return 1
    state = load_state()
    for r in routines:
        name = r["name"]
        last = state["last_fire"].get(name, "never")
        flags = []
        if not r["enabled"]:
            flags.append("disabled")
        if name in state["last_error"]:
            flags.append(f'last error: {state["last_error"][name]}')
        sched = schedule_text(r)
        print(f"  {name:24} [{sched}]  last: {last}"
              + (f"  ({'; '.join(flags)})" if flags else ""))
    return 0


def cmd_validate() -> int:
    try:
        _, routines, warnings = load_config(CONFIG_PATH)
    except ConfigError as e:
        print(e)
        return 1
    for w in warnings:
        print(f"warning: {w}")
    print(f"0 errors, {len(routines)} routine(s) loaded")
    return 0


def cmd_list() -> int:
    try:
        _, routines, _ = load_config(CONFIG_PATH)
    except ConfigError as e:
        print(e)
        return 1
    for r in routines:
        sched = schedule_text(r)
        desc = f'  — {r["description"]}' if r.get("description") else ""
        print(f'{r["name"]:24} {r["_type"]:13} [{sched}]{desc}')
    return 0


def cmd_run(name: str) -> int:
    try:
        settings, routines, _ = load_config(CONFIG_PATH)
    except ConfigError as e:
        print(e)
        return 1
    for r in routines:
        if r["name"] == name:
            fire(r, settings, datetime.now().replace(second=0, microsecond=0), False)
            return 0
    print(f'no routine named "{name}"')
    return 1


def main() -> int:
    args = sys.argv[1:]
    commands = {
        "daemon": daemon.run,
        "start": daemon.start,
        "stop": daemon.stop,
        "status": cmd_status,
        "validate": cmd_validate,
        "list": cmd_list,
    }
    if len(args) == 1 and args[0] in commands:
        return commands[args[0]]()
    if len(args) == 2 and args[0] == "run":
        return cmd_run(args[1])
    print(__doc__.strip())
    return 2


if __name__ == "__main__":
    sys.exit(main())
