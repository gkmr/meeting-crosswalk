"""Match recorder A captures to recorder B notes and calendar events.

Signals, strongest first:
  1. start time, compared as absolute instants (offset included, labels ignored)
  2. participants: named overlap, or at least the head count agreeing
  3. duration
  4. content words shared between the capture summary and the candidate

Tiers:
  HIGH    strong time and participants
  MEDIUM  strong time and partial participants or shared content,
          or same day and participants
  LOW     anything else that is in range (time only)
  UNMATCHED  nothing in range

Two rules learned the hard way:
  - Attendee-contradiction veto. A capture with several voices never matches a
    solo note or event, and a one-voice capture never matches a group meeting,
    however close the times.
  - Time collision. If the top two distinct meetings tie and both start within
    15 minutes of the capture, the capture is LOW and nothing is written. The
    capture's old stream tag is not trusted either, because it probably came
    from the same ambiguous time match. A tie between far-off candidates is
    plain LOW ("ambiguous").

The capture's own title is never evidence: it is either a block name or a
title this lane wrote earlier.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .config import COLLISION_MARGIN, MERGE_MINUTES, STRONG_MINUTES
from .titles import is_generic, tokens

RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNMATCHED": 0}
PLACEHOLDER = re.compile(r"^speaker\s*\d+$", re.IGNORECASE)


def _aware(text: str) -> datetime:
    s = text.strip()
    if s[-1:] in ("Z", "z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("time has no offset, refusing to guess: %r" % text)
    return dt


def parse_instant(text: str) -> datetime:
    """ISO 8601 with an offset, as an absolute instant in UTC. Naive text is an error."""
    return _aware(text).astimezone(timezone.utc)


def _norm(name: str) -> str:
    return " ".join(str(name).lower().split())


def is_placeholder(label: str) -> bool:
    return bool(PLACEHOLDER.match(label.strip()))


def names_match(a: str, b: str) -> bool:
    """Same full name, or a bare first name against a full name."""
    a, b = _norm(a), _norm(b)
    if not a or not b:
        return False
    if a == b:
        return True
    ta, tb = a.split(), b.split()
    return (len(ta) == 1 and ta[0] == tb[0]) or (len(tb) == 1 and tb[0] == ta[0])


@dataclass
class Score:
    kind: str           # "note" or "event"
    id: str
    key: str            # meeting identity: a linked note shares its event's key
    minutes: float
    time: str           # "strong" or "weak"
    people: str         # "full", "partial" or ""
    duration_ok: bool
    shared: int
    points: float
    tier: str
    vetoed: bool
    reasons: list = field(default_factory=list)


@dataclass
class Match:
    capture_id: str
    tier: str
    note_id: str = None
    event_id: str = None
    stream: str = None
    collision: bool = False
    reasons: list = field(default_factory=list)
    candidates: list = field(default_factory=list)
    vetoed: list = field(default_factory=list)
    roster: list = field(default_factory=list)


class _Capture:
    """Precomputed view of a capture for scoring."""

    def __init__(self, capture, cfg, speaker_originals=None):
        originals = {_norm(k): v for k, v in (speaker_originals or {}).items()}
        # Names this lane wrote into the speaker list are put back to the label they replaced,
        # so the lane's own writes never become evidence for the lane.
        labels = [originals.get(_norm(s), s) for s in capture.speakers]
        self.local = _aware(capture.start)
        self.instant = self.local.astimezone(timezone.utc)
        self.duration = float(capture.duration_s or 0)
        self.voices = len({_norm(s) for s in labels})
        people = [p for p in labels + list(capture.attendees) if not is_placeholder(p)]
        self.named = sorted({_norm(p) for p in people if not cfg.is_owner(p)})
        self.content = tokens(capture.notes)


def _roster(names, cfg):
    raw = [n for n in names if str(n).strip()]
    others = [n for n in raw if not cfg.is_owner(n)]
    solo = len(raw) > 0 and len(others) == 0
    return others, solo


def _score(cap: _Capture, kind, cid, key, start, end, people, text, cfg):
    t0 = parse_instant(start)
    minutes = abs((t0 - cap.instant).total_seconds()) / 60.0
    if minutes <= STRONG_MINUTES:
        time = "strong"
    elif t0.astimezone(cap.local.tzinfo).date() == cap.local.date():
        time = "weak"
    else:
        return None
    others, solo = _roster(people, cfg)
    reasons = ["%s %s %.0f min" % (kind, cid, minutes)]

    vetoed = (cap.voices >= 2 and solo) or (cap.voices == 1 and len(others) >= 2)
    if vetoed:
        reasons.append("veto: %d voices vs %s" % (cap.voices, "solo" if solo else "%d people" % len(others)))

    overlap = sum(1 for n in cap.named if any(names_match(n, o) for o in others))
    ratio = overlap / min(len(cap.named), len(others)) if cap.named and others else 0.0
    headcount = cap.voices >= 2 and cap.voices == len(others) + 1
    if overlap and ratio >= 0.5:
        people_tier = "full"
    elif overlap or headcount:
        people_tier = "partial"
    else:
        people_tier = ""
    if people_tier:
        reasons.append("people %s (%d named, head count %s)" % (people_tier, overlap, "agrees" if headcount else "n/a"))

    dur = (parse_instant(end) - t0).total_seconds()
    duration_ok = dur > 0 and cap.duration > 0 and min(dur, cap.duration) / max(dur, cap.duration) >= 0.6
    shared = len(cap.content & tokens(text))
    if shared:
        reasons.append("content %d shared" % shared)

    points = (3 if time == "strong" else 1)
    points += {"full": 3, "partial": 1.5}.get(people_tier, 0)
    points += 1 if duration_ok else 0
    points += 2 if shared >= 2 else (0.5 if shared == 1 else 0)

    if time == "strong" and people_tier == "full":
        tier = "HIGH"
    elif (time == "strong" and (people_tier or shared >= 2)) or (time == "weak" and people_tier == "full"):
        tier = "MEDIUM"
    else:
        tier = "LOW"
    return Score(kind, cid, key, minutes, time, people_tier, duration_ok, shared, points, tier, vetoed, reasons)


def _key_for_note(note, events, cfg):
    if note.event_id:
        return note.event_id
    n0 = parse_instant(note.start)
    mine = [p for p in note.participants if not cfg.is_owner(p)]
    for e in events:
        close = abs((parse_instant(e.start) - n0).total_seconds()) <= MERGE_MINUTES * 60
        if close and any(names_match(p, a) for p in mine for a in e.attendees if not cfg.is_owner(a)):
            return e.id
    return note.id


def match_capture(capture, notes, events, cfg, speaker_originals=None) -> Match:
    cap = _Capture(capture, cfg, speaker_originals)
    live_events = [e for e in events if not is_generic(e.title, cfg.streams)]  # blocks are never candidates
    scores = []
    for n in notes:
        s = _score(cap, "note", n.id, _key_for_note(n, live_events, cfg), n.start, n.end,
                   n.participants, n.title + " " + n.body, cfg)
        if s:
            scores.append(s)
    for e in live_events:
        s = _score(cap, "event", e.id, e.id, e.start, e.end, e.attendees, e.title, cfg)
        if s:
            scores.append(s)

    vetoed = [s.id for s in scores if s.vetoed and s.time == "strong"]  # only the ones that were close
    live = [s for s in scores if not s.vetoed]
    if not live:
        return Match(capture.id, "UNMATCHED", vetoed=vetoed,
                     reasons=["no candidate in range"] + (["vetoed %s" % ", ".join(vetoed)] if vetoed else []))

    groups = {}
    for s in live:
        groups.setdefault(s.key, []).append(s)
    best_of = {k: max(v, key=lambda s: (RANK[s.tier], s.points)) for k, v in groups.items()}
    ranked = sorted(best_of.items(), key=lambda kv: (RANK[kv[1].tier], kv[1].points), reverse=True)
    top_key, top = ranked[0]

    reasons = list(top.reasons)
    if vetoed:
        reasons.append("vetoed %s" % ", ".join(vetoed))
    if len(ranked) > 1:
        second_key, second = ranked[1]
        if top.tier == second.tier and top.points - second.points < COLLISION_MARGIN:
            same_time = top.time == second.time == "strong"
            label = "time collision" if same_time else "ambiguous"
            return Match(capture.id, "LOW", collision=same_time, candidates=[top_key, second_key], vetoed=vetoed,
                         reasons=reasons + ["%s: %s vs %s" % (label, top_key, second_key)])

    by_id_note = {n.id: n for n in notes}
    by_id_event = {e.id: e for e in live_events}
    note_id = next((s.id for s in groups[top_key] if s.kind == "note"), None)
    event_id = next((s.id for s in groups[top_key] if s.kind == "event"), None)
    if event_id is None and top_key in by_id_event:
        event_id = top_key
    note = by_id_note.get(note_id)
    event = by_id_event.get(event_id)

    stream = None
    if note is not None and note.folder:
        stream = note.folder
    elif event is not None:
        stream = cfg.calendar_stream(event.calendar)
    roster = []
    for name in (note.participants if note else []) + (event.attendees if event else []):
        if not cfg.is_owner(name) and _norm(name) not in {_norm(r) for r in roster}:
            roster.append(name)
    return Match(capture.id, top.tier, note_id, event_id, stream, False, reasons,
                 [k for k, _ in ranked[:2]], vetoed, roster)
