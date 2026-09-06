"""Rewrite the three item-id dumps.

Run after a capture to re-read what the newest snapshot holds:

    python _tmp/items_id_dump.py

Three files, and which one an id lands in says what is left to do with
it:

* `items_id_known.tsv` -- the program USES it: a table names it and it
  is not in `RECORDED_ONLY`. Family, group, tier, rarity, icon and the
  amount held.
* `items_id_known_not_in_program.tsv` -- it has been identified and the
  program does nothing with it. Either the dump carries a hand-typed
  `Name` and no table does, or a table names it only for the record.
  **This is the worklist.**
* `items_id_unknown.tsv` -- neither. Where it came from and what it
  reads, for diffing against the next capture.

The last two share their columns, and a row moves between them by
gaining or losing its `Name` -- so a hand-typed identification is never
retyped and never lost.

The amount column is what makes an id identifiable at all: an item is
named by spending some and diffing two captures, so a dump that has
lost its counts cannot be compared against the next one.

**Three sources, not one.** Ordinary items carry an `amount` in
`inventory.items`; the three generics are CURRENCIES and live under
`characters.currencies`; and a period item has no amount at all -- its
copies are LISTED, each with its own expiry, which is why the count
here comes from `period_items.held` rather than from a field.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Vribbels"))

import period_items                         # noqa: E402
from game_data.constants import (            # noqa: E402
    COMBATANT_PROMOTION, EXP_MATERIALS, GROWTH_STONES, NAMED_MATERIALS,
    PARTNER_PROMOTION, PERIOD_ITEMS, RECORDED_ONLY, item_art,
)

OUT = Path(__file__).resolve().parent

# The columns this script owns in both unknown dumps, and the hand-added
# column that decides which of the two a row belongs in.
UNKNOWN_OWNED = ("res_id", "where", "amount")
NAME_COLUMN = "Name"

# What to call each table in the `family` column, in the order the
# rows should come out.
FAMILIES = (
    (NAMED_MATERIALS, "named"),
    (PERIOD_ITEMS, "period item"),
    (EXP_MATERIALS, "EXP material"),
    (GROWTH_STONES, "Growth Stone"),
    (COMBATANT_PROMOTION, "Combatant Promotion (Manual)"),
    (PARTNER_PROMOTION, "Partner Promotion (Certificate)"),
)


def newest_snapshot():
    snaps = sorted((ROOT / "Vribbels" / "snapshots").glob(
        "memory_fragments_*.json"))
    if not snaps:
        raise SystemExit("no snapshot in Vribbels/snapshots/")
    return snaps[-1]


def amounts(snapshot):
    """{res_id: (amount, where)} across all three of the sources."""
    data = json.loads(snapshot.read_text(encoding="utf-8"))
    inventory = data.get("inventory") or {}
    out = {}
    for item in inventory.get("items") or []:
        res_id = item.get("res_id")
        if isinstance(res_id, int):
            out[res_id] = (item.get("amount", 0), "items")
    for key, record in ((data.get("characters") or {}).get("currencies")
                        or {}).items():
        try:
            out[int(key)] = (record.get("amount", 0), "currencies")
        except (TypeError, ValueError):
            continue
    # No amount anywhere: the copies are listed, and `period_items`
    # is what knows where in the nesting they are listed.
    for res_id, expiries in period_items.held(inventory).items():
        out[res_id] = (len(expiries), "period_items")
    return out


def read_existing(path, owned):
    """(user column names, {res_id: their values}) from a file on disk.

    **This script owns the LEFTMOST columns and nothing else.** Anything
    a hand has added to the right of them is read back here and written
    out again untouched, in the same order, so an id named by hand
    survives the next run.

    Raises if the file's own leftmost columns are not the ones this
    script writes: every cell after them would shift by the difference,
    which silently moves each hand-typed value into the wrong column.
    """
    if not path.exists():
        return [], {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return [], {}
    header = lines[0].split("\t")
    if header[:len(owned)] != list(owned):
        raise SystemExit(
            f"{path.name} starts with columns {header[:len(owned)]}, not "
            f"{list(owned)}. Rewriting it would move every hand-typed cell "
            f"into a neighbouring column. Reconcile the header first."
        )
    extra = header[len(owned):]
    kept = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split("\t")
        try:
            res_id = int(cells[0])
        except (IndexError, ValueError):
            continue
        tail = cells[len(owned):]
        kept[res_id] = tail + [""] * (len(extra) - len(tail))
    return extra, kept


def write(path, owned, rows, carried=None):
    """Rewrite `path`, keeping every hand-added column and row.

    `rows` is {res_id: owned values}. An id the snapshot no longer
    carries keeps its row and its hand-typed cells; the columns this
    script owns go BLANK for it, because a stale amount reads exactly
    like a current one.

    `carried` is (extra columns, {res_id: their cells}) from somewhere
    other than this file -- what lets a row MOVE between the two
    unknown dumps with its hand-typed cells intact. Without it the file
    reads its own, which is what a file nothing moves out of wants.
    """
    extra, kept = carried if carried is not None else read_existing(path, owned)
    order = sorted(set(rows) | set(kept))
    blank = [""] * (len(owned) - 1)
    gone = []
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("\t".join(list(owned) + extra) + "\n")
        for res_id in order:
            values = rows.get(res_id)
            if values is None:
                values = blank
                gone.append(res_id)
            tail = kept.get(res_id, [""] * len(extra))
            f.write("\t".join(str(c) for c in
                              [res_id, *values, *tail]) + "\n")
    print(f"{path.name}: {len(order)} rows, {len(extra)} hand-added columns"
          + (f", {len(gone)} id(s) not in this snapshot: {gone}" if gone
             else ""))


def main():
    snapshot = newest_snapshot()
    held = amounts(snapshot)
    print(f"from {snapshot.name}")

    known_rows, named, table_names = {}, set(), {}
    for table, family in FAMILIES:
        for res_id, row in sorted(table.items()):
            named.add(res_id)
            art = item_art(res_id)
            # `""` counts as the icon field, the same way `item_art`
            # reads it: an item that is known and has no art yet. Miss
            # that and its row looks SHAPED, and its name comes out as
            # a group and a tier that were never there.
            icons = [i for i, f in enumerate(row)
                     if isinstance(f, str)
                     and (f.endswith(".png") or f == "")]
            at = icons[0] if icons else len(row)
            # A shaped row is (group, tier, icon); a named one is
            # (name, icon). Which it is, is how many fields precede
            # the icon.
            shaped = at >= 2
            group = row[0] if shaped else ""
            tier = row[1] if shaped else ""
            name = _shaped_name(family, group, tier) if shaped else row[0]
            amount, where = held.get(res_id, ("", ""))
            table_names[res_id] = name
            # **A RECORDED_ONLY id is not in the known file.** That file
            # says what the program uses; an id kept only so the
            # identification is not lost belongs on the worklist with
            # everything else waiting to be used.
            if res_id in RECORDED_ONLY:
                continue
            known_rows[res_id] = (family, group, tier,
                                  art.rarity if art else "", name,
                                  art.icon if art else "", amount, where)

    # **A name typed into a dump does not promote its row to KNOWN.**
    # What moves an id there is one of the tables in
    # `game_data.constants` naming it, and nothing else -- so a
    # half-finished identification stays out on the worklist.
    used = named - RECORDED_ONLY
    rest = {
        res_id: (where, amount)
        for res_id, (amount, where) in sorted(held.items())
        if res_id not in used
    }

    # An id that has BECOME recorded-only was in this file on the last
    # run, and `write` would keep its row -- blank, because it is no
    # longer among the rows passed in -- forever. It has not left the
    # tables, it has moved to the worklist, so its old row goes with it.
    known_owned = ("res_id", "family", "group", "tier", "rarity", "name",
                   "icon", "amount", "where")
    known_path = OUT / "items_id_known.tsv"
    known_extra, known_kept = read_existing(known_path, known_owned)
    write(known_path, known_owned, known_rows,
          carried=(known_extra, {res_id: cells
                                 for res_id, cells in known_kept.items()
                                 if res_id not in RECORDED_ONLY}))

    # The two unknown dumps share one set of hand-added columns and one
    # pool of hand-typed cells, so a row can cross between them without
    # anything being retyped.
    extra, kept = _shared_tail(OUT / "items_id_unknown.tsv",
                               OUT / "items_id_known_not_in_program.tsv",
                               UNKNOWN_OWNED)
    try:
        at = extra.index(NAME_COLUMN)
    except ValueError:
        at = None
        print(f"no `{NAME_COLUMN}` column yet -- every unnamed id stays in "
              f"items_id_unknown.tsv until one exists")

    def identified(res_id):
        cells = kept.get(res_id, [])
        return at is not None and at < len(cells) and cells[at].strip()

    # **An id a table now names leaves both unknown dumps.** They exist
    # to say what is left to do, and a row for a finished id reads as
    # work outstanding. Its hand-typed cells are PRINTED on the way out
    # rather than dropped silently: they are research, and the place
    # they belong now is a comment beside the id in
    # `game_data/constants.py`.
    promoted = sorted(res_id for res_id in kept if res_id in used
                      and any(c.strip() for c in kept[res_id]))
    for res_id in promoted:
        print(f"  now named by the program, dropping its dump row: "
              f"{res_id}	" + "	".join(kept[res_id]))
    for res_id in [r for r in kept if r in used]:
        del kept[res_id]

    # A table's name fills the worklist's `Name` for a recorded-only
    # id, so the file reads the same whether the identification came
    # from a table or from a hand.
    if at is not None:
        for res_id in RECORDED_ONLY & set(rest):
            cells = kept.setdefault(res_id, [""] * len(extra))
            if not cells[at].strip():
                cells[at] = table_names.get(res_id, "")

    named_ids = {r for r in set(rest) | set(kept) if identified(r)}
    write(OUT / "items_id_known_not_in_program.tsv", UNKNOWN_OWNED,
          {r: v for r, v in rest.items() if r in named_ids},
          carried=(extra, {r: c for r, c in kept.items() if r in named_ids}))
    write(OUT / "items_id_unknown.tsv", UNKNOWN_OWNED,
          {r: v for r, v in rest.items() if r not in named_ids},
          carried=(extra, {r: c for r, c in kept.items()
                           if r not in named_ids}))


def _shared_tail(first, second, owned):
    """One (extra columns, {res_id: cells}) pair across two dumps.

    The unknown dumps hold the same hand-added columns, because a row
    crossing between them has to arrive with its cells lined up. The
    FIRST file is the shape both take; the second disagreeing is a
    refusal rather than a guess, since writing one file's cells under
    the other's headings puts every hand-typed value in the wrong
    column.
    """
    extra, kept = read_existing(first, owned)
    other_extra, other_kept = read_existing(second, owned)
    if extra and other_extra and other_extra != extra:
        raise SystemExit(
            f"{first.name} and {second.name} carry different hand-added "
            f"columns ({extra} vs {other_extra}). A row moving between "
            f"them would land under the wrong headings. Reconcile them "
            f"first.")
    extra = extra or other_extra
    merged = dict(other_kept)
    merged.update(kept)
    width = len(extra)
    return extra, {res_id: (cells + [""] * width)[:width]
                   for res_id, cells in merged.items()}


def _shaped_name(family, group, tier):
    """What the game calls one shaped row, from its family and tier."""
    if family == "Growth Stone":
        return f"{tier} Growth Stone of {group}"
    if family == "EXP material":
        return f"{tier} {'Battle Memory' if group == 'Combatant' else 'Support Data'}"
    return f"{tier} {group} {'Manual' if 'Manual' in family else 'Certificate'}"


if __name__ == "__main__":
    main()
