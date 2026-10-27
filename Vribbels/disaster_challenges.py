"""What is left on the live Galactic Disaster season's challenge pages.

The game's Challenge Mission screen has five pages. Weekly Progress is
the Checklist's; the other four are read here: Mission Records, Chaos
Investigation, Battle Report and Annihilation Reward. `board` turns a
snapshot into what the Galactic Disaster tab draws -- per page, the
requirements still to meet, a count done against the page's total,
whether a reward waits to be claimed, and how many achievements are
still locked, by when each opens.

**The game client lists every achievement; the wire only those begun.**
`game_client.disaster_challenges` gives each one's page, its words, the
target its score counts to, what unlocks it and, for one achievement
that rewards others, which. The wire's `disaster_achievement_entities`
has a row for an achievement once it has progress: a `score`, and a
`complete_time` once its reward is CLAIMED. A row the wire has not sent
is an achievement not started. `docs/disaster_challenges.md` has the
rest.

**Done is the condition met, claimed or not**: a claim, or a score at
its target. An achievement for finishing others carries no score of its
own -- its row is issued only when it is claimed -- so it is done once
every one it names is. Done and unclaimed is a reward waiting, which
the page's count says in orange.

No Tk and no managers: this takes the snapshot dict and returns data.
"""

from collections import namedtuple

import schedules

# The pages, in the game's order, which is also the order the finished
# ones stack in at the tab's right. Their titles are the client's
# (`game_client.disaster_challenges`'s `pages`); these stand where the
# client names none.
PAGES = ("disaster_collection", "disaster_ingame", "disaster_battle",
         "penalty")
PAGE_TITLES = {"disaster_collection": "Mission Records",
               "disaster_ingame": "Chaos Investigation",
               "disaster_battle": "Battle Report",
               "penalty": "Annihilation Reward"}

# The snapshot's fields. The first three are the wire's own names; the
# last is the capture's, every codex entry a Chaos run has found since
# the last full codex (`docs/disaster_challenges.md`, *The lists*).
ACHIEVEMENTS_FIELD = "disaster_achievement_entities"
CODEX_FIELD = "chaos_archive_entities"
COLLECTIONS_FIELD = "disaster_collection_entities"
RUN_FINDS_FIELD = "chaos_run_finds"

SEASON_GROUP = "DISASTER_SEASON"
# A Supply round's page opens this many days into the season's
# schedule, and with it the season's part (`disaster_constant_meta`).
PART_STARTS = "unlock_disaster_shop_%d"
DAY = 24 * 3600

# What a locked achievement's line says, summed by when it opens. A part
# for one opening with a Supply round; a countdown for one opening
# inside a part, a Nebula Distortion boss's; nothing for one whose
# opening the client does not date.
LOCKED_PART = "%d Part %d achievement%s"
LOCKED_SOON = "%d achievement%s (in %s)"
LOCKED_UNDATED = "%d locked achievement%s"

# A list achievement's tip: its items still to find, a monster with the
# kills it still wants, and how many open only with a later part.
TIP_COUNT = "%s (%d/%d)"
TIP_LATER = "+%d more in a later part"
TIP_UNREAD = "No capture holds this list yet."

# What the tab says instead of pages.
NO_SEASON = "No Galactic Disaster season is running."
NO_CLIENT = "The game client's challenge pages for %s are not known."
NO_CAPTURE = ("No capture holds this season's challenge pages yet: log in "
              "with the capture running.")

# `rows`: the requirements still to meet, in the game's order;
# `locked`: one line per opening, soonest first. `done` counts against
# `total`, which takes in the achievements for finishing others and the
# locked ones, and not the Annihilation Reward's unnamed ones.
# `unclaimed`: a reward on the page waits to be claimed, unnamed ones'
# included.
Page = namedtuple("Page", "page title done total unclaimed rows locked")
# `tip`: a list achievement's items still to find, one line each, or
# None.
Row = namedtuple("Row", "id text tip")
Board = namedtuple("Board", "season pages note")


def finished(page):
    """Whether nothing on `page` is left to do: what moves its heading
    to the column of finished pages."""
    return page.done >= page.total


def board(raw, now, challenges=None, constants=None):
    """The tab's reading of `raw` at `now`: a `Board`, its `pages` in
    the game's order, or none and a `note` saying why.

    `challenges` is `game_client.known_disaster_challenges()` and
    `constants` the Galactic Disaster's `disaster_constants` limits,
    both read off the client where not given."""
    if challenges is None or constants is None:
        import game_client
        if challenges is None:
            challenges = game_client.known_disaster_challenges()
        if constants is None:
            constants = game_client.known_limits().get(
                "disaster_constants") or {}
    season, window = schedules.live(SEASON_GROUP, raw, now)
    if season is None:
        return Board(None, (), NO_SEASON)
    held = (challenges or {}).get(season)
    if not isinstance(held, dict):
        return Board(season, (), NO_CLIENT % season)
    table = (raw or {}).get(ACHIEVEMENTS_FIELD)
    if not isinstance(table, dict):
        return Board(season, (), NO_CAPTURE)
    wire = table.get(season)
    wire = wire if isinstance(wire, dict) else {}
    start = window.get("start_time")
    reading = _Reading(held, wire, start, now)
    lists = _held_lists(raw)
    pages = []
    for page in PAGES:
        listed = [a for a in held.get("achievements") or ()
                  if a.get("page") == page]
        counted = [a for a in listed if a.get("kind") != "generic"]
        if not counted:
            continue
        rows = tuple(
            Row(a["id"], a.get("text") or a["id"],
                _tip(held, a, lists, reading))
            for a in counted
            if a.get("kind") == "named" and not reading.done(a)
            and reading.open(a))
        pages.append(Page(
            page, (held.get("pages") or {}).get(page) or PAGE_TITLES[page],
            sum(1 for a in counted if reading.done(a)), len(counted),
            any(reading.done(a) and not reading.claimed(a)
                for a in listed),
            rows,
            _locked_lines([a for a in counted if not reading.done(a)
                           and not reading.open(a)],
                          held.get("gates") or {}, constants, start, now)))
    return Board(season, tuple(pages), None)


