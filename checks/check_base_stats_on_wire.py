"""The program's stat tables and stat formula against what the server
says.

`characters.py` and `partners.py` are typed in from the game's screens,
which show a base with Affection mixed in, so an entry typed from them
is wrong by the Affection bonus -- and a patch can move either without a
word. Every battle's entry sends the server's own sheet for each
combatant in it; the capture files it (`Addon._note_base_stats`) and
`base_stats_store` works out and audits what it says. What this holds:

1. **The capture files a battle once**: its readings, stage, stat
   effects, inner values and partners; a battle seen again moves only
   its first and last sightings; each build is filed once beside it; a
   reply without the shape files nothing; a file from before builds
   were kept still reads; and a file that will not read is not written
   over.
2. **The readings resolve as the server means them**: a plain battle's
   bases are the combatants' own; a Chaos battle's bonus comes off
   everyone once one combatant's base is known -- read plainly, or
   solved from the inner value -- and a battle whose combatants
   disagree on it gives nothing; a Sortie's multiplied HP never passes
   for a bonus; level-20 copies do not count; the newest plain reading
   wins, and a change between readings is reported.
3. **The program answers with the server's figure where one is known**
   (`game_data.learned`): a reading at the level asked, a gain read off
   two readings or agreed by a class, a partner's curve. The audit
   still reads the tables, which an installed overlay must not blind,
   and `run_all` clears the overlay after every check.
4. **The stat formula is the server's** (`formula_gaps`): a sheet the
   program's formula reproduces passes, and one it does not is caught.
5. **The maintainer's own readings, where there are any**: every
   combatant must match characters.py at its level, every partner's
   level-60 flats partners.py, and the formula every plain build.
   Fill the file with `python docs/base_stats_backfill.py --write`.
"""

import io
import json
import shutil
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from ._harness import SOURCE_ROOT, add_source_to_path, note
from .check_capture_history import addon_tables

NAME = "stat tables and formula match what the server says"

# Readings of the maintainer's that differ from characters.py for a
# reason nobody has pinned down, as (name, level): the reading. Noted
# rather than failed while the reading stays exactly this; a different
# reading, or none, fails, so the entry cannot outlive the question.
UNEXPLAINED = {
    # DEF 8% over her base, and her partner's flat DEF 8% over the
    # partner's own (43 against 40) -- her sheet, not the Sortie's, since
    # the Potential 7 value says the same. Her limit break or a trait
    # of hers; one plain battle at limit break 0 would say which.
    ("Magna", 60): [None, 197, None],
}

CHAOS = [["ZERO_CHARACTER_STAT__TYPE_VALUE", "n", [40]]]
SORTIE = [["ZERO_TACTICS_MAX_HP_UP_RATE__VALUE", "m", [20]]]


def _addon(folder):
    from capture.manager import ADDON_TEMPLATE
    namespace = {}
    exec(compile(ADDON_TEMPLATE, "<ADDON_TEMPLATE>", "exec"), namespace)
    namespace.update(addon_tables())
    return namespace["Addon"](Path(folder), log_callback=lambda *a: None)


def _entry(rid, level, base, partner=(155, 5, 144), inner=None):
    return {"res_id": rid, "level": level, "limit_break": 0,
            "potential_base_status": inner or {"S_ATK": 1000},
            "equipped_pieces": {"ITEM_PIECE_1": {
                "id": 7, "res_id": 1111011, "level": 5, "lock": False,
                "stat_list": [{"slot": 0, "stat": "S_ATK_INC_ADD_OUT",
                               "type": 0, "value": 50}]}},
            "status": {"info": {
                "BASE_S_ATK": base[0], "BASE_S_DEF": base[1],
                "BASE_S_HP": base[2], "S_PARTNER_BASE_ATK": partner[0],
                "S_PARTNER_BASE_DEF": partner[1],
                "S_PARTNER_BASE_HP": partner[2], "S_ATK": 1000,
                "S_ATK_INC_RATE_OUT": 12.5, "S_ATK_INC_ADD_OUT": 60,
                "S_CRI": 30.0}}}


