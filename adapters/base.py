"""Adapter interfaces. See adapters/README.md for the contract behind each method.

Only the recorder adapter has write methods. The notes and calendar adapters
are read only by construction: the write fence is the absence of a method,
not a flag someone can flip.
"""
from __future__ import annotations

from typing import Iterable, List, Optional, Protocol

from crosswalk.model import Capture, Event, Note


class RecorderAdapter(Protocol):
    """Recorder A: the recorder this lane corrects."""

    # read
    def search(self, start: Optional[str] = None, end: Optional[str] = None) -> List[Capture]: ...
    def get(self, ids: Iterable[str]) -> List[Capture]: ...
    def folder_members(self, folder: str) -> List[str]: ...
    def list_tags(self) -> List[str]: ...

    # write (scoped; every call may raise crosswalk.apply.ScopeError)
    def attach_tags(self, assignments: list) -> None: ...      # <= 25 meetings, <= 50 pairs
    def detach_tags(self, assignments: list) -> None: ...      # same limits
    def add_to_folder(self, folder: str, ids: list) -> None: ...
    def remove_from_folder(self, folder: str, ids: list) -> None: ...  # approval only
    def rename(self, meeting_id: str, title: str) -> None: ...  # <= 100 chars
    def update_speakers(self, meeting_id: str, mappings: list) -> None: ...


class NotesAdapter(Protocol):
    """Recorder B: read only. Sees every calendar; its folder is the parity source."""

    def search(self, start: Optional[str] = None, end: Optional[str] = None) -> List[Note]: ...


class CalendarAdapter(Protocol):
    """All calendars, read only. Each event keeps its own offset; tz labels are metadata."""

    def list_events(self, start: Optional[str] = None, end: Optional[str] = None) -> List[Event]: ...
