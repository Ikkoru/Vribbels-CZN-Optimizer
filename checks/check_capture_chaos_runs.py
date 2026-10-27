"""What the capture records of a Chaos run, and where it keeps them.

`docs/chaos_runs.py` and the Checklist's season estimate read these
records, and everything they report stands on them. Each part fails
quietly:

1. **A payout is the drop the player takes**, in the season's currency
   group. Another item in the same drop is not one.
2. **A fight's mark is noted whether or not it paid** -- a
   `keyword_tag`, a battle id ending `_e`, a break-in -- since how often
   a mark turns up is counted over the fights fought. A break-in is a
   fight of its own spot, `BREAK_IN`, so it does not swell the ordinary
   fights a rate is taken over.
3. **The run names its season** from the season schedule, the Great
   Rift standings only where no window holds it, and its game version
   from the connection's `helo`. A new season's currency is a new item
   id, and nothing downstream is told which. The standings alone name
   the season before until the new season's Great Rift opens.
4. **A run is filed once**, by the second it cleared, however often
   the same clear is read.
5. **The runs live in their own file** (`chaos_store`), every one of
   them: the snapshot no longer carries them, a new capture reads them
   back, runs an older snapshot still carries are folded in, a copy
   that loses a run on its way to disk is refused, and a file that will
   not read is served from its backup.
6. **A run names its season part**, off the schedules: a past season's
   parts cannot be dated once it is over, and the estimate's rules read
   last season's runs by part.
7. **A lost run says where**, and how many non-boss fights its map had
   left -- whether it counts as whole turns on that. An accelerated
   fight says so in its reply, one played by hand in what the client
   sends (`websocket_debug_20260926_214843`).
8. **A run says which Chaos, by which door, and how it was played**:
   the stage id its clear names, `disaster`, `zero_orb` or `chaos`, and
   whether the Delegation Module played it -- said only in what the
   client sent to open it (`websocket_debug_20260927_202839`). A past
   season's Chaos pays less, and the estimate must leave it out. A
   base-game Chaos entered from its own screen is a run of its own.
9. **A run left by an escape is never a whole one**: its close says
   `GIVEUP`, and no lost fight says anything.
10. **A run says what its entry said it was**: the Chaos's id, the
    difficulty, a Zero System map's codex, every effect in force, and
    each mark by the spot it was met on.
11. **A run says which partners it took, at which limit break**: off
    the entry, or the stage a run no capture saw enter is taken up
    from. Their Exploration Passives are not among the effects, and
    the table's Invasion raise is read off them alone.

Synthetic frames in the shapes of those captures. No Tk and no
snapshot needed.
"""

import gzip
import json
import tempfile
from pathlib import Path

from ._harness import add_source_to_path
from .check_capture_history import _Flow, _addon_class

NAME = "capture records Chaos runs"

CURRENCY = 3920031
EXPECTED_PAID = [[6, "BATTLE", "k5", CURRENCY, 60],
                 [17, "BOSS", "", CURRENCY, 180]]
DELEGATED = {"chaos_info": {"acceleration_info": {
    "enabled": True, "cost_currency_id": 2000048}}}


class _Steps:
    """Request-and-reply pairs, each on its own qid."""

    def __init__(self, addon, first):
        self.addon, self.qid = addon, first

    def ask(self, command, params=None):
        self.qid += 1
        family, _, inner = command.partition("/")
        self.addon.websocket_message(_Flow([{
            "cmd": family, "qid": self.qid,
            "params": {"cmd": inner, **(params or {})}}], from_client=True))

    def answer(self, **reply):
        self.addon.websocket_message(_Flow([{"res": "ok", "qid": self.qid,
                                             **reply}]))

    def step(self, command, params=None, **reply):
        self.ask(command, params)
        self.answer(**reply)

    def fight(self, floor, spot, battle, **marks):
        self.step("stage/enter_spot", spot_info={"floor": floor,
                                                 "spot_type": spot})
        self.step("battle/battle_start", snapshot={"cache": {
            "battle_init_wt": {"battle_res_id": battle, "floor": floor,
                               **marks}}})


def _play(addon, closed):
    """The live season's Chaos, by the Delegation Module: a marked fight
    that pays, a marked one that does not, and a boss."""
    steps = _Steps(addon, 100)
    steps.step("disaster/enter_disaster_chaos_stage", DELEGATED,
               service_server_time=closed - 1800)
    steps.fight(6, "SPOT_TYPE_BATTLE", "base_00160", keyword_tag=[5, 5])
    steps.step("spot_reward/get_drop_item", drop_item_result=[
        {"id": CURRENCY, "amount": 60, "group": "disaster_material"},
        {"id": 3000005, "amount": 3, "group": "chaos_orb"}])
    steps.fight(25, "SPOT_TYPE_BATTLE", "base_00167_e")
    steps.fight(17, "SPOT_TYPE_BOSS", "base_00000")
    steps.step("spot_reward/get_drop_item", drop_item_result=[
        {"id": CURRENCY, "amount": 180, "group": "disaster_material"}])
    steps.step("stage/clear_stage", service_server_time=closed,
               stage_id=80000)


def _play_zero(addon, closed):
    """A past season's Chaos, played by hand through the Zero System: a
    fight, and Senectus breaking in on its spot."""
    steps = _Steps(addon, 300)
    steps.step("zero_orb/enter_zero_stage", {"is_psychosis_mode": True},
               service_server_time=closed - 3600)
    steps.fight(28, "SPOT_TYPE_BATTLE", "base_00013")
    steps.step("battle/battle_start", snapshot={"cache": {
        "battle_init_wt": {"battle_res_id": "base_00243", "floor": 28,
                           "break_in": True, "break_in_res_id": "bi_0001",
                           "spot_type": "SPOT_TYPE_ELITE"}}})
    steps.step("stage/clear_stage", service_server_time=closed,
               stage_id=60000)


def _play_delegated_break_in(addon, closed, told_twice):
    """The live Chaos by the Delegation Module, Senectus breaking in on
    a fight: no battle_start of its own, only the reply resolving it
    (`websocket_debug_20260928_003350`) -- or, `told_twice`, both."""
    steps = _Steps(addon, 700)
    steps.step("disaster/enter_disaster_chaos_stage", DELEGATED,
               service_server_time=closed - 1800)
    steps.fight(6, "SPOT_TYPE_BATTLE", "base_00159")
    steps.step("battle/acceleration_resolve", battle_res_id="base_00159",
               seed=1, game_result="BATTLE_RESULT_TYPE_REWARD")
    senectus = {"battle_res_id": "base_00242", "seed": 2, "break_in": True,
                "break_in_res_id": "bi_0001", "spot_type": "SPOT_TYPE_ELITE"}
    if told_twice:
        steps.step("battle/battle_start",
                   snapshot={"cache": {"battle_init_wt": senectus}})
    steps.step("battle/acceleration_resolve",
               game_result="BATTLE_RESULT_TYPE_REWARD", **senectus)
    steps.step("stage/clear_stage", service_server_time=closed,
               stage_id=80000)


def _setup(addon):
    """A connection's `helo`, the standings that name the season, and
    the schedules that date its parts: season 4's, as the wire had it."""
    addon.websocket_message(_Flow([{"cmd": "helo", "params": {
        "device_data": {"client_version": "cznlive 1.464",
                        "patch_version": '{"res":688,"media":227}'}}}],
        from_client=True))
    addon.websocket_message(_Flow([{"res": "ok",
                                    "disaster_boss_rank_entities": {
        "disaster_s03": {"disaster_s03_rank_02": {"score_week_id": 170}},
        "disaster_s04": {"disaster_s04_rank_02": {"score_week_id": 193}},
    }}]))
    addon.websocket_message(_Flow([{"res": "ok", "event_schedules": {
        "DISASTER_SEASON": {"disaster_s04": {
            "start_time": 1783476000, "end_time": 1790726400}},
        "ASSAULT_SCHEDULE": {
            "assault_1_s4": {"start_time": 1783476000,
                             "end_time": 1785283200},
            "assault_1_s5": {"start_time": 1785290400,
                             "end_time": 1787097600},
            "assault_1_s6": {"start_time": 1787101200,
                             "end_time": 1788912000},
            "assault_1_s7": {"start_time": 1788915600,
                             "end_time": 1790726400}},
    }}]))


# The second half of a map as the enter_spot reply carries it: the
# floors from the first boss to the last, one spot each.
MAP = ([(17, "SPOT_TYPE_BOSS")]
       + [(floor, "SPOT_TYPE_BATTLE") for floor in range(18, 33)]
       + [(33, "SPOT_TYPE_SAFETY"), (34, "SPOT_TYPE_BOSS")])
LOST = "BATTLE_RESULT_TYPE_STAGE_FAILED"


def _play_lost(addon, closed, floor, by_hand):
    """A run that pays its first boss and is lost on `floor`, with the
    loss told the accelerated way or the by-hand way."""
    steps = _Steps(addon, 500)

    def enter(at, spot):
        steps.step("stage/enter_spot",
                   spot_info={"floor": at, "spot_type": spot},
                   stage_info={"spot_list": [{"floor": f, "type": t}
                                             for f, t in MAP]})

    steps.step("disaster/enter_disaster_chaos_stage",
               service_server_time=closed - 1800)
    enter(17, "SPOT_TYPE_BOSS")
    steps.step("battle/battle_start", snapshot={"cache": {"battle_init_wt": {
        "battle_res_id": "base_00305", "floor": 17}}})
    steps.step("spot_reward/get_drop_item", drop_item_result=[
        {"id": CURRENCY, "amount": 180, "group": "disaster_material"}])
    enter(floor, "SPOT_TYPE_BATTLE")
    steps.step("battle/battle_start", snapshot={"cache": {"battle_init_wt": {
        "battle_res_id": "base_00160", "floor": floor, "keyword_tag": [5]}}})
    if by_hand:
        steps.step("battle/battle_end", {"game_result": LOST}, battle_info={})
    else:
        steps.step("battle/acceleration_resolve", game_result=LOST,
                   floor=floor)
    steps.step("stage/clear_stage", service_server_time=closed)


def _new(Addon, folder=None, log=None):
    folder = folder or Path(tempfile.mkdtemp(prefix="capture_chaos_"))
    return Addon(folder, log_callback=(log.append if log is not None
                                       else lambda *a, **k: None))


