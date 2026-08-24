"""Spacing rule names must agree across the three places that spell them.

The rules table in `docs/ui_spacing.md` is canonical. `RULE_*` constants
in `ui/spacing_registry.py` copy it, and every `# spacing: <rule>`
comment in the widget code copies it again. A comment cannot import a
constant, so nothing enforces the agreement.

A name that drifts on any side does not fail -- it silently splits a
grep into two partial answers, and a partial answer looks like a
complete one. That is the failure this check exists to catch.

It also checks the SUFFIX each marker carries:

    # spacing: <rule> -- <elements> <orientation>

The elements come from a fixed vocabulary, also read out of the doc, so
that `grep "checkbox"` finds every checkbox gap rather than the subset
that happened to spell it that way. Free text would decay into
`checkbox` / `checkbutton` / `cb` and the searchability with it.
"""

import glob
import io
import re

from ._harness import REPO_ROOT, SOURCE_ROOT

NAME = "spacing markers"

MARKER = re.compile(r"#\s*spacing:\s*(.+?)\s*$", re.M)
ORIENTATIONS = ("↔", "↕")          # <-> and up/down

# Headings this check reads the doc through. Kept here so a rename shows
# up as one edit rather than four scattered string literals.
RULES_HEADING = "## The rules"
VOCAB_HEADING = "### The element vocabulary"
UNRULED_HEADING = "## The unruled rows, as a table"
END_HEADING = "## Checking spacing"

# Set to True once every marker carries a suffix. Until then a bare
# marker is accepted, so the conversion can go file by file with this
# check green the whole way.
REQUIRE_SUFFIX = False


class DocLayoutChanged(Exception):
    """A heading this check navigates by is gone from ui_spacing.md."""

    def __str__(self):
        return (f"docs/ui_spacing.md no longer contains the heading "
                f"{self.args[0]!r}. Update the *_HEADING constants in "
                f"checks/check_spacing_markers.py to match the doc.")


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


def _marker_column(block):
    """The Marker cells of the rules table, and of no other table.

    Anchored on the table's own header row rather than on "any row whose
    last cell is backticked" -- the section holds other tables, and
    matching by shape swept those up as rules with no `RULE_` constant.
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


def _vocabulary(doc):
    """The element words, read from the doc's own table."""
    if VOCAB_HEADING not in doc:
        raise DocLayoutChanged(VOCAB_HEADING)
    # Bounded to the ONE table under its heading. Reading as far as the
    # next section swept up the Treeview levers, the clam colour options
    # and the digit table, all of which are first-column-backticked too.
    block = doc.split(VOCAB_HEADING)[1]
    block = re.split(r"^#{2,4} ", block, maxsplit=1, flags=re.M)[0]
    words = set()
    for row in block.splitlines():
        cell = re.match(r"^\|\s*`([^`]+)`\s*\|", row)
        if cell:
            words.add(cell.group(1))
    if not words:
        raise DocLayoutChanged(VOCAB_HEADING + " (no `term` rows found)")
    return words


def _doc_rules():
    """(rule names, unruled descriptions, element vocabulary).

    Each is scoped to its own SECTION rather than matched across the
    whole document. The unruled table also ends rows with a
    backtick-quoted name -- the rule that row is expected to become --
    and a document-wide match reads those as canonical rules missing a
    `RULE_` constant, which they are, legitimately, right up until they
    are ruled.
    """
    doc = io.open(REPO_ROOT / "docs" / "ui_spacing.md", encoding="utf-8").read()

    rules = _marker_column(_between(doc, RULES_HEADING, UNRULED_HEADING))

    tbd_block = _between(doc, UNRULED_HEADING, END_HEADING)
    # Columns are hand-aligned with padding, so a cell needs stripping
    # before it can be compared against a marker in the code.
    tbd = {cell.strip() for cell in
           re.findall(r"^\|([^|]+)\|", tbd_block, re.M)}
    tbd -= {"Description", ""}
    tbd = {t for t in tbd if set(t) - set("- ")}     # drop the ruler row
    return rules, tbd, _vocabulary(doc)


