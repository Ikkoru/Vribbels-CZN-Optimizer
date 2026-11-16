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
   linear, so the build score, which samples, deals the upgrades as
   the Gear Score counts them.
7. **The tab says which option to use**: Exclude where its gain per
   Quartz is higher, Reroll otherwise.
9. **Avg is the average after, kept or not**: every outcome's score,
   the ones below Now included, held against every outcome counted out.
10. **A pinned fragment is in every build, or in none**: the Optimizer
    builds around it, at the values it is handed, where the run's
    filters let it in; where they refuse it, the run finds nothing.
11. **The build score reads against the Top build**: a fragment of the
    Top build stands at 0 before a readjustment.
12. **A build-score answer is kept by everything its builds are made
    of**: a fragment the run searches rerolled, a readjustable one
    moved to another combatant, or the settings changed, is a new
    signature; the same capture loaded again is not.

13. **The work takes the combatants in the tab's order**: the one
    chosen, then the weighted, heaviest first, then everyone else.
14. **The Gear Score cut leaves out only what cannot reach the top**:
    never a fragment of the Top build, and always one whose every
    substat the preset weighs at nothing.
15. **Saved answers come back after a restart**, and only from the
    same way of working out (`CACHE_VERSION`).
16. **The progress counts each group's readings**, and says Complete
    only when every one is in.

Rules 10 to 12 and 14 run on `_parity_fixture`'s synthetic inventory.
8. **The work keeps an answer by what it was worked out from**: a
   readjusted fragment is worked out again, an unchanged one is not,
   and a combatant's Top build outlasts a capture that changes none of
   what it is made of.
"""

import random

from pathlib import Path

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
    """(mean gain, chance of a gain, average after) over every outcome,
    counted out:
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
    mean = chance = avg = 0.0
    for add, p in dist.items():
        after = start + add
        avg += p * after
        if after > ref + 1e-9:
            mean += p * (after - ref)
            chance += p
    return mean, chance, avg


class _Linear:
    """A score linear in the substats: `read`'s valuer, and `score` the
    same reading for `options` to sample."""

    def __init__(self, fragment):
        import readjust as rj
        self.fragment = fragment
        self.per = {s.name: WEIGHTS[s.name] / rj.max_roll(s)
                    for s in fragment.substats}

    def points(self, sub, value):
        return self.per[sub.name] * value

    def reference(self, fragment):
        now = sum(self.points(s, s.value) for s in fragment.substats)
        return now, now, 0.0

    def score(self, values):
        subs = self.fragment.substats
        values = values or [s.value for s in subs]
        return sum(self.points(s, v) for s, v in zip(subs, values,
                                                     strict=True))


def run():
    add_source_to_path()
    import readjust as rj
    from ui.tabs.readjust_tab import COLUMNS, row_values

    out = []
    tol = 0.01

    # 1 and 2: upgraded twice, CRate 1.6 and Flat ATK 5, and read as
    # four upgrades dealt again, counted out.
    fragment = _fragment([(0, 1.6), (2, 5)])
    valuer = rj.GearValuer(WEIGHTS)
    reading = rj.read_gear(fragment, valuer)
    mean, chance, avg = _counted(fragment, valuer, [0, 1, 2, 3])
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
    # 9
    if abs(reading.plain.avg - avg) > span / rj.BINS + tol:
        out.append(f"Avg reads {reading.plain.avg:.3f} GS where every "
                   f"outcome counted out averages {avg:.3f}: it is the "
                   f"average after a readjustment, the outcomes below Now "
                   f"included.")
    best = None
    for i, sub in enumerate(fragment.substats):
        rest = [j for j in range(4) if j != i]
        m, c, _a = _counted(fragment, valuer, rest)
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
    plain, exclude = rj.options(linear.score, four, exact.now, 6000,
                                random.Random(four.id))
    if abs(plain.mean - exact.plain.mean) \
            > 0.06 * max(exact.plain.mean, 0.01) \
            or exclude.excluded != exact.exclude.excluded:
        out.append(f"sampling a linear score reads {plain.mean:.4f} "
                   f"(excluding {exclude.excluded}) where the "
                   f"exact reading is {exact.plain.mean:.4f} (excluding "
                   f"{exact.exclude.excluded}): `options` deals the "
                   f"upgrades as `read` counts them.")

    # 7
    for plain_mean, exclude_mean, want in ((1.0, 1.8, "Reroll"),
                                           (1.0, 2.2, "Exclude")):
        r = rj.Reading(fragment, "X", 0.0,
                       rj.Option(None, 1, plain_mean, 0.5, 2.0),
                       rj.Option("CRate", 2, exclude_mean, 0.5, 2.0))
        use = row_values(r, rj.GEAR)[[c[0] for c in COLUMNS].index("use")]
        if use != want:
            out.append(f"a plain gain of {plain_mean} against an "
                       f"exclusion's {exclude_mean} says {use!r}, not "
                       f"{want!r}: Use names the option with the higher "
                       f"gain per Quartz.")
    out.extend(_answers_kept_by_content())
    out.extend(_build_score_reads_the_top_build())
    out.extend(_the_work_order_cache_and_progress())
    return out


