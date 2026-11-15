"""What a Substat Readjustment is worth (`readjust`).

Every rule here changes a number on the Substat Readjustment tab and
nothing else, so a broken one reads as a plausible ranking:

1. **The exact distribution is the readjustment's**, as the game's
   Memory Fragment Upgrade Probabilities notice gives it: four
   upgrades, each on one of the substats alike and on any value of its
   roll alike, onto the substats' starting values, however many the
   fragment had. Held against every outcome counted out.
2. **An exclusion deals the upgrades over the other three**, the
   excluded substat back at its starting value, and the best of the
   four exclusions is the one shown.
3. **A readjustment never loses**: the game keeps Before or After, so
   a fragment whose every upgrade already sits at its top on its best
   substat has nothing to gain.
4. **Per Quartz divides by the cost**: 1 plain, 2 with an exclusion.
5. **Only a fully upgraded Legendary with four substats** is listed.
6. **Sampling agrees with the exact reading** where the score is
   linear, so `refine` replacing the top of the build list moves it
   only by the sampling error.
7. **The tab says which option to use**: Exclude where its gain per
   Quartz is higher, Reroll otherwise.
8. **The tab keeps an answer by what it was worked out from**: a
   readjusted fragment is worked out again, an unchanged one is not.
"""

from ._harness import add_source_to_path

NAME = "a Substat Readjustment's worth, per Shuffling Quartz"

# A Legendary Slot VI fragment: ATK% main; CRate, CDmg, Flat ATK and
# Flat DEF as substats, the last added at level 1.
MAIN = {"slot": 0, "type": 0, "stat": "S_ATK_INC_RATE_OUT", "value": 25.0}
BASES = (("S_CRI_INC_ADD", 1.5, 1), ("S_CRI_DMG_RATE_INC_ADD", 3.0, 1),
         ("S_ATK_INC_ADD_OUT", 6, 1), ("S_DEF_INC_ADD_OUT", 4, 2))
WEIGHTS = {"CRate": 2.0, "CDmg": 1.5, "Flat ATK": 0.5, "Flat DEF": 0.1}


def _fragment(ups, level=5, rarity=4, substats=4):
    """A fragment from a stat_list: `ups` [(substat index, value)]."""
    from models.memory_fragment import MemoryFragment
    rows = [MAIN]
    for slot, (stat, value, kind) in enumerate(BASES[:substats], start=1):
        rows.append({"slot": slot, "type": kind, "stat": stat,
                     "value": value})
    for index, value in ups:
        rows.append({"slot": index + 1, "type": 3,
                     "stat": BASES[index][0], "value": value})
    return MemoryFragment.from_json({
        "id": 7, "res_id": int("116%d11" % rarity), "level": level,
        "stat_list": rows})


def _counted(fragment, valuer, eligible):
    """(mean gain, chance of a gain) over every outcome, counted out:
    the exact distribution of what `UPGRADES` upgrades add, each a
    substat of `eligible` and a roll alike, unbinned."""
    import readjust as rj
    subs = fragment.substats
    scaled = valuer.bind(fragment)
    _now, ref, extra = scaled.reference(fragment)
    start = extra + sum(scaled.points(s, s.base_value) for s in subs)
    step = {}
    for i in eligible:
        grid = rj.roll_values(subs[i])
        for v in grid:
            at = round(scaled.points(subs[i], v), 9)
            step[at] = step.get(at, 0.0) + 1.0 / len(eligible) / len(grid)
    dist = {0.0: 1.0}
    for _ in range(rj.UPGRADES):
        out = {}
        for total, p in dist.items():
            for add, q in step.items():
                at = round(total + add, 9)
                out[at] = out.get(at, 0.0) + p * q
        dist = out
    mean = chance = 0.0
    for add, p in dist.items():
        after = start + add
        if after > ref + 1e-9:
            mean += p * (after - ref)
            chance += p
    return mean, chance


class _Linear:
    """A build score linear in the substats, for `refine`."""

    def __init__(self, fragment):
        import readjust as rj
        self.rj = rj
        self.per = {s.name: WEIGHTS[s.name] / rj.max_roll(s)
                    for s in fragment.substats}

    def points(self, sub, value):
        return self.per[sub.name] * value

    def reference(self, fragment):
        now = sum(self.points(s, s.value) for s in fragment.substats)
        return now, now, 0.0

    def swapped(self, fragment, values=None):
        subs = fragment.substats
        return [(s, s.value if values is None else v)
                for s, v in zip(subs, values or [None] * len(subs), strict=True)]

    def rel(self, gear):
        return sum(self.points(s, v) for s, v in gear) / 100


