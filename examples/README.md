# Examples

A synthetic library: 40 captures in recorder A, 15 notes in recorder B, 27 calendar events across four calendars. Every person, company and meeting is invented. The company names are the usual fictional sample names (Contoso, Fabrikam, Litware).

- `library.json`: owner, calendars (each mapped to a stream or none), the recorder's tag catalog, captures, notes, events.
- `inferences.json`: what the transcript step produced for two captures (title, stream, basis, number of agreeing signals).
- `rulings.json`: decisions a person made (one stream, one fragment). Rulings outrank every inferred signal.

The `primary` calendar is the only one recorder A can see, so it holds the "Focus Time" blocks that recorder A names captures after. The real meetings live on `team`, `partners` and `shared`.

## Planted cases

| Capture | Case | What the planner does |
|---|---|---|
| cap-01 | "Focus Time" over a real Product meeting with a linked note | rename to the event title, file in Product, tag Product |
| cap-02 | block title; event has a misleading Los Angeles timezone label; stale `mislabeled` | matches by absolute instant; rename, file, detach `mislabeled` in the same run |
| cap-03, cap-04, cap-32 | fragments: auto title under 5 min, 35 s, 20 s | tag `fragment` only; never filed or renamed |
| cap-13 | a 7-minute pocket recording ruled a fragment | tag `fragment` only |
| cap-16 | 4-minute block-titled capture that matched a real note | not a fragment; renamed and filed |
| cap-05 | MEDIUM match (head count and content, no names) with a stream | filed, renamed, `Speaker 2` fixed; no `needs-review` |
| cap-14 | MEDIUM match on a calendar with no stream | `needs-review`, renamed, not filed |
| cap-06 | already filed; one placeholder speaker | rename and `Speaker 3` fixed from the roster |
| cap-07 | title set by the user; retired tag `Mentorship` | title kept; retired tag out, filed in Mentoring, `Maya` to the full name |
| cap-08 | **time collision**: two events at the same hour, an old Product tag | LOW, not filed, listed for a person |
| cap-09 | solo note that shares words with the capture at the same hour | attendee veto rejects it; matches the group event |
| cap-10 | **two folders**, two stream tags | removal from the second folder planned behind approval; stray tag detached |
| cap-11 | filed in Product, tagged Product and Partners | Partners detached |
| cap-12 | ad hoc hiring loop debrief; unlinked note names the wrong person | content-inferred title (two signals, HIGH), filed in Hiring |
| cap-27 | ad hoc call, nothing to match | content-inferred title (one signal, MEDIUM), filed in Product |
| cap-15 | the capture summary contains instructions to the assistant | ignored: zero ops |
| cap-17 | captured with a UTC timestamp, event stored in local offset | HIGH match by instant |
| cap-21, cap-28, cap-29 | **retired tags** `Recruiting`, `Partnerships`, `Courses` | detached; `Recruiting` still points the unfiled capture at Hiring |
| cap-23 | LOW match (time only) | only the `mislabeled` marker; no rename, no filing |
| cap-24 | MEDIUM match through an unlinked note (a reading group) | filed in Learning; title kept and marked `mislabeled` |
| cap-25, cap-26 | ambiguous first name, a misspelling, a roster that is a login handle | one fix, two skips |
| cap-18, cap-19 | stale `needs-review` and `mislabeled` on filed meetings | detached |
| cap-20 | a user tag outside the vocabulary | never touched |
| cap-22 | no evidence at all | listed, nothing written |
| cap-30, cap-31 | unfiled with one stream tag; unfiled with a ruling | filed |
| cap-33 to cap-40 | clean | zero ops |
