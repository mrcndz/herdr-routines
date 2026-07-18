"""Durable state (state.json, runs.jsonl) and logging."""

import json
from datetime import datetime

from config import state_dir


def log(msg: str) -> None:
    print(f"{datetime.now().isoformat(timespec='seconds')} {msg}", flush=True)


def load_state() -> dict:
    p = state_dir() / "state.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            pass
    return {"last_fire": {}, "tabs": {}, "last_error": {}}


def _write_atomic(path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def save_state(state: dict) -> None:
    _write_atomic(state_dir() / "state.json", json.dumps(state, indent=1))


def update_state(mutate) -> None:
    state = load_state()
    mutate(state)
    save_state(state)


def append_run(settings: dict, entry: dict) -> None:
    p = state_dir() / "runs.jsonl"
    lines = p.read_text().splitlines() if p.exists() else []
    lines.append(json.dumps(entry))
    lines = lines[-int(settings["max_log_lines"]):]
    _write_atomic(p, "\n".join(lines) + "\n")
