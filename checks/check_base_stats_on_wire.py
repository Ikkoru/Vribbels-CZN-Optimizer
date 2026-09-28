"""characters.py's base stats against what the server says.

`characters.py` is typed in from the game's screens, which show a base
with Affection mixed in -- and three entries have been wrong that way
at once. Every battle's entry sends the server's own base for each
combatant in it; the capture files those readings
(`Addon._note_base_stats`) and `base_stats_store.audit` sets them
against the data. What this holds:

1. **The capture files a battle once**: its readings, its stage and
   whether Zero System effects ride it; a battle seen again moves only
   its first and last sightings; a reply without the shape files
   nothing; and a file that will not read is not written over.
2. **The audit believes only plain battles**: none with Zero System
   effects (a Chaos adds +120 ATK, +60 DEF, +180 HP), and only one where
   a combatant matches characters.py exactly -- so a mode's bonus is
   never read as wrong data. It ignores readings below level 60, and
   reports what differs, what is missing, a level gain the program does
   not know, and a base that changed between readings.
3. **The maintainer's own readings, where there are any**: every
   combatant a plain battle has shown must match characters.py at its
   level, and every combatant the server sent must be in it. Fill the
   file with `python docs/base_stats_backfill.py --write`.
"""

import json
import shutil
import tempfile
from pathlib import Path

from ._harness import SOURCE_ROOT, add_source_to_path, note
from .check_capture_history import addon_tables

NAME = "base stats match what the server says"


def _addon(folder):
    from capture.manager import ADDON_TEMPLATE
    namespace = {}
    exec(compile(ADDON_TEMPLATE, "<ADDON_TEMPLATE>", "exec"), namespace)
    namespace.update(addon_tables())
    return namespace["Addon"](Path(folder), log_callback=lambda *a: None)


def _entry(rid, level, base, partner=(155, 5, 144)):
    return {"res_id": rid, "level": level, "status": {"info": {
        "BASE_S_ATK": base[0], "BASE_S_DEF": base[1], "BASE_S_HP": base[2],
        "S_PARTNER_BASE_ATK": partner[0], "S_PARTNER_BASE_DEF": partner[1],
        "S_PARTNER_BASE_HP": partner[2], "S_ATK": 1000}}}


def _reply(entries, stage=1010097, zero=False, when=1790000000):
    return {"res": "ok", "qid": 7, "service_server_time": when,
            "playing_stage_info": {"stage_id": stage,
                                   "ingame_content_config_id": "content_ego"},
            "zero_system_effs": ({"ZERO_CHARACTER_STAT__TYPE_VALUE": [{}]}
                                 if zero else {}),
            "stage_info": {"enter_chars": entries}}


def _the_capture_files_battles():
    import base_stats_store
    out = []
    folder = Path(tempfile.mkdtemp())
    try:
        addon = _addon(folder)
        entries = [_entry(1, 61, (500, 150, 300)), _entry(2, 60, (400, 180,
                                                                  320))]
        addon._note_base_stats("world/get_stage_info", _reply(entries))
        addon._note_base_stats("world/get_stage_info",
                               _reply(entries, when=1790000500))
        addon._note_base_stats("world/get_stage_info",
                               _reply(entries, when=1789999000))
        addon._note_base_stats("world/get_stage_info",
                               _reply(entries[:1], stage=80000, zero=True))
        addon._note_base_stats("world/get_stage_info",
                               {"res": "ok", "stage_info": {
                                   "enter_chars": [{"res_id": 3}]}})
        battles, note_ = base_stats_store.read(folder)
        if note_ or len(battles) != 2:
            out.append(f"four battle entries of two battles and one reply "
                       f"without readings filed {len(battles)} battles "
                       f"({note_}), not 2. See `_note_base_stats` in "
                       f"capture/manager.py.")
            return out
        first = next(b for b in battles if not b["zero_system"])
        if (first["first"], first["last"]) != (1789999000, 1790000500):
            out.append(f"a battle seen three times reads first "
                       f"{first['first']} and last {first['last']}, not "
                       f"the earliest and latest sighting.")
        if [r["base"] for r in first["chars"]] != [[500, 150, 300],
                                                   [400, 180, 320]] \
                or first["stage"] != 1010097:
            out.append(f"a battle is filed as {first}, not with its "
                       f"stage and each combatant's base.")
        if not any(b["zero_system"] for b in battles):
            out.append("a battle with Zero System effects is filed "
                       "without saying so.")
        path = base_stats_store.path_in(folder)
        path.write_text("{not json", encoding="utf-8")
        path.with_name(path.name + ".bak").write_text("{", encoding="utf-8")
        again = _addon(folder)
        again._note_base_stats("world/get_stage_info", _reply(entries))
        if path.read_text(encoding="utf-8") != "{not json":
            out.append("a readings file that will not read was written "
                       "over, and every battle before it lost.")
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return out


