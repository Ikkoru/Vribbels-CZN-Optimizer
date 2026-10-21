"""The game client's facts written into `game_data`'s own tables.

A patch adds combatants and partners, and the program ships what it
knows of them in the tables a player without the client reads:
`CHARACTERS` and `PARTNERS`, and in `partners.py` a new partner class's
level-60 flats (`PARTNER_CLASS_STATS`) and the partner a new combatant
is optimized with (`SIGNATURE_PARTNERS`, `PARTNER_EXCEPTIONS`). `sync`
writes them there, beside the maintainer's own entries.
`docs/client_tables.py --ship` runs it with `from_client.py`; a launch
from source runs that when the client is a newer build than what was
shipped, and so does the build (`OptimizerGUI._report_client_parts`,
`zCreate exe.bat`).

**Only what is marked is the tool's.** Three markers, each the whole of
a line's comment:

- `# client block start` on an entry's first value line and `# client
  block end` on its last: an entry the client fills whole, such as a
  unit the hand table had no entry for. Everything from the one to the
  other is rewritten; the entry's key line and its closing brace are
  not.
- `# client` on one value's line inside an entry of the maintainer's:
  that value is the client's, the rest of the entry the maintainer's.
  In a line table (`LINE_TABLES`), whose entries are one line each, it
  marks a whole entry, on a line holding no other.

Everything unmarked is the maintainer's and never rewritten. Where it
parts from the client, `--audit` says so, and the launch from source
lists it. **A value read in game stays unmarked**:
`check_client_overlay` holds the reader to it, and one this wrote would
vouch for nothing.

An entry the client fills whole carries `"from_client": True`, which is
what the program sees of the mark when it runs: the data check asks such
an entry for nothing of the maintainer's, a Potential 7 entry among
them, and `check_client_overlay` and `--audit` hold nothing to it.
`marked` gives the `# client` values, which nothing at run time can see.

Writes nothing but the tables' marked lines, each line ending as the
file's do, and only where the result still parses to the same table
with the client's values in it (`_verified`).
"""

import ast
import codecs
import copy
import io
import json
import tokenize
from pathlib import Path

# The markers, each the whole of a line's comment.
CLIENT = "# client"
BLOCK_START = "# client block start"
BLOCK_END = "# client block end"

# The key an entry the client fills whole carries.
FROM_CLIENT = "from_client"

HERE = Path(__file__).resolve().parent

# The entry tables, whose entries are dicts of one field a line: (file,
# table, the facts it is written from, the entry's fields in the order
# the hand entries list them).
COMBATANTS = ("characters.py", "CHARACTERS", "combatants",
              ("name", "grade", "attribute", "class", "base_atk", "base_def",
               "base_hp", "base_crit_rate", "base_crit_dmg", "node_50",
               "node_60", "level_gains"))
PARTNERS = ("partners.py", "PARTNERS", "partners",
            ("name", "grade", "class", "passive_name", "passive_desc",
             "values", "stats", "ego_name", "ego_cost", "ego_desc"))
# The line tables, an entry a line: a class's level-60 flats by (grade,
# class), and the partner each combatant is optimized with when it is
# not built, by name.
CLASS_STATS = ("partners.py", "PARTNER_CLASS_STATS")
SIGNATURES = ("partners.py", "SIGNATURE_PARTNERS")
EXCEPTIONS = ("partners.py", "PARTNER_EXCEPTIONS")
LINE_TABLES = (CLASS_STATS, SIGNATURES, EXCEPTIONS)

# The fields drawn one entry to a line, as the hand entries draw them.
MULTILINE = ("values", "stats", "level_gains")


class SyncError(Exception):
    """A table this would write wrong: nothing is written."""


def combatant_entry(fact, whole=True):
    """The entry `characters.py` holds for a combatant the client states,
    from `game_client.combatants`' fact for it. `whole`, the entry of a
    combatant the client fills whole: the default entry's fields where
    the client gives none, and `from_client`, as the overlay builds a
    combatant only the client knows; else only what the client states,
    for a `# client` value to take."""
    from .characters import DEFAULT_CHARACTER
    stated = {field: fact[field] for field in COMBATANTS[3][:-1]
              if fact.get(field) is not None}
    gains = {}
    for level, steps in (fact.get("level_gains") or {}).items():
        if isinstance(steps, dict) and str(level).isdigit():
            gains[int(level)] = {stat: steps.get(stat, 0)
                                 for stat in ("atk", "def", "hp")}
    if gains:
        stated["level_gains"] = dict(sorted(gains.items()))
    if not whole:
        return stated
    entry = {field: stated.get(field, copy.deepcopy(DEFAULT_CHARACTER.get(field)))
             for field in COMBATANTS[3][:-1]}
    if gains:
        entry["level_gains"] = stated["level_gains"]
    entry[FROM_CLIENT] = True
    return entry