def _the_run(run_, failures):
    """What one delegated run of the live season's Chaos records."""
    if run_.get("paid") != EXPECTED_PAID:
        failures.append(
            f"the run's payouts read {run_.get('paid')!r}, not "
            f"{EXPECTED_PAID!r}. A payout is the season currency's part "
            f"of the drop taken -- the Chaos Orbs in the same drop are "
            f"not one -- on the floor and fight it came from.")
    if run_.get("marked") != {"k5": 1, "e": 1}:
        failures.append(
            f"the run's marked fights read {run_.get('marked')!r}, not "
            f"k5 once and e once. The `_e` fight paid nothing and still "
            f"counts: a mark's rate is over the fights fought.")
    if run_.get("fought") != {"BATTLE": 2, "BOSS": 1}:
        failures.append(f"the run's fights read {run_.get('fought')!r}, "
                        f"not two battles and a boss.")
    if run_.get("season") != "disaster_s04":
        failures.append(
            f"the run names season {run_.get('season')!r}, not "
            f"disaster_s04, the standings' newest week. A new season's "
            f"currency is an item id nothing downstream knows, and the "
            f"season is what places it.")
    if run_.get("client") != "cznlive 1.464 r688":
        failures.append(
            f"the run's game version reads {run_.get('client')!r}, not "
            f"'cznlive 1.464 r688' from the helo: nothing could then say "
            f"whether a payout moved with a game update.")
    if run_.get("part") != 3:
        failures.append(
            f"a run cleared on 2026-09-25 names season part "
            f"{run_.get('part')!r}, not 3: the Sortie rotations inside "
            f"the season's window date its parts, the first being the "
            f"preseason. Once the season is over nothing else can, and "
            f"the estimate reads last season's runs by part.")
    if run_.get("lost"):
        failures.append(f"a cleared run reads as lost: {run_['lost']!r}.")
    if (run_.get("stage"), run_.get("via"), run_.get("delegated")) != (
            80000, "disaster", True):
        failures.append(
            f"a delegated run of the live season's Chaos reads stage "
            f"{run_.get('stage')!r}, via {run_.get('via')!r}, delegated "
            f"{run_.get('delegated')!r}, not 80000, 'disaster', True.")


def _zero_run(Addon, failures):
    """A past season's Chaos through the Zero System, and Senectus."""
    addon = _new(Addon)
    _setup(addon)
    _play_zero(addon, closed=1790540000)
    run_ = addon.chaos_runs[-1] if addon.chaos_runs else {}
    if (run_.get("stage"), run_.get("via"), run_.get("delegated")) != (
            60000, "zero_orb", False):
        failures.append(
            f"a run opened through the Zero System and played by hand "
            f"reads stage {run_.get('stage')!r}, via {run_.get('via')!r}, "
            f"delegated {run_.get('delegated')!r}, not 60000, 'zero_orb', "
            f"False. A past season's Chaos pays less, and without these "
            f"its runs are averaged in with the live one's.")
    if run_.get("marked") != {"b1": 1} or run_.get("fought") != {
            "BATTLE": 1, "BREAK_IN": 1}:
        failures.append(
            f"Senectus breaking in reads marked={run_.get('marked')!r} "
            f"fought={run_.get('fought')!r}, not b1 once over a battle "
            f"and a BREAK_IN. A break-in is a fight of its own spot, or it "
            f"swells the fights a mark's rate is taken over.")
    for told_twice in (False, True):
        addon = _new(Addon)
        _setup(addon)
        _play_delegated_break_in(addon, 1790560000, told_twice)
        run_ = addon.chaos_runs[-1] if addon.chaos_runs else {}
        if run_.get("marked") != {"b1": 1} or run_.get("fought") != {
                "BATTLE": 1, "BREAK_IN": 1}:
            failures.append(
                f"Senectus breaking in on a delegated run"
                f"{', told of twice,' if told_twice else ''} reads "
                f"marked={run_.get('marked')!r} "
                f"fought={run_.get('fought')!r}, not b1 once over a "
                f"battle and a BREAK_IN. The Delegation Module resolves "
                f"a break-in with no battle_start, so the resolving reply "
                f"is its only record -- counted once however often told.")


def _the_file(Addon, failures):
    """Where the runs are kept, and what protects them."""
    import chaos_store

    log = []
    folder = Path(tempfile.mkdtemp(prefix="capture_chaos_file_"))
    # A snapshot from before the file, carrying a run of its own.
    legacy = {"closed": 1790000000, "season": "disaster_s04", "paid": [],
              "fought": {}, "marked": {}}
    (folder / "memory_fragments_20260920_000000.json").write_text(
        json.dumps({"chaos_runs": [legacy]}), encoding="utf-8")
    addon = _new(Addon, folder, log)
    _setup(addon)
    _play(addon, closed=1790365000)
    stored, note = chaos_store.read(folder)
    if [r.get("closed") for r in stored] != [1790000000, 1790365000]:
        failures.append(
            f"the runs' file holds {[r.get('closed') for r in stored]} "
            f"({note}), not the older snapshot's run and the one just "
            f"played. It is the only place a player's runs are kept.")
    addon.inventory_data = {"memory_fragments": []}
    addon._save_data()
    saved = json.loads(Path(addon.saved_path).read_text(encoding="utf-8"))
    if "chaos_runs" in saved:
        failures.append("a saved snapshot still carries the Chaos runs, "
                        "repeating the file in every snapshot.")
    again_log = []
    again = _new(Addon, folder, again_log)
    if again.chaos_runs != stored:
        failures.append("a new capture did not read the runs back from "
                        "their file.")
    _setup(again)
    _play(again, closed=1790365000)
    if len(again.chaos_runs) != 2:
        failures.append(
            f"the same clear read twice made {len(again.chaos_runs)} runs "
            f"of two. A run is filed by the second it cleared, or a "
            f"replayed capture doubles every run in it.")

    # A copy that loses a run on its way to disk is refused.
    path = chaos_store.path_in(folder)
    held = gzip.decompress(path.read_bytes())
    namespace = Addon._write_chaos_store.__globals__
    real_json = namespace["json"]

    class _Dropping:
        def __getattr__(self, name):
            return getattr(real_json, name)

        @staticmethod
        def load(f):
            data = real_json.load(f)
            if isinstance(data, dict) and data.get("runs"):
                data["runs"] = data["runs"][1:]
            return data

    namespace["json"] = _Dropping()
    try:
        _play(again, closed=1790370000)
    finally:
        namespace["json"] = real_json
    if gzip.decompress(path.read_bytes()) != held:
        failures.append("a copy that lost a run on its way to disk replaced "
                        "the file anyway. The read-back check is what "
                        "stops that.")
    if not any(line.startswith("[X] Chaos runs") for line in again_log):
        failures.append("a refused write of the runs' file said nothing")
    if path.with_name(path.name + ".tmp").exists():
        failures.append("a refused write left its copy behind")

    # The file lost and its backup there: both readers use the backup.
    path.write_bytes(b"not gzip")
    stored, note = chaos_store.read(folder)
    if len(stored) != 2 or not note:
        failures.append(
            f"with the file unreadable the app read {len(stored)} runs "
            f"({note}), not the backup's two. A write renames the file to "
            f"its backup before the new copy lands, so a capture killed "
            f"between the two leaves only the backup.")
    if len(_new(Addon, folder).chaos_runs) != 2:
        failures.append("with the file unreadable the capture did not read "
                        "its backup.")


def run():
    add_source_to_path()
    Addon = _addon_class()
    failures = []
    addon = _new(Addon)
    _setup(addon)
    _play(addon, closed=1790365000)
    if len(addon.chaos_runs) != 1:
        return [f"one run played, {len(addon.chaos_runs)} recorded. Without "
                f"its record the run is nowhere, and chaos_runs.py never "
                f"sees it."]
    _the_run(addon.chaos_runs[0], failures)
    _zero_run(Addon, failures)

    for by_hand in (False, True):
        how = "by hand" if by_hand else "accelerated"
        for floor, left in ((32, 0), (30, 2)):
            lost = _new(Addon)
            _setup(lost)
            _play_lost(lost, 1790457173, floor, by_hand)
            got = lost.chaos_runs[-1].get("lost") if lost.chaos_runs else None
            if got != [floor, "BATTLE", "k5", left]:
                failures.append(
                    f"a run lost {how} on floor {floor}'s Rare Species "
                    f"reads lost={got!r}, not "
                    f"{[floor, 'BATTLE', 'k5', left]!r}: the floor, spot "
                    f"and mark it was lost on, and the non-boss fights "
                    f"its map still held. Whether a lost run counts as "
                    f"whole turns on that last number.")

    failures.extend(_given_up(Addon))
    failures.extend(_what_the_entry_says(Addon))
    failures.extend(_the_partners(Addon))
    failures.extend(_the_opening_and_nightmare(Addon))
    failures.extend(_the_senectus_place(Addon))
    failures.extend(_the_map_and_route(Addon))
    failures.extend(_the_report_counts_each_mark_once())
    failures.extend(_the_report_pools_and_steps())
    failures.extend(_the_report_pools_by_default())
    failures.extend(_the_table_keeps_a_replayed_row())
    failures.extend(_the_report_reads_at_zero_nodes())
    failures.extend(_the_table_names_the_rolls())
    failures.extend(_a_run_spans_captures(Addon))
    failures.extend(_new_season(Addon))
    _the_file(Addon, failures)
    return failures


def _new_season(Addon):
    """A run in a season the account has no Great Rift row of yet.

    Season 5's schedule as season 4's handover had it: the window opens
    as season 4's closes, a preseason rotation first. The standings still
    end at season 4, and a run in season 5's first part is season 5's.
    """
    addon = _new(Addon)
    _setup(addon)
    addon.websocket_message(_Flow([{"res": "ok", "event_schedules": {
        "DISASTER_SEASON": {
            "disaster_s04": {"start_time": 1783476000,
                             "end_time": 1790726400},
            "disaster_s05": {"start_time": 1790733600,
                             "end_time": 1797984000}},
        "ASSAULT_SCHEDULE": {
            "assault_1_s7": {"start_time": 1788915600,
                             "end_time": 1790726400},
            "assault_1_s8": {"start_time": 1790733600,
                             "end_time": 1792540800},
            "assault_1_s9": {"start_time": 1792548000,
                             "end_time": 1794355200}},
    }}]))
    _play(addon, closed=1792886400)
    run_ = addon.chaos_runs[-1] if addon.chaos_runs else {}
    if (run_.get("season"), run_.get("part")) != ("disaster_s05", 1):
        return [f"a run in season 5's first part, with the standings "
                f"still ending at season 4, reads season "
                f"{run_.get('season')!r} part {run_.get('part')!r}, not "
                f"'disaster_s05' part 1. The schedule opens with the "
                f"season; filed under the season before, its payouts "
                f"are averaged into that season's figures."]
    return []