def _reply(entries, stage=1010097, zero=False, when=1790000000):
    effects = {}
    if zero:
        effects = {
            "ZERO_CHARACTER_STAT__TYPE_VALUE": [{
                "zero_system_eff_id": "zero_orb_x", "opt_values": {
                    "opt_1": -1, "opt_2": 40, "opt_3": -1}}],
            "ZERO_SHOP_FREEREROLL__VALUE": [{
                "zero_system_eff_id": "zero_orb_y",
                "opt_values": {"opt_1": 2}}]}
    return {"res": "ok", "qid": 7, "service_server_time": when,
            "playing_stage_info": {"stage_id": stage,
                                   "ingame_content_config_id": "content_ego"},
            "zero_system_effs": effects,
            "stage_info": {"enter_chars": entries, "enter_supporters": [
                {"res_id": 30094, "level": 60, "limit_break": 0,
                 "status": {"info": {"S_ATK_INC_ADD_OUT": 155,
                                     "S_DEF_INC_ADD_OUT": 5,
                                     "S_HP_INC_ADD_OUT": 144}}}, None]}}


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
        battles, builds, note_ = base_stats_store.read_store(folder)
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
        rows = {r["res_id"]: r for r in first["chars"]}
        if [rows[1]["base"], rows[2]["base"]] != [[500, 150, 300],
                                                  [400, 180, 320]] \
                or first["stage"] != 1010097:
            out.append(f"a battle is filed as {first}, not with its "
                       f"stage and each combatant's base.")
        if rows[1].get("inner") != {"S_ATK": 1000} or rows[1].get(
                "layers") != {"S_ATK_INC_RATE_OUT": 12.5,
                              "S_ATK_INC_ADD_OUT": 60}:
            out.append(f"a combatant is filed with inner "
                       f"{rows[1].get('inner')} and layers "
                       f"{rows[1].get('layers')}: its Potential 7 value "
                       f"and inner layer are what solve a base.")
        if (rows[1].get("partner_id"), rows[1].get("partner_flat")) != \
                (30094, [155, 5, 144]) or "partner_id" in rows[2]:
            out.append("the partner beside a combatant is not filed from "
                       "`enter_supporters`' same place, with its own flat "
                       "stats.")
        chaos = next(b for b in battles if b["zero_system"])
        if chaos.get("effects") != [["ZERO_CHARACTER_STAT__TYPE_VALUE",
                                     "zero_orb_x", [40]]]:
            out.append(f"a Chaos battle's effects are filed as "
                       f"{chaos.get('effects')}: the stat nodes with their "
                       f"values, and no effect outside BASE_EFFECT_GROUPS.")
        if len(builds) != 3 or not all(b.get("pieces") for b in builds):
            out.append(f"{len(builds)} builds are filed where two "
                       f"combatants, seen plain and in a Chaos, make 3, "
                       f"each with its fragments.")
        path = base_stats_store.path_in(folder)
        path.write_text(json.dumps({"kind": base_stats_store.KIND,
                                    "version": 1, "battles": battles}),
                        encoding="utf-8")
        old, kept, _n = base_stats_store.read_store(folder)
        if len(old) != 2 or kept:
            out.append("a readings file from before builds were kept does "
                       "not read as its battles and no builds.")
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


def _cast():
    """Seven combatants of characters.py and their level-60 bases."""
    from game_data import CHARACTERS
    from game_data.characters import table_stats_at_level
    cast = []
    for rid, char in CHARACTERS.items():
        if isinstance(char, dict) and len(cast) < 7:
            b = table_stats_at_level(char, 60)
            cast.append((rid, char["name"],
                         [b["base_atk"], b["base_def"], b["base_hp"]]))
    return cast


def _row(rid, level, base, partner=(0, 0, 0), inner=None, layers=None):
    return {"res_id": rid, "level": level, "base": list(base),
            "partner": list(partner), "inner": inner or {},
            "layers": layers or {}}


def _battle(rows, effects=None, when=1790000000, stage=1):
    return {"stage": stage, "content": "x", "zero_system": effects is not None,
            "effects": effects or [], "first": when, "last": when,
            "chars": rows}


def _plus(base, add):
    return [b + a for b, a in zip(base, add)]