def _the_audit_believes_plain_battles():
    import base_stats_store
    from game_data import CHARACTERS
    from game_data.characters import get_character_stats_at_level
    out = []
    known = [(rid, c) for rid, c in CHARACTERS.items()
             if isinstance(c, dict)][:3]
    (a_id, a), (b_id, b), (c_id, c) = known

    def base(char, level, shift=0):
        s = get_character_stats_at_level(char, level)
        return [s["base_atk"] + shift, s["base_def"], s["base_hp"]]

    def battle(rows, zero=False, when=1790000000):
        return {"stage": 1, "zero_system": zero, "first": when,
                "last": when, "chars": [
                    {"res_id": rid, "level": lvl, "base": bs,
                     "partner": [0, 0, 0]} for rid, lvl, bs in rows]}

    battles = [
        # A plain battle: A matches, so B's gap is B's data.
        battle([(a_id, 60, base(a, 60)), (b_id, 60, base(b, 60, 7))]),
        # A Chaos: everyone +120, and nobody is to blame.
        battle([(c_id, 60, base(c, 60, 120))], zero=True),
        # A Zero System effect that left one combatant alone: the match
        # must not make the others' bonus read as wrong data.
        battle([(a_id, 60, base(a, 60)), (c_id, 60, base(c, 60, 120))],
               zero=True),
        # Nobody matches, no Zero System: a bonus, set aside.
        battle([(c_id, 60, base(c, 60, 50))]),
        # A trial copy at level 20 beside a match: not held to level 60.
        battle([(a_id, 60, base(a, 60)), (c_id, 20, [100, 50, 90])]),
        # A combatant the data does not have.
        battle([(a_id, 60, base(a, 60)), (999999, 60, [1, 2, 3])]),
    ]
    found = base_stats_store.audit(battles)
    names = [row[0] for row in found["differs"]]
    if names != [b["name"]]:
        out.append(f"the audit blames {names}, where only "
                   f"{b['name']}'s plain reading differs -- a Chaos, a "
                   f"battle nobody matches and a level-20 copy must not "
                   f"count. See `base_stats_store.audit`.")
    if [row[0] for row in found["missing"]] != [999999]:
        out.append(f"a combatant the data lacks is reported as "
                   f"{found['missing']}.")
    if c["name"] not in found["unseen"]:
        out.append("a combatant seen only in a Chaos, a bonus battle and "
                   "a trial counts as seen in a plain one.")
    # The same combatant read two ways over time: the newest wins, and
    # the change is reported.
    moved = base_stats_store.audit([
        battle([(a_id, 60, base(a, 60)), (b_id, 60, base(b, 60, 9))],
               when=1780000000),
        battle([(a_id, 60, base(a, 60)), (b_id, 60, base(b, 60))],
               when=1790000000)])
    if moved["differs"] or [row[0] for row in moved["changed"]] != \
            [b["name"]]:
        out.append(f"a base that changed between readings reads as "
                   f"differs {moved['differs']}, changed "
                   f"{moved['changed']}: the newest reading must win and "
                   f"the change be reported.")
    return out


def _the_maintainers_readings():
    import base_stats_store
    snapshots = SOURCE_ROOT / "snapshots"
    battles, note_ = base_stats_store.read(snapshots)
    if not battles:
        note("no base stat readings on file -- `python "
             "docs/base_stats_backfill.py --write` files the debug logs'")
        return []
    out = []
    if note_:
        out.append(f"the base stat readings {note_}.")
    found = base_stats_store.audit(battles)
    for name, level, wire, program, _last in found["differs"]:
        out.append(f"{name} at level {level}: the server says {wire}, "
                   f"characters.py {program}. Fix characters.py (the base "
                   f"is at level 60), or its level gain.")
    for rid, level, wire, _last in found["missing"]:
        out.append(f"the server sent res_id {rid} at level {level} with "
                   f"base {wire}, and characters.py has no such combatant.")
    for name, cls, grade, level, gain in found["gains"]:
        out.append(f"{name} ({cls} grade {grade}) at level {level} gains "
                   f"{gain} over level 60 by the server, a gain the "
                   f"program does not know: fill LEVEL_BONUS_BY_CLASS.")
    if found["unseen"]:
        note(f"{len(found['unseen'])} combatants not yet in a plain "
             f"battle")
    return out


def run():
    add_source_to_path()
    return (_the_capture_files_battles() + _the_audit_believes_plain_battles()
            + _the_maintainers_readings())