def _given_up(Addon):
    """A run left by an escape is filed, and never as a whole one.

    The close is asked for with `is_emergency_exit`, and answered
    `GIVEUP` on a Simulation stage (`websocket_debug_20260929_220558`)
    but `CLEAR` on a Chaos run. No fight is lost, so without reading the
    request the run is filed as cleared, and a whole run's marks are
    averaged over it.
    """
    import chaos_estimate
    failures = []
    # A Chaos run's escape answers CLEAR (`websocket_debug_20260930_
    # 233315`, the regular Chaos): only the request says it was one.
    for said in ("GIVEUP", "CLEAR"):
        addon = _new(Addon)
        _setup(addon)
        steps = _Steps(addon, 700)
        steps.step("disaster/enter_disaster_chaos_stage",
                   service_server_time=1790460000)
        steps.fight(6, "SPOT_TYPE_BATTLE", "base_00160", keyword_tag=[5])
        steps.step("stage/clear_stage", {"is_emergency_exit": True},
                   service_server_time=1790460600, stage_id=80000,
                   return_info={"result": said, "state": "finish"})
        runs = addon.chaos_runs
        if len(runs) != 1:
            failures.append(f"a Chaos run left by an escape answered "
                            f"{said} files {len(runs)} runs, not 1.")
        elif not runs[0].get("gave_up") or chaos_estimate.is_full(runs[0]):
            failures.append(
                f"a Chaos run left by an escape answered {said} reads "
                f"gave_up={runs[0].get('gave_up')!r} and counts as whole: "
                f"the close was asked for with `is_emergency_exit` and no "
                f"fight was lost, so the marks per whole run are averaged "
                f"over a run cut short.")

    # A base-game Chaos entered from its own screen while a Galactic
    # Disaster run is left open starts a run of its own: its clear is
    # not the open run's, and its fights are not added in.
    addon = _new(Addon)
    _setup(addon)
    steps = _Steps(addon, 800)
    steps.step("disaster/enter_disaster_chaos_stage",
               service_server_time=1790460000)
    steps.fight(6, "SPOT_TYPE_BATTLE", "base_00160", keyword_tag=[5])
    steps.step("chaos/enter_embody_chaos_stage",
               service_server_time=1790461000, **EMBODY_ENTRY)
    steps.fight(2, "SPOT_TYPE_BATTLE", "base_00011")
    steps.step("stage/clear_stage", service_server_time=1790461600,
               stage_id=120000004,
               return_info={"result": "CLEAR", "state": "finish"})
    runs = addon.chaos_runs
    got = runs[-1] if runs else {}
    if len(runs) != 1 or (got.get("via"), got.get("stage"),
                          got.get("fought")) != (
            "chaos", 120000004, {"BATTLE": 1}):
        failures.append(
            f"a base-game Chaos entered from its own screen, while a "
            f"Galactic Disaster run was left open, filed {len(runs)} "
            f"run(s), the last via {got.get('via')!r}, stage "
            f"{got.get('stage')!r}, fought {got.get('fought')!r} -- not "
            f"one run via 'chaos', stage 120000004, its own one battle.")
    return failures


# The two entries' replies as the wire had them
# (`websocket_debug_20261001_222841`), cut to what a run records.
EMBODY_ENTRY = {
    "playing_stage_info": {
        "stage_id": 120000004,
        "ingame_content_config_id": "content_chaos_embody_chaos",
        "chaos_info": {"chaos_id": "chaos_05", "embody_info": {
            "embody_chaos_define_id": "embody_chaos_05",
            "embody_chaos_list_id": "embody_chaos_05_06"}},
        "floor_info": [0, 34]},
    "zero_system_effs": {"ZERO_CHARACTER_STAT__TYPE_VALUE": [{
        "zero_system_eff_id": "zero_orb_s2_1_01_01_05",
        "opt_values": {"opt_1": -1, "opt_2": 40}}]},
    "planet_resid": 100501,
    "dev_msg": "[boss_1]_at_1 [boss_2]_at_18 boss_list:base_00133,base_00134",
}
DISASTER_ENTRY = {
    "playing_stage_info": {
        "stage_id": 100000,
        "ingame_content_config_id": "content_disaster_chaos",
        "chaos_info": {"chaos_id": "chaos_10", "disaster_info": {
            "disaster_list_id": "disaster_s05_08",
            "disaster_season_id": "disaster_s05"}}},
}
ZERO_ENTRY = {
    "playing_stage_info": {
        "stage_id": 115000001, "ingame_content_config_id": "content_chaos_zero",
        "chaos_info": {"chaos_id": "chaos_02", "zero_info": {
            "zero_orb_codex_id": 54549623, "zero_orb_slot_id": 3}},
        "floor_info": [0, 28],
        "zero_orb_codex_info": {
            "id": 54549623, "res_id": "zero_orb_codex_013", "lv": 76,
            "coordinate": "zero_orb_coord_007", "option": {
                "bonus_infos": ["zero_orb_bonus_001"],
                "penalty_infos": ["zero_orb_penalty_112",
                                  "zero_orb_penalty_135"],
                "special_infos": ["zero_orb_special_v1_09"]}}},
    "zero_system_effs": {
        "ZERO_ENCOUNTER_RATEUP__COUNT_RARITY": [{
            "zero_system_eff_id": "zero_season_s4_skill_034_05",
            "opt_values": {"opt_1": 3, "opt_2": -1}}],
        "ZERO_NO_SAVEDATA": [{"zero_system_eff_id": "zero_orb_special_v1_04",
                              "opt_values": {"opt_1": 1}}]},
    "planet_resid": 100201,
    "dev_msg": "[boss_1]_at_1 boss_list:base_00000,base_00109",
}


def _tool():
    """`docs/chaos_runs.py`, imported."""
    import importlib.util
    import os
    from ._harness import REPO_ROOT
    here = os.getcwd()
    try:
        spec = importlib.util.spec_from_file_location(
            "chaos_runs_tool", REPO_ROOT / "docs" / "chaos_runs.py")
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
    finally:
        os.chdir(here)              # the tool moves to Vribbels/ on import
    return tool


# A first area as a stage's `spot_list` lists it: (spot id, floor, type).
# Floor -1 is the map's start and floor 0 the event every run opens
# with: neither holds a fight, cleared or not.
SPAN_MAP = ((7, -1, "UNKNOWN"), (8, 0, "UNKNOWN"), (1, 1, "BATTLE"),
            (2, 2, "ELITE"), (3, 3, "BOSS"), (4, 4, "BATTLE"))


def _span_stage(events, cleared=(), playing=None):
    """The run's stage as a reply carries it: the events met so far, the
    map with what is cleared, and the spot being played."""
    return {"stage": {
        "curr_area_id": 0, "used_spot_event": list(events),
        "playing_spot_id": playing,
        "chaos_info": DISASTER_ENTRY["playing_stage_info"]["chaos_info"],
        "spot_list": [{"id": sid, "floor": floor, "type": "SPOT_TYPE_" + kind,
                       "clear": 1 if sid in cleared else 0}
                      for sid, floor, kind in SPAN_MAP]}}


