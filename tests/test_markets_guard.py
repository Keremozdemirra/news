"""Market data sanity: a value outside a plausible range, a jump no market makes, a future date or a stale last
observation is hidden from every page and card, and a bad fresh value never replaces the last good one."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest import mock

from aidaily import markets as M

TODAY = date(2026, 11, 27)


def pts(*rows):
    return [[d, v] for d, v in rows]


class Check(unittest.TestCase):
    def test_a_normal_series_passes(self):
        self.assertIsNone(M.check_series("eurusd", pts(("2026-11-26", 1.0975), ("2026-11-27", 1.0957)), TODAY))

    def test_a_wrong_unit_is_outside_the_bounds(self):
        # cents instead of dollars, a basis-point column read as a yield, a rate times one hundred
        self.assertIn("outside", M.check_series("brent", pts(("2026-11-26", 91.2), ("2026-11-27", 9180.0)), TODAY))
        self.assertIn("outside", M.check_series("ust10", pts(("2026-11-26", 4.85), ("2026-11-27", 485.0)), TODAY))
        self.assertIn("outside", M.check_series("eurusd", pts(("2026-11-27", 0.0)), TODAY))

    def test_a_jump_no_market_makes_is_held(self):
        self.assertIn("moved", M.check_series("eurusd", pts(("2026-11-26", 1.09), ("2026-11-27", 1.4)), TODAY))
        self.assertIn("points", M.check_series("ust2", pts(("2026-11-26", 4.0), ("2026-11-27", 5.6)), TODAY))

    def test_a_real_big_day_passes(self):
        self.assertIsNone(M.check_series("brent", pts(("2026-11-26", 80.0), ("2026-11-27", 92.0)), TODAY))
        self.assertIsNone(M.check_series("ust10", pts(("2026-11-26", 4.2), ("2026-11-27", 4.7)), TODAY))

    def test_a_stale_last_observation_is_held_by_its_publisher_rhythm(self):
        self.assertIn("days old", M.check_series("eurusd", pts(("2026-11-10", 1.09)), TODAY))
        self.assertIsNone(M.check_series("eurusd", pts(("2026-11-20", 1.09)), TODAY))  # a week of holidays and a weekend
        self.assertIsNone(M.check_series("brent", pts(("2026-11-24", 91.8)), TODAY))
        self.assertIsNone(M.check_series("gasoline", pts(("2026-11-16", 3.8)), TODAY))
        self.assertIsNone(M.check_series("gold", pts(("2026-10-01", 4105.0)), TODAY))
        self.assertIn("days old", M.check_series("gold", pts(("2026-08-01", 4105.0)), TODAY))

    def test_a_date_in_the_future_is_held(self):
        self.assertIn("future", M.check_series("eurusd", pts(("2026-12-20", 1.09)), TODAY))

    def test_garbage_is_held_not_raised(self):
        self.assertIn("unreadable", M.check_series("eurusd", [["2026-11-27", "n/a"]], TODAY))
        self.assertIn("unreadable", M.check_series("eurusd", [["yesterday", 1.0]], TODAY))
        self.assertEqual(M.check_series("eurusd", [["2026-11-27", float("nan")]], TODAY), "not a number")

    def test_every_series_has_bounds(self):
        self.assertEqual(sorted(set(M.SERIES) - set(M.BOUNDS)), [])

    def test_the_committed_file_passes_its_own_bounds_when_it_is_fresh(self):
        # the file in the repository is the last good copy: if it fails here, the bounds are wrong, not the file
        data = json.loads((Path(__file__).resolve().parent.parent / "state" / "markets.json").read_text())
        for k, p in data["series"].items():
            last = date.fromisoformat(p[-1][0])
            why = M.check_series(k, p, last)  # judged on its own newest day: bounds and jumps, never age
            self.assertIsNone(why, f"{k}: {why}")


class Sanitize(unittest.TestCase):
    def test_bad_series_leave_and_are_named(self):
        data = {"series": {"eurusd": pts(("2026-11-27", 1.0957)), "brent": pts(("2026-11-27", 9180.0))},
                "dfr": {"value": 250.0, "since": "2026-09-16"}}
        with redirect_stdout(io.StringIO()) as out:
            got = M.sanitize(data, TODAY)
        self.assertEqual(sorted(got["series"]), ["eurusd"])
        self.assertEqual(sorted(got["held"]), ["brent", "dfr"])
        self.assertNotIn("dfr", got)
        self.assertIn("brent not shown", out.getvalue())
        self.assertIn("brent", data["series"])  # the input is untouched

    def test_nothing_held_adds_no_key(self):
        self.assertNotIn("held", M.sanitize({"series": {"eurusd": pts(("2026-11-27", 1.0957))}}, TODAY))


class Load(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "markets.json"
        p = mock.patch.object(M, "FILE", self.file)
        p.start()
        self.addCleanup(p.stop)

    def write(self, series):
        self.file.write_text(json.dumps({"series": series}))

    def test_a_bad_fresh_value_does_not_replace_the_last_good_one(self):
        today = date.today().isoformat()
        good = pts((today, 91.8))
        self.write({"brent": good})
        with mock.patch.object(M, "fetch", lambda: {"series": {"brent": pts((today, 9180.0))}}), redirect_stdout(io.StringIO()) as out:
            got = M.load(live=True)
        self.assertEqual(got["series"]["brent"], good)
        self.assertIn("refused", out.getvalue())
        self.assertEqual(json.loads(self.file.read_text())["series"]["brent"], good)

    def test_an_old_file_shows_nothing_rather_than_old_numbers(self):
        self.write({"eurusd": pts(("2026-01-02", 1.09))})
        with redirect_stdout(io.StringIO()):
            self.assertIsNone(M.load(live=False))


if __name__ == "__main__":
    unittest.main()
