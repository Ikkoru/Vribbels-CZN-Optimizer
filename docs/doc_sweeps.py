"""The doc audit's sweeps: every line a pattern in the kit's
`craft:doc-audit` sweep table finds, for a person to judge.

    python docs/doc_sweeps.py                    lines added since the last audit
    python docs/doc_sweeps.py --since <commit>   lines added since a commit
    python docs/doc_sweeps.py --all              every line in scope
    python docs/doc_sweeps.py --sweep dense,idents   only those sweeps

The scope is `.claude/overlays/doc-audit.md`'s: the prose of `docs/`,
`.claude/` and `CLAUDE.md`, the unreleased section of `CHANGELOG.md`,
and the comments and docstrings of `Vribbels/` and `checks/`; never
`past_plans/`. The last audit is the newest commit whose subject starts
`Doc audit`. An added line is read in its file, so a fenced block or a
docstring is known for what it is, and a file git does not track yet
counts as added whole.

A hit is a question, not a verdict: the overlay's false positives match
these patterns too. The CHANGELOG's narration hits are a group of their
own, since there an entry saying what the program does now is right.

`privacy` reads every file git tracks or would add, whatever `--since`
says, for what a push would publish about this machine and its user: a
drive-letter path, the user's folder, the machine's name, an e-mail
address, the game account's id. Run it before archiving a plan into
`past_plans/`, which makes a gitignored file public. It takes those from the machine and the newest
snapshot as it runs, so this file names nothing private.
"""

import argparse
import ast
import glob
import io
import json
import os
import re
import socket
import subprocess
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = ROOT / "Vribbels" / "snapshots"

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# Written by a tool, not by hand: their comments are its.
GENERATED = {"Vribbels/game_data/from_client.py"}

