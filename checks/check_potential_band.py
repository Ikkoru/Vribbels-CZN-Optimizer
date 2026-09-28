"""The middle 80% takes two shortcuts, and neither changes a band.

Worked out plainly, the Memory Fragments tab's Potential columns took
seconds a refresh with `Show Potential's middle 80%` on, so two
shortcuts stand between them and the numbers. Either one wrong reads
as a plausible band:

1. **An added substat's rolls are convolved once per draw, the
   existing substats' once per band** (`_added_then_rest`), by splitting
   the later level-ups binomially between the two. Held bin for bin
   against the plain mixture over every draw of its whole sum: one
   substat to add, two, and none of its own that rolls.
2. **The Highest Potential column tries presets ceiling first and stops
   early** (`best_potential`), since a band's top never passes its
   ceiling. Held against working out every preset's band, on presets
   where the highest ceiling is not the highest top, one whose ceiling
   stops the search, and a tie -- which goes to the higher ceiling,
   then to the preset listed first.

How close a band is to the game's outcomes is `check_potential_mean`'s.
"""

from itertools import combinations

from ._harness import add_source_to_path

NAME = "the middle 80%'s shortcuts change no band"

MAIN = ("S_ATK_INC_ADD_OUT", 60)          # Flat ATK
# Every rolled stat left out of a preset below weighs 0, so the scene
# they set holds for the +0 fragment with Crit Rate, Flat DEF and HP%:
# SPIKY has the higher ceiling and STEADY the higher top, and MAIN_ONLY
# weighs nothing the fragment can roll, so its ceiling of 0 stops a
# search that has any band at all.
SPIKY = {"Extra DMG%": 1.0, "HP%": 1.0}
STEADY = {"Flat DEF": 1.0, "DEF%": 1.0, "CRate": 1.0}
MAIN_ONLY = {"Flat ATK": 1.0}
# Two stats at 0 so that two draws roll alike and are merged.
MIXED = {"ATK%": 1.0, "CRate": 0.9, "CDmg": 0.8, "DoT%": 0.3,
         "Flat DEF": 0.0, "Ego": 0.0, "Flat HP": 0.1}


def _weights(named):
    from game_data import STATS
    out = {info[0]: 0.0 for info in STATS.values() if info[3] > 0}
    out.update(named)
    return out


def _fragment(level, substats, res_id=1014101):
    from models.memory_fragment import MemoryFragment
    stats = [{"slot": 0, "type": 0, "stat": MAIN[0], "value": MAIN[1]}]
    for n, (raw, value) in enumerate(substats, 1):
        stats.append({"slot": n, "type": 1, "stat": raw, "value": value})
    return MemoryFragment.from_json({"id": 1, "res_id": res_id,
                                     "level": level, "stat_list": stats})


def _per_draw(existing, pool, added, rest):
    """Every draw alike: its first rolls, then `rest` level-ups each on
    one of all its substats alike."""
    from models.memory_fragment import _blend, _convolve, _dist, _power
    draws = list(combinations(pool, added))
    parts = []
    for chosen in draws:
        first = (0, [1.0])
        for grid in chosen:
            first = _convolve(first, _dist([grid]))
        grids = existing + list(chosen)
        parts.append((1.0 / len(draws),
                      _convolve(first, _power(_dist(grids), rest))))
    return _blend(parts)


def _gap(a, b):
    """The largest difference in any bin between two distributions."""
    (first_a, chances_a), (first_b, chances_b) = a, b
    bins = {}
    for first, chances, sign in ((first_a, chances_a, 1.0),
                                 (first_b, chances_b, -1.0)):
        for i, chance in enumerate(chances):
            bins[first + i] = bins.get(first + i, 0.0) + sign * chance
    return max(abs(v) for v in bins.values())