def run():
    add_source_to_path()
    import readjust as rj
    from ui.tabs.readjust_tab import row_values

    out = []
    tol = 0.01

    # 1 and 2: upgraded twice, CRate 1.6 and Flat ATK 5, and read as
    # four upgrades dealt again, counted out.
    fragment = _fragment([(0, 1.6), (2, 5)])
    valuer = rj.GearValuer(WEIGHTS)
    reading = rj.read_gear(fragment, valuer)
    mean, chance = _counted(fragment, valuer, [0, 1, 2, 3])
    span = rj.UPGRADES * max(valuer.bind(fragment).points(s, rj.max_roll(s))
                   for s in fragment.substats)
    if abs(reading.plain.mean - mean) > span / rj.BINS + tol \
            or abs(reading.plain.chance - chance) > 0.02:
        out.append(f"a plain readjustment reads "
                   f"{reading.plain.mean:.3f} GS at "
                   f"{reading.plain.chance:.3f}, where every outcome "
                   f"counted out gives {mean:.3f} at {chance:.3f}: each "
                   f"upgrade lands on a substat alike and on any roll "
                   f"alike, onto the starting values.")
    best = None
    for i, sub in enumerate(fragment.substats):
        rest = [j for j in range(4) if j != i]
        m, c = _counted(fragment, valuer, rest)
        if best is None or m > best[1]:
            best = (sub.name, m, c)
    if reading.exclude.excluded != best[0] \
            or abs(reading.exclude.mean - best[1]) > span / rj.BINS + tol:
        out.append(f"the best exclusion reads {reading.exclude.excluded} "
                   f"at {reading.exclude.mean:.3f} GS; counted out it is "
                   f"{best[0]} at {best[1]:.3f}: an exclusion deals the "
                   f"upgrades over the other three substats.")

    # 3: every upgrade a top CRate roll -- nothing a readjustment can beat.
    maxed = _fragment([(0, 2.0), (0, 2.0), (0, 2.0), (0, 2.0)])
    top = rj.read_gear(maxed, valuer)
    if top.plain.mean > tol or top.plain.chance > tol \
            or top.exclude.mean > tol:
        out.append(f"a fragment with four top CRate rolls reads a gain of "
                   f"{top.plain.mean:.3f} GS at {top.plain.chance:.3f}: "
                   f"the game keeps Before where After is worse, so "
                   f"nothing can beat it and the gain is 0.")

    # 4
    if abs(reading.exclude.per_quartz
           - reading.exclude.mean / rj.EXCLUDE_COST) > 1e-9 \
            or abs(reading.plain.per_quartz - reading.plain.mean) > 1e-9:
        out.append("Per Quartz is not the gain over the cost: an "
                   "exclusion costs 2 Shuffling Quartz, a plain "
                   "readjustment 1.")

    # 5
    for what, f in (("a level-4 Legendary", _fragment([(0, 1.6)], level=4)),
                    ("an Epic", _fragment([(0, 1.6)], rarity=3)),
                    ("a three-substat Legendary",
                     _fragment([(0, 1.6)], substats=3))):
        if rj.readjustable(f):
            out.append(f"{what} is listed for readjustment; only a fully "
                       f"upgraded Legendary with four substats can be.")
    if not rj.readjustable(fragment):
        out.append("a fully upgraded Legendary with four substats is not "
                   "listed for readjustment.")

    # 6: sampling a linear score lands on the exact reading.
    four = _fragment([(0, 1.3), (1, 2.5), (2, 5), (3, 3)])
    linear = _Linear(four)
    exact = rj.read(four, linear)
    sampled = rj.refine(exact, linear, samples=6000)
    if abs(sampled.plain.mean - exact.plain.mean) \
            > 0.06 * max(exact.plain.mean, 0.01) \
            or sampled.exclude.excluded != exact.exclude.excluded:
        out.append(f"sampling a linear score reads {sampled.plain.mean:.4f} "
                   f"(excluding {sampled.exclude.excluded}) where the "
                   f"exact reading is {exact.plain.mean:.4f} (excluding "
                   f"{exact.exclude.excluded}): `refine` deals the "
                   f"upgrades as `read` counts them.")

    # 7
    for plain_mean, exclude_mean, want in ((1.0, 1.8, "Reroll"),
                                           (1.0, 2.2, "Exclude")):
        r = rj.Reading(fragment, "X", 0.0,
                       rj.Option(None, 1, plain_mean, 0.5, 2.0),
                       rj.Option("CRate", 2, exclude_mean, 0.5, 2.0))
        use = row_values(r, rj.GEAR)[13]
        if use != want:
            out.append(f"a plain gain of {plain_mean} against an "
                       f"exclusion's {exclude_mean} says {use!r}, not "
                       f"{want!r}: Use names the option with the higher "
                       f"gain per Quartz.")
    out.extend(_answers_kept_by_content())
    return out


