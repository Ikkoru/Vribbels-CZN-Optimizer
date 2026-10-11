"""How every event on record would read on the Checklist, login by login.

    python docs/events_replay.py              # every event, every login
    python docs/events_replay.py devil node   # events matching a word
    python docs/events_replay.py --fallback   # the fallback, scored

Replays each `mission/get_list` reply in every debug log, loose and
archived, through the Checklist's own event readers, and prints a line
whenever an event's reading CHANGES. The totals are the game client's,
read now (`game_client`), as the program reads them at launch.

**`--fallback` scores the reading of an event the client does not
hold** (`docs/events.md`, *An event the client does not hold*): every
event the client does hold is replayed with its own entry hidden and
its family's left in, and each reading is judged against the client's
total. `short`, `long`, `false-done` and `LIKELY-WRONG` are the wrong
answers; a change to the fallback is kept only while it adds none.

**Use it after mapping or changing anything under `EVENT_READERS`**: a
reader is checked against every instalment the account has seen rather
than against the one it was written from. The Node Lists reading
nothing, an arena counted as 40 rewards where it held 17 and the step
tracks reading `0/1+?` were all found this way.

Why logins and not snapshots: snapshots carry event data only from
the day the capture started keeping it, while a debug log has the whole
login burst. Each login becomes a snapshot-shaped `raw` -- its event
missions, completion records, streaks and trials, the `event_*` tables
of the same log's `event/get_list`, and every schedule window any log
has carried (a window is a fixed definition, so the union is safe).
`now` is the reply's own server time.

Reads the snapshots folder and the game client, and writes nothing.
"""

import collections
import datetime
import gzip
import io
import json
import os
import re
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "Vribbels"
SNAPS = SOURCE / "snapshots"
sys.path.insert(0, str(SOURCE))
os.chdir(SOURCE)

import game_client                                            # noqa: E402
import schedules                                              # noqa: E402
from capture import archive                                   # noqa: E402
from ui.tabs import checklist_tab as ct                       # noqa: E402

# What a login reply is reduced to: the fields the event readers take.
MISSION_FIELDS = ("event_mission_reward_entities", "attendance_entities",
                  "combat_trial_entities")

# What `--fallback` scores: the groups whose readers take a total, and
# how a reading's figures are read back.
SCORED_GROUPS = ("EVENT_SCHEDULE", "EVENT_NODELIST_PAGE", "EVENT_DAILY_CHECK")
READING = re.compile(r"^(~?)(\d+)/(\d+)(\+\?)?$")


def logs():
    """(name, text stream) for every debug log, oldest first, once each."""
    seen = set()
    for name, handle in archive.stream_members(SNAPS, "websocket_debug_"):
        if name in seen:
            continue
        seen.add(name)
        yield name, io.TextIOWrapper(handle, encoding="utf-8",
                                     errors="replace")
    for path in sorted(SNAPS.glob("websocket_debug_*.jsonl.gz")):
        if archive.member_name(path) not in seen:
            with gzip.open(path, "rt", encoding="utf-8",
                           errors="replace") as fh:
                yield path.name, fh


def logins():
    """[(log, login dict)], plus every schedule window seen anywhere.

    A login dict holds the `mission/get_list` reply's event fields and
    the `event/get_list` tables that came before it in the same log.
    """
    windows, found = {}, []
    for name, fh in logs():
        pending, tables = {}, {}
        for line in fh:
            if not line.strip():
                continue
            try:
                frame = json.loads(line)
            except ValueError:
                continue
            data = frame.get("data")
            rows = data if isinstance(data, list) else [data]
            if frame.get("direction") == "client_to_server":
                for r in rows:
                    if isinstance(r, dict) and r.get("qid") is not None:
                        pending[r["qid"]] = "%s/%s" % (
                            r.get("cmd"), (r.get("params") or {}).get("cmd"))
                continue
            for r in rows:
                if not isinstance(r, dict):
                    continue
                cmd = pending.pop(r.get("qid"), "?")
                sched = r.get("event_schedules")
                if isinstance(sched, dict):
                    for group, events in sched.items():
                        if isinstance(events, dict):
                            windows.setdefault(group, {}).update(events)
                if cmd == "event/get_list":
                    tables = {k: v for k, v in r.items()
                              if k.startswith("event_")}
                if cmd == "mission/get_list":
                    login = {k: r.get(k) for k in MISSION_FIELDS}
                    login["missions"] = r.get("event_mission_entities") or []
                    login["tables"] = dict(tables)
                    login["now"] = r.get("service_server_time") or \
                        datetime.datetime.fromisoformat(frame["ts"]).replace(
                            tzinfo=datetime.UTC).timestamp()
                    found.append((name, login))
        print("  read %s" % name, file=sys.stderr, flush=True)
    return found, windows


