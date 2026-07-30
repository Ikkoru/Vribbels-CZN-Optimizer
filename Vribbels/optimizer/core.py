"""
Pure per-combo evaluation core for the optimizer.

Everything in this module is a module-level function operating on plain
picklable data -- no GearOptimizer instance, no Tk, no manager access.
This lets the multiprocessing workers use it directly: a worker process
only needs this module (plus game_data / models, which it imports
normally on spawn) and the per-run context dict built by
GearOptimizer.build_run_context().

Formula source of truth: docs/game_formulas.md. The GearOptimizer
formula methods delegate here, so there is exactly ONE implementation
of each formula. When in-game math disagrees, fix docs/game_formulas.md
first, then this module.

The per-run context (`ctx`) consumed by evaluate_combo is a plain dict:

    {
      "char_static":       dict, see GearOptimizer._build_char_static
                           (base/affection/partner/potential/equipment
                           values -- constant across every combo of a run),
      "attribute":         str, resolved element attribute ("" = none),
      "set_effect_shares": dict {int set_id: float 0..1} -- per-
                           CONDITIONAL-set effect shares (absent = 0),
      "sets_selected":     list[int] of chosen set ids,
      "max_flex_slots":    int 0..6,
      "hal":               dict of Have-at-least minimums (may be empty),
      "score_pre":         dict, see build_score_precompute(),
      "gref":              dict, see build_greedy_refs() -- the greedy
                           trim references {"D": float, "S": float}.
                           Per-run constants used ONLY to gate in-flight
                           trimming (trim_blend); the displayed score is
                           re-blended parent-side against the run's true
                           max-D / max-S (see optimizer.optimize).
    }

Scoring (percent-normalized blend)
----------------------------------
compute_score_components returns (D, S): D is the normalized damage
term, S is the shield/heal term. Two blends exist:

  * trim_blend(D, S, sp, gref): (1-h)*D/gD_ref + h*S/gS_ref, using the
    per-run GREEDY refs. A per-run constant divisor pair, so it's safe
    for the parallel/sequential in-flight trim and the deterministic
    tie-break -- every worker sees the same divisors.
  * the DISPLAY blend (parent-side, after the merge): same formula but
    with D_ref/S_ref = the run's true max-D / max-S across all surviving
    results, then all scores are rescaled so the top row reads 100. See
    optimizer.optimize's post-merge re-blend.

evaluate_combo returns (status, score, stats): on COMBO_OK, score is
the trim_blend scalar (greedy refs) that gates trimming and the
tie-break, and the raw (D, S) components ride inside stats under the
"_D" / "_S" keys for the parent-side display re-blend. The result-tuple
shape (gear, score, stats) is therefore unchanged.
"""

from game_data import SETS, SLOT_ORDER, SET_STAT_NAME_MAP

# SET_STAT_NAME_MAP is defined in game_data/sets.py, beside the `stat`
# values it maps, and re-exported here (and by optimizer.py) under the
# same name for the callers that have always imported it from the
# optimizer package.


# evaluate_combo() status codes -- the caller maps these onto its
# counters (total_combinations / passed_set_reqs / passed_have_at_least)
# so single-thread and parallel paths count identically.
COMBO_DUPLICATE = 0   # same fragment id appears twice -> skip silently
COMBO_SET_FAIL = 1    # too many wildcard slots for max_flex_slots
COMBO_HAL_FAIL = 2    # passed sets, failed a Have-at-least minimum
COMBO_OK = 3          # scored


def parse_set_effect_shares(settings: dict) -> dict:
    """Per-conditional-set effect shares from a settings dict:
    settings["set_effect_pcts"] ({str set_id: int 0-100}, absent id = 0)
    -> {int set_id: float 0..1}, zero entries dropped so an empty dict
    means "no conditional set contributes" and consumers can skip the
    set walk entirely."""
    shares: dict = {}
    for k, v in (settings.get("set_effect_pcts") or {}).items():
        try:
            sid = int(k)
            val = float(v) / 100.0
        except (TypeError, ValueError):
            continue
        if val > 0:
            shares[sid] = min(1.0, val)
    return shares