class _Reading:
    """One season's achievements against the wire's rows."""

    def __init__(self, held, wire, start, now):
        self.by_id = {a["id"]: a for a in held.get("achievements") or ()
                      if isinstance(a, dict) and a.get("id")}
        self.gates = held.get("gates") or {}
        self.wire, self.start, self.now = wire, start, now
        self._done = {}

    def row(self, achievement):
        row = self.wire.get(achievement["id"])
        return row if isinstance(row, dict) else None

    def claimed(self, achievement):
        row = self.row(achievement)
        return bool(row and _count(row.get("complete_time")))

    def done(self, achievement, seen=()):
        """Claimed, or its score at its target; for one rewarding
        others, every one of those done. `seen` stops a loop the client
        should never hold."""
        key = achievement["id"]
        if key in self._done:
            return self._done[key]
        row = self.row(achievement)
        answer = self.claimed(achievement) or bool(
            row and _count(row.get("score"))
            and row["score"] >= (achievement.get("count") or 1))
        children = achievement.get("children") or ()
        if not answer and achievement.get("kind") == "meta" and children \
                and key not in seen:
            answer = all(child in self.by_id and self.done(
                self.by_id[child], seen + (key,)) for child in children)
        self._done[key] = answer
        return answer

    def open(self, achievement):
        """Whether an achievement can be worked on: no gate, a row on
        the wire, or its gate's day reached."""
        return self.gate_open(achievement.get("gate")) \
            or self.row(achievement) is not None

    def gate_open(self, gate):
        if not gate:
            return True
        day = self.gates.get(gate)
        return (isinstance(day, int) and _count(self.start)
                and self.now >= self.start + day * DAY)


def _locked_lines(locked, gates, constants, start, now):
    """One line per opening of the achievements still `locked`, soonest
    first; the undated last."""
    parts = {constants.get(PART_STARTS % n): n for n in range(1, 10)
             if isinstance(constants.get(PART_STARTS % n), int)}
    by_day = {}
    for achievement in locked:
        day = gates.get(achievement.get("gate"))
        by_day.setdefault(day if isinstance(day, int) else None, []).append(
            achievement)
    out = []
    for day in sorted(by_day, key=lambda d: (d is None, d or 0)):
        count = len(by_day[day])
        plural = "" if count == 1 else "s"
        if day is None or not _count(start):
            out.append(LOCKED_UNDATED % (count, plural))
        elif day in parts:
            out.append(LOCKED_PART % (count, parts[day], plural))
        else:
            out.append(LOCKED_SOON % (count, plural,
                                      _in(start + day * DAY - now)))
    return tuple(out)


def _in(seconds):
    """`8d`, `5h`, `40m`: how long until an opening, rounded down as
    every countdown on the Checklist is."""
    for size, unit in ((DAY, "d"), (3600, "h"), (60, "m")):
        if seconds >= size or unit == "m":
            return "%d%s" % (max(1, int(seconds // size)), unit)


def _held_lists(raw):
    """{collection id: {item id: count}}: every codex page and season
    collection the snapshot holds, a Chaos run's finds since the last
    full codex laid over them. None where the snapshot holds neither."""
    raw = raw or {}
    codex, collections = raw.get(CODEX_FIELD), raw.get(COLLECTIONS_FIELD)
    if not isinstance(codex, dict) and not isinstance(collections, list):
        return None
    out = {}
    for key, row in (codex.items() if isinstance(codex, dict) else ()):
        if isinstance(row, dict) and isinstance(row.get("collection"), dict):
            out[str(key)] = dict(row["collection"])
    for row in collections if isinstance(collections, list) else ():
        if isinstance(row, dict) and isinstance(row.get("collection"), dict):
            out[str(row.get("res_id"))] = dict(row["collection"])
    finds = raw.get(RUN_FINDS_FIELD)
    out[RUN_FINDS_FIELD] = finds if isinstance(finds, dict) else {}
    return out


def _tip(held, achievement, lists, reading):
    """A list achievement's tip lines, or None for one collecting no
    list. A run's finds count as found: a codex entry is never lost."""
    listed = (held.get("lists") or {}).get(achievement.get("list") or "")
    if not isinstance(listed, dict):
        return None
    if lists is None:
        return (TIP_UNREAD,)
    have = lists.get(listed.get("collection")) or {}
    finds = lists.get(RUN_FINDS_FIELD) or {}
    lines, later = [], 0
    for item in listed.get("items") or ():
        item_id, name, most, gate = (list(item) + [None] * 4)[:4]
        count = max(_number(have.get(item_id)), _number(finds.get(item_id)))
        most = most if _count(most) else 1
        if count >= most:
            continue
        if not reading.gate_open(gate):
            later += 1
            continue
        name = name or item_id
        lines.append(TIP_COUNT % (name, count, most) if most > 1 else name)
    if later:
        lines.append(TIP_LATER % later)
    return tuple(lines) or None


def _count(value):
    """True for a whole number above zero."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and value > 0


def _number(value):
    return value if _count(value) else 0
