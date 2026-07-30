"""
Launch-time sanity checks on the game-data files.

WHY THIS FILE EXISTS
====================
The game-data files under `game_data/` are hand-maintained, and most
mistakes in them are SILENT: a misspelled stat name is ignored, a
partner grade/class pair with no stat row falls back to plausible-but-
wrong numbers, a duplicated dict key throws away the entry above it. The
program keeps running and the scores are simply wrong. These checks turn
that class of mistake into a message box at launch.

THIS IS THE FILE TO EDIT when the game legitimately releases something
outside today's parameters -- every threshold is a named constant in the
"RULES" block below, ordered by data file and then by field, so widening
a range is a one-line change. Vocabularies (attributes, classes, stat
names) are NOT duplicated here: they are read from the data modules
themselves, so adding a newly-released attribute or class to the data
file widens the check automatically. Each of those definitions carries a
comment saying so.

TWO LAYERS
==========
`check_data_files()` -- text/AST level. Catches syntax errors (with
file, line and column) and duplicate dict keys, neither of which the
value layer could ever see: a syntax error stops the file being
importable, and a duplicate key is gone by the time Python has built the
dict. Must run BEFORE `game_data` is imported, so it parses the files as
text and imports nothing from the package. Source runs only -- a frozen
build has no .py files, and cannot have a syntax error in them anyway
because PyInstaller compiles them at build time, so the build would have
failed first.

`find_data_problems()` -- value level. Runs against the imported dicts,
so it sees final values whatever expression produced them. Safe to call
from a worker thread; it touches no UI and no global state. Line numbers
come from a best-effort AST map, and are omitted when the source isn't
available.

Everything here is advisory except a syntax error, which is fatal by
nature: the file cannot be imported, so the program cannot run.
"""

import ast
import re
import sys
from pathlib import Path

# ===========================================================================
# RULES -- edit these when the game releases data outside current bounds.
# Ranges are inclusive on both ends.
# ===========================================================================

# ---- characters.py --------------------------------------------------------
CHARACTERS_GRADE = (4, 5)
CHARACTERS_BASE_ATK = (300, 541)
CHARACTERS_BASE_DEF = (133, 208)
CHARACTERS_BASE_HP = (293, 423)
CHARACTERS_BASE_CRIT_RATE = 3.0          # exact, every character
CHARACTERS_BASE_CRIT_DMG = 125.0         # exact, every character
CHARACTERS_LEVEL_BONUS_ATK = (4, 9)      # level_61_bonus / level_62_bonus
CHARACTERS_LEVEL_BONUS_DEF = (2, 7)
CHARACTERS_LEVEL_BONUS_HP = (4, 10)

# ---- partners.py ----------------------------------------------------------
# Partner grade is deliberately NOT range-checked. Grades include the 4.5
# seasonal-pass tier, and what actually matters is that the partner's
# (grade, class) pair has a row in PARTNER_CLASS_STATS -- without one,
# get_partner_base_stats silently substitutes generic stats. A new grade
# tier is therefore added to PARTNER_CLASS_STATS in partners.py, not
# here.
PARTNERS_VALUES_PER_STAT = 5             # one per limit break, E0..E4
PARTNERS_TIER_RATIO_RANGE = (1.5, 2.0)   # max/min of a tier tuple
PARTNERS_TIER_RATIO_EXTRA = (4.0, 5.0)   # ...or exactly one of these
PARTNERS_EGO_COST = (2, 4)

# ---- sets.py --------------------------------------------------------------
SETS_PIECES = (2, 4)
SETS_TYPES = ("conditional", "unconditional")

# ---- reporting ------------------------------------------------------------
MAX_REPORTED_PROBLEMS = 25               # then "... and N more"
_RATIO_EPS = 1e-6

# Files parsed by the text layer. constants.py gets a syntax and
# duplicate-key check but no value checks: the game doesn't add data to
# it.
_SYNTAX_CHECKED = ("characters.py", "partners.py", "sets.py", "constants.py")


# ===========================================================================
# Reporting helpers
# ===========================================================================

_MB_OK = 0x00000000
_MB_ICONERROR = 0x00000010
_MB_ICONWARNING = 0x00000030
_MB_SETFOREGROUND = 0x00010000
_MB_TOPMOST = 0x00040000

_EDIT_HINT = "Checks and thresholds live in game_data_validator.py"


