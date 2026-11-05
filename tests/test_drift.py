"""Drift metrics before and after one cleanup run on the fixture, plus the parity judge."""
import unittest

import support
from crosswalk import Capture, measure, parity


class DriftTests(unittest.TestCase):
    def test_before(self):
        lib, _, _ = support.load()
        d = measure(lib.captures, lib.config())
        self.assertEqual(d.as_dict(), {"library": 40, "filed": 18, "not_one_folder": 21, "multi_stream": 2,
                                       "mislabeled": 5, "needs_review": 2, "fragment": 0, "retired_tag": 4})
        self.assertEqual(len(d.breaches()), 5)

    def test_after_unattended_run(self):
        lib, _, _, recorder, _, _, report = support.cycle()
        self.assertEqual(report.status, "ok")
        d = measure(recorder.search(), lib.config())
        self.assertEqual(d.as_dict(), {"library": 40, "filed": 32, "not_one_folder": 5, "multi_stream": 0,
                                       "mislabeled": 3, "needs_review": 1, "fragment": 4, "retired_tag": 0})
        # what is left is left on purpose: collision, two folders awaiting approval, no evidence
        self.assertEqual(d.breaches(), ["not-one-folder 5 > 0"])
        self.assertTrue(d.line().startswith("drift | not-one-folder 5 (captures >= 60 s) | multi-stream 0"))

    def test_after_operator_run_with_approval(self):
        lib, _, _, recorder, _, _, _ = support.cycle(approve=True)
        self.assertEqual(measure(recorder.search(), lib.config()).not_one_folder, 4)

    def test_not_one_folder_ignores_fragments_and_short_captures(self):
        caps = [
            Capture("a", "Real", "2026-09-01T09:00:00-04:00", 600),                       # counts
            Capture("b", "Real", "2026-09-01T09:00:00-04:00", 600, tags=["fragment"]),    # tagged fragment
            Capture("c", "Real", "2026-09-01T09:00:00-04:00", 30),                        # under 60 s
            Capture("d", "Real", "2026-09-01T09:00:00-04:00", 600, folders=["Product", "Learning"]),  # two folders
        ]
        self.assertEqual(measure(caps).not_one_folder, 2)


class ParityJudge(unittest.TestCase):
    def test_parity_with_recorder_b_folders(self):
        lib, inf, rul, recorder, ledger, _, _ = support.cycle()
        again = support.build_plan(support.snapshot(lib, recorder), inf, rul, ledger)
        p = parity(recorder.search(), again.rows, lib.notes)
        self.assertEqual((p["agree"], p["total"], p["miss"]), (10, 11, ["cap-10"]))  # waits on the approval

    def test_parity_after_approval(self):
        lib, inf, rul, recorder, ledger, _, _ = support.cycle(approve=True)
        again = support.build_plan(support.snapshot(lib, recorder), inf, rul, ledger)
        p = parity(recorder.search(), again.rows, lib.notes)
        self.assertEqual((p["agree"], p["total"]), (11, 11))

    def test_collision_is_not_counted_as_a_match(self):
        lib, inf, rul, recorder, ledger, plan, _ = support.cycle()
        p = parity(recorder.search(), plan.rows, lib.notes)
        self.assertNotIn("cap-08", p["miss"] + p["unfiled"])


if __name__ == "__main__":
    unittest.main()
