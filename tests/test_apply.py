"""Executor guard rails: scope failure, approval gate, tag-create race guard, write fence, per-batch errors."""
import unittest

import support
from adapters.fake import FakeCalendar, FakeNotes, FakeRecorder
from crosswalk import Ledger, apply_plan, build_plan


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.lib, self.inf, self.rul = support.load()

    def plan(self, recorder, ledger):
        return build_plan(support.snapshot(self.lib, recorder), self.inf, self.rul, ledger)

    def test_scope_error_stops_the_write_phase_cleanly(self):
        recorder = FakeRecorder(self.lib.captures, self.lib.tags, scope_error=True)
        ledger = Ledger()
        before = [(c.id, c.title, c.tags, c.folders) for c in recorder.search()]
        report = apply_plan(self.plan(recorder, ledger), recorder, ledger)
        self.assertEqual(report.status, "blocked-scope")
        self.assertEqual(report.calls, 0)
        self.assertEqual(sum(report.written.values()), 0)
        self.assertEqual([(c.id, c.title, c.tags, c.folders) for c in recorder.search()], before)

    def test_folder_removal_needs_approval(self):
        recorder = FakeRecorder(self.lib.captures, self.lib.tags)
        report = apply_plan(self.plan(recorder, Ledger()), recorder, Ledger())
        self.assertEqual([(o.capture_id, o.kind) for o in report.gated], [("cap-10", "unfile")])
        self.assertNotIn("remove_from_folder", recorder.calls)
        self.assertEqual(recorder.get(["cap-10"])[0].folders, ["Product", "Personal"])

    def test_new_tag_names_are_not_created_unattended(self):
        tags = [t for t in self.lib.tags if t != "fragment"]
        recorder = FakeRecorder(self.lib.captures, tags)
        ledger = Ledger()
        report = apply_plan(self.plan(recorder, ledger), recorder, ledger)
        self.assertEqual(sorted(o.capture_id for o in report.blocked), ["cap-03", "cap-04", "cap-13", "cap-32"])
        self.assertNotIn("fragment", [t.lower() for t in recorder.list_tags()])

    def test_new_tag_name_is_created_by_one_serial_call_first(self):
        tags = [t for t in self.lib.tags if t != "fragment"]
        recorder = FakeRecorder(self.lib.captures, tags)
        ledger = Ledger()
        report = apply_plan(self.plan(recorder, ledger), recorder, ledger, allow_new_tags=True)
        self.assertEqual(report.status, "ok")
        self.assertEqual([t.lower() for t in recorder.list_tags()].count("fragment"), 1)
        self.assertEqual(recorder.calls[0], "attach_tag")  # the serial create runs before any batch

    def test_one_failing_batch_does_not_stop_the_rest(self):
        class Flaky(FakeRecorder):
            def rename(self, meeting_id, title):
                if meeting_id == "cap-01":
                    raise RuntimeError("timeout")
                return super().rename(meeting_id, title)

        recorder = Flaky(self.lib.captures, self.lib.tags)
        ledger = Ledger()
        report = apply_plan(self.plan(recorder, ledger), recorder, ledger)
        self.assertEqual(report.status, "partial")
        self.assertEqual([e["meetings"] for e in report.errors], [["cap-01"]])
        self.assertEqual(report.written["rename"], 10)

    def test_write_fence_notes_and_calendar_have_no_write_methods(self):
        writes = ("attach_tags", "detach_tags", "add_to_folder", "remove_from_folder", "rename", "update_speakers")
        for adapter in (FakeNotes(self.lib.notes), FakeCalendar(self.lib.events)):
            for name in writes:
                self.assertFalse(hasattr(adapter, name), "%s.%s" % (type(adapter).__name__, name))

    def test_fake_recorder_rejects_oversized_batches(self):
        recorder = FakeRecorder(self.lib.captures, self.lib.tags)
        too_many = [{"meeting_id": c.id, "tag_names": ["Product"]} for c in self.lib.captures[:26]]
        with self.assertRaises(ValueError):
            recorder.attach_tags(too_many)


if __name__ == "__main__":
    unittest.main()