def _a_run_spans_captures(Addon):
    """A run one capture leaves open is taken up by the next, and what
    was played between the two is told apart from what the captures saw.

    The 2026-10-21 run, cut down: entered and fought into on the PC, the
    capture ending; an Elite and the boss played on another device, the
    boss's win completed only once the PC took the run up again; a
    Rare Species after; the clear restating 144 and 48 where the
    captures saw the 48 alone. The run is one, `resumed` once, its
    `unseen` the Elite and the boss being played, `restated` the clear's
    -- and `chaos_estimate.recovery` places the 144 on the boss and
    leaves the Elite's marks unknown. A run left open whose events the
    next stage does not begin with is another run: not taken up.
    Returns complaints."""
    import chaos_estimate as ce
    out = []
    folder = Path(tempfile.mkdtemp(prefix="capture_chaos_"))
    first = _new(Addon, folder)
    _setup(first)
    steps = _Steps(first, 1100)
    steps.step("disaster/enter_disaster_chaos_stage",
               service_server_time=1790460000, stage_info=_span_stage(["e0"]),
               **DISASTER_ENTRY)
    steps.step("stage/enter_spot",
               spot_info={"floor": 1, "spot_type": "SPOT_TYPE_BATTLE",
                          "spot_id": 1},
               stage_info=_span_stage(["e0", "e1"])["stage"])
    steps.step("battle/battle_start", snapshot={"cache": {"battle_init_wt": {
        "battle_res_id": "base_00160", "floor": 1}}})
    if not (folder / "chaos_runs" / "open.json").exists():
        out.append("a run in progress left no open.json beside the runs' "
                   "file: a capture that ends partway leaves the next "
                   "nothing to take up (`Addon._save_open_chaos`).")
    second = _new(Addon, folder)
    _setup(second)
    steps = _Steps(second, 1200)
    steps.step("world/get_stage_info", service_server_time=1790461000,
               stage_info=_span_stage(["e0", "e1", "e2", "e3"],
                                      cleared=(7, 8, 1, 2), playing=3))
    steps.step("stage/enter_spot",
               spot_info={"floor": 4, "spot_type": "SPOT_TYPE_BATTLE",
                          "spot_id": 4},
               stage_info=_span_stage(["e0", "e1", "e2", "e3", "e4"],
                                      cleared=(1, 2, 3))["stage"])
    steps.step("battle/battle_start", snapshot={"cache": {"battle_init_wt": {
        "battle_res_id": "base_00161", "floor": 4, "keyword_tag": [5]}}})
    steps.step("spot_reward/get_drop_item", drop_item_result=[
        {"id": CURRENCY, "amount": 48, "group": "disaster_material"}])
    steps.step("stage/clear_stage", service_server_time=1790461600,
               stage_id=100000, return_info={
                   "result": "CLEAR", "confirm_drop_item": [
                       {"id": 2000001, "amount": 2000, "group": "common_gold"},
                       {"id": CURRENCY, "amount": 144,
                        "group": "disaster_material"},
                       {"id": CURRENCY, "amount": 48,
                        "group": "disaster_material"}]})
    run_ = second.chaos_runs[-1] if second.chaos_runs else {}
    want = {"opened": 1790460000, "started_elsewhere": None,
            "resumed": [1790461000],
            "unseen": [[0, 2, "ELITE", False], [0, 3, "BOSS", True]],
            "restated": [144, 48],
            "paid": [[4, "BATTLE", "k5", CURRENCY, 48]]}
    got = {key: run_.get(key) for key in want}
    if got != want:
        out.append(f"a run taken up by the next capture reads {got}, not "
                   f"{want}: one run, from its own entry, the Elite and the "
                   f"boss played meanwhile unseen, the clear's restatement "
                   f"kept (`Addon._resume_chaos`).")
    if not run_:
        return out
    if (folder / "chaos_runs" / "open.json").exists():
        out.append("open.json is still there after its run cleared: the "
                   "next capture would take a filed run up again.")
    kinds = {144: {("BOSS", "")}, 48: {("BATTLE", "k5")}}
    found = ce.recovery(run_, kinds)
    if found != ([(3, "BOSS", "", 144)], ["1 fight(s) unseen (2 elite)"]) \
            or not ce.is_partial(run_):
        out.append(f"chaos_estimate.recovery reads {found} for it, partial "
                   f"{ce.is_partial(run_)}: the 144 only bosses pay is the "
                   f"unseen boss's, on floor 3, and the Elite no capture saw "
                   f"leaves the run's marks unknown.")
    both = ce.recovery(run_, {144: {("BOSS", ""), ("ELITE", "k5")}})
    if both[0] or "144 unexplained" not in both[1]:
        out.append(f"an amount both a boss and a mark pay reads {both}: "
                   f"placed on either, it could be the other's.")
    row = _tool().row_of(run_, "x", {}, {run_.get("season"): kinds})
    if (row["total"], row["gaps"]) != (
            "192", "resumed 1, recovered 3:boss:144, partial: 1 fight(s) "
                   "unseen (2 elite)") \
            or not row["payouts"].endswith("3:boss:144~"):
        out.append(f"docs/chaos_runs.py writes the run as total "
                   f"{row['total']!r}, payouts {row['payouts']!r}, gaps "
                   f"{row['gaps']!r}: the recovered 144 counts, marked `~`.")

    # **Another run's leftovers are not taken up.** A run left open, then
    # finished elsewhere; the next stage the capture sees is a new run's,
    # whose events do not begin with the kept ones.
    folder = Path(tempfile.mkdtemp(prefix="capture_chaos_"))
    left = _new(Addon, folder)
    _setup(left)
    steps = _Steps(left, 1300)
    steps.step("disaster/enter_disaster_chaos_stage",
               service_server_time=1790462000, stage_info=_span_stage(["x0"]),
               **DISASTER_ENTRY)
    later = _new(Addon, folder)
    _setup(later)
    steps = _Steps(later, 1400)
    steps.step("world/get_stage_info", service_server_time=1790463000,
               stage_info=_span_stage(["y0", "y1"], cleared=(7, 8, 1),
                                      playing=2))
    steps.step("stage/clear_stage", service_server_time=1790463600,
               stage_id=100000, return_info={"result": "CLEAR"})
    other = later.chaos_runs[-1] if later.chaos_runs else {}
    if (other.get("opened"), other.get("started_elsewhere"),
            other.get("unseen")) != (None, True,
                                     [[0, 1, "BATTLE", False],
                                      [0, 2, "ELITE", True]]):
        out.append(f"a stage whose events do not begin with the run left "
                   f"open reads opened {other.get('opened')!r}, started "
                   f"elsewhere {other.get('started_elsewhere')!r}, unseen "
                   f"{other.get('unseen')!r}: it is another run, opened from "
                   f"the stage alone, every fight on its map unseen -- not "
                   f"the start on floor -1 or the opening event on floor 0.")

    # **A Sortie is no Chaos run.** Its stage carries a `chaos_info` too,
    # naming `assault_info` where a Chaos names its door.
    folder = Path(tempfile.mkdtemp(prefix="capture_chaos_"))
    sortie = _new(Addon, folder)
    _setup(sortie)
    steps = _Steps(sortie, 1500)
    stage = _span_stage(["s0", "s1"], cleared=(8, 1), playing=2)
    stage["stage"]["chaos_info"] = {"chaos_id": "chaos_assault_00001",
                                    "assault_info": {}}
    steps.step("world/get_stage_info", service_server_time=1790464000,
               stage_info=stage)
    steps.step("stage/clear_stage", service_server_time=1790464600,
               stage_id=200000057, return_info={"result": "CLEAR"})
    if sortie.chaos_runs or (folder / "chaos_runs" / "open.json").exists():
        out.append(f"a Sortie's stage was taken up as a Chaos run started "
                   f"elsewhere ({len(sortie.chaos_runs)} filed): only a stage "
                   f"naming a Chaos door is (`CHAOS_DOORS`).")

    # **The spot a resuming reply enters is watched whole**: a capture
    # begun mid-run, whose first word of it is the next spot's entry.
    folder = Path(tempfile.mkdtemp(prefix="capture_chaos_"))
    joined = _new(Addon, folder)
    _setup(joined)
    steps = _Steps(joined, 1600)
    steps.step("stage/enter_spot", service_server_time=1790465000,
               spot_info={"floor": 2, "spot_type": "SPOT_TYPE_ELITE",
                          "spot_id": 2},
               stage_info=_span_stage(["z0", "z1", "z2"], cleared=(8, 1),
                                      playing=2)["stage"])
    steps.step("battle/battle_start", snapshot={"cache": {"battle_init_wt": {
        "battle_res_id": "base_00162", "floor": 2}}})
    steps.step("stage/clear_stage", service_server_time=1790465600,
               stage_id=100000, return_info={"result": "CLEAR"})
    caught = joined.chaos_runs[-1] if joined.chaos_runs else {}
    got = (caught.get("unseen"), caught.get("entered"), caught.get("fought"))
    if got != ([[0, 1, "BATTLE", False]], {"0": [2]}, {"ELITE": 1}):
        out.append(f"a run taken up on a spot's own entry reads unseen, "
                   f"entered, fought {got}: the Elite it enters is seen and "
                   f"fought, the battle before it the one fight unseen.")
    return out


def _the_table_names_the_rolls():
    """`docs/chaos_runs.py`'s `rolled` names the bonus and penalties a
    run rolled, from its effects, whichever door -- a Galactic Disaster
    run has no codex to read them from, and `ELITE_ADD` among them is
    what the fight comparison splits the runs by. Tree nodes and
    specials are not rolls; a run filed before runs kept their effects
    is `?`, not a run that rolled nothing."""
    tool = _tool()
    run_ = {"closed": 1789000000, "season": "disaster_s04", "via": "disaster",
            "paid": [], "stage": 80000, "effects": [
                ["ZERO_ELITE_ADD__COUNT", "zero_orb_penalty_008", []],
                ["ZERO_ENCOUNTER_RATEUP__COUNT_RARITY",
                 "zero_season_s4_skill_034_05", []],
                ["ZERO_FATE_RATIOUP__VALUE", "zero_orb_bonus_010", [65]],
                ["ZERO_REINFORCE_CONTENTS__CONTENTS_RATIO",
                 "zero_orb_special_opt_9004", []]]}
    rolled = tool.row_of(run_, "runs.json.gz", {})["rolled"]
    old = tool.row_of({k: v for k, v in run_.items() if k != "effects"},
                      "runs.json.gz", {})["rolled"]
    out = []
    if rolled != "ELITE_ADD:p008 FATE_RATIOUP:b010" or old != "?":
        out.append(f"chaos_runs.py's rolled column reads {rolled!r} for a "
                   f"Galactic Disaster run rolling ELITE_ADD and a Fate "
                   f"bonus, and {old!r} for one filed with no effects: "
                   f"'ELITE_ADD:p008 FATE_RATIOUP:b010' and '?'.")
    if "ELITE_ADD" not in (tool.rolled_counts(rolled) or {}) \
            or tool.rolled_counts(old) is not None:
        out.append("chaos_runs.rolled_counts does not read the rolled "
                   "column back, so the ELITE_ADD comparison splits no "
                   "run.")
    return out


def _the_report_reads_at_zero_nodes():
    """`docs/chaos_runs.py`'s changes table reads every amount at 0
    nodes and every boss by its place in the run: a first boss paying
    180 at 25 nodes on floor 17 of one map and 144 at none on another's
    has not changed, a third boss is read as paid, and a payout no whole
    amount at 0 nodes comes to is flagged. Read as paid, every node
    bought is a change, and a real one drowns among them; read by
    floor, a new map is all new bosses.

    The place comes off the map's `floors`, whose end is the second
    boss's floor -- so a run whose first boss was paid while no capture
    watched still has its others in place -- else off the order of the
    boss floors paid. A third boss paying other than 60, and another
    boss paying 60, are flagged: the order and the pay disagree.
    Returns complaints."""
    tool = _tool()

    def row(date, nodes, payouts, floors="0-34", season="s04"):
        return {"date": date, "season": season, "part": "part 3",
                "client": "cznlive 1.464 r688", "amplified": str(nodes),
                "payouts": payouts, "marked": "", "fought": "",
                "floors": floors}

    out = []
    for each, want in (
            (row("x", 0, "17:boss:1 34:boss:1 37:boss:1", "?"),
             {17: "boss 1", 34: "boss 2", 37: "boss 3"}),
            (row("x", 0, "28:boss:1 31:boss:1", "0-28"),
             {28: "boss 2", 31: "boss 3"}),
            (row("x", 0, "17:boss:1 20:boss:1 28:boss:1 31:boss:1 33:boss:1",
                 "0-28"),
             {17: "boss x17", 20: "boss x20", 28: "boss 2", 31: "boss 3",
              33: "boss x33"})):
        if tool.boss_orders(each) != want:
            out.append(f"chaos_runs.boss_orders reads bosses on "
                       f"{each['payouts']!r} with floors {each['floors']!r} "
                       f"as {tool.boss_orders(each)}, not {want}: the map's "
                       f"last floor is the second boss, the one before it "
                       f"the first, the one after it the third.")
    rows = {r["date"]: r for r in (
        row("2026-09-17 18:21", 25,
            "17:boss:180 34:boss:180 37:boss:60 5:battle:60+k5"),
        row("2026-09-18 18:21", 0,
            "17:boss:144 28:boss:144 31:boss:60 5:battle:48+k5", "0-28",
            "s05"),
        row("2026-09-19 18:21", 0, "17:boss:150"),
        row("2026-09-20 18:21", 25, "17:boss:181 37:boss:59"),
        row("2026-09-21 18:21", 0, "17:boss:60"))}
    found, flags = tool.changes(rows)
    said = [(cells[0], cells[1]) for cells in found]
    want = [("2026-09-19 18:21", "boss 1"), ("2026-09-20 18:21", "boss 1"),
            ("2026-09-20 18:21", "boss 3"), ("2026-09-21 18:21", "boss 1")]
    told = [any(text in flag for flag in flags)
            for text in ("181 at 25 nodes", "third boss paid 59",
                         "boss 1 paid 60")]
    if said != want or not all(told):
        out.append(f"chaos_runs.py's changes table reads {said} with flags "
                   f"{flags}, not {want} with 181 at 25 nodes, a third boss "
                   f"paying 59 and a first boss paying 60 flagged: 180 at "
                   f"25 nodes is 144 at 0, season 5's floor-28 boss is season "
                   f"4's floor-34 one, the third boss is read as paid, and "
                   f"181 at 25 nodes fits no whole amount.")
    return out


