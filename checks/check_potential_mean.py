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
And the Upgraded line shows the average only when asked, between the
ends -- `21-41-80` -- and never for a fragment with nothing left to
roll.

The likely band (`compute_fragment_potential_band`) needs the whole
distribution, so it is held against an enumeration over every point of
every roll's grid: its ends within the rounding its bins allow.
"""

import collections
from itertools import combinations, product

from ._harness import add_source_to_path

NAME = "average Potential is the mean of every outcome"


def _fragment(level, substats, main=("S_ATK_INC_ADD_OUT", 60),
              res_id=1014101):
    """A fragment of `res_id`'s rarity: its fourth digit, 4 Legendary."""
    from models.memory_fragment import MemoryFragment
    stats = [{"slot": 0, "type": 0, "stat": main[0], "value": main[1]}]
    for n, (raw, value) in enumerate(substats, 1):
        stats.append({"slot": n, "type": 1, "stat": raw, "value": value})
    return MemoryFragment.from_json({"id": 1, "res_id": res_id,
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


def _band_enumerated(fragment, weights, bounds, tail=0.1):
    """The exact (low, high) band: every added stat, every substat an
    upgrade can land on and every point of every roll's grid, weighed
    by its chance. GS unrounded and unclamped."""
    from game_data import STATS
    from game_data.constants import MAX_LEVEL_PER_RARITY
    from models.memory_fragment import _raw_substat_score

    def grid(raw_name):
        name, _short, is_pct, max_roll, min_roll = STATS[raw_name]
        step = 0.1 if is_pct else 1.0
        count = int(round((max_roll - min_roll) / step)) + 1
        return [weights.get(name, 1.0) * (min_roll + i * step) / max_roll * 10
                for i in range(count)]

    def spread(options, times):
        """{sum: chance} of `times` draws, each any of `options` alike."""
        out = {0.0: 1.0}
        for _ in range(times):
            nxt = collections.defaultdict(float)
            for total, chance in out.items():
                for value in options:
                    nxt[round(total + value, 9)] += chance / len(options)
            out = nxt
        return out

    base = _raw_substat_score(fragment, weights)
    remaining = MAX_LEVEL_PER_RARITY[fragment.rarity_num] - fragment.level
    present = {s.name for s in fragment.substats}
    held = [s.raw_name for s in fragment.substats]
    pool = [raw for raw, info in STATS.items()
            if info[3] > 0 and info[0] not in present
            and info[0] != fragment.main_stat.name]
    to_add = min(4 - len(held), remaining)
    outcomes = collections.defaultdict(float)
    choices = list(combinations(pool, to_add)) if to_add else [()]
    for extra in choices:
        first = {0.0: 1.0}
        for raw in extra:
            # Summed, not assigned: a stat weighed 0 rolls the same 0
            # at every point of its grid.
            nxt = collections.defaultdict(float)
            for total, chance in first.items():
                for value in grid(raw):
                    nxt[round(total + value, 9)] += chance / len(grid(raw))
            first = nxt
        slots = held + list(extra)
        # An upgrade: a substat alike, then a point of its grid alike --
        # each point weighed by its substat's share.
        per_up = collections.defaultdict(float)
        for raw in slots:
            for value in grid(raw):
                per_up[value] += 1.0 / (len(slots) * len(grid(raw)))
        ups = {0.0: 1.0}
        for _ in range(remaining - to_add):
            nxt = collections.defaultdict(float)
            for total, chance in ups.items():
                for value, p in per_up.items():
                    nxt[round(total + value, 9)] += chance * p
            ups = nxt
        for a, pa in first.items():
            for u, pu in ups.items():
                outcomes[a + u] += pa * pu / len(choices)
    low_raw, high_raw = bounds
    ends, total = [], 0.0
    wanted = [tail, 1.0 - tail]
    for value in sorted(outcomes):
        total += outcomes[value]
        while wanted and total >= wanted[0] - 1e-9:
            ends.append((base + value - low_raw) / (high_raw - low_raw) * 100)
            wanted.pop(0)
    return tuple(ends)


def run():
    add_source_to_path()
    from models.memory_fragment import (
        _DIST_BIN, compute_fragment_potential,
        compute_fragment_potential_band, compute_fragment_potential_mean,
        compute_gs_bounds, normalize_gs)
    failures = []
    weights = {"ATK%": 1.0, "CRate": 0.9, "CDmg": 0.8, "DoT%": 0.3,
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

    # The band against its enumeration. Each roll is binned to within
    # half a bin, so a sum of `rolls` rolls to within that many halves,
    # and the display's own rounding to a tenth on top.
    band_cases = (
        ("a +3 with four substats", _fragment(3, [
            ("S_DOT_ATK_DMG_RATE_INC_ADD", 2.8), ("S_DEF_INC_ADD_OUT", 5),
            ("S_ATK_INC_RATE_OUT", 1.0), ("S_CRI_DMG_RATE_INC_ADD", 3.2)]),
         2),
        ("a +3 with three, which adds its fourth", _fragment(3, [
            ("S_CRI_INC_ADD", 1.6), ("S_DEF_INC_ADD_OUT", 4),
            ("S_HP_INC_RATE_OUT", 1.1)]), 2),
        ("a +2 with three, which adds its fourth and rolls twice more",
         _fragment(2, [("S_CRI_INC_ADD", 1.6), ("S_DEF_INC_ADD_OUT", 4),
                       ("S_HP_INC_RATE_OUT", 1.1)]), 3),
        ("a Rare +1 with two, which adds two", _fragment(1, [
            ("S_CRI_INC_ADD", 1.6), ("S_HP_INC_RATE_OUT", 1.1)],
            res_id=1013101), 3),
    )
    for what, fragment, rolls in band_cases:
        bounds = compute_gs_bounds(weights,
                                   exclude_stat=fragment.main_stat.name)
        want = _band_enumerated(fragment, weights, bounds)
        got = compute_fragment_potential_band(fragment, weights, bounds)
        slack = rolls * _DIST_BIN / 2 + 0.05
        if any(abs(g - w) > slack for g, w in zip(got, want)):
            failures.append(
                f"{what}: the likely band reads {got[0]}-{got[1]}, where "
                f"every outcome enumerated puts a tenth of them below "
                f"{want[0]:.2f} and a tenth above {want[1]:.2f}. The "
                f"Upgraded line would show a band the game does not "
                f"have.")
        low, high = compute_fragment_potential(fragment, weights, bounds)
        if not low <= got[0] <= got[1] <= high:
            failures.append(f"{what}: the likely band {got} is not inside "
                            f"the range {low}-{high}.")

    done = _fragment(5, [("S_CRI_INC_ADD", 1.6), ("S_DEF_INC_ADD_OUT", 4),
                         ("S_HP_INC_RATE_OUT", 1.1),
                         ("S_ATK_INC_RATE_OUT", 1.2)])
    bounds = compute_gs_bounds(weights, exclude_stat=done.main_stat.name)
    if (compute_fragment_potential_mean(done, weights, bounds)
            != compute_fragment_potential(done, weights, bounds)[0]):
        failures.append("a fragment with nothing left to roll averages "
                        "somewhere other than its own GS.")
    if (compute_fragment_potential_band(done, weights, bounds)
            != compute_fragment_potential(done, weights, bounds)):
        failures.append("a fragment with nothing left to roll has a likely "
                        "band other than its own GS at both ends.")

    from czn_optimizer_gui import OptimizerGUI
    phrase = OptimizerGUI._potentials_phrase
    ranged = [(21.0, 80.0, "Rei")]
    if phrase(ranged) != "Highest Potential: 21-80 Rei":
        failures.append(f"the Upgraded line without averages reads "
                        f"{phrase(ranged)!r}.")
    if phrase(ranged, {"Rei": 41.3}) != "Highest Potential: 21-41-80 Rei":
        failures.append(f"the Upgraded line with an average reads "
                        f"{phrase(ranged, {'Rei': 41.3})!r}, not "
                        f"'Highest Potential: 21-41-80 Rei'.")
    if "avg" in phrase([(55.0, 55.0, "Rei")], {"Rei": 55.0}):
        failures.append("a fragment with nothing left to roll shows an "
                        "average beside its one number.")
    return failures