def _the_work_order_cache_and_progress():
    """13, 15 and 16: what the user sees of the work besides its
    answers -- which combatants come first, whether a restart keeps
    what was worked out, and what the progress says."""
    import tempfile

    import readjust as rj
    import readjust_work as rw
    from ui.tabs.readjust_tab import COMPLETE, OUT_OF, progress_lines

    out = []
    names = ["Ann", "Bea", "Cyd", "Dee", "Eve"]
    weights = {"Ann": 2, "Dee": 5, "Eve": 2}
    for mode, chosen, want in (
            ("one", "Cyd", ["Cyd", "Dee", "Ann", "Eve", "Bea"]),
            ("one", "Dee", ["Dee", "Ann", "Eve", "Bea", "Cyd"]),
            ("weighted", "Cyd", ["Dee", "Ann", "Eve", "Bea", "Cyd"])):
        got = rw.ordered(names, mode, chosen, weights)
        if got != want:
            out.append(f"with {mode!r} and {chosen} chosen the work takes "
                       f"{got}, not {want}: the chosen one first in one "
                       f"mode, then the weighted, heaviest first, then the "
                       f"rest.")

    # 15
    folder = Path(tempfile.mkdtemp(prefix="readjust_cache_"))
    first = rw.ReadjustWork(None, lambda *_a: None, cache_dir=folder)
    key = ("a signature", "read", ("content",))
    first.answers[key] = ("now", "plain", "exclude")
    first._dirty = True
    first.save()
    again = rw.ReadjustWork(None, lambda *_a: None, cache_dir=folder)
    if again.answers.get(key) != ("now", "plain", "exclude"):
        out.append("answers saved by one launch are not there in the "
                   "next: a restart would work everything out again.")
    if not (folder / "CACHEDIR.TAG").read_bytes().startswith(
            b"Signature: 8a477f597d28d172789f06886806bc55"):
        out.append("the cache folder carries no CACHEDIR.TAG: backups "
                   "would copy answers the program can work out again.")
    real = rw.CACHE_VERSION
    rw.CACHE_VERSION = real + 1
    try:
        older = rw.ReadjustWork(None, lambda *_a: None, cache_dir=folder)
    finally:
        rw.CACHE_VERSION = real
    if older.answers:
        out.append("answers saved by another way of working out "
                   "(CACHE_VERSION) are read back: a change to the model "
                   "would show the old one's numbers.")

    # 16
    half, whole = rw.Status(10), rw.Status(10)
    half.done, whole.done = 4, 10
    groups = {"one": ["Ann"], "weighted": ["Ann", "Dee"],
              "all": ["Ann", "Dee", "Eve"]}
    statuses = {"Ann": whole, "Dee": half, "Eve": whole}
    lines = progress_lines(groups, statuses, rj.BACKGROUND)
    want = [lines[0], "For one:", COMPLETE % 10, "For weighted:",
            OUT_OF % (14, 20), "For all:", OUT_OF % (24, 30)]
    if lines != want or lines[0] == "Done":
        out.append(f"the progress reads {lines}, not {want}: each group "
                   f"counts its combatants' readings, Complete only when "
                   f"every one is in.")
    return out


