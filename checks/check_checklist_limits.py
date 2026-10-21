"""The Checklist's maximums follow the game client, and say when they part.

Every `<current>/<max>` on the tab counts up to a figure the game sets:
the day's Activity, the weekly currencies' caps, the Arkhianon Supply's
week and level, the Simulation Challenges, the Offensive's stars, the
Matrix's levels, the Chaos weekly score, the Great Rift's tier, an
Overclock's runs, and the days a season's shop pages open on. Three
ways this goes wrong with nothing to show for it:

1. **A table read wrong** puts a plausible number on a row: a cap of 0
   reads every holding as over it, a missing kind takes another's.
   Held on a synthetic client.
2. **The constant stands where the client spoke**, and a patch that
   raises a cap leaves the row finished early.
3. **The two part and nobody hears**: the tab reads the client's, so
   the constant a player without the client gets goes stale silently.
   `limit_mismatches` is what the launch tells the maintainer.

No Tk, no snapshot and no installed client needed.
"""

from ._harness import add_source_to_path

NAME = "the Checklist's maximums follow the game client"

NOW = 1792573894          # 2026-10-21 10:11 UTC
DAY = 24 * 3600


class _FakeClient:
    """Just enough of `game_client.Client` for `limits`."""

    def __init__(self, tables):
        self.tables = tables

    def rows(self, name):
        if name not in self.tables:
            raise KeyError(name)
        return self.tables[name]


def _client(gc):
    return _FakeClient({
        gc.ACTIVITY_TIERS: [{"id": "daily_0%d" % n, "point_count": str(p)}
                            for n, p in enumerate((20, 60, 120), 1)],
        gc.WEEKLY_CHARGES: [
            {"id": "2000027", "charge_type": "CHARGE_WEEK",
             "add_value": "5", "max": "5"},
            {"id": "2000036", "charge_type": "CHARGE_WEEK",
             "add_value": "3", "max": "10"},
            {"id": "2000099", "charge_type": "CHARGE_DAY",
             "add_value": "1", "max": "1"}],
        gc.PASS_TABLE: [
            {"id": "season_pass_009", "delete_flag": "NO",
             "mission_key": "pass_mission_009", "weekly_max_exp": "12000",
             "max_level": "80"},
            {"id": "season_pass_001", "delete_flag": "YES",
             "mission_key": "pass_mission_001", "weekly_max_exp": "1",
             "max_level": "1"}],
        gc.PASS_MISSIONS: (
            [{"id": "pass_mission_009_%02d" % n, "reset_type": "RESET_DAILY"}
             for n in range(1, 8)]
            + [{"id": "pass_mission_009_20", "reset_type": "RESET_WEEKLY"},
               {"id": "pass_mission_0090_01", "reset_type": "RESET_DAILY"},
               {"id": "pass_mission_001_01", "reset_type": "RESET_DAILY"}]),
        gc.SIMULATION_TABLE: [
            {"id": "content_boss", "limit_type": "LIMIT_WEEK",
             "limit_count": "4"},
            {"id": "content_growth", "limit_type": "NONE",
             "limit_count": "-1"}],
        gc.OFFENSIVE_DEFINES: [
            {"id": "remnants_boss_penalty_006",
             "ink_remnants_reward_key": "remnants_boss_reward"}],
        gc.OFFENSIVE_STAGES: [
            {"id": "remnants_boss_s06_0%d" % n,
             "link_remnants_boss_penalty_define_id":
                 "remnants_boss_penalty_006"} for n in range(1, 5)],
        gc.OFFENSIVE_REWARDS: [
            {"id": "remnants_boss_reward_%02d" % n,
             "total_star_count": str(n)} for n in range(1, 13)],
        gc.MATRIX_LISTS: [{"id": "zero_orb_5",
                           "link_zero_reward_key": "zero_orb5"}],
        gc.MATRIX_LEVELS: [{"id": "zero_orb5_%d" % n,
                            "reward_level": str(n)} for n in range(1, 121)],
        gc.DISASTER_SEASONS: [{"id": "disaster_s05",
                               "max_clear_score": "9000"}],
        gc.RIFT_TIERS: [{"total_reward": "50000"},
                        {"total_reward": "400000"}],
        gc.OVERCLOCK_TABLE: [
            {"id": "event_overclock_live_15", "limit_type": "LIMIT_DAY",
             "limit_count": "5"}],
        gc.DISASTER_CONSTANTS: [
            {"id": "unlock_disaster_shop_1", "value": "20"},
            {"id": "unlock_disaster_shop_2", "value": "41"},
            {"id": "season_drop_item", "value": "3920001,3920002"}],
    })


