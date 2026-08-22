"""The three DoT types do not share a damage formula.

Agony scales off ATK and DoT% like the others but neither crits nor
takes buffs; Fracture and Scorched do both, which makes them ordinary
ATK-scaling damage. Dropping the buffs is what makes the difference
build-dependent rather than a constant rescale: a conditional set
dialled up for `DMG multi` lifts the Fracture share and not the Agony
one, so the two rank gear differently.

Nothing about a regression here is visible. Folding Agony back into the
shared `atk_scaling` term still produces a full, plausible, correctly
sorted results table -- one that has quietly ranked crit gear for a
combatant whose damage cannot crit.

Canonical: docs/game_formulas.md §3.4 and §8.
"""

from ._harness import add_source_to_path

NAME = "DoT types score by their own rules"

# A conditional set with a `DMG multi` effect, and its piece count.
DMG_MULTI_SET = 10
DMG_MULTI_PIECES = 2

BASE_SETTINGS = {
    "avg_card_dmg_pct": 100,
    "avg_mult_buff_pct": 0,
    "avg_add_buff_pct": 0,
    "atk_def_split": 0,
    "shielding_healing_weight": 0,
}
STATS = {"ATK": 5000, "DEF": 500, "CRate": 0, "CDmg": 125,
         "Extra DMG%": 0, "DoT%": 0}

# share key -> (label, crits, takes buffs)
TYPES = {
    "dot_pct": ("Agony", False, False),
    "fracture_pct": ("Fracture/Scorched", True, True),
    "extra_pct": ("Extra", True, True),
}


class _Piece:
    """Only the two attributes the score walk reads off a fragment."""

    def __init__(self, set_id):
        self.set_id = set_id
        self.main_stat = None


def run():
    failures = []
    add_source_to_path()
    from optimizer import core
    from game_data.sets import SETS

    set_info = SETS.get(DMG_MULTI_SET)
    if not set_info or set_info.get("stat") != "DMG multi":
        return [
            f"Set {DMG_MULTI_SET} is no longer a `DMG multi` conditional "
            f"set, so this check is testing nothing. Point it at one that is."
        ]

    bare = [_Piece(1)] * 6
    with_set = [_Piece(DMG_MULTI_SET)] * DMG_MULTI_PIECES + [_Piece(1)] * 4

    for key, (label, crits, buffed) in TYPES.items():
        pure = dict(BASE_SETTINGS, **{key: 100})

        sp = core.build_score_precompute(pure)
        no_crit = core.compute_score_components(
            bare, dict(STATS, CRate=0, CDmg=200), sp, "Passion")[0]
        all_crit = core.compute_score_components(
            bare, dict(STATS, CRate=100, CDmg=200), sp, "Passion")[0]
        moved = all_crit != no_crit
        if moved and not crits:
            failures.append(
                f"{label} damage responded to CRate/CDmg ({no_crit:.2f} -> "
                f"{all_crit:.2f}). It cannot crit, so crit gear must not "
                f"rank for a combatant whose damage is all {label}."
            )
        elif crits and not moved:
            failures.append(
                f"{label} damage ignored CRate/CDmg ({no_crit:.2f}). It "
                f"crits, so crit gear is being under-ranked for it."
            )

        sp = core.build_score_precompute(dict(pure, set_effect_pcts={
            str(DMG_MULTI_SET): 100}))
        without = core.compute_score_components(bare, STATS, sp, "Passion")[0]
        within = core.compute_score_components(with_set, STATS, sp, "Passion")[0]
        lifted = within != without
        if lifted and not buffed:
            failures.append(
                f"{label} damage was lifted by a conditional `DMG multi` "
                f"set ({without:.2f} -> {within:.2f}). It takes no buffs."
            )
        elif buffed and not lifted:
            failures.append(
                f"{label} damage ignored a conditional `DMG multi` set "
                f"({without:.2f}). It takes buffs."
            )

    # The typed shares must partition the damage linearly: a mixed
    # setting has to equal the shares' weighted pure terms, or a slider
    # is being dropped from the blend.
    mixed = dict(BASE_SETTINGS, extra_pct=30, dot_pct=30, fracture_pct=20)
    sp = core.build_score_precompute(mixed)
    blended = core.compute_score_components(bare, STATS, sp, "Passion")[0]

    parts = 0.0
    for key in TYPES:
        share = mixed[key] / 100.0
        pure_sp = core.build_score_precompute(dict(BASE_SETTINGS, **{key: 100}))
        parts += share * core.compute_score_components(
            bare, STATS, pure_sp, "Passion")[0]
    normal_sp = core.build_score_precompute(dict(BASE_SETTINGS))
    parts += 0.20 * core.compute_score_components(
        bare, STATS, normal_sp, "Passion")[0]

    if abs(blended - parts) > 1e-9:
        failures.append(
            f"Mixed shares do not equal the weighted pure terms "
            f"({blended:.6f} vs {parts:.6f}). A share is missing from the "
            f"blend, or normal_share is not the remainder."
        )

    return failures
