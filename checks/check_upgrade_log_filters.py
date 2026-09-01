"""The Upgrade Log Settings decide one thing, for two readers.

The Capture tab's `Upgraded` line and the Memory Fragments tab's Highest
GS / Highest Potential columns both ask which presets a fragment is
worth scoring against. **A fragment called mediocre in the log and
promising in the list is worse than either verdict alone**, so the
decision lives in `upgrade_log_filters` and both read it there.

What that leaves worth pinning is the decision itself, and its rules are
the kind that look arbitrary until they bite:

  * a preset stays if ANY of its combatants wants the fragment. ALL
    would drop a preset shared across elements from the one combatant
    who could use the piece.
  * every filter is opt-out, so all four off means no preset is dropped
    -- not "none survive".
  * the tests read the fragment's MAIN stat, so they are per fragment
    and cannot be hoisted out of a scoring loop.

No Tk and no managers: the module takes what it needs as arguments,
which is what let the columns use it at all.
"""

from ._harness import add_source_to_path

NAME = "upgrade log filters"


class _Stat:
    def __init__(self, name):
        self.name = name


class _Fragment:
    """As much of a fragment as the filters look at."""

    def __init__(self, main):
        self.main_stat = _Stat(main) if main else None


class _Settings:
    def __init__(self, values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class _PerCombatant:
    """An `optimizer_settings_manager`, as far as these tests reach."""

    def __init__(self, rows):
        self.rows = rows

    def get(self, res_id, field):
        return self.rows.get(str(res_id), {}).get(field)


def run():
    add_source_to_path()
    from upgrade_log_filters import (
        UPGRADE_LOG_FILTERS, combatant_accepts_main, filter_flags,
        presets_for_fragment,
    )

    failures = []
    all_on = {key: True for key in UPGRADE_LOG_FILTERS}
    all_off = {key: False for key in UPGRADE_LOG_FILTERS}

    # An ATK-scaling damage dealer and a DEF-scaling healer, so one
    # rejects what the other takes.
    osm = _PerCombatant({
        "1": {"atk_def_split": 0, "shielding_healing_weight": 0},
        "2": {"atk_def_split": 100, "shielding_healing_weight": 100},
    })

    def accepts(rid, main, flags=all_on):
        return combatant_accepts_main(rid, _Fragment(main), flags, osm)

    for rid, main, want, why in (
        (1, "DEF%", False, "an ATK-scaling combatant rejects a DEF% main"),
        (1, "ATK%", True, "and takes an ATK% one"),
        (2, "ATK%", False, "a DEF-scaling combatant rejects an ATK% main"),
        (2, "DEF%", True, "and takes a DEF% one"),
        (1, "HP%", False, "a damage dealer rejects an HP% main"),
        (2, "HP%", True, "a healer takes one"),
        (1, "Ego", False, "a damage dealer rejects an Ego main"),
        (1, None, True, "a fragment with no main stat is never filtered"),
    ):
        if accepts(rid, main) is not want:
            failures.append(f"combatant {rid} with a {main} main: "
                            f"expected {want} -- {why}")

    # Opt-out: every filter off drops nothing.
    for rid, main in ((1, "DEF%"), (1, "HP%"), (1, "Ego"), (2, "ATK%")):
        if not accepts(rid, main, all_off):
            failures.append(
                f"combatant {rid} rejects a {main} main with every filter "
                f"OFF. The filters are opt-out; off has to mean no test ran."
            )

    # ANY, not ALL: a preset shared by the two stays for both mains.
    shared = {"Shared": [1, 2], "Solo DPS": [1]}
    for main in ("ATK%", "DEF%"):
        names = presets_for_fragment(_Fragment(main), shared, all_on, osm)
        if "Shared" not in names:
            failures.append(
                f"a preset covering both combatants is dropped for a {main} "
                f"main. It stays if ANY of its combatants wants the "
                f"fragment -- ALL hides the piece from the one who does."
            )
    names = presets_for_fragment(_Fragment("DEF%"), shared, all_on, osm)
    if "Solo DPS" in names:
        failures.append(
            "a preset whose only combatant rejects the main is kept. That "
            "is the whole of what the filters do."
        )

    # Nothing selected is not the same as nothing surviving.
    if presets_for_fragment(_Fragment("ATK%"), {}, all_on, osm):
        failures.append("an empty selection produced preset names")
    every = presets_for_fragment(_Fragment("DEF%"), shared, all_off, osm)
    if sorted(every) != sorted(shared):
        failures.append(
            f"with every filter off the survivors are {sorted(every)}, not "
            f"every selected preset. Off must not narrow anything."
        )

    # A missing setting reads as ON, because the filters ship on.
    flags = filter_flags(_Settings({}))
    if not all(flags.values()):
        failures.append(
            f"an empty settings file reads as {flags}. Every filter ships "
            f"on, and a fragment hidden from a preset is recoverable where "
            f"a misleading score is not."
        )
    if filter_flags(None) != all_on:
        failures.append("no settings manager at all has to read as all on")

    return failures