WANT = {
    "activity": 120,
    "charges": {"2000027": [5, 5], "2000036": [3, 10]},
    "passes": {"season_pass_009": [12000, 80, 7]},
    "simulation": {"content_boss": 4},
    "offensives": {"remnants_boss_penalty_006": [4, 12]},
    "matrix": {"zero_orb_5": 120},
    "disaster_weekly": {"disaster_s05": 9000},
    "rift_target": 400000,
    "overclocks": {"event_overclock_live_15": 5},
    "disaster_constants": {"unlock_disaster_shop_1": 20,
                           "unlock_disaster_shop_2": 41},
}


def _reader(gc):
    """`game_client.limits` on a synthetic client. Returns complaints."""
    client = _client(gc)
    got = gc.limits(client)
    out = []
    for kind, want in WANT.items():
        if got.get(kind) != want:
            out.append(
                f"the client's {kind!r} limit reads {got.get(kind)!r}, not "
                f"{want!r}. Each is read off its own table "
                f"(`game_client.limits`): a pass's dailies are its own "
                f"missions resetting daily, an Offensive's stars its "
                f"reward track's most, a retired pass none.")
    # One table missing costs its own kind and nothing else.
    del client.tables[gc.WEEKLY_CHARGES]
    try:
        partial = sorted(gc.limits(client))
    except Exception as exc:                    # noqa: BLE001
        partial = repr(exc)
    if not isinstance(partial, list) or "charges" in partial \
            or "activity" not in partial:
        out.append(
            f"with the weekly charges' table missing the limits read "
            f"{partial}: a kind whose table will not read is left out "
            f"alone, its constant standing, and the rest still read.")
    return out


def _snapshot():
    """The rows the maximums apply to, at their live ids."""
    return {
        "event_schedules": {
            "SEASON_PASS": {"season_pass_009": {
                "start_time": NOW - 20 * DAY, "end_time": NOW + 20 * DAY}},
            "DISASTER_SEASON": {"disaster_s05": {
                "start_time": NOW - 21 * DAY, "end_time": NOW + 63 * DAY}},
            "REMNANTS_BOSS_PENALTY": {"remnants_boss_penalty_006": {
                "start_time": NOW - DAY, "end_time": NOW + 20 * DAY}}},
        "season_pass_entity": {"res_id": "season_pass_009",
                               "week_exp": 11000, "free_reward_rank": 75},
        "zero_orb_entity": {"reward_list_id": "zero_orb_5",
                            "reward_level": 100},
        "stage_limit_entities": {"content_boss": {"count": 1,
                                                  "reset_time": NOW}},
        "mission_entities": {},
        "characters": {"currencies": {"2000036": {"amount": 9}}},
    }


def _rows(ct, gc):
    """The rows read the client's maximums, and the constants without.
    Returns complaints."""
    out = []
    try:
        gc.use({"limits": WANT})
        got = ct._readings(_snapshot(), NOW)
        for key, want in (("supply_weekly", "11000/12000"),
                          ("supply_season", "75/80"),
                          ("simulation", "3/4"),
                          ("matrix", "100/120"),
                          ("sortie_currency", "9/10")):
            if not got.get(key) or got[key][0][0] != want:
                out.append(
                    f"with the client's maximums the {key!r} row reads "
                    f"{(got.get(key) or [[None]])[0][0]!r}, not {want}: the "
                    f"row counts up to the client's figure for the id the "
                    f"snapshot has live, where it states one.")
        gc.use(None)
        got = ct._readings(_snapshot(), NOW)
        for key, want in (("supply_weekly", "%d/%d" % (
                min(11000, ct.PASS_WEEK_EXP_FULL), ct.PASS_WEEK_EXP_FULL)),
                          ("matrix", "100/%d" % ct.MATRIX_LEVELS)):
            if not got.get(key) or got[key][0][0] != want:
                out.append(
                    f"with no client read the {key!r} row reads "
                    f"{(got.get(key) or [[None]])[0][0]!r}, not {want}: the "
                    f"module's own figure stands where the client says "
                    f"nothing.")
    finally:
        gc.use(None)
    return out