def _the_readings_resolve():
    import base_stats_store as bs
    out = []
    if bs.solve_base(1127, 155, 53.1, 87) != 524 or \
            bs.solve_base(100, 0, 0, 0) != 100:
        out.append("solve_base does not invert the inner formula: "
                   "round((524 + 155) * 1.531 + 87) is 1127.")
    (a_id, a, a60), (b_id, b, b60), (c_id, c, c60), (d_id, d, d60), \
        (e_id, e, e60), (f_id, f, f60), (g_id, g, g60) = _cast()
    bonus = [120, 60, 180]
    g_true = _plus(g60, [9, 0, 0])
    g_inner = bs._half_up((g_true[0] + 155) * 1.2 + 30)
    battles = [
        # A plain battle: A matches, B's base is 7 over.
        _battle([_row(a_id, 60, a60), _row(b_id, 60, _plus(b60, [7, 0, 0])),
                 _row(999999, 60, [1, 2, 3])]),
        # A Chaos: A, known plainly, says the bonus; C is 5 ATK over.
        _battle([_row(a_id, 60, _plus(a60, bonus)),
                 _row(c_id, 60, _plus(_plus(c60, bonus), [5, 0, 0]))],
                effects=CHAOS, stage=2),
        # A Chaos whose combatants disagree: nothing for D.
        _battle([_row(a_id, 60, _plus(a60, bonus)),
                 _row(b_id, 60, _plus(b60, [107, 60, 180])),
                 _row(d_id, 60, _plus(d60, bonus))], effects=CHAOS, stage=3),
        # A Sortie: A's HP multiplied; no bonus for E.
        _battle([_row(a_id, 60, [a60[0], a60[1], int(a60[2] * 1.8)]),
                 _row(e_id, 60, [e60[0], e60[1], int(e60[2] * 1.8)])],
                effects=SORTIE, stage=4),
        # A level-20 copy of F beside a known combatant.
        _battle([_row(a_id, 60, a60), _row(f_id, 20, [100, 50, 90])]),
        # G alone in a Chaos: solved from the inner value, ATK only.
        _battle([_row(g_id, 60, _plus(g_true, bonus), partner=(155, 5, 144),
                      inner={"S_ATK": g_inner},
                      layers={"S_ATK_INC_RATE_OUT": 20,
                              "S_ATK_INC_ADD_OUT": 30})],
                effects=CHAOS, stage=5),
    ]
    found = bs.audit(battles)
    differs = {row[0]: (row[2], row[5]) for row in found["differs"]}
    want = {b: (_plus(b60, [7, 0, 0]), "plain"),
            c: (_plus(c60, [5, 0, 0]), "derived"),
            g: ([g_true[0], None, None], "derived")}
    if differs != want:
        out.append(f"the audit reads {differs}, where B is 7 over in a "
                   f"plain battle, C 5 over once A's plain base takes the "
                   f"Chaos bonus off, and G's ATK 9 over as its inner "
                   f"value solves it -- and a battle that disagrees, a "
                   f"Sortie and a level-20 copy give nothing. See "
                   f"`base_stats_store.resolve`.")
    if [row[0] for row in found["missing"]] != [999999]:
        out.append(f"a combatant the data lacks is reported as "
                   f"{found['missing']}.")
    if not any(row[0] == 3 for row in found["conflicts"]):
        out.append("a Chaos battle whose combatants say different "
                   "bonuses is not reported as set aside.")
    for name in (d, e, f):
        if name not in found["unseen"]:
            out.append(f"{name} -- only in a battle that disagrees, a "
                       f"Sortie or at level 20 -- counts as settled.")
    moved = bs.audit([
        _battle([_row(a_id, 60, a60), _row(b_id, 60, _plus(b60, [9, 0, 0]))],
                when=1780000000),
        _battle([_row(a_id, 60, a60), _row(b_id, 60, b60)])])
    if moved["differs"] or [row[0] for row in moved["changed"]] != [b]:
        out.append(f"a base that changed between readings reads as "
                   f"differs {moved['differs']}, changed "
                   f"{moved['changed']}: the newest reading must win and "
                   f"the change be reported.")
    return out


