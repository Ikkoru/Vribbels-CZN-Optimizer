"""The event shapes a Checklist row has to recognise before it can count.

Every one of these misreads as a plausible number rather than an error:

* a **Node List** is scheduled by its own number and its missions carry
  a combatant's, so a reader pairing by name finds no rows and the row
  shows a deadline and nothing else;
* an **earlier instalment's rows** outlive its schedule, and the stem
  that finds a devil event's later days swallowed all of them -- one
  arena recorded as holding 40 rewards where it held 17;
* one instalment **scheduled twice** voted twice for its family's total
  and agreed with itself;
* a **final reward** is invisible until claimed, so the row has to know
  the family pays one to say it is waiting;
* a **step track** is one accumulating mission row that is never itself
  claimed, and read as a mission it is `0/1+?` for the event's whole run.

`docs/events.md` has the evidence for each. No Tk and no snapshot
needed.
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace

from ._harness import add_source_to_path

NAME = "event shapes"

NOW = 1789380000
DAY = 24 * 3600


def _mission(res_id, issued=None, claimed=False):
    row = {"res_id": res_id, "complete_time": 1 if claimed else 0}
    if issued is not None:
        row["issued_time"] = issued
    return row


def _raw(missions=(), records=(), schedules=None):
    raw = {"mission_entities": {row["res_id"]: row for row in missions}}
    if records:
        raw["event_mission_reward_entities"] = list(records)
    if schedules:
        raw["event_schedules"] = schedules
    return raw


def _manager():
    import checklist_manager
    manager = checklist_manager.ChecklistManager(
        Path(tempfile.mkdtemp(prefix="event_shapes_")))
    manager.load()
    return manager


def _recalled(ct, raw, manager=None):
    """`raw` after the tab's two recall passes, and the manager."""
    manager = manager or _manager()
    stub = SimpleNamespace(context=SimpleNamespace(checklist_manager=manager))
    ct.ChecklistTab._recall_event_totals(stub, raw, NOW)
    ct.ChecklistTab._recall_finals(stub, raw, NOW)
    return raw, manager


def _node_lists(ct):
    """A Node List owns the instalment its window saw issued FIRST."""
    out = []
    six = {"start_time": NOW - 40 * DAY, "end_time": NOW - 19 * DAY}
    seven = {"start_time": NOW - 19 * DAY + 3600, "end_time": NOW + 2 * DAY}
    missions = (
        # An instalment older than both windows: nobody's.
        _mission("event_node_1055_1_01", issued=NOW - 90 * DAY),
        _mission("event_node_30113_1_01", issued=NOW - 39 * DAY),
        # Issued days in, inside SEVEN's window: still six's instalment,
        # because its FIRST row places it.
        _mission("event_node_30113_2_01", issued=NOW - 10 * DAY),
        _mission("event_node_30115_1_01", issued=NOW - 18 * DAY),
        _mission("event_node_30115_achievement_01", issued=NOW - 9 * DAY),
    )
    raw = _raw(missions, schedules={"EVENT_NODELIST_PAGE": {
        "event_nodelist_006": six, "event_nodelist_007": seven}})
    for name, want in (
            ("event_nodelist_006", ["event_node_30113_1_01",
                                    "event_node_30113_2_01"]),
            ("event_nodelist_007", ["event_node_30115_1_01",
                                    "event_node_30115_achievement_01"])):
        got = ct._event_rows(raw, name)
        if got != want:
            out.append(
                f"{name} took {got!r}, not {want!r}. A Node List's missions "
                f"carry the combatant's number and the schedule carries its "
                f"own, so the only link is WHEN the instalment's first row "
                f"was issued -- inside the schedule's window, and nobody "
                f"else's.")

    # No window, no pairing: without one every instalment would do.
    bare = _raw(missions, schedules={"EVENT_NODELIST_PAGE": {
        "event_nodelist_007": {}}})
    if ct._event_rows(bare, "event_nodelist_007"):
        out.append(
            "a Node List with no window took rows. Time is the only link "
            "to its missions, and without a window it would link to all "
            "of them.")

    # Its completion record sits on the ACHIEVEMENT page, under the
    # instalment's own id.
    flagged = dict(raw, event_mission_reward_entities=[{
        "res_id": "event_node_30115_achievement", "reward_step": 0,
        "version": 0, ct.EVENT_DONE_FLAG: ct.EVENT_DONE_VALUE}])
    if not ct._event_finished(flagged, "event_nodelist_007"):
        out.append(
            "event_node_30115_achievement did not finish event_nodelist_007. "
            "The later Node Lists keep their completion record on the "
            "achievement page, under the instalment the list owns.")
    if ct._event_finished(flagged, "event_nodelist_006"):
        out.append("one Node List's completion record finished another.")
    return out


