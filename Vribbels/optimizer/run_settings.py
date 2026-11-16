"""The settings an Optimizer run takes for one combatant, assembled from
what is saved: the combatant's own Optimizer settings, the global
candidacy filters, Exclude Combatant's MFs, and the combatant's preset.

The Optimizer tab runs with this, and so does anything that must find
the build the Optimizer tab would -- the Substat Readjustment tab's
Build Score among them. No Tk on this module's import path.
"""

from game_data import CHARACTERS, SETS

# Every force-main flag the per-character settings hold.
FORCE_MAIN_KEYS = ("slot4_hp", "slot5_hp", "slot6_hp", "slot6_ego")
# How many fragments per slot survive the pre-filter, by per cent of
# that slot's candidates (with the 10-fragment floor `get_gear_by_slot`
# keeps). Internal: not user-facing.
TOP_PERCENT = 20
MAX_RESULTS = 100


def resolve_res_id(optimizer, hero_name):
    """`hero_name`'s res_id, or None if unknown.

    Resolution order:
      1. optimizer.character_info[name].res_id  -- live captured data
      2. the CHARACTERS key whose entry has this name -- every
         combatant the game has, owned or not

    The second is the only one a combatant not obtained has: its
    settings, shipped defaults included, and its Potential 7 are all
    looked up by it. An entry carries no res_id field of its own; the
    key is the res_id.
    """
    if not hero_name:
        return None
    info = optimizer.character_info.get(hero_name)
    if info is not None and getattr(info, "res_id", None):
        try:
            return int(info.res_id)
        except (TypeError, ValueError):
            pass
    for rid, data in CHARACTERS.items():
        if isinstance(data, dict) and data.get("name") == hero_name:
            try:
                return int(rid)
            except (TypeError, ValueError):
                return None
    return None


def exclude_order(saved, roster, res_id_of):
    """Order Mode's order over `roster`: the combatants `saved` places,
    in its order, then every one it does not, by name -- so a new
    combatant ranks last, its MFs free for everyone above it.

    `saved` is res_id strings; `res_id_of` maps a name to its res_id."""
    by_id = {}
    for name in roster:
        rid = res_id_of(name)
        if rid is not None:
            by_id.setdefault(str(rid), name)
    placed = []
    for rid in saved:
        name = by_id.get(str(rid))
        if name is not None and name not in placed:
            placed.append(name)
    return placed + sorted(name for name in roster if name not in placed)


def excluded_by_order(order, current):
    """Whose MFs Order Mode keeps from `current`: everyone before it. A
    combatant the order does not hold ranks after all of them."""
    return list(order[:order.index(current)]) if current in order \
        else list(order)


def weights_for(character_presets, presets, char_name):
    """The scoring weights for `char_name`.

    Resolution order (matches the Combatants tab):
      1. The combatant's assigned preset (`CharacterPresetManager`). An
         assigned name PresetManager no longer has falls through.
      2. The active preset (`PresetManager.selected_preset`).
      3. An empty dict -- the GS helpers read that as every weight 1.0.

    Returns a dict[stat_name, weight] (padded by PresetManager.get_preset
    to cover SUPPORTED_STATS), or an empty dict for the default.
    """
    if presets is None:
        return {}
    if character_presets is not None and char_name:
        assigned = character_presets.get_preset_for(char_name)
        if assigned:
            weights = presets.get_preset(assigned)
            if weights is not None:
                return weights
    active = presets.selected_preset
    if active:
        weights = presets.get_preset(active)
        if weights is not None:
            return weights
    return {}


