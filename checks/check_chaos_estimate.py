"""The season estimate's Chaos share, and when a player's own runs
overrule the figures the program shipped with (`chaos_estimate`).

Every rule here changes a number on the seasonal shop's tip and nothing
else, so a broken one reads as a plausible figure:

1. **The shipped figures add up as the module says**: bosses by part
   and day, a part never measured borrowing its neighbour's, and the
   marks a run meets over every day, all times the runs a day.
2. **Staleness is counted in whole seasons**, and the rules follow it:
   a lower payout is ignored while the program is fresh, last season's
   runs join after one stale season, lower payouts count after two
   unless the highest makes `TOP_SHARE` of them.
3. **The player's rates take over only on both conditions**: two stale
   seasons AND `RATE_RUNS` whole runs since the release, none inside a
   `RATE_EVENTS` window.
4. **A lost run is whole only when a boss had paid and no non-boss
   fight was left**, and then misses its own fight's payout and every
   boss after it.
5. **`chaos_runs_per_day` reads as a sane number or not at all**, sits
   at the foot of settings.json, and names itself in the tip's label.
"""

import math

from ._harness import add_source_to_path

NAME = "the Chaos estimate follows its rules"

LIVE = "disaster_s04"
DAY = 86400
AFTER = 1790000000          # a clear time after the release


def _run(season, part, bosses=(), marks=(), marked=None, lost=None,
         closed=AFTER):
    """A run in the capture's record shape."""
    paid = [[floor, "BOSS", "", 1, amount] for floor, amount in bosses]
    paid += [[5, "BATTLE", mark, 1, amount] for mark, amount in marks]
    return {"season": season, "part": part, "closed": closed, "paid": paid,
            "marked": marked or {}, "lost": lost}


