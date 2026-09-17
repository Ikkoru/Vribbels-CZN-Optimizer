"""How far each combatant is through the two Sortie ladders.

The game shows a combatant's Sortie progress as two figures -- `1/4`
for the achievements and `2/12` for the titles -- and this reads both
off a snapshot as one `3/16`.

**A rung is DONE when its row exists.** Both ladders are sparse: the
wire sends nothing for a rung that has not been reached, so what a
snapshot holds is exactly the count completed. No field says so --
`score` is 1, 2 or 3 depending on the combatant and carries no
completion of its own, and `complete_time` is 0 on rungs whose reward
HAS been collected, so neither can be read as a flag. The presence of
the row is the whole of it.

**The totals are the game's, not the wire's.** Because an unearned rung
sends nothing, no snapshot can say how long a ladder is. A combatant
reaching a rung past the end is the one sign that the game has changed
its shape, and `warn` is what makes that say so.
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

    `warn` is called with a complaint string for anything the ladders
    say that the game's shape does not allow -- a rung past the end,
    which is how a longer ladder would first show itself.
    """
    done = {}
    seen = {}
    for key, pattern, length, label in (
            (ACHIEVEMENT_FIELD, _ACHIEVEMENT_ID, ACHIEVEMENTS, "achievement"),
            (TITLE_FIELD, _TITLE_ID, TITLES, "title")):
        for row in _rows(raw, key):
            if not isinstance(row, dict):
                continue
            found = pattern.match(str(row.get("res_id") or ""))
            if not found:
                continue
            char, rung = int(found.group(1)), int(found.group(2))
            seen.setdefault((char, label), set()).add(rung)
            done[char] = done.get(char, 0) + 1
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