def empty_char_static() -> dict:
    """Char-static inputs for `char_name=None` calls: all zeros except
    the 125.0 base Crit DMG default (matches the historical behavior of
    calculate_build_stats without a character)."""
    return {
        "base_atk": 0, "base_def": 0, "base_hp": 0,
        "base_cr": 0, "base_cd": 125.0,
        "affection_atk": 0, "affection_def": 0, "affection_hp": 0,
        "partner_flat_atk": 0, "partner_flat_def": 0, "partner_flat_hp": 0,
        "partner_atk_pct": 0, "partner_def_pct": 0, "partner_hp_pct": 0,
        "partner_cdmg": 0, "partner_extra_dmg": 0,
        "partner_crate": 0, "partner_dot": 0, "partner_ego": 0,
        # Conditional partner passive effects ("stats_conditional" in
        # partners.py). NOTE: ALL partner PASSIVE contributions -- these
        # cond keys AND the unconditional keys above -- are excluded
        # from the Have-at-least / Potential-7 comparison values (the
        # partner_flat_* class stats DO count for ATK/DEF/HP); the
        # conditional/unconditional split is kept for future use.
        "partner_atk_pct_cond": 0, "partner_def_pct_cond": 0,
        "partner_hp_pct_cond": 0,
        "partner_crate_cond": 0, "partner_cdmg_cond": 0,
        "partner_extra_dmg_cond": 0, "partner_dot_cond": 0,
        "partner_ego_cond": 0,
        "pot_atk_pct": 0, "pot_def_pct": 0, "pot_hp_pct": 0,
        "pot_crate": 0, "pot_cdmg": 0,
        "equip_flat_atk": 0, "equip_flat_def": 0, "equip_flat_hp": 0,
        "equip_atk_pct": 0.0, "equip_def_pct": 0.0, "equip_hp_pct": 0.0,
    }


