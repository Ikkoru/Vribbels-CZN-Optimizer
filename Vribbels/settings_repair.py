"""Settings files that will not read, repaired or set aside at launch.

A settings file can stop reading as JSON: a slip in a hand edit, a save
cut short, an editor that saved it with a byte-order mark or in the
system's ANSI code page. Its manager then reads an empty store, and the
first save writes that over everything the file held. So before the
defaults sync or any manager reads the folder, `repair_folder` goes
through every file in `KINDS`:

* **It reads**: left as it is.
* **Part of it reads** (`Reader`): what reads is saved in its place,
  and the original kept beside it (`json_file.set_aside`). The files'
  shapes are fixed, so a record a lost bracket moved -- out beside its
  collection, or inside the record before it -- is put back where it
  belongs (`_rehome`). A record that only partly reads -- a scoring
  preset, a combatant's optimizer settings -- is left out whole, rather
  than kept with defaults standing in for what was lost
  (`Kind.entries`).
* **Nothing in it reads**: it is set aside, and the sync that runs
  next copies the shipped default into its place where there is one.
* **It will not open**: left as it is. Its manager saves nothing over
  it this session, and neither does the sync.

Each file it touched comes back as a `Repair`, for the window to report
once it is up (`OptimizerGUI._report_settings_repairs`).
"""

import json
import locale
import re
from pathlib import Path

import character_preset_manager
import optimizer_settings_manager
import preset_manager
import settings_manager
from json_file import set_aside, write_json

# A key path element standing for every key.
ANY = object()

REPAIRED, SET_ASIDE, UNREAD, FAILED = ("repaired", "set aside", "unread",
                                       "failed")