def _the_table_keeps_a_replayed_row():
    """`docs/chaos_runs.py`'s default pass keeps a row a log was replayed
    into against the capture's own record of the same run.

    The default pass reads only the newest logs, and every run the
    runs' file holds; the file's record was made by the capture code of
    its day. Written over a log's row, it took back a break-in the
    record never saw (the 2026-09-28 00:42 run) and blanked every field
    added since. `--all` rebuilds from what it reads, which is right."""
    tool = _tool()
    run_ = {"closed": 1790545320, "season": "disaster_s04", "part": 3,
            "via": "disaster", "delegated": True, "client": "x",
            "paid": [], "marked": {"k5": 1}, "fought": {"BATTLE": 12},
            "stage": 80000}
    replayed = dict(run_, marked={"b1": 1, "k5": 1},
                    fought={"BATTLE": 12, "BREAK_IN": 1})
    old = tool.row_of(replayed, "websocket_debug_20260928_003350.jsonl", {})
    rows = {old["date"]: dict(old, notes="yours")}
    found = [(run_, "runs.json.gz")]
    kept = tool.merge(rows, found, {}, ["notes"], full=False)[old["date"]]
    rebuilt = tool.merge(rows, found, {}, ["notes"], full=True)[old["date"]]
    if (kept["marked"], kept["notes"]) != ("b1:1 k5:1", "yours") \
            or rebuilt["marked"] != "k5:1":
        return [f"chaos_runs.py's default pass reads a replayed row's "
                f"marks as {kept['marked']!r} (notes {kept['notes']!r}) "
                f"against the runs' file's own record, and --all as "
                f"{rebuilt['marked']!r}: the default pass keeps the "
                f"replay's 'b1:1 k5:1' and your columns, --all rebuilds "
                f"from what it found."]
    return []


def _what_the_entry_says(Addon):
    """A run records what its entry says it is: the Chaos's own id, the
    difficulty its list id names, a Zero System map's codex with its
    level and options, every Zero System effect with its values, the
    planet, the bosses and the floors -- and each mark by the spot it
    was met on. What these change is not on the wire, and a rate read
    over runs that differ in them is a rate of their mix."""
    failures = []
    addon = _new(Addon)
    _setup(addon)
    steps = _Steps(addon, 900)
    steps.step("chaos/enter_embody_chaos_stage",
               service_server_time=1790461000, **EMBODY_ENTRY)
    steps.fight(2, "SPOT_TYPE_BATTLE", "base_00011_e")
    steps.fight(3, "SPOT_TYPE_ELITE", "base_00012", keyword_tag=[5])
    steps.step("stage/clear_stage", service_server_time=1790461600,
               stage_id=120000004)
    steps.step("zero_orb/enter_zero_stage", DELEGATED,
               service_server_time=1790462000, **ZERO_ENTRY)
    steps.step("stage/clear_stage", service_server_time=1790462600,
               stage_id=115000001)
    embody, zero = (addon.chaos_runs + [{}, {}])[:2]
    want = {"chaos": "chaos_05", "content": "content_chaos_embody_chaos",
            "difficulty": "embody_chaos_05_06", "planet": 100501,
            "floors": [0, 34], "bosses": ["base_00133", "base_00134"],
            "effects": [["ZERO_CHARACTER_STAT__TYPE_VALUE",
                         "zero_orb_s2_1_01_01_05", [40]]],
            "marked_at": {"BATTLE": {"e": 1}, "ELITE": {"k5": 1}}}
    got = {k: embody.get(k) for k in want}
    if got != want or "codex" in embody:
        failures.append(f"a base-game Chaos run records {got}, not {want}, "
                        f"and no codex.")
    codex = {"res_id": "zero_orb_codex_013", "lv": 76,
             "coordinate": "zero_orb_coord_007",
             "bonus": ["zero_orb_bonus_001"],
             "penalty": ["zero_orb_penalty_112", "zero_orb_penalty_135"],
             "special": ["zero_orb_special_v1_09"]}
    effects = [["ZERO_ENCOUNTER_RATEUP__COUNT_RARITY",
                "zero_season_s4_skill_034_05", [3]],
               ["ZERO_NO_SAVEDATA", "zero_orb_special_v1_04", [1]]]
    if (zero.get("codex"), zero.get("effects"), zero.get("chaos"),
            zero.get("difficulty"), zero.get("delegated")) != (
            codex, effects, "chaos_02", None, True):
        failures.append(
            f"a Zero System run records codex {zero.get('codex')}, effects "
            f"{zero.get('effects')}, chaos {zero.get('chaos')!r}, "
            f"difficulty {zero.get('difficulty')!r}, delegated "
            f"{zero.get('delegated')!r} -- not the map's codex with its "
            f"level and options, every effect with its values, chaos_02, "
            f"no list id, and played by the Delegation Module.")
    # A Galactic Disaster run's difficulty, from `disaster_info` (the
    # 2026-10-21 21:47 capture's entry, cut down).
    steps.step("disaster/enter_disaster_chaos_stage",
               service_server_time=1790463000, **DISASTER_ENTRY)
    steps.step("stage/clear_stage", service_server_time=1790463600,
               stage_id=100000)
    disaster = (addon.chaos_runs + [{}, {}, {}])[2]
    if disaster.get("difficulty") != "disaster_s05_08":
        failures.append(
            f"a Galactic Disaster run records difficulty "
            f"{disaster.get('difficulty')!r}, not 'disaster_s05_08': its "
            f"list id is under `chaos_info.disaster_info`, and read one "
            f"level up every row of docs/chaos_runs.tsv says `?`.")
    return failures


# Each combatant's partner as an entry's `stage_info` lists it (the
# 2026-10-21 15:53 capture's, cut down), the third combatant's left
# without one.
SUPPORTERS = {"enter_supporters": [
    {"id": 4, "res_id": 30135, "limit_break": 2, "level": 60},
    {"id": 5, "res_id": 1025, "limit_break": 0, "level": 60}]}
SIG_STEPS = {"30135": [["EFF_PARTNER_UNIQUE_SPARK", [[0, 1]]],
                       ["EFF_BREAK_IN_RATEUP_PCT_ADD", [[0, 0.56], [2, 1.12]]]]}


def _the_opening_and_nightmare(Addon):
    """A run records whether it was in Nightmare Mode -- the entry
    request's `is_psychosis_mode` -- and the option picked at its
    opening event, the map's PRE_START spot (Kyrken's Messenger), with
    what it gave; a pick at a later event is not taken for it. The
    table says whether the pick set the first 3 normal battles' enemies
    to 1 HP. Returns complaints."""
    out = []
    addon = _new(Addon)
    _setup(addon)
    steps = _Steps(addon, 1800)
    stage = {"stage": dict(_map_stage([(1, 1, "BATTLE", False)]),
                           spot_list=[{"id": 7, "floor": -1,
                                       "type": "SPOT_TYPE_UNKNOWN",
                                       "type2": "SPOT_TYPE_PRE_START",
                                       "spot_pool_id": "uk_sys_s02_01d"}])}
    steps.step("disaster/enter_disaster_chaos_stage",
               {"is_psychosis_mode": True}, service_server_time=1790490000,
               stage_info=stage, **DISASTER_ENTRY)

    def pick(event, option, rewards):
        chosen = {"id": option, "encounter_id": event,
                  "succ_rewards": [rewards]}
        steps.step("encounter/select_option",
                   {"info": {"select_id": option}},
                   result={"info": {"history": [{
                       "id": event, "selection": chosen,
                       "all": [chosen, {"id": event + "_s6"}]}]}})

    pick("uk_sys_s02_01d", "uk_sys_s02_01d_s1",
         [{"res_id": "up_mhp_20p", "type": "MAX_HP_PCT", "value": 20},
          {"res_id": "nbf_nb_en_00658", "type": "NB_EFF",
           "link_res_ids": ["nb_en_00658"], "value": 1}])
    pick("uk_evt_s01_01", "uk_evt_s01_01_s2",
         [{"res_id": "other", "type": "GOLD", "value": 1}])
    steps.step("stage/clear_stage", service_server_time=1790490600,
               stage_id=100000)
    run_ = addon.chaos_runs[-1] if addon.chaos_runs else {}
    opening = run_.get("opening") or {}
    if (run_.get("nightmare"), opening.get("picked"),
            opening.get("offered")) != (True, "uk_sys_s02_01d_s1",
                                        ["uk_sys_s02_01d_s1",
                                         "uk_sys_s02_01d_s6"]) \
            or "nb_en_00658" not in (opening.get("rewards") or ()):
        out.append(f"a Nightmare Mode run picking the 1-HP bonus option at "
                   f"Kyrken's Messenger records nightmare "
                   f"{run_.get('nightmare')!r} and opening {opening}: True, "
                   f"and the pick at the PRE_START event with the 1-HP "
                   f"effect among its rewards, not the later event's.")
    row = _tool().row_of(run_, "x", {})
    if (row["nightmare"], row["1hp_start"]) != ("on", "yes"):
        out.append(f"chaos_runs.py writes nightmare {row['nightmare']!r} "
                   f"and 1hp_start {row['1hp_start']!r} for it, not 'on' "
                   f"and 'yes'.")
    return out


