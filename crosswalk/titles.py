"""Generic title detection and the title trust order.

Recorder A cannot see secondary calendars. It names a capture after whatever
block sits on the primary calendar at that hour ("Focus Time", "Hold"), or
falls back to an auto title ("Zoom meeting", "10:00 AM - 10:30 AM"). Those
titles are expected to be wrong and are never evidence for or against a match.
"""
from __future__ import annotations

import re

from .config import MAX_TITLE_CHARS

GENERIC_TITLE = re.compile(
    r"""
      ^\s*\d{1,2}:\d{2}\s?(am|pm)\b                     # bare clock time: "10:00 AM - 10:30 AM"
    | \bfocus\s*time\b | \bfocus\s+block\b | \bdeep\s+work\b
    | ^\s*(tentative\s+)?hold\b | \bdo\s+not\s+book\b
    | ^\s*(busy|blocked?|placeholder|packing|commute)\s*$
    | \b(zoom|google\s+meet|meet|teams|webex|slack|chrome|comet|avconferenced
        |granola|facetime|in-person)\s+meeting\s*$       # recorder auto titles
    | ^\s*untitled(\s+meeting)?\s*$
    | ^\s*(new|mobile)\s+recording\s*$
    | \brecorder\s+test\b | ^\s*getting\s+started\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_STOP = set(
    "a an and the of for with to on in at by from about is are was were be this that it its "
    "our your my we you they them their call meeting sync chat notes next".split()
)


def tokens(text: str) -> set:
    """Content words, lower case, stopwords and short words removed."""
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2 and w not in _STOP}


def is_generic(title: str, stream_names=()) -> bool:
    """True for block titles, recorder auto titles, a bare stream name, or nothing at all."""
    t = (title or "").strip()
    if not t:
        return True
    if t.lower() in {s.lower() for s in stream_names}:
        return True
    return bool(GENERIC_TITLE.search(t))


def clean_title(title: str) -> str:
    """No long dashes, single spaces, at most MAX_TITLE_CHARS."""
    t = title.replace(chr(0x2014), " - ").replace(chr(0x2013), " - ")  # em and en dash
    t = " ".join(t.split())
    if len(t) > MAX_TITLE_CHARS:
        t = t[: MAX_TITLE_CHARS].rstrip()
    return t


def agrees(title: str, content: str) -> bool:
    """A title agrees with the content when they share a content word. No content means no objection."""
    c = tokens(content)
    return not c or bool(tokens(title) & c)


TRUST_ORDER = (
    "user",               # 1. the user set the recorder title by hand: never overwritten
    "calendar_and_note",  # 2. matched event + a recorder B note linked to that same event, title agrees with content
    "content_inferred",   # 3. a title inferred from the transcript or summary
    "calendar",           # 4. a matched event whose title is not a block
    "recorder",           # 5. nothing better: keep what the recorder has
)


def choose_title(capture, note=None, event=None, inference=None, stream_names=()):
    """Return (title, source) by the trust order above.

    `note` and `event` must already be trusted matches (HIGH or MEDIUM). An
    unlinked note's title is never a source: ad hoc notes often carry the
    wrong title or the wrong person.
    """
    if capture.title_set_by_user:
        return capture.title, "user"
    if (
        event is not None and note is not None and note.event_id == event.id
        and not is_generic(event.title, stream_names)
        and agrees(event.title, capture.notes)
    ):
        return clean_title(event.title), "calendar_and_note"
    if inference is not None and inference.title and not is_generic(inference.title, stream_names):
        return clean_title(inference.title), "content_inferred"
    if event is not None and not is_generic(event.title, stream_names):
        return clean_title(event.title), "calendar"
    return capture.title, "recorder"


def note_title_wrong(note, inference):
    """True when a content-inferred title contradicts the note title; None when not assessed."""
    if note is None or inference is None:
        return None
    return not (tokens(note.title) & tokens(inference.title))
