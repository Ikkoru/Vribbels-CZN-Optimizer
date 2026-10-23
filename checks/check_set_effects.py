"""A set with several bonuses counts every one of them.

`sets.py` lists a set's bonuses as `effects` where it has more than one
(Snowflake of OFM's Powder Snow damage and its Critical Damage), and
every formula reads them through `sets.set_effects`. A reader left on
the one `stat` and `value` reads nothing off such a set, and the build
still ranks, plausibly, without the bonus:

1. **The stat sheet** (`core.compute_build_stats`): each Final-stat
   bonus, a conditional one at the set's effect share.
2. **The damage card multiplier** (`core.damage_card_multiplier`):
   each `DMG multi` and `DMG add` bonus at the share.
3. **The contributions popup** (`GearOptimizer.compute_build_breakdown`)
   agrees with the stat sheet.
4. **The preset derivation** prices a set's every bonus
   (`preset_derivation.synthetic_sets`).
5. **The launch-time data check** reads `effects` in place of the pair,
   and names a bonus typed wrong inside it.

Held on a probe set put into `SETS` for the run, and on Snowflake of
OFM itself.
"""

from ._harness import add_source_to_path

NAME = "a set's every bonus counts"

PROBE = 9998
COMBATANT = "Rossweisse"


class _Piece:
    """What the formulas read off a fragment: a set and no stats."""
    main_stat = None
    substats = ()

    def __init__(self, set_id):
        self.set_id = set_id

    def get_total_stats(self):
        return {}


def run():
    add_source_to_path()
    from optimizer import core
    from optimizer.optimizer import GearOptimizer
    from game_data import SETS, set_effects
    import preset_derivation as pd
    import game_data_validator as gv
    from game_data.client_overlay import hand

    out = []
    snowflake = SETS.get(31) or {}
    if len(set_effects(snowflake)) < 2:
        out.append("Snowflake of OFM lists fewer than two bonuses: this "
                   "check's case of several is gone. Point it at one.")
    opt = GearOptimizer()
    cs = opt._build_char_static(COMBATANT, 61)
    bare = [_Piece(1)] * 6
    try:
        SETS[PROBE] = {"name": "Probe Set", "pieces": 2,
                       "type": "conditional",
                       "effects": [{"stat": "Crit DMG", "value": 20},
                                   {"stat": "Crit Rate", "value": 10},
                                   {"stat": "DMG multi", "value": 30},
                                   {"stat": "DMG add", "value": 40}]}
        worn = [_Piece(PROBE)] * 2 + [_Piece(1)] * 4
        shares = {PROBE: 0.5}
        before = core.compute_build_stats(bare, cs, shares)
        after = core.compute_build_stats(worn, cs, shares)
        moved = (round(after["CDmg"] - before["CDmg"], 6),
                 round(after["CRate"] - before["CRate"], 6))
        if moved != (10.0, 5.0):
            out.append(f"a conditional set of four bonuses at half share "
                       f"moves CDmg and CRate by {moved}, not (10, 5): each "
                       f"Final-stat bonus counts (`compute_build_stats`).")
        sp = core.build_score_precompute({"set_effect_pcts": {str(PROBE): 50}})
        lift = round(core.damage_card_multiplier(worn, sp)
                     - core.damage_card_multiplier(bare, sp), 6)
        if lift != round(1.0 * 0.15 + 0.20, 6):
            out.append(f"its DMG multi and DMG add bonuses lift the damage "
                       f"card multiplier by {lift}, not 0.35 at half share "
                       f"(`damage_card_multiplier`).")
        settings = {"set_effect_pcts": {str(PROBE): 50}}
        breakdown = opt.compute_build_breakdown(worn, COMBATANT,
                                                settings=settings)
        cdmg = (breakdown.get("CDmg") or {}).get("set_effect")
        if cdmg != 10:
            out.append(f"the contributions popup gives the set's CDmg as "
                       f"{cdmg!r}, not the 10 the stat sheet counts: both "
                       f"read every bonus (`compute_build_breakdown`).")
        priced = pd.synthetic_sets(PROBE, {PROBE: 0.5})
        if round(priced.get("CDmg", 0), 6) != 10 + 25 \
                or round(priced.get("CRate", 0), 6) != 5:
            out.append(f"the preset derivation prices the set as {priced}: "
                       f"CDmg 10 and CRate 5 at half share, beside "
                       f"Executioner's Tool's 25 (`synthetic_sets`).")
        # The data check reads the table as typed (`client_overlay.hand`),
        # a copy of its own: the probe goes there too, for the run.
        hand("SETS")[PROBE] = SETS[PROBE]
        problems = []
        gv._check_sets(problems)
        if any("Probe Set" in p for p in problems):
            out.append(f"the data check refuses a well-formed set of "
                       f"several bonuses: {[p for p in problems if 'Probe' in p]}")
        SETS[PROBE]["effects"].append({"stat": "Crit Damage", "value": 5})
        problems = []
        gv._check_sets(problems)
        if not any("Probe Set" in p and "Crit Damage" in p for p in problems):
            out.append("a bonus typed wrong inside `effects` passes the data "
                       "check: its stat is silently ignored.")
    finally:
        SETS.pop(PROBE, None)
        hand("SETS").pop(PROBE, None)
    return out


# What this check must catch, for `checks/faults.py`.
FAULTS = [
    ("only the first bonus read", "game_data.sets:set_effects",
     "for e in info.get(\"effects\") or () if isinstance(e, dict)]",
     "for e in (info.get(\"effects\") or ())[:1] if isinstance(e, dict)]",
     "each Final-stat bonus counts"),
    ("the stat sheet on the one pair", "optimizer.core:compute_build_stats",
     "for raw_stat, value in set_effects(set_info):",
     "for raw_stat, value in [(set_info.get('stat'), set_info.get('value', 0))]:",
     "each Final-stat bonus counts"),
    ("the card multiplier on the one pair",
     "optimizer.core:damage_card_multiplier",
     "for raw_stat, value in set_effects(set_info):",
     "for raw_stat, value in [(set_info.get('stat'), set_info.get('value', 0))]:",
     "lift the damage card multiplier"),
    ("the popup on the one pair",
     "optimizer.optimizer:GearOptimizer.compute_build_breakdown",
     "for raw, val in set_effects(si):",
     "for raw, val in [(si.get('stat'), si.get('value', 0))]:",
     "the contributions popup gives"),
    ("the derivation on the one pair", "preset_derivation:synthetic_sets",
     "for stat, value in set_effects(info):",
     "for stat, value in [(info.get('stat'), info.get('value', 0))]:",
     "the preset derivation prices"),
    ("a bonus's stat left unchecked", "game_data_validator:_check_sets",
     "if stat not in stat_names:", "if False:", "typed wrong inside"),
]