def compute_build_stats(gear: list, cs: dict,
                        set_effect_shares: dict = None) -> dict:
    """Final ATK/DEF/HP layered formula over a 6-piece build.

    `cs` is the char-static dict (see GearOptimizer._build_char_static);
    everything combo-dependent is derived from `gear` here.
    `set_effect_shares` is the per-conditional-set effect share dict
    ({int set_id: float 0..1}, see parse_set_effect_shares); None/empty
    means no conditional set effect touches Final stats. Returns the
    exact dict shape calculate_build_stats has always returned,
    including the underscore-prefixed scoring internals.
    """
    # ----- Memory Fragment (substats + main stats) -----------------------
    # Sum % and flat contributions from the 6 fragments. Set bonuses are
    # applied below and lumped into the same "Memory Fragment %" bucket
    # since they're triggered by gear pieces.
    mf_atk_pct, mf_def_pct, mf_hp_pct = 0, 0, 0
    gear_flat_atk, gear_flat_def, gear_flat_hp = 0, 0, 0
    crit_rate, crit_dmg = 0, 0
    ego, extra_dmg, dot_dmg = 0, 0, 0

    for piece in gear:
        piece_stats = piece.get_total_stats()
        mf_atk_pct += piece_stats.get("ATK%", 0)
        mf_def_pct += piece_stats.get("DEF%", 0)
        mf_hp_pct += piece_stats.get("HP%", 0)
        gear_flat_atk += piece_stats.get("Flat ATK", 0)
        gear_flat_def += piece_stats.get("Flat DEF", 0)
        gear_flat_hp += piece_stats.get("Flat HP", 0)
        crit_rate += piece_stats.get("CRate", 0)
        crit_dmg += piece_stats.get("CDmg", 0)
        ego += piece_stats.get("Ego", 0)
        extra_dmg += piece_stats.get("Extra DMG%", 0)
        dot_dmg += piece_stats.get("DoT%", 0)

    # Set bonuses: count pieces per set, route satisfied bonuses into
    # the right bucket. See docs/game_formulas.md §5 for the full taxonomy:
    #   - "unconditional" sets always apply at full value.
    #   - "conditional" sets with stat in {Crit DMG, Crit Rate} apply at
    #     value × that set's own effect share.
    #   - "conditional" sets with stat in {DMG multi, DMG add} do NOT
    #     touch Final stats; they're handled by the score functions
    #     (skipped here).
    shares = set_effect_shares or {}
    set_counts = {}
    for piece in gear:
        set_counts[piece.set_id] = set_counts.get(piece.set_id, 0) + 1
    # Conditional crit-set contributions are tracked separately: they
    # count toward Final CRate/CDmg (and the score) at each set's own
    # effect-share weighting, but the Have-at-least gate must NOT
    # see them -- conditional procs never appear on the in-game stat
    # sheet, and the in-game minimum requirements only check
    # sheet-visible stats. See the _hal_* return keys.
    cond_crate = 0.0
    cond_cdmg = 0.0
    for set_id, count in set_counts.items():
        if set_id not in SETS:
            continue
        set_info = SETS[set_id]
        if count < set_info["pieces"]:
            continue
        stype = set_info["type"]
        raw_stat = set_info.get("stat", "")
        value = set_info.get("value", 0)

        if stype == "unconditional":
            effective = value
        elif stype == "conditional" and raw_stat in ("Crit DMG", "Crit Rate"):
            effective = value * shares.get(set_id, 0.0)
        else:
            # Conditional DMG multi / DMG add: handled by the optimizer
            # score function (flows through card_mult, not Final stats).
            continue

        program_stat = SET_STAT_NAME_MAP.get(raw_stat)
        if program_stat == "ATK%":
            mf_atk_pct += effective
        elif program_stat == "DEF%":
            mf_def_pct += effective
        elif program_stat == "HP%":
            mf_hp_pct += effective
        elif program_stat == "CDmg":
            crit_dmg += effective
            if stype == "conditional":
                cond_cdmg += effective
        elif program_stat == "CRate":
            crit_rate += effective
            if stype == "conditional":
                cond_crate += effective

    # Potential-node % bonuses (these go into the inner multiplier
    # alongside Memory Fragment %).
    potential_atk_pct = cs["pot_atk_pct"]
    potential_def_pct = cs["pot_def_pct"]
    potential_hp_pct = cs["pot_hp_pct"]
    # Potential-node CRate/CDmg are flat additions (not part of the
    # ATK/DEF/HP formula structure).
    crit_rate += cs["pot_crate"]
    crit_dmg += cs["pot_cdmg"]

    # Partner passive bonuses: ATK%/DEF%/HP% go into the OUTER
    # multiplier alongside Equipment %; CRate / CDmg / Extra DMG% /
    # DoT% / Ego are flat additions to their respective totals.
    # Every partner PASSIVE bonus -- unconditional ("stats") and
    # conditional ("stats_conditional", *_cond keys) alike -- applies
    # at full value to Final stats and the score, but NONE of it
    # counts toward the Have-at-least / Potential-7 comparison values:
    # per in-game verification, the Potential 7 requirement checks
    # ignore all Partner passive bonuses. (The Partner's flat CLASS
    # stats, by contrast, DO count -- they sit inside _inner.) The
    # conditional/unconditional split is kept in case a future
    # consumer needs the distinction. For ATK/DEF/HP the partner %
    # lands in the OUTER multiplier, which the inner comparison never
    # sees; the crit/extra/dot/ego exclusions are explicit (see the
    # _hal_* return keys).
    partner_atk_pct = cs["partner_atk_pct"] + cs["partner_atk_pct_cond"]
    partner_def_pct = cs["partner_def_pct"] + cs["partner_def_pct_cond"]
    partner_hp_pct = cs["partner_hp_pct"] + cs["partner_hp_pct_cond"]
    crit_rate += cs["partner_crate"] + cs["partner_crate_cond"]
    crit_dmg += cs["partner_cdmg"] + cs["partner_cdmg_cond"]
    extra_dmg += cs["partner_extra_dmg"] + cs["partner_extra_dmg_cond"]
    dot_dmg += cs["partner_dot"] + cs["partner_dot_cond"]
    ego += cs["partner_ego"] + cs["partner_ego_cond"]

    # ----- Apply the layered Final ATK/DEF/HP formulas -------------------
    # Final X = ((Base X + Partner X) × (1 + MF X% + Potential X%)
    #            + Gear Flat X + Affection Flat X)
    #         × (1 + Partner X% + Equipment X%)
    #         + Equipment Flat X
    def _inner(base, partner_flat, mf_pct, pot_pct, gear_flat, affection_flat):
        """Inner stat = the build's value BEFORE the outer multiplier
        (Partner flat class stats included inside the multiplier).
        Feeds _final, and is exposed under the "_inner_X" keys for the
        Have-at-least check, the "Potential 7 X" rows in the Stat
        Contributions popup, and the Pot7 rows in Stats Comparison --
        checks that exist primarily (but not exclusively) for the
        in-game Potential 7 stat requirements. Per in-game
        verification, those checks DO see the Partner's flat class
        stats, but ignore Partner passive bonuses (including the
        Partner% outer multiplier), Equipment (% and flat), and
        conditional set procs -- exactly what this inner value omits.
        """
        inner_mult = 1 + (mf_pct + pot_pct) / 100
        return (base + partner_flat) * inner_mult + gear_flat + affection_flat

    def _final(base, partner_flat, mf_pct, pot_pct, gear_flat, affection_flat,
               partner_pct, equip_pct, equip_flat):
        outer_mult = 1 + (partner_pct + equip_pct) / 100
        inner = _inner(base, partner_flat, mf_pct, pot_pct, gear_flat,
                       affection_flat)
        return inner * outer_mult + equip_flat

    # Shield_Heal_DEF: a Final-DEF variant where Partner_FLAT_DEF is
    # pulled OUT of the inner multiplier (treated as additive flat
    # instead). The only difference from regular Final DEF. See
    # docs/game_formulas.md §4.1 for the formula derivation. Computed
    # here because it shares all the same inputs as Final DEF; consumed
    # by compute_score via the _shield_heal_def return key.
    def _final_shield_heal_def(base, partner_flat, mf_pct, pot_pct, gear_flat,
                               affection_flat, partner_pct, equip_pct, equip_flat):
        inner_mult = 1 + (mf_pct + pot_pct) / 100
        outer_mult = 1 + (partner_pct + equip_pct) / 100
        # Difference vs _final: partner_flat is NOT added to `base`
        # before applying inner_mult -- it's added as a separate flat
        # contribution. The rest of the layered structure is identical.
        inner = base * inner_mult + partner_flat + gear_flat + affection_flat
        return inner * outer_mult + equip_flat

    total_atk = _final(
        cs["base_atk"], cs["partner_flat_atk"], mf_atk_pct, potential_atk_pct,
        gear_flat_atk, cs["affection_atk"],
        partner_atk_pct, cs["equip_atk_pct"], cs["equip_flat_atk"],
    )
    total_def = _final(
        cs["base_def"], cs["partner_flat_def"], mf_def_pct, potential_def_pct,
        gear_flat_def, cs["affection_def"],
        partner_def_pct, cs["equip_def_pct"], cs["equip_flat_def"],
    )
    total_hp = _final(
        cs["base_hp"], cs["partner_flat_hp"], mf_hp_pct, potential_hp_pct,
        gear_flat_hp, cs["affection_hp"],
        partner_hp_pct, cs["equip_hp_pct"], cs["equip_flat_hp"],
    )
    # Potential-7 ATK/DEF/HP -- the inner build value: Partner flat
    # class stats included, no Partner passive % and no Equipment
    # (% or flat). Used by meets_have_at_least and surfaced as
    # "Potential 7 X" in the breakdown popup and Stats Comparison.
    inner_atk = _inner(cs["base_atk"], cs["partner_flat_atk"], mf_atk_pct,
                       potential_atk_pct, gear_flat_atk, cs["affection_atk"])
    inner_def = _inner(cs["base_def"], cs["partner_flat_def"], mf_def_pct,
                       potential_def_pct, gear_flat_def, cs["affection_def"])
    inner_hp = _inner(cs["base_hp"], cs["partner_flat_hp"], mf_hp_pct,
                      potential_hp_pct, gear_flat_hp, cs["affection_hp"])
    shield_heal_def = _final_shield_heal_def(
        cs["base_def"], cs["partner_flat_def"], mf_def_pct, potential_def_pct,
        gear_flat_def, cs["affection_def"],
        partner_def_pct, cs["equip_def_pct"], cs["equip_flat_def"],
    )
    total_cr = cs["base_cr"] + crit_rate
    total_cd = cs["base_cd"] + crit_dmg

    return {
        "ATK": total_atk, "DEF": total_def, "HP": total_hp,
        "CRate": total_cr, "CDmg": total_cd,
        # Summed % buckets — informational; reflects total % from MF+
        # potential+partner+equipment so the user can see what's
        # contributing. The Final ATK/DEF/HP above already account for
        # the layered formula.
        "ATK%": mf_atk_pct + potential_atk_pct + partner_atk_pct + cs["equip_atk_pct"],
        "DEF%": mf_def_pct + potential_def_pct + partner_def_pct + cs["equip_def_pct"],
        "HP%":  mf_hp_pct + potential_hp_pct + partner_hp_pct + cs["equip_hp_pct"],
        "Ego": ego, "Extra DMG%": extra_dmg, "DoT%": dot_dmg,
        # Optimizer-scoring internals (underscore-prefixed). UI display
        # code can filter them out by ignoring keys starting with "_".
        # See compute_score.
        "_base_def_for_shield": cs["base_def"],
        "_shield_heal_def": shield_heal_def,
        # Have-at-least / Potential-7 comparison values for CRate/CDmg:
        # the final value MINUS conditional set contributions and MINUS
        # ALL partner passive contributions. The score keeps using the
        # full modeled CRate/CDmg; only the minimum gate (and the Pot7
        # display rows) use these.
        "_hal_crate": (total_cr - cond_crate
                       - cs["partner_crate"] - cs["partner_crate_cond"]),
        "_hal_cdmg": (total_cd - cond_cdmg
                      - cs["partner_cdmg"] - cs["partner_cdmg_cond"]),
        # Same for Extra DMG% / DoT% / Ego: final value minus ALL
        # partner passive contributions (no conditional-set path feeds
        # these).
        "_hal_extra": (extra_dmg - cs["partner_extra_dmg"]
                       - cs["partner_extra_dmg_cond"]),
        "_hal_dot": dot_dmg - cs["partner_dot"] - cs["partner_dot_cond"],
        "_hal_ego": ego - cs["partner_ego"] - cs["partner_ego_cond"],
        # Inner values (Partner flat included; no Partner% / outer
        # multiplier, no Equipment). Used by meets_have_at_least and
        # displayed as the "Potential 7 X" rows (popup + Stats
        # Comparison).
        "_inner_atk": inner_atk,
        "_inner_def": inner_def,
        "_inner_hp":  inner_hp,
    }