def _overclock(ct, gc):
    """An Overclock's cap is the client's where it holds the event."""
    live = {"start_time": NOW - DAY, "end_time": NOW + 10 * DAY}
    raw = {"overclock_entities": {"event_overclock_live_15": {
        "res_id": "event_overclock_live_15", "count": 3, "reset_time": NOW}}}
    try:
        gc.use({"limits": WANT})
        got = ct._event_overclock(raw, "event_overclock_live_15", live, NOW)
    finally:
        gc.use(None)
    if not got or got[0][0] != "3/5":
        return [f"an Overclock the client caps at 5, three runs taken, "
                f"read {got!r}, not 3/5: the client's `limit_count` is the "
                f"day's cap, ahead of the shapes past events ran at."]
    return []


def _pages(ct, gc):
    """A season's shop pages open on the client's day offsets."""
    raw = _snapshot()
    start = raw["event_schedules"]["DISASTER_SEASON"]["disaster_s05"][
        "start_time"]
    try:
        gc.use({"limits": WANT})
        got = ct._client_rounds(raw, "disaster_s05")
    finally:
        gc.use(None)
    want = [start + 20 * DAY, start + 41 * DAY]
    if got != want:
        return [f"the season's pages open at {got}, not {want}: page n "
                f"opens `unlock_disaster_shop_<n>` days after the season's "
                f"schedule (`_client_rounds`), which is what the game's "
                f"`arrives after` popup counts."]
    return []


def _mismatches(ct, gc):
    """`limit_mismatches` names each figure the client states otherwise,
    and nothing where they agree. Returns complaints."""
    out = []
    agreeing = {
        "activity": ct.ACTIVITY_FULL,
        "passes": {"season_pass_009": [ct.PASS_WEEK_EXP_FULL,
                                       ct.PASS_LEVEL_FULL,
                                       ct.PASS_DAILY_COUNT],
                   "season_pass_ch_002": [1, 1, 1]},
        "simulation": {ct.SIMULATION_STAGE: ct.SIMULATION_RUNS}}
    try:
        gc.use({"limits": agreeing})
        quiet = ct.limit_mismatches()
        gc.use({"limits": WANT})
        loud = ct.limit_mismatches(_snapshot(), NOW)
    finally:
        gc.use(None)
    if quiet:
        out.append(
            f"limit_mismatches named {quiet} where the client agrees with "
            f"every constant -- the Chinese server's pass (`_ch_`) runs its "
            f"own figures and is no mismatch.")
    for word in ("ACTIVITY_FULL", "PASS_WEEK_EXP_FULL (season_pass_009)",
                 "SIMULATION_RUNS", "SORTIE_CAP", "MATRIX_LEVELS (zero_orb_5)",
                 "OFFENSIVE_BOSSES (remnants_boss_penalty_006)",
                 "GREAT_RIFT_TARGET"):
        if not any(line.startswith(word + ":") for line in loud):
            out.append(
                f"limit_mismatches did not name {word} where the client "
                f"states another figure: {loud}. The tab reads the "
                f"client's, so a constant left behind goes stale with "
                f"nothing to say so.")
    return out


def run():
    add_source_to_path()
    import game_client as gc
    from ui.tabs import checklist_tab as ct

    failures = []
    failures.extend(_reader(gc))
    failures.extend(_rows(ct, gc))
    failures.extend(_overclock(ct, gc))
    failures.extend(_pages(ct, gc))
    failures.extend(_mismatches(ct, gc))
    return failures


# What this check must catch, for `checks/faults.py`.
FAULTS = [
    ("a retired pass read", "game_client:_passes",
     'if row.get("delete_flag") == "YES":', "if False:",
     "a retired pass none"),
    ("one missing table losing them all", "game_client:limits",
     "except (KeyError, ValueError, TypeError):\n            continue",
     "except ():\n            continue", "left out alone"),
    ("the pass's limits not the client's", "ui.tabs.checklist_tab:_pass_limits",
     'stated = _limit("passes", pass_id) if pass_id else None',
     "stated = None", "for the id the snapshot has live"),
    ("the Overclock's stated cap ignored",
     "ui.tabs.checklist_tab:_event_overclock",
     'stated = _limit("overclocks", name)', "stated = None",
     "ahead of the shapes"),
    ("the pages not dated off the client",
     "ui.tabs.checklist_tab:_client_rounds",
     "    if not _is_count(start):\n        return None",
     "    return None", "`arrives after` popup"),
    ("a mismatch not told", "ui.tabs.checklist_tab:limit_mismatches",
     "if theirs is not None and theirs != ours:", "if False:",
     "goes stale with nothing to say so"),
    ("the Chinese server's figures told", "ui.tabs.checklist_tab:"
     "limit_mismatches", 'if "_ch" not in key', "if key",
     "runs its own figures"),
]
