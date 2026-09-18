"""How far each combatant is through the two Sortie ladders.

The game shows a combatant's Sortie progress as two figures -- `1/4`
for the achievements and `2/12` for the titles -- and this reads both
off a snapshot as one `3/16`.

**A rung is DONE when its `complete_time` is non-zero**, on both
ladders. The row EXISTING is not enough: an achievement row is issued
while the rung is still in progress, so most of them sit at
`complete_time` 0 and counting rows overstates a combatant by up to
three. Title rows only arrive once earned, so for them the two
readings agree -- which is why one rule serves both, and why it keeps
serving if titles ever start arriving early the way achievements do.

Neither of the other likely-looking fields is a flag. `score` is 1, 2
or 3 on achievement rows without tracking completion: one combatant's
done rung scores 3 and another's scores 1. `acquired_count` reaches 3
on title rows that still count once each.

**The totals are the game's, not the wire's.** Both ladders are sparse
-- nothing is sent for a rung not yet reached -- so no snapshot can say
how long a ladder is; the longest one an account has touched is a
floor. A combatant reaching a rung past the end is the one sign that
the game has changed shape, and `warn` is what makes that say so.
"""

import re
import sys

# The game's ladder lengths, the same for every combatant. NOT derived:
# the wire cannot state them, and a guess from what an account has
# earned is an undercount by construction.
ACHIEVEMENTS = 4
TITLES = 12
TOTAL = ACHIEVEMENTS + TITLES

ACHIEVEMENT_FIELD = "assault_char_achievement_entities"
TITLE_FIELD = "assault_char_title_entities"

_ACHIEVEMENT_ID = re.compile(r"^assault_char_achieve_(\d+)_(\d+)$")
_TITLE_ID = re.compile(r"^assault_char_title_(\d+)_(\d+)$")

# Dark yellow, and the reset after it. The launchers open a console, so
# a warning printed there is read; the same line on a released build
# goes to a stream nobody is watching, which is why this never replaces
# a reading on screen.
WARN = "\033[33m"
RESET = "\033[0m"


def _rows(raw, key):
    value = (raw or {}).get(key)
    if isinstance(value, dict):
        return list(value.values())
    return value if isinstance(value, list) else []


def progress(raw, warn=None):
    """{combatant res_id: (done, total)} across both ladders.

    A combatant with rows but nothing finished reads 0 rather than
    dropping out, because the game shows it that way too.

    `warn` is called with a complaint string for anything the ladders
    say that the game's shape does not allow -- a rung past the end,
    which is how a longer ladder would first show itself.
    """
    done = {}
    seen = {}
    for key, pattern, label in (
            (ACHIEVEMENT_FIELD, _ACHIEVEMENT_ID, "achievement"),
            (TITLE_FIELD, _TITLE_ID, "title")):
        for row in _rows(raw, key):
            if not isinstance(row, dict):
                continue
            found = pattern.match(str(row.get("res_id") or ""))
            if not found:
                continue
            char, rung = int(found.group(1)), int(found.group(2))
            seen.setdefault((char, label), set()).add(rung)
            done[char] = done.get(char, 0) + bool(row.get("complete_time"))
    if warn is not None:
        for (char, label), rungs in sorted(seen.items()):
            length = ACHIEVEMENTS if label == "achievement" else TITLES
            over = sorted(r for r in rungs if r > length)
            if over:
                warn("combatant %d has %s rung%s %s, past the %d this "
                     "build knows the %s ladder to hold. Its Sortie "
                     "column will read above %d until `sortie_progress`"
                     " is told the new length."
                     % (char, label, "" if len(over) == 1 else "s",
                        ", ".join(str(r) for r in over), length, label,
                        TOTAL))
    return {char: (count, TOTAL) for char, count in done.items()}


def to_console(message):
    """Put a warning where the launchers' console will show it.

    Dark yellow rather than red: the reading is still usable, it is
    just measured against a shape the game has moved on from.
    """
    try:
        sys.stderr.write("%s[!] Sortie: %s%s\n" % (WARN, message, RESET))
        sys.stderr.flush()
    except Exception:                                         # noqa: BLE001
        pass
