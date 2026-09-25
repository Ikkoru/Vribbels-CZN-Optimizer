"""Write `docs/chaos_runs.tsv`: one Galactic Disaster Chaos run per row.

    python docs/chaos_runs.py          # logs since the newest row
    python docs/chaos_runs.py --all    # every log, loose and archived

`docs/chaos_runs.cmd` runs the first from Explorer.

Re-run it after any capture that holds a run. **By default it reads
only from the log that holds the newest row onward** -- that log is
read again, since a run may have been added to it after the last
pass -- and keeps every older row as the file has it. The archive is
opened only when that log is no longer loose. `--all` rebuilds every
row from every log, which is what a change to how a run is measured
needs.

**Columns to the RIGHT of `log` are yours and are kept**, matched to
the run by its `date`. The wire does not say WHY a floor paid -- a
Rare Species modifier, an Aether Eater, the Core of Discord -- so
those are notes only someone who watched the run can add, and
re-running this must not lose them.

The columns this script owns:

| column    | what it says                                            |
| --------- | --------------------------------------------------------- |
| `date`    | when the run was cleared, UTC                             |
| `season`  | which Galactic Disaster season's currency it paid         |
| `part`    | which third of the season it fell in, season 4 only       |
| `total`   | what the run paid in the season's currency                |
| `payouts` | every payout in order, as `floor:amount`                  |
| `SPOT_*`  | the payouts at each kind of spot, `+` between them        |
| `log`     | the capture it was read from                              |

**A run's payout is measured through the addon's own cache**, not by
adding up what the wire says. Counting the wire's deltas over-counts
about sevenfold: `drop_item` under a `battle/reward_complete` is the
reward MENU being offered, `drop_item_info` under the merchant is a
price list, and the clear's own envelope restates the whole run
rather than adding to it.

**`spot_type` is a weak label and the amount is a better one.** Three
`SPOT_TYPE_ELITE` floors in one run paid nothing while a fourth paid
60: what earns the currency is a modifier on the monster, which the
wire never names. The column is here because it is what the wire
does say, not because it explains anything.

Nothing here writes to `snapshots/`; the archive is read in place.
"""
import collections
import datetime
import glob
import gzip
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Vribbels"
sys.path.insert(0, str(SOURCE))
os.chdir(SOURCE)

OUT = ROOT / "docs" / "chaos_runs.tsv"

# The season currencies, one id per season -- see `game_data`.
CURRENCY = {3920001: "s01", 3920002: "s02", 3920006: "s03", 3920031: "s04"}

# When each of season 4's shop pages opened, which is what splits the
# season into its parts. Derived in `checklist_tab.shop_pages_open`.
PARTS = [(1785290400, "part 1"), (1787187600, "part 2"),
         (1788915600, "part 3")]

OPENS = "disaster/enter_disaster_chaos_stage"
CLOSES = "stage/clear_stage"
ENTERS = "stage/enter_spot"
PAYS = "spot_reward/get_drop_item"

# What this script fills in. Anything after them in an existing file
# is the maintainer's and is carried over by `date`.
OWNED = ["date", "season", "part", "total", "payouts"]

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


def part_of(when, season):
    """Which third of the season a run fell in, or `?`.

    Only season 4's page dates have been derived, so a run paid in
    any other season's currency gets no part rather than season 4's.
    """
    if season != "s04":
        return "?"
    got = [name for at, name in PARTS if at <= when]
    return got[-1] if got else "before s04"


def held(addon):
    """What the addon believes is held of each season currency."""
    out = {}
    for row in ((addon.inventory_data or {}).get("items") or []):
        if isinstance(row, dict) and row.get("res_id") in CURRENCY:
            out[row["res_id"]] = row.get("amount")
    for row in ((addon.character_data or {}).get("currencies") or {}).values():
        if isinstance(row, dict) and row.get("res_id") in CURRENCY:
            out[row["res_id"]] = row.get("amount")
    return out


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