def _answers_kept_by_content():
    """8. **The work keeps an answer by what it was worked out from.** A
    new capture holding the same fragments asks for nothing again; a
    readjusted fragment, same id and new rolls, is asked for again and
    its old answer dropped; a deleted one's answer is dropped. Kept by id
    instead, the list would go on showing a readjusted fragment's old
    worth, and nothing would say so."""
    import copy
    import readjust as rj
    from readjust_work import ReadjustWork

    out = []
    tab = ReadjustWork(None, lambda *_a: None)
    frags = []
    for n, ups in enumerate(([(0, 1.3)] * 4, [(1, 2.5)] * 4,
                             [(2, 5)] * 4)):
        f = _fragment(ups)
        f.id = 100 + n
        frags.append(f)
    sig = "a gear signature"
    template = {"measure": rj.GEAR}

    def status(fragments):
        wanted = []
        keys = {f.id: rj.content(f) for f in fragments}
        got = tab._status("X", sig, template, fragments, keys, wanted)
        return got, sorted(f.id for *_rest, chunk in wanted for f in chunk)

    def asked(fragments):
        return status(fragments)[1]

    def answer(fragments):
        for f in fragments:
            tab.answers[(sig, "read", rj.content(f))] = ("answer", f.id)

    tab._forget("capture 1", frags)
    answer(frags)
    top_key = ("a build signature", "top", None)
    tab.answers[top_key] = {"top": [f.id for f in frags], "cut": []}
    same = [copy.deepcopy(f) for f in frags]
    tab._forget("capture 2", same)
    if asked(same):
        out.append(f"a new capture of the same fragments asks for "
                   f"{asked(same)} again: an answer is kept by what it was "
                   f"worked out from, not by the capture.")
    if top_key not in tab.answers:
        out.append("a new capture of the same fragments drops a "
                   "combatant's Top build: it is kept by its signature, "
                   "which holds every fragment it could be made of.")
    rerolled = [copy.deepcopy(f) for f in frags]
    sub = rerolled[1].substats[1]
    sub.upgrade_values = [2.0, 2.0, 2.0]
    sub.value = sub.base_value + sum(sub.upgrade_values)
    tab._forget("capture 3", rerolled)
    readings = status(rerolled)[0].readings
    if asked(rerolled) != [rerolled[1].id] or rerolled[1].id in readings:
        out.append(f"after a readjustment of fragment {rerolled[1].id} the "
                   f"work asks for {asked(rerolled)} and shows "
                   f"{readings.get(rerolled[1].id)} for it: the "
                   f"readjusted fragment alone is worked out again, and its "
                   f"old answer is not shown.")
    answer(rerolled)
    left = rerolled[:2]
    tab._forget("capture 4", left)
    gone = [k for k in tab.answers
            if k[2] is not None and k[2][0] == rerolled[2].id]
    if gone or asked(left):
        out.append(f"after fragment {rerolled[2].id} is deleted the work "
                   f"keeps {len(gone)} answer(s) of it and asks for "
                   f"{asked(left)}: a deleted fragment's answers are "
                   f"dropped, and nothing else is asked for.")
    return out


