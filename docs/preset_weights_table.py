"""`docs/preset_weights.tsv`: every shipped Gear Score preset's weights
as a table, one row per preset, to read and sort as the maintainer
likes. The shipped presets themselves stay in
`Vribbels/default_settings/presets.json`; this mirrors them.

    python docs/preset_weights_table.py           # warn where they differ
    python docs/preset_weights_table.py --fill    # bring the table level

`--fill` writes every shipped preset's weights into the table: rows it
holds are updated where they stand, missing ones are appended at the
end. A row for a preset that no longer ships is left for the maintainer
to delete, and warned about. `docs/preset_weights.py`'s `--new` and
`--write` call `update` for the presets they write, and `zCreate
exe.bat` runs the warning first thing. Always exits 0: a reminder, not
a gate.

**Rows and columns are found by name, never by position**, so the
maintainer may reorder either; a write keeps the order it finds. The
first column is the preset's name, headed `PRESET_HEADER`.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TABLE = HERE / "preset_weights.tsv"
SHIPPED = HERE.parent / "Vribbels" / "default_settings" / "presets.json"

PRESET_HEADER = "Preset"
# (header, the key presets.json uses), in the order a new table takes.
COLUMNS = [
    ("ATK Flat", "Flat ATK"),
    ("ATK%", "ATK%"),
    ("DEF Flat", "Flat DEF"),
    ("DEF%", "DEF%"),
    ("Crit%", "CRate"),
    ("CDMG", "CDmg"),
    ("Extra%", "Extra DMG%"),
    ("DoT%", "DoT%"),
    ("Ego", "Ego"),
    ("HP%", "HP%"),
    ("HP Flat", "Flat HP"),
]
KEY_OF = {h.casefold(): k for h, k in COLUMNS}
HEADER_OF = {k: h for h, k in COLUMNS}

ORANGE = "\x1b[38;5;208m"
GREEN = "\x1b[92m"
RESET = "\x1b[0m"


def fmt(value):
    """A weight as the table writes it: 1 for 1.0, 0.077 for 0.077."""
    return "%g" % value


def same(a, b):
    return abs(a - b) <= 1e-9 + 1e-6 * max(abs(a), abs(b))


def read(path=TABLE):
    """(header, rows, problems). `header` is the column headings as
    found; `rows` is [(preset, {key: float or None})] in the file's
    order, None where a cell is blank or not a number."""
    if not Path(path).exists():
        return [PRESET_HEADER] + [h for h, _k in COLUMNS], [], [
            "%s does not exist" % Path(path).name]
    # utf-8-sig and splitlines: a spreadsheet's save adds a BOM or CRLF.
    lines = Path(path).read_bytes().decode("utf-8-sig").splitlines()
    lines = [ln for ln in lines if ln.strip()]
    if not lines:
        return [PRESET_HEADER] + [h for h, _k in COLUMNS], [], [
            "%s is empty" % Path(path).name]
    header = [c.strip() for c in lines[0].split("\t")]
    problems = []
    if header[0].casefold() != PRESET_HEADER.casefold():
        problems.append("the first column is headed %r, not %r"
                        % (header[0], PRESET_HEADER))
    keys = [KEY_OF.get(h.casefold()) for h in header[1:]]
    for h, k in zip(header[1:], keys, strict=True):
        if k is None:
            problems.append("column %r is not a stat the table knows "
                            "(%s)" % (h, ", ".join(h_ for h_, _ in COLUMNS)))
    for h, k in COLUMNS:
        if k not in keys:
            problems.append("no %r column" % h)
    rows = []
    for ln in lines[1:]:
        cells = [c.strip() for c in ln.split("\t")]
        weights = {}
        # Padded: a spreadsheet drops a row's trailing empty cells.
        for k, cell in zip(keys, cells[1:] + [""] * len(keys),
                           strict=False):
            if k is None:
                continue
            try:
                weights[k] = float(cell)
            except ValueError:
                weights[k] = None
        rows.append((cells[0], weights))
    return header, rows, problems


def write(header, rows, path=TABLE):
    """Write `rows` under `header`, in their order. Columns the table
    does not know are kept, blank."""
    keys = [KEY_OF.get(h.casefold()) for h in header[1:]]
    out = ["\t".join(header)]
    for preset, weights in rows:
        cells = [preset]
        for k in keys:
            v = weights.get(k) if k else None
            cells.append("" if v is None else fmt(v))
        out.append("\t".join(cells))
    Path(path).write_bytes(("\n".join(out) + "\n").encode("utf-8"))


def update(presets, path=TABLE):
    """Write `presets` ({preset: {key: weight}}) into the table: a row
    it holds is updated where it stands, a new one appended. Returns
    the names appended."""
    header, rows, _problems = read(path)
    known = {h.casefold() for h in header}
    header = header + [h for h, _k in COLUMNS if h.casefold() not in known]
    index = {name: i for i, (name, _w) in enumerate(rows)}
    added = []
    for name, weights in presets.items():
        row = {k: float(v) for k, v in weights.items()
               if isinstance(v, (int, float))}
        if name in index:
            rows[index[name]] = (name, row)
        else:
            rows.append((name, row))
            added.append(name)
    write(header, rows, path)
    return added


def shipped(path=SHIPPED):
    return json.loads(Path(path).read_text(encoding="utf-8"))["presets"]


def differences(table=TABLE, presets_path=SHIPPED):
    """[line] for every way the table and the shipped presets differ."""
    _header, rows, out = read(table)
    presets = shipped(presets_path)
    seen = {}
    for name, weights in rows:
        if name in seen:
            out.append("%r has two rows" % name)
            continue
        seen[name] = weights
        if name not in presets:
            out.append("%r is in the table but not shipped" % name)
            continue
        for h, k in COLUMNS:
            if k not in weights:
                continue
            mine, theirs = weights[k], presets[name].get(k, 0.0)
            if mine is None:
                out.append("%s %s: blank or not a number, shipped %s"
                           % (name, h, fmt(theirs)))
            elif not same(mine, theirs):
                out.append("%s %s: table %s, shipped %s"
                           % (name, h, fmt(mine), fmt(theirs)))
    for name in presets:
        if name not in seen:
            out.append("%r ships but has no row in the table" % name)
    return out


def main(argv):
    if "--fill" in argv:
        added = update(shipped())
        print("Table written: %d presets, %d appended%s" % (
            len(shipped()), len(added),
            (": " + ", ".join(added)) if added else ""))
    found = differences()
    if found:
        print(ORANGE + "docs/preset_weights.tsv differs from the shipped "
              "presets (default_settings/presets.json):" + RESET)
        for line in found:
            print(ORANGE + "   " + line + RESET)
        print(ORANGE + "   To make the table follow the shipped presets: "
              "python docs/preset_weights_table.py --fill" + RESET)
    else:
        print(GREEN + "docs/preset_weights.tsv matches the shipped "
              "presets." + RESET)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
