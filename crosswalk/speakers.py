"""Speaker label fixes, from the meeting's own roster only.

A replacement name must come from the matched note's participants or the
matched event's attendees. Nothing is invented, guessed from a partial match,
or copied from a login handle.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .match import _norm, is_placeholder

_HANDLE = re.compile(r"^[^\s]+$")          # one token
_NOT_A_PERSON = re.compile(r"\b(bot|notetaker|assistant|recorder|booking)\b", re.IGNORECASE)


def is_clean_name(name: str) -> bool:
    """At least two words, letters only (plus . ' -), not a bot."""
    n = name.strip()
    if _HANDLE.match(n) or _NOT_A_PERSON.search(n):
        return False
    return all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", w) for w in n.split())


def speaker_fixes(speakers, roster, cfg):
    """Return [(label, name)] for labels that resolve to exactly one roster member.

    - "Speaker N": only when it is the only placeholder and exactly one roster
      member is not already named among the speakers.
    - A bare first name: when exactly one roster member has that first name.
    - A misspelled full name: when exactly one roster member is a close match.
    Anything ambiguous is skipped.
    """
    clean = [r for r in roster if is_clean_name(r) and not cfg.is_owner(r)]
    if not clean:
        return []
    labels = [s for s in speakers if not cfg.is_owner(s)]
    named = {_norm(s) for s in labels if not is_placeholder(s)}
    unclaimed = [r for r in clean if _norm(r) not in named]
    placeholders = [s for s in labels if is_placeholder(s)]
    fixes = []
    for label in labels:
        n = _norm(label)
        if n in {_norm(r) for r in clean}:
            continue  # already a correct full name
        if is_placeholder(label):
            if len(placeholders) == 1 and len(unclaimed) == 1:
                fixes.append((label, unclaimed[0]))
            continue
        parts = n.split()
        if len(parts) == 1:
            hits = [r for r in clean if _norm(r).split()[0] == parts[0]]
        else:
            hits = [r for r in clean if SequenceMatcher(None, n, _norm(r)).ratio() >= 0.85]
        if len(hits) == 1 and _norm(hits[0]) not in named:
            fixes.append((label, hits[0]))
    return fixes