def partner_entry(fact, whole=True):
    """The entry `partners.py` holds for a partner the client states,
    from `game_client.partners`' fact for it, its passive drawn from the
    client's lines (`client_overlay.passive_template`). `whole` as for
    `combatant_entry`; the client writes no Ego description."""
    from .client_overlay import passive_template
    from .partners import DEFAULT_PARTNER
    stated = {field: fact[field] for field in PARTNERS[3]
              if field not in ("passive_desc", "values", "stats", "ego_desc")
              and fact.get(field) is not None}
    if fact.get("passive_lines"):
        stated["passive_desc"], stated["values"] = passive_template(
            fact["passive_lines"])
    if fact.get("stats"):
        stated["stats"] = {stat: tuple(steps) for stat, steps
                           in sorted(fact["stats"].items())}
    if not whole:
        return stated
    entry = {field: stated.get(field, copy.deepcopy(DEFAULT_PARTNER.get(field)))
             for field in PARTNERS[3]}
    entry["ego_desc"] = ""
    entry[FROM_CLIENT] = True
    return entry


def class_stats(partner_facts):
    """{(grade, class): level-60 flats} for each pair whose partners the
    client holds all agree on them, as the overlay lays them over
    `PARTNER_CLASS_STATS`."""
    seen = {}
    for fact in partner_facts.values():
        flat = fact.get("level_60")
        if isinstance(flat, dict) and fact.get("grade") is not None \
                and fact.get("class"):
            seen.setdefault((fact["grade"], fact["class"]), []).append(
                {stat: flat.get(stat, 0) for stat in ("atk", "def", "hp")})
    return {pair: flats[0] for pair, flats in seen.items()
            if all(flat == flats[0] for flat in flats)}


def pairings(combatants, recommended, partner_names, signature, exceptions):
    """({combatant name: partner name} for `SIGNATURE_PARTNERS`, the same
    for `PARTNER_EXCEPTIONS`): the partner the client recommends for
    each combatant (`game_client.recommended_partners`). A 5-star's goes
    to the first, being the partner it was released with, as every
    5-star there agrees; anyone else's to the second, a default the
    maintainer's own choice replaces. A name one table holds is kept out
    of the other.

    `combatants` is {res_id: (name, grade)} as `CHARACTERS` holds them,
    `partner_names` {res_id: name} as `PARTNERS` does: a pairing names
    only a partner the program has."""
    sig, exc = {}, {}
    for rid, (name, grade) in combatants.items():
        partner = partner_names.get(recommended.get(rid))
        if not partner or not name:
            continue
        if grade == 5:
            if name not in exceptions:
                sig[name] = partner
        elif name not in signature:
            exc[name] = partner
    return sig, exc


def sync(facts, folder=HERE, write=True):
    """Bring the marked lines of the tables in `folder` level with
    `facts` -- `{"combatants": ..., "partners": ..., "recommended":
    ...}`, as `game_client.combatants`, `partners` and
    `recommended_partners` give them: a unit or a pairing a table lacks
    added, every block and `# client` value rewritten. Returns (lines
    saying what changed, {file name: its new text}); writes the files
    where `write`."""
    folder = Path(folder)
    # A unit the client has no name for yet is left out, as the overlay
    # leaves it: an entry called Unknown would stand for every one.
    combatants = {int(k): v for k, v in (facts.get("combatants") or {}).items()
                  if str(k).isdigit() and isinstance(v, dict) and v.get("name")}
    partners = {int(k): v for k, v in (facts.get("partners") or {}).items()
                if str(k).isdigit() and isinstance(v, dict) and v.get("name")}
    recommended = {int(k): int(v) for k, v
                   in (facts.get("recommended") or {}).items()
                   if str(k).isdigit() and str(v).isdigit()}
    said = []
    names = (COMBATANTS[0], PARTNERS[0])
    held = {name: _read(folder / name) for name in names}
    texts = dict(held)
    for spec, facts_of, build in ((COMBATANTS, combatants, combatant_entry),
                                  (PARTNERS, partners, partner_entry)):
        texts[spec[0]] = _sync_entries(
            texts[spec[0]], spec[0], spec[1],
            {rid: build(fact) for rid, fact in facts_of.items()},
            {rid: build(fact, whole=False) for rid, fact in facts_of.items()},
            said)
    texts[CLASS_STATS[0]] = _sync_lines(texts[CLASS_STATS[0]], CLASS_STATS[0],
                                        CLASS_STATS[1], class_stats(partners),
                                        said)
    # By the names the tables hold once the units are in.
    units = {rid: (entry.get("name"), entry.get("grade")) for rid, entry
             in _held(texts[COMBATANTS[0]], COMBATANTS[1]).items()
             if isinstance(entry, dict)}
    partner_names = {rid: entry.get("name") for rid, entry
                     in _held(texts[PARTNERS[0]], PARTNERS[1]).items()
                     if isinstance(entry, dict)}
    sig, exc = pairings(units, recommended, partner_names,
                        _held(texts[SIGNATURES[0]], SIGNATURES[1]),
                        _held(texts[EXCEPTIONS[0]], EXCEPTIONS[1]))
    for spec, theirs in ((SIGNATURES, sig), (EXCEPTIONS, exc)):
        texts[spec[0]] = _sync_lines(texts[spec[0]], spec[0], spec[1],
                                     theirs, said)
    changed = {name: text for name, text in texts.items()
               if text != held[name]}
    if write:
        write_out(changed, folder)
    return said, changed