def _the_overlay_answers():
    import base_stats_store as bs
    from game_data import CHARACTERS, PARTNERS, learned
    from game_data.characters import (LEVEL_BONUS_BY_CLASS,
                                      get_character_stats_at_level,
                                      table_stats_at_level)
    from game_data.partners import get_partner_stats, table_partner_stats
    out = []

    def triple(stats):
        return [stats["base_atk"], stats["base_def"], stats["base_hp"]]

    def pick(want):
        return next((rid, c) for rid, c in CHARACTERS.items()
                    if isinstance(c, dict) and want(c))

    silent = [(rid, c) for rid, c in CHARACTERS.items()
              if isinstance(c, dict) and c.get("level_61_bonus") is None
              and (LEVEL_BONUS_BY_CLASS.get((c["class"], c["grade"]))
                   or {}).get(61) is None]
    pairs = {}
    for rid, c in silent:
        pairs.setdefault((c["class"], c["grade"]), []).append((rid, c))
    (x_id, x), (y_id, y) = next(v for v in pairs.values() if len(v) >= 2)[:2]
    z_id, z = pick(lambda c: c.get("level_61_bonus") is None and (
        LEVEL_BONUS_BY_CLASS.get((c["class"], c["grade"])) or {}).get(61)
        and c is not x and c is not y)
    zgain = LEVEL_BONUS_BY_CLASS[(z["class"], z["grade"])][61]
    x60, y60 = triple(table_stats_at_level(x, 60)), \
        triple(table_stats_at_level(y, 60))
    x60r, x61r = _plus(x60, [3, 0, 0]), _plus(x60, [13, 4, 11])
    z61r = [500, 200, 400]
    kin = {}
    for p, v in PARTNERS.items():
        if isinstance(v, dict):
            kin.setdefault((v["grade"], v["class"]), []).append(p)
    pid, sib = next(ids for ids in kin.values() if len(ids) >= 2)[:2]
    try:
        learned.install({x_id: {60: x60r, 61: x61r}, z_id: {"61": z61r}},
                        {pid: {50: [1, 2, 3]}})
        got = {
            "x at 60": triple(get_character_stats_at_level(x, 60)),
            "x at 61": triple(get_character_stats_at_level(x, 61)),
            "x at 62": triple(get_character_stats_at_level(x, 62)),
            "y at 61": triple(get_character_stats_at_level(y, 61)),
            "y's table at 61": triple(table_stats_at_level(y, 61)),
            "z at 60": triple(get_character_stats_at_level(z, 60)),
        }
        want = {
            "x at 60": x60r, "x at 61": x61r, "x at 62": x61r,
            "y at 61": _plus(y60, [10, 4, 11]), "y's table at 61": y60,
            "z at 60": [z61r[0] - zgain["atk"], z61r[1] - zgain["def"],
                        z61r[2] - zgain["hp"]],
        }
        if got != want:
            out.append(f"with readings installed the program reads {got}, "
                       f"not {want}: a reading at the level asked, a gain "
                       f"read off two readings or agreed by the class, a "
                       f"known gain walked down to 60 -- and the table "
                       f"untouched. See `get_character_stats_at_level`.")
        flats = [get_partner_stats(p, level) for p, level in
                 ((pid, 50), (sib, 50), (pid, 49))]
        if [list(f.values()) for f in flats[:2]] != [[1, 2, 3]] * 2 or \
                flats[2] != table_partner_stats(pid, 49) or \
                table_partner_stats(pid, 50) == {"atk": 1, "def": 2,
                                                 "hp": 3}:
            out.append(f"with a partner's reading installed, it, a partner "
                       f"of the same grade and class at that level, and "
                       f"another level read {flats}: the reading twice, "
                       f"then the table -- which stays the table.")
        # The audit must still read the tables: installed, the server's
        # figure would come back as the program's and B's gap vanish.
        (a_id, _a, a60), (b_id, b, b60) = _cast()[:2]
        learned.install({b_id: {60: _plus(b60, [7, 0, 0])}}, {})
        seen = bs.audit([_battle([_row(a_id, 60, a60),
                                  _row(b_id, 60, _plus(b60, [7, 0, 0]))])])
        if [row[0] for row in seen["differs"]] != [b]:
            out.append("with the server's reading installed the audit no "
                       "longer sees characters.py differ: it must read "
                       "the tables, not `get_character_stats_at_level`.")
    finally:
        learned.clear()
    return out + _run_all_clears_the_overlay()


def _run_all_clears_the_overlay():
    from checks import run_all
    from game_data import CHARACTERS, learned
    rid = next(r for r, c in CHARACTERS.items() if isinstance(c, dict))
    seen = []

    def installs():
        learned.install({rid: {60: [1, 2, 3]}}, {})
        return []

    def looks():
        seen.append(dict(learned.BASES))
        return []

    saved = run_all.CHECKS
    run_all.CHECKS = [SimpleNamespace(NAME="installs", run=installs),
                      SimpleNamespace(NAME="looks", run=looks)]
    try:
        with redirect_stdout(io.StringIO()):
            run_all.main([])
    finally:
        run_all.CHECKS = saved
        learned.clear()
    if seen != [{}]:
        return [f"a check after one that installed readings saw "
                f"{seen}: run_all.main must clear `game_data.learned` "
                f"after every check."]
    return []


