"""A combatant's Affinity is the level its exp reaches, not the rewards
claimed.

The capture sends `friendship_exp` and `friendship_reward_index`, and
the second counts the Affinity rewards CLAIMED: a combatant levelled and
not yet claimed reads below its level, and its stats -- which follow the
level -- read low with nothing to say so. `constants.AFFINITY_TO_NEXT`
turns the exp into the level.

Held three ways: the maintainer's readings off the game; every battle
sheet on file, whose flat layer names the Affinity row the server
applied; and the program's own reading of the newest snapshot.
"""

from datetime import datetime

from ._harness import SOURCE_ROOT, add_source_to_path, newest_snapshot, note

NAME = "Affinity is the level, not the rewards claimed"

# (exp, level), read in game by the maintainer.
READ = ((10340, 33), (10430, 34))


def _snapshots():
    """[(capture time as epoch, {res_id: (exp, claimed)})], oldest
    first, over the loose snapshots."""
    import json
    out = []
    for path in sorted((SOURCE_ROOT / "snapshots").glob(
            "memory_fragments_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            when = datetime.fromisoformat(data["capture_time"]).timestamp()
        except (OSError, ValueError, KeyError, TypeError):
            continue
        out.append((when, {
            c["res_id"]: (c.get("friendship_exp") or 0,
                          c.get("friendship_reward_index") or 0)
            for c in (data.get("characters") or {}).get("characters") or []
            if "friendship_exp" in c}))
    return sorted(out, key=lambda pair: pair[0])


def _sheets_follow_the_level(snaps):
    """Each battle sheet's Affinity row lies between the levels the
    snapshots either side of the battle give, wherever those say more
    than the rewards claimed did. Returns (complaints, sheets read)."""
    import base_stats_store as bs
    from game_data import CHARACTERS, FRIENDSHIP_BONUSES
    from game_data.constants import affinity_level
    from models.memory_fragment import MemoryFragment
    rows = {lvl: (a, d, h) for lvl, a, d, h in FRIENDSHIP_BONUSES}
    _battles, builds, _note = bs.read_store(SOURCE_ROOT / "snapshots")
    out, read = [], 0
    for build in builds:
        rid, st = build.get("res_id"), build.get("status") or {}
        when = build.get("first")
        if build.get("zero_system") or "BASE_S_ATK" not in st \
                or not isinstance(CHARACTERS.get(rid), dict) or not when:
            continue
        before = [s for t, s in snaps if t <= when and rid in s]
        after = [s for t, s in snaps if t > when and rid in s]
        if not before or not after:
            continue
        exp_b, claimed = before[-1][rid]
        low, high = affinity_level(exp_b), affinity_level(after[0][rid][0])
        if low <= claimed or low < 20:
            continue
        gear = [MemoryFragment.from_json(p)
                for p in build.get("pieces") or () if isinstance(p, dict)]
        flats = {s: sum(p.get_total_stats().get("Flat " + s, 0)
                        for p in gear) for s in bs.STATS}
        fits = [lvl for lvl, row in rows.items() if all(
            bs._half_up(flats[s] + row[i]) == st.get("S_%s_INC_ADD_OUT" % s, 0)
            for i, s in enumerate(bs.STATS))]
        read += 1
        if not any(low <= lvl <= high for lvl in fits):
            out.append(
                f"{CHARACTERS[rid]['name']}'s battle sheet fits Affinity "
                f"{fits}, where its exp gives {low} to {high} and its "
                f"rewards claimed say {claimed}: the exp table "
                f"(constants.AFFINITY_TO_NEXT) or the reading is wrong.")
    return out, read


def run():
    add_source_to_path()
    from game_data.constants import (AFFINITY_CAP, AFFINITY_CAP_EXP,
                                     affinity_level)
    out = []
    for exp, level in READ + ((AFFINITY_CAP_EXP, AFFINITY_CAP),):
        if affinity_level(exp) != level:
            out.append(f"exp {exp} reads Affinity {affinity_level(exp)}, "
                       f"where the game says {level}.")

    snaps = _snapshots()
    if not snaps:
        note("no snapshot on hand: the rewards claimed and the battle "
             "sheets were not held against the exp table")
        return out
    for _when, rows in snaps:
        for rid, (exp, claimed) in rows.items():
            if claimed > affinity_level(exp, claimed):
                out.append(f"res_id {rid} has claimed {claimed} Affinity "
                           f"rewards on exp {exp}, which the table makes "
                           f"level {affinity_level(exp)}: a level can "
                           f"never be below its rewards.")
                break
    sheets, read = _sheets_follow_the_level(snaps)
    out.extend(sheets)
    if not read:
        note("no battle sheet of a combatant levelled past its rewards "
             "claimed, so which of the two the stats follow went untested")

    from optimizer.optimizer import GearOptimizer
    opt = GearOptimizer()
    opt.load_data(newest_snapshot())
    latest = snaps[-1][1]
    for name, info in opt.character_info.items():
        exp, claimed = latest.get(info.res_id, (None, None))
        if exp is not None and info.friendship_index \
                != affinity_level(exp, claimed):
            out.append(f"the program reads {name}'s Affinity as "
                       f"{info.friendship_index}, where exp {exp} is "
                       f"level {affinity_level(exp, claimed)} "
                       f"({claimed} rewards claimed). See "
                       f"`GearOptimizer.load_data`.")
            break
    return out
