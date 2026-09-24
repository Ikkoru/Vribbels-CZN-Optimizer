"""How every event on record would read on the Checklist, login by login.

    python docs/events_replay.py              # every event, every login
    python docs/events_replay.py devil node   # events matching a word

Replays each `mission/get_list` reply in every debug log, loose and
archived, through the Checklist's own event readers, and prints a line
whenever an event's reading CHANGES. At the end it prints what the
family records came to -- totals and final rewards -- as the program
would have learned them over the same history.

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

Reads the snapshots folder, writes nothing there. The family records
go to a scratch ChecklistManager in a temp directory, never to
`Vribbels/settings/`.
"""

import datetime
import gzip
import io
import json
import os
import sys
import tarfile
import tempfile
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "Vribbels"
SNAPS = SOURCE / "snapshots"
sys.path.insert(0, str(SOURCE))
os.chdir(SOURCE)

import checklist_manager                                      # noqa: E402
import schedules                                              # noqa: E402
from capture import archive                                   # noqa: E402
from ui.tabs import checklist_tab as ct                       # noqa: E402

# What a login reply is reduced to: the fields the event readers take.
MISSION_FIELDS = ("event_mission_reward_entities", "attendance_entities",
                  "combat_trial_entities")


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


def main(argv):
    want = [a for a in argv[1:] if not a.startswith("-")]
    print("Reading every debug log; this takes a minute.", flush=True)
    found, windows = logins()
    manager = checklist_manager.ChecklistManager(
        Path(tempfile.mkdtemp(prefix="events_replay_")))
    manager.load()
    stub = SimpleNamespace(context=SimpleNamespace(checklist_manager=manager))
    last = {}
    for name, login in found:
        raw = {"mission_entities": {row["res_id"]: row
                                    for row in login["missions"]
                                    if isinstance(row, dict)},
               "event_schedules": windows}
        for field in MISSION_FIELDS:
            raw[field] = login[field] or []
        raw.update(login["tables"])
        now = login["now"]
        ct.ChecklistTab._recall_event_totals(stub, raw, now)
        ct.ChecklistTab._recall_finals(stub, raw, now)
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
    print()
    print("Families that paid a final reward:")
    for family, events in sorted(manager.finals.items()):
        print("   %-20s %s" % (family, ", ".join(events)))
    print("What finished instalments held:")
    for family, held in sorted(manager.events.items()):
        print("   %-20s %s" % (family, ", ".join(
            "%s %d" % pair for pair in sorted(held.items()))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
