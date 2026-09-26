"""Every path an instruction file or a doc names still exists.

`CLAUDE.md`, `.claude/rules/*.md` and `.claude/skills/*/SKILL.md` tell
Claude what to run and where to look, and `docs/*.md` are what they
point to. All of them cite paths, and a rename leaves the citation
pointing at nothing.

**A rule or a skill fails more quietly than a doc.** A doc is read while
working in the area it covers, so a dead path in it surfaces on the next
visit. A path-scoped rule loads only when a file it covers is read, and
a skill loads only when its description triggers -- so a stale one sits
unread until the moment it is needed, which is the worst moment to find
out. The `paths:` globs have the same shape of failure: a rule scoped to
a directory that no longer exists never loads at all, and nothing says
so. A doc surfaces its dead path sooner, but only to a reader who
tries to follow it, and nothing else ever did.

What is checked, per file:

* every backticked token that looks like a path or a filename resolves,
  relative to the repo root or to `Vribbels/`; a bare filename is
  resolved by searching the tree, so a rename is caught wherever the
  file moved to;
* a rule's `paths:` globs each match at least one file;
* a skill carries `name` and `description` frontmatter, which is what
  the model matches a task against.

Identifiers are NOT checked. Function and constant names move for
reasons a spelling check cannot follow, and the false alarms would
teach the reader to skip the output.
"""

import re
from pathlib import Path

from ._harness import REPO_ROOT, Skip

NAME = "instruction files name things that exist"

SOURCE = REPO_ROOT / "Vribbels"

# Directories a citation never points into, and that make the basename
# search slow and ambiguous when walked.
SKIPPED_DIRS = {".git", "__pycache__", "_tmp", "snapshots", "build",
                "dist", "node_modules", ".venv", "venv"}

# A backticked token is tested when it looks like a path: it carries a
# separator, or it ends in one of these. Anything else is prose or an
# identifier, and identifiers are out of scope.
FILE_SUFFIXES = (".py", ".md", ".bat", ".json", ".tsv", ".spec", ".txt")

# Frontmatter keys a skill needs. `description` is what a task is
# matched against, so a skill without one never triggers.
SKILL_KEYS = ("name", "description")

BACKTICKED = re.compile(r"`([^`\n]+)`")

# Trailing punctuation that belongs to the sentence, not the path.
# Stripped from the END only: a leading dot is part of the name
# (`.claude/rules/`, `.defaults_sync.json`) and stripping it turns a
# real path into one that resolves nowhere.
TRIM = ".,;:)\"'"

# Paths that are cited and legitimately absent, with the reason. Each
# is a file something WRITES rather than one the repo ships.
EXPECTED_ABSENT = {
    "plan.md",                 # created only while a task is being planned
    ".defaults_sync.json",     # written beside the settings at runtime
    "paused_task.md",          # written to be deleted
    "RELEASE_NOTES.md",        # assembled at release
    "_tmp/skill_notes.md",     # the improvement queue, written as
                               # lessons land and cleared on review
    "_capture_addon.py",       # generated into `snapshots/` per capture
    "captured.json",           # the Gacha History's own files, written
    "imported.json",           # into `snapshots/gacha_history/`
    "memory_fragments_*.json", # a capture's snapshots
    "config.json",             # a legacy file old versions left behind
}

# Folders the PROGRAM writes, not the repo: a clone has neither, so a
# citation into them names what a run creates.
RUNTIME_DIRS = ("settings/", "snapshots/")


def _instruction_files():
    """(label, path) for every file this check reads."""
    found = []
    root_md = REPO_ROOT / "CLAUDE.md"
    if root_md.exists():
        found.append(("CLAUDE.md", root_md))
    for path in sorted((REPO_ROOT / "docs").glob("*.md")):
        found.append((f"docs/{path.name}", path))
    for path in sorted((REPO_ROOT / ".claude" / "rules").glob("*.md")):
        found.append((f".claude/rules/{path.name}", path))
    for path in sorted(
            (REPO_ROOT / ".claude" / "skills").glob("*/SKILL.md")):
        found.append((f".claude/skills/{path.parent.name}/SKILL.md", path))
    return found


