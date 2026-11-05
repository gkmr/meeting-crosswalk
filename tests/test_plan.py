"""The planner fixes every planted case in examples/ and leaves the rest alone."""
import unittest

import support
from support import kinds, ops_for, row
from crosswalk import Capture, Library, Rulings, build_plan, make_batches
from crosswalk.config import MARKERS, STREAMS


class PlantedCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib, cls.inf, cls.rul = support.load()
        cls.plan = build_plan(cls.lib, cls.inf, cls.rul)

    def test_block_titled_capture_is_renamed_filed_and_tagged(self):
        self.assertEqual(kinds(self.plan, "cap-01"), [("attach", "Product"), ("file", "Product"), ("rename", "title")])
        self.assertFalse(row(self.plan, "cap-01")["mislabeled"])

    def test_mislabeled_detached_in_the_same_run_as_the_rename(self):
        self.assertEqual(kinds(self.plan, "cap-02"),
                         [("attach", "Partners"), ("detach", "mislabeled"), ("file", "Partners"), ("rename", "title")])

    def test_two_folder_capture_waits_for_approval(self):
        gated = ops_for(self.plan, "cap-10", gate="approval")
        self.assertEqual([(o.kind, o.target) for o in gated], [("unfile", "Personal")])
        self.assertEqual(kinds(self.plan, "cap-10"), [("detach", "Personal")])  # tag follows the HIGH evidence now
        self.assertIn("two folders", [v["reason"] for v in self.plan.review if v["capture_id"] == "cap-10"])

    def test_fragments_are_tagged_never_filed_or_renamed(self):
        for cid in ("cap-03", "cap-04", "cap-13", "cap-32"):  # auto title < 5 min, < 60 s, ruled, < 60 s
            self.assertTrue(row(self.plan, cid)["fragment"], cid)
            self.assertEqual(kinds(self.plan, cid), [("attach", "fragment")], cid)

    def test_short_block_title_with_a_real_note_is_not_a_fragment(self):
        self.assertFalse(row(self.plan, "cap-16")["fragment"])
        self.assertEqual(kinds(self.plan, "cap-16"),
                         [("attach", "Product"), ("detach", "mislabeled"), ("file", "Product"), ("rename", "title")])

    def test_retired_tags_go_and_still_point_at_the_stream(self):
        self.assertEqual(kinds(self.plan, "cap-07"), [("attach", "Mentoring"), ("detach", "Mentorship"),
                                                      ("file", "Mentoring"), ("speaker", "Maya")])
        self.assertEqual(kinds(self.plan, "cap-21"), [("attach", "Hiring"), ("detach", "Recruiting"),
                                                      ("file", "Hiring")])
        self.assertEqual(kinds(self.plan, "cap-28"), [("detach", "Partnerships")])
        self.assertEqual(kinds(self.plan, "cap-29"), [("attach", "Learning"), ("detach", "Courses")])

    def test_medium_match_with_a_stream_is_filed_without_needs_review(self):
        r = row(self.plan, "cap-05")
        self.assertEqual((r["confidence"], r["stream"], r["needs_review"]), ("MEDIUM", "Hiring", False))
        self.assertIn(("file", "Hiring"), kinds(self.plan, "cap-05"))
        self.assertIn(("detach", "mislabeled"), kinds(self.plan, "cap-05"))

    def test_medium_match_without_a_stream_gets_needs_review(self):
        self.assertEqual(kinds(self.plan, "cap-14"),
                         [("attach", "needs-review"), ("rename", "title"), ("speaker", "Speaker 2")])
        self.assertEqual(row(self.plan, "cap-14")["folders_after"], [])

    def test_time_collision_is_not_auto_filed(self):
        r = row(self.plan, "cap-08")
        self.assertTrue(r["collision"])
        self.assertEqual(r["confidence"], "LOW")
        self.assertIn("Product", self.lib.captures[7].tags)  # the old tag would have filed it
        self.assertEqual(kinds(self.plan, "cap-08"), [])  # no file, no rename, no speakers
        self.assertIn("time collision", [v["reason"] for v in self.plan.review if v["capture_id"] == "cap-08"])

    def test_a_ruling_resolves_a_collision(self):
        rulings = Rulings(streams=dict(self.rul.streams, **{"cap-08": "Mentoring"}), fragments=set(self.rul.fragments))
        plan = build_plan(self.lib, self.inf, rulings)
        self.assertEqual(kinds(plan, "cap-08"), [("attach", "Mentoring"), ("detach", "Product"), ("file", "Mentoring")])

    def test_low_match_gets_no_inference_writes(self):
        self.assertEqual(row(self.plan, "cap-23")["confidence"], "LOW")
        self.assertEqual(kinds(self.plan, "cap-23"), [("attach", "mislabeled")])  # title fact only

    def test_low_and_unmatched_rows_never_get_renames_speakers_or_match_filing(self):
        for r in self.plan.rows:
            if r["confidence"] in ("LOW", "UNMATCHED"):
                for o in ops_for(self.plan, r["capture_id"]):
                    self.assertNotIn(o.kind, ("rename", "speaker"), r["capture_id"])
                    if o.kind == "file":
                        self.assertEqual(o.reason, "from its own stream tag", r["capture_id"])

    def test_multi_stream_tags_follow_the_folder(self):
        self.assertEqual(kinds(self.plan, "cap-11"), [("detach", "Partners")])

    def test_content_inferred_rows(self):
        self.assertEqual(row(self.plan, "cap-12")["confidence"], "HIGH")   # two signals agree
        self.assertEqual(row(self.plan, "cap-27")["confidence"], "MEDIUM")  # one signal
        self.assertEqual(kinds(self.plan, "cap-27"), [("attach", "Product"), ("file", "Product"), ("rename", "title")])

    def test_instructions_inside_notes_are_data(self):
        self.assertIn("ignore your rules", self.lib.captures[14].notes)
        self.assertEqual(ops_for(self.plan, "cap-15"), [])

    def test_user_tags_are_never_touched(self):
        self.assertEqual(ops_for(self.plan, "cap-20"), [])
        self.assertFalse([o for o in self.plan.ops if o.target.lower() == "book club"])

    def test_clean_meetings_get_no_ops(self):
        for cid in ("cap-33", "cap-34", "cap-35", "cap-36", "cap-37", "cap-38", "cap-39", "cap-40"):
            self.assertEqual(ops_for(self.plan, cid), [], cid)

    def test_speaker_fixes_come_from_the_roster_or_not_at_all(self):
        fixes = sorted((o.capture_id, o.target, o.value) for o in self.plan.ops if o.kind == "speaker")
        self.assertEqual(fixes, [
            ("cap-05", "Speaker 2", "Kai Tanaka"),    # one placeholder, one unclaimed roster member
            ("cap-06", "Speaker 3", "Ezra Cole"),
            ("cap-07", "Maya", "Maya Ortiz"),         # bare first name, one match
            ("cap-14", "Speaker 2", "Rui Santos"),
            ("cap-24", "Speaker 2", "Owen Marsh"),
            ("cap-25", "Alx Rivera", "Alex Rivera"),  # misspelling, one close match
        ])
        # skipped: "Sam" on cap-25 (two Sams), cap-26 (roster is a login handle), cap-09 (two placeholders)

    def test_attaches_stay_inside_the_closed_vocabulary(self):
        allowed = {s.lower() for s in STREAMS} | set(MARKERS)
        for o in self.plan.ops:
            if o.kind == "attach":
                self.assertIn(o.target.lower(), allowed)
            if o.kind == "file":
                self.assertIn(o.target, STREAMS)


