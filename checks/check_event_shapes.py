"""The event shapes a Checklist row has to recognise before it can count.

Every one of these misreads as a plausible number rather than an error:

* a **Node List** is scheduled by its own number and its missions carry
  a combatant's, so a reader pairing by name finds no rows and the row
  shows a deadline and nothing else;
* an **earlier instalment's rows** outlive its schedule, and the stem
  that finds a devil event's later days swallowed all of them -- one
  arena read as holding 40 rewards where it held 17;
* the game client can name one instalment **twice**, under its
  schedule's id and its own, and a family rule counting ids lets it
  agree with itself;
* a **final reward** is invisible until claimed, so the row has to know
  the event pays one to say it is waiting;
* a **step track** is one accumulating mission row that is never itself
  claimed, and read as a mission it is `0/1+?` for the event's whole run.

`docs/events.md` has the evidence for each. No Tk, no snapshot and no
game client needed: the client's totals are given in the shape
`game_client.known_event_totals` returns.
"""

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


def _onto(ct, raw, known=None):
    """`raw` with the client's totals put on it, as a refresh does.
    `known` is {event id: (rewards, final, steps)}; none where not
    given, never the machine's own client."""
    ct.event_totals_onto(raw, NOW, known or {})
    return raw


def _asked(ct, raw, name, segments):
    """What `_mark_finished` asks of one row: (claimed, total, ticked),
    or None where it asks nothing."""
    key = ct.EVENT_KEY_PREFIX + name
    stub = SimpleNamespace(context=SimpleNamespace())
    return ct.ChecklistTab._mark_finished(
        stub, raw, {key: tuple(segments)}).get(key)


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

    # Four of the seven lists on record keep their completion record on
    # the ACHIEVEMENT page, under the instalment's own id.
    flagged = dict(raw, event_mission_reward_entities=[{
        "res_id": "event_node_30115_achievement", "reward_step": 0,
        "version": 0, ct.EVENT_DONE_FLAG: ct.EVENT_DONE_VALUE}])
    if not ct._event_finished(flagged, "event_nodelist_007"):
        out.append(
            "event_node_30115_achievement did not finish event_nodelist_007. "
            "Node Lists can keep their completion record on the "
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
            f"took them as arena_2's -- counting one instalment as 40 "
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


def _client_totals(ct):
    """The client's total is the event's, under either of its ids."""
    out = []
    live = {"start_time": NOW - 5 * DAY, "end_time": NOW + 10 * DAY}
    name = "event_schedule_probe_2"

    def event(known, claimed, held=3):
        missions = [_mission("event_probe_2_%02d" % n, claimed=n <= claimed)
                    for n in range(1, held + 1)]
        raw = _onto(ct, _raw(missions, schedules={
            "EVENT_SCHEDULE": {name: live}}), known)
        return ct._event_missions(raw, name, live, NOW), raw

    # Held under the instalment's own id while the schedule names it
    # the long way: `_event_key` makes the two one.
    got, raw = event({"event_probe_2": (6, 0, 0)}, claimed=1)
    if got != [("1/6", ct.TODO)]:
        out.append(
            f"three rows issued of an event the client holds as six read "
            f"{got!r}, not 1/6. The client states the whole event, so "
            f"there is no floor to mark and nothing still to guess.")
    if name not in raw.get(ct.EVENT_CLIENT_FIELD, {}):
        out.append(
            f"the client's `event_probe_2` did not reach {name}. The game "
            f"names some instalments both ways, and the client's tables "
            f"may hold either.")

    # Every reward the client lists claimed is the whole event: green
    # with no word from the game, which no floor could ever be.
    got, _raw_ = event({name: (3, 0, 0)}, claimed=3)
    if got != [("3/3", ct.DONE)]:
        out.append(
            f"every reward the client lists claimed reads {got!r}, not "
            f"3/3 done.")

    # Its own entry beats its family's.
    got, raw = event({"event_probe_1": (20, 0, 0), "event_probe_3": (20, 0, 0),
                      name: (6, 0, 0)}, claimed=1)
    if got != [("1/6", ct.TODO)] or raw.get(ct.EVENT_TOTALS_FIELD):
        out.append(
            f"an event the client holds as six, in a family of twenties, "
            f"reads {got!r} with family totals "
            f"{raw.get(ct.EVENT_TOTALS_FIELD)!r}. The family speaks only "
            f"for an event the client does not hold.")

    # More rows than the client lists: paired wrongly, or the event
    # grew after the client was read. The wire's own reading answers.
    got, _raw_ = event({name: (2, 0, 0)}, claimed=3)
    if got != [("3/3" + ct.UNKNOWN_MORE, ct.FLOOR)]:
        out.append(
            f"three rows against a client total of two read {got!r}, not "
            f"the floor. A total the rows in hand have outgrown is wrong "
            f"about this event, and a reading built on it would say less "
            f"is left than the account can see.")
    return out


def _one_instalment_votes_once(ct):
    """Two ids of one instalment are one vote for the family."""
    out = []
    known = {"event_schedule_arena_2": (17, 0, 0), "event_arena_2": (17, 0, 0)}
    got = ct.family_total("event_arena_3", known)
    if got is not None:
        out.append(
            f"one arena under two ids answered for the family with {got!r}. "
            f"`event_schedule_arena_2` and `event_arena_2` are the same "
            f"instalment, and one instalment is a number rather than a "
            f"pattern.")
    known["event_schedule_arena_1"] = (17, 0, 0)
    if ct.family_total("event_arena_3", known) != 17:
        out.append("two real instalments of one family did not agree on 17.")
    # The live instalment's twin must not vote for it either.
    if ct.family_total("event_arena_2", known) is not None:
        out.append(
            "a live instalment's own twin id voted on its total. The "
            "client's word on an event it holds is read directly, not as "
            "family history.")

    # A final reward wants one instalment paying one, not two.
    if not ct.family_final("event_arena_3", {"event_arena_1": (17, 1, 0)}):
        out.append(
            "one instalment paying a final reward did not mark its "
            "family. Being wrong costs a row asking Finished? over a "
            "reward that is not there; missing it costs the reward.")
    if ct.family_final("event_arena_3", {"event_arena_3": (17, 1, 0)}):
        out.append("an event counted as its own family's history.")
    return out


def _final_rewards(ct):
    """A final reward the client lists, or one its family paid."""
    out = []
    live = {"start_time": NOW - 5 * DAY, "end_time": NOW + 10 * DAY}
    name = "event_probe_2"

    def event(known, claimed, final_taken=False):
        missions = [_mission("event_probe_2_%02d" % n, claimed=n <= claimed)
                    for n in range(1, 4)]
        records = []
        if final_taken:
            records.append({"res_id": name, "reward_step": 0, "version": 0,
                            ct.EVENT_DONE_FLAG: ct.EVENT_DONE_VALUE})
        raw = _onto(ct, _raw(missions, records, {
            "EVENT_SCHEDULE": {name: live}}), known)
        return ct._event_missions(raw, name, live, NOW), raw

    held = {name: (3, 1, 0)}
    got, raw = event(held, claimed=3)
    if got != [("3/4", ct.FINAL_WAITING)]:
        out.append(
            f"every row claimed of an event the client says pays a final "
            f"reward reads {got!r}, not 3/4 waiting. The final reward is "
            f"invisible until claimed; the client is what says it is "
            f"there.")
    asked = _asked(ct, raw, name, got)
    if asked is not None:
        out.append(
            f"a final reward the client lists asked Finished? "
            f"({asked!r}). The client says it exists, so there is nothing "
            f"for the answer to settle.")
    got, _raw_ = event(held, claimed=2)
    if got != [("2/4", ct.TODO)]:
        out.append(f"a row still unclaimed beside a listed final reward "
                   f"reads {got!r}, not 2/4.")
    got, _raw_ = event(held, claimed=3, final_taken=True)
    if got != [("4/4", ct.DONE)]:
        out.append(
            f"a final reward the game has recorded as taken reads {got!r}, "
            f"not 4/4 done.")

    # **An event the client does not hold** borrows its family's: a
    # final reward known that way is a guess, and the row asks.
    family = {"event_probe_1": (3, 1, 0)}
    got, raw = event(family, claimed=3)
    want = [("3/4" + ct.UNKNOWN_MORE, ct.FINAL_WAITING)]
    if got != want:
        out.append(
            f"every row claimed, in a family whose last instalment paid a "
            f"final reward, reads {got!r}, not {want!r}. Nothing else says "
            f"this one has one waiting.")
    asked = _asked(ct, raw, name, got)
    if asked != (3, 4, False):
        out.append(
            f"a final reward known only from the family did not ask "
            f"Finished? ({asked!r}). The person who can see the game is the "
            f"one who knows whether this instalment has one.")
    got, _raw_ = event(family, claimed=2)
    if got != [("2/4" + ct.UNKNOWN_MORE, ct.FLOOR)]:
        out.append(
            f"a row still unclaimed beside a family's final reward reads "
            f"{got!r}. The final is counted in the total, and the row is "
            f"an ordinary floor until the rows are all taken.")

    # A family that never paid one reads as it always did.
    got, raw = event({"event_probe_1": (3, 0, 0)}, claimed=3)
    if got != [("3/3" + ct.UNKNOWN_MORE, ct.FLOOR)] \
            or name in raw.get(ct.EVENT_FINALS_FIELD, ()):
        out.append(
            f"an event whose family paid no final reward reads {got!r}. "
            f"Nothing says it has one.")
    return out


def _step_tracks(ct):
    """A step track is read off its record, never its one mission row."""
    out = []
    live = {"start_time": NOW - 5 * DAY, "end_time": NOW + 10 * DAY}
    name = "event_schedule_love_9"

    def event(known, step=None, flag=0):
        records = []
        if step is not None:
            records.append({"res_id": "event_season_love_9",
                            "reward_step": step, "version": 3,
                            ct.EVENT_DONE_FLAG: flag})
        raw = _onto(ct, _raw([_mission("event_love_09_01")], records, {
            "EVENT_SCHEDULE": {name: live}}), known)
        return ct._event_missions(raw, name, live, NOW)

    # The client states the ladder's size.
    ladder = {name: (21, 0, 1)}
    for step, flag, want, why in (
            (None, 0, ("0/21", ct.TODO),
             "a track with no claim yet, and so no record"),
            (7, 0, ("7/21", ct.TODO), "a track seven steps in"),
            # **At the top of its ladder it stays a floor.** Read as the
            # steps claimed, a full `reward_step` means finished; read as
            # the track's size, every track sits there from its first
            # claim. Only the game's flag tells them apart.
            (21, 0, ("21/21", ct.FLOOR),
             "a track at the top of its ladder with no flag"),
            (21, ct.EVENT_DONE_VALUE, ("21/21", ct.DONE),
             "a flagged track")):
        got = event(ladder, step, flag)
        if got != [want]:
            out.append(f"{why} reads {got!r}, not {[want]!r}. See "
                       f"`_client_steps`.")
    got = event({name: (21, 1, 1)}, 21)
    if got != [("21/22", ct.FINAL_WAITING)]:
        out.append(f"a track at its top with a final reward to come reads "
                   f"{got!r}, not 21/22 waiting.")

    # One the client does not hold reads off its record alone.
    got = event({}, 7)
    if got != [("7/7" + ct.UNKNOWN_MORE, ct.FLOOR)]:
        out.append(
            f"a step track seven steps in reads {got!r}. Its one mission "
            f"row accumulates a score and is never itself claimed, so read "
            f"as a mission the event is 0/1+? for its whole run; the steps "
            f"are on the record.")
    got = event({}, 7, ct.EVENT_DONE_VALUE)
    if got != [("7/7", ct.DONE)]:
        out.append(f"a flagged step track reads {got!r}, not 7/7 done.")
    got = event({"event_schedule_love_1": (21, 0, 1),
                 "event_schedule_love_2": (21, 0, 1)}, 7)
    if got != [(ct.EXPECTED_VALUE + "7/21", ct.TODO)]:
        out.append(
            f"a step track whose family the client holds at 21 twice reads "
            f"{got!r}, not ~7/21.")

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
    for probe in (_node_lists, _earlier_instalments, _client_totals,
                  _one_instalment_votes_once, _final_rewards, _step_tracks):
        failures.extend(probe(ct))
    return failures