def _build_score_reads_the_top_build():
    """10 to 12, on the synthetic inventory: the Optimizer's pin, the
    build score's reference, and what a build-score answer is kept by.
    The pin decides which fragments the build score can read at all,
    and the signature whether a capture shows answers of an inventory
    it no longer holds -- both wrong would read as a plausible list."""
    import copy
    import tempfile
    from pathlib import Path

    import readjust as rj
    from optimizer.optimizer import GearOptimizer

    from . import _parity_fixture as fixture

    out = []
    snap = Path(tempfile.mkdtemp(prefix="readjust_")) / "fixture.json"
    fixture.write(snap)
    loaded = GearOptimizer()
    loaded.load_data(str(snap))
    o = rj.lean_optimizer(loaded)
    name = fixture.COMBATANT_NAME
    settings = dict(fixture.SETTINGS, max_results=5)
    top = rj.top_build(o, name, settings)
    if not top:
        return ["the synthetic inventory has no Top build: rules 10 to 12 "
                "could not run."]
    in_top = {f.id for f in top}

    # 10: pinned, in every build; at other values, at those; refused by
    # a main-stat filter, in none.
    pick = next(f for f in o.fragments
                if f.slot_num == 4 and f.id not in in_top)
    pinned = o.optimize(name, settings, pinned=pick)
    if not pinned or any(pick.id not in {p.id for p in gear}
                         for gear, _s, _st in pinned):
        out.append(f"a run with fragment {pick.id} pinned returns "
                   f"{len(pinned)} build(s), not all wearing it: a pinned "
                   f"fragment is in every build the run finds.")
    raised = rj.at_values(pick, [s.value + 5 for s in pick.substats])
    again = o.optimize(name, settings, pinned=raised)
    if not again or not any(p is raised for p in again[0][0]):
        out.append("a fragment pinned at other substat values is not the "
                   "copy the run was handed: the build is made around the "
                   "values it is pinned at.")
    other = next(f.main_stat.name for f in o.fragments
                 if f.slot_num == 4 and f.main_stat.name
                 != pick.main_stat.name)
    refused = o.optimize(name, dict(settings, main_stat_4=[other]),
                         pinned=pick)
    if refused:
        out.append(f"fragment {pick.id} ({pick.main_stat.name}) pinned "
                   f"under a Slot IV filter for {other} still returns "
                   f"{len(refused)} build(s): the pin is held to the run's "
                   f"filters, and a fragment they refuse can be in no "
                   f"build.")

    # 11
    valuer = rj.BuildValuer(o, name, settings, top)
    member = top[0]
    reading = rj.read_build(o, name, settings, valuer, member, samples=100)
    if reading is None or abs(reading[0]) > 1e-6:
        out.append(f"fragment {member.id} of the Top build reads Now "
                   f"{reading and reading[0]}: the build score stands "
                   f"against the Top build, which reads 0.")

    # 14: the cut keeps the Top build, and drops a fragment whose every
    # substat the preset weighs at nothing.
    if set(rj.gear_cut(o, name, settings)) & in_top:
        out.append("the Gear Score cut leaves out a fragment of the Top "
                   "build: it would never be read, though the best build "
                   "already wears it.")
    from game_data.constants import STATS
    stray = next(f for f in o.fragments
                 if rj.readjustable(f) and f.id not in in_top)
    blind = {info[0]: 0.0 for info in STATS.values()}
    blind.update({s.name: 0.0 for s in stray.substats})
    keeps = {info[0]: 1.0 for info in STATS.values()
             if info[0] not in {s.name for s in stray.substats}}
    blind.update(keeps)
    if stray.id not in rj.gear_cut(o, name,
                                   dict(settings, slot_filter_weights=blind)):
        out.append(f"fragment {stray.id}, whose every substat the preset "
                   f"weighs at 0, is read: at its best it reaches no Gear "
                   f"Score, so it cannot reach the top third of its slot.")

    # 12
    sig = rj.build_signature(o, name, settings)
    reloaded = GearOptimizer()
    reloaded.load_data(str(snap))
    if rj.build_signature(rj.lean_optimizer(reloaded), name,
                          settings) != sig:
        out.append("the same capture loaded again gives another build "
                   "signature: a reload would work everything out again.")
    rerolled = copy.copy(o)
    rerolled.fragments = [copy.deepcopy(f) for f in o.fragments]
    sub = rerolled.fragments[0].substats[0]
    sub.value += 1
    if rj.build_signature(rerolled, name, settings) == sig:
        out.append("a fragment the run could use, rerolled, leaves the "
                   "build signature as it was: the Top build and every "
                   "build around a fragment would be shown from the "
                   "inventory before it.")
    moved = copy.copy(o)
    moved.fragments = [copy.copy(f) for f in o.fragments]
    target = next(f for f in moved.fragments if rj.readjustable(f))
    target.equipped_to = "Someone Else"
    if rj.build_signature(moved, name, settings) == sig:
        out.append("a readjustable fragment moved to another combatant "
                   "leaves the build signature as it was: whether Exclude "
                   "Combatant's MFs lets it be pinned would be read off "
                   "its old owner.")
    if rj.build_signature(o, name, dict(settings, extra_pct=0)) == sig:
        out.append("other run settings leave the build signature as it "
                   "was: the answers of the settings before would be "
                   "shown.")
    return out