def _native_message(title: str, text: str, icon: int) -> None:
    """Owner-less native Windows message box, for the text layer -- it
    runs before any Tk root exists, and creating a throwaway one is an
    anti-pattern here (see the pre-startup prompt in
    czn_optimizer_gui.py). Prints instead off Windows."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, text, title, icon | _MB_SETFOREGROUND | _MB_TOPMOST
            )
            return
        except Exception:
            pass
    print(f"{title}\n\n{text}", file=sys.stderr)


def _data_dir() -> Path | None:
    """Directory holding the game-data source files, or None when the
    sources aren't on disk (frozen build)."""
    if getattr(sys, "frozen", False):
        return None
    d = Path(__file__).resolve().parent / "game_data"
    return d if d.is_dir() else None


def _trim(problems: list[str]) -> str:
    shown = problems[:MAX_REPORTED_PROBLEMS]
    extra = len(problems) - len(shown)
    text = "\n".join(shown)
    if extra > 0:
        text += f"\n... and {extra} more"
    return text


# ===========================================================================
# Layer 1: syntax + duplicate keys (text/AST, before game_data imports)
# ===========================================================================

def _key_repr(node) -> str | None:
    """A comparable, printable form of a dict-literal key, or None if the
    key isn't a literal we can compare (e.g. a computed expression)."""
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Tuple):
        parts = [_key_repr(e) for e in node.elts]
        if any(p is None for p in parts):
            return None
        return "(" + ", ".join(parts) + ")"
    return None


def _duplicate_keys(tree: ast.AST, filename: str) -> list[str]:
    """Every dict literal in the file, checked for repeated keys.

    Covers both a repeated top-level entry (two characters sharing a
    res_id -- the second silently wins) and a repeated field inside one
    entry (two `base_atk` lines -- likewise).
    """
    problems = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        seen: dict[str, int] = {}
        for key in node.keys:
            if key is None:          # {**spread}
                continue
            text = _key_repr(key)
            if text is None:
                continue
            if text in seen:
                problems.append(
                    f"{filename} | Ln: {key.lineno} | duplicate key {text} "
                    f"(first at line {seen[text]}) -- the later entry "
                    f"silently replaces the earlier one"
                )
            else:
                seen[text] = key.lineno
    return problems


def check_data_files() -> bool:
    """Parse each game-data file and report syntax errors and duplicate
    keys. Returns False if the program must not continue (a file doesn't
    parse), True otherwise -- including when the check is skipped.

    Call before importing `game_data`.
    """
    data_dir = _data_dir()
    if data_dir is None:
        return True

    fatal: list[str] = []
    warnings: list[str] = []

    for name in _SYNTAX_CHECKED:
        path = data_dir / name
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            warnings.append(f"{name} | could not be read ({exc})")
            continue
        try:
            tree = ast.parse(source, filename=name)
        except SyntaxError as exc:
            line = exc.lineno or 0
            col = exc.offset or 0
            detail = [f"File: {name} | Ln: {line} | Col: {col}",
                      f"  {exc.msg}"]
            text = (exc.text or "").rstrip("\n")
            if text:
                detail.append(f"  {text.strip()}")
                caret_pad = max(0, col - 1 - (len(text) - len(text.lstrip())))
                detail.append("  " + " " * caret_pad + "^")
            fatal.append("\n".join(detail))
            continue
        warnings.extend(_duplicate_keys(tree, name))

    if fatal:
        _native_message(
            "Game data won't parse",
            "The program can't start because a game-data file has a "
            "syntax error:\n\n" + "\n\n".join(fatal) + "\n\n" + _EDIT_HINT,
            _MB_ICONERROR,
        )
        return False

    if warnings:
        _native_message(
            "Game data problems",
            "Duplicate entries found in the game-data files. The later "
            "entry silently replaces the earlier one:\n\n"
            + _trim(warnings) + "\n\n" + _EDIT_HINT,
            _MB_ICONWARNING,
        )
    return True


# ===========================================================================
# Layer 2: value checks (imported dicts + best-effort line map)
# ===========================================================================