def count_locked_slots(combo, sets_selected: list) -> int:
    """Count how many slots are "locked" into a chosen set's satisfied bonus.

    A slot is locked if it belongs to a fully-satisfied bonus from one of
    the user's chosen sets. Total wildcard slots = 6 - locked; the build
    is valid if wildcard count <= max_flex_slots.

    This single rule implicitly enumerates the 6 combo-shape variants
    from docs/game_formulas.md:
      - locked=6 (0 wildcards): shape 4+2 (one 4pc + one 2pc) or 2+2+2
      - locked=4 (2 wildcards): shape 4+wild2 or 2+2+wild2
      - locked=2 (4 wildcards): shape 2+wild4
      - locked=0 (6 wildcards): shape wild6

    The max_flex_slots stepper cap maps directly to "how many wildcards
    are tolerated". Equivalent to enumerating per-shape but avoids
    partition combinatorics.

    Returns 0 when sets_selected is empty (every slot is a wildcard) --
    the caller's max_flex_slots check then determines whether that's
    acceptable.
    """
    if not sets_selected:
        return 0
    # Quick count: pieces per set in this build.
    set_counts: dict = {}
    for piece in combo:
        set_counts[piece.set_id] = set_counts.get(piece.set_id, 0) + 1
    locked = 0
    for set_id in sets_selected:
        if set_id not in SETS:
            continue
        pieces_needed = SETS[set_id]["pieces"]
        if set_counts.get(set_id, 0) >= pieces_needed:
            # Bonus is satisfied; this set locks `pieces_needed` slots.
            # We don't count overflow (e.g. 6 of a 4pc set still only
            # locks 4 -- the extra 2 are wildcards).
            locked += pieces_needed
    return locked


