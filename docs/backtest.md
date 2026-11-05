# Backtest: one cleanup on a real library (2026-11-02)

The numbers below are aggregates from a one-shot cleanup of my own recorder A library. No meeting content, titles, ids or people are published; only counts. The planner was the earlier version of the logic in `crosswalk/plan.py` (the code here is a clean rewrite of it), and the writes went out in batches of at most 25 meetings and 50 (meeting, tag) pairs.

## What changed

| Metric | Before | After | What it counts |
|---|---:|---:|---|
| Library | 1,152 | 1,152 | meetings in recorder A (nothing is deleted; the recorder had no delete) |
| Filed | 999 | 1,037 | meetings in at least one folder |
| Not in exactly one folder | 101 | 19 | captures of 60 s or more, not tagged fragment, in zero folders or in two |
| More than one stream tag | 52 | 0 | meetings carrying two stream tags at once |
| Mislabeled | 853 (74%) | 105 (9%) | meetings carrying the `mislabeled` marker, meaning the title is still a calendar block or auto title |
| Needs-review | 719 | 1 | meetings carrying `needs-review`, meaning a MEDIUM match that is not filed |
| Retired tags | 209 | 0 | meetings carrying any of the four retired tag names |
| Fragments identified | n/a | 109 | captures tagged `fragment` and listed for deletion by hand |

Writes: 1,689 tag removals and 141 tag additions, zero failed writes.

Against the drift targets (see `crosswalk/drift.py`): multi-stream 0, mislabeled under 10%, needs-review under 5% and retired tags 0 were met. Not-in-one-folder ended at 19, not 0. Those are left for a person by design: the lane does not file without evidence and never removes a capture from a folder on its own.

Most of the change is tag removals, for two reasons. An earlier rule attached `mislabeled` whenever the recorder title differed from the calendar title; the current rule keeps it only while the title is still a block or auto title, so markers on content titles came off. And `needs-review` comes off once a meeting is filed, which most of the 719 already were. The cleanup also removed retired and duplicate stream tags and attached the folder-name stream tag where it was missing.

## The two outside judges

A planner that grades its own plan proves little. Two checks were independent of it.

**1. Folder parity against the second recorder.** Recorder B files its notes in folders with the same names. For 40 October meetings that both recorders captured, the recorder A folder after the cleanup matched the recorder B folder on 37. All 3 misses were time collisions: two meetings on the calendar at the same hour, and the capture ended up in the other meeting's folder. That is the reason `match.py` now treats a tie between two same-hour candidates as LOW and `plan.py` refuses to file such a capture, even from its own old stream tag. `drift.parity()` runs the same check on the fixture.

**2. An independent re-read after the cleanup.** After the writes, a separate pass read the library back from the recorder and caught 1 capture the planner had put in the wrong folder. That is why `apply.py` decides success from a fresh read rather than from its own call count, and why only verified writes enter the ledger.

## How the fixture mirrors it

The same metric code runs on the 40 invented captures in `examples/`:

```
before  drift | not-one-folder 21 (captures >= 60 s) | multi-stream 2 | mislabeled 5 (12%) | needs-review 2 (5%) | fragment 0 | retired-tag 4 | library 40 | filed 18
after   drift | not-one-folder 5 (captures >= 60 s) | multi-stream 0 | mislabeled 3 (8%) | needs-review 1 (2%) | fragment 4 | retired-tag 0 | library 40 | filed 32
```

The fixture is built to contain one of each case, not to match the real distribution, so its percentages are not comparable to the table above.

## Caveats

- One library, one person, one cleanup. The thresholds were tuned on the same library they were tested on.
- The parity sample is 40 meetings from one month.
- The metrics come from the recorder's own state (tags and folders). They show the library is consistent with the rules; they do not prove every stream assignment is right. The parity check and the re-read are the evidence for that, and both are small samples.
