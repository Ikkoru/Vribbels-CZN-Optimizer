"""Write `docs/chaos_runs.tsv`: one Galactic Disaster Chaos run per row,
and report what pays in a run and whether it has moved.

    python docs/chaos_runs.py          # snapshots, and logs since the newest row
    python docs/chaos_runs.py --all    # snapshots, and every log, loose and archived

`docs/chaos_runs.cmd` runs the first from Explorer.

**A run comes from two places, and is one row.** The capture records
every Chaos run in its snapshot (`chaos_runs`, carried from each
snapshot to the next), and a debug log replays through the same capture
code to the same records -- see `Addon._note_chaos` in
`Vribbels/capture/manager.py`. A run is keyed by the second it cleared,
which both give alike, so a run a snapshot and a log both hold is one
row, whose `log` names the debug log.

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

The columns this script owns:

| column    | what it says                                                  |
| --------- | --------------------------------------------------------------- |
| `date`    | when the run was cleared, UTC                                   |
| `season`  | the Galactic Disaster season it ran in                          |
| `part`    | which part of the season: the shop page open when it cleared   |
| `client`  | the game client and data patch it ran on: `cznlive 1.464 r688`  |
| `total`   | what the run paid in the season's currency                      |
| `payouts` | every payout in order, `floor:spot:amount`, `+mark` for a mark  |
| `marked`  | the fights carrying a mark, paid or not: `k5:2 e:1`             |
| `fought`  | the fights, by spot: `battle:11 elite:4 boss:3`                 |
| `SPOT_*`  | the payouts at each kind of spot, `+` between them              |
| `log`     | the capture it was read from                                    |

**What pays is the fight, and the wire names what makes one pay.** A
boss pays a set amount for its floor. Any other fight pays only where
it carries a mark -- a `keyword_tag` (`k5`) or a battle id ending `_e`
(`e`) -- and each mark pays a set amount. So a run's take is set but
for how many marked fights it meets, and the report after the table
answers four questions, per season part and per game version: have the
set amounts moved, and have the marks' rates?

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
OWNED = ["date", "season", "part", "client", "total", "payouts", "marked",
         "fought"]
# The maintainer's column the summary reads: see the module docstring.
MISSED = "missed"
SPOT_COLUMN = "SPOT_TYPE_"

# A rate comparison with fewer fights than this on either side says
# nothing, and one whose difference is under this many standard errors
# is chance.
FEWEST_FIGHTS = 30
Z_DIFFERS = 2.0

from capture.manager import CaptureManager                    # noqa: E402


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
    """(runs, newest snapshot) over the loose snapshots: (name, run) for
    every run any of them holds, and the newest one's contents."""
    runs, newest = [], None
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


def row_of(run, source, parts):
    """One run as {column: cell}, over the columns this script owns."""
    currency = currency_of(run)
    season = short(run.get("season")) or CURRENCY.get(currency, "?")
    paid = [p for p in run.get("paid") or () if p[3] == currency]
    row = {
        "date": datetime.datetime.fromtimestamp(
            run["closed"], datetime.UTC).strftime("%Y-%m-%d %H:%M"),
        "season": season,
        "part": part_of(run["closed"], run.get("season"), parts),
        "client": run.get("client") or "?",
        "total": str(sum(amount for *_rest, amount in paid)),
        "payouts": " ".join(token(floor, spot, mark, amount)
                            for floor, spot, mark, _item, amount in paid),
        "marked": " ".join("%s:%d" % item for item in
                           sorted((run.get("marked") or {}).items())),
        "fought": " ".join("%s:%d" % (spot.lower(), n) for spot, n in
                           sorted((run.get("fought") or {}).items())),
        "log": source,
    }
    by_spot = collections.defaultdict(list)
    for _floor, spot, _mark, _item, amount in paid:
        by_spot[SPOT_COLUMN + str(spot)].append(str(amount))
    for column, amounts in by_spot.items():
        row[column] = "+".join(amounts)
    return row


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


def _describe(amounts, marked, fights, runs):
    sets = " ".join("%s=%s" % (name, "/".join(map(str, sorted(values))))
                    for name, values in sorted(amounts.items()))
    rates = ", ".join("%s %d in %d fights" % (mark, n, fights)
                      for mark, n in sorted(marked.items())) or "none marked"
    return "%2d run(s): %s | %s" % (runs, sets or "nothing paid", rates)


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

    kept = {} if full else dict(rows)
    for run, source in found.values():
        row = row_of(run, source, parts)
        old = rows.get(row["date"], {})
        # A part is dated only while its season is live; a row read
        # again after keeps the one it was given.
        if row["part"] == "?" and old.get("part") not in (None, "", "?"):
            row["part"] = old["part"]
        if stamp(old.get("log")) and not stamp(source):
            row["log"] = old["log"]
        kept[row["date"]] = {**{c: old.get(c, "") for c in theirs}, **row}
    new = len({row_of(run, s, parts)["date"] for run, s in found.values()}
              - set(rows))

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
    unknown = sorted({row["season"] for row in kept.values()
                      if row["season"] == "?"})
    if unknown:
        print("   ! a run with no season: no standings were read before it "
              "cleared, and its currency is not in CURRENCY")
    if not kept:
        return
    by_part = collections.defaultdict(list)
    tally = collections.Counter()
    counted = []
    for row in kept.values():
        missed = missed_of(row)
        if missed:
            counted.append("%s +%d" % (row["date"], missed))
        by_part["%s %s" % (row["season"], row["part"])].append(
            int(row["total"] or 0) + missed)
        for _floor, _spot, amount, _mark in payouts_of(row["payouts"]):
            tally[amount] += 1
    if counted:
        print("   counted with what they missed: %s"
              % ", ".join(sorted(counted)))
    by_season = collections.defaultdict(list)
    for part, got in by_part.items():
        by_season[part.split()[0]].extend(got)
    for part in sorted(by_part):
        got = by_part[part]
        print("   %-14s %2d run(s), mean %5.0f, min %5d, max %5d"
              % (part, len(got), sum(got) / len(got), min(got), max(got)))
    # The season's own line is its `per_run` in the Checklist's
    # SEASON_ESTIMATE; the parts show whether one pays differently.
    for season in sorted(by_season):
        got = by_season[season]
        print("   %-14s %2d run(s), mean %5.0f, min %5d, max %5d"
              % (season + " whole", len(got), sum(got) / len(got), min(got),
                 max(got)))
    allp = [total for got in by_part.values() for total in got]
    print("   %-14s %2d run(s), mean %5.0f, min %5d, max %5d"
          % ("ALL", len(allp), sum(allp) / len(allp), min(allp), max(allp)))
    print()
    print("   payout values: %s"
          % ", ".join("%dx%d" % (n, v) for v, n in sorted(tally.items())))
    report(kept)


if __name__ == "__main__":
    main()