def meets_have_at_least(stats: dict, hal: dict) -> bool:
    """Check whether a build's stats meet every "Have at least" minimum.

    Returns True if all configured thresholds are satisfied (or no
    thresholds set). Empty / missing / zero thresholds are skipped
    (trivially met).

    These minimums exist primarily (but not exclusively) to help the
    user meet the in-game Potential 7 stat requirements, and the
    comparison values mirror what those in-game checks can see. Per
    in-game verification, the Potential 7 checks ignore ALL Partner
    PASSIVE bonuses (unconditional and conditional alike), all
    Equipment contributions, and conditional set procs (which never
    appear on the stat sheet) -- but they DO see the Partner's flat
    class stats.

    For ATK / DEF / HP, the comparison value is the INNER stat -- see
    _inner() in compute_build_stats: (Base + Partner flat) inside the
    inner multiplier, plus fragment flat and Affection flat; no outer
    (Partner% + Equipment%) multiplier, no Equipment flat.

    For CRate / CDmg, the comparison value is the final value minus
    conditional set contributions and minus all partner passive
    contributions (the _hal_crate / _hal_cdmg keys).

    For Ego / Extra DMG% / DoT%, the comparison value is the final
    value minus all partner passive contributions (_hal_ego /
    _hal_extra / _hal_dot); no conditional-set path feeds these stats.

    The optimizer SCORE still models every excluded source (conditional
    sets at their per-set effect-share weighting, partner passives at
    full value) -- only this gate ignores them.
    """
    if not hal:
        return True
    # Stats with an alternative comparison key; everything else uses
    # the regular key.
    alt_keys = {
        "ATK": "_inner_atk",
        "DEF": "_inner_def",
        "HP":  "_inner_hp",
        "CRate": "_hal_crate",
        "CDmg": "_hal_cdmg",
        "Extra DMG%": "_hal_extra",
        "DoT%": "_hal_dot",
        "Ego": "_hal_ego",
    }
    for stat, min_val in hal.items():
        if min_val is None or min_val <= 0:
            continue
        lookup_key = alt_keys.get(stat, stat)
        # Fall back to the regular stat if the inner key is missing
        # (defensive -- compute_build_stats always populates them).
        actual = stats.get(lookup_key, stats.get(stat, 0))
        if actual < min_val:
            return False
    return True


