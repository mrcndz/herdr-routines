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

    def test_leap_day_matches(self):
        c = Cron("0 0 29 2 *")
        self.assertTrue(c.matches(dt("2028-02-29T00:00")))

    def test_leap_day_most_recent_rolls_back_to_prior_leap_year(self):
        # catch-up window is only 7 days, so a Feb-29-only cron checked
        # in a non-leap year finds nothing within the window
        c = Cron("0 0 29 2 *")
        self.assertIsNone(c.most_recent(dt("2027-03-01T00:00")))

    def test_dom_and_dow_ored_when_both_restricted(self):
        # standard (Vixie) cron: both day fields restricted → either matches
        c = Cron("0 0 1 * mon")
        self.assertTrue(c.matches(dt("2026-07-01T00:00")))   # dom only, Wed the 1st
        self.assertTrue(c.matches(dt("2026-07-06T00:00")))   # dow only, a Monday
        self.assertTrue(c.matches(dt("2026-06-01T00:00")))   # both: Mon the 1st
        self.assertFalse(c.matches(dt("2026-07-02T00:00")))  # neither, Thu the 2nd

    def test_dom_restricted_dow_star_still_ands(self):
        c = Cron("0 0 13 * *")
        self.assertTrue(c.matches(dt("2026-07-13T00:00")))
        self.assertFalse(c.matches(dt("2026-07-14T00:00")))

    def test_dow_restricted_dom_star_still_ands(self):
        c = Cron("0 9 * * fri")
        self.assertTrue(c.matches(dt("2026-07-17T09:00")))   # Friday
        self.assertFalse(c.matches(dt("2026-07-18T09:00")))  # Saturday

    def test_star_step_counts_as_unrestricted_for_or_rule(self):
        # Vixie rule: */N still counts as "*" — no OR, both fields must match
        c = Cron("0 0 */2 * mon")
        self.assertTrue(c.matches(dt("2026-07-13T00:00")))   # Mon, day 13 ∈ {1,3,5...}
        self.assertFalse(c.matches(dt("2026-07-06T00:00")))  # Mon, day 6 ∉ {1,3,5...}
        self.assertFalse(c.matches(dt("2026-07-01T00:00")))  # day 1 ∈ set but Wed

    def test_friday_the_13th_or_semantics(self):
        c = Cron("0 9 13 * fri")
        self.assertTrue(c.matches(dt("2026-07-13T09:00")))   # the 13th (a Monday)
        self.assertTrue(c.matches(dt("2026-07-17T09:00")))   # a Friday (the 17th)
        self.assertFalse(c.matches(dt("2026-07-14T09:00")))  # Tuesday the 14th

    def test_month_rollover_in_most_recent(self):
        c = Cron("0 0 1 * *")
        self.assertEqual(c.most_recent(dt("2026-08-03T00:00")),
                         dt("2026-08-01T00:00"))

    def test_step_of_one_is_equivalent_to_wildcard(self):
        c = Cron("*/1 * * * *")
        for m in (0, 1, 30, 59):
            self.assertTrue(c.matches(dt(f"2026-07-20T10:{m:02d}")))

    def test_single_value_range(self):
        c = Cron("0 0 5-5 * *")
        self.assertTrue(c.matches(dt("2026-07-05T00:00")))
        self.assertFalse(c.matches(dt("2026-07-06T00:00")))

    def test_mixed_names_and_numbers_in_dow_list(self):
        c = Cron("0 9 * * mon,3")
        self.assertTrue(c.matches(dt("2026-07-20T09:00")))  # Monday
        self.assertTrue(c.matches(dt("2026-07-22T09:00")))  # Wednesday (3)

    def test_whitespace_tolerance(self):
        c = Cron("  0   9  *  *  * ")
        self.assertTrue(c.matches(dt("2026-07-20T09:00")))

    def test_field_boundary_values(self):
        c = Cron("59 23 31 12 *")
        self.assertTrue(c.matches(dt("2026-12-31T23:59")))
        c2 = Cron("0 0 1 1 *")
        self.assertTrue(c2.matches(dt("2026-01-01T00:00")))

    def test_dow_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            Cron("* * * * 8")

    def test_dom_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            Cron("* * 32 * *")
        with self.assertRaises(ValueError):
            Cron("* * 0 * *")


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

    def test_large_value(self):
        self.assertEqual(parse_every("90m"), 5400)

    def test_leading_zeros(self):
        self.assertEqual(parse_every("0001m"), 60)

    def test_huge_value(self):
        self.assertEqual(parse_every("999999d"), 999999 * 86400)

    def test_unicode_digits_accepted(self):
        # \d and int() both accept unicode digits (e.g. full-width "1"),
        # so this is not rejected the way ascii-only validation would expect
        self.assertEqual(parse_every("１m"), 60)

    def test_whitespace_tolerated(self):
        self.assertEqual(parse_every("  15m  "), 900)
        self.assertEqual(parse_every("15 m"), 900)


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

    def test_catch_up_window_boundary_exactly_7_days(self):
        # most_recent scans CATCH_UP_WINDOW_MIN (7*24*60) minutes back,
        # inclusive of the last minute in that range; the farthest a match
        # can be found is CATCH_UP_WINDOW_MIN - 1 minutes before now
        from datetime import timedelta
        from schedule import CATCH_UP_WINDOW_MIN
        now = dt("2026-07-18T00:00:00")
        just_in = now - timedelta(minutes=CATCH_UP_WINDOW_MIN - 1)
        just_out = now - timedelta(minutes=CATCH_UP_WINDOW_MIN)

        c_in = Cron(f"{just_in.minute} {just_in.hour} {just_in.day} {just_in.month} *")
        self.assertEqual(c_in.most_recent(now), just_in)

        c_out = Cron(f"{just_out.minute} {just_out.hour} {just_out.day} {just_out.month} *")
        self.assertIsNone(c_out.most_recent(now))

    def test_catch_up_beyond_window_finds_nothing(self):
        r = routine(cron="0 0 1 1 *", catch_up=True)  # once a year
        now = dt("2026-07-18T00:05:00")
        self.assertIsNone(due(r, "2020-01-01T00:00:00", now))

    def test_every_exact_boundary_fires(self):
        r = routine(every="30m")
        hit = due(r, "2026-07-18T09:00:00", dt("2026-07-18T09:30:00"))
        self.assertIsNotNone(hit)
        self.assertFalse(hit[1])

    def test_every_one_second_before_boundary_does_not_fire(self):
        r = routine(every="30m")
        self.assertIsNone(due(r, "2026-07-18T09:00:00", dt("2026-07-18T09:29:59")))


if __name__ == "__main__":
    unittest.main()
