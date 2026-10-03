"""Write `docs/chaos_runs.tsv`: one Chaos run per row, and report what
pays in a run and whether it has moved.

    python docs/chaos_runs.py          # the runs' file, snapshots, and logs since the newest row
    python docs/chaos_runs.py --all    # the same, and every log, loose and archived

`docs/chaos_runs.cmd` runs the first from Explorer.

**A run comes from three places, and is one row.** The capture files
every Chaos run into a file of its own (`Vribbels/chaos_store.py`);
snapshots from before that file carry theirs as `chaos_runs`; and a
debug log replays through the same capture code to the same records --
see `Addon._note_chaos` in `Vribbels/capture/manager.py`. A run is
keyed by the second it cleared, which all three give alike, so a run
several hold is one row, whose `log` names the debug log.

**Only the live season's own Chaos is averaged.** A past season's
Chaos -- entered through the Zero System -- pays the live season's
currency too, but less, so the means, the report and the shipped
figures read the season's own Chaos alone, and every other Chaos gets
its own lines after them.

Re-run it after any capture that holds a run. **By default it reads
every loose snapshot, and only the logs from the one that holds the
newest log-read row onward** -- that log is read again, since a run may
have been added to it after the last pass -- and keeps every older row
as the file has it. The archive is opened only when that log is no
longer loose. `--all` rebuilds every row, which is what a change to how
a run is read needs.

**Columns to the RIGHT of `log` are yours and are kept**, matched to
the run by its `date`: what happened in a run that the wire cannot say,
such as a boss lost to.

**`missed` is the one of yours this script reads**, and is always
there to fill in: what a run would have paid but for a mistake -- a
floor lost to a boss, a reward left behind. The means, minimums and
maximums it prints count `total + missed`, since they stand for what a
run pays played through; `total` stays what was paid. Say in `notes`
what was missed.

**A lost run that still counts as whole fills its own `missed`** where
the cell is empty: the lost fight's payout and every boss after it, as
the latest cleared run of that season part paid them --
`chaos_estimate.missed`, which also says when a lost run counts. A
cell you filled is kept, and flagged where the two disagree.

The columns this script owns:

| column    | what it says                                                  |
| --------- | --------------------------------------------------------------- |
| `date`    | when the run was cleared, UTC                                   |
| `season`  | the Galactic Disaster season it ran in                          |
| `part`    | which part of the season: the shop page open when it cleared   |
| `chaos`   | which Chaos it was, by the stage id its clear names -- `chaos_estimate.CHAOS_NAMES` |
| `door`    | how it was entered: `Galactic Disaster`, `Zero System` or `own screen` (a base-game Chaos's) |
| `difficulty` | the number ending the list id it was entered with (`6`), or a Zero System map's level (`lv80`) |
| `special` | a Zero System map's special options, by `chaos_estimate.ZERO_SPECIALS` where named |
| `options` | a Zero System map's bonus and penalty options: `b001 p112` |
| `mode`    | `delegated`, played by the Delegation Module down one path, or `ordinary` |
| `client`  | the game client and data patch it ran on: `cznlive 1.464 r688`  |
| `total`   | what the run paid in the season's currency                      |
| `payouts` | every payout in order, `floor:spot:amount`, `+mark` for a mark  |
| `marked`  | the fights carrying a mark, paid or not: `k5:2 e:1`             |
| `marked_at` | the same by the spot each was met on: `battle.k5:1 elite.k5:1` |
| `fought`  | the fights, by spot: `battle:11 elite:4 boss:3`; `unknown` is a fight a `?` encounter offered, `break_in` a hidden mini-boss |
| `lost`    | where a lost run was lost: `floor:spot:non-boss fights left`, `+mark` for a mark |
| `SPOT_*`  | the payouts at each kind of spot, `+` between them              |
| `log`     | the capture it was read from                                    |

**What pays is the fight, and the wire names what makes one pay.** A
boss pays a set amount for its floor. Any other fight pays only where
it carries a mark -- the Rare Species, `keyword_tag` 5 (`k5`), or the
Aether Eater, a battle id ending `_e` (`e`) -- and each mark pays a set
amount. So a run's take is set but for how many marked fights it
meets. A hidden mini-boss is a break-in (`b1` is Senectus), paying
nothing of itself; one that breaks in on a Rare Species carries its
keyword, `b1+k5`, and pays as one. A mark the report has never seen is
flagged.

**The report after the table** flags every set amount that changed
from one run to the next, with what else changed there -- the season
part, the game version -- and then answers four questions per part and
per version: have the set amounts moved, and have the marks' rates?
Until a part and a version have changed apart, it says it cannot tell.

**A mark's rate is also tested for a shift in time**, taking a change
to be sudden and lasting, as a balance patch is: across the whole runs
in order, the split into a before and an after that fits best, kept
only if shuffling the runs rarely fits as well (`shifts`). A run inside
one of `chaos_estimate.RATE_EVENTS` -- something that raised the rates
for a while -- is left out. Last, the figures `chaos_estimate.SHIPPED`
wants, for the release step to copy.

**A rate a run is not a rate a fight, and a map's own mix of fights can
move the first alone.** Season 5's Chaos -- and any Chaos given its
special option in the Zero System -- makes every floor after the first
boss an Elite or an Unidentified Area floor. Elite floors turn up as
often as before, so a run holds fewer ordinary battles and meets fewer
marks, with no mark's rate a fight moving. Read across that change, the
per-run figures and `shipped_figures` fall, and the shift test, which
takes battle and Elite fights together, can report a shift for a mark
met more on one kind than the other: the Aether Eater has only been met
on battles. That is the map, not the rates. The by-spot lines after the
shift test read each kind of fight apart, and `special` says which runs
had the option. Expect it at the end of season 5, against season 4's
runs, and again at the end of season 6, against season 5's.

**The season's skill tree moves rates as it is levelled.** Every run
records the Zero System effects in force (`Addon._chaos_setup`), and
among them are the season's own `ZERO_ENCOUNTER_RATEUP__*` and
`ZERO_BREAK_IN_RATEUP__*` nodes. A shift that lines up with one taken
is the tree's.

**A season is named by the run, not by its currency.** Each season pays
in an item id of its own, and the capture names the season a run
cleared in from the Great Rift standings; the currency is then whatever
that run was paid most of. `CURRENCY` places only a run no standings
had been read before. A season's parts are dated the way the Checklist
dates its shop pages, for the season live in the newest snapshot; a
row keeps the part it was given once the season is over.

Nothing here writes to `snapshots/`; the archive is read in place.
"""
import collections
import datetime
import glob
import gzip
import importlib.util
import io
import json
import math
import os
import random
import re
import shutil
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Vribbels"
sys.path.insert(0, str(SOURCE))
os.chdir(SOURCE)

