"""Print a debug capture's requests in order, each with its time and the
reply that answers it: where a question about the wire starts.

    python docs/log_requests.py [log ...] [--cmd NAME[,NAME]] [--grep TEXT]
                                [--from HH:MM[:SS]] [--to HH:MM[:SS]]
                                [--width N] [--asks] [--changes REGEX]

A `log` is named as for `replay_log.py`: a debug capture's name or the
start of its stamp (`20261021_1404`), loose in `Vribbels/snapshots/` or
in their archive; the newest loose one where none is named. Several
print in order.

- `--cmd` keeps the requests of these commands, by the request's `cmd`
  or its `params.cmd`: `zero_orb`, `disaster_skilltree_level_up`.
- `--grep` keeps the requests whose request or reply holds TEXT, in any
  case.
- `--from` and `--to` keep the requests made between two times of day,
  as the log's own stamps give them: the machine's local time, where
  the Chaos runs' table and a snapshot's `capture_time` are UTC.
- `--width` cuts each request and reply to N characters (600 unless
  given; 0 prints them whole).
- `--asks` prints the requests alone, one line each.
- `--changes` follows a field instead: every key or plain value REGEX
  finds, in any case and at any depth of a request or reply, printed
  with its path and the request it rode on whenever it reads something
  new. Across several logs it says when a field first turned up and
  every reply that moved it. Takes `--from`, `--to` and `--width`.

A reply is the server message carrying the request's `qid`; a request
the log never answers prints `(no reply)`, and a message the server
pushed unasked is not shown. Sign-in fields -- tokens, cookies, the
session, device ids -- print as `<blanked>`, so the output can be
pasted.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay_log

# A field whose value signs the account in, by its key.
SECRET = re.compile(r"token|cookie|session|password|device_id|uuid|sign",
                    re.IGNORECASE)
BLANK = "<blanked>"


def blank(value):
    """`value` with every sign-in field's value blanked, at any depth."""
    if isinstance(value, dict):
        return {key: BLANK if SECRET.search(str(key)) else blank(held)
                for key, held in value.items()}
    if isinstance(value, list):
        return [blank(held) for held in value]
    return value


def requests(lines):
    """[(stamp, request, reply or None)] for one log's lines, in the
    order asked. A `qid` the client reuses after a reconnect answers the
    latest request carrying it."""
    out, waiting = [], {}
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        data = record.get("data")
        if record.get("direction") == "client_to_server" \
                and isinstance(data, list):
            for request in data:
                if isinstance(request, dict):
                    entry = [record.get("ts"), request, None]
                    out.append(entry)
                    waiting[request.get("qid")] = entry
        elif record.get("direction") == "server_to_client" \
                and isinstance(data, dict):
            entry = waiting.pop(data.get("qid"), None)
            if entry is not None:
                entry[2] = data
    return [tuple(entry) for entry in out]


def command(request):
    """`cmd`, or `cmd/params.cmd` where the request names a sub-command."""
    inner = (request.get("params") or {}).get("cmd")
    name = str(request.get("cmd") or "?")
    return f"{name}/{inner}" if isinstance(inner, str) else name


def clock(stamp):
    """The time of day of a log stamp (`2026-10-21T14:04:25.53`)."""
    return stamp[11:19] if isinstance(stamp, str) else ""


def _cut(value, width):
    text = json.dumps(blank(value), ensure_ascii=False)
    return text if not width or len(text) <= width else \
        text[:width] + f"... ({len(text)} chars)"


def _matches(value, path, pattern, out):
    """Add to `out` (path, JSON text) for each key under `value` that
    `pattern` finds or each plain value it finds, not looking inside
    what a key's match already takes."""
    if isinstance(value, dict):
        for key, held in value.items():
            where = f"{path}.{key}"
            if pattern.search(str(key)):
                out.append((where, json.dumps(blank(held),
                                              ensure_ascii=False)))
            else:
                _matches(held, where, pattern, out)
    elif isinstance(value, list):
        for at, held in enumerate(value):
            _matches(held, f"{path}[{at}]", pattern, out)
    elif pattern.search(str(value)):
        out.append((path, json.dumps(value, ensure_ascii=False)))


def print_changes(logs, pattern, width, start="", end=""):
    """Each new value of what `pattern` finds, with the request it rode
    on, across `logs` in order. `reset_resp` is left out of the path:
    what rides there is the same field as at the top level."""
    last = {}
    for name, lines in logs:
        print(f"== {name}")
        for stamp, request, reply in requests(lines):
            when = clock(stamp)
            if (start and when < start) or (end and when[:len(end)] > end):
                continue
            found = []
            _matches(request, "ask", pattern, found)
            _matches(reply, "reply", pattern, found)
            told = False
            for path, text in found:
                short = path.replace(".reset_resp", "")
                if last.get(short) == text:
                    continue
                last[short] = text
                if not told:
                    print(when, command(request),
                          _cut(request.get("params"), 200))
                    told = True
                print("   ", path, "=",
                      text if not width or len(text) <= width else
                      text[:width] + f"... ({len(text)} chars)")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("logs", nargs="*")
    parser.add_argument("--cmd", default="")
    parser.add_argument("--grep", default="")
    parser.add_argument("--from", dest="start", default="")
    parser.add_argument("--to", dest="end", default="")
    parser.add_argument("--width", type=int, default=600)
    parser.add_argument("--asks", action="store_true")
    parser.add_argument("--changes", default="")
    args = parser.parse_args(argv)
    if args.changes:
        print_changes(replay_log.find_logs(args.logs),
                      re.compile(args.changes, re.IGNORECASE), args.width,
                      args.start, args.end)
        return 0
    names = {name for name in args.cmd.split(",") if name}
    needle = args.grep.lower()
    for name, lines in replay_log.find_logs(args.logs):
        print(f"== {name}")
        for stamp, request, reply in requests(lines):
            when = clock(stamp)
            if (args.start and when < args.start) or \
                    (args.end and when[:len(args.end)] > args.end):
                continue
            asked = command(request)
            if names and not (names & {request.get("cmd"), asked,
                                       asked.split("/")[-1]}):
                continue
            if needle and needle not in json.dumps(
                    [request, reply], ensure_ascii=False).lower():
                continue
            if args.asks:
                print(when, asked, _cut(request.get("params"), args.width))
                continue
            print(f"{when} {asked} (qid {request.get('qid')})")
            print("   ask  ", _cut(request.get("params"), args.width))
            print("   reply", "(no reply)" if reply is None
                  else _cut(reply, args.width))
    return 0


if __name__ == "__main__":
    sys.exit(main())
