"""The default presets' derivation still runs, and is re-checked once a
Galactic Disaster season.

`docs/preset_weights.py` derives the shipped Gear Score weights from the
Optimizer's own score, at a reference build made of the program's own
data (`docs/preset_weights.md`). It reaches deep into the program -- the
optimizer's statics, the scoring core, the partner and potential
helpers -- so a refactor can break it without anything else noticing,
and the next time the weights are due the tool no longer runs. What
this holds:

1. **Every preset derives** from the stored archetypes: the scaling
   stat reads 1, every weight is a finite number of zero or more, and a
   stat the score cannot price keeps the preset's own tie-breaker.
2. **The reference build is the one documented**: level 61, the class's
   5-star partner's flat stats, potential nodes 5 and 6 at their fifth
   level, node 7 taken, the highest Affection.
3. **The check is not overdue**: from a Galactic Disaster season's part
   2 on, `python docs/preset_weights.py --check` must have run in that
   season, since the archetypes follow the game.

Needs the maintainer's captured data and the stored archetypes; skips
without them.
"""

import importlib.util
import json
import math

from ._harness import REPO_ROOT, Skip, add_source_to_path, newest_snapshot

NAME = "the default presets still derive"


def _tool():
    path = REPO_ROOT / "docs" / "preset_weights.py"
    spec = importlib.util.spec_from_file_location("preset_weights", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run():
    add_source_to_path()
    if newest_snapshot() is None:
        raise Skip("no snapshot to build the reference combatants from")
    tool = _tool()
    if not tool.ARCHETYPES.exists():
        raise Skip("no stored archetypes -- run `python "
                   "docs/preset_weights.py --derive`")
    stored = json.loads(tool.ARCHETYPES.read_text(encoding="utf-8"))
    import os
    here = os.getcwd()
    try:
        world = tool.World()
        out = []
        for preset in tool.all_presets(world):
            name = tool.combatant_of(preset)
            if name not in world.settings:
                continue
            derived, _stats, _notes = tool.derive_preset(world, stored,
                                                         preset)
            spec = tool.VARIANTS.get(preset) or {}
            s = dict(world.settings[name], **spec.get("settings", {}))
            current = world.presets.get(preset) or world.presets.get(
                spec.get("like", ""), {})
            unit = tool.baseline(s, current)
            if derived.get(unit) != 1.0:
                out.append(f"{preset} reads {derived.get(unit)} on its "
                           f"scaling stat {unit}, not 1. See `baseline` "
                           f"and `derive_preset` in docs/preset_weights.py.")
            # Asked of the settings, not of `baseline`, which would
            # agree with itself however it chose.
            if (s.get("atk_def_split", 0) >= 50
                    or s.get("shielding_healing_weight", 0) >= 50) \
                    and derived.get("DEF%") != 1.0:
                out.append(f"{preset} scales off DEF or heals, and reads "
                           f"{derived.get('DEF%')} on DEF%, not 1.")
            bad = [k for k, v in derived.items()
                   if not isinstance(v, (int, float)) or math.isnan(v)
                   or math.isinf(v) or v < 0]
            if bad:
                out.append(f"{preset} derives {bad} as "
                           f"{[derived[k] for k in bad]}.")
            if derived.get("Ego") != current.get("Ego", 0.0):
                out.append(f"{preset}'s Ego is {derived.get('Ego')}, not "
                           f"its own tie-breaker {current.get('Ego')}: the "
                           f"score prices Ego at nothing, so the preset's "
                           f"weight must stand.")
        out.extend(_reference_is_documented(tool, world))
        out.extend(_not_overdue(tool, world, stored))
        return out
    finally:
        os.chdir(here)


def _reference_is_documented(tool, world):
    from game_data import FRIENDSHIP_BONUSES, PARTNER_CLASS_STATS
    from game_data.characters import (get_character_by_name,
                                      get_character_stats_at_level,
                                      get_potential_stat_bonus)
    from game_data import CHARACTERS
    from game_data.characters import CHARACTERS_BY_NAME
    out = []
    # A combatant the tables know: settings saved while one was new
    # carry its res_id as the name, and that sorts first.
    name = next(n for n in sorted(world.settings) if n in CHARACTERS_BY_NAME)
    cs = world.statics(name)
    char = get_character_by_name(name)
    level = get_character_stats_at_level(char, tool.LEVEL)
    if cs["base_atk"] != level["base_atk"]:
        out.append(f"{name}'s reference base ATK is {cs['base_atk']}, not "
                   f"{level['base_atk']} at level {tool.LEVEL}.")
    _prid, partner = world.partner(name)
    cls = (partner or {}).get("class") or char.get("class")
    flat = PARTNER_CLASS_STATS[(tool.PARTNER_GRADE, cls)]
    if cs["partner_flat_atk"] != flat["atk"]:
        out.append(f"{name}'s reference partner ATK is "
                   f"{cs['partner_flat_atk']}, not the class's 5-star "
                   f"{flat['atk']}.")
    if cs["affection_atk"] != FRIENDSHIP_BONUSES[-1][1]:
        out.append(f"{name}'s reference Affection ATK is "
                   f"{cs['affection_atk']}, not the highest tier's.")
    rid = next(r for r, c in CHARACTERS.items()
               if isinstance(c, dict) and c.get("name") == name)
    total = {}
    for node in (50, 60):
        stat, bonus = get_potential_stat_bonus(rid, node,
                                               tool.POTENTIAL_LEVEL)
        total[stat] = total.get(stat, 0) + bonus
    keys = {"ATK%": "pot_atk_pct", "DEF%": "pot_def_pct",
            "HP%": "pot_hp_pct", "CRate": "pot_crate", "CDmg": "pot_cdmg"}
    for stat, bonus in total.items():
        if stat in keys and abs(cs[keys[stat]] - bonus) > 1e-9:
            out.append(f"{name}'s reference {stat} from potential nodes is "
                       f"{cs[keys[stat]]}, not {bonus} at level "
                       f"{tool.POTENTIAL_LEVEL}.")
    from optimizer import core
    from game_data.potential_7 import get_potential_7
    if cs.get("potential_7") != core.potential_7_effects(get_potential_7(rid)):
        out.append(f"{name}'s reference build does not have node 7 taken, "
                   f"so the weights leave out what its growth makes a "
                   f"stat worth.")
    return out


def _not_overdue(tool, world, stored):
    season, part = tool.season_part(world.snapshot)
    if season is None or part is None or part < 2:
        return []
    checked = stored.get("checked") or {}
    if checked.get("season") == season and (checked.get("part") or 0) >= 2:
        return []
    return [f"{season} is in its part {part} and the preset archetypes "
            f"were last checked {checked.get('at', 'never')} "
            f"({checked.get('season')} part {checked.get('part')}): run "
            f"`python docs/preset_weights.py --check`, and re-derive if "
            f"it reports weights that moved."]