def _the_senectus_place(Addon):
    """A run keeps its fights in order, so the table can say the floor
    a Senectus broke in on and the fights before it -- every fight, in a
    run without one; and whether Distortion Adaptation was on, off the
    entry request's `is_chaos_level_mode`. Returns complaints."""
    out = []
    for told_twice in (False, True):
        addon = _new(Addon)
        _setup(addon)
        _play_delegated_break_in(addon, 1790560000, told_twice)
        run_ = addon.chaos_runs[-1] if addon.chaos_runs else {}
        row = _tool().row_of(run_, "x", {})
        if (row["senectus"], row["fights_before"]) != ("6", "battle:1"):
            out.append(
                f"a Senectus breaking in on floor 6 after one battle"
                f"{', told of twice,' if told_twice else ''} is written "
                f"senectus {row['senectus']!r}, fights_before "
                f"{row['fights_before']!r}, not '6' and 'battle:1' "
                f"(`fights`, `chaos_runs.senectus_of`).")
    addon = _new(Addon)
    _setup(addon)
    steps = _Steps(addon, 900)
    steps.step("disaster/enter_disaster_chaos_stage",
               {**DELEGATED, "is_chaos_level_mode": False,
                "chaos_level_mode_custom_supporter_info": [True, False]},
               service_server_time=1790560000 - 1800)
    steps.fight(6, "SPOT_TYPE_BATTLE", "base_00160")
    steps.fight(9, "SPOT_TYPE_ELITE", "base_00161")
    steps.fight(17, "SPOT_TYPE_BOSS", "base_00000")
    steps.step("stage/clear_stage", service_server_time=1790560000,
               stage_id=80000)
    run_ = addon.chaos_runs[-1] if addon.chaos_runs else {}
    row = _tool().row_of(run_, "x", {})
    if (row["senectus"], row["fights_before"], row["distortion"]) != (
            "", "battle:1 boss:1 elite:1", "off"):
        out.append(
            f"a run with no Senectus and Distortion Adaptation off is "
            f"written senectus {row['senectus']!r}, fights_before "
            f"{row['fights_before']!r}, distortion {row['distortion']!r}: "
            f"not empty, every fight it had, and 'off'.")
    # A partner Distortion Adaptation assigned in place of the player's
    # own: its slot's flag, in team order (websocket_debug_20261027_202354,
    # Sereniel's slot given the assigned Peko).
    held = (run_.get("level_mode") or {}).get("custom_supporters")
    written = _tool().partners_of({**run_, "partners": [[30076, 0],
                                                        [30092, 0]]})
    if held != [True, False] or not written.startswith("Peko LB0 DA, ") \
            or written.endswith(" DA"):
        out.append(f"a run whose first partner Distortion Adaptation "
                   f"assigned keeps the flags {held!r} and writes "
                   f"partners {written!r}: not [True, False], with `DA` "
                   f"after the first partner alone.")
    if _tool().senectus_of({}) != ("?", "?"):
        out.append("a run filed before runs kept their fights in order "
                   "reads as one with no Senectus, not as `?`.")
    # The Zero System's entry request carries no `is_chaos_level_mode`
    # (websocket_debug_20261002_154326): the door has no Distortion
    # Adaptation, which is not the same as not knowing.
    addon = _new(Addon)
    _setup(addon)
    _play_zero(addon, 1790560000)
    run_ = addon.chaos_runs[-1] if addon.chaos_runs else {}
    if _tool().distortion_of(run_) != "" or _tool().distortion_of({}) != "?":
        out.append(f"a Zero System run is written distortion "
                   f"{_tool().distortion_of(run_)!r} and a run with no "
                   f"entry seen {_tool().distortion_of({})!r}: not empty "
                   f"(the door has no Distortion Adaptation) and '?'.")
    return out


def _the_partners(Addon):
    """A run records each combatant's partner and its limit break, off
    the entry's `enter_supporters` -- or, for a run no capture saw
    enter, off the stage reply it is taken up from. An entry with no
    stage says nothing, which is not a team without partners. The
    table writes them, and what they raised the Invasion chance by: a
    partner's Exploration Passive is not among the run's effects, so
    the partners are its only record. Returns complaints."""
    import game_client
    out = []
    addon = _new(Addon)
    _setup(addon)
    steps = _Steps(addon, 1500)
    steps.step("chaos/enter_embody_chaos_stage",
               service_server_time=1790461000, **EMBODY_ENTRY)
    steps.step("stage/clear_stage", service_server_time=1790461600,
               stage_id=120000004)
    steps.step("disaster/enter_disaster_chaos_stage",
               service_server_time=1790463000, stage_info=SUPPORTERS,
               **DISASTER_ENTRY)
    steps.step("stage/clear_stage", service_server_time=1790463600,
               stage_id=100000)
    embody, disaster = (addon.chaos_runs + [{}, {}])[:2]
    team = [[30135, 2], [1025, 0]]
    if disaster.get("partners") != team or "partners" in embody:
        out.append(f"a run entered with Sig at LB2 and Ivy at LB0 records "
                   f"partners {disaster.get('partners')!r}, and one whose "
                   f"entry carries no stage {embody.get('partners')!r}: "
                   f"{team!r} in team order, and none at all.")
    later = _new(Addon)
    _setup(later)
    steps = _Steps(later, 1600)
    steps.step("world/get_stage_info", service_server_time=1790470000,
               stage_info=dict(_span_stage(["e0"]), **SUPPORTERS))
    steps.step("stage/clear_stage", service_server_time=1790470600,
               stage_id=100000)
    taken = later.chaos_runs[-1] if later.chaos_runs else {}
    if (taken.get("started_elsewhere"), taken.get("partners")) != (True,
                                                                   team):
        out.append(f"a run taken up from a stage reply reads started "
                   f"elsewhere {taken.get('started_elsewhere')!r} with "
                   f"partners {taken.get('partners')!r}, not True with "
                   f"{team!r}: the stage reply lists them as the entry "
                   f"does (`Addon._resume_chaos`).")
    held = game_client._facts
    try:
        game_client.use({"format": game_client.CACHE_FORMAT,
                         "exploration_effects": SIG_STEPS})
        tool = _tool()
        cells = [(row["partners"], row["invasion"]) for row in (
            tool.row_of(dict(disaster, client=client), "x", {})
            for client in ("cznlive 1.837 r126", "cznlive 1.814 r88"))]
        cells.append(tuple(tool.row_of(embody, "x", {})[key]
                           for key in ("partners", "invasion")))
        want = [("Sig LB2, Ivy LB0", "+16%"), ("Sig LB2, Ivy LB0", ""),
                ("?", "?")]
        if cells != want:
            out.append(f"docs/chaos_runs.py writes partners and invasion "
                       f"{cells}, not {want}: Sig's Danger Intuition at LB2 "
                       f"is +16% from the client that brought the passives, "
                       f"nothing before it, and a run that kept no partners "
                       f"is unknown.")
    finally:
        game_client.use(held)
    return out


def _report_read_as_paid():
    """Fault: chaos_runs.py's report reading each payout as paid, not at
    0 nodes. The tool is loaded from its file on each use, out of the
    runner's reach, so its loader is wrapped instead."""
    global _tool
    real = _tool

    def loaded():
        tool = real()
        tool.base_payouts = lambda row, recovered=False: [
            (tool._key(floor, spot, mark, tool.boss_orders(row)), spot,
             amount, mark, amount)
            for floor, spot, amount, mark
            in tool.payouts_of(row["payouts"], recovered)]
        return tool
    _tool = loaded


def _report_bosses_by_rank():
    """Fault: chaos_runs.py placing each boss by the order of the floors
    paid alone, the map's `floors` passed over."""
    global _tool
    real = _tool

    def loaded():
        tool = real()
        tool._map_end = lambda row: None
        return tool
    _tool = loaded


def _report_any_third_pay():
    """Fault: chaos_runs.py's changes table holding the third boss to
    whatever the odd one in the case paid, so neither odd pay is
    flagged."""
    global _tool
    real = _tool

    def loaded():
        tool = real()
        tool.THIRD_BOSS_PAYS = 59
        return tool
    _tool = loaded


def _report_fights_after():
    """Fault: chaos_runs.py counting every fight of a run as before
    its Senectus."""
    global _tool
    real = _tool

    def loaded():
        tool = real()
        held = tool.senectus_of

        def every(run):
            floors, _before = held(run)
            if "fights" not in run:
                return floors, _before
            counts = tool.collections.Counter(
                spot.lower() for _f, spot, _m in run["fights"])
            return floors, " ".join("%s:%d" % pair
                                    for pair in sorted(counts.items()))
        tool.senectus_of = every
        return tool
    _tool = loaded


def _report_no_door_unknown():
    """Fault: chaos_runs.py writing `?` for a run whose door has no
    Distortion Adaptation, as for one whose entry was never seen."""
    global _tool
    real = _tool

    def loaded():
        tool = real()
        tool.distortion_of = lambda run: {True: "on", False: "off"}.get(
            (run.get("level_mode") or {}).get("on"), "?")
        return tool
    _tool = loaded


def _map_stage(spots, area=0):
    """A Chaos stage carrying `spots`, (id, floor, type, mark) each, as
    an area's map in its replies: the mark True for a Rare Species,
    `eidolon` for a Persona Card spot, another string for that
    `event_id`."""
    def marked(mark):
        if mark is True:
            return {"event_id": "keyword_monster"}
        if mark == "eidolon":
            return {"eidolon_reward_tag_id": "tag_1"}
        return {"event_id": mark} if mark else {}
    return {"curr_area_id": area,
            "chaos_info": DISASTER_ENTRY["playing_stage_info"]["chaos_info"],
            "spot_list": [dict({"id": sid, "floor": floor,
                                "type": "SPOT_TYPE_" + kind}, **marked(mark))
                          for sid, floor, kind, mark in spots]}


