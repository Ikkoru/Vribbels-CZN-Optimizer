"""The season estimate's Chaos share, and when a player's own runs
overrule the figures the program shipped with (`chaos_estimate`).

Every rule here changes a number on the seasonal shop's tip and nothing
else, so a broken one reads as a plausible figure:

1. **The shipped figures add up as the module says**: bosses by part
   and day, a part never measured borrowing its neighbour's, and the
   marks a run meets over every day, every payout at its part's
   amplification nodes but a `flat` boss's, all times the runs a day.
2. **A payout is base plus 1% a node, rounded up**, and reads back to
   the one base it came from.
3. **A part's nodes**: the season's tree, carried past the parts it
   lists by the season before; a season with none takes that one's
   whole; the shipped `nodes` where the client has no tree; a part's
   own runs raising it to the most one had, of the season's own tree
   alone. A season dated by nothing runs as many parts.
4. **The player's payouts are read at their own run's nodes**, or at
   their part's count where the run kept no effects, so runs at
   different nodes agree on one base.
5. **Staleness is counted in whole seasons**, and the rules follow it:
   a lower payout is ignored while the program is fresh, last season's
   runs join after one stale season, lower payouts count after two
   unless the highest makes `TOP_SHARE` of them.
6. **The player's rates take over on rule 4's two conditions** --
   two stale seasons AND `RATE_RUNS` whole runs since the release, none
   inside a `RATE_EVENTS` window -- **or rule 5's**: a season no
   figures were shipped for, and `UNSHIPPED_RATE_RUNS` whole runs of it.
7. **A lost run is whole only when a boss had paid and no non-boss
   fight was left**, and then misses its own fight's payout and every
   boss after it.
8. **Only the live season's own Chaos counts**: a past season's, entered
   through the Zero System, pays the live currency at other amounts.
9. **`chaos_runs_per_day` reads as a sane number or not at all**, sits
   at the foot of settings.json under its `#5` heading, and names
   itself in the tip's label.
10. **The client's tree is read by part** (`game_client.season_nodes`):
    a part's count takes in the parts before it, the nodes the client
    has rows for, amplification nodes alone.

The client's trees are put in place for the run with `game_client.use`
and the shipped extract's taken away, so the cases read the same on any
machine.
"""

import math

from ._harness import add_source_to_path

NAME = "the Chaos estimate follows its rules"

LIVE = "disaster_s04"
DAY = 86400
AFTER = 1790000000          # a clear time after the release
TREES = {"disaster_s04": [13, 19, 25], "disaster_s05": [13]}


def _run(season, part, bosses=(), marks=(), marked=None, lost=None,
         closed=AFTER, nodes=0, other=()):
    """A run in the capture's record shape, with `nodes` of its own
    season's amplification nodes in force, and `other` effects besides;
    `nodes` None for a run filed before runs kept their effects."""
    import game_client
    number = int(season.rsplit("_s", 1)[1])
    paid = [[floor, "BOSS", "", 1, amount] for floor, amount in bosses]
    paid += [[5, "BATTLE", mark, 1, amount] for mark, amount in marks]
    run = {"season": season, "part": part, "closed": closed, "paid": paid,
           "marked": marked or {}, "lost": lost}
    if nodes is not None:
        run["effects"] = [[game_client.AMPLIFY_GROUP,
                           "zero_season_s%d_skill_%03d_001" % (number, n), [1]]
                          for n in range(nodes)] + list(other)
    return run