OUT = ROOT / "docs" / "chaos_runs.tsv"

# The season currencies seen so far. Only a run no standings named a
# season for is placed by this; see the module docstring.
CURRENCY = {3920001: "s01", 3920002: "s02", 3920006: "s03", 3920031: "s04"}

# What this script fills in. Anything after them in an existing file
# is the maintainer's and is carried over by `date`.
OWNED = ["date", "season", "part", "chaos", "door", "difficulty",
         "special", "options", "mode", "client", "total", "payouts",
         "marked", "marked_at", "fought", "lost"]
# The maintainer's column the summary reads: see the module docstring.
MISSED = "missed"
SPOT_COLUMN = "SPOT_TYPE_"

# The marks by the game's names; one missing here is new, and flagged.
MARKS = {"k5": "Rare Species", "e": "Aether Eater", "b1": "Senectus"}

# A rate comparison with fewer fights than this on either side says
# nothing, and one whose difference is under this many standard errors
# is chance.
FEWEST_FIGHTS = 30
Z_DIFFERS = 2.0

# A shift in a mark's rate needs this many whole runs on each side of
# it, and holds when fewer than this share of shuffled orders split as
# well. The shuffles are seeded, so a run of the script is repeatable.
FEWEST_RUNS = 5
SHIFT_ALPHA = 0.01
SHIFT_TRIALS = 999

from capture.manager import CaptureManager                    # noqa: E402
import chaos_estimate                                          # noqa: E402
import chaos_store                                             # noqa: E402

# Each Chaos's season, by name, for telling the live season's own
# Chaos from a past one: `current`.
CHAOS_SEASONS = {name: season for name, season
                 in chaos_estimate.CHAOS_NAMES.values()}


class _Flow:
    """The one thing `websocket_message` reads: the last message."""

    def __init__(self, payload, from_client):
        text = json.dumps(payload)

        class _Msg:
            content = text.encode("utf-8")
            is_text = True
        msg = _Msg()
        msg.text = text
        msg.from_client = from_client

        class _WS:
            messages = [msg]
        self.websocket = _WS()


def stamp(name):
    """A log's `YYYYMMDD_HHMMSS`, which sorts as its start time does."""
    found = re.search(r"websocket_debug_(\d{8}_\d{6})", name or "")
    return found.group(1) if found else ""


def logs(since=""):
    """(name, lines) for every debug log started at `since` or later.

    Loose logs first, then the archive -- and the archive only when
    `since` is older than every loose log. Compaction archives the
    oldest logs and leaves the newest loose, so when `since` is loose
    nothing archived can be as new, and walking the archive (a solid
    stream, decompressed end to end) would find nothing to read.
    """
    loose = sorted(glob.glob("snapshots/websocket_debug_*.jsonl.gz"))
    for path in loose:
        if stamp(path) >= since:
            with gzip.open(path, "rt", encoding="utf-8",
                           errors="replace") as fh:
                yield os.path.basename(path), list(fh)
    archive = "snapshots/archived_captures.tar.xz"
    if not os.path.exists(archive):
        return
    if since and loose and since >= stamp(loose[0]):
        return
    print("   opening the archive...", flush=True)
    with tarfile.open(archive) as tf:
        for member in tf:
            if ("websocket_debug" not in member.name
                    or stamp(member.name) < since):
                continue
            handle = tf.extractfile(member)
            if handle is None:
                continue
            raw = handle.read()
            if member.name.endswith(".gz"):
                raw = gzip.decompress(raw)
            yield os.path.basename(member.name), io.StringIO(
                raw.decode("utf-8", "replace")).readlines()


