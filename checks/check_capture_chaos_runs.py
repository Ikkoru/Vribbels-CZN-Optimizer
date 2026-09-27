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
3. **The run names its season** from the Great Rift standings, and its
   game version from the connection's `helo`. A new season's currency
   is a new item id, and nothing downstream is told which.
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
   the stage id its clear names, `disaster` or `zero_orb`, and whether
   the Delegation Module played it -- said only in what the client sent
   to open it (`websocket_debug_20260927_202839`). A past season's
   Chaos pays less, and the estimate must leave it out.

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

    _the_file(Addon, failures)
    return failures
