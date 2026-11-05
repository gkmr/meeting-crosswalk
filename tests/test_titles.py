import unittest

import support
from crosswalk.model import Capture, Event, Inference, Note
from crosswalk.titles import choose_title, clean_title, is_generic

STREAMS = ("Product", "Partners", "Hiring", "Personal", "Mentoring", "Learning")


class GenericTitleTests(unittest.TestCase):
    def test_block_and_auto_titles(self):
        for t in ["Focus Time", "focus time (do not book)", "Hold", "Tentative hold: partner", "Deep work",
                  "10:00 AM - 10:30 AM", "2:00 PM", "Zoom meeting", "Google Meet meeting", "In-Person meeting",
                  "Mobile recording", "Untitled", "Recorder test", "Packing", "", "  "]:
            self.assertTrue(is_generic(t, STREAMS), t)

    def test_bare_stream_name_is_generic(self):
        self.assertTrue(is_generic("Product", STREAMS))
        self.assertTrue(is_generic("hiring", STREAMS))

    def test_real_titles(self):
        for t in ["Weekly product planning", "Holdings review", "Board meeting", "Team meeting",
                  "1:1 with Sam Chen", "Design review", "Lunch with Lena", "Launch go/no-go"]:
            self.assertFalse(is_generic(t, STREAMS), t)

    def test_clean_title(self):
        self.assertEqual(clean_title("Pitch " + chr(0x2014) + " Fabrikam  board"), "Pitch - Fabrikam board")
        self.assertEqual(len(clean_title("x" * 140)), 100)


class TrustOrderTests(unittest.TestCase):
    def setUp(self):
        self.plan = support.plan_fixture()

    def test_user_title_is_never_overwritten(self):
        r = support.row(self.plan, "cap-07")
        self.assertEqual((r["corrected_title"], r["title_source"]), ("Mentoring session with Maya", "user"))
        self.assertNotIn("rename", [o.kind for o in support.ops_for(self.plan, "cap-07")])

    def test_calendar_plus_linked_note(self):
        r = support.row(self.plan, "cap-01")
        self.assertEqual((r["corrected_title"], r["title_source"]), ("Weekly product planning", "calendar_and_note"))

    def test_content_inferred_and_wrong_note_title(self):
        r = support.row(self.plan, "cap-12")
        self.assertEqual(r["title_source"], "content_inferred")
        self.assertEqual(r["corrected_title"], "Staff engineer loop debrief")
        self.assertEqual(r["note_title_original"], "Call with Theo Park")
        self.assertTrue(r["note_title_wrong"])

    def test_event_without_linked_note(self):
        r = support.row(self.plan, "cap-09")
        self.assertEqual((r["corrected_title"], r["title_source"]), ("Partner intro with Litware", "calendar"))

    def test_nothing_better_keeps_the_block_title_and_flags_it(self):
        r = support.row(self.plan, "cap-24")  # matched by an unlinked note: its title is not a source
        self.assertEqual((r["corrected_title"], r["title_source"]), ("Focus Time", "recorder"))
        self.assertTrue(r["mislabeled"])

    def test_content_beats_a_linked_title_that_disagrees(self):
        cap = Capture("c", "Focus Time", "2026-10-12T10:00:00-04:00", 1800, notes="Budget review for the offsite.")
        ev = Event("e", "product", "Team lunch", "2026-10-12T10:00:00-04:00", "2026-10-12T10:30:00-04:00")
        note = Note("n", "Team lunch", ev.start, ev.end, event_id="e")
        inf = Inference("c", "Offsite budget review")
        self.assertEqual(choose_title(cap, note, ev, inf, STREAMS), ("Offsite budget review", "content_inferred"))
        self.assertEqual(choose_title(cap, note, ev, None, STREAMS), ("Team lunch", "calendar"))


if __name__ == "__main__":
    unittest.main()