def write_out(changed, folder=HERE):
    """Write each {file name: text} `sync` gave back into `folder`."""
    for name, text in changed.items():
        _write(Path(folder) / name, text)


def marked(table, folder=HERE):
    """{entry key: {field: line}} of the `# client` values in one of the
    entry tables (`CHARACTERS`, `PARTNERS`), and {entry key: line} in a
    line table (`LINE_TABLES`): what the client fills among the
    maintainer's entries, which nothing at run time can see."""
    lines = {spec[1] for spec in LINE_TABLES}
    for spec in (COMBATANTS, PARTNERS, *LINE_TABLES):
        if spec[1] == table:
            text = _read(Path(folder) / spec[0])
            break
    else:
        raise KeyError(table)
    comments = _comments(text)
    node = _table(ast.parse(text), table)
    out = {}
    for key_node, value in zip(node.keys, node.values):
        key = ast.literal_eval(key_node)
        if table in lines:
            if comments.get(key_node.lineno) == CLIENT:
                out[key] = key_node.lineno
            continue
        if not isinstance(value, ast.Dict) or not value.keys \
                or _block(value, comments):
            continue
        for field_node, field_value in zip(value.keys, value.values):
            span = range(field_node.lineno, field_value.end_lineno + 1)
            if any(comments.get(line) == CLIENT for line in span):
                out.setdefault(key, {})[ast.literal_eval(field_node)] = \
                    field_node.lineno
    return out


# ------------------------------------------------------------- writing


def _sync_entries(text, name, table, whole, stated, said):
    """`text` with the entry table's blocks the client's `whole` entries,
    its `# client` values what the client has `stated`, and a block
    added for each unit it lacks."""
    comments = _comments(text)
    node = _table(ast.parse(text), table)
    if node is None:
        raise SyncError(f"{name} assigns no {table} dict")
    lines = text.splitlines(keepends=True)
    newline = _newline(text)
    edits = []
    held = set()
    key_indent, field_indent = _indents(node)
    for key_node, value in zip(node.keys, node.values):
        key = ast.literal_eval(key_node)
        held.add(key)
        if not isinstance(value, ast.Dict) or not value.keys:
            continue
        who = _who(key, value)
        block = _block(value, comments)
        if block == "broken":
            said.append(f"{name}: {table}[{key!r}] {who} has a block marker "
                        f"without its pair, so nothing in it was touched")
            continue
        if block:
            fact = whole.get(key)
            if fact is None:
                said.append(f"{name}: {table}[{key!r}] {who} is the "
                            f"client's, and the client no longer holds it: "
                            f"left as it was")
                continue
            first, last = value.keys[0].lineno, value.values[-1].end_lineno
            if not (value.lineno < first and last < value.end_lineno):
                raise SyncError(f"{name}: {table}[{key!r}] does not hold "
                                f"its fields on lines of their own")
            new = _block_body(fact, field_indent)
            if _bare(lines[first - 1:last]) != new:
                edits.append((first, last, new))
                said.append(f"{name}: {table}[{key!r}] {fact.get('name')} "
                            f"rewritten from the client")
            continue
        fact = stated.get(key)
        for field_node, field_value in zip(value.keys, value.values):
            span = range(field_node.lineno, field_value.end_lineno + 1)
            if not any(comments.get(line) == CLIENT for line in span):
                continue
            field = ast.literal_eval(field_node)
            if fact is None or field not in fact:
                said.append(f"{name}: {table}[{key!r}] {who} marks {field!r} "
                            f"the client's, which states none: left as it "
                            f"was")
                continue
            shared = [n for n in value.keys if n is not field_node
                      and n.lineno in span]
            if shared or field_node.lineno == value.lineno \
                    or field_value.end_lineno == value.end_lineno:
                said.append(f"{name}: {table}[{key!r}] {who}'s {field!r} "
                            f"shares its line, so it was not touched")
                continue
            new = _field_lines(field, fact[field], field_indent)
            new[-1] += "  " + CLIENT
            if _bare(lines[field_node.lineno - 1:field_value.end_lineno]) \
                    != new:
                edits.append((field_node.lineno, field_value.end_lineno, new))
                said.append(f"{name}: {table}[{key!r}] {who}'s {field!r} "
                            f"set to the client's")
    added = [key for key in sorted(whole) if key not in held]
    if added:
        new = []
        for key in added:
            new.append(" " * key_indent + _literal(key) + ": {")
            new += _block_body(whole[key], field_indent)
            new.append(" " * key_indent + "},")
            said.append(f"{name}: {table}[{key!r}] {whole[key].get('name')} "
                        f"added from the client")
        edits.append((_closing(lines, node, name, table),
                      node.end_lineno - 1, new))
    result = _apply(lines, edits, newline)
    _verified(result, table, whole, held | set(added))
    return result


