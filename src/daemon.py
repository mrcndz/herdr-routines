"""The scheduler daemon: tick loop, config reload, pidfile lifecycle."""

import os
import signal
import subprocess
import sys
import time
from datetime import datetime

from config import CONFIG_PATH, ConfigError, load_config, state_dir
from runner import fire
from schedule import due
from state import load_state, log, update_state

TICK_SECONDS = 15


def daemon_pid():
    pidfile = state_dir() / "daemon.pid"

    if pidfile.exists():
        try:
            pid = int(pidfile.read_text().strip())
            os.kill(pid, 0)
            return pid
        except (OSError, ValueError):
            pass

    return None


class Daemon:
    def __init__(self):
        self.settings = None
        self.routines = None
        self.mtime = None

    def reload_config_if_changed(self) -> None:
        mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.exists() else None

        if mtime == self.mtime:
            return
        self.mtime = mtime

        try:
            self.settings, self.routines, warnings = load_config(CONFIG_PATH)
        except ConfigError as e:
            log(f"config invalid, keeping previous: {e}")
            return

        for w in warnings:
            log(f"warning: {w}")
        log(f"config loaded: {len(self.routines)} routine(s)")

    def seed_countdown(self, routine: dict, now: datetime) -> bool:
        """First sight of an `every` routine starts its countdown."""
        if not routine["_every"]:
            return False

        if routine["name"] in load_state()["last_fire"]:
            return False

        update_state(lambda s: s["last_fire"].update({routine["name"]: now.isoformat()}))
        return True

    def fire_if_due(self, routine: dict, now: datetime) -> None:
        hit = due(routine, load_state()["last_fire"].get(routine["name"]), now)
        if not hit:
            return

        scheduled, late = hit
        # persisted before launching: no double-fire
        update_state(lambda s: s["last_fire"].update({routine["name"]: scheduled.isoformat()}))

        fire(routine, self.settings, scheduled, late)

    def tick(self) -> None:
        self.reload_config_if_changed()
        now = datetime.now()

        for routine in self.routines or []:
            if not self.seed_countdown(routine, now):
                self.fire_if_due(routine, now)

    def loop(self) -> None:
        while True:
            try:
                self.tick()
            except Exception as e:  # the daemon must survive anything
                log(f"tick error: {e}")
            time.sleep(TICK_SECONDS)


def run() -> int:
    """The foreground daemon loop (the `daemon` subcommand)."""
    pidfile = state_dir() / "daemon.pid"

    if daemon_pid():
        print("daemon already running")
        return 1

    pidfile.write_text(str(os.getpid()))
    log(f"daemon started (pid {os.getpid()}, config {CONFIG_PATH})")
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    try:
        Daemon().loop()
    finally:
        pidfile.unlink(missing_ok=True)
        log("daemon stopped")

    return 0


def start() -> int:
    """Spawn the daemon detached, logging to the state dir."""
    if daemon_pid():
        print("daemon already running")
        return 0

    logf = open(state_dir() / "daemon.log", "a")
    subprocess.Popen([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py"), "daemon"],
                     stdout=logf, stderr=logf, start_new_session=True)

    print(f"daemon starting (log: {state_dir() / 'daemon.log'})")

    return 0


def stop() -> int:
    pid = daemon_pid()

    if not pid:
        print("daemon not running")
        return 1
    try:
        os.kill(pid, signal.SIGTERM)
        print("daemon stopped")
    except OSError:
        (state_dir() / "daemon.pid").unlink(missing_ok=True)
        print("daemon not running (removed stale pidfile)")
        return 1

    return 0