def _split_matches_every_draw():
    from game_data import STATS
    from models.memory_fragment import (
        _added_then_rest, _roll_grid, compute_gs_bounds)
    weights = MIXED
    low, high = compute_gs_bounds(weights, exclude_stat="Flat ATK")
    scale = 100.0 / (high - low)

    def grids(raws):
        return [_roll_grid(STATS[raw], weights.get(STATS[raw][0], 1.0),
                           scale) for raw in raws]

    def pool(held):
        return [_roll_grid(info, weights.get(info[0], 1.0), scale)
                for raw, info in STATS.items()
                if info[3] > 0 and raw not in held and info[0] != "Flat ATK"]

    three = ["S_CRI_INC_ADD", "S_DEF_INC_ADD_OUT", "S_HP_INC_RATE_OUT"]
    two = ["S_CRI_INC_ADD", "S_HP_INC_RATE_OUT"]
    cases = (
        ("a +0 with three, adding one and rolling four more", three, 1, 4),
        ("two, adding two and rolling two more", two, 2, 2),
        ("none that rolls, adding two and rolling one more", [], 2, 1),
    )
    out = []
    for what, held, added, rest in cases:
        want = _per_draw(grids(held), pool(held), added, rest)
        got = _added_then_rest(grids(held), pool(held), added, rest)
        gap = _gap(got, want)
        if gap > 1e-12:
            out.append(
                f"{what}: the split distribution differs from every draw "
                f"worked out in full by up to {gap:.2e} in a bin. Every "
                f"band with a substat still to add reads from it -- see "
                f"`_added_then_rest` in models/memory_fragment.py.")
    return out


def _search_matches_every_preset():
    from models.memory_fragment import (
        compute_fragment_potential, compute_fragment_potential_band,
        compute_gs_bounds)
    from ui.tabs.inventory_tab import best_potential
    presets = [("Spiky", _weights(SPIKY)), ("Main only", _weights(MAIN_ONLY)),
               ("Steady", _weights(STEADY)),
               ("Steady again", _weights(STEADY))]
    scene = _fragment(0, [("S_CRI_INC_ADD", 1.6), ("S_DEF_INC_ADD_OUT", 4),
                          ("S_HP_INC_RATE_OUT", 1.1)])
    fragments = (
        ("a +0 with three", scene),
        ("a +3 with four", _fragment(3, [
            ("S_DOT_ATK_DMG_RATE_INC_ADD", 2.8), ("S_DEF_INC_ADD_OUT", 5),
            ("S_ATK_INC_RATE_OUT", 1.0), ("S_CRI_DMG_RATE_INC_ADD", 3.2)])),
        ("a +5, nothing left to roll", _fragment(5, [
            ("S_CRI_INC_ADD", 1.6), ("S_DEF_INC_ADD_OUT", 4),
            ("S_HP_INC_RATE_OUT", 1.1), ("S_ATK_INC_RATE_OUT", 1.2)])),
    )
    out = []
    for what, fragment in fragments:
        ranked, bands = [], []
        for index, (name, weights) in enumerate(presets):
            bounds = compute_gs_bounds(weights,
                                       exclude_stat=fragment.main_stat.name)
            low, high = compute_fragment_potential(fragment, weights, bounds)
            ranked.append((high, low, index, name, weights, bounds))
            bands.append(compute_fragment_potential_band(
                fragment, weights, bounds))
        if fragment is scene:
            spiky, main_only, steady = ranked[0], ranked[1], ranked[2]
            if not (spiky[0] > steady[0] and bands[2][1] > bands[0][1]
                    and main_only[0] <= bands[0][1]):
                out.append(
                    "the presets no longer set their scene: Spiky must "
                    "have the higher ceiling, Steady the higher top, and "
                    "Main only a ceiling at most Spiky's top. Without it "
                    "a search that stops too early passes -- pick new "
                    "weights for them.")
        by_top = max(range(len(ranked)),
                     key=lambda i: (bands[i][1], ranked[i][0], -i))
        want = (bands[by_top][0], bands[by_top][1], ranked[by_top][3])
        got = best_potential(fragment, ranked, True)
        if got != want:
            out.append(
                f"{what}: the Highest Potential column's middle 80% picks "
                f"{got}, where every preset's band worked out picks "
                f"{want}. The search's early stop is wrong -- see "
                f"`best_potential` in ui/tabs/inventory_tab.py.")
        by_ceiling = max(range(len(ranked)),
                         key=lambda i: (ranked[i][0], -i))
        want = (ranked[by_ceiling][1], ranked[by_ceiling][0],
                ranked[by_ceiling][3])
        got = best_potential(fragment, ranked, False)
        if got != want:
            out.append(f"{what}: the Highest Potential column's full range "
                       f"picks {got}, not the highest ceiling's {want}.")
    if best_potential(scene, [], True) is not None:
        out.append("no presets at all gives a Highest Potential rather "
                   "than none.")
    return out


def run():
    add_source_to_path()
    return _split_matches_every_draw() + _search_matches_every_preset()