def build_score_precompute(settings: dict) -> dict:
    """Extract the combo-independent parts of the score formula from a
    per-character settings dict, once per run. Consumed by
    compute_score."""
    extra_share = settings.get("extra_pct", 0) / 100.0
    dot_share = settings.get("dot_pct", 0) / 100.0
    def_split = settings.get("atk_def_split", 0) / 100.0
    heal_share = settings.get("shielding_healing_weight", 0) / 100.0
    set_effect_shares = parse_set_effect_shares(settings)
    # avg_card_dmg_pct is the average card's intrinsic multiplier as a
    # percentage (100 = card does normal damage, 150 = +50%, etc.)
    base_multiplier = settings.get("avg_card_dmg_pct", 100) / 100.0
    avg_mult_buff = settings.get("avg_mult_buff_pct", 0) / 100.0
    avg_add_buff = settings.get("avg_add_buff_pct", 0) / 100.0
    return {
        "extra_share": extra_share,
        "dot_share": dot_share,
        "def_split": def_split,
        "heal_share": heal_share,
        "set_effect_shares": set_effect_shares,
        "base_multiplier": base_multiplier,
        "avg_mult_buff": avg_mult_buff,
        "avg_add_buff": avg_add_buff,
        # The damage-normalization baseline: the damage card multiplier
        # WITHOUT the conditional DMG-multi/DMG-add set terms. A per-run
        # constant; see compute_score for how (and why) it's applied.
        "buff_baseline": (
            base_multiplier * (1 + avg_mult_buff) + avg_add_buff
        ),
    }


def compute_score_components(gear: list, stats: dict, sp: dict,
                            attribute: str) -> tuple:
    """Return the (D, S) score components for a build.

    D = normalized damage term (the damage score divided by the per-run
    buff baseline). S = shield/heal term (no card multiplier -- buffs
    don't apply to shields/heals). The blends combine these against
    references; see the module docstring. Splitting them out lets the
    optimizer re-blend against run-max references after enumeration
    without re-deriving per-build math.

    See docs/game_formulas.md §3, §4, §5, §8. Constants that don't
    affect relative ranking are dropped from the comparison.
    """
    set_effect_shares = sp["set_effect_shares"]

    # ----- Conditional set DMG multi / DMG add accumulator -----
    # These flow through the damage card multiplier only (NOT
    # shield/heal -- see docs §5), each scaled by its own set's
    # effect share. An empty shares dict (no conditional set dialed
    # up) skips the whole walk -- the common case.
    set_dmg_multi_total = 0.0
    set_dmg_add_total = 0.0
    if set_effect_shares:
        set_counts: dict = {}
        for piece in gear:
            set_counts[piece.set_id] = set_counts.get(piece.set_id, 0) + 1
        for set_id, count in set_counts.items():
            share = set_effect_shares.get(set_id, 0.0)
            if not share or set_id not in SETS:
                continue
            set_info = SETS[set_id]
            if set_info.get("type") != "conditional":
                continue
            if count < set_info["pieces"]:
                continue
            raw_stat = set_info.get("stat", "")
            value = set_info.get("value", 0)
            if raw_stat == "DMG multi":
                set_dmg_multi_total += value * share
            elif raw_stat == "DMG add":
                set_dmg_add_total += value * share

    # ----- Card multiplier (damage only) -----
    # The damage card multiplier includes the user's avg buffs plus the
    # conditional DMG multi / DMG add set effects. Shielding/healing has
    # NO card multiplier at all: per maintainer-verified game behavior,
    # neither the Avg Multi/Add Buff% assumptions nor DMG multi/add set
    # effects affect shields or heals.
    mult_buffs_dmg = sp["avg_mult_buff"] + set_dmg_multi_total / 100.0
    add_buffs_dmg = sp["avg_add_buff"] + set_dmg_add_total / 100.0
    card_mult_dmg = sp["base_multiplier"] * (1 + mult_buffs_dmg) + add_buffs_dmg

    # ----- Crit modifier -----
    # Average damage per hit = (1 - p_crit) * base + p_crit * base * (1 + bonus)
    #                        = base * (1 + p_crit * bonus)
    # where bonus = (Final_CDmg - 100) / 100. CRate cap = 100%.
    final_crate = max(0.0, min(100.0, stats.get("CRate", 0)))
    final_cdmg = stats.get("CDmg", 125)
    crit_modifier = 1 + (final_crate / 100.0) * max(0.0, (final_cdmg - 100.0) / 100.0)

    # ----- Element DMG% -----
    # The optimizer treats all of a character's damage as their
    # element. We pick up the matching Element DMG% main stat from
    # slot 5 (if equipped). For Unknown-attribute characters, the
    # resolved attribute already reflects the user's element_override.
    element_dmg_pct = 0
    if attribute:
        elem_main_name = f"{attribute} DMG%"
        for piece in gear:
            if piece.main_stat and piece.main_stat.name == elem_main_name:
                element_dmg_pct += piece.main_stat.value
    element_multiplier = 1 + element_dmg_pct / 100.0

    # ----- ATK vs DEF scaling damage formulas -----
    # Constants (0.35, Enemy_Defense_Multiplier) dropped -- same
    # across all builds. See docs §3.1 / §3.2.
    final_atk = stats.get("ATK", 0)
    final_def = stats.get("DEF", 0)
    atk_scaling = card_mult_dmg * final_atk * element_multiplier * crit_modifier
    def_scaling = card_mult_dmg * (final_atk * 0.3 + final_def * 2.1) \
                  * element_multiplier * crit_modifier

    # Extra DMG and DoT always use ATK formula with the Mechanic_DMG%
    # multiplier (Extra DMG% or DoT% respectively). See docs §3 notes.
    extra_dmg_pct = stats.get("Extra DMG%", 0)
    dot_dmg_pct = stats.get("DoT%", 0)
    extra_dmg_per_hit = atk_scaling * (1 + extra_dmg_pct / 100.0)
    dot_dmg_per_hit = atk_scaling * (1 + dot_dmg_pct / 100.0)

    # ----- Blend damage by share -----
    # The character's damage is partitioned by type:
    #   extra_share  : Extra-typed damage (always ATK formula)
    #   dot_share    : DoT-typed damage   (always ATK formula)
    #   normal_share : everything else (split between ATK and DEF
    #                  formulas via def_split slider)
    # Shares sum to 1.0. If extra + dot > 1, normal_share clamps to 0.
    normal_share = max(0.0, 1.0 - sp["extra_share"] - sp["dot_share"])
    damage_score = (
        normal_share * (1.0 - sp["def_split"]) * atk_scaling
        + normal_share * sp["def_split"] * def_scaling
        + sp["extra_share"] * extra_dmg_per_hit
        + sp["dot_share"] * dot_dmg_per_hit
    )

    # ----- Shield/heal score -----
    # See docs §4.1. Shield_Heal_DEF differs from Final DEF only in
    # having Partner_FLAT_DEF outside the inner multiplier. No card
    # multiplier here (see the card-multiplier comment above).
    base_def_raw = stats.get("_base_def_for_shield", 0)
    shield_heal_def = stats.get("_shield_heal_def", 0)
    shield_heal_score = (base_def_raw + shield_heal_def) / 2.0 * 0.3

    # ----- Normalize the damage term -----
    # Divide the damage portion by the "buff baseline" (the damage card
    # multiplier without the conditional set terms) so the D component
    # is comparable across characters WITHOUT disturbing ranking: the
    # baseline is a per-run constant, so within-list order and ratios
    # are preserved exactly, and dividing out the user's external-buff
    # assumptions means two characters with different Avg Card DMG% /
    # buff settings compare on build quality alone. The shield/heal (S)
    # term is NOT divided -- buffs don't apply to it, so there's
    # nothing to divide out.
    baseline = sp["buff_baseline"]
    if baseline <= 0:
        baseline = 1.0
    damage_norm = damage_score / baseline
    return (damage_norm, shield_heal_score)