def _the_map_and_route(Addon):
    """A run keeps each area's map as first sent -- its spot types
    counted, the Rare Species spots apart, and whether the list held one
    spot a floor, as a delegated run's route-only list does -- and
    every spot it entered by type. The map a later reply sends again,
    after a spot has turned into another, does not replace it. Returns
    complaints."""
    out = []
    addon = _new(Addon)
    _setup(addon)
    steps = _Steps(addon, 1700)
    whole = [(7, -1, "UNKNOWN", False), (8, 0, "UNKNOWN", False),
             (1, 1, "BATTLE", True), (2, 1, "ELITE", "eidolon"),
             (3, 2, "UNKNOWN", "dis04_desire_insert"), (4, 3, "BOSS", False)]
    steps.step("disaster/enter_disaster_chaos_stage",
               service_server_time=1790480000,
               stage_info={"stage": _map_stage(whole)}, **DISASTER_ENTRY)
    for sid, floor, kind in ((1, 1, "BATTLE"), (3, 2, "UNKNOWN")):
        steps.step("stage/enter_spot",
                   spot_info={"floor": floor, "spot_type": "SPOT_TYPE_" + kind,
                              "spot_id": sid},
                   stage_info=_map_stage(whole[:2] + [
                       (1, 1, "ELITE", False)] + whole[3:]))
    steps.step("stage/enter_spot",
               spot_info={"floor": 4, "spot_type": "SPOT_TYPE_BATTLE",
                          "spot_id": 9},
               stage_info=_map_stage([(9, 4, "BATTLE", False),
                                      (10, 5, "BOSS", False)], area=1))
    steps.step("battle/battle_start", snapshot={"cache": {
        "battle_init_wt": {"battle_res_id": "base_00160", "floor": 4},
        "battle_stage_wt": {"player": {"status": {"info": {
            "S_CURRENT_HP": 2400, "S_HP": 3200}}}}}})
    steps.step("stage/clear_stage", service_server_time=1790480600,
               stage_id=100000)
    run_ = addon.chaos_runs[-1] if addon.chaos_runs else {}
    if run_.get("hp") != [[4, 2400, 3200]] \
            or _tool().hp_of(run_) != "75-75%":
        out.append(f"a fight starting at 2400 of 3200 HP records hp "
                   f"{run_.get('hp')!r}, written {_tool().hp_of(run_)!r}: "
                   f"[[4, 2400, 3200]] and '75-75%', the party's HP off "
                   f"the stage's player status (`Addon._chaos_hp`).")
    want_maps = {"0": {"spots": {"BATTLE": 1, "ELITE": 1, "UNKNOWN": 1,
                                 "BOSS": 1},
                       "keyword": {"BATTLE": 1},
                       "events": {"keyword_monster": 1, "eidolon_reward": 1,
                                  "dis04_desire_insert": 1},
                       "path": False},
                 "1": {"spots": {"BATTLE": 1, "BOSS": 1}, "keyword": {},
                       "events": {}, "path": True}}
    want_route = {"BATTLE": 2, "UNKNOWN": 1}
    if (run_.get("maps"), run_.get("route")) != (want_maps, want_route):
        out.append(f"a run records maps {run_.get('maps')} and route "
                   f"{run_.get('route')}, not {want_maps} and {want_route}: "
                   f"each area's map as first sent, its Rare Species spots "
                   f"apart and a one-spot-a-floor list marked `path`, and "
                   f"every spot entered (`Addon._note_chaos_map`).")
    tool = _tool()
    cell = tool.map_of(run_)
    back = tool.maps_of(cell)
    if back.get("0", {}).get("keyword") != {"battle": 1} \
            or back.get("0", {}).get("events") != want_maps["0"]["events"] \
            or back.get("1", {}).get("path") is not True:
        out.append(f"chaos_runs.py writes the maps as {cell!r} and reads "
                   f"them back as {back}: the Rare Species spots, the spot "
                   f"events and the `path` mark do not survive the table.")
    for row, want in (
            ({"chaos": "Celestial Bulwark", "special": ""}, "s05"),
            ({"chaos": "Swamp of Judgment",
              "special": "Promise Upon the Snow+Sekred’s Breath"}, "s05"),
            ({"chaos": "Laboratory 0", "special": "Forbidden Catalyst"},
             "s01"),
            ({"chaos": "Twin Star's Shadow", "special": "Diallos’s Glory"},
             "no Effect")):
        if tool.effect_season(row) != want:
            out.append(f"chaos_runs.effect_season reads {row} as "
                       f"{tool.effect_season(row)!r}, not {want!r}: the "
                       f"season whose Effect shapes the map, by the Chaos's "
                       f"own or the Effect it was given.")
    return out


def _the_report_counts_each_mark_once():
    """`docs/chaos_runs.py` counts a marked fight toward the marks it
    is: a Senectus on a Rare Species spot as Senectus alone -- the spot
    was counted on the Rare Species fight before it -- season 3's
    Persona Card battle, tagged `k0+k1`, as one mark, and the Aether
    Eater over battles alone, where it is met. Counting the inherited
    keyword again counts the spot twice. Returns complaints."""
    tool = _tool()
    out = []
    for key, want in (("b1+k5", ["b1"]), ("k0+k1", []),
                      ("k5", ["k5"]), ("e+k5", ["e", "k5"])):
        if tool.identities(key) != want:
            out.append(f"chaos_runs.identities reads {key!r} as "
                       f"{tool.identities(key)}, not {want}.")
    rows = [{"marked": "b1+k5:1 k5:2 e:1",
             "marked_at": "battle.k5:1 elite.k5:1 battle.e:1 "
                          "break_in.b1+k5:1",
             "fought": "battle:10 elite:4", "payouts": "", "amplified": "0",
             "season": "s04"}]
    facts = tool._group_facts(rows)
    met_on = tool.spots_met(rows)
    got = (tool.over_of(facts, "k5", met_on), tool.over_of(facts, "e", met_on),
           tool.over_of(facts, "b1", met_on))
    if got != ((2, 14), (1, 10), (1, 1)):
        out.append(f"a run meeting a Rare Species battle and Elite, Senectus "
                   f"on the battle's spot and an Aether Eater reads {got}, "
                   f"not ((2, 14), (1, 10), (1, 1)): the Rare Species "
                   f"twice over every fight, the Aether Eater over battles, "
                   f"Senectus over runs.")
    return out


def _the_report_pools_and_steps():
    """`docs/chaos_runs.py`'s bosses table puts every Chaos but a
    season's own on one `offseason` row while they keep one pattern, and
    one that breaks it on an `exception` row of its own; and its
    version steps show a step between parts or game versions only where
    it shifts. Pooled blindly, an odd Chaos would hide in the pattern;
    listed in full, the steps bury the one that moved. Returns
    complaints."""
    import contextlib
    import io
    tool = _tool()

    def row(date, chaos, door, payouts, part="part 3", client="1.464 r688"):
        return {"date": date, "season": "s04", "part": part, "chaos": chaos,
                "door": door, "special": "", "client": "cznlive " + client,
                "amplified": "0", "floors": "0-34", "payouts": payouts,
                "marked": "", "marked_at": "", "fought": "battle:10"}

    out = []
    rows = {r["date"]: r for r in (
        row("2026-09-01 00:00", "Burning Life", "Zero System",
            "17:boss:108 34:boss:108"),
        row("2026-09-02 00:00", "Laboratory 0", "Zero System",
            "17:boss:108 34:boss:108"),
        row("2026-09-03 00:00", "Theater of Illusions", "Zero System",
            "17:boss:108 34:boss:120"))}
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        tool.bosses_table(rows)
    lines = printed.getvalue().splitlines()
    offseason = [line for line in lines if "offseason" in line]
    odd = [line for line in lines if "exception" in line]
    if len(offseason) != 1 or "Theater" in offseason[0] or len(odd) != 1 \
            or "Theater of Illusions" not in odd[0]:
        out.append(f"chaos_runs.bosses_table printed {lines}: Burning Life "
                   f"and Laboratory 0 on one offseason row, and Theater of "
                   f"Illusions, its second boss paying 120 where theirs pay "
                   f"108, on an exception row of its own.")
    own = {r["date"]: r for r in (
        row("2026-09-10 00:00", "The Kaleidoscope Hatchery",
            "Galactic Disaster", "17:boss:144", "part 2"),
        row("2026-09-20 00:00", "The Kaleidoscope Hatchery",
            "Galactic Disaster", "17:boss:150", "part 3"),
        row("2026-09-21 00:00", "The Kaleidoscope Hatchery",
            "Galactic Disaster", "17:boss:150", "part 3", "1.465 r690"))}
    shifted = {name: [moved for _step, moved in tool._steps(own, key)]
               for name, key in tool.STEPS}
    if shifted != {"season": [], "part": [True], "version": [True, False]}:
        out.append(f"chaos_runs._steps reads a first boss paying 144 in "
                   f"part 2 and 150 in part 3, the same over part 3's two "
                   f"versions, as {shifted}: no step between seasons, the "
                   f"part step and the version step crossing it shifted, "
                   f"the later version step not.")
    return out


def _the_report_pools_by_default():
    """`docs/chaos_runs.py` pools by default and shows every row with
    `--full` (`FULL`): a rate table's single map only where its rate
    differs from the rest of its Effect's pool, as a red exception;
    the other Chaos by when they were played, the preseason -- which
    pays nothing, its shop not open -- on a row of its own, and a Chaos
    whose bosses pay otherwise than the rest as an exception. Returns
    complaints."""
    import contextlib
    import io
    tool = _tool()
    out = []

    def run(date, chaos, special, met, part="part 3", payouts=""):
        return {"date": date, "season": "s05", "part": part, "chaos": chaos,
                "door": "Zero System", "special": special,
                "mode": "delegated", "client": "cznlive 1.837 r130",
                "amplified": "0", "floors": "0-28", "payouts": payouts,
                "marked": "b1:1" if met else "", "marked_at": "",
                "fought": "battle:10"}

    runs = [run("2026-10-0%d 00:00" % n, "Swamp of Judgment",
                "Promise Upon the Snow", False) for n in range(1, 9)]
    runs += [run("2026-10-1%d 00:00" % n, "The Blue Pot",
                 "Promise Upon the Snow", True) for n in range(1, 9)]

    def measure(members):
        return sum(1 for row in members if tool.met_of(row)), len(members)

    shown = tool.pools_shown(runs, measure, tool.FEWEST_RUNS)
    odd = sorted(label for _t, label, _m, exception in shown if exception)
    tool.FULL = True
    every = tool.pools_shown(runs, measure, tool.FEWEST_RUNS)
    tool.FULL = False
    if odd != ["Swamp of Judgment, Promise Upon the Snow, delegated",
               "The Blue Pot, Promise Upon the Snow, delegated"] \
            or any(exception for *_rest, exception in every) \
            or len(every) <= len(shown) - len(odd):
        out.append(f"chaos_runs.pools_shown marks {odd} as exceptions for "
                   f"a map meeting Senectus in none of 8 runs and one in "
                   f"all 8 under one Effect, and shows {len(every)} pools "
                   f"with --full: both maps exceptions to the rest of "
                   f"their Effect's pool, and --full every pool with "
                   f"none marked.")
    others = {"x": [
        run("2026-09-01 00:00", "Laboratory 0", "", False, "preseason"),
        run("2026-09-02 00:00", "Burning Life", "", False, "part 2",
            "17:boss:108 28:boss:108"),
        run("2026-09-03 00:00", "Twin Star's Shadow", "", False, "part 2",
            "17:boss:108 28:boss:108"),
        run("2026-09-04 00:00", "The Blue Pot", "", False, "part 2",
            "17:boss:108 28:boss:130")]}
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        tool.others_table(others, {})
    lines = printed.getvalue().splitlines()
    rows = {line.split()[0] + (" " + line.split()[1] if line.split()[0]
                               in ("offseason", "exception:") else ""):
            line for line in lines[3:]}
    if set(rows) != {"preseason", "offseason s05", "exception: offseason"} \
            or "The Blue Pot" not in rows.get("exception: offseason", "") \
            or "2 Chaos" not in rows.get("offseason s05", ""):
        out.append(f"chaos_runs.others_table printed {lines}: the "
                   f"preseason run on a row of its own, Burning Life and "
                   f"Twin Star's Shadow on one offseason row, and The Blue "
                   f"Pot, its second boss paying 130, as an exception.")
    return out