def run_settings(optimizer, opt_settings, char_name, res_id, *,
                 order_mode, min_gear_level, ignore_offelement, weights):
    """The settings dict `GearOptimizer.optimize` takes for `char_name`.

    Combines:
      * Filter fields used by `get_gear_by_slot` (main-stat filters per
        slot, top_percent, excluded_heroes, the global candidacy
        filters).
      * Set-combo fields for the locked-count rule.
      * Scoring fields used by `calculate_build_stats` and
        `_compute_optimizer_score` (Extra%, DoT%, ATK/DEF split,
        shield/heal weight, per-set effect shares, avg buff fields,
        level stepper, element override, have-at-least minimums).

    `opt_settings` is the OptimizerSettingsManager, None for the
    defaults; `order_mode` whether Exclude Combatant's MFs runs by order;
    `min_gear_level` and `ignore_offelement` the global filters;
    `weights` the combatant's preset (`weights_for`).

    See docs/game_formulas.md §8 for the formula consumers of each field.
    """
    if opt_settings is None or res_id is None:
        s = {
            "force_main": dict.fromkeys(FORCE_MAIN_KEYS, False),
            "sets_selected": [],
            "max_flex_slots": 6,
            "have_at_least": {},
        }
    else:
        s = opt_settings.get_character_data(res_id)

    # Force-main flags -> per-slot main stat filter lists (None = "no filter").
    slot4_filter = ["HP%"] if s["force_main"].get("slot4_hp") else None
    slot5_filter = ["HP%"] if s["force_main"].get("slot5_hp") else None
    slot6_filter = []
    if s["force_main"].get("slot6_hp"):
        slot6_filter.append("HP%")
    if s["force_main"].get("slot6_ego"):
        slot6_filter.append("Ego")
    slot6_filter = slot6_filter or None

    # Selected sets -> split into 4-piece and 2-piece lists for the
    # optimizer's legacy fields (kept for back-compat; the locked-count
    # rule uses `sets_selected` directly).
    selected_4pc = []
    selected_2pc = []
    for sid in s.get("sets_selected", []):
        sinfo = SETS.get(sid)
        if sinfo is None:
            continue
        if sinfo.get("pieces") == 4:
            selected_4pc.append(sid)
        elif sinfo.get("pieces") == 2:
            selected_2pc.append(sid)

    def res_id_of(name):
        return resolve_res_id(optimizer, name)

    # Excluded characters' gear: res_ids -> hero names. In Order Mode,
    # everyone before `char_name` in the order.
    excluded_heroes = []
    excluded_res_ids = set(opt_settings.get_excluded_gear_chars()
                           if opt_settings else [])
    if order_mode:
        roster = sorted(set(optimizer.characters)
                        | set(optimizer.character_info))
        order = exclude_order(
            opt_settings.get_exclude_order() if opt_settings else [],
            roster, res_id_of)
        kept = excluded_by_order(order, char_name)
        excluded_res_ids = {str(rid) for rid in map(res_id_of, kept)
                            if rid is not None}
    # Never the combatant's own gear: their pieces are free to re-equip.
    current = str(res_id) if res_id else None
    for hero_name in optimizer.characters:
        rid = res_id_of(hero_name)
        if rid is None:
            continue
        if str(rid) == current:
            continue
        if str(rid) in excluded_res_ids:
            excluded_heroes.append(hero_name)

    return {
        # ----- Legacy filter fields (consumed by get_gear_by_slot + optimize) -----
        "four_piece_sets": selected_4pc,
        "two_piece_sets": selected_2pc,
        "main_stat_4": slot4_filter,
        "main_stat_5": slot5_filter,
        "main_stat_6": slot6_filter,
        "top_percent": TOP_PERCENT,
        "include_equipped": True,    # always include; exclude list is the gate
        "excluded_heroes": excluded_heroes,
        "max_results": MAX_RESULTS,
        # GLOBAL minimum-MF-level candidacy filter. 0 = off.
        "min_gear_level": min_gear_level,
        # GLOBAL off-element Slot V candidacy filter: drops Slot V
        # candidates whose main stat is an element DMG% not matching
        # the combatant's element; ATK%/HP% mains always pass.
        "ignore_offelement_slot5": ignore_offelement,
        # ----- Set-combo fields (consumed by optimize's locked-count rule) -----
        "sets_selected": list(s.get("sets_selected", [])),
        "max_flex_slots": int(s.get("max_flex_slots", 6)),
        # ----- Weights for the slot pre-filter sort -----
        # The optimizer ranks fragments per slot by their score under
        # these weights before applying the Top filter. When None or
        # empty, it falls back to fragment.gear_score (the active
        # preset's cached value).
        "slot_filter_weights": weights or None,
        # ----- Scoring fields (consumed by calculate_build_stats + _compute_optimizer_score) -----
        "optimize_for_level": s.get("optimize_for_level", 62),
        "extra_pct": s.get("extra_pct", 0),
        "dot_pct": s.get("dot_pct", 0),
        "fracture_pct": s.get("fracture_pct", 0),
        "atk_def_split": s.get("atk_def_split", 0),
        "shielding_healing_weight": s.get("shielding_healing_weight", 0),
        "set_effect_pcts": dict(s.get("set_effect_pcts", {}) or {}),
        "avg_card_dmg_pct": s.get("avg_card_dmg_pct", 100),
        "avg_mult_buff_pct": s.get("avg_mult_buff_pct", 0),
        "avg_add_buff_pct": s.get("avg_add_buff_pct", 0),
        "element_override": s.get("element_override"),
        "have_at_least": s.get("have_at_least", {}),
    }


def saved_run_settings(optimizer, context, char_name):
    """`run_settings` for `char_name` from what is saved alone, as the
    Optimizer tab would run it with that combatant selected. `context`
    carries the managers (`AppContext`); a missing one is its default."""
    manager = getattr(context, "settings_manager", None)
    opt_settings = getattr(context, "optimizer_settings_manager", None)
    try:
        level = max(0, min(5, int(manager.get("optimizer_min_gear_level", 4))
                           if manager is not None else 4))
    except (TypeError, ValueError):
        level = 0
    offelement = bool(manager.get("optimizer_ignore_offelement", True)) \
        if manager is not None else True
    return run_settings(
        optimizer, opt_settings, char_name,
        resolve_res_id(optimizer, char_name),
        order_mode=bool(opt_settings and opt_settings.get_exclude_order_mode()),
        min_gear_level=level, ignore_offelement=offelement,
        weights=weights_for(getattr(context, "character_preset_manager", None),
                            getattr(context, "preset_manager", None),
                            char_name))
