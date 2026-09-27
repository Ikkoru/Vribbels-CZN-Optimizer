"""A fragment's average Potential is the mean of every way its remaining
level-ups can land.

`compute_fragment_potential_mean` is a closed form: by linearity, each
level-up adds its expected roll. It has three ways to be wrong without
a sound, each showing as a plausible number:

1. **An upgrade into an existing substat** must average over the four
   substats alike, each at its roll's midpoint.
2. **A level-up that adds a substat** draws it from the stats the
   fragment has not got and cannot have -- never its own main -- and
   later upgrades can then land on it too.
3. **Nothing left to roll** is the fragment's current GS.

Held against an enumeration of every outcome, with each roll a coin
between the stat's minimum and maximum: the same mean as the game's
even grid between them, which is all the closed form assumes of it.
And the Upgraded line shows the average only when asked, and never for
a fragment with nothing left to roll.
"""

import collections
from itertools import product

from ._harness import add_source_to_path

NAME = "average Potential is the mean of every outcome"


def _fragment(level, substats, main=("S_ATK_INC_ADD_OUT", 60)):
    from models.memory_fragment import MemoryFragment
    stats = [{"slot": 0, "type": 0, "stat": main[0], "value": main[1]}]
    for n, (raw, value) in enumerate(substats, 1):
        stats.append({"slot": n, "type": 1, "stat": raw, "value": value})
    return MemoryFragment.from_json({"id": 1, "res_id": 1014101,
                                     "level": level, "stat_list": stats})


def _enumerated(fragment, weights):
    """The exact expected raw score, every outcome enumerated."""
    from game_data import STATS
    from models.memory_fragment import _raw_substat_score

    def rolls(raw_name):
        info = STATS[raw_name]
        weight = weights.get(info[0], 1.0)
        return [value / info[3] * weight * 10 for value in (info[3], info[4])]

    base = _raw_substat_score(fragment, weights)
    remaining = 5 - fragment.level
    present = {s.name for s in fragment.substats}
    held = [s.raw_name for s in fragment.substats]
    main = fragment.main_stat.name
    pool = [raw for raw, info in STATS.items()
            if info[3] > 0 and info[0] not in present and info[0] != main]
    to_add = min(4 - len(held), remaining)
    total, weight_sum = 0.0, 0.0
    for extra in (product(pool, repeat=to_add) if to_add else [()]):
        if len(set(extra)) < len(extra):
            continue
        slots = held + list(extra)
        per_add = [rolls(raw) for raw in extra]
        per_up = [gain for raw in slots for gain in rolls(raw)]
        up_count = remaining - to_add
        added = collections.Counter()
        for choice in product(*[range(2)] * to_add):
            added[sum(per_add[i][c] for i, c in enumerate(choice))] += 1
        ups = collections.Counter()
        for choice in product(per_up, repeat=up_count):
            ups[sum(choice)] += 1
        mean = (sum(a * k for a, k in added.items()) / sum(added.values())
                + sum(u * k for u, k in ups.items()) / sum(ups.values()))
        total += mean
        weight_sum += 1
    return base + total / weight_sum


def run():
    add_source_to_path()
    from models.memory_fragment import (
        compute_fragment_potential, compute_fragment_potential_mean,
        compute_gs_bounds, normalize_gs)
    failures = []
    weights = {"ATK%": 1.0, "Crit Rate": 0.9, "Crit DMG": 0.8, "DoT%": 0.3,
               "Flat DEF": 0.0, "Flat HP": 0.1}
    cases = (
        ("a +1 with four substats", _fragment(1, [
            ("S_DOT_ATK_DMG_RATE_INC_ADD", 2.8), ("S_DEF_INC_ADD_OUT", 5),
            ("S_ATK_INC_RATE_OUT", 1.0), ("S_HP_INC_ADD_OUT", 12)])),
        ("a +0 with three, which adds its fourth", _fragment(0, [
            ("S_CRI_INC_ADD", 1.6), ("S_DEF_INC_ADD_OUT", 4),
            ("S_HP_INC_RATE_OUT", 1.1)])),
    )
    for what, fragment in cases:
        bounds = compute_gs_bounds(weights,
                                   exclude_stat=fragment.main_stat.name)
        want = normalize_gs(_enumerated(fragment, weights), bounds)
        got = compute_fragment_potential_mean(fragment, weights, bounds)
        if abs(got - want) > 0.05:
            failures.append(
                f"{what}: the average Potential reads {got}, where every "
                f"outcome enumerated averages {want}. The Upgraded line "
                f"would show a mean the game does not have.")
        low, high = compute_fragment_potential(fragment, weights, bounds)
        if not low <= got <= high:
            failures.append(f"{what}: the average {got} is outside the "
                            f"range {low}-{high} it averages.")

    done = _fragment(5, [("S_CRI_INC_ADD", 1.6), ("S_DEF_INC_ADD_OUT", 4),
                         ("S_HP_INC_RATE_OUT", 1.1),
                         ("S_ATK_INC_RATE_OUT", 1.2)])
    bounds = compute_gs_bounds(weights, exclude_stat=done.main_stat.name)
    if (compute_fragment_potential_mean(done, weights, bounds)
            != compute_fragment_potential(done, weights, bounds)[0]):
        failures.append("a fragment with nothing left to roll averages "
                        "somewhere other than its own GS.")

    from czn_optimizer_gui import OptimizerGUI
    phrase = OptimizerGUI._potentials_phrase
    ranged = [(21.0, 80.0, "Rei")]
    if phrase(ranged) != "Highest Potential: 21-80 Rei":
        failures.append(f"the Upgraded line without averages reads "
                        f"{phrase(ranged)!r}.")
    if phrase(ranged, {"Rei": 41.3}) != \
            "Highest Potential: 21-80 (avg 41) Rei":
        failures.append(f"the Upgraded line with an average reads "
                        f"{phrase(ranged, {'Rei': 41.3})!r}, not "
                        f"'Highest Potential: 21-80 (avg 41) Rei'.")
    if "avg" in phrase([(55.0, 55.0, "Rei")], {"Rei": 55.0}):
        failures.append("a fragment with nothing left to roll shows an "
                        "average beside its one number.")
    return failures