def trim_blend(components: tuple, sp: dict, gref: dict) -> float:
    """In-flight trim score: percent-normalized blend of (D, S) against
    the per-run GREEDY references. A per-run constant divisor pair, so
    it's safe for the parallel/sequential trim and the deterministic
    tie-break. NOT the displayed score -- see optimizer.optimize's
    post-merge re-blend against the run's true max-D / max-S.

    heal_share = 0 -> pure damage (D/D_ref); heal_share = 1 -> pure
    shield/heal (S/S_ref); in between, weighted blend.
    """
    d, s = components
    d_ref = gref["D"]
    s_ref = gref["S"]
    h = sp["heal_share"]
    return (1.0 - h) * (d / d_ref) + h * (s / s_ref)


def build_greedy_refs(slot_candidates: dict, char_static: dict,
                      set_effect_shares: dict, score_pre: dict,
                      attribute: str) -> dict:
    """Build the per-run GREEDY trim references {"D": float, "S": float}.

    Takes the top candidate in each slot (the lists arrive pre-sorted by
    the character's preset weights / gear score in optimize()), forms
    that single greedy combo, and reads its (D, S) components. These
    become the divisors in trim_blend -- a per-run constant pair, which
    is what keeps the in-flight trim and the deterministic tie-break
    parallel-safe (every worker divides by the same two numbers).

    The greedy refs only gate TRIMMING, never the displayed score (the
    parent re-blends survivors against the run's true max-D / max-S).
    So a ref that undershoots the true max just means the trim blend is
    slightly miscalibrated on that axis -- harmless given the trim keeps
    max_results * 10 headroom. Both refs are floored at a small epsilon
    so a degenerate all-zero slot list (or a pure-support build with no
    damage) can't divide by zero; if a ref floors, that term is
    effectively un-normalized for trimming only.

    Returns {"D": d_ref, "S": s_ref}. Called once per run, parent-side.
    """
    EPS = 1e-9
    greedy_combo = []
    for slot_num in SLOT_ORDER:
        cands = slot_candidates.get(slot_num) or []
        if not cands:
            # No candidate in a slot means the run returns empty before
            # trimming ever happens; refs are irrelevant, return safe
            # non-zero divisors.
            return {"D": 1.0, "S": 1.0}
        greedy_combo.append(cands[0])

    stats = compute_build_stats(
        greedy_combo, char_static, set_effect_shares=set_effect_shares
    )
    d, s = compute_score_components(greedy_combo, stats, score_pre, attribute)
    return {"D": max(d, EPS), "S": max(s, EPS)}


