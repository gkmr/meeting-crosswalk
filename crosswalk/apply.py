"""Execute a plan against a recorder adapter, then verify by reading back.

- Ops already in the ledger are skipped.
- Ops gated for approval (folder removals) run only with approve_removals.
- A tag name the recorder does not have yet is not created unattended. With
  allow_new_tags, each new name is created by one serial call before anything
  is batched, because two concurrent first-attaches of the same new name can
  create two tags with the same display name.
- A ScopeError (the token lacks write scope) stops the write phase at once.
  Other errors are recorded per batch and the run continues.
- Success is decided by a fresh read of the recorder, not by counting calls.
  Only verified writes are recorded as done in the ledger.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .plan import make_batches


class ScopeError(Exception):
    """The recorder token predates the write scopes. Reconnecting the connector fixes it."""


@dataclass
class ApplyReport:
    status: str = "ok"                              # ok | partial | blocked-scope
    written: Counter = field(default_factory=Counter)
    calls: int = 0
    skipped: int = 0
    gated: list = field(default_factory=list)
    blocked: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    unverified: list = field(default_factory=list)

    def summary(self) -> str:
        w = ", ".join("%s %d" % kv for kv in sorted(self.written.items())) or "none"
        return ("apply: %s | verified writes: %s | calls %d | skipped %d | gated %d | blocked %d | errors %d | unverified %d"
                % (self.status, w, self.calls, self.skipped, len(self.gated), len(self.blocked),
                   len(self.errors), len(self.unverified)))


def _call(recorder, payload):
    op = payload["op"]
    if op == "add_to_folder":
        return recorder.add_to_folder(payload["folder"], payload["meeting_ids"])
    if op == "remove_from_folder":
        return recorder.remove_from_folder(payload["folder"], payload["meeting_ids"])
    if op == "attach_tag":
        return recorder.attach_tags(payload["assignments"])
    if op == "detach_tag":
        return recorder.detach_tags(payload["assignments"])
    if op == "rename":
        return recorder.rename(payload["meeting_id"], payload["title"])
    if op == "update_speakers":
        return recorder.update_speakers(payload["meeting_id"], payload["mappings"])
    raise ValueError("unknown op %r" % op)


def _reflected(op, cap) -> bool:
    if cap is None:
        return False
    tags = {t.lower() for t in cap.tags}
    if op.kind == "attach":
        return op.target.lower() in tags
    if op.kind == "detach":
        return op.target.lower() not in tags
    if op.kind == "file":
        return op.target in cap.folders
    if op.kind == "unfile":
        return op.target not in cap.folders
    if op.kind == "rename":
        return cap.title == op.value
    if op.kind == "speaker":
        return op.value in cap.speakers and op.target not in cap.speakers
    return False


def verify_ops(ops, captures, ledger):
    """Record each op as ok or unverified by what a fresh read shows. Returns (ok, unverified)."""
    after = {c.id: c for c in captures}
    ok, unverified = [], []
    for o in ops:
        if _reflected(o, after.get(o.capture_id)):
            ledger.record(o, "ok")
            ok.append(o)
        else:
            ledger.record(o, "unverified")
            unverified.append(o)
    return ok, unverified


def apply_plan(plan, recorder, ledger, approve_removals=False, allow_new_tags=False) -> ApplyReport:
    report = ApplyReport(skipped=len(plan.skipped))
    todo = []
    for op in plan.ops:
        if op.gate != "auto" and not approve_removals:
            report.gated.append(op)
        elif ledger.done(op):
            report.skipped += 1
        else:
            todo.append(op)

    known = {t.lower() for t in recorder.list_tags()}
    new = [o for o in todo if o.kind == "attach" and o.target.lower() not in known]
    if new and not allow_new_tags:
        report.blocked = new
        todo = [o for o in todo if o not in new]

    sent = []
    try:
        if new and allow_new_tags:
            first = {}
            for o in new:
                first.setdefault(o.target.lower(), o)
            for o in first.values():  # one serial call per brand-new name
                recorder.attach_tags([{"meeting_id": o.capture_id, "tag_names": [o.target]}])
                report.calls += 1
                sent.append(o)
                todo.remove(o)
        for payload, ops in make_batches(todo):
            try:
                _call(recorder, payload)
                report.calls += 1
                sent.extend(ops)
            except ScopeError:
                raise
            except Exception as exc:  # one bad batch never fails the run
                report.errors.append({"op": payload["op"], "meetings": sorted({o.capture_id for o in ops}),
                                      "error": str(exc)})
                for o in ops:
                    ledger.record(o, "error")
    except ScopeError as exc:
        report.status = "blocked-scope"
        report.errors.append({"op": "write phase", "meetings": [], "error": str(exc)})

    ids = sorted({o.capture_id for o in sent})
    ok, report.unverified = verify_ops(sent, recorder.get(ids) if ids else [], ledger)
    for o in ok:
        report.written[o.kind] += 1
    ledger.save()
    if report.status == "ok" and (report.errors or report.unverified):
        report.status = "partial"
    return report