def _earlier_instalments(ct):
    """Rows issued before every row of the event's own are not its."""
    out = []
    july = NOW - 60 * DAY
    missions = [_mission("event_arena_1_1_%02d" % n, issued=july - 110 * DAY)
                for n in range(1, 4)]
    missions += [_mission("event_arena_2_1_01", issued=july + DAY),
                 _mission("event_arena_2_2_01", issued=july + 2 * DAY)]
    raw = _raw(missions, schedules={"EVENT_ARENA": {"event_arena_2": {
        "start_time": july, "end_time": july + 21 * DAY}}})
    got = ct._event_rows(raw, "event_arena_2")
    if got != ["event_arena_2_1_01", "event_arena_2_2_01"]:
        out.append(
            f"event_arena_2 took {got!r}. arena_1's rows outlived its "
            f"schedule, and the stem that finds a devil event's later DAYS "
            f"took them as arena_2's -- recording one instalment as 40 "
            f"rewards where it held 17. A row issued before any of the "
            f"event's own belongs to an earlier instalment.")

    # The devil's later days arrive WITH day one, in its opening batch,
    # and must still be taken.
    batch = NOW - 5 * DAY
    devil = [_mission("event_devil_%02d_%02d" % (day, task), issued=batch)
             for day in range(1, 8) for task in range(1, 4)]
    raw = _raw(devil, schedules={"EVENT_SCHEDULE": {
        "event_schedule_devil_001": {"start_time": batch - DAY,
                                     "end_time": batch + 20 * DAY}}})
    got = len(ct._event_rows(raw, "event_schedule_devil_001"))
    if got != 21:
        out.append(
            f"the devil event took {got} of its 21 rows. Its later days "
            f"were issued in the same batch as day one, which is not "
            f"earlier than day one.")
    return out


def _one_instalment_votes_once(ct):
    """Two schedules of one instalment are one vote for the family."""
    out = []
    manager = _manager()
    manager.record_event_total("event_arena", "event_schedule_arena_2", 17)
    manager.record_event_total("event_arena", "event_arena_2", 17)
    got = manager.event_total("event_arena", "event_arena_3",
                              same=ct._event_key)
    if got is not None:
        out.append(
            f"one arena scheduled twice answered for the family with "
            f"{got!r}. `event_schedule_arena_2` and `event_arena_2` are the "
            f"same instalment, and one instalment is a number rather than "
            f"a pattern.")
    manager.record_event_total("event_arena", "event_schedule_arena_1", 17)
    if manager.event_total("event_arena", "event_arena_3",
                           same=ct._event_key) != 17:
        out.append("two real instalments of one family did not agree on 17.")
    # The live instalment's twin must not vote for it either.
    if manager.event_total("event_arena", "event_arena_2",
                           same=ct._event_key) is not None:
        out.append(
            "a live instalment's own twin schedule voted on its total. A "
            "live instalment's rows are what has been issued so far.")
    return out


def _final_rewards(ct):
    """A family that paid a final reward is watched for the next one."""
    out = []
    ended = {"start_time": NOW - 60 * DAY, "end_time": NOW - 40 * DAY}
    live = {"start_time": NOW - 5 * DAY, "end_time": NOW + 10 * DAY}

    def event(live_claimed, final_taken=False, step=0, past_final=True):
        missions = [_mission("event_probe_1_%02d" % n, claimed=True)
                    for n in range(1, 4)]
        missions += [_mission("event_probe_2_%02d" % n,
                              claimed=n <= live_claimed)
                     for n in range(1, 4)]
        records = []
        if past_final:
            records.append({"res_id": "event_probe_1", "reward_step": step,
                            "version": step, ct.EVENT_DONE_FLAG:
                                ct.EVENT_DONE_VALUE})
        if final_taken:
            records.append({"res_id": "event_probe_2", "reward_step": 0,
                            "version": 0, ct.EVENT_DONE_FLAG:
                                ct.EVENT_DONE_VALUE})
        raw = _raw(missions, records, {"EVENT_SCHEDULE": {
            "event_probe_1": ended, "event_probe_2": live}})
        raw, manager = _recalled(ct, raw)
        return ct._event_missions(raw, "event_probe_2", live, NOW), manager

    got, manager = event(live_claimed=3)
    want = [("3/4" + ct.UNKNOWN_MORE, ct.FINAL_WAITING)]
    if got != want:
        out.append(
            f"every row claimed, and a family that paid a final reward last "
            f"time, reads {got!r}, not {want!r}. The final reward is "
            f"invisible until claimed; the family's past is the only thing "
            f"that says it is waiting.")
    if manager.finals != {"event_probe": ["event_probe_1"]}:
        out.append(
            f"the family's final reward was recorded as {manager.finals!r}. "
            f"Its record is purged weeks after the instalment ends, so it "
            f"has to be written down while it is there.")
    if ct.unsure_ceiling(got) != (3, 4):
        out.append(
            f"a waiting final reward did not ask `Finished?` "
            f"({ct.unsure_ceiling(got)!r}). It is known only from the "
            f"family's past, and the person who can see the game is the "
            f"one who knows whether this instalment has one.")

    got, _manager = event(live_claimed=2)
    if got != [("2/4" + ct.UNKNOWN_MORE, ct.FLOOR)]:
        out.append(
            f"a row still unclaimed beside a known final reward reads "
            f"{got!r}. The final is counted in the total, and the row is "
            f"an ordinary floor until the rows are all taken.")

    got, _manager = event(live_claimed=3, final_taken=True)
    if got != [("4/4", ct.DONE)]:
        out.append(
            f"a final reward the game has recorded as taken reads {got!r}, "
            f"not 4/4 done.")

    # A family nobody has seen pay one reads as it always did.
    got, manager = event(live_claimed=3, past_final=False)
    if got != [("3/3" + ct.UNKNOWN_MORE, ct.FLOOR)] or manager.finals:
        out.append(
            f"a family with no final reward on record reads {got!r} and "
            f"recorded {manager.finals!r}. Nothing says it has one.")

    # A STEP TRACK flags on its own ladder, which is not a final reward.
    got, manager = event(live_claimed=3, step=10)
    if manager.finals:
        out.append(
            f"a finished step track was recorded as a final reward: "
            f"{manager.finals!r}. Its flag is the ladder's own.")
    return out


