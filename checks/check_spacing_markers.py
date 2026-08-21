"""Spacing rule names must agree across the three places that spell them.

The rules table in `docs/ui_spacing.md` is canonical. `RULE_*` constants
in `ui/spacing_registry.py` copy it, and every `# spacing: <rule>`
comment in the widget code copies it again. A comment cannot import a
constant, so nothing enforces the agreement.

A name that drifts on any side does not fail -- it silently splits a
grep into two partial answers, and a partial answer looks like a
complete one. That is the failure this check exists to catch, and it is
the only one here that needs no game data at all.
"""

import glob
import io
import re

from ._harness import REPO_ROOT, SOURCE_ROOT

NAME = "spacing markers"

MARKER = re.compile(r"#\s*spacing:\s*(.+?)\s*$", re.M)
PREFIXES = ("TBD -- ", "exception -- ", "out of scope -- ",
            "unique -- ")

# Headings this check reads the doc through. Kept here so a rename shows
# up as one edit rather than four scattered string literals.
RULES_HEADING = "## The rules"
UNRULED_HEADING = "## The unruled rows, as a table"
END_HEADING = "## Checking spacing"


class DocLayoutChanged(Exception):
    """A heading this check navigates by is gone from ui_spacing.md."""

    def __str__(self):
        return (f"docs/ui_spacing.md no longer contains the heading "
                f"{self.args[0]!r}. Update the *_HEADING constants in "
                f"checks/check_spacing_markers.py to match the doc.")


def _doc_rules():
    """(canonical rule names, descriptions of the rows not yet ruled on).

    Each is scoped to its own SECTION rather than matched across the whole
    document. The unruled table also ends rows with a backtick-quoted name
    -- the rule that row is expected to become -- and a document-wide
    match reads those as canonical rules missing a `RULE_` constant, which
    they are, legitimately, right up until they are ruled.
    """
    doc = io.open(REPO_ROOT / "docs" / "ui_spacing.md", encoding="utf-8").read()

    rules_block = _between(doc, RULES_HEADING, UNRULED_HEADING)
    rules = _marker_column(rules_block)

    tbd_block = _between(doc, UNRULED_HEADING, END_HEADING)
    # Columns are hand-aligned with padding, so a cell needs stripping
    # before it can be compared against a marker in the code.
    tbd = {cell.strip() for cell in
           re.findall(r"^\|([^|]+)\|", tbd_block, re.M)}
    tbd -= {"Description", ""}
    tbd = {t for t in tbd if set(t) - set("- ")}     # drop the ruler row
    return rules, tbd


def _marker_column(block):
    """The Marker cells of the rules table, and of no other table.

    Anchored on the table's own header row rather than on "any row whose
    last cell is backticked" -- the section holds other tables (the font
    inventory names modules that way), and matching by shape swept those
    up as rules with no `RULE_` constant.
    """
    lines = block.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^\|\s*Gap\s*\|.*\|\s*Marker\s*\|$", line):
            rows = []
            for row in lines[i + 2:]:            # skip the ruler row
                if not row.startswith("|"):
                    break
                cell = re.match(r"^\|.*\|\s*`([^`]+)`\s*\|$", row)
                if cell:
                    rows.append(cell.group(1))
            return rows
    raise DocLayoutChanged("the rules table header (| Gap | ... | Marker |)")


def _between(doc, start, end):
    """Text between two headings, or a DocLayoutChanged naming the missing one.

    Split-and-index would raise IndexError here, which reads as the check
    being broken rather than as the document having been reorganised --
    and reorganising it is a normal thing to do.
    """
    for heading in (start, end):
        if heading not in doc:
            raise DocLayoutChanged(heading)
    return doc.split(start)[1].split(end)[0]


def run():
    failures = []
    try:
        rules, doc_tbd = _doc_rules()
    except DocLayoutChanged as e:
        return [str(e)]

    reg = io.open(SOURCE_ROOT / "ui" / "spacing_registry.py",
                  encoding="utf-8").read()
    consts = set(re.findall(r'^RULE_\w+ = "([^"]+)"', reg, re.M))

    for rule in rules:
        if rule not in consts:
            failures.append(
                f"rule {rule!r} is in the docs table but has no RULE_ constant"
            )
    for const in consts:
        if const not in rules:
            failures.append(
                f"RULE_ constant {const!r} is not a row in the docs table"
            )

    used, code_tbd = set(), set()
    for path in glob.glob(str(SOURCE_ROOT / "**" / "*.py"), recursive=True):
        if "__pycache__" in path or "_capture_addon" in path:
            continue
        text = io.open(path, encoding="utf-8", errors="replace").read()
        # Matched per line, deliberately. A marker naming a rule or a TBD
        # must fit on ONE line; joining continuation comments to find a
        # longer one also welds unrelated prose onto the end of a
        # perfectly good marker and then reports it as a typo. Only the
        # `exception` and `out of scope` forms wrap, and their text is
        # free prose that nothing is matched against.
        for m in MARKER.finditer(text):
            body = m.group(1)
            if body.startswith("TBD -- "):
                code_tbd.add(body[len("TBD -- "):])
            elif body.startswith(PREFIXES[1:]):
                # exception / out of scope / unique. None of these name a
                # rule -- `unique` exists precisely for a deliberate value
                # that no rule covers and that is not an exception to one
                # either -- so their free text is never matched against
                # anything.
                continue
            elif body.startswith("<rule>"):
                continue          # the convention's own description
            else:
                used.add(body)

    for name in sorted(used - set(rules)):
        failures.append(
            f"code marker {name!r} matches no rule in the docs table -- "
            f"a typo here splits grep into two partial answers"
        )
    for name in sorted(code_tbd - doc_tbd):
        failures.append(
            f"TBD marker {name!r} is in the code but has no row in "
            f"{UNRULED_HEADING!r}"
        )
    for name in sorted(doc_tbd - code_tbd):
        failures.append(
            f"TBD row {name!r} is in the docs but no code site carries it"
        )
    return failures
