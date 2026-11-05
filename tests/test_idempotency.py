"""A second run produces zero ops. The ledger, not the recorder state, is the loop guard."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from dataclasses import asdict

import support
from adapters.fake import FakeRecorder
from crosswalk import Ledger, Op, apply_plan, build_plan
from crosswalk.__main__ import main


def dump_library(lib, captures, path):
    data = {"owner": lib.owner, "calendars": [{"id": k, "stream": v} for k, v in lib.calendars.items()],
            "tags": lib.tags, "captures": [asdict(c) for c in captures],
            "notes": [asdict(n) for n in lib.notes], "events": [asdict(e) for e in lib.events]}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


class ConnectorFlow(unittest.TestCase):
    """The skill's path: plan to files, send batches through a connector, verify from a fresh read."""

    def test_plan_send_verify_replan(self):
        lib, inf, rul = support.load()
        ex = support.EXAMPLES
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            args = [os.path.join(ex, "library.json"), "--inferences", os.path.join(ex, "inferences.json"),
                    "--rulings", os.path.join(ex, "rulings.json"), "--ledger", os.path.join(d, "ledger.json")]
            self.assertEqual(main(["plan"] + args + ["--out", os.path.join(d, "out")]), 0)
            recorder = FakeRecorder(lib.captures, lib.tags)  # stands in for the connector
            plan = build_plan(lib, inf, rul)
            apply_plan(plan, recorder, Ledger())           # sends; this ledger is thrown away
            dump_library(lib, recorder.search(), os.path.join(d, "after.json"))
            rc = main(["verify", os.path.join(d, "out", "plan.json"), os.path.join(d, "after.json"),
                       "--ledger", os.path.join(d, "ledger.json")])
            self.assertEqual(rc, 0)
            self.assertEqual(main(["plan"] + args + ["--out", os.path.join(d, "out2")]), 0)
            with open(os.path.join(d, "out2", "plan.json"), encoding="utf-8") as fh:
                again = json.load(fh)
        self.assertEqual([o for o in again["ops"] if o["gate"] == "auto"], [])  # the stale file plans nothing new
        self.assertEqual(len(again["skipped"]), len(plan.auto_ops))


class SecondRun(unittest.TestCase):
    def test_fresh_read_then_replan_is_empty(self):
        lib, inf, rul, recorder, ledger, plan, report = support.cycle(approve=True)
        self.assertEqual(sum(report.written.values()), len(plan.ops))
        again = build_plan(support.snapshot(lib, recorder), inf, rul, ledger)
        self.assertEqual(again.ops, [])

    def test_unattended_replan_has_no_auto_ops_only_the_gated_removal(self):
        lib, inf, rul, recorder, ledger, _, _ = support.cycle(approve=False)
        again = build_plan(support.snapshot(lib, recorder), inf, rul, ledger)
        self.assertEqual(again.auto_ops, [])
        self.assertEqual([(o.capture_id, o.kind, o.target) for o in again.gated_ops], [("cap-10", "unfile", "Personal")])

    def test_stale_snapshot_plus_ledger_is_empty(self):
        # The second slot reads an old snapshot (the recorder has not caught up). The ledger still stops repeats.
        lib, inf, rul, recorder, ledger, plan, _ = support.cycle(approve=True)
        stale = build_plan(lib, inf, rul, ledger)
        self.assertEqual(stale.ops, [])
        self.assertEqual(len(stale.skipped), len(plan.ops))

    def test_a_changed_value_is_written_again(self):
        lib, inf, rul, recorder, ledger, _, _ = support.cycle()
        snap = support.snapshot(lib, recorder)
        next(e for e in snap.events if e.id == "evt-01").title = "Weekly product and launch planning"
        again = build_plan(snap, inf, rul, ledger)
        self.assertEqual([(o.capture_id, o.kind, o.value) for o in again.auto_ops],
                         [("cap-01", "rename", "Weekly product and launch planning")])


class LedgerTests(unittest.TestCase):
    def test_persists_to_disk(self):
        op = Op("attach", "cap-01", "Product")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ledger.json")
            led = Ledger(path)
            led.record(op, "ok")
            led.save()
            self.assertTrue(Ledger(path).done(op))

    def test_tag_can_cycle_off_and_on(self):
        led = Ledger()
        on, off = Op("attach", "c", "needs-review"), Op("detach", "c", "needs-review")
        led.record(on, "ok")
        led.record(off, "ok")
        self.assertFalse(led.done(on))
        self.assertTrue(led.done(off))

    def test_tag_slots_ignore_case(self):
        led = Ledger()
        led.record(Op("attach", "c", "Product"), "ok")
        self.assertTrue(led.done(Op("attach", "c", "product")))

    def test_unverified_writes_are_retried_next_run(self):
        lib, inf, rul = support.load()
        recorder = FakeRecorder(lib.captures, lib.tags, drop_writes=True)  # says yes, changes nothing
        ledger = Ledger()
        plan = build_plan(support.snapshot(lib, recorder), inf, rul, ledger)
        report = apply_plan(plan, recorder, ledger)
        self.assertEqual(report.status, "partial")
        self.assertEqual(len(report.unverified), len(plan.auto_ops))
        again = build_plan(support.snapshot(lib, recorder), inf, rul, ledger)
        self.assertEqual(len(again.auto_ops), len(plan.auto_ops))


if __name__ == "__main__":
    unittest.main()
