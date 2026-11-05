"""Drift metrics: the monthly judge of the recorder's state.

Read only. It looks at what the recorder holds now (folders, tags, durations),
not at what the planner intended, so it catches drift from any source:
the lane, the user, or the recorder itself.

Targets:
  not-one-folder  0     captures of 60 s or more, not tagged fragment, not in exactly one folder
  multi-stream    0     meetings with more than one stream tag
  mislabeled      < 10% of the library
  needs-review    < 5%  of the library
  fragment        listed, no target (a person deletes them)
  retired-tag     0     meetings carrying any retired tag
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .config import FRAGMENT, FRAGMENT_SECONDS, MISLABELED, NEEDS_REVIEW, Config


@dataclass
class Drift:
    library: int = 0
    filed: int = 0
    not_one_folder: int = 0
    multi_stream: int = 0
    mislabeled: int = 0
    needs_review: int = 0
    fragment: int = 0
    retired_tag: int = 0

    def pct(self, n: int) -> float:
        return n / self.library if self.library else 0.0

    def line(self) -> str:
        return ("drift | not-one-folder %d (captures >= 60 s) | multi-stream %d | mislabeled %d (%.0f%%) | "
                "needs-review %d (%.0f%%) | fragment %d | retired-tag %d | library %d | filed %d"
                % (self.not_one_folder, self.multi_stream, self.mislabeled, 100 * self.pct(self.mislabeled),
                   self.needs_review, 100 * self.pct(self.needs_review), self.fragment, self.retired_tag,
                   self.library, self.filed))

    def breaches(self) -> list:
        out = []
        if self.not_one_folder:
            out.append("not-one-folder %d > 0" % self.not_one_folder)
        if self.multi_stream:
            out.append("multi-stream %d > 0" % self.multi_stream)
        if self.pct(self.mislabeled) >= 0.10:
            out.append("mislabeled %.0f%% >= 10%%" % (100 * self.pct(self.mislabeled)))
        if self.pct(self.needs_review) >= 0.05:
            out.append("needs-review %.0f%% >= 5%%" % (100 * self.pct(self.needs_review)))
        if self.retired_tag:
            out.append("retired-tag %d > 0" % self.retired_tag)
        return out

    def as_dict(self) -> dict:
        return asdict(self)


def measure(captures, cfg: Config = None) -> Drift:
    cfg = cfg or Config()
    d = Drift(library=len(captures))
    for c in captures:
        tags = [t.lower() for t in c.tags]
        folders = set(c.folders)
        if folders:
            d.filed += 1
        if float(c.duration_s or 0) >= FRAGMENT_SECONDS and len(folders) != 1 and FRAGMENT not in tags:
            d.not_one_folder += 1
        if len({cfg.canonical(t) for t in c.tags if cfg.canonical(t)}) > 1:
            d.multi_stream += 1
        d.mislabeled += MISLABELED in tags
        d.needs_review += NEEDS_REVIEW in tags
        d.fragment += FRAGMENT in tags
        d.retired_tag += any(cfg.retired_target(t) for t in c.tags)
    return d


def parity(captures, rows, notes) -> dict:
    """Outside judge: does recorder A's folder agree with recorder B's folder for the same meeting?

    Pairs come from the crosswalk (HIGH or MEDIUM, not a collision, not a
    fragment). Folders come from a fresh read of both recorders.
    """
    caps = {c.id: c for c in captures}
    folder_of = {n.id: n.folder for n in notes}
    agree, miss, unfiled = [], [], []
    for r in rows:
        if r["confidence"] not in ("HIGH", "MEDIUM") or r["collision"] or r["fragment"] or not r["note_id"]:
            continue
        want = folder_of.get(r["note_id"])
        cap = caps.get(r["capture_id"])
        if not want or cap is None:
            continue
        have = list(dict.fromkeys(cap.folders))
        (agree if have == [want] else unfiled if not have else miss).append(r["capture_id"])
    return {"agree": len(agree), "total": len(agree) + len(miss) + len(unfiled), "miss": miss, "unfiled": unfiled}