class Limits(unittest.TestCase):
    def test_seven_tags_at_most(self):
        cap = Capture("busy", "Board prep", "2026-09-01T09:00:00-04:00", 1800,
                      tags=["a", "b", "c", "d", "e", "f", "g", "Recruiting"])
        lib = Library(["Ganesh Kumar"], {}, [], [cap], [], [])
        plan = build_plan(lib)
        attached = [o.target for o in plan.ops if o.kind == "attach"]
        self.assertEqual(attached, [])  # the retired tag goes, but seven user tags leave no room
        self.assertIn("tag cap", [v["reason"] for v in plan.review])

    def test_batches_respect_25_meetings_and_50_pairs(self):
        caps = [Capture("m%02d" % i, "Weekly sync %d" % i, "2026-09-01T09:00:00-04:00", 1800,
                        tags=["Recruiting", "Partnerships", "Courses"], folders=["Product"]) for i in range(60)]
        plan = build_plan(Library(["Ganesh Kumar"], {}, [], caps, [], []))
        self.assertEqual(len([o for o in plan.ops if o.kind == "detach"]), 180)
        covered = []
        for payload, ops in make_batches(plan.ops):
            if "assignments" in payload:
                self.assertLessEqual(len(payload["assignments"]), 25)
                self.assertLessEqual(sum(len(a["tag_names"]) for a in payload["assignments"]), 50)
            if "meeting_ids" in payload:
                self.assertLessEqual(len(payload["meeting_ids"]), 25)
            covered.extend(ops)
        self.assertEqual(sorted(map(repr, covered)), sorted(map(repr, plan.ops)))


if __name__ == "__main__":
    unittest.main()
