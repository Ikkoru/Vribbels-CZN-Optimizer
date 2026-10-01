"""Read each Great Rift division's top score off cznmetadecks.com, for
`RIFT_RECORDED_TOPS` in `Vribbels/stats_history.py`.

    python docs/rift_tops_fetch.py 4               # season 4, both parts
    python docs/rift_tops_fetch.py 4 --part 2      # one part
    python docs/rift_tops_fetch.py 4 --final       # mark them finals
    python docs/rift_tops_fetch.py 4 --pause 10    # seconds between requests

Prints the table's lines for both servers, ready to paste over the
part's old ones. Reads only; nothing in the repo is written.

**The site keeps each subdivision's top hundred on both servers**, as
the game's own rows, in the page itself: `/meta?define=<part>` carries
every row as `{"s": read at, "r": rank id, "u": user id, "n": name,
"sc": score}`. A row's score is `sc` over 10^8 -- the rest is a
tie-break -- and a user id's first digit is its server. Only each
subdivision's top score and the newest `s` are kept, **never who**.

A division's top is its subdivision I's (`stats_history.rift_table`
says why), Master's first. The newest `s` is the reading's date: a
part whose newest row was read after the part ended is its final, which
is what `--final` says -- the site does not.

One request per part, `--pause` seconds apart (5 by default), and one
retry after the same pause.
"""

import argparse
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone

SITE = "https://cznmetadecks.com/meta?define=%s"
AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VribbelsRiftTops/1.0"
# A user id's first digit, as the site's rows give it.
SERVERS = {"1": "asia", "3": "global"}
# Each division's subdivision I, Master's first: 30 is Master I, 5 is
# Bronze I, on `stats_history`'s thirty-step scale.
DIVISION_TOPS = (30, 25, 20, 15, 10, 5)
ROW = re.compile(r'"s":"([^"]+)","r":"disaster_s\d+_rank_best_\d+_(\d+)",'
                 r'"u":"(\d+)","n":"(?:[^"\\]|\\.)*","sc":(\d+)')


def fetch(url, pause):
    for attempt in (1, 2):
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": AGENT})
            with urllib.request.urlopen(request, timeout=60) as reply:
                return reply.read().decode("utf-8", "replace")
        except OSError as e:
            if attempt == 2:
                raise
            print("  retrying after %s" % e, file=sys.stderr)
            time.sleep(pause)


def tops_of(html):
    """{server: ({subdivision: top score}, newest read)} off one page."""
    # The rows sit inside a JSON string in the page, quotes escaped.
    text = html.replace('\\"', '"')
    found = {}
    for read, number, user, score in ROW.findall(text):
        server = SERVERS.get(user[:1])
        if server is None:
            continue
        tops, newest = found.setdefault(server, ({}, ""))
        best = int(score) // 10 ** 8
        number = int(number)
        tops[number] = max(tops.get(number, 0), best)
        if read > newest:
            found[server] = (tops, read)
    return found


def stamp(read):
    """The site's ISO time as the table writes one, UTC to the second."""
    at = datetime.fromisoformat(read.replace("Z", "+00:00"))
    return at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("season", type=int)
    parser.add_argument("--part", type=int, choices=(1, 2))
    parser.add_argument("--final", action="store_true")
    parser.add_argument("--pause", type=float, default=5.0)
    args = parser.parse_args()
    parts = (args.part,) if args.part else (1, 2)
    lines = []
    for index, part in enumerate(parts):
        if index:
            time.sleep(args.pause)
        define = "disaster_s%02d_rank_%02d" % (args.season, part)
        print("reading %s" % define, file=sys.stderr)
        found = tops_of(fetch(SITE % define, args.pause))
        if not found:
            print("  no rows: the site does not list %s" % define,
                  file=sys.stderr)
            continue
        for server in ("global", "asia"):
            if server not in found:
                print("  no %s rows" % server, file=sys.stderr)
                continue
            tops, newest = found[server]
            values = tuple(tops.get(n) for n in DIVISION_TOPS)
            when = "FINAL" if args.final else '"%s"' % stamp(newest)
            print("  %s newest row read %s" % (server, stamp(newest)),
                  file=sys.stderr)
            lines.append(
                '    ("%s", %d, %d): (%s,\n'
                '        CZNMETADECKS %% "%s",\n'
                '        %r),' % (server, args.season, part, when, define,
                                  values))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