def _split_suffix(body):
    """(rule-or-description, suffix) for one marker body."""
    head, sep, tail = body.partition(" -- ")
    return (head, tail) if sep else (head, "")


def _check_suffix(suffix, vocab, where, failures):
    """The `<elements> <orientation>` half of a marker."""
    if not suffix:
        if REQUIRE_SUFFIX:
            failures.append(
                f"{where} carries no ` -- <elements> <orientation>` suffix. "
                f"Without it the marker says which RULE applies but not to "
                f"WHAT, and splitting that rule later means re-reading "
                f"every site."
            )
        return
    orientation = suffix[-1]
    if orientation not in ORIENTATIONS:
        failures.append(
            f"{where} ends with {orientation!r}, not ↔ or ↕. The "
            f"orientation is written even where the rule's own name "
            f"carries an arrow -- optional means grep returns a partial "
            f"answer that looks complete."
        )
        return
    words = [w.strip() for w in suffix[:-1].split(",")]
    for word in words:
        if not word:
            failures.append(f"{where} has an empty element name.")
        elif word not in vocab:
            failures.append(
                f"{where} names element {word!r}, which is not in the "
                f"vocabulary in docs/ui_spacing.md. Free spellings split "
                f"one grep into several; add the word to that table if it "
                f"is genuinely a new kind of element."
            )


def run():
    failures = []
    try:
        rules, doc_tbd, vocab = _doc_rules()
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

    used, code_tbd, code_exceptions = set(), set(), set()
    for path in glob.glob(str(SOURCE_ROOT / "**" / "*.py"), recursive=True):
        if "__pycache__" in path or "_capture_addon" in path:
            continue
        rel = path.replace(str(SOURCE_ROOT), "").lstrip("\\/")
        text = io.open(path, encoding="utf-8", errors="replace").read()
        # Matched per line, deliberately. A marker naming a rule or a TBD
        # must fit on ONE line; joining continuation comments to find a
        # longer one also welds unrelated prose onto the end of a
        # perfectly good marker and then reports it as a typo. Only the
        # `exception` and `out of scope` forms wrap, and their text is
        # free prose that nothing is matched against.
        for m in MARKER.finditer(text):
            body = m.group(1)
            line = text[:m.start()].count("\n") + 1
            where = f"{rel}:{line}"
            if body.startswith("TBD -- "):
                code_tbd.add(body[len("TBD -- "):])
            elif body.startswith("exception -- "):
                # An exception DOES name a rule -- the one it excepts --
                # so that grepping a rule surfaces its own exceptions.
                rule, suffix = _split_suffix(body[len("exception -- "):])
                code_exceptions.add(rule)
                _check_suffix(suffix, vocab, where, failures)
            elif body.startswith("unique -- "):
                # No rule to name, but the elements and orientation are
                # written the same way so one grep finds every gap of a
                # kind, ruled or not.
                # A body with no second ` -- ` is still in the old form,
                # which REQUIRE_SUFFIX decides on.
                rest = body[len("unique -- "):]
                head, sep, _what = rest.partition(" -- ")
                _check_suffix(head.strip() if sep else "", vocab, where,
                              failures)
            elif body.startswith("out of scope -- "):
                continue
            elif body.startswith("<rule>") or body.startswith("<elements>"):
                continue          # the convention's own description
            else:
                rule, suffix = _split_suffix(body)
                used.add(rule)
                _check_suffix(suffix, vocab, where, failures)

    for name in sorted(used - set(rules)):
        failures.append(
            f"code marker {name!r} matches no rule in the docs table -- "
            f"a typo here splits grep into two partial answers"
        )
    for name in sorted(code_exceptions - set(rules)):
        failures.append(
            f"exception marker {name!r} names no rule in the docs table. "
            f"An exception has to name the rule it excepts, in the Marker "
            f"column's spelling -- and on ONE line, or the name is "
            f"truncated at the wrap and greps for it find nothing."
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
