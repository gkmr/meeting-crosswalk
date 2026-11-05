"""In-memory adapters for tests and the demo. No network, no real API.

FakeRecorder enforces the same limits a real recorder connector enforced in
practice, so a plan that passes here does not get rejected for shape later.
"""
from __future__ import annotations

from crosswalk.apply import ScopeError
from crosswalk.config import MAX_BATCH_MEETINGS, MAX_BATCH_PAIRS, MAX_TITLE_CHARS, STREAMS
from crosswalk.match import parse_instant


def _in_window(start, lo, hi):
    t = parse_instant(start)
    return (lo is None or t >= parse_instant(lo)) and (hi is None or t < parse_instant(hi))


class FakeRecorder:
    def __init__(self, captures, tags=(), folders=STREAMS, scope_error=False, drop_writes=False):
        self._caps = {c.id: c.copy() for c in captures}
        self._order = [c.id for c in captures]
        self._tags = list(dict.fromkeys(tags))
        self._folders = list(folders)
        self.scope_error = scope_error    # simulate a token without write scope
        self.drop_writes = drop_writes    # simulate a write that returns success but does not land
        self.calls = []

    # read
    def search(self, start=None, end=None):
        return [self._caps[i].copy() for i in self._order if _in_window(self._caps[i].start, start, end)]

    def get(self, ids):
        return [self._caps[i].copy() for i in ids if i in self._caps]

    def folder_members(self, folder):
        return [i for i in self._order if folder in self._caps[i].folders]

    def list_tags(self):
        return list(self._tags)

    # write
    def _write(self, name, n_meetings, n_pairs=0):
        if self.scope_error:
            raise ScopeError("insufficient_scope")
        if n_meetings > MAX_BATCH_MEETINGS or n_pairs > MAX_BATCH_PAIRS:
            raise ValueError("%s batch too large: %d meetings, %d pairs" % (name, n_meetings, n_pairs))
        self.calls.append(name)
        return not self.drop_writes

    def _cap(self, mid):
        if mid not in self._caps:
            raise KeyError("unknown meeting %s" % mid)
        return self._caps[mid]

    def attach_tags(self, assignments):
        pairs = sum(len(a["tag_names"]) for a in assignments)
        if not self._write("attach_tag", len(assignments), pairs):
            return
        for a in assignments:
            cap = self._cap(a["meeting_id"])
            for name in a["tag_names"]:
                if name.lower() not in {t.lower() for t in self._tags}:
                    self._tags.append(name)  # auto-created, like the real thing
                if name.lower() not in {t.lower() for t in cap.tags}:
                    cap.tags.append(name)

    def detach_tags(self, assignments):
        pairs = sum(len(a["tag_names"]) for a in assignments)
        if not self._write("detach_tag", len(assignments), pairs):
            return
        for a in assignments:
            cap = self._cap(a["meeting_id"])
            drop = {n.lower() for n in a["tag_names"]}
            cap.tags = [t for t in cap.tags if t.lower() not in drop]

    def add_to_folder(self, folder, ids):
        if folder not in self._folders:
            raise ValueError("unknown folder %r (folders are not created unattended)" % folder)
        if not self._write("add_to_folder", len(ids)):
            return
        for i in ids:
            cap = self._cap(i)
            if folder not in cap.folders:
                cap.folders.append(folder)

    def remove_from_folder(self, folder, ids):
        if not self._write("remove_from_folder", len(ids)):
            return
        for i in ids:
            cap = self._cap(i)
            cap.folders = [f for f in cap.folders if f != folder]

    def rename(self, meeting_id, title):
        if len(title) > MAX_TITLE_CHARS:
            raise ValueError("title longer than %d characters" % MAX_TITLE_CHARS)
        if not self._write("rename", 1):
            return
        cap = self._cap(meeting_id)
        cap.title = title
        cap.title_set_by_user = False  # a lane rename is not a user title

    def update_speakers(self, meeting_id, mappings):
        cap = self._cap(meeting_id)
        for m in mappings:
            if m["from"] not in cap.speakers:
                raise ValueError("speaker %r not in meeting %s" % (m["from"], meeting_id))
        if not self._write("update_speakers", 1):
            return
        for m in mappings:
            cap.speakers = [m["to"] if s == m["from"] else s for s in cap.speakers]


class FakeNotes:
    """Recorder B. Read only: there is no write method to call."""

    def __init__(self, notes):
        self._notes = list(notes)

    def search(self, start=None, end=None):
        return [n for n in self._notes if _in_window(n.start, start, end)]


class FakeCalendar:
    """All calendars. Read only: there is no write method to call."""

    def __init__(self, events):
        self._events = list(events)

    def list_events(self, start=None, end=None):
        return [e for e in self._events if _in_window(e.start, start, end)]