def _closing(lines, node, name, table):
    """The line closing a table, which an added entry goes before: one of
    its own, or the entry would land inside the last one."""
    if not lines[node.end_lineno - 1].strip().startswith("}"):
        raise SyncError(f"{name}: {table} does not close on a line of its "
                        f"own")
    return node.end_lineno


def _sync_lines(text, name, table, theirs, said):
    """`text` with the line table's `# client` entries the client's, and
    an entry added for each key it lacks."""
    comments = _comments(text)
    node = _table(ast.parse(text), table)
    if node is None:
        raise SyncError(f"{name} assigns no {table} dict")
    lines = text.splitlines(keepends=True)
    edits, held = [], set()
    key_indent, _field = _indents(node)
    starts = [key_node.lineno for key_node in node.keys]
    for key_node, value in zip(node.keys, node.values):
        key = ast.literal_eval(key_node)
        held.add(key)
        if comments.get(key_node.lineno) != CLIENT:
            continue
        if key not in theirs:
            said.append(f"{name}: {table}[{key!r}] is the client's, and the "
                        f"client no longer states it: left as it was")
            continue
        # A line holding other entries too is rewritten for none: the
        # rewrite is the whole line.
        if value.end_lineno != key_node.lineno \
                or starts.count(key_node.lineno) > 1:
            said.append(f"{name}: {table}[{key!r}] shares its line or runs "
                        f"past it, so it was not touched")
            continue
        new = [" " * key_indent + f"{_literal(key)}: {_literal(theirs[key])},"
               f"  {CLIENT}"]
        if _bare(lines[key_node.lineno - 1:key_node.lineno]) != new:
            edits.append((key_node.lineno, key_node.lineno, new))
            said.append(f"{name}: {table}[{key!r}] set to the client's")
    added = [key for key in sorted(theirs, key=repr) if key not in held]
    if added:
        new = [" " * key_indent + f"{_literal(key)}: {_literal(theirs[key])},"
               f"  {CLIENT}" for key in added]
        edits.append((_closing(lines, node, name, table),
                      node.end_lineno - 1, new))
        said += [f"{name}: {table}[{key!r}] added from the client"
                 for key in added]
    return _apply(lines, edits, _newline(text))


def _block_body(entry, indent):
    """An entry's field lines, the first marked `BLOCK_START` and the
    last `BLOCK_END`."""
    body = []
    for field, value in entry.items():
        body += _field_lines(field, value, indent)
    body[0] += "  " + BLOCK_START
    body[-1] += "  " + BLOCK_END
    return body


def _field_lines(field, value, indent):
    """One field as a hand entry writes it: the dicts in `MULTILINE`
    one entry to a line, anything else on one."""
    pad = " " * indent
    if field in MULTILINE and isinstance(value, dict) and value:
        out = [f"{pad}{_literal(field)}: {{"]
        out += [f"{pad}    {_literal(k)}: {_literal(v)},"
                for k, v in value.items()]
        out.append(f"{pad}}},")
        return out
    return [f"{pad}{_literal(field)}: {_literal(value)},"]