def _the_formula_holds():
    import base_stats_store as bs
    from game_data import CHARACTERS, FRIENDSHIP_BONUSES
    rid, char = next((r, c) for r, c in CHARACTERS.items()
                     if isinstance(c, dict))
    _lvl, atk, def_, hp = FRIENDSHIP_BONUSES[-1]
    base = [500, 150, 400]
    status = {"BASE_S_ATK": base[0], "BASE_S_DEF": base[1],
              "BASE_S_HP": base[2], "S_ATK_INC_ADD_OUT": atk,
              "S_DEF_INC_ADD_OUT": def_, "S_HP_INC_ADD_OUT": hp,
              "S_ATK": base[0] + atk, "S_DEF": base[1] + def_,
              "S_HP": base[2] + hp,
              "S_CRI": char.get("base_crit_rate", 0),
              "S_CRI_DMG_RATE": char.get("base_crit_dmg", 125.0),
              "S_ADDI_ATK_DMG_RATE": 0, "S_DOT_ATK_DMG_RATE": 0}
    build = {"res_id": rid, "level": 60, "nodes": [], "pieces": [],
             "inner": {"S_ATK": base[0] + atk}, "status": status,
             "zero_system": False}
    out = []
    gaps = bs.formula_gaps([build], {})
    if gaps:
        out.append(f"a sheet the formula reproduces reads as {gaps}.")

    def broken(**change):
        return dict(build, status=dict(status, **change))
    faults = {"CRate": broken(S_CRI=status["S_CRI"] + 1),
              "outer ATK%": broken(S_ATK_INC_RATE_IN=5),
              "final ATK": broken(S_ATK=status["S_ATK"] + 3),
              "flat: no Affection row fits": broken(
                  S_ATK_INC_ADD_OUT=atk + 1)}
    for what, fault in faults.items():
        if not any(g[1] == what for g in bs.formula_gaps([fault], {})):
            out.append(f"a sheet whose {what} the formula cannot give "
                       f"passes. See `base_stats_store.formula_gaps`.")
    if bs.formula_gaps([faults["CRate"]], {rid: {"CRate": 1}}):
        out.append("a CRate gap of exactly an allowed bonus still fails.")
    return out


def _the_maintainers_readings():
    import base_stats_store
    snapshots = SOURCE_ROOT / "snapshots"
    battles, builds, note_ = base_stats_store.read_store(snapshots)
    if not battles:
        note("no base stat readings on file -- `python "
             "docs/base_stats_backfill.py --write` files the debug logs'")
        return []
    out = []
    if note_:
        out.append(f"the base stat readings {note_}.")
    found = base_stats_store.audit(battles)
    odd = dict(UNEXPLAINED)
    for name, level, wire, program, _last, how in found["differs"]:
        if odd.get((name, level)) == wire:
            odd.pop((name, level))
            note(f"{name} at level {level}: the server says {wire}, "
                 f"characters.py {program} -- unexplained, see UNEXPLAINED")
            continue
        out.append(f"{name} at level {level}: the server says {wire} "
                   f"({how}), characters.py {program}. Fix characters.py "
                   f"(the base is at level 60), or its level gain.")
    for (name, level), wire in odd.items():
        out.append(f"UNEXPLAINED holds {name} at level {level} as {wire}, "
                   f"and the readings no longer say so: settle it, and "
                   f"drop the entry.")
    for rid, level, wire, _last in found["missing"]:
        out.append(f"the server sent res_id {rid} at level {level} with "
                   f"base {wire}, and characters.py has no such combatant.")
    for name, cls, grade, level, gain in found["gains"]:
        out.append(f"{name} ({cls} grade {grade}) at level {level} gains "
                   f"{gain} over level 60 by the server, a gain the tables "
                   f"do not know: fill LEVEL_BONUS_BY_CLASS.")
    for stage, content, stat, bonuses, _last in found["conflicts"]:
        out.append(f"stage {stage} ({content}) gives its combatants "
                   f"{stat} bonuses of {bonuses}: a Chaos bonus is the "
                   f"same for everyone, so either a combatant's base is "
                   f"known wrongly or the mode is not what ADDITIVE says.")
    below = []
    for name, level, wire, program, _last in found["partners"]:
        if level >= 60:
            out.append(f"partner {name} at level {level} has flat stats "
                       f"{wire} by the server, {program} by "
                       f"PARTNER_CLASS_STATS.")
        else:
            below.append(f"{name} {level}")
    if below:
        note(f"partner flats below 60 unlike the linear table, which the "
             f"program replaces with the server's: {', '.join(below)}")
    gaps = base_stats_store.formula_gaps(builds)
    for rid, what, server, program in gaps:
        out.append(f"res_id {rid}'s sheet says {what} {server}, the "
                   f"program's formula {program}. docs/game_formulas.md "
                   f"section 1 first, then optimizer/core.py.")
    if not any(not b.get("zero_system") for b in builds):
        note("no build from a plain battle on file for the formula")
    if found["unseen"]:
        note(f"{len(found['unseen'])} combatants not yet settled by any "
             f"battle")
    return out


def run():
    add_source_to_path()
    return (_the_capture_files_battles() + _the_readings_resolve()
            + _the_overlay_answers() + _the_formula_holds()
            + _the_maintainers_readings())
