"""Plain records for the three sources, plus loaders for the JSON fixtures.

Recorder A (captures) is the one the lane writes to. Recorder B (notes) and
the calendars are read only. Times are ISO 8601 strings with an offset; the
matcher turns them into absolute instants.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field

from .config import Config


@dataclass
class Capture:
    """A recording in recorder A. Its title is often a calendar block name."""
    id: str
    title: str
    start: str
    duration_s: float
    speakers: list = field(default_factory=list)
    attendees: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    folders: list = field(default_factory=list)
    notes: str = ""                 # the recorder's own summary or key points
    title_set_by_user: bool = False

    def copy(self) -> "Capture":
        return copy.deepcopy(self)


@dataclass
class Note:
    """A note in recorder B. It sees every calendar, so its folder is the parity source."""
    id: str
    title: str
    start: str
    end: str
    participants: list = field(default_factory=list)
    folder: str = None
    event_id: str = None            # set only when the user linked the note to a calendar event
    body: str = ""


@dataclass
class Event:
    """A calendar event. tz_label is creator metadata and never used in arithmetic."""
    id: str
    calendar: str
    title: str
    start: str
    end: str
    attendees: list = field(default_factory=list)
    tz_label: str = None


@dataclass
class Inference:
    """A title and stream inferred from transcript content by the agent step."""
    capture_id: str
    title: str
    stream: str = None
    basis: str = ""
    signals: int = 1                # independent signals that agree; 2 or more makes it HIGH


@dataclass
class Rulings:
    """Decisions a person made. They outrank every inferred signal."""
    streams: dict = field(default_factory=dict)   # capture id -> stream
    fragments: set = field(default_factory=set)   # capture ids to treat as fragments


@dataclass
class Library:
    owner: list
    calendars: dict
    tags: list
    captures: list
    notes: list
    events: list

    def config(self) -> Config:
        return Config(owner=tuple(self.owner), calendars=dict(self.calendars))


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def library_from_dict(data: dict) -> Library:
    return Library(
        owner=list(data.get("owner", ["Ganesh Kumar"])),
        calendars={c["id"]: c.get("stream") for c in data.get("calendars", [])},
        tags=list(data.get("tags", [])),
        captures=[Capture(**c) for c in data.get("captures", [])],
        notes=[Note(**n) for n in data.get("notes", [])],
        events=[Event(**e) for e in data.get("events", [])],
    )


def load_library(path) -> Library:
    return library_from_dict(_read(path))


def load_inferences(path) -> dict:
    if not path:
        return {}
    return {i["capture_id"]: Inference(**i) for i in _read(path)}


def load_rulings(path) -> Rulings:
    if not path:
        return Rulings()
    data = _read(path)
    return Rulings(streams=dict(data.get("streams", {})), fragments=set(data.get("fragments", [])))
