"""Idempotency ledger: the loop guard for writes.

Every write the lane makes is recorded against a slot: one tag on one
meeting, one folder on one meeting, the title of one meeting, one speaker
label on one meeting. A planned op is skipped when the slot's last recorded
write is the same action with the same value. If the corrected value changes,
the slot no longer matches and the write goes ahead.

The ledger, not the recorder state, is the guard. A recorder read can be stale
or partial; the ledger is what this lane knows it already did.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

_FAMILY = {"attach": "tag", "detach": "tag", "file": "folder", "unfile": "folder",
           "rename": "title", "speaker": "speaker"}


def slot(op) -> str:
    target = op.target.lower() if _FAMILY[op.kind] == "tag" else op.target
    return "|".join((_FAMILY[op.kind], op.capture_id, target))


class Ledger:
    def __init__(self, path=None):
        self.path = path
        self.slots = {}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                self.slots = json.load(fh).get("slots", {})

    def done(self, op) -> bool:
        last = self.slots.get(slot(op))
        return bool(last) and last["status"] == "ok" and last["kind"] == op.kind and last["value"] == op.value

    def record(self, op, status: str, ts: str = None):
        self.slots[slot(op)] = {
            "kind": op.kind,
            "value": op.value,
            "status": status,
            "ts": ts or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }

    def filter(self, ops):
        """Split ops into (to_do, already_done)."""
        todo, skipped = [], []
        for op in ops:
            (skipped if self.done(op) else todo).append(op)
        return todo, skipped

    def speaker_originals(self, capture_id: str) -> dict:
        """{name this lane wrote: the label it replaced}, so the matcher can undo its own evidence."""
        out = {}
        prefix = "speaker|%s|" % capture_id
        for key, rec in self.slots.items():
            if key.startswith(prefix) and rec["kind"] == "speaker" and rec["status"] == "ok":
                out[rec["value"]] = key[len(prefix):]
        return out

    def save(self, path=None):
        path = path or self.path
        if not path:
            return
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "slots": self.slots}, fh, indent=1, sort_keys=True)
        os.replace(tmp, path)
