"""What the capture records of a Galactic Disaster Chaos run.

`docs/chaos_runs.py` reads these records out of snapshots and debug
logs alike, and everything it reports stands on them. Each part fails
quietly:

1. **A payout is the drop the player takes**, in the season's currency
   group. Another item in the same drop is not one.
2. **A fight's mark is noted whether or not it paid** -- a
   `keyword_tag`, a battle id ending `_e` -- since how often a mark
   turns up is counted over the fights fought.
3. **The run names its season** from the Great Rift standings, and its
   game version from the connection's `helo`. A new season's currency
   is a new item id, and nothing downstream is told which.
4. **A run is filed once**, by the second it cleared, however often
   the same clear is read.
5. **The runs carry from one snapshot to the next**, like the ranking
   history: a capture that starts empty writes them away at its first
   save.

Synthetic frames in the shapes of `websocket_debug_20260925_194713`.
No Tk and no snapshot needed.
"""

import json
import tempfile
from pathlib import Path

from ._harness import add_source_to_path
from .check_capture_history import _Flow, _addon_class

NAME = "capture records Chaos runs"

CURRENCY = 3920031
EXPECTED_PAID = [[6, "BATTLE", "k5", CURRENCY, 60],
                 [17, "BOSS", "", CURRENCY, 180]]


def _play(addon, closed):
    """One run: a marked fight that pays, a marked one that does not,
    and a boss, cleared at `closed`."""
    qid = [100]

    def step(command, **reply):
        qid[0] += 1
        family, _, inner = command.partition("/")
        addon.websocket_message(_Flow([{
            "cmd": family, "qid": qid[0], "params": {"cmd": inner}}],
            from_client=True))
        addon.websocket_message(_Flow([{"res": "ok", "qid": qid[0],
                                        **reply}]))

    def fight(floor, spot, battle, **marks):
        step("stage/enter_spot", spot_info={"floor": floor,
                                            "spot_type": spot})
        step("battle/battle_start", snapshot={"cache": {"battle_init_wt": {
            "battle_res_id": battle, "floor": floor, **marks}}})

    step("disaster/enter_disaster_chaos_stage",
         service_server_time=closed - 1800)
    fight(6, "SPOT_TYPE_BATTLE", "base_00160", keyword_tag=[5, 5])
    step("spot_reward/get_drop_item", drop_item_result=[
        {"id": CURRENCY, "amount": 60, "group": "disaster_material"},
        {"id": 3000005, "amount": 3, "group": "chaos_orb"}])
    fight(25, "SPOT_TYPE_BATTLE", "base_00167_e")
    fight(17, "SPOT_TYPE_BOSS", "base_00000")
    step("spot_reward/get_drop_item", drop_item_result=[
        {"id": CURRENCY, "amount": 180, "group": "disaster_material"}])
    step("stage/clear_stage", service_server_time=closed)


def _setup(addon):
    """A connection's `helo`, and the standings that name the season."""
    addon.websocket_message(_Flow([{"cmd": "helo", "params": {
        "device_data": {"client_version": "cznlive 1.464",
                        "patch_version": '{"res":688,"media":227}'}}}],
        from_client=True))
    addon.websocket_message(_Flow([{"res": "ok",
                                    "disaster_boss_rank_entities": {
        "disaster_s03": {"disaster_s03_rank_02": {"score_week_id": 170}},
        "disaster_s04": {"disaster_s04_rank_02": {"score_week_id": 193}},
    }}]))


def run():
    add_source_to_path()
    Addon = _addon_class()
    failures = []
    folder = Path(tempfile.mkdtemp(prefix="capture_chaos_"))
    addon = Addon(folder, log_callback=lambda *a, **k: None)
    _setup(addon)
    _play(addon, closed=1790365000)

    runs = addon.chaos_runs
    if len(runs) != 1:
        return [f"one run played, {len(runs)} recorded. Without its record, "
                f"the run is in no snapshot and chaos_runs.py never sees "
                f"it."]
    run_ = runs[0]
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

    # Saved, carried into the next capture, and read again: still one.
    addon.inventory_data = {"memory_fragments": []}
    addon._save_data()
    saved = json.loads(Path(addon.saved_path).read_text(encoding="utf-8"))
    if saved.get("chaos_runs") != runs:
        failures.append("a saved snapshot does not carry the Chaos runs, "
                        "which is the only place a player's runs are kept.")
    again = Addon(folder, log_callback=lambda *a, **k: None)
    if again.chaos_runs != runs:
        failures.append(
            "the Chaos runs did not carry into the next capture; it would "
            "write them away at its first save.")
    _setup(again)
    _play(again, closed=1790365000)
    if len(again.chaos_runs) != 1:
        failures.append(
            f"the same clear read twice made {len(again.chaos_runs)} runs. "
            f"A run is filed by the second it cleared, or a replayed "
            f"capture doubles every run in it.")
    return failures
