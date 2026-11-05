import unittest

import support
from crosswalk.match import match_capture, parse_instant


def capture(lib, cid):
    return next(c for c in lib.captures if c.id == cid)


class InstantTests(unittest.TestCase):
    def test_offsets_compare_as_absolute_instants(self):
        self.assertEqual(parse_instant("2026-10-15T14:00:00Z"), parse_instant("2026-10-15T10:00:00-04:00"))
        self.assertEqual(parse_instant("2026-10-15T15:00:00+01:00"), parse_instant("2026-10-15T10:00:00-04:00"))

    def test_naive_time_is_refused(self):
        with self.assertRaises(ValueError):
            parse_instant("2026-10-15T10:00:00")


class MatchTests(unittest.TestCase):
    def setUp(self):
        self.lib, _, _ = support.load()
        self.cfg = self.lib.config()

    def m(self, cid, **kw):
        return match_capture(capture(self.lib, cid), self.lib.notes, self.lib.events, self.cfg, **kw)

    def test_timezone_label_is_metadata_not_arithmetic(self):
        evt = next(e for e in self.lib.events if e.id == "evt-02")
        self.assertEqual(evt.tz_label, "America/Los_Angeles")  # the trap is planted
        m = self.m("cap-02")
        self.assertEqual((m.tier, m.event_id, m.stream), ("HIGH", "evt-02", "Partners"))

    def test_utc_capture_matches_event_stored_in_local_offset(self):
        m = self.m("cap-17")
        self.assertEqual((m.tier, m.event_id), ("HIGH", "evt-17"))

    def test_block_events_are_never_candidates(self):
        m = self.m("cap-01")
        self.assertEqual((m.tier, m.event_id, m.note_id), ("HIGH", "evt-01", "note-01"))
        self.assertFalse(m.collision)
        self.assertNotIn("evt-b1", " ".join(m.reasons + m.candidates))

    def test_tiers(self):
        self.assertEqual(self.m("cap-01").tier, "HIGH")       # time + named people
        self.assertEqual(self.m("cap-05").tier, "MEDIUM")     # time + head count + content
        self.assertEqual(self.m("cap-23").tier, "LOW")        # time only
        self.assertEqual(self.m("cap-22").tier, "UNMATCHED")  # nothing that day

    def test_attendee_contradiction_veto_is_load_bearing(self):
        m = self.m("cap-09")
        self.assertIn("note-09", m.vetoed)                   # solo note vs three voices
        self.assertEqual((m.event_id, m.stream), ("evt-09", "Partners"))
        # Without voices to compare, the solo Personal note wins on shared words. The veto is what stops it.
        blind = capture(self.lib, "cap-09").copy()
        blind.speakers = []
        b = match_capture(blind, self.lib.notes, self.lib.events, self.cfg)
        self.assertEqual((b.note_id, b.stream), ("note-09", "Personal"))

    def test_time_collision_is_low_with_no_pick(self):
        m = self.m("cap-08")
        self.assertTrue(m.collision)
        self.assertEqual(m.tier, "LOW")
        self.assertEqual(sorted(m.candidates), ["evt-08a", "evt-08b"])
        self.assertIsNone(m.note_id)
        self.assertIsNone(m.event_id)

    def test_lane_written_speaker_names_are_not_evidence(self):
        cap = capture(self.lib, "cap-14").copy()
        cap.speakers = ["Ganesh Kumar", "Rui Santos"]  # as the lane left it after a speaker fix
        naive = match_capture(cap, self.lib.notes, self.lib.events, self.cfg)
        guarded = match_capture(cap, self.lib.notes, self.lib.events, self.cfg,
                                speaker_originals={"Rui Santos": "Speaker 2"})
        self.assertEqual(naive.tier, "HIGH")      # its own write would promote it
        self.assertEqual(guarded.tier, "MEDIUM")  # the ledger puts the label back


if __name__ == "__main__":
    unittest.main()