def _literal(value):
    """`value` as Python source: strings double-quoted and ASCII, as
    the hand tables write them."""
    if value is None or isinstance(value, bool):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, tuple):
        inner = ", ".join(_literal(v) for v in value)
        return f"({inner},)" if len(value) == 1 else f"({inner})"
    if isinstance(value, list):
        return "[" + ", ".join(_literal(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{_literal(k)}: {_literal(v)}"
                               for k, v in value.items()) + "}"
    raise SyncError(f"cannot write {type(value).__name__} {value!r}")


def _apply(lines, edits, newline):
    """`lines` with each (first, last, new lines) put in, bottom first so
    the numbers above stay right; `last` below `first` inserts before
    `first`. A line kept keeps its own ending."""
    out = list(lines)
    for first, last, new in sorted(edits, key=lambda e: e[0], reverse=True):
        out[first - 1:last] = [line + newline for line in new]
    return "".join(out)


def _verified(text, table, theirs, keys):
    """Raise unless `text` parses to the table with exactly `keys`, and
    every block in it the client's entry."""
    node = _table(ast.parse(text), table)
    try:
        held = ast.literal_eval(node)
    except ValueError as exc:
        raise SyncError(f"{table} no longer reads as a literal: {exc}")
    if set(held) != keys:
        raise SyncError(f"{table} would hold {sorted(set(held) ^ keys)} "
                        f"otherwise than it should")
    for key, entry in held.items():
        if isinstance(entry, dict) and entry.get(FROM_CLIENT) \
                and key in theirs and entry != theirs[key]:
            raise SyncError(f"{table}[{key!r}] would read {entry}, not the "
                            f"client's {theirs[key]}")


# ------------------------------------------------------------- reading


def _read(path):
    raw = Path(path).read_bytes()
    return raw.decode("utf-8-sig")


def _write(path, text):
    """`text` into `path`, a byte-order mark kept where it had one."""
    path = Path(path)
    bom = path.read_bytes().startswith(codecs.BOM_UTF8)
    path.write_bytes((codecs.BOM_UTF8 if bom else b"") + text.encode("utf-8"))


def _newline(text):
    """The ending most of `text`'s lines have."""
    crlf = text.count("\r\n")
    return "\r\n" if crlf and crlf >= text.count("\n") - crlf else "\n"


def _bare(lines):
    """`lines` without their endings, to compare with what would go in."""
    return [line.rstrip("\r\n") for line in lines]


def _comments(text):
    """{line number: the comment ending it, stripped}."""
    out = {}
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            out[token.start[0]] = token.string.strip()
    return out


def _held(text, table):
    """What `table` holds in `text`, read as the literal it is."""
    node = _table(ast.parse(text), table)
    if node is None:
        raise SyncError(f"no {table} dict to read")
    return ast.literal_eval(node)


def _table(tree, table):
    """The dict a module-level `table = {...}` assigns, or None."""
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Dict) \
                and any(isinstance(t, ast.Name) and t.id == table
                        for t in node.targets):
            return node.value
    return None


def _block(entry, comments):
    """True where an entry's first value line carries `BLOCK_START` and
    its last `BLOCK_END`; "broken" where only one does; else False."""
    start = comments.get(entry.keys[0].lineno) == BLOCK_START
    end = comments.get(entry.values[-1].end_lineno) == BLOCK_END
    inner = any(comments.get(line) in (BLOCK_START, BLOCK_END)
                for line in range(entry.keys[0].lineno + 1,
                                  entry.values[-1].end_lineno))
    if start and end and not inner:
        return True
    return "broken" if start or end or inner else False


def _indents(node):
    """(the table's key indent, an entry's field indent), as its first
    dict entry has them; the hand tables' 4 and 8 where none does."""
    for key_node, value in zip(node.keys, node.values):
        if isinstance(value, ast.Dict) and value.keys \
                and value.keys[0].lineno > key_node.lineno:
            return key_node.col_offset, value.keys[0].col_offset
    for key_node in node.keys:
        return key_node.col_offset, key_node.col_offset + 4
    return 4, 8


def _who(key, value):
    """An entry's name, for the lines said about it."""
    for field_node, field_value in zip(value.keys, value.values):
        if isinstance(field_node, ast.Constant) and field_node.value == "name" \
                and isinstance(field_value, ast.Constant):
            return str(field_value.value)
    return str(key)
