"""Vocabulary and limits.

Everything the lane is allowed to write is named here. If a tag, folder or
limit is not in this file, the planner will not produce it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# One folder per meeting. The folder is the stream truth; the stream tag mirrors it.
STREAMS = ("Product", "Partners", "Hiring", "Personal", "Mentoring", "Learning")

# Marker tags. Together with the stream names this is the closed vocabulary.
MISLABELED = "mislabeled"      # title is still a calendar block or recorder auto title
NEEDS_REVIEW = "needs-review"  # MEDIUM match that is not filed yet
FRAGMENT = "fragment"          # accidental or empty capture, listed for deletion by hand
MARKERS = (MISLABELED, NEEDS_REVIEW, FRAGMENT)

# Old tag names. Detached on sight, never attached. Each still hints at a stream.
RETIRED = {
    "recruiting": "Hiring",
    "mentorship": "Mentoring",
    "partnerships": "Partners",
    "courses": "Learning",
}

MAX_TAGS_PER_MEETING = 7
MAX_BATCH_MEETINGS = 25
MAX_BATCH_PAIRS = 50
MAX_TITLE_CHARS = 100

FRAGMENT_SECONDS = 60             # anything shorter is a fragment
FRAGMENT_AUTO_TITLE_SECONDS = 300  # auto or block titled, no notes, shorter than this

STRONG_MINUTES = 15       # start times this close are strong evidence
MERGE_MINUTES = 5         # an unlinked note this close to an event, sharing a person, is the same meeting
COLLISION_MARGIN = 1.5    # top two candidates closer than this are a tie


@dataclass
class Config:
    owner: tuple = ("Ganesh Kumar",)
    calendars: dict = field(default_factory=dict)  # calendar id -> stream name or None
    streams: tuple = STREAMS
    retired: dict = field(default_factory=lambda: dict(RETIRED))

    def __post_init__(self):
        self._streams = {s.lower(): s for s in self.streams}
        self._owner = {" ".join(o.lower().split()) for o in self.owner}

    def canonical(self, tag: str):
        """Stream name for a tag that is a stream tag, else None."""
        return self._streams.get(tag.strip().lower())

    def retired_target(self, tag: str):
        return self.retired.get(tag.strip().lower())

    def is_owner(self, name: str) -> bool:
        return " ".join(name.lower().split()) in self._owner

    def lane_tags(self) -> set:
        """Lower-cased names the lane manages. Anything else belongs to the user."""
        return set(self._streams) | {m for m in MARKERS} | set(self.retired)

    def calendar_stream(self, calendar_id):
        return self.calendars.get(calendar_id)
