"""Cron expression and interval parsing; firing decisions."""

import re
from datetime import datetime, timedelta

CATCH_UP_WINDOW_MIN = 7 * 24 * 60

MONTH_NAMES = {n: i + 1 for i, n in enumerate(
    "jan feb mar apr may jun jul aug sep oct nov dec".split())}
DOW_NAMES = {n: i for i, n in enumerate(
    "sun mon tue wed thu fri sat".split())}


def _parse_field(field: str, lo: int, hi: int, names: dict) -> set:
    values = set()
    for part in field.split(","):
        part = part.strip().lower()
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = int(step_s)
        if part in ("*", ""):
            lo_v, hi_v = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            lo_v = names[a] if a in names else int(a)
            hi_v = names[b] if b in names else int(b)
        else:
            v = names[part] if part in names else int(part)
            lo_v = hi_v = v
        if not (lo <= lo_v <= hi and lo <= hi_v <= hi):
            raise ValueError(f"field value out of range [{lo},{hi}]: {field!r}")
        values.update(range(lo_v, hi_v + 1, step))
    if hi == 7:  # dow: 0 and 7 are both Sunday
        values = {0 if v == 7 else v for v in values}
    return values


class Cron:
    def __init__(self, expr: str):
        fields = expr.split()
        if len(fields) != 5:
            raise ValueError(f"cron needs 5 fields, got {len(fields)}: {expr!r}")
        self.minute = _parse_field(fields[0], 0, 59, {})
        self.hour = _parse_field(fields[1], 0, 23, {})
        self.dom = _parse_field(fields[2], 1, 31, {})
        self.month = _parse_field(fields[3], 1, 12, MONTH_NAMES)
        self.dow = _parse_field(fields[4], 0, 7, DOW_NAMES)
        # standard cron: when BOTH day fields are restricted, either matches;
        # like Vixie cron, a field starting with `*` (incl. */N) counts as
        # unrestricted for this rule
        self.dom_restricted = not fields[2].strip().startswith("*")
        self.dow_restricted = not fields[4].strip().startswith("*")

    def _day_matches(self, dt: datetime) -> bool:
        dom_ok = dt.day in self.dom
        dow_ok = dt.isoweekday() % 7 in self.dow
        if self.dom_restricted and self.dow_restricted:
            return dom_ok or dow_ok
        return dom_ok and dow_ok

    def matches(self, dt: datetime) -> bool:
        return (dt.minute in self.minute and dt.hour in self.hour
                and dt.month in self.month and self._day_matches(dt))

    def most_recent(self, now: datetime):
        """Most recent matching minute ≤ now, within the catch-up window."""
        dt = now.replace(second=0, microsecond=0)
        for _ in range(CATCH_UP_WINDOW_MIN):
            if self.matches(dt):
                return dt
            dt -= timedelta(minutes=1)
        return None


def parse_every(text: str) -> int:
    """Interval sugar ('45s', '15m', '2h', '1d') → seconds."""
    m = re.fullmatch(r"(\d+)\s*([smhd])", text.strip())
    if not m:
        raise ValueError(f"bad interval {text!r} (use e.g. 45s, 15m, 2h, 1d)")
    total = int(m.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]
    if total == 0:
        raise ValueError(f"interval must be positive: {text!r}")
    return total


def due(routine: dict, last_fire: str | None, now: datetime):
    """Returns (scheduled_time, late) if the routine should fire, else None."""
    if routine.get("enabled", True) is False:
        return None
    if routine["_every"]:
        # first fire is one interval after the routine appears; the daemon
        # seeds last_fire when it first sees the routine
        if last_fire is not None and (now - datetime.fromisoformat(last_fire)).total_seconds() >= routine["_every"]:
            return now.replace(second=0, microsecond=0), False
        return None
    minute = now.replace(second=0, microsecond=0)
    last_dt = datetime.fromisoformat(last_fire) if last_fire else None
    if routine["_cron"].matches(minute):
        if last_dt is None or last_dt < minute:
            return minute, False
        return None
    if routine.get("catch_up"):
        recent = routine["_cron"].most_recent(minute)
        if recent and last_dt is not None and last_dt < recent:
            return recent, True
    return None
