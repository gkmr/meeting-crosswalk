# Changelog

## 1.0.0 (2026-11-05)

First public version: a clean rewrite of the private lane at v3.1.

- `crosswalk/` package: matching by absolute instant with HIGH, MEDIUM and LOW tiers, attendee-contradiction veto, time-collision rule; generic title regex and title trust order; folder-first planner with a closed tag vocabulary, fragment rule and roster-only speaker fixes; batches of at most 25 meetings and 50 pairs; executor with read-back verification and a `verify` command for connector runs; idempotency ledger; drift metrics and a parity judge.
- Adapter interfaces and an in-memory fake recorder. No real API calls.
- Public versions of the lane prompt and the briefer skill.
- 40-capture synthetic fixture with planted cases, 63 unit tests.
- Aggregate numbers from the 2026-11-02 backtest on a 1,152-meeting library.

## Before 1.0.0 (private)

- v3.1 (2026-11-02): folders became the stream truth, closed tag vocabulary, fragment tag, monthly drift line. One-shot cleanup of the whole library.
- 2026-10-20: renames and folder writes switched on; content-inferred titles.
- 2026-09-18: folder and tag parity with the second recorder; speaker fixes from transcript labels.
- 2026-08-04: write-back to the recorder (tags, speakers), tag-create race guard, attendee-contradiction veto.
- 2026-07-15: calendar instant rule after a timezone-label incident.
