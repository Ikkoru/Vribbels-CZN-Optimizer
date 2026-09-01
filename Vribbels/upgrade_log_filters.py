"""Which presets a fragment is worth scoring against.

The Capture tab's Upgrade Log Settings decide this for the `Upgraded`
log line: a Log Presets checklist saying which presets to consider at
all, and four mismatch filters dropping a preset whose combatants cannot
use the fragment's MAIN stat.

The Memory Fragments tab's Highest GS and Highest Potential columns ask
the same question, and the answer has to be the same one -- a fragment
called mediocre in the log and promising in the list is worse than
either verdict alone. So the decision lives here rather than in either
tab, and both call it.

Everything takes its managers as arguments. Nothing here reads a widget
or a tab, which is what lets the columns use it without reaching into
the Capture tab's state.
"""

from game_data.characters import get_character
from optimizer.optimizer import SLOT5_ELEMENT_MAINS


# The four mismatch filters, by their `settings.json` keys. Order is the
# Capture tab's reading order; nothing depends on it.
UPGRADE_LOG_FILTERS = (
    "upgrade_log_ignore_atkdef_mismatch",
    "upgrade_log_ignore_element_mismatch",
    "upgrade_log_ignore_dps_hp",
    "upgrade_log_ignore_dps_ego",
)

# A combatant whose Shielding & Healing weight is at or below this is
# treated as a damage dealer, and rejects the mains that buy neither
# damage nor a useful amount of anything else.
DPS_HEAL_WEIGHT = 45

# The ATK/DEF Split bands. Below the first is ATK-scaling and rejects a
# DEF% main; above the second is DEF-scaling and rejects an ATK% one.
# Between them is a hybrid, which accepts both.
ATK_SCALING_BELOW = 33
DEF_SCALING_ABOVE = 67


def filter_flags(settings_manager) -> dict:
    """Every mismatch filter's state, keyed by its settings key.

    A missing setting, or no manager at all, reads as ON -- the filters
    ship on, and a fragment hidden from a preset is recoverable where a
    misleading score is not.
    """
    if settings_manager is None:
        return {key: True for key in UPGRADE_LOG_FILTERS}
    return {key: bool(settings_manager.get(key, True))
            for key in UPGRADE_LOG_FILTERS}


def _combatant_setting(osm, res_id, field: str) -> int:
    """One of a combatant's 0-100 Important Settings sliders as an int.

    Anything unreadable reads as 0 -- the same value a combatant with no
    stored entry gets.
    """
    if osm is None:
        return 0
    try:
        return int(osm.get(res_id, field) or 0)
    except (TypeError, ValueError):
        return 0


def combatant_accepts_main(res_id, fragment, flags: dict, osm) -> bool:
    """Whether `fragment` is plausibly for this combatant, judged only by
    its MAIN stat. Every test is opt-out through `flags`.

    Element: an element DMG% main that is not the combatant's element
    contributes nothing to their damage. A combatant whose element
    cannot be resolved -- unknown character, no Element override -- is
    never filtered: with no element, no element main is more off-element
    than another. Matches the optimizer's off-element Slot V candidacy
    filter.

    ATK/DEF: read off the combatant's ATK/DEF Split, the share of their
    damage that scales off DEF. The test is on the MAIN STAT rather than
    the slot, so it covers ATK% in slots IV, V and VI and DEF% in slot
    VI.

    DPS: a damage dealer rejects an HP% main (slots IV, V and VI) and an
    Ego main (slot VI).
    """
    main = fragment.main_stat.name if fragment.main_stat else None
    if not main:
        return True

    if flags.get("upgrade_log_ignore_element_mismatch") and \
            main in SLOT5_ELEMENT_MAINS:
        try:
            attribute = get_character(int(res_id)).get("attribute", "Unknown")
        except (TypeError, ValueError, AttributeError):
            attribute = "Unknown"
        if attribute == "Unknown":
            attribute = (osm.get(res_id, "element_override")
                         if osm is not None else None) or ""
        if attribute and main != f"{attribute} DMG%":
            return False

    if flags.get("upgrade_log_ignore_atkdef_mismatch") and \
            main in ("ATK%", "DEF%") and osm is not None:
        def_split = _combatant_setting(osm, res_id, "atk_def_split")
        if main == "DEF%" and def_split <= ATK_SCALING_BELOW:
            return False
        if main == "ATK%" and def_split >= DEF_SCALING_ABOVE:
            return False

    dps_filtered_mains = {
        "HP%": flags.get("upgrade_log_ignore_dps_hp"),
        "Ego": flags.get("upgrade_log_ignore_dps_ego"),
    }
    if dps_filtered_mains.get(main) and osm is not None:
        heal_weight = _combatant_setting(
            osm, res_id, "shielding_healing_weight")
        if heal_weight <= DPS_HEAL_WEIGHT:
            return False

    return True


def selected_log_presets(character_preset_manager, preset_manager,
                         log_presets_manager) -> dict:
    """Preset name -> the res_ids assigned to it that are SELECTED.

    Keyed by preset because that is the unit both readers display; the
    res_ids come along so the mismatch filters can ask who actually
    wants the fragment.

    A combatant absent from `log_presets.json` counts as selected, which
    is the default a new assignment gets. Assignments to since-deleted
    presets are skipped.
    """
    cpm, pm = character_preset_manager, preset_manager
    if cpm is None or pm is None or cpm.is_corrupted():
        return {}
    by_preset: dict = {}
    for rid, preset in cpm.assignments_by_id.items():
        if not preset or not pm.has_preset(preset):
            continue
        if log_presets_manager is None or log_presets_manager.is_selected(rid):
            by_preset.setdefault(preset, []).append(rid)
    return by_preset


def presets_for_fragment(fragment, selected: dict, flags: dict, osm):
    """The preset names from `selected` that `fragment` survives.

    ANY rather than ALL: a preset shared by combatants of different
    elements or scaling stays as long as ONE of them wants the fragment.
    Dropping it because a second combatant would not use the fragment
    would hide it from the one who would.
    """
    if not any(flags.values()):
        return list(selected)
    return [name for name, rids in selected.items()
            if any(combatant_accepts_main(rid, fragment, flags, osm)
                   for rid in rids)]