def _walk():
    """Every file in the repo worth matching a bare name against."""
    out = {}
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIPPED_DIRS for part in path.parts):
            continue
        out.setdefault(path.name, []).append(path)
    return out


def _looks_like_a_path(token: str) -> bool:
    """A citation to test, as against prose, a command or a repo slug.

    The end of the token decides: a directory's trailing slash or a
    known extension. Without that test `Vorbroker/Vribbels-CZN-Optimizer`
    reads as a path, and it is a GitHub slug.
    """
    if token.startswith("~") or ":" in token:
        return False                     # outside the repo, or a URL
    if "<" in token or token in FILE_SUFFIXES:
        return False                     # a placeholder, or a bare
        # extension like `.py`
    if token.split("Vribbels/", 1)[-1].startswith(RUNTIME_DIRS):
        return False                     # made by a run, not shipped
    if " " in token and not token.endswith(".bat"):
        return False                     # a command line; only the
        # launchers have spaces in their names
    return token.endswith("/") or token.endswith(FILE_SUFFIXES)


def _resolves(token: str, by_name) -> bool:
    """Does this citation point at something on disk?"""
    bare = token.rstrip("/")
    for base in (REPO_ROOT, SOURCE):
        if (base / bare).exists():
            return True
    # A brace set names several files at once: `{capture,setup}_tab.py`.
    if "{" in bare and "}" in bare:
        head, rest = bare.split("{", 1)
        inner, tail = rest.split("}", 1)
        return all(_resolves(head + part + tail, by_name)
                   for part in inner.split(","))
    # A bare filename, cited without its directory. Found anywhere in
    # the tree, it is current; found nowhere, it has been renamed.
    if "/" not in bare and bare in by_name:
        return True
    # A glob in the citation itself, e.g. `game_data/*.py`.
    if any(ch in bare for ch in "*?"):
        for base in (REPO_ROOT, SOURCE):
            try:
                if next(base.glob(bare), None) is not None:
                    return True
            except (ValueError, OSError):
                pass
    return False


def _frontmatter(text: str) -> str:
    """The YAML block at the top of the file, or ''."""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[3:end] if end != -1 else ""


def run():
    files = _instruction_files()
    if not files:
        raise Skip("no CLAUDE.md, rules or skills to read")
    by_name = _walk()
    problems = []

    for label, path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in BACKTICKED.findall(text):
            token = token.strip().rstrip(TRIM).strip()
            if not token or token in EXPECTED_ABSENT:
                continue
            if not _looks_like_a_path(token):
                continue
            if not _resolves(token, by_name):
                problems.append(
                    f"{label} cites `{token}`, which is not in the repo "
                    f"under either the root or `Vribbels/`. An instruction "
                    f"file is read when its subject comes up, so a dead "
                    f"path here surfaces at the moment it was needed.")

        front = _frontmatter(text)
        if label.startswith(".claude/rules/"):
            globs = re.findall(r'^\s*-\s*"?([^"\n]+?)"?\s*$',
                               front.split("paths:", 1)[-1], re.M) \
                if "paths:" in front else []
            for pattern in globs:
                if next(REPO_ROOT.glob(pattern), None) is None:
                    problems.append(
                        f"{label} is scoped to `{pattern}`, which matches "
                        f"no file. A path-scoped rule loads only when a "
                        f"file it covers is read, so this one never loads "
                        f"and nothing reports that.")
        if label.startswith(".claude/skills/"):
            for key in SKILL_KEYS:
                if not re.search(rf"^{key}:\s*\S", front, re.M):
                    problems.append(
                        f"{label} has no `{key}` in its frontmatter. A "
                        f"skill is matched to a task on its name and "
                        f"description; without them it never triggers.")
    return problems