def _step_tracks(ct):
    """A step track is read off its record, never its one mission row."""
    out = []
    live = {"start_time": NOW - 5 * DAY, "end_time": NOW + 10 * DAY}

    def event(step, flag=0, history=()):
        missions = [_mission("event_love_09_01")]
        records = [{"res_id": "event_season_love_9", "reward_step": step,
                    "version": 3, ct.EVENT_DONE_FLAG: flag}]
        windows = {"event_schedule_love_9": live}
        for index, past in enumerate(history, start=1):
            missions.append(_mission("event_love_%02d_01" % index))
            records.append({"res_id": "event_season_love_%d" % index,
                            "reward_step": past, "version": 9,
                            ct.EVENT_DONE_FLAG: 0})
            windows["event_schedule_love_%d" % index] = {
                "start_time": NOW - (60 + 30 * index) * DAY,
                "end_time": NOW - (50 + 30 * index) * DAY}
        raw = _raw(missions, records, {"EVENT_SCHEDULE": windows})
        raw, manager = _recalled(ct, raw)
        return ct._event_missions(raw, "event_schedule_love_9", live,
                                  NOW), manager

    got, _manager = event(step=7)
    if got != [("7/7" + ct.UNKNOWN_MORE, ct.FLOOR)]:
        out.append(
            f"a step track seven steps in reads {got!r}. Its one mission "
            f"row accumulates a score and is never itself claimed, so read "
            f"as a mission the event is 0/1+? for its whole run; the steps "
            f"are on the record.")
    got, _manager = event(step=7, flag=ct.EVENT_DONE_VALUE)
    if got != [("7/7", ct.DONE)]:
        out.append(f"a flagged step track reads {got!r}, not 7/7 done.")
    got, manager = event(step=7, history=(21, 21))
    if got != [(ct.EXPECTED_VALUE + "7/21", ct.TODO)]:
        out.append(
            f"a step track whose family finished at 21 twice reads {got!r}. "
            f"A finished instalment is filed under its STEPS, so the family "
            f"total is there to be read.")
    if manager.events.get("event_love") != {"event_schedule_love_1": 21,
                                            "event_schedule_love_2": 21}:
        out.append(
            f"finished step tracks were filed as {manager.events!r}. Filed "
            f"by their mission rows, every one of them holds 1.")

    # A record with no steps on it is not a step track: the bartender's
    # final reward wrote (0, 0, 1).
    raw = _raw([_mission("event_bartender_1_01_01", claimed=True)],
               [{"res_id": "event_bartender_1", "reward_step": 0,
                 "version": 0, ct.EVENT_DONE_FLAG: ct.EVENT_DONE_VALUE}])
    if ct._step_records(raw, "event_bartender_01"):
        out.append("a final reward's (0, 0, 1) record read as a step track.")
    return out


def run():
    add_source_to_path()
    from ui.tabs import checklist_tab as ct

    failures = []
    for probe in (_node_lists, _earlier_instalments, _one_instalment_votes_once,
                  _final_rewards, _step_tracks):
        failures.extend(probe(ct))
    return failures