def fresh_addon(work):
    """The real generated addon, built the way a capture builds it."""
    manager = CaptureManager(work, log_callback=lambda *a, **k: None)
    script = manager._generate_addon_script(debug_mode=False)
    spec = importlib.util.spec_from_file_location("_chaos_addon", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return type(module.addons[0])(
        work, dict_path=module.DICT_PATH, log_callback=lambda *a, **k: None,
        debug_mode=False, catalogue_path=work / "cat.json")


def runs_in(lines, addon):
    """Every whole run one log holds, as the capture records them."""
    for line in lines:
        if not line.strip():
            continue
        try:
            frame = json.loads(line)
        except ValueError:
            continue
        try:
            addon.websocket_message(_Flow(
                frame.get("data"),
                frame.get("direction") == "client_to_server"))
        except Exception:                                     # noqa: BLE001
            pass
    return list(addon.chaos_runs)


def snapshots():
    """(runs, newest snapshot): (source, run) for every run the runs'
    own file and the loose snapshots hold, and the newest snapshot's
    contents."""
    stored, note = chaos_store.read("snapshots")
    if note:
        print("   ! the runs' file: %s" % note)
    runs = [(chaos_store.FILE, run) for run in stored if run.get("closed")]
    newest = None
    for path in sorted(glob.glob("snapshots/memory_fragments_*.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        newest = data
        for run in data.get("chaos_runs") or ():
            if isinstance(run, dict) and run.get("closed"):
                runs.append((os.path.basename(path), run))
    return runs, newest


def season_parts(raw):
    """{season: [when each part opened, first to last]} for the season
    live in `raw`, dated the way the Checklist dates its shop pages; {}
    where nothing dates it."""
    if not raw:
        return {}
    try:
        import schedules
        import shop_stock
        from ui.tabs import checklist_tab
        group = shop_stock.season_group_of(
            checklist_tab.SEASONAL_SHOP_CATEGORY)
        name, season = schedules.live(group, raw, time.time())
        starts = checklist_tab._page_openings(raw, name, season)
    except Exception:                                         # noqa: BLE001
        return {}
    return {name: list(starts)} if name and starts else {}


def short(season):
    """`disaster_s04` as `s04`; None stays None."""
    return str(season).rsplit("_", 1)[-1] if season else None


def part_of(when, season, parts):
    """Which part of `season` a run clearing at `when` fell in, or `?`."""
    starts = parts.get(season)
    if not starts:
        return "?"
    opened = sum(1 for start in starts if start <= when)
    return "part %d" % opened if opened else "preseason"


def currency_of(run):
    """The item a run was paid most of, which is its season's currency."""
    paid = collections.Counter()
    for _floor, _spot, _mark, item, amount in run.get("paid") or ():
        paid[item] += amount
    return paid.most_common(1)[0][0] if paid else None


def token(floor, spot, mark, amount):
    """One payout as the `payouts` column writes it."""
    return "%s:%s:%s%s" % (floor, str(spot).lower(), amount,
                           "+" + mark if mark else "")


def payouts_of(cell):
    """(floor, spot, amount, mark) per payout in a `payouts` cell."""
    out = []
    for part in (cell or "").split():
        where, _, mark = part.partition("+")
        pieces = where.split(":")
        if len(pieces) != 3 or not pieces[2].isdigit():
            continue
        out.append((pieces[0], pieces[1], int(pieces[2]), mark))
    return out


def counts_of(cell):
    """{name: n} from a `marked` or `fought` cell."""
    out = {}
    for part in (cell or "").split():
        name, _, n = part.rpartition(":")
        if n.isdigit():
            out[name] = int(n)
    return out


def lost_token(lost):
    """A run's `lost` as the column writes it: `floor:spot:left`, and
    `+mark` for a mark; '' for a cleared run."""
    if not isinstance(lost, (list, tuple)) or len(lost) < 4:
        return ""
    floor, spot, mark, left = lost[:4]
    return "%s:%s:%s%s" % (floor, str(spot).lower(), left,
                           "+" + mark if mark else "")


def lost_of(cell):
    """A `lost` cell back as the capture's [floor, SPOT, mark, left], or
    None."""
    where, _, mark = (cell or "").partition("+")
    pieces = where.split(":")
    if (len(pieces) != 3 or not pieces[0].lstrip("-").isdigit()
            or not pieces[2].isdigit()):
        return None
    return [int(pieces[0]), pieces[1].upper(), mark, int(pieces[2])]


# The doors a run comes in by, as the `door` column names them.
DOORS = {"disaster": "Galactic Disaster", "zero_orb": "Zero System",
         "chaos": "own screen"}


def difficulty_of(run):
    """A run's difficulty as the `difficulty` column writes it: the
    number ending the list id a base-game or Galactic Disaster Chaos is
    entered with (`embody_chaos_04_06` is 6), a Zero System map's level
    (`lv80`), '?' where the record holds neither. The Galactic Disaster
    list's number is read the way the base game's is, which nothing on
    the wire confirms."""
    codex = run.get("codex")
    if isinstance(codex, dict) and codex.get("lv") is not None:
        return "lv%s" % codex["lv"]
    tail = str(run.get("difficulty") or "").rsplit("_", 1)[-1]
    return str(int(tail)) if tail.isdigit() else "?"


def short_option(option):
    """A codex option as the `options` column writes it:
    `zero_orb_bonus_001` as `b001`, `zero_orb_penalty_112` as `p112`."""
    for prefix, letter in (("zero_orb_bonus_", "b"),
                           ("zero_orb_penalty_", "p")):
        if str(option).startswith(prefix):
            return letter + str(option)[len(prefix):]
    return str(option)


def marked_at_of(cell):
    """{spot: {mark: n}} from a `marked_at` cell."""
    out = collections.defaultdict(dict)
    for part in (cell or "").split():
        where, _, n = part.rpartition(":")
        spot, _, mark = where.partition(".")
        if n.isdigit() and mark:
            out[spot][mark] = int(n)
    return out


def run_of_row(row):
    """A row in the shape the capture records a run, for
    `chaos_estimate`'s readers."""
    paid = [[int(floor) if floor.lstrip("-").isdigit() else floor,
             spot.upper(), mark, None, amount]
            for floor, spot, amount, mark in payouts_of(row["payouts"])]
    return {"paid": paid, "lost": lost_of(row.get("lost")),
            "marked": counts_of(row.get("marked"))}


def row_of(run, source, parts):
    """One run as {column: cell}, over the columns this script owns."""
    currency = currency_of(run)
    season = short(run.get("season")) or CURRENCY.get(currency, "?")
    paid = [p for p in run.get("paid") or () if p[3] == currency]
    part = part_of(run["closed"], run.get("season"), parts)
    # The capture's own stamp, for a season no longer live.
    if part == "?" and isinstance(run.get("part"), int):
        part = "part %d" % run["part"] if run["part"] else "preseason"
    row = {
        "date": datetime.datetime.fromtimestamp(
            run["closed"], datetime.UTC).strftime("%Y-%m-%d %H:%M"),
        "season": season,
        "part": part,
        "chaos": chaos_estimate.chaos_name(run),
        "door": DOORS.get(run.get("via", "disaster"), run.get("via")),
        "difficulty": difficulty_of(run),
        "special": "+".join(chaos_estimate.ZERO_SPECIALS.get(s, s)
                            for s in (run.get("codex") or {}).get(
                                "special") or ()),
        "options": " ".join(
            short_option(o) for kind in ("bonus", "penalty")
            for o in (run.get("codex") or {}).get(kind) or ()),
        "mode": ("delegated" if run.get("delegated") else "ordinary")
                if "delegated" in run else "?",
        "client": run.get("client") or "?",
        "total": str(sum(amount for *_rest, amount in paid)),
        "payouts": " ".join(token(floor, spot, mark, amount)
                            for floor, spot, mark, _item, amount in paid),
        "marked": " ".join("%s:%d" % item for item in
                           sorted((run.get("marked") or {}).items())),
        "marked_at": " ".join(
            "%s.%s:%d" % (spot.lower(), mark, n)
            for spot, marks in sorted((run.get("marked_at") or {}).items())
            for mark, n in sorted(marks.items())),
        "fought": " ".join("%s:%d" % (spot.lower(), n) for spot, n in
                           sorted((run.get("fought") or {}).items())),
        "lost": lost_token(run.get("lost")),
        "log": source,
    }
    by_spot = collections.defaultdict(list)
    for _floor, spot, _mark, _item, amount in paid:
        by_spot[SPOT_COLUMN + str(spot)].append(str(amount))
    for column, amounts in by_spot.items():
        row[column] = "+".join(amounts)
    return row


def current(row):
    """Whether a row is a run of its own season's Chaos -- what the
    means, the report and the shipped figures are about. A base-game
    Chaos never is. A row that cannot name its Chaos came the Galactic
    Disaster's way unless its stage is a bare number, which only an
    unnamed Chaos leaves."""
    name = row.get("chaos") or "?"
    if name in CHAOS_SEASONS and CHAOS_SEASONS[name] is None:
        return False
    season = CHAOS_SEASONS.get(name)
    if season is None:
        return not name.isdigit()
    return season == "disaster_" + row["season"]


def merge(rows, found, parts, theirs, full):
    """{date: row}: the file's `rows` with each run `found` -- (run, the
    log or snapshot it came from) -- written over its own, the
    maintainer's columns `theirs` kept. `full` rebuilds every row from
    what was found."""
    kept = {} if full else dict(rows)
    for run, source in found:
        row = row_of(run, source, parts)
        old = rows.get(row["date"], {})
        # A row a log was replayed into stays as it is against the
        # capture's own record of the same run: the replay runs today's
        # capture code, and the record kept whatever the code of its day
        # did -- a break-in it could not see, fields it did not keep.
        if not full and stamp(old.get("log")) and not stamp(source):
            continue
        # A part is dated only while its season is live; a row read
        # again after keeps the one it was given.
        if row["part"] == "?" and old.get("part") not in (None, "", "?"):
            row["part"] = old["part"]
        if stamp(old.get("log")) and not stamp(source):
            row["log"] = old["log"]
        kept[row["date"]] = {**{c: old.get(c, "") for c in theirs}, **row}
    return kept


def existing():
    """(header, {date: {column: cell}}) from the file as it stands."""
    if not OUT.exists():
        return [], {}
    lines = OUT.read_text(encoding="utf-8").splitlines()
    if not lines or "log" not in lines[0].split("\t"):
        return [], {}
    header = lines[0].split("\t")
    rows = {}
    for line in lines[1:]:
        cells = line.split("\t")
        if cells and cells[0]:
            cells += [""] * (len(header) - len(cells))
            rows[cells[0]] = dict(zip(header, cells))
    return header, rows


def missed_of(row):
    """What a run lost to a mistake: the `missed` cell, blank for none."""
    cell = (row.get(MISSED) or "").strip()
    if not cell:
        return 0
    try:
        return int(cell)
    except ValueError:
        print("   ! %s: `%s` is %r, not a number -- counted as 0"
              % (row["date"], MISSED, cell))
        return 0


def _group_facts(rows):
    """For one group of rows: (set amounts, {mark: marked fights},
    fights). A set amount is keyed `boss <floor>` or the mark's name,
    and holds every amount it has paid."""
    amounts = collections.defaultdict(set)
    marked = collections.Counter()
    fights = 0
    for row in rows:
        for floor, spot, amount, mark in payouts_of(row["payouts"]):
            if mark:
                amounts[mark].add(amount)
            elif spot == "boss":
                amounts["boss %s" % floor].add(amount)
            else:
                amounts["%s %s, no mark" % (spot, floor)].add(amount)
        marked.update(counts_of(row.get("marked")))
        fought = counts_of(row.get("fought"))
        fights += fought.get("battle", 0) + fought.get("elite", 0)
    return amounts, marked, fights


def _named(key):
    """A set amount's or a mark's name as the report prints it; a fight
    carrying several marks, each by its name."""
    return " + ".join(MARKS.get(part, part) for part in key.split("+"))


def _describe(amounts, marked, fights, runs):
    sets = ", ".join("%s %s" % (_named(name),
                                "/".join(map(str, sorted(values))))
                     for name, values in sorted(amounts.items()))
    rates = ", ".join("%s %d in %d fights" % (_named(mark), n, fights)
                      for mark, n in sorted(marked.items())) or "none marked"
    return "%2d run(s): %s | %s" % (runs, sets or "nothing paid", rates)


def changes(rows):
    """Lines flagging, run by run: a set amount that differs from the
    last run that paid it, with what else changed between the two; a
    boss floor paying for the first time; a payout with no mark; and a
    mark never seen before."""
    out, last, first, unnamed = [], {}, True, set()
    for date in sorted(rows):
        row = rows[date]
        where = ("%s %s" % (row["season"], row["part"]),
                 row.get("client") or "?")
        for mark in counts_of(row.get("marked")):
            for part in mark.split("+"):
                if part not in MARKS and part not in unnamed:
                    unnamed.add(part)
                    out.append("   ! %s: a mark never seen before, %s -- "
                               "add it to MARKS once named" % (date, part))
        for floor, spot, amount, mark in payouts_of(row["payouts"]):
            if mark:
                key = mark
            elif spot == "boss":
                key = "boss %s" % floor
            else:
                out.append("   ! %s: floor %s's %s paid %d with no mark -- "
                           "a paying fight nothing names yet"
                           % (date, floor, spot, amount))
                continue
            if key in last and last[key][0] != amount:
                was, when, there = last[key]
                moved = ["the part (%s -> %s)" % (there[0], where[0])
                         if there[0] != where[0] else None,
                         "the game version (%s -> %s)" % (there[1], where[1])
                         if there[1] != where[1] else None]
                moved = [m for m in moved if m]
                out.append("   ! %s: %s paid %d, where %s paid %d; %s" % (
                    date, _named(key), amount, when, was,
                    "between the two, " + " and ".join(moved) + " changed"
                    if moved else "nothing else changed between the two"))
            elif key not in last and key.startswith("boss") and not first:
                out.append("   ! %s: %s paid for the first time (%d)"
                           % (date, key, amount))
            last[key] = (amount, date, where)
        first = False
    return out


def _compare_amounts(a, b):
    """Differences between two groups' set amounts, as phrases."""
    out = []
    for name in sorted(set(a) | set(b)):
        if name in a and name in b and a[name] != b[name]:
            out.append("%s %s -> %s" % (
                name, "/".join(map(str, sorted(a[name]))),
                "/".join(map(str, sorted(b[name])))))
        elif name not in a or name not in b:
            out.append("%s only %s" % (name, "after" if name in b
                                       else "before"))
    return out


def _compare_rates(a, b):
    """How two groups' mark rates compare, as phrases."""
    (marked_a, fights_a), (marked_b, fights_b) = a, b
    if min(fights_a, fights_b) < FEWEST_FIGHTS:
        return ["too few fights to compare (%d and %d; %d a side)"
                % (fights_a, fights_b, FEWEST_FIGHTS)]
    out = []
    for mark in sorted(set(marked_a) | set(marked_b)):
        pa, pb = marked_a[mark] / fights_a, marked_b[mark] / fights_b
        pooled = (marked_a[mark] + marked_b[mark]) / (fights_a + fights_b)
        spread = math.sqrt(pooled * (1 - pooled)
                           * (1 / fights_a + 1 / fights_b)) or 1
        z = (pb - pa) / spread
        out.append("%s %.3f -> %.3f a fight: %s" % (
            mark, pa, pb, "MOVED" if abs(z) >= Z_DIFFERS else "same"))
    return out


def report(rows):
    """The four questions, per season part and per game version."""
    groups = collections.defaultdict(list)
    for row in rows.values():
        groups[("%s %s" % (row["season"], row["part"]),
                row.get("client") or "?")].append(row)
    facts = {key: _group_facts(members) for key, members in groups.items()}
    print()
    flagged = changes(rows)
    print("   Changes, run by run:" if flagged
          else "   Changes, run by run: none")
    for line in flagged:
        print(line)
    print("   What pays, by season part and game version:")
    for key in sorted(groups):
        print("   %-14s %-22s %s" % (key[0], key[1],
                                     _describe(*facts[key],
                                               len(groups[key]))))

    def pairs(same, other):
        return [(a, b) for a in sorted(groups) for b in sorted(groups)
                if a < b and a[same] == b[same] and a[other] != b[other]
                and "?" not in a[0] + a[1] + b[0] + b[1]]

    for question, same, other, what in (
            ("Set amounts, by season part", 1, 0, "amounts"),
            ("Set amounts, by game version", 0, 1, "amounts"),
            ("Mark rates, by season part", 1, 0, "rates"),
            ("Mark rates, by game version", 0, 1, "rates")):
        found = pairs(same, other)
        if not found:
            print("   %s: can't tell -- no two %s share a %s" % (
                question, "parts" if other == 0 else "versions",
                "game version" if same == 1 else "season part"))
            continue
        for a, b in found:
            if what == "amounts":
                moved = _compare_amounts(facts[a][0], facts[b][0])
                verdict = "; ".join(moved) or "same"
            else:
                verdict = "; ".join(_compare_rates(facts[a][1:],
                                                   facts[b][1:]))
            print("   %s: %s -> %s: %s" % (question, a[other], b[other],
                                           verdict))


def _reference(rows, row):
    """({boss floor: amount}, {mark: amount}) to price a lost run's
    `missed` by: its part's bosses as the latest cleared run of that
    season part paid them, and each mark as last paid -- the shipped
    figures where no run has."""
    entry = chaos_estimate.shipped_entry("disaster_" + row["season"])
    marks = {mark: amount for mark, (amount, _rate)
             in (entry.get("marks") or {}).items()}
    found = re.match(r"part (\d+)$", row.get("part") or "")
    bosses = (chaos_estimate.shipped_bosses(entry, int(found.group(1)))
              if found else {})
    for date in sorted(rows):
        other = rows[date]
        for _floor, spot, amount, mark in payouts_of(other["payouts"]):
            if mark and spot != "boss":
                marks[mark] = amount
        if (other is row or other.get("lost")
                or (other["season"], other["part"], other.get("chaos"))
                != (row["season"], row["part"], row.get("chaos"))):
            continue
        table = {int(floor): amount for floor, spot, amount, _mark
                 in payouts_of(other["payouts"])
                 if spot == "boss" and floor.isdigit()}
        if table:
            bosses = table
    return bosses, marks


def fill_missed(rows):
    """Fill each whole lost run's empty `missed`; flag one filled by
    hand that the loss does not come to. The dates filled, in order."""
    filled = []
    for date in sorted(rows):
        row = rows[date]
        run = run_of_row(row)
        if not run["lost"] or not chaos_estimate.is_full(run):
            continue
        due = chaos_estimate.missed(run, *_reference(rows, row))
        cell = (row.get(MISSED) or "").strip()
        if not cell:
            if due:
                row[MISSED] = str(due)
                filled.append("%s +%d" % (date, due))
        elif missed_of(row) != due:
            print("   ! %s: `missed` says %s; the loss comes to %d"
                  % (date, cell, due))
    return filled


def _whole_runs(rows):
    """The rows a rate is counted over, oldest first: whole runs, none
    inside a `chaos_estimate.RATE_EVENTS` window."""
    out = []
    for date in sorted(rows):
        row = rows[date]
        when = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M").replace(
            tzinfo=datetime.UTC).timestamp()
        if (chaos_estimate.is_full(run_of_row(row))
                and not chaos_estimate.in_rate_event(when)):
            out.append(row)
    return out


def _log_likelihood(k, n):
    """Of k marked fights in n, at their own rate."""
    if k <= 0 or k >= n:
        return 0.0
    p = k / n
    return k * math.log(p) + (n - k) * math.log(1 - p)


def _best_split(ks, ns):
    """(what the best before-and-after split gains in log-likelihood
    over one rate throughout, where it falls), with `FEWEST_RUNS` a
    side; (0.0, None) where no split gains."""
    total_k, total_n = sum(ks), sum(ns)
    whole = _log_likelihood(total_k, total_n)
    best, at, k_left, n_left = 0.0, None, 0, 0
    for i in range(1, len(ks)):
        k_left += ks[i - 1]
        n_left += ns[i - 1]
        if min(i, len(ks) - i) < FEWEST_RUNS:
            continue
        gain = (_log_likelihood(k_left, n_left)
                + _log_likelihood(total_k - k_left, total_n - n_left)
                - whole)
        if gain > best:
            best, at = gain, i
    return best, at


def split_test(ks, ns, rng):
    """(where the best split falls, the share of shuffled orders that
    split as well), or (None, None) where there is no split to test."""
    gain, at = _best_split(ks, ns)
    if at is None:
        return None, None
    pairs = list(zip(ks, ns))
    beaten = 0
    for _ in range(SHIFT_TRIALS):
        rng.shuffle(pairs)
        if _best_split([k for k, _n in pairs],
                       [n for _k, n in pairs])[0] >= gain:
            beaten += 1
    return at, (beaten + 1) / (SHIFT_TRIALS + 1)


def shifts(ks, ns, rng, offset=0):
    """[(index, p)] for every shift in a rate over runs in order: the
    best split where it holds, then each side searched again."""
    at, p = split_test(ks, ns, rng)
    if at is None or p >= SHIFT_ALPHA:
        return []
    return (shifts(ks[:at], ns[:at], rng, offset) + [(offset + at, p)]
            + shifts(ks[at:], ns[at:], rng, offset + at))


def rate_shifts(rows):
    """Print each mark's rate over the whole runs, and any shift in it."""
    runs = _whole_runs(rows)
    fights = []
    for row in runs:
        fought = counts_of(row.get("fought"))
        fights.append(fought.get("battle", 0) + fought.get("elite", 0))
    marks = sorted({one for row in runs
                    for key in counts_of(row.get("marked"))
                    for one in key.split("+")})
    print("   Mark rates over time, %d whole run(s)%s:" % (
        len(runs), "" if len(runs) == len(rows)
        else ", %d left out" % (len(rows) - len(runs))))
    for mark in marks:
        ks = [sum(n for key, n in counts_of(row.get("marked")).items()
                  if mark in key.split("+")) for row in runs]
        found = shifts(ks, fights, random.Random(0))
        if found:
            edges = [0] + [at for at, _p in found] + [len(ks)]
            print("   ! %s shifted: %s (p %s)" % (_named(mark), ", ".join(
                "%.3f a fight from %s" % (sum(ks[a:b]) / max(1, sum(
                    fights[a:b])), runs[a]["date"][:10])
                for a, b in zip(edges, edges[1:])),
                ", ".join("%.3f" % p for _at, p in found)))
            continue
        _at, p = split_test(ks, fights, random.Random(0))
        print("   %s: %d in %d fights, %.3f a fight, %.2f a run; %s" % (
            _named(mark), sum(ks), sum(fights),
            sum(ks) / max(1, sum(fights)), sum(ks) / max(1, len(runs)),
            "no shift (p %.2f)" % p if p is not None
            else "too few runs to look for a shift (%d a side)"
            % FEWEST_RUNS))
    spot_rates(runs, marks)


def spot_rates(runs, marks):
    """Print each mark's rate on each kind of ordinary fight, over the
    runs that recorded where their marks were met: see the module
    docstring's note on a map's own mix of fights."""
    told = [row for row in runs
            if row.get("marked_at") or not row.get("marked")]
    if not told:
        return
    for mark in marks:
        parts, met = [], 0
        for spot in ("battle", "elite"):
            n = sum(counts_of(row.get("fought")).get(spot, 0)
                    for row in told)
            k = sum(count for row in told
                    for key, count in marked_at_of(
                        row.get("marked_at")).get(spot, {}).items()
                    if mark in key.split("+"))
            met += k
            if n:
                parts.append("%.3f per %s (%d in %d)" % (k / n, spot, k, n))
        # A break-in is a spot of its own, and is never met on either.
        if parts and met:
            print("      %s by spot, %d run(s): %s" % (
                _named(mark), len(told), ", ".join(parts)))


def shipped_figures(rows):
    """Print, per season, what `chaos_estimate.SHIPPED` wants: each
    part's bosses as its latest cleared run paid them, each mark's
    amount as last paid, and each mark per whole run."""
    by_season = collections.defaultdict(dict)
    for date, row in rows.items():
        if row["season"] != "?":
            by_season[row["season"]][date] = row
    print("   For chaos_estimate.SHIPPED:")
    for season in sorted(by_season):
        members = by_season[season]
        bosses, amounts = {}, {}
        for date in sorted(members):
            row = members[date]
            for _floor, spot, amount, mark in payouts_of(row["payouts"]):
                if mark and spot != "boss":
                    amounts[mark] = amount
            found = re.match(r"part (\d+)$", row["part"] or "")
            table = {int(floor): amount for floor, spot, amount, _mark
                     in payouts_of(row["payouts"])
                     if spot == "boss" and floor.isdigit()}
            if found and table and not row.get("lost"):
                bosses[int(found.group(1))] = table
        whole = _whole_runs(members)
        counted = collections.Counter()
        for row in whole:
            for key, n in counts_of(row.get("marked")).items():
                counted[key] += n
        marks = {mark: (amounts.get(mark, 0),
                        round(counted[mark] / len(whole), 2) if whole else 0)
                 for mark in sorted(set(amounts) | set(counted))}
        print('       "disaster_%s": {' % season)
        print('           "bosses": %s,' % dict(sorted(bosses.items())))
        print('           "marks": %s,  # %d whole run(s)' % (marks,
                                                              len(whole)))
        print('       },')


def main():
    full = "--all" in sys.argv[1:]
    header, rows = existing()
    theirs = header[header.index("log") + 1:] if header else []
    if MISSED not in theirs:
        theirs.insert(0, MISSED)
    from_logs = [row["log"] for row in rows.values() if stamp(row["log"])]
    since = "" if full or not from_logs else max(map(stamp, from_logs))
    if since:
        print("Reading Chaos runs from the snapshots, and from "
              "websocket_debug_%s on (the newest row's log); --all reads "
              "every log." % since, flush=True)
    else:
        print("Reading Chaos runs from the snapshots and every log, loose "
              "and archived.", flush=True)

    held, newest = snapshots()
    parts = season_parts(newest)
    # By the second each run cleared: a run a snapshot and a log both
    # hold is one run, and the log, read second, names it.
    found = {run["closed"]: (run, name) for name, run in held}
    seen = 0
    for name, lines in logs(since):
        seen += 1
        work = Path(tempfile.mkdtemp(prefix="chaos_"))
        try:
            got = runs_in(lines, fresh_addon(work))
        finally:
            shutil.rmtree(work, ignore_errors=True)
        print("   %s: %d run(s)" % (name, len(got)), flush=True)
        for run in got:
            found[run["closed"]] = (run, name)

    kept = merge(rows, found.values(), parts, theirs, full)
    new = len({row_of(run, s, parts)["date"] for run, s in found.values()}
              - set(rows))
    filled = fill_missed(kept)

    spots = {c for row in kept.values() for c in row
             if c.startswith(SPOT_COLUMN)}
    header = OWNED + sorted(spots) + ["log"] + theirs
    lines = ["\t".join(header)]
    for date in sorted(kept):
        lines.append("\t".join(kept[date].get(c, "") for c in header))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("%d snapshot run(s), %d log(s) read, %d new run(s), %d row(s) -> "
          "%s" % (len(held), seen, new, len(kept), OUT.relative_to(ROOT)))
    if theirs:
        print("   kept your columns: %s" % ", ".join(theirs))
    if filled:
        print("   filled `missed` for whole lost runs: %s" % ", ".join(filled))
    unknown = sorted({row["season"] for row in kept.values()
                      if row["season"] == "?"})
    if unknown:
        print("   ! a run with no season: no standings were read before it "
              "cleared, and its currency is not in CURRENCY")
    if not kept:
        return
    own = {date: row for date, row in kept.items() if current(row)}
    by_part = collections.defaultdict(list)
    others = collections.defaultdict(list)
    tally = collections.Counter()
    counted = []
    for row in kept.values():
        missed = missed_of(row)
        if missed:
            counted.append("%s +%d" % (row["date"], missed))
        paid = int(row["total"] or 0) + missed
        if current(row):
            by_part["%s %s" % (row["season"], row["part"])].append(paid)
            for _floor, _spot, amount, _mark in payouts_of(row["payouts"]):
                tally[amount] += 1
        else:
            others[", ".join(cell for cell in (
                row["chaos"], row.get("door"), row.get("special"),
                row["mode"]) if cell)].append(row)
    if counted:
        print("   counted with what they missed: %s"
              % ", ".join(sorted(counted)))

    def line(label, got):
        print("   %-14s %2d run(s), mean %5.0f, min %5d, max %5d"
              % (label, len(got), sum(got) / len(got), min(got), max(got)))

    # What a run of the season's own Chaos pays played through, by part
    # and by season. The estimate is built from its parts instead --
    # `shipped_figures`.
    by_season = collections.defaultdict(list)
    for part, got in by_part.items():
        by_season[part.split()[0]].extend(got)
    for part in sorted(by_part):
        line(part, by_part[part])
    for season in sorted(by_season):
        line(season + " whole", by_season[season])
    if by_part:
        line("ALL", [total for got in by_part.values() for total in got])
    print()
    print("   payout values: %s"
          % ", ".join("%dx%d" % (n, v) for v, n in sorted(tally.items())))
    report(own)
    print()
    rate_shifts(own)
    print()
    shipped_figures(own)
    if others:
        print()
        print("   Other Chaos, left out of everything above:")
        for label in sorted(others):
            rows = others[label]
            print("   %-30s %s" % (label, _describe(
                *_group_facts(rows), len(rows))))


if __name__ == "__main__":
    main()
