"""The combatants' base stats as the server states them, in a file of
their own: `snapshots/base_stats/readings.json`.

Every battle's entry (`world/get_stage_info`) sends each combatant in
it with a `status.info` block: `BASE_S_ATK`, `BASE_S_DEF`, `BASE_S_HP`
-- the base at the combatant's level -- and `S_PARTNER_BASE_*`, their
partner's flat stats. The capture files each battle's readings here
(`Addon._note_base_stats`); `audit` sets them against `characters.py`,
which is otherwise typed in by hand from the game's screens.

**A mode can add to the base.** A Chaos stage adds its Zero System
nodes -- `zero_system_effs`, +120 ATK, +60 DEF and +180 HP for most
combatants -- and other modes may add their own. So a battle is PLAIN,
and its readings believed, only when it carries no Zero System effects
AND at least one of its combatants matches characters.py exactly: the
game added nothing there, so a combatant who differs in the same battle
has wrong data. A battle where nobody matches is set aside -- a bonus,
or every combatant in it wrong, which some plain battle would show.

**Only readings at level 60 or above count.** characters.py holds level
60 and the program treats a lower level as 60, while the server's base
below 60 is genuinely lower -- and combatant trials and event stories
field level-20 or 25 copies.

**The newest plain reading wins.** A patch can change a base stat, so
an older plain reading unlike the newest is reported as a change, and
characters.py is held to the newest.

Kept apart like the Chaos runs (`chaos_store.py`): a subfolder, ONE
writer, and a write that goes through a read-back copy keeping the
previous file as `<name>.bak`. No Tk: `checks/check_base_stats_on_wire`
and `docs/base_stats_backfill.py` read through this.
"""

import json
from pathlib import Path

FOLDER = "base_stats"
FILE = "readings.json"
KIND = "vribbels base stat readings"
BACKUP = ".bak"


def path_in(snapshots):
    """Where the readings' file sits under a snapshots folder."""
    return Path(snapshots) / FOLDER / FILE


def read(snapshots):
    """(battles, note): every battle filed, and a note where the file
    had to be read from its backup or could not be read at all; [] and
    None where there is no file yet."""
    path = path_in(snapshots)
    tried = []
    for candidate in (path, path.with_name(path.name + BACKUP)):
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            tried.append("%s: %s" % (candidate.name, e))
            continue
        battles = data.get("battles") if isinstance(data, dict) else None
        if not isinstance(battles, list):
            tried.append("%s: not a base stat readings file" % candidate.name)
            continue
        note = None
        if candidate != path:
            note = "read from the backup (%s)" % "; ".join(tried or [
                "%s missing" % path.name])
        return [b for b in battles if isinstance(b, dict)], note
    if tried:
        return [], "could not be read: " + "; ".join(tried)
    return [], None


def _base_at(char, level):
    from game_data.characters import get_character_stats_at_level
    b = get_character_stats_at_level(char, level or 60)
    return [b["base_atk"], b["base_def"], b["base_hp"]]


def _comparable(row):
    """A reading characters.py can be held to: one at level 60 or above.

    Below 60 the server's base is genuinely lower, while characters.py
    keeps level 60 and the program treats a lower level as 60 -- and a
    combatant trial or an event story fields its combatants at 20 or 25.
    """
    return isinstance(row, dict) and isinstance(row.get("level"), int) \
        and row["level"] >= 60


def plain_battles(battles):
    """The battles whose readings are believed: no Zero System effects,
    and at least one combatant exactly as characters.py has them."""
    from game_data.characters import CHARACTERS
    out = []
    for battle in battles:
        if battle.get("zero_system"):
            continue
        for r in battle.get("chars") or []:
            if not _comparable(r):
                continue
            char = CHARACTERS.get(r.get("res_id"))
            if isinstance(char, dict) and list(r.get("base") or []) == \
                    _base_at(char, r.get("level")):
                out.append(battle)
                break
    return out


def audit(battles):
    """Set the readings against characters.py.

    Returns a dict of lists:

    - `differs`: (name, level, wire, program, last seen) for each
      combatant whose newest plain reading is not what characters.py
      gives at that level;
    - `missing`: (res_id, level, wire, last seen) for a combatant the
      server sent that characters.py does not have;
    - `changed`: (name, level, older, newer, older's last, newer's
      first) where plain readings of one level disagree over time;
    - `gains`: (name, class, grade, level, wire - level-60 base) for a
      plain reading above 60 that characters.py cannot reproduce
      because a gain up to that level is unknown -- it says what the
      gain is, where `differs` would blame the base;
    - `unseen`: names in characters.py no plain battle has shown.
    """
    from game_data.characters import CHARACTERS, level_bonus
    out = {"differs": [], "missing": [], "changed": [], "gains": [],
           "unseen": []}

    # Every plain reading per (combatant, level), oldest first.
    history = {}
    for battle in sorted(plain_battles(battles),
                         key=lambda b: b.get("last") or 0):
        for r in battle.get("chars") or []:
            if not _comparable(r):
                continue
            key = (r.get("res_id"), r.get("level"))
            history.setdefault(key, []).append(
                (list(r.get("base") or []), battle.get("first"),
                 battle.get("last")))
    seen = set()
    for (rid, level), rows in sorted(history.items(), key=str):
        newest, _first, last = rows[-1]
        for older, old_first, old_last in rows[:-1]:
            if older != newest:
                name = (CHARACTERS.get(rid) or {}).get("name", rid) \
                    if isinstance(CHARACTERS.get(rid), dict) else rid
                out["changed"].append((name, level, older, newest,
                                       old_last, rows[-1][1]))
        char = CHARACTERS.get(rid)
        if not isinstance(char, dict):
            out["missing"].append((rid, level, newest, last))
            continue
        seen.add(rid)
        program = _base_at(char, level)
        unknown_gain = level and level > 60 and any(
            level_bonus(char, step) is None for step in range(61, level + 1))
        if unknown_gain and newest != program:
            base60 = _base_at(char, 60)
            out["gains"].append((char["name"], char.get("class"),
                                 char.get("grade"), level,
                                 [w - b for w, b in zip(newest, base60)]))
            continue
        if newest != program:
            out["differs"].append((char["name"], level, newest, program,
                                   last))
    out["unseen"] = sorted(c["name"] for rid, c in CHARACTERS.items()
                           if isinstance(c, dict) and rid not in seen)
    return out
