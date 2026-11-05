"""Planner: three sources in, one crosswalk and a list of writes out.

The planner never writes. It returns ops, and apply.py executes them against
an adapter. Rules, in the order they are applied to each capture:

  1. Match it (match.py). LOW and UNMATCHED rows get no inference writes:
     no filing from the match, no rename, no speaker fix.
  2. Fragment rule. Under 60 s, or a block or auto title under 5 min with no
     notes, or already tagged fragment, or ruled a fragment. A fragment is
     tagged and listed for deletion by hand; never filed or renamed.
  3. Stream, folder first. One folder: that folder is the stream. Two
     folders: a removal is planned only with strong evidence, and it waits for
     approval. No folder: ruling, then the match, then a content inference,
     then the capture's own single stream tag. A time collision blocks all of
     these except a ruling.
  4. Title by the trust order (titles.py). A title the user set is kept.
  5. Tags from the closed vocabulary: the stream tag equals the folder name,
     retired tags go, mislabeled tracks whether the title is still generic,
     needs-review marks a MEDIUM row that is not filed. Tags outside the
     vocabulary belong to the user and are never touched. Seven at most.
  6. Speaker fixes from the matched roster.
  7. The ledger drops writes already made.
"""
from __future__ import annotations

import json
import os
from collections import Counter, OrderedDict
from dataclasses import asdict, dataclass, field

from .config import (FRAGMENT, FRAGMENT_AUTO_TITLE_SECONDS, FRAGMENT_SECONDS, MAX_BATCH_MEETINGS,
                     MAX_BATCH_PAIRS, MAX_TAGS_PER_MEETING, MISLABELED, NEEDS_REVIEW)
from .match import RANK, match_capture, parse_instant
from .model import Rulings
from .speakers import speaker_fixes
from .titles import choose_title, is_generic, note_title_wrong

WRITABLE = ("HIGH", "MEDIUM")
KINDS = ("unfile", "file", "detach", "attach", "rename", "speaker")  # execution order
API = {"unfile": "remove_from_folder", "file": "add_to_folder", "detach": "detach_tag",
       "attach": "attach_tag", "rename": "rename", "speaker": "update_speakers"}


@dataclass(frozen=True)
class Op:
    kind: str           # one of KINDS
    capture_id: str
    target: str         # folder name, tag name, "title", or the speaker label being replaced
    value: str = ""     # new title or new speaker name
    gate: str = "auto"  # "auto" or "approval"
    reason: str = ""


@dataclass
class Plan:
    rows: list
    ops: list
    review: list
    skipped: list = field(default_factory=list)

    @property
    def auto_ops(self):
        return [o for o in self.ops if o.gate == "auto"]

    @property
    def gated_ops(self):
        return [o for o in self.ops if o.gate != "auto"]

    def counts(self) -> dict:
        c = Counter(o.kind for o in self.auto_ops)
        tiers = Counter(r["confidence"] for r in self.rows)
        return {
            "captures": len(self.rows),
            "confidence": {t: tiers.get(t, 0) for t in ("HIGH", "MEDIUM", "LOW", "UNMATCHED")},
            "ops": {k: c.get(k, 0) for k in KINDS if c.get(k)},
            "gated": len(self.gated_ops),
            "skipped_by_ledger": len(self.skipped),
            "review": len(self.review),
        }

    def batches(self, include_gated=True):
        ops = self.ops if include_gated else self.auto_ops
        return make_batches(ops)

    def to_dict(self) -> dict:
        return {"counts": self.counts(), "ops": [asdict(o) for o in self.ops],
                "review": self.review, "skipped": [asdict(o) for o in self.skipped]}


def make_batches(ops):
    """Group ops into recorder calls: [(payload, ops)].

    Tag calls carry at most MAX_BATCH_MEETINGS meetings and MAX_BATCH_PAIRS
    (meeting, tag) pairs. Folder calls carry at most MAX_BATCH_MEETINGS ids.
    Renames and speaker fixes are one call per meeting.
    """
    out = []
    for kind in KINDS:
        group = [o for o in ops if o.kind == kind]
        if not group:
            continue
        if kind in ("file", "unfile"):
            by_folder = OrderedDict()
            for o in group:
                by_folder.setdefault((o.target, o.gate), []).append(o)
            for (folder, gate), items in by_folder.items():
                for i in range(0, len(items), MAX_BATCH_MEETINGS):
                    chunk = items[i:i + MAX_BATCH_MEETINGS]
                    payload = {"op": API[kind], "folder": folder, "meeting_ids": [o.capture_id for o in chunk]}
                    if gate != "auto":
                        payload["gate"] = gate
                    out.append((payload, chunk))
        elif kind in ("attach", "detach"):
            per = OrderedDict()
            for o in group:
                per.setdefault(o.capture_id, []).append(o)
            cur, cur_ops, pairs = [], [], 0
            for cid, items in per.items():
                if cur and (len(cur) == MAX_BATCH_MEETINGS or pairs + len(items) > MAX_BATCH_PAIRS):
                    out.append(({"op": API[kind], "assignments": cur}, cur_ops))
                    cur, cur_ops, pairs = [], [], 0
                cur.append({"meeting_id": cid, "tag_names": [o.target for o in items]})
                cur_ops = cur_ops + items
                pairs += len(items)
            if cur:
                out.append(({"op": API[kind], "assignments": cur}, cur_ops))
        elif kind == "rename":
            for o in group:
                out.append(({"op": API[kind], "meeting_id": o.capture_id, "title": o.value}, [o]))
        else:
            per = OrderedDict()
            for o in group:
                per.setdefault(o.capture_id, []).append(o)
            for cid, items in per.items():
                maps = [{"from": o.target, "to": o.value} for o in items]
                out.append(({"op": API[kind], "meeting_id": cid, "mappings": maps}, items))
    return out