def display_blend(d: float, s: float, sp: dict, d_ref: float,
                  s_ref: float) -> float:
    """The un-rescaled display blend for one result against the run's
    true max-D / max-S references: (1-h)*D/D_ref + h*S/S_ref. optimize()
    applies this to every surviving result then divides the whole column
    by the top result's value (x100) so the top row reads 100 at any
    slider position (order-preserving). Refs are floored by the caller.
    """
    h = sp["heal_share"]
    return (1.0 - h) * (d / d_ref) + h * (s / s_ref)


def compute_score(gear: list, stats: dict, sp: dict, attribute: str) -> float:
    """Scalar optimizer score for callers OUTSIDE optimize() -- the
    Optimizer tab's refresh_after_load recompute and any other
    GearOptimizer client that wants a single comparable number without
    the reference machinery. Returns (1-h)*D + h*S with D already
    normalized by the buff baseline and S the raw shield/heal term.
    Within a single character/settings context the ranking matches the
    trim blend; only the absolute magnitude differs (no /ref, no
    top-row rescale). optimize() itself uses compute_score_components +
    trim_blend and re-blends for display.

    See docs/game_formulas.md §3, §4, §5, §8.
    """
    d, s = compute_score_components(gear, stats, sp, attribute)
    return d * (1.0 - sp["heal_share"]) + s * sp["heal_share"]


def evaluate_combo(combo, ctx: dict):
    """Evaluate one candidate 6-piece combo against a run context.

    Returns (status, score, stats):
      - (COMBO_DUPLICATE, 0.0, None) same fragment twice
      - (COMBO_SET_FAIL,  0.0, None) wildcard count over max_flex_slots
      - (COMBO_HAL_FAIL,  0.0, None) failed a Have-at-least minimum
      - (COMBO_OK,   trim_score, stats) scored build

    On COMBO_OK, `score` is trim_blend(D, S) against the per-run GREEDY
    refs -- the scalar that gates in-flight trimming and the
    deterministic tie-break, so the result-tuple shape (gear, score,
    stats) and every sort/merge/remap path are unchanged. The raw (D,
    S) components ride along inside `stats` under the "_D" / "_S" keys,
    so the parent can re-blend against the run's true max-D / max-S for
    display without re-deriving per-build math. See the module
    docstring.

    Pure given (combo, ctx). The caller owns all counter bookkeeping so
    single-thread and parallel paths count identically (a duplicate
    combo increments total_combinations only; SET_FAIL likewise;
    HAL_FAIL additionally counted in passed_set_reqs; OK counted in
    both passed counters).
    """
    piece_ids = [p.id for p in combo]
    if len(piece_ids) != len(set(piece_ids)):
        return (COMBO_DUPLICATE, 0.0, None)

    # Unified set-combo rule (see count_locked_slots for the shape
    # taxonomy): count slots locked into chosen-set bonuses; the build
    # is valid if its wildcard count fits under max_flex_slots.
    locked = count_locked_slots(combo, ctx["sets_selected"])
    if (6 - locked) > ctx["max_flex_slots"]:
        return (COMBO_SET_FAIL, 0.0, None)

    # Compute build stats. Per-set effect shares let conditional Crit
    # DMG / Crit Rate sets contribute to Final stats at each set's own
    # weighting; conditional DMG multi / DMG add sets affect the
    # damage card multiplier separately inside the score functions.
    stats = compute_build_stats(
        list(combo), ctx["char_static"],
        set_effect_shares=ctx["set_effect_shares"],
    )

    # Hard constraint: "Have at least this much". Builds that fail
    # any minimum are excluded entirely (not just docked points).
    if not meets_have_at_least(stats, ctx["hal"]):
        return (COMBO_HAL_FAIL, 0.0, None)

    components = compute_score_components(
        list(combo), stats, ctx["score_pre"], ctx["attribute"]
    )
    trim_score = trim_blend(components, ctx["score_pre"], ctx["gref"])
    # Carry the raw components for the parent-side display re-blend.
    stats["_D"], stats["_S"] = components
    return (COMBO_OK, trim_score, stats)


def result_sort_key(entry):
    """Deterministic sort key for result tuples (gear, score, stats):
    score descending, then the tuple of fragment ids ascending as a
    tie-break. Equal-score builds are interchangeable quality-wise, but
    the explicit tie-break makes single-thread and parallel runs (any
    worker count) produce byte-identical result orderings -- which is
    what makes parity testable. Used by optimize()'s in-flight trim and
    final sort; the parallel merge must use the same key.
    """
    gear, score, _stats = entry
    return (-score, tuple(p.id for p in gear))
