"""Read the game client's own data tables and English text. Reads only.

    python docs/client_tables.py                     what is installed
    python docs/client_tables.py --list REGEX        archived paths
    python docs/client_tables.py --table NAME        one table, as TSV
    python docs/client_tables.py --text REGEX        English text by id or words
    python docs/client_tables.py --ship              rewrite the shipped names

`--table` takes a table's archived name without `db/` and `.db`, such
as `event@event` or `char_base@char_combatant`; `--out FILE` writes the
TSV there instead of printing it, `--rows N` prints only the first N,
and `--client DIR` names an install other than the one the program
finds. What each table holds, and what was checked against it, is
`docs/client_data.md`.

`--ship` rewrites `Vribbels/game_data/from_client.py`, what a player
whose client the program cannot read sees instead: run it after a
patch, before a release, and review its diff.

The reader itself is `Vribbels/game_client.py`, the same one the
program runs at launch. Python 3.14, for `compression.zstd`.
"""

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "Vribbels"))

import game_client                                            # noqa: E402
from game_client import Client                                # noqa: E402

SHIPPED = REPO / "Vribbels" / "game_data" / "from_client.py"

SHIPPED_HEAD = '''"""Event names and Excursion type counts read off the game client.

Written by `python docs/client_tables.py --ship`, as of the game build
`BUILD`; never edited by hand. What a player's own client says wins
over these (`game_client`), so this is what a player sees whose client
the program could not find or read.

ASCII throughout: a name's other characters are written as escapes.
"""

'''


def _tsv(columns, rows):
    clean = str.maketrans({"\t": " ", "\n": " ", "\r": " "})
    yield "\t".join(columns)
    for row in rows:
        yield "\t".join(row[c].translate(clean) for c in columns)


def shipped_source(client):
    """The text of `from_client.py` for what `client` holds."""
    names = game_client.event_names(client)
    visits = game_client.excursion_types(client)
    lines = [SHIPPED_HEAD, f"BUILD = {client.archive.build}", "",
             "# {schedule id: English name}. See game_client.event_names.",
             "EVENT_NAMES = {"]
    lines += [f"    {ascii(key)}: {ascii(name)},"
              for key, name in sorted(names.items())]
    lines += ["}", "",
              "# {combatant res_id: Excursion types}. See "
              "game_client.excursion_types.",
              "EXCURSION_TYPES = {"]
    lines += [f"    {res_id}: {count}," for res_id, count
              in sorted(visits.items())]
    lines += ["}", ""]
    return "\n".join(lines)


def main(argv=None):
    # The text holds characters a cp932 console cannot encode, and the
    # failure would land as a UnicodeEncodeError from print().
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--client")
    parser.add_argument("--list", metavar="REGEX")
    parser.add_argument("--table", metavar="NAME")
    parser.add_argument("--text", metavar="REGEX")
    parser.add_argument("--ship", action="store_true")
    parser.add_argument("--rows", type=int)
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    install = game_client.find_install(args.client)
    if install is None:
        print("no game client found: name one with --client")
        return 1
    client = Client(install)
    archive = client.archive
    if args.list:
        pattern = re.compile(args.list, re.I)
        for name in sorted(archive.files):
            if pattern.search(name):
                print(name)
    elif args.table:
        columns, rows = client.table(args.table)
        lines = list(_tsv(columns, rows[:args.rows] if args.rows else rows))
        if args.out:
            Path(args.out).write_text("\n".join(lines) + "\n",
                                      encoding="utf-8")
            print(f"{len(rows)} rows to {args.out}")
        else:
            print("\n".join(lines))
    elif args.text:
        pattern = re.compile(args.text, re.I)
        for key, value in client.text().items():
            if pattern.search(key) or pattern.search(value):
                print(f"{key}\t{value}")
    elif args.ship:
        SHIPPED.write_text(shipped_source(client), encoding="utf-8",
                           newline="\n")
        print(f"build {archive.build} to {SHIPPED.relative_to(REPO)}")
    else:
        installed = sorted({archive.groups[g] for g, spans
                            in archive.streams.items()
                            if all(path for _s, _l, path in spans)})
        tables = sum(1 for n in archive.files if n.startswith("db/"))
        print(f"{install}: build {archive.build}, groups installed: "
              f"{', '.join(installed)}; {len(archive.files)} files, "
              f"{tables} tables, {len(client.text())} English texts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