def _answers_kept_by_content():
    """8. **The tab keeps an answer by what it was worked out from.** A
    new capture holding the same fragments asks for nothing again; a
    readjusted fragment, same id and new rolls, is asked for again and
    its old answer dropped; a deleted one's answer is dropped. Kept by id
    instead, the list would go on showing a readjusted fragment's old
    worth, and nothing would say so."""
    import copy
    import readjust as rj
    from ui.tabs.readjust_tab import ReadjustTab

    out = []
    tab = ReadjustTab.__new__(ReadjustTab)
    tab._answers, tab._inflight, tab._inputs, tab._token = {}, {}, {}, None
    frags = []
    for n, ups in enumerate(([(0, 1.3)] * 4, [(1, 2.5)] * 4,
                             [(2, 5)] * 4)):
        f = _fragment(ups)
        f.id = 100 + n
        frags.append(f)
    sig = ("gear", "weights")
    signatures = {"X": (sig, {"measure": rj.GEAR})}

    def asked(fragments):
        _readings, wanted, _waiting = tab._needed(fragments, signatures)
        return sorted(f.id for *_rest, chunk, _refine in wanted
                      for f in chunk)

    def answer(fragments):
        for f in fragments:
            tab._answers[(sig, "read", rj.content(f))] = ("answer", f.id)

    tab._forget("capture 1", frags)
    answer(frags)
    same = [copy.deepcopy(f) for f in frags]
    tab._forget("capture 2", same)
    if asked(same):
        out.append(f"a new capture of the same fragments asks for "
                   f"{asked(same)} again: an answer is kept by what it was "
                   f"worked out from, not by the capture.")
    rerolled = [copy.deepcopy(f) for f in frags]
    sub = rerolled[1].substats[1]
    sub.upgrade_values = [2.0, 2.0, 2.0]
    sub.value = sub.base_value + sum(sub.upgrade_values)
    tab._forget("capture 3", rerolled)
    readings, _wanted, _waiting = tab._needed(rerolled, signatures)
    if asked(rerolled) != [rerolled[1].id] or rerolled[1].id in readings["X"]:
        out.append(f"after a readjustment of fragment {rerolled[1].id} the "
                   f"tab asks for {asked(rerolled)} and shows "
                   f"{readings['X'].get(rerolled[1].id)} for it: the "
                   f"readjusted fragment alone is worked out again, and its "
                   f"old answer is not shown.")
    answer(rerolled)
    left = rerolled[:2]
    tab._forget("capture 4", left)
    gone = [k for k in tab._answers if k[2][0] == rerolled[2].id]
    if gone or asked(left):
        out.append(f"after fragment {rerolled[2].id} is deleted the tab "
                   f"keeps {len(gone)} answer(s) of it and asks for "
                   f"{asked(left)}: a deleted fragment's answers are "
                   f"dropped, and nothing else is asked for.")
    return out


FAULTS = [
    ("an exclusion dealing over all four", "readjust:read",
     "rest = grids[:i] + grids[i + 1:]", "rest = grids",
     "the best exclusion reads"),
    ("a loss counted as a gain", "readjust:_option",
     "if after > ref + width / 2:", "if True:",
     "four top CRate rolls"),
    ("upgrades dealt onto the current values", "readjust:read",
     "starts = [valuer.points(sub, sub.base_value)",
     "starts = [valuer.points(sub, sub.value)",
     "counted out gives"),
    ("per Quartz ignoring the cost", "readjust:Option.per_quartz",
     "return self.mean / self.cost", "return self.mean",
     "Per Quartz is not the gain"),
    ("an Epic readjusted", "readjust:readjustable",
     "fragment.rarity_num == LEGENDARY and", "fragment.rarity_num >= 3 and",
     "an Epic is listed"),
    ("sampling deals over all four when excluding", "readjust:refine",
     "every[:i] + every[i + 1:]", "every", "sampling a linear score"),
    ("Use naming the cheaper option always",
     "readjust:Reading.best",
     "key=lambda o: (o.per_quartz, -o.cost))",
     "key=lambda o: (-o.cost, o.per_quartz))",
     "Use names the option"),
    ("every answer dropped with each capture",
     "ui.tabs.readjust_tab:ReadjustTab._forget",
     "for key in [k for k in self._answers if k[2] not in live]:",
     "for key in list(self._answers):",
     "not by the capture"),
    ("an answer kept by the fragment's id alone", "readjust:content",
     "tuple((s.raw_name, s.value, s.base_value,\n"
     "                   tuple(s.upgrade_values)) for s in fragment.substats))",
     "len(fragment.substats))",
     "the readjusted fragment alone"),
    ("a deleted fragment's answers kept",
     "ui.tabs.readjust_tab:ReadjustTab._forget",
     "live = {rj.content(f) for f in fragments}",
     "live = {k[2] for k in self._answers}",
     "a deleted fragment's answers are"),
]
