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
    failures.extend(_the_table_keeps_a_replayed_row())
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


def _the_table_keeps_a_replayed_row():
    """`docs/chaos_runs.py`'s default pass keeps a row a log was replayed
    into against the capture's own record of the same run.

    The default pass reads only the newest logs, and every run the
    runs' file holds; the file's record was made by the capture code of
    its day. Written over a log's row, it took back a break-in the
    record never saw (the 2026-09-28 00:42 run) and blanked every field
    added since. `--all` rebuilds from what it reads, which is right."""
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
    return failures
