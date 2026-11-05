"""Command line.

  python3 -m crosswalk demo [--approve-removals]
      Full cycle on examples/ against the in-memory fake recorder:
      drift before, plan, apply, verify, drift after, re-plan, parity.
  python3 -m crosswalk plan LIBRARY [--inferences F] [--rulings F] [--ledger F] [--out DIR]
      Write crosswalk.json, plan.json and batches/ for a library file. Writes nothing to any recorder.
  python3 -m crosswalk verify PLAN_JSON AFTER_LIBRARY --ledger F [--approved]
      After the batches went out through a connector: compare a fresh read of the recorder
      with the plan and record only the confirmed writes in the ledger.
  python3 -m crosswalk drift LIBRARY
      Print the drift line and any missed targets.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

from .apply import apply_plan, verify_ops
from .drift import measure, parity
from .ledger import Ledger
from .model import Library, load_inferences, load_library, load_rulings
from .plan import Op, build_plan, write_outputs

EXAMPLES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples")


def _print_plan(plan):
    c = plan.counts()
    tiers = " ".join("%s %d" % kv for kv in c["confidence"].items())
    ops = ", ".join("%s %d" % kv for kv in c["ops"].items()) or "none"
    print("plan    %d captures | %s" % (c["captures"], tiers))
    print("        ops: %s | gated %d | skipped by ledger %d" % (ops, c["gated"], c["skipped_by_ledger"]))
    batches = plan.batches()
    if batches:
        biggest = max(batches, key=lambda b: len(b[1]))
        print("        %d recorder calls, largest carries %d pairs" % (len(batches), len(biggest[1])))
    for item in plan.review:
        print("        review %-7s %-20s %s" % (item["capture_id"], item["reason"], item["detail"]))


def demo(approve_removals=False):
    from adapters.fake import FakeCalendar, FakeNotes, FakeRecorder

    lib = load_library(os.path.join(EXAMPLES, "library.json"))
    inferences = load_inferences(os.path.join(EXAMPLES, "inferences.json"))
    rulings = load_rulings(os.path.join(EXAMPLES, "rulings.json"))
    cfg = lib.config()
    recorder, notes, calendar = FakeRecorder(lib.captures, lib.tags), FakeNotes(lib.notes), FakeCalendar(lib.events)
    ledger = Ledger()

    def snapshot():
        return Library(lib.owner, lib.calendars, recorder.list_tags(), recorder.search(), notes.search(),
                       calendar.list_events())

    print("before  " + measure(recorder.search(), cfg).line())
    plan = build_plan(snapshot(), inferences, rulings, ledger, cfg)
    _print_plan(plan)
    report = apply_plan(plan, recorder, ledger, approve_removals=approve_removals)
    print(report.summary())
    after = recorder.search()
    d = measure(after, cfg)
    print("after   " + d.line())
    print("        targets missed: %s" % ("; ".join(d.breaches()) or "none"))
    again = build_plan(snapshot(), inferences, rulings, ledger, cfg)
    print("re-plan %d auto ops, %d gated" % (len(again.auto_ops), len(again.gated_ops)))
    p = parity(after, again.rows, lib.notes)
    print("parity  recorder A folder agrees with recorder B folder on %d of %d matched meetings%s"
          % (p["agree"], p["total"], (" (miss: %s)" % ", ".join(p["miss"])) if p["miss"] else ""))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m crosswalk", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    d = sub.add_parser("demo")
    d.add_argument("--approve-removals", action="store_true")
    p = sub.add_parser("plan")
    p.add_argument("library")
    p.add_argument("--inferences")
    p.add_argument("--rulings")
    p.add_argument("--ledger")
    p.add_argument("--out", default="out")
    v = sub.add_parser("verify")
    v.add_argument("plan")
    v.add_argument("after")
    v.add_argument("--ledger", required=True)
    v.add_argument("--approved", action="store_true", help="the gated removals were approved and sent")
    r = sub.add_parser("drift")
    r.add_argument("library")
    args = ap.parse_args(argv)

    if args.cmd == "verify":
        with open(args.plan, encoding="utf-8") as fh:
            ops = [Op(**o) for o in json.load(fh)["ops"]]
        ops = [o for o in ops if o.gate == "auto" or args.approved]
        ledger = Ledger(args.ledger)
        ok, unverified = verify_ops(ops, load_library(args.after).captures, ledger)
        ledger.save()
        print("verify  confirmed %d (%s) | unverified %d" % (
            len(ok), ", ".join("%s %d" % kv for kv in sorted(Counter(o.kind for o in ok).items())) or "none",
            len(unverified)))
        for o in unverified:
            print("        unverified %s %s %s %s" % (o.capture_id, o.kind, o.target, o.value))
        return 0 if not unverified else 1

    if args.cmd == "demo":
        return demo(args.approve_removals)
    if args.cmd == "plan":
        lib = load_library(args.library)
        plan = build_plan(lib, load_inferences(args.inferences), load_rulings(args.rulings), Ledger(args.ledger))
        write_outputs(plan, args.out)
        _print_plan(plan)
        print("wrote   %s/crosswalk.json, plan.json, batches/" % args.out)
        return 0
    if args.cmd == "drift":
        lib = load_library(args.library)
        dr = measure(lib.captures, lib.config())
        print(dr.line())
        print("targets missed: %s" % ("; ".join(dr.breaches()) or "none"))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