FAULTS = [
    ("the cut keeping only what cannot reach the top", "readjust:gear_cut",
     "top_gs(f, valuer) < bar)", "top_gs(f, valuer) >= bar)",
     "leaves out a fragment of the Top"),
    ("the weighted taken lightest first", "readjust_work:ordered",
     "key=lambda n: (-weights[n], n))", "key=lambda n: (weights[n], n))",
     "heaviest first"),
    ("answers never saved", "readjust_work:ReadjustWork.save",
     "        os.replace(temp, path)\n", "        pass\n",
     "not there in the"),
    ("another version's answers read back", "readjust_work:ReadjustWork._load",
     "saved.get(\"version\") == CACHE_VERSION",
     "saved.get(\"version\") is not None",
     "another way of working out"),
    ("Complete before every reading is in",
     "ui.tabs.readjust_tab:progress_lines",
     "elif total is not None and done >= total:",
     "elif total is not None and done > 0:",
     "Complete only when"),
    ("the pin ignoring the run's filters",
     "optimizer.optimizer:GearOptimizer.optimize",
     "candidates = [pinned] if any(\n"
     "                    f.id == pinned.id for f in allowed) else []",
     "candidates = [pinned]",
     "still returns"),
    ("the pin left out", "optimizer.optimizer:GearOptimizer.optimize",
     "if pinned is not None and slot_num == pinned.slot_num:",
     "if False:",
     "not all wearing it"),
    ("the build score read against nothing", "readjust:BuildValuer.rel",
     "out = (1 - self.h) * (d / self.d0 - 1) if self.d0 else 0.0",
     "out = (1 - self.h) * (d / self.d0) if self.d0 else 0.0",
     "of the Top build reads Now"),
    ("a build signature blind to rolls", "readjust:build_signature",
     "            pool.append(content(f))\n",
     "            pool.append(f.id)\n",
     "rerolled, leaves the"),
    ("a build signature blind to owners", "readjust:build_signature",
     "owners = sorted((f.id, f.equipped_to or \"\")",
     "owners = sorted((f.id, \"\")",
     "moved to another combatant"),
    ("a Top build dropped with each capture",
     "readjust_work:ReadjustWork._forget",
     "if k[2] is not None and k[2] not in live]:",
     "if k[2] not in live]:",
     "drops a combatant's Top build"),
    ("Avg counting only the outcomes kept", "readjust:_option",
     "        avg += p * after\n",
     "        avg += p * max(after, ref)\n",
     "Avg reads"),
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
    ("sampling deals over all four when excluding", "readjust:options",
     "every[:i] + every[i + 1:]", "every", "sampling a linear score"),
    ("Use naming the cheaper option always",
     "readjust:Reading.best",
     "key=lambda o: (o.per_quartz, -o.cost))",
     "key=lambda o: (-o.cost, o.per_quartz))",
     "Use names the option"),
    ("every answer dropped with each capture",
     "readjust_work:ReadjustWork._forget",
     "if k[2] is not None and k[2] not in live]:",
     "if True]:",
     "not by the capture"),
    ("an answer kept by the fragment's id alone", "readjust:content",
     "tuple((s.raw_name, s.value, s.base_value,\n"
     "                   tuple(s.upgrade_values)) for s in fragment.substats))",
     "len(fragment.substats))",
     "the readjusted fragment alone"),
    ("a deleted fragment's answers kept",
     "readjust_work:ReadjustWork._forget",
     "live = {rj.content(f) for f in fragments}",
     "live = {k[2] for k in self.answers}",
     "a deleted fragment's answers are"),
]