def login_raw(login, windows):
    """One login as the snapshot-shaped `raw` the readers take."""
    raw = {"mission_entities": {row["res_id"]: row
                                for row in login["missions"]
                                if isinstance(row, dict)},
           "event_schedules": windows}
    for field in MISSION_FIELDS:
        raw[field] = login[field] or []
    raw.update(login["tables"])
    return raw


def verdict(words, state, truth):
    """What one fallback reading says against the client's total."""
    found = READING.match(str(words))
    if not found:
        return "no-reading" if not words else "unparsed"
    tilde, claimed, total, more = found.groups()
    claimed, total = int(claimed), int(total)
    if state == ct.DONE and claimed < truth:
        return "false-done"
    if state == ct.LIKELY_DONE and claimed < truth:
        return "LIKELY-WRONG"
    if total > truth:
        return "long"
    if more:
        return "floor"
    if total < truth:
        return "short"
    return "expected" if tilde else "exact"


def score_fallback(found, windows, want):
    """Print `--fallback`'s verdicts, per event and in all."""
    known = game_client.known_event_totals()
    by_key = ct._known_by_key(known)
    tally = collections.Counter()
    per_event = collections.defaultdict(collections.Counter)
    for _name, login in found:
        raw, now = login_raw(login, windows), login["now"]
        for group in SCORED_GROUPS:
            for event, window in schedules.all_live(group, raw, now):
                held = known.get(event) or by_key.get(ct._event_key(event))
                if held is None or (want and not any(w in event
                                                     for w in want)):
                    continue
                key = ct._event_key(event)
                trial = dict(raw)
                ct.event_totals_onto(trial, now, {
                    k: v for k, v in known.items()
                    if ct._event_key(k) != key})
                segments = list(ct.EVENT_READERS[group](
                    trial, event, window, now))
                words, state = segments[0] if segments else ("", None)
                said = verdict(words, state, held[0] + held[1])
                tally[said] += 1
                per_event[event][said] += 1
    for event, counts in sorted(per_event.items()):
        print("  %-32s %s" % (event, dict(counts.most_common())))
    print("in all:", dict(tally.most_common()))


def main(argv):
    want = [a for a in argv[1:] if not a.startswith("-")]
    install = game_client.find_install()
    if install is not None:
        game_client.use(game_client.read_facts(install))
    else:
        print("No game client found: the shipped totals stand in.")
    print("Reading every debug log; this takes a minute.", flush=True)
    found, windows = logins()
    if "--fallback" in argv:
        score_fallback(found, windows, want)
        return 0
    last = {}
    for name, login in found:
        raw = login_raw(login, windows)
        now = login["now"]
        ct.event_totals_onto(raw, now)
        for group in ct.EVENT_GROUPS:
            for event, window in schedules.all_live(group, raw, now):
                if want and not any(w in event for w in want):
                    continue
                reader = ct.EVENT_READERS.get(group)
                reading = str(list(reader(raw, event, window, now))
                              if reader else "no reader")
                if last.get(event) != reading:
                    print("%s  %-22s %-30s %s"
                          % (name[16:31], group, event, reading))
                    last[event] = reading
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
