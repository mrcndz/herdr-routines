import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from schedule import Cron, due, parse_every


def dt(s):
    return datetime.fromisoformat(s)


class TestCronParsing(unittest.TestCase):
    def test_wildcard(self):
        c = Cron("* * * * *")
        self.assertTrue(c.matches(dt("2026-07-18T13:37")))

    def test_exact_minute_hour(self):
        c = Cron("0 9 * * *")
        self.assertTrue(c.matches(dt("2026-07-20T09:00")))
        self.assertFalse(c.matches(dt("2026-07-20T09:01")))
        self.assertFalse(c.matches(dt("2026-07-20T10:00")))

    def test_ranges(self):
        c = Cron("0 9-18 * * *")
        self.assertTrue(c.matches(dt("2026-07-20T18:00")))
        self.assertFalse(c.matches(dt("2026-07-20T19:00")))

    def test_lists(self):
        c = Cron("0 9 * * 1,3,5")
        self.assertTrue(c.matches(dt("2026-07-20T09:00")))   # Monday
        self.assertFalse(c.matches(dt("2026-07-21T09:00")))  # Tuesday

    def test_steps(self):
        c = Cron("*/15 * * * *")
        for m, ok in [(0, True), (15, True), (30, True), (45, True), (7, False)]:
            self.assertEqual(c.matches(dt(f"2026-07-20T10:{m:02d}")), ok)

    def test_range_with_step(self):
        c = Cron("0 9-18/2 * * *")
        self.assertTrue(c.matches(dt("2026-07-20T11:00")))
        self.assertFalse(c.matches(dt("2026-07-20T10:00")))

    def test_dow_names(self):
        c = Cron("0 9 * * mon-fri")
        self.assertTrue(c.matches(dt("2026-07-17T09:00")))   # Friday
        self.assertFalse(c.matches(dt("2026-07-18T09:00")))  # Saturday

    def test_dow_names_list(self):
        c = Cron("0 10 * * sat,sun")
        self.assertTrue(c.matches(dt("2026-07-18T10:00")))   # Saturday
        self.assertTrue(c.matches(dt("2026-07-19T10:00")))   # Sunday
        self.assertFalse(c.matches(dt("2026-07-20T10:00")))  # Monday

    def test_sunday_is_0_and_7(self):
        for expr in ("0 9 * * 0", "0 9 * * 7"):
            self.assertTrue(Cron(expr).matches(dt("2026-07-19T09:00")))

    def test_month_names(self):
        c = Cron("0 0 1 jan *")
        self.assertTrue(c.matches(dt("2026-01-01T00:00")))
        self.assertFalse(c.matches(dt("2026-02-01T00:00")))

    def test_dom(self):
        c = Cron("0 0 15 * *")
        self.assertTrue(c.matches(dt("2026-07-15T00:00")))
        self.assertFalse(c.matches(dt("2026-07-14T00:00")))

    def test_case_insensitive_names(self):
        c = Cron("0 9 * * MON-FRI")
        self.assertTrue(c.matches(dt("2026-07-17T09:00")))

    def test_invalid(self):
        for expr in ("* * * *", "* * * * * *", "61 * * * *", "* 25 * * *",
                     "a * * * *", "* * * * 8-9"):
            with self.assertRaises(ValueError, msg=expr):
                Cron(expr)

    def test_most_recent(self):
        c = Cron("0 9 * * *")
        self.assertEqual(c.most_recent(dt("2026-07-18T13:37")),
                         dt("2026-07-18T09:00"))
        self.assertEqual(c.most_recent(dt("2026-07-18T09:00")),
                         dt("2026-07-18T09:00"))
        self.assertEqual(c.most_recent(dt("2026-07-18T08:59")),
                         dt("2026-07-17T09:00"))


class TestParseEvery(unittest.TestCase):
    def test_units(self):
        self.assertEqual(parse_every("45s"), 45)
        self.assertEqual(parse_every("15m"), 900)
        self.assertEqual(parse_every("2h"), 7200)
        self.assertEqual(parse_every("1d"), 86400)

    def test_invalid(self):
        for text in ("", "10", "m", "1w", "1.5h", "-1m", "0s", "0m"):
            with self.assertRaises(ValueError, msg=text):
                parse_every(text)


def routine(**kw):
    r = {"name": "t", "_cron": None, "_every": None}
    if "cron" in kw:
        r["_cron"] = Cron(kw.pop("cron"))
    if "every" in kw:
        r["_every"] = parse_every(kw.pop("every"))
    r.update(kw)
    return r


class TestDue(unittest.TestCase):
    def test_cron_fires_on_match(self):
        r = routine(cron="0 9 * * *")
        self.assertEqual(due(r, None, dt("2026-07-18T09:00:10")),
                         (dt("2026-07-18T09:00"), False))

    def test_cron_no_double_fire_same_minute(self):
        r = routine(cron="0 9 * * *")
        self.assertIsNone(due(r, "2026-07-18T09:00:00", dt("2026-07-18T09:00:40")))

    def test_cron_no_fire_off_schedule(self):
        r = routine(cron="0 9 * * *")
        self.assertIsNone(due(r, None, dt("2026-07-18T09:01:00")))

    def test_every_waits_for_seed_when_no_history(self):
        # the daemon seeds last_fire on first sight; due() itself never
        # fires an `every` routine without history
        r = routine(every="30m")
        self.assertIsNone(due(r, None, dt("2026-07-18T09:07:00")))

    def test_every_respects_interval(self):
        r = routine(every="30m")
        self.assertIsNone(due(r, "2026-07-18T09:00:00", dt("2026-07-18T09:15:00")))
        self.assertIsNotNone(due(r, "2026-07-18T09:00:00", dt("2026-07-18T09:30:00")))

    def test_disabled_never_fires(self):
        r = routine(cron="* * * * *", enabled=False)
        self.assertIsNone(due(r, None, dt("2026-07-18T09:00:00")))

    def test_catch_up_fires_late_once(self):
        r = routine(cron="0 9 * * *", catch_up=True)
        hit = due(r, "2026-07-17T09:00:00", dt("2026-07-18T13:37:00"))
        self.assertEqual(hit, (dt("2026-07-18T09:00"), True))
        # after the late fire, nothing more is due
        self.assertIsNone(due(r, "2026-07-18T09:00:00", dt("2026-07-18T13:38:00")))

    def test_catch_up_without_history_does_not_late_fire(self):
        # intended: catch-up only rescues routines with a fire history,
        # mirroring the every-seed philosophy (first sight never fires late)
        r = routine(cron="0 9 * * *", catch_up=True)
        self.assertIsNone(due(r, None, dt("2026-07-18T13:37:00")))

    def test_no_catch_up_skips_missed(self):
        r = routine(cron="0 9 * * *")
        self.assertIsNone(due(r, "2026-07-17T09:00:00", dt("2026-07-18T13:37:00")))


if __name__ == "__main__":
    unittest.main()