def _report_pools_never_odd():
    """Fault: chaos_runs.py's rate pools never finding a map that
    differs from its Effect's."""
    global _tool
    real = _tool

    def loaded():
        tool = real()
        tool._rate_moved = lambda *args, **kwargs: ([], False)
        return tool
    _tool = loaded


def _report_preseason_pooled_in():
    """Fault: chaos_runs.py pooling the preseason with the offseason."""
    global _tool
    real = _tool

    def loaded():
        tool = real()
        tool.period_of = lambda row: "offseason %s" % row["season"]
        return tool
    _tool = loaded


def _report_breakins_counted_twice():
    """Fault: chaos_runs.py counting a break-in toward every mark it
    carries."""
    global _tool
    real = _tool

    def loaded():
        tool = real()
        tool.identities = lambda key: key.split("+")
        return tool
    _tool = loaded


def _report_effects_unknown():
    """Fault: chaos_runs.py knowing no season's Effect by its special
    option, so a Zero System map given one pools by its Chaos alone."""
    global _tool
    real = _tool

    def loaded():
        tool = real()
        tool.EFFECT_SEASONS = {}
        return tool
    _tool = loaded


def _report_offseason_all_kept():
    """Fault: chaos_runs.py's bosses table pooling every other Chaos on
    the offseason row, the one that breaks the pattern among them."""
    global _tool
    real = _tool

    def loaded():
        tool = real()
        source = tool.bosses_table
        tool.bosses_table = lambda rows: source({
            date: dict(row, payouts=row["payouts"].replace(
                "34:boss:120", "34:boss:108")) for date, row in rows.items()})
        return tool
    _tool = loaded


def _report_steps_unshifted():
    """Fault: chaos_runs.py's version steps never calling a step
    shifted, so no finer step is ever shown."""
    global _tool
    real = _tool

    def loaded():
        tool = real()
        source = tool._steps
        tool._steps = lambda rows, key: [(step, False)
                                         for step, _s in source(rows, key)]
        return tool
    _tool = loaded


# What this check must catch, for `checks/faults.py`.
FAULTS = [
    ("a run left by its capture not taken up",
     "capture.manager:ADDON_TEMPLATE",
     "        if self.chaos_run is None and asked in CHAOS_RESUMES:\n"
     "            self._resume_chaos(data)",
     "        pass", "a run taken up by the next capture reads"),
    ("a run in progress kept only as it entered",
     "capture.manager:ADDON_TEMPLATE",
     "if asked in (CHAOS_ENTERS, CHAOS_RESOLVES, CHAOS_FIGHTS, CHAOS_PAYS):",
     "if False:", "a run taken up by the next capture reads"),
    ("another run's leftovers taken up", "capture.manager:ADDON_TEMPLATE",
     "        if not (run and kept and events[:len(kept)] == kept",
     "        if not (run and kept",
     "a stage whose events do not begin with the run left open"),
    ("the clear's restatement not kept", "capture.manager:ADDON_TEMPLATE",
     'run["restated"] = [', 'run["restated_not"] = [',
     "a run taken up by the next capture reads"),
    ("a Sortie taken up as a Chaos run", "capture.manager:ADDON_TEMPLATE",
     "        if via is None:\n            return\n",
     "        if via is None:\n            via = \"chaos\"\n",
     "a Sortie's stage was taken up"),
    ("the spot a resuming reply enters noted unseen",
     "capture.manager:ADDON_TEMPLATE",
     '            entered.add(entering["spot_id"])',
     "            pass", "a run taken up on a spot's own entry"),
    ("the opening floors noted unseen", "capture.manager:ADDON_TEMPLATE",
     '                    or spot["floor"] < 1):',
     '                    or spot["floor"] < 0):',
     "a stage whose events do not begin with the run left open"),
    ("an amount both pay placed on a boss", "chaos_estimate:recovery",
     'if (BOSS, "") in options and not marks and bosses:',
     'if (BOSS, "") in options and bosses:',
     "an amount both a boss and a mark pay"),
    ("a Galactic Disaster run's difficulty read a level up",
     "capture.manager:ADDON_TEMPLATE",
     'or disaster.get("disaster_list_id")),',
     'or info.get("disaster_list_id")),',
     "a Galactic Disaster run records difficulty"),
    ("the partners not kept", "capture.manager:ADDON_TEMPLATE",
     "    if isinstance(team, list):\n        out[\"partners\"]",
     "    if False:\n        out[\"partners\"]",
     "a run entered with Sig at LB2"),
    ("an entry with no stage read as a team without partners",
     "capture.manager:ADDON_TEMPLATE",
     'team = stage.get("enter_supporters") if isinstance(stage, dict) '
     'else None',
     'team = stage.get("enter_supporters") if isinstance(stage, dict) '
     'else []',
     "a run entered with Sig at LB2"),
    ("a run taken up without its partners", "capture.manager:ADDON_TEMPLATE",
     '"stage_info": data.get("stage_info")})',
     '"stage_info": None})', "a run taken up from a stage reply"),
    ("the report reading payouts as paid", _report_read_as_paid, None, None,
     "180 at 25 nodes is 144 at 0"),
    ("a payout no whole base fits read as one",
     "chaos_estimate:base_of",
     "    if amplified(whole, nodes) == amount:\n        return whole\n"
     "    return amount * 100 / (100 + nodes)",
     "    return whole", "181 at 25 nodes"),
    ("a later map replacing the first", "capture.manager:ADDON_TEMPLATE",
     "        if held and area not in maps:", "        if held:",
     "each area's map as first sent"),
    ("a route-only list taken for a whole map",
     "capture.manager:ADDON_TEMPLATE",
     '"path": max(floors.values()) == 1}', '"path": False}',
     "each area's map as first sent"),
    ("a spot entered twice counted once", "capture.manager:ADDON_TEMPLATE",
     "                route[spot] = route.get(spot, 0) + 1",
     "                route[spot] = 1", "each area's map as first sent"),
    ("Nightmare Mode not kept", "capture.manager:ADDON_TEMPLATE",
     '                self.chaos_nightmare = sent.get("is_psychosis_mode")\n',
     "", "a Nightmare Mode run picking"),
    ("a later event's pick taken for the opening",
     "capture.manager:ADDON_TEMPLATE",
     ['            if (not isinstance(choice, dict) or "opening" in run\n',
      '                    or choice.get("encounter_id") != '
      'run.get("opening_event")):\n'],
     ["            if (not isinstance(choice, dict)\n",
      "                    or False):\n"],
     "a Nightmare Mode run picking"),
    ("the party's HP not kept", "capture.manager:ADDON_TEMPLATE",
     "                self._chaos_hp(run, cache)\n", "",
     "a fight starting at 2400 of 3200 HP"),
    ("the party's most HP read as its current",
     "capture.manager:ADDON_TEMPLATE",
     'current, most = info.get("S_CURRENT_HP"), info.get("S_HP")',
     'current, most = info.get("S_HP"), info.get("S_HP")',
     "a fight starting at 2400 of 3200 HP"),
    ("a map's spot events but the Rare Species dropped",
     "capture.manager:ADDON_TEMPLATE",
     "            if event:\n", "            if event == \"keyword_monster\":\n",
     "each area's map as first sent"),
    ("a Zero System map pooled by its Chaos, not its Effect",
     _report_effects_unknown, None, None, "the season whose Effect shapes"),
    ("the bosses table hiding an odd Chaos in the offseason row",
     _report_offseason_all_kept, None, None, "on an exception row"),
    ("the version steps never shifted", _report_steps_unshifted, None, None,
     "the part step and the version step"),
    ("the rate pools never finding an odd map", _report_pools_never_odd,
     None, None, "both maps exceptions"),
    ("the preseason pooled with the offseason", _report_preseason_pooled_in,
     None, None, "the preseason run on a row of its own"),
    ("the report counting a break-in's keyword again",
     _report_breakins_counted_twice, None, None,
     "the Rare Species twice over every fight"),
    ("the report placing bosses by the floors paid alone",
     _report_bosses_by_rank, None, None, "the map's last floor is the second"),
    ("the report holding the third boss to no pay",
     _report_any_third_pay, None, None, "a third boss paying 59"),
    ("a partner's passive counted before the passives came",
     "chaos_estimate:run_raise",
     'return invasion_raise(run["partners"]) if had_passives(run) else 0.0',
     'return invasion_raise(run["partners"])',
     "nothing before it"),
    ("fights not kept in order", "capture.manager:ADDON_TEMPLATE",
     '        run.setdefault("fights", []).append([floor, spot, mark])\n',
     "", "a Senectus breaking in on floor 6"),
    ("Distortion Adaptation not kept", "capture.manager:ADDON_TEMPLATE",
     '                    "on": sent.get("is_chaos_level_mode"),\n',
     '                    "on": None,\n', "Distortion Adaptation off"),
    ("the fights after the Senectus counted before it",
     _report_fights_after, None, None, "a Senectus breaking in on floor 6"),
    ("the assigned partners' flags not kept", "capture.manager:ADDON_TEMPLATE",
     '                    "custom_supporters": sent.get(\n'
     '                        "chaos_level_mode_custom_supporter_info")}',
     '                    "custom_supporters": None}',
     "Distortion Adaptation assigned keeps the flags"),
    ("a door without Distortion Adaptation read as unknown",
     _report_no_door_unknown, None, None, "a Zero System run is written"),
]
