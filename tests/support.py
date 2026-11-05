"""Shared helpers for the tests. Not a test module."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
EXAMPLES = os.path.join(ROOT, "examples")

from adapters.fake import FakeCalendar, FakeNotes, FakeRecorder  # noqa: E402
from crosswalk import Ledger, Library, apply_plan, build_plan, load_inferences, load_library, load_rulings  # noqa: E402


def load():
    lib = load_library(os.path.join(EXAMPLES, "library.json"))
    inf = load_inferences(os.path.join(EXAMPLES, "inferences.json"))
    rul = load_rulings(os.path.join(EXAMPLES, "rulings.json"))
    return lib, inf, rul


def plan_fixture(ledger=None):
    lib, inf, rul = load()
    return build_plan(lib, inf, rul, ledger)


def ops_for(plan, cid, gate=None):
    return [o for o in plan.ops if o.capture_id == cid and (gate is None or o.gate == gate)]


def kinds(plan, cid):
    return sorted((o.kind, o.target) for o in ops_for(plan, cid, gate="auto"))


def row(plan, cid):
    return next(r for r in plan.rows if r["capture_id"] == cid)


def snapshot(lib, recorder):
    return Library(lib.owner, lib.calendars, recorder.list_tags(), recorder.search(),
                   FakeNotes(lib.notes).search(), FakeCalendar(lib.events).list_events())


def cycle(approve=False):
    """Plan and apply once against a fresh fake recorder. Returns (lib, inf, rul, recorder, ledger, plan, report)."""
    lib, inf, rul = load()
    recorder = FakeRecorder(lib.captures, lib.tags)
    ledger = Ledger()
    plan = build_plan(snapshot(lib, recorder), inf, rul, ledger)
    report = apply_plan(plan, recorder, ledger, approve_removals=approve)
    return lib, inf, rul, recorder, ledger, plan, report
