"""Every section a doc or a code comment cites by name is there.

The docs point at each other's sections by name -- `` `file.md`,
*Heading* ``, or `*Heading*, below` within a file -- and so do the
code's comments and docstrings. Nothing else follows those names: a
heading renamed, or a bold lead reworded, leaves every citation of it
pointing at nothing, in files the edit never touched, and a reader
following one finds no such section.

`docs/doc_sweeps.py`'s `xrefs` resolves each against the file it names:
its headings, its bold leads and its table rows' first cells. This holds
the repository to it, and holds the resolver to a corpus of its own
built to exercise each rule.
"""

import sys

from ._harness import REPO_ROOT

# `docs/` on the path at import, so the fault runner finds the module
# its faults patch under the same name `run` imports.
if str(REPO_ROOT / "docs") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "docs"))

NAME = "every section a doc or a comment cites is there"

# A corpus of the check's own: each citation is answered or not by
# design, so a resolver that stops telling them apart says so.
CORPUS = {
    "docs/a.md": (
        "# A\n\n"
        "## Heading here\n\n"
        "**A bold lead** opens this paragraph.\n\n"
        "| A row name | what |\n| --- | --- |\n\n"
        "## The `x` key\n\n"
        "See *Heading here*, below, and *Gone away*, above.\n"
        "An example in a span, `*Not a citation*, below`.\n"
        "A span in a heading: *The `x` key*, above, *The `y` key*, above.\n"),
    "docs/b.md": (
        "# B\n\n"
        "Cites `a.md`, *Heading here*, and `a.md`, *A bold lead*, and "
        "`a.md`, *A row name*, and `a.md`, *Renamed since*.\n"),
    "Vribbels/c.py": (
        '"""A docstring citing `a.md`, *Heading here*."""\n\n'
        "# A comment citing `a.md`, *No such section*.\n"
        "x = 1\n"),
}
KINDS = {"docs/a.md": "prose", "docs/b.md": "prose", "Vribbels/c.py": "code"}

# (path, cited) the resolver must report, and nothing else.
WANTED = {
    ("docs/a.md", "Gone away"),
    ("docs/a.md", "The `y` key"),
    ("docs/b.md", "Renamed since"),
    ("Vribbels/c.py", "No such section"),
}


def _corpus(sweeps):
    """What the resolver reports of the check's own corpus."""
    return {(rel, cited) for rel, _n, _what, cited in
            sweeps.xrefs(files=KINDS, read=CORPUS.__getitem__)}


def run():
    import doc_sweeps as sweeps
    out = []
    got = _corpus(sweeps)
    for rel, cited in sorted(WANTED - got):
        out.append(f"the resolver missed {rel}'s citation of *{cited}*, "
                   f"which nothing in its file answers: a renamed heading "
                   f"would go unreported (`doc_sweeps.xrefs`).")
    for rel, cited in sorted(got - WANTED):
        out.append(f"the resolver reported {rel}'s citation of *{cited}*, "
                   f"which a heading, a bold lead or a table row answers, "
                   f"or which is an example in a code span "
                   f"(`doc_sweeps.anchors`).")
    for rel, number, what, cited in sweeps.xrefs():
        out.append(f"{rel}:{number} cites *{cited}*: {what}. A heading "
                   f"renamed, or a citation mistyped; point it at the "
                   f"section's name as it stands.")
    return out


SW = "doc_sweeps"

FAULTS = [
    ("a missing section passes",
     f"{SW}:xrefs",
     "        return any(name == want or name.startswith(want)\n"
     "                   for name in names(rel))",
     "        return True",
     "would go unreported"),
    ("bold leads not read as anchors",
     f"{SW}:anchors",
     "        out.update(_cited_name(m) for m in re.findall("
     "r\"\\*\\*(.+?)\\*\\*\", line))\n",
     "",
     "A bold lead"),
    ("table rows not read as anchors",
     f"{SW}:anchors",
     "        if cell:\n            out.add(_cited_name(cell.group(1)))\n",
     "",
     "A row name"),
    ("an example in a code span taken for a citation",
     f"{SW}:_example",
     "    return \"\" if text.startswith(\"``\") or \"*\" in text else text",
     "    return text",
     "Not a citation"),
    ("every code span dropped, a heading's own among them",
     f"{SW}:_example",
     "    return \"\" if text.startswith(\"``\") or \"*\" in text else text",
     "    return \"\"",
     "The `y` key"),
    ("the code's comments not read",
     f"{SW}:xrefs",
     "        lines = list(_code(text)) if kind == \"code\" else \\\n",
     "        lines = [] if kind == \"code\" else \\\n",
     "No such section"),
]