def run():
    add_source_to_path()
    import chaos_estimate as ce
    import settings_manager
    from ui.tabs import checklist_tab

    failures = []
    shipped = ce.SHIPPED[LIVE]
    marks_a_run = sum(amount * rate
                      for amount, rate in shipped["marks"].values())
    part2 = sum(shipped["bosses"][2].values())
    part3 = sum(shipped["bosses"][3].values())

    # 1. The shipped figures alone.
    want = 21 * part2 + 21 * part2 + 21 * part3 + 63 * marks_a_run
    got = ce.season_chaos(LIVE, [], [21, 21, 21], 1)
    if not math.isclose(got, want):
        failures.append(
            f"season 4 at one run a day comes to {got!r}, not {want!r}: "
            f"each part's bosses times its days -- the first part "
            f"borrowing the second's -- plus the marks a run meets over "
            f"all 63 days.")
    doubled = ce.season_chaos(LIVE, [], [21, 21, 21], 2)
    if not math.isclose(doubled, 2 * want):
        failures.append(f"two runs a day come to {doubled!r}, not twice "
                        f"one run's {want!r}.")

    # 2. Staleness, and the set-amount rules that follow it.
    for live, stale in (("disaster_s04", 0), ("disaster_s05", 0),
                        ("disaster_s06", 1), ("disaster_s07", 2),
                        ("mystery", 0)):
        if ce.staleness(live, "disaster_s04") != stale:
            failures.append(
                f"released in season 4, {live} reads "
                f"{ce.staleness(live, 'disaster_s04')} stale season(s), "
                f"not {stale}: a season counts once it has run whole "
                f"without an update.")

    def floor17(live, runs, stale):
        return ce.boss_table(live, 3, runs, None, ce.SHIPPED, stale)[17]

    fresh = [_run(LIVE, 3, [(17, 200)]), _run(LIVE, 3, [(17, 180)]),
             _run(LIVE, 3, [(17, 150)])]
    if floor17(LIVE, fresh, 0) != 190:
        failures.append(
            f"fresh, a part-3 floor 17 seen paying 200, 180 and 150 "
            f"settles at {floor17(LIVE, fresh, 0)!r}, not 190: the 150 "
            f"is a lower level and ignored, the rest averaged.")
    if floor17(LIVE, [_run(LIVE, 3, [(17, 150)])], 0) != 180:
        failures.append("fresh, a lower payout alone overruled the "
                        "shipped 180.")
    last = [_run("disaster_s05", 3, [(17, 200)]),
            _run("disaster_s04", 3, [(17, 260)])]
    if floor17("disaster_s06", last, 1) != 200:
        failures.append(
            f"one season stale, last season's 200 and a 260 from two "
            f"seasons back settle at "
            f"{floor17('disaster_s06', last, 1)!r}, not 200: last "
            f"season counts, the one before it does not.")
    if floor17("disaster_s06", last, 0) != 180:
        failures.append("fresh, last season's runs counted.")
    mixed = [_run("disaster_s07", 3, [(17, amount)])
             for amount in (150, 150, 180)]
    if floor17("disaster_s07", mixed, 2) != 160:
        failures.append(
            f"two seasons stale, 150, 150 and 180 settle at "
            f"{floor17('disaster_s07', mixed, 2)!r}, not their mean 160: "
            f"lower payouts count once the shipped one may be the stale "
            f"one.")
    mostly = [_run("disaster_s07", 3, [(17, 180)]) for _ in range(7)] + [
        _run("disaster_s07", 3, [(17, 150)]) for _ in range(3)]
    if floor17("disaster_s07", mostly, 2) != 180:
        failures.append(
            f"two seasons stale, seven 180s and three 150s settle at "
            f"{floor17('disaster_s07', mostly, 2)!r}, not 180: a highest "
            f"payout making {ce.TOP_SHARE:.0%} of them stands alone.")

    # 3. The rates.
    many = [_run("disaster_s07", 3, marked={"k5": 3}, closed=AFTER + i)
            for i in range(ce.RATE_RUNS)]
    rates, counted = ce.mark_rates("disaster_s07", many, ce.SHIPPED, 2, 0)
    if counted != ce.RATE_RUNS or rates.get("k5") != 3:
        failures.append(
            f"two seasons stale with {ce.RATE_RUNS} whole runs of three "
            f"Rare Species each, the rate reads {rates.get('k5')!r} over "
            f"{counted!r} runs, not 3 over {ce.RATE_RUNS}.")
    for stale, runs, why in (
            (1, many, "one season stale"),
            (2, many[1:], f"{ce.RATE_RUNS - 1} runs")):
        rates, counted = ce.mark_rates("disaster_s07", runs, ce.SHIPPED,
                                       stale, 0)
        if counted is not None:
            failures.append(f"{why}, the player's rates took over; both "
                            f"conditions have to hold.")
    early = ce.mark_rates("disaster_s07", many, ce.SHIPPED, 2,
                          AFTER + 1)[1]
    if early is not None:
        failures.append("runs from before the release counted towards "
                        "the player's rates.")
    events = ce.RATE_EVENTS
    try:
        ce.RATE_EVENTS = (("2026-01-01", "2099-01-01", "test"),)
        if ce.mark_rates("disaster_s07", many, ce.SHIPPED, 2, 0)[1]:
            failures.append("runs inside a RATE_EVENTS window counted "
                            "towards the player's rates.")
    finally:
        ce.RATE_EVENTS = events

    # 4. Lost runs.
    bosses = {17: 180, 34: 180, 37: 60}
    values = {"k5": 60, "e": 90}
    for lost, paid, whole, due, what in (
            ([37, "BOSS", "", 0], [(17, 180), (34, 180)], True, 60,
             "the hidden boss"),
            ([32, "BATTLE", "k5", 0], [(17, 180)], True, 60 + 180 + 60,
             "the last fight, a Rare Species"),
            ([17, "BOSS", "", 5], [], False, 0, "the first boss"),
            ([30, "BATTLE", "", 2], [(17, 180)], False, 0,
             "a fight with two more after it")):
        run_ = _run(LIVE, 3, paid, lost=lost)
        if ce.is_full(run_) != whole or ce.missed(run_, bosses,
                                                  values) != due:
            failures.append(
                f"a run lost on {what} reads whole={ce.is_full(run_)} "
                f"missing {ce.missed(run_, bosses, values)}, not "
                f"whole={whole} missing {due}.")

    # 5. The setting.
    for value, want in ((None, 1), ("2", 2), (1.5, 1.5), (0, 1), (-2, 1),
                        ("abc", 1), (float("nan"), 1), (float("inf"), 1),
                        (ce.MAX_RUNS_PER_DAY + 1, 1)):
        if ce.runs_per_day(value) != want:
            failures.append(f"chaos_runs_per_day {value!r} reads "
                            f"{ce.runs_per_day(value)!r}, not {want!r}.")
    layout = [key for key, _default in settings_manager.SettingsManager.LAYOUT]
    if layout[-2:] != ["#5", "chaos_runs_per_day"] or dict(
            settings_manager.SettingsManager.LAYOUT).get(
                "chaos_runs_per_day") != ce.DEFAULT_RUNS_PER_DAY:
        failures.append(
            "chaos_runs_per_day is not the last key of settings.json, "
            "under its own `#5` Settings without UI heading, defaulting "
            "to one run a day.")
    for runs, want in ((1, "1 lvl 8+ Chaos run/day"),
                       (2, "2 lvl 8+ Chaos runs/day")):
        if not checklist_tab.season_estimate_label(runs).startswith(want):
            failures.append(
                f"the tip's label at {runs} a day reads "
                f"{checklist_tab.season_estimate_label(runs)!r}.")
    return failures