def _line_map(filename: str, dict_name: str) -> dict:
    """{key -> line number} for one module-level dict literal, empty when
    the source isn't available or doesn't parse (layer 1 already
    reported that)."""
    data_dir = _data_dir()
    if data_dir is None:
        return {}
    path = data_dir / filename
    if not path.is_file():
        return {}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=filename)
    except (OSError, SyntaxError):
        return {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        if not any(isinstance(t, ast.Name) and t.id == dict_name
                   for t in node.targets):
            continue
        out = {}
        for key in node.value.keys:
            if isinstance(key, ast.Constant):
                out[key.value] = key.lineno
            elif (isinstance(key, ast.UnaryOp)
                  and isinstance(key.op, ast.USub)
                  and isinstance(key.operand, ast.Constant)):
                # Negative literals parse as unary minus, not a Constant --
                # without this the placeholder partner ids (-1..-4) get no
                # line number.
                out[-key.operand.value] = key.lineno
        return out
    return {}


class _Reporter:
    """Accumulates problem lines, each prefixed with file, line (when
    known) and a human label for the entry."""

    def __init__(self, filename: str, lines: dict):
        self.filename = filename
        self.lines = lines
        self.problems: list[str] = []

    def add(self, key, label: str, message: str) -> None:
        where = f"{self.filename}"
        line = self.lines.get(key)
        if line:
            where += f" | Ln: {line}"
        self.problems.append(f"{where} | {label} | {message}")


def _in_range(value, bounds) -> bool:
    try:
        return bounds[0] <= value <= bounds[1]
    except TypeError:
        return False


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_tier_tuple(rep: _Reporter, key, label: str, field: str,
                      stat: str, values) -> None:
    """Shape rules shared by `values`, `stats` and `stats_conditional`:
    exactly PARTNERS_VALUES_PER_STAT numbers, non-decreasing, and a
    max/min ratio inside PARTNERS_TIER_RATIO_RANGE or exactly one of
    PARTNERS_TIER_RATIO_EXTRA."""
    where = f"{field}['{stat}']"
    if not isinstance(values, (tuple, list)):
        rep.add(key, label, f"{where} is {type(values).__name__}, expected "
                            f"{PARTNERS_VALUES_PER_STAT} values")
        return
    if len(values) != PARTNERS_VALUES_PER_STAT:
        rep.add(key, label, f"{where} has {len(values)} values, expected "
                            f"{PARTNERS_VALUES_PER_STAT} (E0..E4) -- fewer "
                            f"than 5 makes the whole passive read as zero")
        return
    if not all(_is_number(v) for v in values):
        rep.add(key, label, f"{where} has a non-numeric value: {values}")
        return
    if any(b < a for a, b in zip(values, values[1:])):
        rep.add(key, label, f"{where} is not ascending: {values}")
        return
    lo, hi = values[0], values[-1]
    if lo <= 0:
        return
    ratio = hi / lo
    ok = (PARTNERS_TIER_RATIO_RANGE[0] - _RATIO_EPS <= ratio
          <= PARTNERS_TIER_RATIO_RANGE[1] + _RATIO_EPS)
    if not ok:
        ok = any(abs(ratio - r) < _RATIO_EPS
                 for r in PARTNERS_TIER_RATIO_EXTRA)
    if not ok:
        allowed = (f"{PARTNERS_TIER_RATIO_RANGE[0]}-"
                   f"{PARTNERS_TIER_RATIO_RANGE[1]}, "
                   + ", ".join(str(r) for r in PARTNERS_TIER_RATIO_EXTRA))
        rep.add(key, label, f"{where} E4/E0 ratio is {ratio:.4g} "
                            f"({hi}/{lo}); expected {allowed}")


def _check_characters(problems: list[str]) -> None:
    from game_data import (CHARACTERS, ATTRIBUTE_COLORS,
                           POTENTIAL_STAT_VALUES, CLASSES)

    rep = _Reporter("characters.py", _line_map("characters.py", "CHARACTERS"))
    node_stats = tuple(POTENTIAL_STAT_VALUES)
    attributes = tuple(ATTRIBUTE_COLORS)
    required = ("name", "grade", "attribute", "class", "base_atk",
                "base_def", "base_hp", "base_crit_rate", "base_crit_dmg",
                "node_50", "node_60")
    bonus_ranges = {"atk": CHARACTERS_LEVEL_BONUS_ATK,
                    "def": CHARACTERS_LEVEL_BONUS_DEF,
                    "hp": CHARACTERS_LEVEL_BONUS_HP}
    names: dict = {}

    for key, data in CHARACTERS.items():
        if key == 0 or data is None:      # the unequipped sentinel
            continue
        label = f"{data.get('name', '?')} ({key})" if isinstance(data, dict) \
            else str(key)
        if not isinstance(key, int):
            rep.add(key, label, f"res_id key is {type(key).__name__}, not "
                                f"int -- lookups are int-keyed, so this "
                                f"entry can never match")
        if not isinstance(data, dict):
            rep.add(key, label, f"entry is {type(data).__name__}, expected a "
                                f"dict")
            continue

        for field in required:
            if field not in data:
                rep.add(key, label, f"missing '{field}'")

        if "name" in data:
            other = names.get(data["name"])
            if other is not None:
                rep.add(key, label, f"name duplicates res_id {other} -- "
                                    f"CHARACTERS_BY_NAME keeps only one, so "
                                    f"the other is lost to name lookups")
            else:
                names[data["name"]] = key

        if "grade" in data and not _in_range(data["grade"], CHARACTERS_GRADE):
            rep.add(key, label, f"grade {data['grade']} outside "
                                f"{CHARACTERS_GRADE[0]}-{CHARACTERS_GRADE[1]}")
        if "attribute" in data and data["attribute"] not in attributes:
            rep.add(key, label, f"attribute '{data['attribute']}' is not one "
                                f"of {', '.join(attributes)}")
        if "class" in data and data["class"] not in CLASSES:
            rep.add(key, label, f"class '{data['class']}' is not one of "
                                f"{', '.join(CLASSES)}")

        for field, bounds in (("base_atk", CHARACTERS_BASE_ATK),
                              ("base_def", CHARACTERS_BASE_DEF),
                              ("base_hp", CHARACTERS_BASE_HP)):
            if field in data and not _in_range(data[field], bounds):
                rep.add(key, label, f"{field} {data[field]} outside "
                                    f"{bounds[0]}-{bounds[1]}")

        for field, expected in (("base_crit_rate", CHARACTERS_BASE_CRIT_RATE),
                                ("base_crit_dmg", CHARACTERS_BASE_CRIT_DMG)):
            if field in data and data[field] != expected:
                rep.add(key, label, f"{field} is {data[field]}, expected "
                                    f"{expected}")

        for field in ("node_50", "node_60"):
            value = data.get(field)
            if field in data and value not in node_stats:
                rep.add(key, label, f"{field} '{value}' is not one of "
                                    f"{', '.join(node_stats)} -- an unknown "
                                    f"name makes the node bonus zero")

        for field in ("level_61_bonus", "level_62_bonus"):
            bonus = data.get(field)
            if bonus is None:
                continue
            if not isinstance(bonus, dict):
                rep.add(key, label, f"{field} is {type(bonus).__name__}, "
                                    f"expected a dict")
                continue
            for unknown in set(bonus) - set(bonus_ranges):
                rep.add(key, label, f"{field} has unknown key '{unknown}' "
                                    f"(expected atk / def / hp) -- it is "
                                    f"silently ignored")
            for stat, bounds in bonus_ranges.items():
                if stat not in bonus:
                    rep.add(key, label, f"{field} is missing '{stat}'")
                elif not _in_range(bonus[stat], bounds):
                    rep.add(key, label, f"{field}['{stat}'] {bonus[stat]} "
                                        f"outside {bounds[0]}-{bounds[1]}")

    problems.extend(rep.problems)


def _check_partners(problems: list[str]) -> None:
    from game_data import (PARTNERS, PARTNER_CLASS_STATS, PARTNER_STAT_NAMES,
                           CLASSES)

    rep = _Reporter("partners.py", _line_map("partners.py", "PARTNERS"))
    required = ("name", "grade", "class", "passive_name", "passive_desc",
                "values", "stats", "ego_name", "ego_cost", "ego_desc")
    names: dict = {}

    for key, data in PARTNERS.items():
        label = f"{data.get('name', '?')} ({key})" if isinstance(data, dict) \
            else str(key)
        if not isinstance(key, int):
            rep.add(key, label, f"res_id key is {type(key).__name__}, not int")
        if not isinstance(data, dict):
            rep.add(key, label, f"entry is {type(data).__name__}, expected a "
                                f"dict")
            continue

        for field in required:
            if field not in data:
                rep.add(key, label, f"missing '{field}'")

        if "name" in data:
            other = names.get(data["name"])
            if other is not None:
                rep.add(key, label, f"name duplicates res_id {other}")
            else:
                names[data["name"]] = key

        if "class" in data and data["class"] not in CLASSES:
            rep.add(key, label, f"class '{data['class']}' is not one of "
                                f"{', '.join(CLASSES)}")

        if "grade" in data and "class" in data:
            pair = (data["grade"], data["class"])
            if pair not in PARTNER_CLASS_STATS:
                rep.add(key, label,
                        f"(grade, class) {pair} has no PARTNER_CLASS_STATS "
                        f"row -- base stats fall back to generic values, "
                        f"which are wrong for every build using this partner")

        if "ego_cost" in data and not _in_range(data["ego_cost"],
                                                PARTNERS_EGO_COST):
            rep.add(key, label, f"ego_cost {data['ego_cost']} outside "
                                f"{PARTNERS_EGO_COST[0]}-"
                                f"{PARTNERS_EGO_COST[1]}")

        for field in ("values", "stats", "stats_conditional"):
            table = data.get(field)
            if table is None:
                continue
            if not isinstance(table, dict):
                rep.add(key, label, f"{field} is {type(table).__name__}, "
                                    f"expected a dict")
                continue
            for stat, values in table.items():
                if field != "values" and stat not in PARTNER_STAT_NAMES:
                    rep.add(key, label,
                            f"{field} key '{stat}' is not one of "
                            f"{', '.join(PARTNER_STAT_NAMES)} -- it is "
                            f"silently ignored, so the bonus is lost")
                _check_tier_tuple(rep, key, label, field, stat, values)

        desc = data.get("passive_desc")
        values = data.get("values")
        if isinstance(desc, str) and isinstance(values, dict):
            used = set(re.findall(r"\{([^{}]*)\}", desc))
            for missing in sorted(used - set(values)):
                rep.add(key, label,
                        f"passive_desc uses {{{missing}}} but 'values' has no "
                        f"such key -- the text shows the placeholder as-is")
            for unused in sorted(set(values) - used):
                rep.add(key, label,
                        f"values['{unused}'] is never used in passive_desc")

    problems.extend(rep.problems)


def _check_sets(problems: list[str]) -> None:
    from game_data import (SETS, SET_STAT_NAME_MAP, SET_CARD_MULT_STATS,
                           ATTRIBUTE_COLORS)

    rep = _Reporter("sets.py", _line_map("sets.py", "SETS"))
    attributes = tuple(ATTRIBUTE_COLORS)
    stat_names = tuple(SET_STAT_NAME_MAP) + tuple(SET_CARD_MULT_STATS)
    required = ("name", "pieces", "bonus", "type", "stat", "value")
    names: dict = {}

    for key, data in SETS.items():
        label = f"{data.get('name', '?')} ({key})" if isinstance(data, dict) \
            else str(key)
        if not isinstance(key, int):
            rep.add(key, label, f"set id key is {type(key).__name__}, not int")
        if not isinstance(data, dict):
            rep.add(key, label, f"entry is {type(data).__name__}, expected a "
                                f"dict")
            continue

        for field in required:
            if field not in data:
                rep.add(key, label, f"missing '{field}'")

        if "name" in data:
            other = names.get(data["name"])
            if other is not None:
                rep.add(key, label, f"name duplicates set id {other}")
            else:
                names[data["name"]] = key

        if "pieces" in data and data["pieces"] not in SETS_PIECES:
            rep.add(key, label, f"pieces {data['pieces']} is not "
                                f"{' or '.join(str(p) for p in SETS_PIECES)}")
        if "type" in data and data["type"] not in SETS_TYPES:
            rep.add(key, label, f"type '{data['type']}' is not one of "
                                f"{', '.join(SETS_TYPES)}")
        if "value" in data and not _is_number(data["value"]):
            rep.add(key, label, f"value {data['value']!r} is not a number")

        stat = data.get("stat")
        if "stat" in data:
            if stat not in stat_names:
                rep.add(key, label, f"stat '{stat}' is not one of "
                                    f"{', '.join(stat_names)} -- it is "
                                    f"silently ignored, so the bonus is lost "
                                    f"while the set still counts for "
                                    f"set-locking")
            elif (stat in SET_CARD_MULT_STATS
                  and data.get("type") != "conditional"):
                rep.add(key, label,
                        f"stat '{stat}' only takes effect on a conditional "
                        f"set; on type '{data.get('type')}' it contributes "
                        f"nothing anywhere")

        for element in data.get("elements") or ():
            if element not in attributes:
                rep.add(key, label, f"elements entry '{element}' is not one "
                                    f"of {', '.join(attributes)} -- the Set "
                                    f"Configuration row is mis-coloured")

    problems.extend(rep.problems)


def find_data_problems() -> list[str]:
    """Every value-level problem across the game-data files, as formatted
    report lines. Empty means everything is within parameters.

    Safe on a worker thread: reads imported data, touches no UI. A check
    that raises is reported rather than propagated, so one broken rule
    can't take the program down.
    """
    problems: list[str] = []
    for check in (_check_characters, _check_partners, _check_sets):
        try:
            check(problems)
        except Exception as exc:                     # noqa: BLE001
            problems.append(f"{check.__name__} could not run: "
                            f"{type(exc).__name__}: {exc}")
    return problems


def format_problem_report(problems: list[str]) -> str:
    """The message-box body for a list of value-level problems."""
    count = len(problems)
    header = (f"{count} problem{'s' if count != 1 else ''} found in the "
              f"game-data files. The program still works, but any build "
              f"using the affected entries may be scored wrongly.\n\n")
    return header + _trim(problems) + "\n\n" + _EDIT_HINT