_NUMBER = re.compile(r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?")
_BARE_KEY = re.compile(r"[A-Za-z0-9_$][\w$.\-]*")
_PLAIN = {'"': re.compile(r"[^\"\\\r\n]+"), "'": re.compile(r"[^'\\\r\n]+")}
_WORDS = (("true", True), ("false", False), ("null", None),
          ("True", True), ("False", False), ("None", None),
          ("NaN", float("nan")), ("Infinity", float("inf")),
          ("-Infinity", float("-inf")))
_ESCAPES = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t"}
# Names a report lists before it says how many more.
_NAMES_SHOWN = 6


class _Bad(Exception):
    """What starts here does not read as what was expected."""


class _Unclosed(_Bad):
    """A string ran into a line break. Whatever followed it on the
    line is gone with it, and the next line is read as it stands."""


class Reader:
    """A JSON reader that goes on past what a hand edit or a cut-off
    save leaves behind.

    It takes what JSON takes, and comments, single quotes, trailing and
    missing commas, bare keys and Python's True, False and None. A
    member or element that does not read is skipped to the next comma
    or closing bracket at its own depth. A line break ends a string,
    since JSON never holds one raw, and the end of the text closes
    whatever is open.

    `damage` is the key path of every place something was left out --
    an index for an array's element -- and `cut` the path where the
    text ended inside a value, or None. A number or a word the text ends
    on counts as cut: `12` may have been `125`. `truncated` says the
    text stops partway through: a text ending on a closing bracket is
    whole, and short of a bracket missing inside it.
    """

    def __init__(self, text):
        self.text = text
        self.at = 0
        self.damage = []
        self.cut = None
        self.truncated = False

    def read(self):
        """The value the text holds, as far as it reads; None for none."""
        self._space()
        try:
            value = self._value(())
        except (_Bad, RecursionError):
            self.damage.append(())
            return None
        self.truncated = self.cut is not None \
            and not self.text.rstrip().endswith(("}", "]"))
        rest = self.text[self.at:]
        if self.cut is None and rest.strip(" \t\r\n,}]"):
            # Something after the value besides a stray closing bracket.
            self.damage.append(())
        return value

    # ---------------------------------------------------------- pieces

    def _space(self):
        text, end = self.text, len(self.text)
        while self.at < end:
            if text[self.at] in " \t\r\n\ufeff":
                self.at += 1
            elif text.startswith("//", self.at):
                line_end = text.find("\n", self.at)
                self.at = end if line_end < 0 else line_end + 1
            elif text.startswith("/*", self.at):
                close = text.find("*/", self.at + 2)
                self.at = end if close < 0 else close + 2
            else:
                return

    def _cut_at(self, path):
        """The text ends inside the value at `path`. Only the first, and
        deepest, place it ended counts: the levels above it end there
        too."""
        if self.cut is None:
            self.cut = path
            self.damage.append(path)

    def _joins(self, length):
        """Whether `length` characters from here run on into a word, as
        `nullx` and `12px` do: then they are not the word or the number."""
        after = self.at + length
        return after < len(self.text) and (self.text[after].isalnum()
                                           or self.text[after] in "_$.")

    def _value(self, path):
        if self.at >= len(self.text):
            self._cut_at(path)
            return None
        ch = self.text[self.at]
        if ch == "{":
            return self._object(path)
        if ch == "[":
            return self._array(path)
        if ch in "\"'":
            return self._string(path)
        for word, value in _WORDS:
            if self.text.startswith(word, self.at) \
                    and not self._joins(len(word)):
                self.at += len(word)
                return value
        found = _NUMBER.match(self.text, self.at)
        if found and not self._joins(found.end() - self.at):
            self.at = found.end()
            number = found.group().lstrip("+")
            if any(mark in number for mark in ".eE"):
                return float(number)
            return int(number)
        raise _Bad

    def _string(self, path):
        quote = self.text[self.at]
        self.at += 1
        plain = _PLAIN[quote]
        parts = []
        text, end = self.text, len(self.text)
        while True:
            run = plain.match(text, self.at)
            if run:
                parts.append(run.group())
                self.at = run.end()
            if self.at >= end:
                self._cut_at(path)
                return None
            ch = text[self.at]
            if ch == quote:
                self.at += 1
                joined = "".join(parts)
                if any("\ud800" <= c <= "\udfff" for c in joined):
                    # A pair of \u escapes for one character beyond the
                    # BMP, as an ASCII-only save writes it.
                    joined = joined.encode("utf-16", "surrogatepass") \
                        .decode("utf-16", "replace")
                return joined
            if ch in "\r\n":
                raise _Unclosed
            # A backslash.
            if self.at + 1 >= end:
                self._cut_at(path)
                return None
            code = text[self.at + 1]
            if code == "u":
                digits = text[self.at + 2:self.at + 6]
                if len(digits) < 4:
                    self._cut_at(path)
                    return None
                try:
                    parts.append(chr(int(digits, 16)))
                except ValueError:
                    raise _Bad from None
                self.at += 6
            else:
                parts.append(_ESCAPES.get(code, code))
                self.at += 2

    def _key(self, path):
        if self.text[self.at] in "\"'":
            return self._string(path)
        found = _BARE_KEY.match(self.text, self.at)
        if not found:
            raise _Bad
        self.at = found.end()
        return found.group()

    def _starts_key(self, ch):
        return ch in "\"'" or bool(_BARE_KEY.match(ch))

    def _starts_value(self, ch):
        return ch in "{[\"'-+." or ch.isalnum()

    def _skip(self):
        """On to the next comma or closing bracket at the reading
        point's own depth, past whatever does not read."""
        text, end = self.text, len(self.text)
        depth, quote = 0, None
        while self.at < end:
            ch = text[self.at]
            if quote:
                if ch == "\\":
                    self.at += 2
                    continue
                if ch == quote or ch in "\r\n":
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch in "{[":
                depth += 1
            elif ch in "}]":
                if depth == 0:
                    return
                depth -= 1
            elif ch == "," and depth == 0:
                return
            self.at += 1

    def _ends_after(self, value, here, container, close, store):
        """After a value: True where it stands, False where it does not
        and has been dropped; None where the text ended, which ends the
        container too. `store` keeps the value."""
        self._space()
        if self.at >= len(self.text):
            # A string or a bracket closes itself; a number or a word
            # the text ends on may be cut short.
            if isinstance(value, (dict, list, str)):
                store()
                self._cut_at(container)
            else:
                self._cut_at(here)
            return None
        ch = self.text[self.at]
        if ch in ",}]" or (self._starts_key(ch) if close == "}"
                           else self._starts_value(ch)):
            store()
            return True
        self.damage.append(here)
        self._skip()
        return False

    def _object(self, path):
        self.at += 1
        out = {}
        while True:
            self._space()
            start = self.at
            if self.at >= len(self.text):
                self._cut_at(path)
                return out
            ch = self.text[self.at]
            if ch in "}]":
                if ch == "}":
                    self.at += 1
                else:
                    # The brace is missing; the bracket is a parent's.
                    self.damage.append(path)
                return out
            if ch == ",":
                self.at += 1
                continue
            key = None
            try:
                key = self._key(path)
                if self.cut is not None:
                    return out
                self._space()
                if not self.text.startswith(":", self.at):
                    raise _Bad
                self.at += 1
                self._space()
                value = self._value(path + (key,))
            except _Bad as exc:
                self.damage.append(path if key is None else path + (key,))
                if not isinstance(exc, _Unclosed):
                    self._skip()
                if self.at == start:
                    self.at += 1
                continue
            if self.cut is not None:
                if isinstance(value, (dict, list)):
                    out[key] = value        # what it held before the end
                return out

            def store(key=key, value=value):
                out[key] = value
            if self._ends_after(value, path + (key,), path, "}",
                                store) is None:
                return out

    def _array(self, path):
        self.at += 1
        out = []
        while True:
            self._space()
            start = self.at
            if self.at >= len(self.text):
                self._cut_at(path)
                return out
            ch = self.text[self.at]
            if ch in "}]":
                if ch == "]":
                    self.at += 1
                else:
                    self.damage.append(path)
                return out
            if ch == ",":
                self.at += 1
                continue
            here = path + (len(out),)
            try:
                value = self._value(here)
            except _Bad as exc:
                self.damage.append(here)
                if not isinstance(exc, _Unclosed):
                    self._skip()
                if self.at == start:
                    self.at += 1
                continue
            if self.cut is not None:
                if isinstance(value, (dict, list)):
                    out.append(value)
                return out
            if self._ends_after(value, here, path, "]",
                                lambda value=value: out.append(value)) is None:
                return out


# ------------------------------------------------------------- the kinds

def _at(data, path):
    """What stands at `path` in `data`, or None."""
    for key in path:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def _matches(pattern, path):
    return len(pattern) <= len(path) and all(
        want is ANY or want == got for want, got in zip(pattern, path))


def _combatant(res_id, entry=None):
    """A combatant's name for a report: the entry's own hint, else the
    game data's, else the id."""
    if isinstance(entry, dict) and isinstance(entry.get("name_hint"), str) \
            and entry["name_hint"]:
        return entry["name_hint"]
    try:
        from game_data.characters import CHARACTERS
        known = CHARACTERS.get(int(res_id))
    except (ImportError, ValueError, TypeError):
        known = None
    if isinstance(known, dict) and known.get("name"):
        return known["name"]
    return str(res_id)


def _is_object(data):
    """The test of a file whose manager reads any object as far as it
    can."""
    return None if isinstance(data, dict) else \
        "Top-level JSON must be an object."


def _holds_keys(data):
    """Whether any setting is left besides the section markers. A
    setting that reads False or 0 counts: it may differ from its
    default."""
    return any(not str(key).startswith("#") for key in data)


def _holds_anything(data):
    """Whether any section but the version holds something: a file with
    nothing else would only stand in the way of a fresh start."""
    return any(value for key, value in data.items() if key != "version")


def _rehome(data, collection, fits, keep=()):
    """Put records a lost bracket left in the wrong place back into
    `data[collection]`: one beside it at the top, which a missing
    opening brace leaves, or one inside another record, which a missing
    closing brace and the comma read past it leave. `fits(key, value)`
    says whether a value is one of them, as the file's fixed shape
    tells; `keep` are the top-level keys that belong where they are.

    Returns the moves, (old path, new path) in the order made, so the
    damage found on the way can be followed to where it now stands
    (`_remap`). A new path of None is a record dropped, its name taken
    already."""
    moves = []
    home = data.get(collection)
    if not isinstance(home, dict):
        home = data[collection] = {}

    def move(old, key, value):
        if key in home:
            moves.append((old, None))
            return False
        home[key] = value
        moves.append((old, (collection, key)))
        return True

    for key in [k for k in data if k != collection and k not in keep]:
        if fits(key, data[key]):
            move((key,), key, data.pop(key))
    work = [((collection, key), value) for key, value in home.items()]
    while work:
        path, record = work.pop()
        if not isinstance(record, dict):
            continue
        for key in [k for k in record if fits(k, record[k])]:
            value = record.pop(key)
            if move(path + (key,), key, value):
                work.append(((collection, key), value))
    return moves


def _remap(path, moves):
    """Where `path` stands once `moves` are made; None where what it
    pointed into was dropped."""
    for old, new in moves:
        if path[:len(old)] == old:
            if new is None:
                return None
            path = new + path[len(old):]
    return path


def _rehome_presets(data):
    # The file's shape holds no object but a preset's weights, so any
    # object found beside "presets" or inside a preset is a preset.
    return _rehome(data, "presets",
                   lambda name, value: isinstance(value, dict),
                   keep=("selected_preset",))


def _rehome_combatants(data):
    # A combatant's settings are an object under a res_id, and no key
    # inside them is all digits with an object under it.
    return _rehome(data, "characters",
                   lambda key, value: isinstance(key, str) and key.isdigit()
                   and isinstance(value, dict))


def _tidy_presets(data):
    """Take out the presets `PresetManager.load` would refuse the whole
    file over, and name them. A stray weight left where a preset should
    be is a piece of the damaged preset already named, and goes
    unnamed."""
    presets = data.get("presets")
    lost = []
    if isinstance(presets, dict):
        for name in list(presets):
            if preset_manager.preset_problem(name, presets[name]):
                if isinstance(presets.pop(name), dict):
                    lost.append(str(name))
    selected = data.get("selected_preset")
    if selected is not None and not isinstance(selected, str):
        del data["selected_preset"]
    return lost


def _tidy_assignments(data):
    """Take out what `CharacterPresetManager.load` would refuse the
    whole file over, and name the combatants it cost."""
    hints = data.get("name_hints")
    if "name_hints" in data and not isinstance(hints, dict):
        del data["name_hints"]
        hints = None
    lost = []
    assignments = data.get("assignments")
    if isinstance(assignments, dict):
        for key in list(assignments):
            if character_preset_manager.assignment_problem(
                    key, assignments[key]):
                del assignments[key]
                hint = hints.get(key) if isinstance(hints, dict) else None
                lost.append(hint if isinstance(hint, str) and hint
                            else _combatant(key))
    if isinstance(hints, dict):
        for key in list(hints):
            if not isinstance(hints[key], str):
                del hints[key]
    version = data.get("version", 1)
    if isinstance(version, bool) or not isinstance(version, int):
        del data["version"]
    return lost


def _assignment_name(data, parent, key):
    hint = _at(data, ("name_hints", key))
    return hint if isinstance(hint, str) and hint else _combatant(key)


class Kind:
    """One settings file, and what a repair of it has to respect.

    `problem` is its manager's own test of a file, so a repair is held
    to the same rules a load is. `entries` are the places whose members
    a user knows by name: `(pattern, whole, name)`, where damage at or
    under an entry names it in the report, and a WHOLE one is dropped
    rather than kept in part. `rehome` puts misplaced records back
    (`_rehome`), `tidy` takes out what the manager would refuse.
    `holds` says whether what is left is worth saving at all; where it
    is not, the file is set aside, and a shipped default (`shipped`)
    takes its place.
    """

    def __init__(self, name, problem, holds, entries=(), rehome=None,
                 tidy=None, shipped=False):
        self.name = name
        self.problem = problem
        self.holds = holds
        self.entries = entries
        self.rehome = rehome or (lambda data: [])
        self.tidy = tidy or (lambda data: [])
        self.shipped = shipped

    def drop_damaged(self, data, damage, cut=None):
        """Drop every whole entry the damage reached into. Returns
        (names of the entries it cost, how much it cost unnamed). The
        place the text was `cut` costs nothing unnamed: a report says
        the file ends early instead."""
        lost, unnamed = [], 0
        for path in damage:
            found = [entry for entry in self.entries
                     if _matches(entry[0], path)]
            if not found:
                if path != cut:
                    unnamed += 1
                continue
            pattern, whole, name = max(found, key=lambda e: len(e[0]))
            where = path[:len(pattern)]
            parent, key = _at(data, where[:-1]), where[-1]
            label = name(data, parent, key)
            if whole and isinstance(parent, dict) and key in parent:
                del parent[key]
            if label not in lost:
                lost.append(label)
        return lost, unnamed


KINDS = (
    Kind("settings.json", settings_manager.structure_problem, _holds_keys,
         entries=(((ANY,), False, lambda data, parent, key: str(key)),)),
    Kind("presets.json", preset_manager.structure_problem,
         lambda data: bool(data.get("presets")),
         entries=((("presets", ANY), True,
                   lambda data, parent, key: str(key)),),
         rehome=_rehome_presets, tidy=_tidy_presets, shipped=True),
    Kind("character_preset.json",
         character_preset_manager.structure_problem,
         lambda data: bool(data.get("assignments")),
         entries=((("assignments", ANY), False, _assignment_name),),
         tidy=_tidy_assignments, shipped=True),
    Kind("optimizer_settings.json",
         optimizer_settings_manager.structure_problem,
         lambda data: bool(data.get("characters")),
         entries=((("characters", ANY), True,
                   lambda data, parent, key: _combatant(
                       key, parent.get(key) if isinstance(parent, dict)
                       else None)),),
         rehome=_rehome_combatants, shipped=True),
    # Every section of these reads its entries on their own, dropping
    # the ones that do not, so nothing here is whole.
    Kind("checklist.json", _is_object, _holds_anything),
    Kind("log_presets.json", _is_object, _holds_anything),
)


# ---------------------------------------------------------- the repair

class Repair:
    """What `repair_folder` did to one file.

    `outcome` is REPAIRED (what read was saved in its place), SET_ASIDE
    (nothing in it read), UNREAD (it would not open, or would not move)
    or FAILED (the repair itself raised). `kept_as` is the original's
    new name. `lost` names what did not survive, as far as names could
    be read, and `unnamed` counts what did not survive under no
    readable name. `cut` says the file ended early, so whatever came
    after the end is gone as well, and `replaced` that some of its
    bytes were not text and were replaced. `defaults` is filled in once
    the sync has run (`note_defaults`): whether a file stands where a
    set-aside one was.
    """

    def __init__(self, kind, outcome, kept_as=None, lost=(), unnamed=0,
                 cut=False, replaced=False, error=None):
        self.name = kind.name
        self.shipped = kind.shipped
        self.outcome = outcome
        self.kept_as = kept_as
        self.lost = list(lost)
        self.unnamed = unnamed
        self.cut = cut
        self.replaced = replaced
        self.error = error
        self.defaults = False

    @property
    def cost_something(self):
        return bool(self.lost or self.unnamed or self.cut or self.replaced)

    def describe(self):
        """One paragraph for the report."""
        if self.outcome == UNREAD:
            return (f"{self.name} could not be read ({self.error}). "
                    f"Nothing is saved to it until it can be: restart the "
                    f"program once it can.")
        if self.outcome == FAILED:
            return f"{self.name} could not be checked ({self.error})."
        kept = f"The original is kept as {self.kept_as}."
        if self.outcome == SET_ASIDE:
            instead = ("the shipped defaults are in its place"
                       if self.defaults else "it starts afresh")
            return f"{self.name}: nothing in it could be read, so " \
                   f"{instead}. {kept}"
        if not self.cost_something:
            return f"{self.name} was repaired, with nothing lost. {kept}"
        out = [f"{self.name} was repaired."]
        if self.lost or self.unnamed:
            shown = self.lost[:_NAMES_SHOWN]
            more = len(self.lost) - len(shown) + self.unnamed
            if shown:
                names = ", ".join(shown)
                tail = f", and {more} more" if more else ""
                out.append(f"Not recovered: {names}{tail}.")
            else:
                out.append("Some of what it held could not be recovered.")
        if self.cut:
            out.append("It ends early, so whatever followed is gone too.")
        if self.replaced:
            out.append("Some of its characters could not be read, and "
                       "were replaced.")
        out.append(kept)
        return " ".join(out)


def _decode(raw):
    """The text, and how it had to be read: "utf-8" as every manager
    reads it, "bom" past a byte-order mark, "ansi" in the system's code
    page, "damaged" with what would not decode replaced."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    else:
        if text.startswith("\ufeff"):
            return text[1:], "bom"
        return text, "utf-8"
    text = raw.decode("utf-8", errors="replace").lstrip("\ufeff")
    if any(ord(ch) > 0x7F and ch != "\ufffd" for ch in text):
        # Some of it decodes as more than ASCII, so it IS UTF-8, and
        # what does not decode is damage rather than another encoding.
        return text, "damaged"
    # The ANSI code page itself: `getencoding` is not masked by UTF-8
    # mode, where `getpreferredencoding` answers utf-8.
    ansi = getattr(locale, "getencoding", None)
    try:
        return raw.decode(ansi() if ansi else
                          locale.getpreferredencoding(False)), "ansi"
    except (UnicodeDecodeError, LookupError):
        return text, "damaged"


def _strict(text):
    try:
        return json.loads(text)
    except ValueError:
        return None


def repair_file(folder, kind):
    """Repair `kind`'s file in `folder`, or set it aside. A `Repair`, or
    None where the file is missing or reads as it is."""
    path = Path(folder) / kind.name
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return Repair(kind, UNREAD, error=str(exc))
    text, how = _decode(raw)
    data = _strict(text)
    if data is not None and how == "utf-8" and kind.problem(data) is None:
        return None
    damage, cut_at, cut = [], None, False
    if data is None:
        reader = Reader(text)
        data = reader.read()
        damage, cut_at, cut = reader.damage, reader.cut, reader.truncated
    lost, unnamed = [], 0
    if isinstance(data, dict):
        # Records back in place FIRST, and the damage followed there: a
        # damaged preset left beside "presets" is still dropped whole.
        moves = kind.rehome(data)
        damage = [p for p in (_remap(p, moves) for p in damage)
                  if p is not None]
        if cut_at is not None:
            cut_at = _remap(cut_at, moves)
        lost, unnamed = kind.drop_damaged(data, damage, cut_at)
        lost += [name for name in kind.tidy(data) if name not in lost]
    keep = (isinstance(data, dict) and kind.problem(data) is None
            and kind.holds(data))
    try:
        kept = set_aside(path)
    except OSError as exc:
        return Repair(kind, UNREAD, error=f"it could not be moved aside: "
                                          f"{exc}")
    if not keep:
        return Repair(kind, SET_ASIDE, kept_as=kept.name)
    try:
        write_json(path, data, indent=2, ensure_ascii=False)
    except OSError:
        # The original is safe beside it, and with nothing in its place
        # the sync and the managers start it afresh.
        return Repair(kind, SET_ASIDE, kept_as=kept.name)
    return Repair(kind, REPAIRED, kept_as=kept.name, lost=lost,
                  unnamed=unnamed, cut=cut, replaced=how == "damaged")


def repair_folder(folder):
    """Every file in `KINDS` in `folder` that did not read as it was,
    repaired or set aside. The `Repair`s, in `KINDS` order; empty is
    the normal case."""
    out = []
    for kind in KINDS:
        try:
            done = repair_file(folder, kind)
        except Exception as exc:        # never the reason a launch fails
            done = Repair(kind, FAILED, error=f"{type(exc).__name__}: {exc}")
        if done is not None:
            out.append(done)
    return out


def note_defaults(repairs, folder):
    """Once the sync has run: which set-aside files have a default in
    their place now."""
    for repair in repairs:
        if repair.outcome == SET_ASIDE:
            repair.defaults = (Path(folder) / repair.name).exists()


def salvage(path):
    """What `path` holds, read as leniently as a repair reads it, with
    nothing written: a dict, or None. For a reader that runs before
    `repair_folder` can."""
    try:
        raw = Path(path).read_bytes()
    except OSError:
        return None
    text, _how = _decode(raw)
    data = _strict(text)
    if data is None:
        data = Reader(text).read()
    return data if isinstance(data, dict) else None
