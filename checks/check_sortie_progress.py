"""A Sortie rung is done when it is STAMPED, not when it is sent.

The wire issues an achievement row while the rung is still in
progress, so counting rows overstates a combatant by up to three --
which is the shape of a bug nobody notices, because it is right for
anyone who has finished everything they have started. Title rows
happen to arrive only once earned, so the two readings agree there;
the single rule is what keeps the count right if that ever changes.

The other two candidate fields are decoys. `score` is 1, 2 or 3 on
achievement rows without tracking completion, and `acquired_count`
reaches 3 on title rows that count once each.

The totals cannot come off the wire: both ladders are sparse, so an
unearned rung sends nothing and the longest ladder an account has
touched is a floor, never the length. They are the game's numbers, and
the guard is what says the game has moved.
"""

import glob
import json
import os

from ._harness import SOURCE_ROOT, add_source_to_path, note

NAME = "Sortie progress counts stamped rungs"

add_source_to_path()

import sortie_progress as sp                                   # noqa: E402

STAMP = 1785952172          # any non-zero epoch; the value is not read


def _ladder(char, achievements=(), titles=(), **fields):
    ach = {"assault_char_achieve_%d_%d" % (char, n):
           dict({"res_id": "assault_char_achieve_%d_%d" % (char, n)}, **fields)
           for n in achievements}
    tit = {"assault_char_title_%d_%d" % (char, n):
           dict({"res_id": "assault_char_title_%d_%d" % (char, n)}, **fields)
           for n in titles}
    return {sp.ACHIEVEMENT_FIELD: ach, sp.TITLE_FIELD: tit}


def _completion_is_the_stamp():
    out = []
    # The real shape: Magna after one run -- one stamped achievement,
    # two stamped titles, and the game showing 1/4 and 2/12.
    got = sp.progress(_ladder(1010, achievements=(4,), titles=(9, 10),
                              score=1, complete_time=STAMP))
    if got.get(1010) != (3, sp.TOTAL):
        out.append(
            f"one achievement and two titles, all stamped, read "
            f"{got.get(1010)!r} rather than (3, {sp.TOTAL}).")

    # Khalipe's real shape: four achievement rows, one of them
    # finished. The game says 1/4, so three issued rows must not count.
    raw = _ladder(1008, achievements=(1, 2, 3), score=1, complete_time=0)
    raw[sp.ACHIEVEMENT_FIELD].update(
        _ladder(1008, achievements=(4,), score=1,
                complete_time=STAMP)[sp.ACHIEVEMENT_FIELD])
    got = sp.progress(raw)
    if got.get(1008) != (1, sp.TOTAL):
        out.append(
            f"four achievement rows with one stamped read {got.get(1008)!r} "
            f"rather than (1, {sp.TOTAL}). A row is ISSUED while its rung "
            f"is still in progress; `complete_time` is what finishes it.")

    # Same rule on the other ladder, so an unstamped title row cannot
    # start counting the day the game begins sending one.
    open_titles = sp.progress(_ladder(1052, titles=(4, 6, 7), complete_time=0))
    if open_titles.get(1052) != (0, sp.TOTAL):
        out.append(
            f"three unstamped title rows read {open_titles.get(1052)!r} "
            f"rather than (0, {sp.TOTAL}). Both ladders take the same rule.")
    return out


def _neither_score_nor_acquired_count_is_completion():
    out = []
    # One combatant's finished rung scores 3 and another's scores 1, so
    # a reading that weighed `score` would disagree with the game on
    # some combatants and not others.
    loud = sp.progress(_ladder(1052, achievements=(1,), score=3,
                               complete_time=STAMP))
    quiet = sp.progress(_ladder(1008, achievements=(4,), score=1,
                                complete_time=STAMP))
    if loud.get(1052) != quiet.get(1008):
        out.append(
            "two combatants with one finished achievement each read "
            "differently because their `score` differs. `score` is not "
            "completion.")

    # `acquired_count` reaches 3 on a title rung that is still one rung.
    many = sp.progress(_ladder(30084, titles=(9,), acquired_count=3,
                               complete_time=STAMP))
    if many.get(30084) != (1, sp.TOTAL):
        out.append(
            f"a title row with acquired_count 3 read {many.get(30084)!r} "
            f"rather than (1, {sp.TOTAL}). It is not a rung multiplier.")
    return out