def _ceil(base, nodes):
    """1% a node, rounded up, worked in whole numbers."""
    return -(-base * (100 + nodes) // 100)


def _sums(ce, table):
    """1: the shipped figures alone, season 4 at one run and two a day."""
    failures = []
    shipped = table[LIVE]
    flat = set(shipped["flat"])
    want = 0
    for part, nodes in zip((1, 2, 3), TREES[LIVE]):
        bosses = shipped["bosses"][max(part, 2)]
        want += 21 * (sum(amount if floor in flat else _ceil(amount, nodes)
                          for floor, amount in bosses.items())
                      + sum(_ceil(amount, nodes) * rate
                            for amount, rate in shipped["marks"].values()))
    got = ce.season_chaos(LIVE, [], [21, 21, 21], 1, shipped=table)
    if not math.isclose(got, want):
        failures.append(
            f"season 4 at one run a day comes to {got!r}, not {want!r}: "
            f"each part's bosses times its days -- the first part "
            f"borrowing the second's -- plus the marks a run meets, every "
            f"payout at its part's nodes (13, 19, 25), the floor-37 boss "
            f"at base.")
    doubled = ce.season_chaos(LIVE, [], [21, 21, 21], 2, shipped=table)
    if not math.isclose(doubled, 2 * want):
        failures.append(f"two runs a day come to {doubled!r}, not twice "
                        f"one run's {want!r}.")
    return failures


def _payouts(ce):
    """2: a payout at n nodes, and back."""
    failures = []
    for base, nodes, paid in ((144, 5, 152), (48, 5, 51), (144, 19, 172),
                              (144, 25, 180), (48, 25, 60), (72, 25, 90),
                              (144, 0, 144)):
        if ce.amplified(base, nodes) != paid or ce.base_of(paid, nodes) != base:
            failures.append(
                f"{base} at {nodes} nodes pays {ce.amplified(base, nodes)!r} "
                f"and reads back as {ce.base_of(paid, nodes)!r}, not {paid} "
                f"and {base}: 1% a node, rounded up, as every captured "
                f"payout is.")
    off = [(base, nodes) for base in range(0, 400) for nodes in range(0, 40)
           if ce.base_of(ce.amplified(base, nodes), nodes) != base]
    if off:
        failures.append(f"a payout reads back to another base: {off[:5]}.")
    return failures


def _nodes(ce, game_client, from_client):
    """3: a part's nodes."""
    failures = []

    def nodes(live, parts, runs=(), shipped=None):
        return ce.season_nodes(live, parts, runs, None,
                               ce.SHIPPED if shipped is None else shipped)

    for live, runs, want, what in (
            ("disaster_s05", (), [13, 19, 25],
             "season 5's tree lists part 1, and parts 2 and 3 add what "
             "season 4's did"),
            ("disaster_s06", (), [13, 19, 25],
             "a season with no tree takes season 5's, extended"),
            ("disaster_s05", [_run("disaster_s05", 1, nodes=15)],
             [15, 19, 25], "a part-1 run at 15 nodes raises part 1"),
            ("disaster_s05", [_run("disaster_s05", 1, nodes=21)],
             [21, 21, 25], "a part never holds fewer than the one before"),
            ("disaster_s05",
             [_run("disaster_s05", 1, nodes=2, other=[
                 [game_client.AMPLIFY_GROUP, "zero_season_s4_skill_%03d_001"
                  % n, [1]] for n in range(20)])],
             [13, 19, 25], "season 4's tree, carried into a run, raises "
                           "nothing of season 5's")):
        got = nodes(live, 3, runs)
        if got != want:
            failures.append(f"{live}'s parts read {got} nodes, not {want}: "
                            f"{what} (`season_nodes`).")
    held = from_client.SEASON_NODES if hasattr(from_client,
                                               "SEASON_NODES") else None
    try:
        from_client.SEASON_NODES = {}
        game_client.use({"format": game_client.CACHE_FORMAT})
        got = nodes("disaster_s05", 3,
                    shipped={"disaster_s04": {"nodes": (10, 14)},
                             "disaster_s05": {"nodes": (12,)}})
        if got != [12, 16, 16]:
            failures.append(f"with no client tree, season 5 reads {got}, not "
                            f"[12, 16, 16]: the shipped `nodes`, carried by "
                            f"season 4's, the last part holding its count.")
        if nodes("disaster_s05", 2, shipped={}) != [0, 0]:
            failures.append("with no tree anywhere, a part holds nodes.")
    finally:
        if held is None:
            del from_client.SEASON_NODES
        else:
            from_client.SEASON_NODES = held
        game_client.use({"format": game_client.CACHE_FORMAT,
                         "season_nodes": TREES})
    if ce.parts_shipped("disaster_s05") != 3:
        failures.append(
            f"season 5, its tree listing one part, is given "
            f"{ce.parts_shipped('disaster_s05')} part(s) where nothing dates "
            f"them, not season 4's 3.")
    return failures


def _base_reading(ce, table):
    """4: the player's payouts at their own nodes."""
    failures = []
    seen = [_run(LIVE, 3, [(17, 152), (37, 60)], nodes=5),
            _run(LIVE, 3, [(17, 163), (37, 60)], nodes=13)]
    got = ce.boss_table(LIVE, 3, seen, None, table, 0)
    if got.get(17) != 144 or got.get(37) != 60:
        failures.append(
            f"runs paying 152 at 5 nodes and 163 at 13 settle at {got}: "
            f"both are 144 at base, and the flat floor-37 boss 60 as paid "
            f"(`base_of` in `boss_table`).")
    old = ce.boss_table(LIVE, 3, [_run(LIVE, 3, [(17, 180)], nodes=None)],
                        None, table, 0)
    if old.get(17) != 144:
        failures.append(
            f"a part-3 run that kept no effects, paying 180, settles at "
            f"{old.get(17)!r}: it reads at its part's 25 nodes, 144 at base.")
    marks = ce.mark_values(LIVE, [_run(LIVE, 3, marks=[("k5", 51)], nodes=5),
                                  _run(LIVE, 3, marks=[("k5", 60)], nodes=25)],
                           table, 0)
    if marks.get("k5") != 48:
        failures.append(f"Rare Species paying 51 at 5 nodes and 60 at 25 "
                        f"settle at {marks.get('k5')!r}, not their base 48.")
    return failures


def _staleness(ce, table):
    """5: staleness and the set-amount rules that follow it."""
    failures = []
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
        return ce.boss_table(live, 3, runs, None, table, stale)[17]

    fresh = [_run(LIVE, 3, [(17, 170)]), _run(LIVE, 3, [(17, 150)]),
             _run(LIVE, 3, [(17, 120)])]
    if floor17(LIVE, fresh, 0) != 160:
        failures.append(
            f"fresh, a part-3 floor 17 seen paying 170, 150 and 120 at base "
            f"settles at {floor17(LIVE, fresh, 0)!r}, not 160: the 120 is "
            f"a lower level and ignored, the rest averaged.")
    if floor17(LIVE, [_run(LIVE, 3, [(17, 120)])], 0) != 144:
        failures.append("fresh, a lower payout alone overruled the "
                        "shipped 144.")
    past = _run(LIVE, 3, [(17, 200)], marked={"k5": 9})
    past.update(via="zero_orb", stage=60000)
    if floor17(LIVE, [past], 0) != 144 or ce.mark_rates(
            LIVE, [past] * ce.RATE_RUNS, table, 2, 0)[1] is not None:
        failures.append(
            "a run of a past season's Chaos, entered through the Zero "
            "System, moved the live Chaos's figures. It pays the live "
            "currency at other amounts, and the estimate is of the live "
            "Chaos alone.")
    for run_, name in ((past, "Burning Life"),
                       (_run(LIVE, 3), "The Kaleidoscope Hatchery")):
        if ce.chaos_name(run_) != name:
            failures.append(f"a run reads as Chaos {ce.chaos_name(run_)!r}, "
                            f"not {name!r}.")
    last = [_run("disaster_s05", 3, [(17, 200)]),
            _run("disaster_s04", 3, [(17, 260)])]
    if floor17("disaster_s06", last, 1) != 200:
        failures.append(
            f"one season stale, last season's 200 and a 260 from two "
            f"seasons back settle at "
            f"{floor17('disaster_s06', last, 1)!r}, not 200: last "
            f"season counts, the one before it does not.")
    if floor17("disaster_s06", last, 0) != 144:
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
    return failures


def _rates(ce, table):
    """6: rules 4 and 5."""
    failures = []
    # Season 7 is shipped here, so rule 5 stays out of rule 4's cases.
    shipped = dict(table, disaster_s07=table[LIVE])
    many = [_run("disaster_s07", 3, marked={"k5": 3}, closed=AFTER + i)
            for i in range(ce.RATE_RUNS)]
    rates, counted = ce.mark_rates("disaster_s07", many, shipped, 2, 0)
    if counted != ce.RATE_RUNS or rates.get("k5") != 3:
        failures.append(
            f"two seasons stale with {ce.RATE_RUNS} whole runs of three "
            f"Rare Species each, the rate reads {rates.get('k5')!r} over "
            f"{counted!r} runs, not 3 over {ce.RATE_RUNS}.")
    for stale, runs, why in (
            (1, many, "one season stale"),
            (2, many[1:], f"{ce.RATE_RUNS - 1} runs")):
        rates, counted = ce.mark_rates("disaster_s07", runs, shipped,
                                       stale, 0)
        if counted is not None:
            failures.append(f"{why}, the player's rates took over; both "
                            f"conditions have to hold.")
    early = ce.mark_rates("disaster_s07", many, shipped, 2,
                          AFTER + 1)[1]
    if early is not None:
        failures.append("runs from before the release counted towards "
                        "the player's rates.")
    events = ce.RATE_EVENTS
    try:
        ce.RATE_EVENTS = (("2026-01-01", "2099-01-01", "test"),)
        if ce.mark_rates("disaster_s07", many, shipped, 2, 0)[1]:
            failures.append("runs inside a RATE_EVENTS window counted "
                            "towards the player's rates.")
    finally:
        ce.RATE_EVENTS = events

    enough = many[:ce.UNSHIPPED_RATE_RUNS]
    rates, counted = ce.mark_rates("disaster_s07", enough, table, 0, 0)
    if counted != ce.UNSHIPPED_RATE_RUNS or rates.get("k5") != 3:
        failures.append(
            f"a season no figures were shipped for, with "
            f"{ce.UNSHIPPED_RATE_RUNS} whole runs of it, reads "
            f"{rates.get('k5')!r} Rare Species a run over {counted!r} runs, "
            f"not its own 3: the borrowed rates are another map's (rule 5).")
    for runs, figures, why in (
            (enough[1:], table, f"{ce.UNSHIPPED_RATE_RUNS - 1} runs"),
            (enough, shipped, "a season shipped figures cover")):
        counted = ce.mark_rates("disaster_s07", runs, figures, 0, 0)[1]
        if counted is not None:
            failures.append(f"{why}: the player's rates took over under "
                            f"rule 5.")
    return failures


def _lost(ce):
    """7: lost runs."""
    failures = []
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
    return failures


def _setting(ce):
    """9: the setting."""
    import settings_manager
    from ui.tabs import checklist_tab
    failures = []
    for value, want in ((None, 1), ("2", 2), (1.5, 1.5), (0, 1), (-2, 1),
                        ("abc", 1), (float("nan"), 1), (float("inf"), 1),
                        (ce.MAX_RUNS_PER_DAY + 1, 1)):
        if ce.runs_per_day(value) != want:
            failures.append(f"chaos_runs_per_day {value!r} reads "
                            f"{ce.runs_per_day(value)!r}, not {want!r}.")
    layout = [key for key, _default in settings_manager.SettingsManager.LAYOUT]
    headings = [i for i, key in enumerate(layout) if key.startswith("#")]
    if (layout[headings[-1]] != "#5" or "chaos_runs_per_day"
            not in layout[headings[-1]:] or dict(
                settings_manager.SettingsManager.LAYOUT).get(
                    "chaos_runs_per_day") != ce.DEFAULT_RUNS_PER_DAY):
        failures.append(
            "chaos_runs_per_day is not at the foot of settings.json, under "
            "its last heading, `#5` Settings without UI, defaulting to one "
            "run a day.")
    for runs, want in ((1, "1 lvl 8+ Chaos run/day"),
                       (2, "2 lvl 8+ Chaos runs/day")):
        if not checklist_tab.season_estimate_label(runs).startswith(want):
            failures.append(
                f"the tip's label at {runs} a day reads "
                f"{checklist_tab.season_estimate_label(runs)!r}.")
    return failures


def _client_tree(game_client):
    """10: the client's tree read by part, off a stand-in client."""
    group = game_client.AMPLIFY_GROUP
    rows = {
        game_client.ZERO_EFFECTS_TABLE: [
            {"id": "amp", "zero_eff": group},
            {"id": "other", "zero_eff": "ZERO_ENCOUNTER_RATEUP"}],
        game_client.SEASON_SKILLS_TABLE: [
            {"id": "s_amp", "link_zero_system_eff_id": "[amp]"},
            {"id": "s_other", "link_zero_system_eff_id": "[other]"}],
        game_client.SEASON_NODES_TABLE: [
            {"id": "disaster_s09_skilltree_%d" % n, "node_num": "n_%d" % n,
             "link_zero_orb_season_skill_id":
                 "[s_amp]" if n in (2, 3, 5, 6, 8) else "[s_other]"}
            for n in range(1, 9)],
        game_client.SEASON_LAYOUTS_TABLE: [
            {"id": "ds_s09_skilltree_circle_1",
             "line_1_node_num_list": "[1,2,3]",
             "line_2_node_num_list": "[3,4]"},
            {"id": "ds_s09_skilltree_circle_2",
             "line_1_node_num_list": "[3,4,5,6]"},
            {"id": "ds_s09_skilltree_circle_2_uk",
             "line_1_node_num_list": "[8]"},
            {"id": "ds_s09_skilltree_circle_3",
             "line_1_node_num_list": "[1,2,3,4,5,6,7,9]"}],
    }

    class _Client:
        def rows(self, name):
            return rows.get(name, [])

    got = game_client.season_nodes(_Client())
    if got != {"disaster_s09": [2, 4, 4]}:
        return [f"a tree whose layouts list nodes 1-4, then 3-6, then 1-7 "
                f"and a number with no row, amplification on 2, 3, 5, 6 and "
                f"the unlisted 8, reads {got}, not [2, 4, 4]: each part "
                f"counts what its layout and those before it list, "
                f"amplification nodes with rows alone, a `_uk` layout none."]
    return []


def run():
    add_source_to_path()
    import chaos_estimate as ce
    import game_client
    from game_data import from_client

    held = game_client._facts
    failures = []
    try:
        game_client.use({"format": game_client.CACHE_FORMAT,
                         "season_nodes": TREES})
        # The cases are read against season 4's figures alone: a later
        # season shipped beside it becomes the one every season after it
        # starts from, which is a reading of the table, not of the rules.
        table = {LIVE: ce.SHIPPED[LIVE]}
        failures += _sums(ce, table)
        failures += _payouts(ce)
        failures += _nodes(ce, game_client, from_client)
        failures += _base_reading(ce, table)
        failures += _staleness(ce, table)
        failures += _rates(ce, table)
        failures += _lost(ce)
        failures += _setting(ce)
        failures += _client_tree(game_client)
    finally:
        game_client.use(held)
    return failures


# What this check must catch, for `checks/faults.py`.
FAULTS = [
    ("a payout amplified without rounding up", "chaos_estimate:amplified",
     "return math.ceil(round(amount * (100 + nodes) / 100, 6))",
     "return amount * (100 + nodes) // 100", "at 5 nodes pays"),
    ("the player's payouts taken as base", "chaos_estimate:boss_table",
     "else base_of(amount, nodes))", "else amount)",
     "runs paying 152 at 5 nodes"),
    ("a mark's payouts taken as base", "chaos_estimate:mark_values",
     "seen[mark].append(base_of(amount, nodes))",
     "seen[mark].append(amount)", "Rare Species paying 51"),
    ("the flat boss amplified", "chaos_estimate:season_chaos",
     "bosses = sum(amount if floor in flat else amplified(amount, held)",
     "bosses = sum(amplified(amount, held)", "the floor-37 boss at base"),
    ("another season's tree counted", "chaos_estimate:run_nodes",
     "if entry[0] == AMPLIFY_GROUP and own and int(own.group(1)) == number:",
     "if entry[0] == AMPLIFY_GROUP:", "raises nothing of season 5's"),
    ("a part past the tree not carried by the season before",
     "chaos_estimate:_extended",
     "own.append(own[-1] + before[part - 1] - before[part - 2])",
     "own.append(own[-1])", "parts 2 and 3 add what"),
    ("a season with no tree left at nothing", "chaos_estimate:_extended",
     "if not own:\n        return before",
     "if not own:\n        return []", "a season with no tree takes"),
    ("a part's runs not raising its count", "chaos_estimate:season_nodes",
     "out.append(max(count, seen.get(part, 0), out[-1] if out else 0))",
     "out.append(count)", "a part-1 run at 15 nodes"),
    ("a run with no effects read at base", "chaos_estimate:_nodes_of",
     "return tree[min(part, len(tree)) - 1]", "return 0",
     "kept no effects"),
    ("rule 5 never applied", "chaos_estimate:mark_rates",
     "if unshipped and run.get(\"season\") == live]", "if False]",
     "rule 5"),
    ("rule 5 for a shipped season", "chaos_estimate:mark_rates",
     "unshipped = live not in shipped", "unshipped = True",
     "a season shipped figures cover"),
    ("an undated season given its measured parts alone",
     "chaos_estimate:parts_shipped",
     "return max(measured, len(_extended(live, shipped)))",
     "return measured", "not season 4's 3"),
    ("the shipped nodes passed over", "chaos_estimate:_tree",
     'return list((shipped.get(season) or {}).get("nodes") or ())',
     "return []", "with no client tree"),
    ("a part's layout read alone", "game_client:season_nodes",
     "shown |= parts[part]", "shown = set(parts[part])",
     "each part counts what its layout"),
    ("a node with no row counted", "game_client:season_nodes",
     "counts.append(sum(1 for number in shown if held.get(number)))",
     "counts.append(sum(1 for number in shown if held.get(number, True)))",
     "amplification nodes with rows alone"),
]
