"""A combatant's Sortie progress counts rungs, not fields.

The two ladders are SPARSE -- the wire sends nothing for a rung that
has not been reached -- so the count of rows IS the count completed.
Every field that looks like it might say so does not:

* `score` is 1, 2 or 3 depending on the combatant, on rows that are
  all equally done;
* `complete_time` is 0 on rungs whose reward has been collected, so it
  is not the claim marker it resembles.

Reading either as a flag gives a figure that disagrees with the game
on some combatants and not others -- which is the shape of a bug
nobody notices for months.

The totals cannot come off the wire for the same reason the count can:
an unearned rung sends nothing, so the longest ladder an account has
touched is a floor, never the length. They are the game's numbers, and
the guard is what says the game has moved.
"""

from ._harness import add_source_to_path

NAME = "Sortie progress counts rungs"

add_source_to_path()

import sortie_progress as sp                                   # noqa: E402


def _ladder(char, achievements=(), titles=(), **fields):
    ach = {"assault_char_achieve_%d_%d" % (char, n):
           dict({"res_id": "assault_char_achieve_%d_%d" % (char, n)}, **fields)
           for n in achievements}
    tit = {"assault_char_title_%d_%d" % (char, n):
           dict({"res_id": "assault_char_title_%d_%d" % (char, n)}, **fields)
           for n in titles}
    return {sp.ACHIEVEMENT_FIELD: ach, sp.TITLE_FIELD: tit}


def _counts_rows_not_fields():
    out = []
    # The real shape: Magna after one run -- one achievement, two
    # titles, and the game showing 1/4 and 2/12.
    raw = _ladder(1010, achievements=(4,), titles=(9, 10),
                  score=1, complete_time=0)
    got = sp.progress(raw)
    if got.get(1010) != (3, sp.TOTAL):
        out.append(
            f"one achievement and two titles read {got.get(1010)!r}, not "
            f"(3, {sp.TOTAL}). A rung is done when its row exists.")

    # `score` differs between combatants on rows that are all done, so
    # a reading that weighed it would disagree with the game on some.
    loud = _ladder(1052, achievements=(1, 2, 3), score=3)
    quiet = _ladder(1008, achievements=(1, 2, 3), score=1)
    if sp.progress(loud).get(1052) != sp.progress(quiet).get(1008):
        out.append(
            "two combatants with three achievements each read differently "
            "because their `score` differs. `score` is not completion.")

    # `complete_time` is 0 on rungs already collected, so it cannot
    # subtract from the count either.
    zero = _ladder(1008, achievements=(1, 2, 3), complete_time=0)
    stamped = _ladder(1008, achievements=(1, 2, 3), complete_time=123456)
    if sp.progress(zero) != sp.progress(stamped):
        out.append(
            "`complete_time` changed the count. It is 0 on rungs whose "
            "reward has been collected, so it says nothing about either "
            "completion or claiming.")
    return out


def _an_empty_snapshot_says_nothing():
    for raw in ({}, None, {sp.ACHIEVEMENT_FIELD: None, sp.TITLE_FIELD: None},
                {sp.ACHIEVEMENT_FIELD: [], sp.TITLE_FIELD: {}}):
        if sp.progress(raw):
            return [f"{raw!r} produced a reading. A snapshot taken before "
                    f"the ladders were captured has nothing to say."]
    return []


def _a_longer_ladder_announces_itself():
    """The one sign the game has changed shape, and it must be loud."""
    out = []
    said = []
    sp.progress(_ladder(1010, achievements=(1, 2, 3, 4)), warn=said.append)
    if said:
        out.append(f"a full, legal ladder warned anyway: {said!r}")

    said = []
    sp.progress(_ladder(1010, achievements=(1, 2, 3, 4, 5)),
                warn=said.append)
    if not said:
        out.append(
            "a rung past the end of the ladder passed in silence. It is "
            "the only sign the game has lengthened one, and without it "
            "the column reads above its own total with no explanation.")
    else:
        text = said[0]
        for wanted in ("1010", "5", "achievement"):
            if wanted not in text:
                out.append(
                    f"the warning does not say {wanted!r}: {text!r}. It has "
                    f"to name the combatant, the rung and the ladder, or it "
                    f"cannot be acted on.")
    return out


def run():
    problems = []
    for probe in (_counts_rows_not_fields, _an_empty_snapshot_says_nothing,
                  _a_longer_ladder_announces_itself):
        problems.extend(probe())
    return problems