LINE_SWEEPS = {
    "narration": re.compile(
        r"\b(used to|previously|formerly|no longer|renamed from|the old "
        r"|an earlier attempt|for months|went unread|we now)\b"
        r"|\bnow (does|reads|is|has|shows|comes|names|counts|takes|says"
        r"|gives|keeps|holds|runs|lists)\b", re.I),
    "stale-output": re.compile(
        r"\b\d[\d,]*\s+(captured|snapshots?|rows?|readings?|files?"
        r"|so far|ever)\b|\b\d+\s+of\s+the\b"
        r"|(?<![\w/.:\\-])\d+/\d+(?![\w/.%:-])", re.I),
    "stale-status": re.compile(
        r"\bnot pushed\b|\bis built\b|\blocal branch\b|\bhandoff\b", re.I),
    "dated": re.compile(r"\(updated \d{4}-\d\d-\d\d\)"),
    "unfollowable": re.compile(
        r"\bthe (second|third|fourth|fifth|first \d+|first (two|three|four))"
        r"\b(?!\s+(\w+\s+)?(row|column|line|step|item|entry|bullet|table"
        r"|section|part|half|of|in)\b)"
        r"|\bsee `[^`]+\.md`(?!\s*[,(:\u00a7]| \*| section)", re.I),
    "mirrored": re.compile(
        r"\bstored as .+ in\b|\bsingle source of truth\b"
        r"|\bthis table is for documentation\b", re.I),
}
# A heading that names nothing. The shape with a comma or "and" is one
# the overlay lists as false here: its headings are cited by their words.
HEADING = re.compile(r"^#+ (What|Why|Where|How|Which|When)\b")
SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z`*(\[])")
DENSE_WORDS = 40
TOKEN = re.compile(r"`([^`\s]+)`")
CODE_LIKE = re.compile(r"^[A-Za-z_][\w.]*$")
ALL = ["privacy", *LINE_SWEEPS, "dense", "headings", "emphasis", "idents"]


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          check=True).stdout


def kind_of(rel):
    """How a file is read: "prose", "changelog", "code", or None."""
    if rel.startswith("past_plans/") or rel in GENERATED:
        return None
    if rel == "CHANGELOG.md":
        return "changelog"
    if rel == "CLAUDE.md" or (rel.endswith(".md")
                              and rel.startswith(("docs/", ".claude/"))):
        return "prose"
    if rel.endswith(".py") and rel.startswith(("Vribbels/", "checks/")) \
            and not rel.startswith("Vribbels/snapshots/"):
        return "code"
    return None


def last_audit():
    found = git("log", "--grep", "^Doc audit", "-1", "--format=%H").strip()
    if not found:
        raise SystemExit("no commit's subject starts `Doc audit`: give "
                         "--since")
    return found


def added(base):
    """{path: line numbers added since `base`, working tree included},
    None for a file added whole."""
    out = {}
    path = None
    for raw in git("diff", "-U0", base, "--", ".").splitlines():
        if raw.startswith("+++ "):
            path = raw[6:] if raw.startswith("+++ b/") else None
            continue
        hunk = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", raw)
        if hunk and path:
            start, count = int(hunk.group(1)), int(hunk.group(2) or 1)
            out.setdefault(path, set()).update(range(start, start + count))
    for rel in git("ls-files", "--others", "--exclude-standard").splitlines():
        out[rel] = None
    return out


def in_scope(only=None):
    """{path: its kind}, every file the sweeps read; those in `only`
    alone where given."""
    files = git("ls-files").splitlines() + \
        git("ls-files", "--others", "--exclude-standard").splitlines()
    out = {}
    for rel in files:
        kind = kind_of(rel)
        if kind and (only is None or rel in only) and (ROOT / rel).exists():
            out[rel] = kind
    return out


def _markdown(text, changelog=False):
    """(line number, line) outside fenced blocks; for the CHANGELOG, its
    unreleased section alone."""
    fenced, inside = False, not changelog
    for number, line in enumerate(text.splitlines(), 1):
        if changelog and line.startswith("## ["):
            inside = "unreleased" in line.lower()
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if inside and not fenced:
            yield number, line


def _code(text):
    """(line number, prose) of every comment and docstring line."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    lines = text.splitlines()
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) \
                    and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                docs.update(range(first.lineno, first.end_lineno + 1))
    comments = {}
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT:
                comments[token.start[0]] = token.string.lstrip("#").strip()
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    for number in sorted(docs | set(comments)):
        if number in comments:
            yield number, comments[number]
        else:
            yield number, lines[number - 1].strip().strip("\"'")


def lines_of(rel, kind):
    text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    if kind == "code":
        return list(_code(text))
    return list(_markdown(text, changelog=kind == "changelog"))


def _dense(line):
    if line.lstrip().startswith(("|", "#")):
        return None
    for sentence in SENTENCE.split(line):
        words = len(sentence.split())
        marks = (sentence.count("\u2014") + sentence.count(";")
                 + sentence.count(" -- "))
        if words > DENSE_WORDS or marks >= 2:
            return f"{words} words, {marks} dashes or semicolons"
    return None


def _emphasis(lines):
    bold = sum(1 for _, line in lines
               if line.lstrip("-*0123456789. ").startswith("**")
               or line.lstrip().startswith("- **"))
    heads = sum(1 for _, line in lines if line.startswith("#"))
    if bold >= 6 and bold > max(heads, 1) * 1.5:
        return f"{bold} lines open in bold against {heads} headings"
    return None


def _words():
    """Every name the source, the scripts and the wire catalogue hold."""
    corpus = []
    for base in ("Vribbels", "checks", "docs"):
        for path in (ROOT / base).rglob("*"):
            if path.suffix in (".py", ".bat", ".cmd", ".tsv") \
                    and "snapshots" not in path.parts \
                    and "build_tcl" not in path.parts:
                corpus.append(path.read_text(encoding="utf-8",
                                             errors="replace"))
    catalogue = ROOT / "Vribbels" / "settings" / "wire_catalogue.json"
    if catalogue.exists():
        corpus.append(catalogue.read_text(encoding="utf-8", errors="replace"))
    return set(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", "\n".join(corpus)))


def _unresolved(line, words):
    out = []
    for token in TOKEN.findall(line):
        token = token.rstrip("()")
        if not CODE_LIKE.match(token) or token.endswith(
                (".py", ".md", ".json", ".tsv", ".bat")):
            continue
        pieces = [p for p in token.split(".") if p]
        name = pieces[-1] if pieces else token
        code_like = ("_" in name.strip("_")
                     or re.search(r"[a-z][A-Z]", name) or len(pieces) > 1)
        if code_like and not (name.isupper() and "_" not in name) \
                and name not in words:
            out.append(token)
    return out


def privacy_patterns():
    """[(what, pattern)] for what this machine and its user would show."""
    home = Path.home().name
    patterns = [
        ("a drive-letter path", re.compile(r"(?<![\w/\\])[A-Za-z]:[\\/]"
                                           r"(?![\\/])")),
        ("the user's folder", re.compile(
            r"Users[\\/]+" + re.escape(home) + r"\b", re.I)),
        ("an e-mail address", re.compile(
            r"[\w.+-]+@[\w-]+(\.[\w-]+)*\.[A-Za-z]{2,}")),
    ]
    host = socket.gethostname()
    if host and len(host) > 3:
        patterns.append(("the machine's name",
                         re.compile(r"\b" + re.escape(host) + r"\b", re.I)))
    ids = set()
    snaps = glob.glob(str(SNAPSHOTS / "memory_fragments_*.json"))
    if snaps:
        try:
            data = json.loads(Path(max(snaps, key=os.path.getmtime))
                              .read_text(encoding="utf-8"))
            for key in ("items", "piece_items"):
                for item in (data.get("inventory") or {}).get(key) or ():
                    if isinstance(item, dict) and item.get("user_id"):
                        ids.add(str(item["user_id"]))
        except (OSError, ValueError, AttributeError):
            pass
    for account in sorted(ids):
        patterns.append(("the game account's id",
                         re.compile(re.escape(account))))
    return patterns


def privacy():
    """(path, line, what, text) for the private hits in every file a
    commit would carry: those git tracks, and those it would add."""
    patterns = privacy_patterns()
    files = git("ls-files").splitlines() + \
        git("ls-files", "--others", "--exclude-standard").splitlines()
    for rel in files:
        path = ROOT / rel
        try:
            if path.stat().st_size > 5_000_000:
                continue
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for what, pattern in patterns:
                if pattern.search(line):
                    yield rel, number, what, line.strip()


def sweep(names, since=None, every=False):
    """{sweep: [(path, line, note, text)]}."""
    found = {name: [] for name in names}
    if "privacy" in names:
        found["privacy"] = list(privacy())
    wanted = None if every else added(since or last_audit())
    files = in_scope(None if wanted is None else set(wanted))
    words = _words() if "idents" in names else None
    for rel, kind in sorted(files.items()):
        lines = lines_of(rel, kind)
        keep = None if wanted is None else wanted.get(rel)
        fresh = [(n, t) for n, t in lines if keep is None or n in keep]
        if not fresh:
            continue
        if "emphasis" in names and kind == "prose":
            said = _emphasis(lines)
            if said:
                found["emphasis"].append((rel, 0, said, ""))
        for number, text in fresh:
            for name, pattern in LINE_SWEEPS.items():
                if name in names and pattern.search(text):
                    group = "narration (CHANGELOG, a question)" \
                        if name == "narration" and kind == "changelog" \
                        else name
                    found.setdefault(group, []).append(
                        (rel, number, "", text.strip()))
            if kind == "code":
                continue
            if "dense" in names:
                said = _dense(text)
                if said:
                    found["dense"].append((rel, number, said, text.strip()))
            if "headings" in names and HEADING.match(text):
                found["headings"].append((rel, number, "", text.strip()))
            if "idents" in names:
                for token in _unresolved(text, words):
                    found["idents"].append(
                        (rel, number, "no source holds it", token))
    return found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--since")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--sweep", help="comma-separated: " + ", ".join(ALL))
    args = ap.parse_args(argv)
    names = args.sweep.split(",") if args.sweep else ALL
    unknown = [n for n in names if n not in ALL]
    if unknown:
        ap.error(f"no sweep {', '.join(unknown)}; there are {', '.join(ALL)}")
    found = sweep(names, since=args.since, every=args.all)
    scope = "every line in scope" if args.all else \
        f"lines added since {args.since or 'the last audit'}"
    print(f"doc sweeps over {scope}")
    for name, hits in found.items():
        print(f"\n== {name}: {len(hits) or 'nothing found'}")
        for rel, number, note, text in hits:
            where = f"{rel}:{number}" if number else rel
            note = f" [{note}]" if note else ""
            print(f"{where}{note}: {text[:220]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