def runs_in(name, lines, addon):
    """Every whole run in one log, with each payout kept apart."""
    found, qids, live, spot, floor = [], {}, None, "?", -1
    for line in lines:
        if not line.strip():
            continue
        try:
            frame = json.loads(line)
        except ValueError:
            continue
        data = frame.get("data")
        from_client = frame.get("direction") == "client_to_server"
        rows = data if isinstance(data, list) else [data]
        if from_client:
            for r in rows:
                if isinstance(r, dict) and r.get("qid") is not None:
                    qids[r["qid"]] = "%s/%s" % (
                        r.get("cmd"), (r.get("params") or {}).get("cmd"))
        before = held(addon)
        try:
            addon.websocket_message(_Flow(data, from_client))
        except Exception:                                     # noqa: BLE001
            pass
        if from_client:
            continue
        after = held(addon)
        for r in rows:
            if not isinstance(r, dict):
                continue
            asked = qids.get(r.get("qid"), "?")
            when = r.get("service_server_time") or 0
            info = r.get("spot_info")
            if asked == ENTERS and isinstance(info, dict):
                spot = info.get("spot_type") or "?"
                floor = info.get("floor", floor)
            if asked == OPENS:
                live = {"opened": when, "log": name, "paid": []}
                spot, floor = "?", -1
            elif asked == CLOSES and live is not None:
                live["closed"] = when
                found.append(live)
                live = None
            if live is None:
                continue
            moved = [(item, amount - before[item])
                     for item, amount in after.items()
                     if before.get(item) is not None
                     and amount != before[item]]
            if moved:
                # Which season's currency it was. A run pays in one,
                # so the first is the run's own.
                live.setdefault("season", CURRENCY[moved[0][0]])
                live["paid"].append(
                    (floor, spot if asked == PAYS else asked.split("/")[-1],
                     sum(value for _item, value in moved)))
    return found


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


def row_of(run):
    """One run as {column: cell}, over the columns this script owns."""
    at = collections.defaultdict(list)
    for _floor, where, value in run["paid"]:
        at[where].append(value)
    row = {
        "date": datetime.datetime.fromtimestamp(
            run["closed"], datetime.UTC).strftime("%Y-%m-%d %H:%M"),
        "season": run.get("season", "?"),
        "part": part_of(run["closed"], run.get("season")),
        "total": str(sum(value for _f, _w, value in run["paid"])),
        "payouts": " ".join("%s:%s" % (floor, value)
                            for floor, _w, value in run["paid"]),
        "log": run["log"],
    }
    for where, values in at.items():
        row[where] = "+".join(str(v) for v in values)
    return row


def main():
    full = "--all" in sys.argv[1:]
    header, rows = existing()
    theirs = header[header.index("log") + 1:] if header else []
    since = "" if full or not rows else stamp(rows[max(rows)]["log"])
    if since:
        print("Reading Chaos runs from websocket_debug_%s on (the newest "
              "row's log); --all reads every log." % since, flush=True)
    else:
        print("Reading Chaos runs from every log, loose and archived.",
              flush=True)

    found, seen = [], 0
    for name, lines in logs(since):
        seen += 1
        work = Path(tempfile.mkdtemp(prefix="chaos_"))
        try:
            got = runs_in(name, lines, fresh_addon(work))
        finally:
            shutil.rmtree(work, ignore_errors=True)
        print("   %s: %d run(s)" % (name, len(got)), flush=True)
        found.extend(got)

    # Keyed by date, so a run read twice -- from the log that held the
    # newest row, or from a capture archived twice -- fills one row.
    # A run read again replaces its own cells and keeps the maintainer's.
    kept = {} if full else dict(rows)
    for run in found:
        row = row_of(run)
        notes = rows.get(row["date"], {})
        kept[row["date"]] = {**{c: notes.get(c, "") for c in theirs}, **row}
    new = len({row_of(run)["date"] for run in found} - set(rows))

    spots = {c for row in kept.values() for c in row
             if c not in OWNED and c != "log" and c not in theirs}
    header = OWNED + sorted(spots) + ["log"] + theirs
    lines = ["\t".join(header)]
    for date in sorted(kept):
        lines.append("\t".join(kept[date].get(c, "") for c in header))
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("%d log(s) read, %d new run(s), %d row(s) -> %s"
          % (seen, new, len(kept), OUT.relative_to(ROOT)))
    if theirs:
        print("   kept your columns: %s" % ", ".join(theirs))
    if not kept:
        return
    by_part = collections.defaultdict(list)
    tally = collections.Counter()
    for row in kept.values():
        by_part["%s %s" % (row["season"], row["part"])].append(
            int(row["total"] or 0))
        for pay in row["payouts"].split():
            tally[int(pay.rsplit(":", 1)[1])] += 1
    for part in sorted(by_part):
        got = by_part[part]
        print("   %-12s %2d run(s), mean %5.0f, min %5d, max %5d"
              % (part, len(got), sum(got) / len(got), min(got), max(got)))
    allp = [total for got in by_part.values() for total in got]
    print("   %-12s %2d run(s), mean %5.0f, min %5d, max %5d"
          % ("ALL", len(allp), sum(allp) / len(allp), min(allp), max(allp)))
    print()
    print("   payout values: %s"
          % ", ".join("%dx%d" % (n, v) for v, n in sorted(tally.items())))


if __name__ == "__main__":
    main()