def _a_combatant_who_has_finished_nothing_still_reads():
    """0/16 is a reading; dropping out of the map is not.

    The game shows a combatant with rungs in progress as 0/4, and a
    column that simply leaves the cell empty reads as "no data".
    """
    got = sp.progress(_ladder(30047, achievements=(1, 2, 3), complete_time=0))
    if got.get(30047) != (0, sp.TOTAL):
        return [f"a combatant with three unfinished rungs read "
                f"{got.get(30047)!r} rather than (0, {sp.TOTAL})."]
    return []


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


def _captured_ladders():
    """The newest snapshot that carries both ladders, or None.

    Snapshots taken before the capture read these keys have them empty,
    and there is no telling those from an account with no Sortie
    progress -- so the newest one HOLDING rows is the only useful one.
    """
    for path in sorted(glob.glob(str(SOURCE_ROOT / "snapshots" / "*.json")),
                       key=os.path.getmtime, reverse=True):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        rows = {key: data.get(key)
                for key in (sp.ACHIEVEMENT_FIELD, sp.TITLE_FIELD)}
        if any(rows.values()):
            return os.path.basename(path), rows
    return None


def _the_real_ladders_still_need_the_stamp():
    """Against captured data: does the distinction still bite?

    If every row the game sends is finished, counting rows and counting
    stamps agree and this check's whole subject is unobservable. That
    is worth SAYING rather than passing quietly, because it would make
    a regression to row-counting invisible here.
    """
    found = _captured_ladders()
    if not found:
        note("no snapshot carries the Sortie ladders yet, so the reading "
             "was exercised only against constructed rows")
        return []
    name, rows = found

    def count(key, stamped_only):
        # Unpacked here rather than through the module's own helper, so
        # a bug in that helper cannot hide behind itself.
        held = rows.get(key)
        held = (list(held.values()) if isinstance(held, dict)
                else held if isinstance(held, list) else [])
        return sum(1 if not stamped_only else bool(row.get("complete_time"))
                   for row in held
                   if isinstance(row, dict) and row.get("res_id"))

    out = []
    for key, label in ((sp.ACHIEVEMENT_FIELD, "achievement"),
                       (sp.TITLE_FIELD, "title")):
        sent, stamped = count(key, False), count(key, True)
        if not sent:
            note(f"{name} carries no {label} rows")
        elif sent == stamped and label == "achievement":
            note(f"every {label} row in {name} is stamped, so row-counting "
                 f"and stamp-counting cannot be told apart there")
        if stamped > sent:
            out.append(
                f"{name}: {stamped} stamped {label} rows out of {sent} sent. "
                f"Counting is broken.")

    # A rung past the end of a ladder is a game change, and it has to
    # land here rather than only in the launcher's console -- by the
    # time anyone reads that, the column has been wrong for a session.
    # Checking the combined figure would not see it: one ladder can
    # overrun while the pair still sits under the total.
    lengthened = []
    reading = sp.progress(rows, warn=lengthened.append)
    out.extend(f"{name}: {said}" for said in lengthened)

    over = {c: got for c, got in reading.items() if got[0] > sp.TOTAL}
    if over:
        out.append(
            f"{name} reads above {sp.TOTAL} for {sorted(over)}, which the "
            f"game's ladders cannot produce.")
    return out


def run():
    problems = []
    for probe in (_completion_is_the_stamp,
                  _neither_score_nor_acquired_count_is_completion,
                  _a_combatant_who_has_finished_nothing_still_reads,
                  _an_empty_snapshot_says_nothing,
                  _a_longer_ladder_announces_itself,
                  _the_real_ladders_still_need_the_stamp):
        problems.extend(probe())
    return problems