def build_plan(library, inferences=None, rulings=None, ledger=None, cfg=None) -> Plan:
    cfg = cfg or library.config()
    inferences = inferences or {}
    rulings = rulings or Rulings()
    notes = {n.id: n for n in library.notes}
    events = {e.id: e for e in library.events}
    rows, ops, review = [], [], []
    for cap in library.captures:
        row, cap_ops, cap_review = _plan_capture(cap, library, cfg, inferences.get(cap.id), rulings, ledger,
                                                 notes, events)
        rows.append(row)
        ops.extend(cap_ops)
        review.extend(cap_review)
    skipped = []
    if ledger is not None:
        ops, skipped = ledger.filter(ops)
    return Plan(rows, ops, review, skipped)


def _plan_capture(cap, lib, cfg, inf, rulings, ledger, notes, events):
    originals = ledger.speaker_originals(cap.id) if ledger is not None else {}
    m = match_capture(cap, lib.notes, lib.events, cfg, originals)
    ops, review = [], []

    def add(kind, target, value="", gate="auto", reason=""):
        ops.append(Op(kind, cap.id, target, value, gate, reason))

    def flag(reason, detail=""):
        review.append({"capture_id": cap.id, "title": cap.title, "reason": reason, "detail": detail})

    # 1. confidence: a ruling wins, a collision blocks, else the stronger of match and inference
    ruled = rulings.streams.get(cap.id)
    matched = m.tier in WRITABLE
    inf_tier = None if inf is None else ("HIGH" if inf.signals >= 2 else "MEDIUM")
    if ruled:
        conf, basis = "HIGH", "ruling"
    elif m.collision:
        conf, basis = "LOW", "time collision"
    elif inf_tier and RANK[inf_tier] > RANK[m.tier]:
        conf, basis = inf_tier, "content inferred (%d signal%s)" % (inf.signals, "" if inf.signals == 1 else "s")
    else:
        conf, basis = m.tier, "match"
    writable = conf in WRITABLE
    note = notes.get(m.note_id) if matched else None
    event = events.get(m.event_id) if matched else None

    # 2. fragment
    lower_tags = {t.lower() for t in cap.tags}
    has_notes = bool(cap.notes.strip()) or note is not None
    fragment = (
        cap.id in rulings.fragments
        or FRAGMENT in lower_tags
        or cap.duration_s < FRAGMENT_SECONDS
        or (is_generic(cap.title, cfg.streams) and cap.duration_s < FRAGMENT_AUTO_TITLE_SECONDS and not has_notes)
    )

    # 3. stream, folder first
    inferred_stream = inf.stream if (inf is not None and writable) else None
    evidence = ruled or (m.stream if matched else None) or inferred_stream
    if evidence and not cfg.canonical(evidence):
        flag("stream not in vocabulary", evidence)
        evidence = None
    tag_streams = sorted({cfg.canonical(t) for t in cap.tags if cfg.canonical(t)}
                         | {cfg.retired_target(t) for t in cap.tags if cfg.retired_target(t)})
    current = list(dict.fromkeys(cap.folders))
    folders_after = list(current)
    stream = None
    if fragment:
        stream = current[0] if len(current) == 1 else None
        flag("fragment", "tag only; delete by hand")
    elif len(current) == 1:
        stream = current[0]
        if evidence and evidence != stream:
            flag("folder disagrees", "filed in %s, evidence says %s" % (stream, evidence))
    elif len(current) > 1:
        strong = ruled or (m.stream if m.tier == "HIGH" else None)
        if strong in current:
            stream = strong
            folders_after = [strong]
            extra = [f for f in current if f != strong]
            for f in extra:
                add("unfile", f, gate="approval", reason="two folders, %s match says %s" % (m.tier, strong))
            flag("two folders", "remove from %s once approved" % ", ".join(extra))
        else:
            flag("two folders", "no strong evidence, a person decides")
    else:
        if m.collision and not ruled:
            flag("time collision", " vs ".join(m.candidates))
        elif evidence:
            stream = evidence
        elif len(tag_streams) == 1:
            stream = tag_streams[0]
        else:
            flag("stream unknown", "%s; stream tags: %s" % (conf, ", ".join(tag_streams) or "none"))
        if stream:
            add("file", stream, reason="from %s" % (basis if evidence else "its own stream tag"))
            folders_after = [stream]

    # 4. title
    title_after = cap.title
    corrected, source = cap.title, ("user" if cap.title_set_by_user else "recorder")
    if writable and not fragment:
        corrected, source = choose_title(cap, note, event, inf, cfg.streams)
        if source != "user" and corrected != cap.title and not is_generic(corrected, cfg.streams):
            add("rename", "title", corrected, reason=source)
            title_after = corrected

    # 5. tags from the closed vocabulary
    lane = cfg.lane_tags()
    if len(folders_after) == 1:
        stream_tags = [folders_after[0]]
    elif stream:
        stream_tags = [stream]
    else:
        stream_tags = [cfg.canonical(t) for t in cap.tags if cfg.canonical(t)]
    markers = []
    if fragment:
        markers.append(FRAGMENT)
    elif is_generic(title_after, cfg.streams):
        markers.append(MISLABELED)
    filed = bool(folders_after)
    if not fragment and not filed and (conf == "MEDIUM" or (NEEDS_REVIEW in lower_tags and conf != "HIGH")):
        markers.append(NEEDS_REVIEW)
    wanted = stream_tags + markers
    wanted_lower = {t.lower() for t in wanted}
    detach = [t for t in cap.tags if t.lower() in lane and t.lower() not in wanted_lower]
    attach = [t for t in dict.fromkeys(wanted) if t.lower() not in lower_tags]
    room = MAX_TAGS_PER_MEETING - (len(cap.tags) - len(detach))
    if len(attach) > room:
        flag("tag cap", "would exceed %d tags; not attached: %s" % (MAX_TAGS_PER_MEETING, ", ".join(attach[room:])))
        attach = attach[:max(room, 0)]
    for t in detach:
        add("detach", t, reason=_detach_reason(t, cfg, stream_tags))
    for t in attach:
        add("attach", t, reason="stream" if cfg.canonical(t) else "marker")

    # 6. speakers, from the matched roster only
    if matched and not fragment and m.roster:
        for label, name in speaker_fixes(cap.speakers, m.roster, cfg):
            add("speaker", label, name, reason="roster of %s" % (m.event_id or m.note_id))

    start = parse_instant(cap.start)
    row = {
        "capture_id": cap.id,
        "capture_title_original": cap.title,
        "corrected_title": corrected,
        "title_source": source,
        "note_id": m.note_id,
        "event_id": m.event_id,
        "note_title_original": notes[m.note_id].title if m.note_id in notes else None,
        "note_title_wrong": note_title_wrong(notes.get(m.note_id), inf),
        "inference_basis": inf.basis if inf is not None else None,
        "stream": stream,
        "folders_after": folders_after,
        "start": start.isoformat(),
        "duration_s": cap.duration_s,
        "confidence": conf,
        "basis": [basis] + m.reasons,
        "collision": m.collision,
        "fragment": fragment,
        "mislabeled": MISLABELED in markers,
        "needs_review": NEEDS_REVIEW in markers,
        "attendees": list(m.roster) if matched else [],
    }
    return row, ops, review


def _detach_reason(tag, cfg, stream_tags):
    if cfg.retired_target(tag):
        return "retired tag"
    if cfg.canonical(tag):
        return "stream is %s" % (stream_tags[0] if stream_tags else "unsettled")
    return "marker no longer true"


def write_outputs(plan: Plan, out_dir: str):
    """crosswalk.json for consumers, plan.json for people, batches/ for the executor."""
    os.makedirs(os.path.join(out_dir, "batches"), exist_ok=True)
    for name in os.listdir(os.path.join(out_dir, "batches")):
        if name.endswith(".json"):
            os.remove(os.path.join(out_dir, "batches", name))
    with open(os.path.join(out_dir, "crosswalk.json"), "w", encoding="utf-8") as fh:
        json.dump(plan.rows, fh, indent=1)
    with open(os.path.join(out_dir, "plan.json"), "w", encoding="utf-8") as fh:
        json.dump(plan.to_dict(), fh, indent=1)
    for i, (payload, _) in enumerate(plan.batches()):
        with open(os.path.join(out_dir, "batches", "%02d_%s.json" % (i, payload["op"])), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1)
