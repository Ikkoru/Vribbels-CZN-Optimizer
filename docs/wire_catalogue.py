"""What the wire has sent, and which of it nothing reads.

The capture keeps a catalogue as it runs: every `command|key` pair it
has seen, with a count, when it was first and last seen, the type and a
short sample. It lives in `Vribbels/settings/wire_catalogue.json` --
beside the settings rather than among the captures, since the snapshots
folder is the one that gets emptied.

**The point is the UNREAD half.** `entity` and `issued_limit_entities`
were both on the wire for months before anything looked at them, and no
amount of reading the addon would have said so -- a field nobody reads
leaves no trace in the code. This prints what the catalogue holds
against what the addon actually asks for, so the ones nothing touches
are named outright.

    python docs/wire_catalogue.py            # everything nothing reads
    python docs/wire_catalogue.py --all      # every pair, read or not
    python docs/wire_catalogue.py supply     # pairs matching a word
    python docs/wire_catalogue.py --file X   # a catalogue from elsewhere

**What the addon reads is derived from its source**, not listed here:
every `data.get("x")`, `carrier.get("x")` and `raw.get("x")` in
`capture/manager.py`. So the two halves cannot drift -- a key the addon
stops reading turns up in this report on the next run.

A key being unread is not a bug. Most of this wire is content the
program has no use for. It is a list of things nobody has LOOKED at,
which is a different and more useful thing than a list of bugs.
"""

import io
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "Vribbels"
CATALOGUE = SOURCE / "settings" / "wire_catalogue.json"
ADDON = SOURCE / "capture" / "manager.py"

# How the addon spells "read this key off a payload". Four shapes,
# because it uses all four:
#
#   data.get("x")            the common one
#   data["x"]                once the key is known to be there
#   "x" in data              the guard before that
#   ("x", "result_x", ...)   a tuple of spellings to try in turn
#
# The receiver names are listed for the first two rather than matching
# any `.get(` -- a plain dict lookup is spelled the same way, and most
# of those are not wire keys.
CARRIER = r"(?:data|carrier|raw|raw_data|payload|entry|held|doc|row)"
READS = [
    re.compile(r"\b" + CARRIER + r"\s*\.\s*get\(\s*[\"']([a-z_][a-z0-9_]*)[\"']"),
    re.compile(r"\b" + CARRIER + r"\s*\[\s*[\"']([a-z_][a-z0-9_]*)[\"']\s*\]"),
    re.compile(r"[\"']([a-z_][a-z0-9_]*)[\"']\s+in\s+" + CARRIER + r"\b"),
]

# The fourth shape: a tuple of spellings walked in turn, which is how
# the event records and the streaks are read. Taken as the whole
# bracket rather than line by line -- the tuple wraps, so its first
# entry shares a line with `for key in (` and its last with `):`.
#
# **Erring towards READ here would hide the thing this exists to
# find**, so the span is bounded tightly: only what is between that
# `for key in (` and its closing bracket.
TUPLES = re.compile(r"for key in \((.*?)\):", re.S)
QUOTED = re.compile(r"[\"']([a-z_][a-z0-9_]*)[\"']")


def keys_the_addon_reads():
    """Every wire key named in the capture source."""
    text = io.open(ADDON, encoding="utf-8").read()
    found = set()
    for pattern in READS:
        found |= {m.group(1) for m in pattern.finditer(text)}
    for span in TUPLES.finditer(text):
        found |= {m.group(1) for m in QUOTED.finditer(span.group(1))}
    return found


def main(argv):
    book = CATALOGUE
    argv = list(argv)
    if "--file" in argv:
        at = argv.index("--file")
        book = Path(argv[at + 1])
        del argv[at:at + 2]
    if not book.exists():
        print("No catalogue yet at %s." % book)
        print("It is written as a capture runs -- start one, play, stop.")
        return 1
    rows = json.loads(io.open(book, encoding="utf-8").read())["keys"]
    read = keys_the_addon_reads()

    show_all = "--all" in argv
    wanted = [a for a in argv[1:] if not a.startswith("--")]

    listed = []
    for name, row in sorted(rows.items()):
        command, _, key = name.partition("|")
        if wanted and not any(w.lower() in name.lower() for w in wanted):
            continue
        if not show_all and key in read:
            continue
        listed.append((name, key in read, row))

    if not listed:
        print("Nothing to show. %d pairs catalogued, %d keys read by the "
              "addon." % (len(rows), len(read)))
        return 0

    width = min(60, max(len(n) for n, _r, _row in listed))
    print("%-*s  %-4s %6s  %-19s  %s"
          % (width, "command|key", "read", "seen", "first seen", "sample"))
    for name, is_read, row in listed:
        print("%-*s  %-4s %6d  %-19s  %s"
              % (width, name[:width], "yes" if is_read else "-",
                 row.get("count", 0), str(row.get("first"))[:19],
                 str(row.get("sample"))[:60]))
    print()
    print("%d shown, of %d pairs catalogued. The addon reads %d keys."
          % (len(listed), len(rows), len(read)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
