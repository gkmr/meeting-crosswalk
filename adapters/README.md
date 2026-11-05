# Adapters

The lane reads three sources and writes to one. Each source sits behind a small interface (`adapters/base.py`), so the planner never knows which product is on the other side. This repo ships the interfaces and an in-memory fake (`adapters/fake.py`) that the tests and the demo use. It makes no real API calls.

In my setup the recorders were reached through their MCP connectors from an agent session. The tool names below are what those connectors looked like at the time of writing; they change, so treat them as a guide for writing your own adapter, not as a contract. Unofficial, no affiliation with any vendor.

## Recorder A: the one this lane corrects

| Method | Contract |
|---|---|
| `search(start, end)` | Captures whose start falls in the window. Each has `id`, `title`, `start` (ISO 8601 with offset), `duration_s`, `speakers` (labels as the transcript shows them, including `Speaker N`), `attendees`, `tags`, `folders`, `notes` (the recorder's own summary or key points) and `title_set_by_user`. |
| `get(ids)` | The same records for specific ids. Used for read-back verification after writes. |
| `folder_members(folder)` | Ids in a folder. Read membership from the folder side by searching with a folder filter; in my setup the folder detail call returned stale membership. |
| `list_tags()` | Every tag name the recorder knows. Checked before any attach so new names are never created by accident. |
| `attach_tags(assignments)` / `detach_tags(assignments)` | `[{"meeting_id", "tag_names": [...]}]`, at most 25 meetings and 50 pairs per call. Tag names are case-insensitive. Attaching a name that does not exist creates it. |
| `add_to_folder(folder, ids)` | Folder must already exist. At most 25 ids per call in this planner. |
| `remove_from_folder(folder, ids)` | Only after a person approves. The unattended lane never calls it. |
| `rename(meeting_id, title)` | At most 100 characters. A lane rename must not mark the title as user-set. |
| `update_speakers(meeting_id, mappings)` | `[{"from": label, "to": name}]`, one call per meeting. |

Every write may raise `crosswalk.apply.ScopeError`. That means the token predates the write scopes; reconnecting the connector re-runs the authorization. The executor stops the whole write phase on the first one and does not retry.

**`title_set_by_user`.** If the recorder does not expose it, derive it: a title that is not generic, is not the primary calendar block at that hour, and is not in the ledger as a lane rename was set by a person. Never overwrite it.

**Delete.** The recorder in my setup had no delete. Fragments are tagged `fragment` and listed for a person.

## Recorder B: read only

| Method | Contract |
|---|---|
| `search(start, end)` | Notes with `id`, `title`, `start`, `end`, `participants`, `folder` (its stream), `event_id` (set only when the user linked the note to a calendar event) and `body`. |

Recorder B sees every calendar, so its folder is the parity source and its participants are a roster for speaker fixes. Its titles are trusted only when the note is linked to the matched event.

## Calendars: read only

| Method | Contract |
|---|---|
| `list_events(start, end)` | Events across all calendars, each with `id`, `calendar`, `title`, `start`, `end` (ISO 8601 with offset), `attendees` and `tz_label`. |

Time is the stored date-time plus its embedded offset. `tz_label` (the zone the creator picked) is metadata and never used in arithmetic. Read calendars one at a time and page them: event descriptions can be very long. Each calendar id maps to a stream (or none) in the library's `calendars` list.

## The write fence

Only the recorder A adapter has write methods. `FakeNotes` and `FakeCalendar` have none, and a test checks that. A real recorder B or calendar adapter should be written the same way: if the method does not exist, no prompt or bug can call it.

## The fake

`FakeRecorder(captures, tags, scope_error=False, drop_writes=False)` holds captures in memory and enforces the same limits as the real thing: batch sizes, title length, known folders, speaker labels that exist. `scope_error=True` simulates a token without write scope. `drop_writes=True` simulates a recorder that says yes and changes nothing, which is what read-back verification is for. `calls` records every write call for assertions.
