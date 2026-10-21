"""Print a debug capture's requests in order, each with its time and the
reply that answers it: where a question about the wire starts.

    python docs/log_requests.py [log ...] [--cmd NAME[,NAME]] [--grep TEXT]
                                [--from HH:MM[:SS]] [--to HH:MM[:SS]]
                                [--width N] [--asks]

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
import replay_log                                             # noqa: E402

# A field whose value signs the account in, by its key.
SECRET = re.compile(r"token|cookie|session|password|device_id|uuid|sign",
                    re.I)
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("logs", nargs="*")
    parser.add_argument("--cmd", default="")
    parser.add_argument("--grep", default="")
    parser.add_argument("--from", dest="start", default="")
    parser.add_argument("--to", dest="end", default="")
    parser.add_argument("--width", type=int, default=600)
    parser.add_argument("--asks", action="store_true")
    args = parser.parse_args(argv)
    names = {name for name in args.cmd.split(",") if name}
    needle = args.grep.lower()
    for name, lines in replay_log.find_logs(args.logs):
        print(f"== {name}")
        for stamp, request, reply in requests(lines):
            when = clock(stamp)
            if args.start and when < args.start or \
                    args.end and when[:len(args.end)] > args.end:
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
