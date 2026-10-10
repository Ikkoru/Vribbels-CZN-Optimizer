"""The game client's own tables and English text, read from its install.

What changes every patch and the server never sends: each event's
English name, every item's, and how many Excursion types each
combatant has.
`docs/client_data.md` says where each is kept and how it was held
against what the program already knew; `docs/client_tables.py` is the
maintainer's tool over the same reader. Reads only: nothing here
writes inside the install.

**Read once per game build.** What is read goes to `CACHE_FILE` in the
settings folder, keyed by the build the client's manifest states, so
the launch after a patch reads the client again and every other launch
reads the cache. A read decompresses and decrypts the whole English
text table, so it runs on a worker (`OptimizerGUI._start_client_read`).

**Three sources, the first that knows an id winning**: what this
machine's client says, then `game_data/from_client.py` -- the same
reading as of the build the program shipped with, written by
`docs/client_tables.py --ship` -- then nothing, where the caller falls
back to the id. A player whose client is not installed, or moved where
nothing finds it, sees the shipped names.

Two formats, both read as the ripper reads them
(github.com/cznrip/Chaos-Zero-Nightmare-ASSet-Ripper, MIT), which is
the reference when a patch changes either:

* **The archive** (`Archive`): `manifest.ssra` indexes every file; a
  file is a zstd frame at an offset into its GROUP's stream, the
  group's `.ssrc` chunks laid end to end in chunk-id order.
* **A table** (`table`): XORed with a repeating 256-byte key, then a
  container of named blobs -- row count, column names, and a row's
  values separated by zero bytes. The key is READ OFF THE DATA rather
  than written here, so a patch that changes it changes nothing.

**Every structural assumption is checked and fails by name**: a
manifest version or a table header this was not written against
raises saying which, rather than reading garbage -- and a launch that
meets one keeps the shipped names.
"""

import collections
import json
import re
import struct
from pathlib import Path

try:
    from compression import zstd
except ImportError:                  # Python before 3.14: no reading
    zstd = None

from json_file import write_json

# STOVE's default install, and the uninstall entry naming where the
# game really went: its icon is the loader under `bin`.
DEFAULT_INSTALL = Path(r"C:\ProgramData\Smilegate\Games\ChaosZeroNightmare")
UNINSTALL_KEY = (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
                 r"\Stove App STOVE_CHAOSZERO")
GAMERES = Path("bin") / "appdata" / "cznlive" / "gameres"

# What the cache is called in the settings folder, and the shape of
# what it holds. A cache of another format is read as no cache.
CACHE_FILE = "game_client.json"
CACHE_FORMAT = 2

# The manifest layout this reads. A different version is a different
# layout until shown otherwise.
SSRA_VERSION = 4
SSRA_HEADER = "<4s5I5Q"      # magic, version, build, chunks, files,
                             # flags, then string table offset and size,
                             # chunk and file table offsets, one more
CHUNK_ENTRY = "<IHHQQQ"      # id, group, -, length, stored length, -
FILE_ENTRY = "<IIQIIIIBBHI"  # -, -, offset, stored, length, -, name,
                             # compressed, encrypted, group, flags
DELETED = 1                  # a file entry's flag bit

# A table's magic once decrypted, and its header's own stated size.
MAGIC = b"PLPcK"
TABLE_HEADER = "<5sBHBQIIBIQ"
TABLE_HEADER_SIZE = 0x26

# The table the key is read from: large enough that every one of the
# 256 positions holds thousands of bytes, most of them zero.
KEY_SOURCE = "text/en/text.db"
TEXT_TABLE = "text/en/text.db"

# The columns of `event@event` that name what a row is the event OF.
# The wire's schedule id turns up in one of them, which one depending
# on the kind of event, and the row's `title` is its name.
EVENT_JOINS = ("id", "link_event_schedule_id", "multiple_link",
               "multiple_key")
EVENT_TABLE = "event@event"
EVENT_DELETED = ("delete_flag", "YES")

# Schedules with no row of their own in `event@event`, and the table
# naming each: (table, column holding the schedule id, column holding
# the name's text id). A trauma code's schedule reaches its event row
# through the code's own id instead (`_trauma_codes`).
EVENT_NAME_TABLES = (
    # The returning players' events.
    ("life_cycle_event_content@life_cycle_event_content",
     "multiple_link", "title"),
    # A countdown check-in, such as the Nightmare Carnival's.
    ("countdown_attendance@countdown_attendance_define",
     "id", "content_desc"),
)
TRAUMA_CODE_TABLE = "event_trauma_code@event_trauma_code"

# A schedule numbered among others of its kind -- `event_combatant_
# trial_15` among the trials -- that no table names, named after its
# kind where every named member shares one name.
FAMILY_NUMBER = re.compile(r"_\d+$")

# Every Combatant Trial is called the same, and two run at once: each
# is named for the combatant it features, its first slot's.
TRIAL_TABLE = "event_combatant_trial@event_combatant_trial"
TRIAL_LEAD = "slot_1_link_event_combatant_trial_slot_id"
TRIAL_SLOT = re.compile(r"combatant_trial_(\d+)")
COMBATANT_NAME = "char_base@name@%s"
TRIAL_NAME = "%s - %s"           # the trial's name, then the combatant

# Where a combatant's Excursion types are listed: one row each, and
# the row's `group` is `normal_visit_<res_id>`.
VISIT_TABLE = "town_visit@town_normal_visit"
VISIT_GROUP = re.compile(r"normal_visit_(\d+)")

# An item's English name: the text `item@name@<res_id>`, one for every
# item the game has, whichever item table holds its row.
ITEM_NAME = re.compile(r"item@name@(\d+)")

# Markup the text carries for the game's own renderer.
MARKUP = re.compile(r"<[^>]*>")


def _cstr(blob, offset):
    return blob[offset:blob.find(b"\0", offset)].decode("utf-8", "replace")


class Archive:
    """The client's archive: its index, and any file in it by path."""

    def __init__(self, install=DEFAULT_INSTALL):
        self.root = Path(install) / GAMERES
        data = (self.root / "manifest.ssra").read_bytes()
        (magic, version, self.build, chunks, files, _flags, str_off,
         str_size, chunk_off, file_off, _extra) = _header(data)
        strings = data[str_off:str_off + str_size]
        self.groups = self._groups(data, str_off + str_size)
        self.streams = self._streams(data, chunk_off, chunks)
        self.files = {}
        for i in range(files):
            (_h, _u, offset, stored, length, _u2, name_off, compressed,
             encrypted, group, flags) = struct.unpack_from(
                FILE_ENTRY, data, file_off + i * struct.calcsize(FILE_ENTRY))
            if flags & DELETED:
                continue
            name = _cstr(strings, name_off).replace("\\", "/").strip("/")
            self.files[name] = (group, offset, stored, length,
                                bool(compressed), bool(encrypted))

    @staticmethod
    def _groups(data, at):
        """{group index: name}: `lang_en`, `base`, and so on. A chunk is
        named after its group, and only the groups the player installed
        have chunks on disk."""
        if data[at:at + 4] != b"GRPS":
            raise ValueError("no GRPS group table after the strings")
        count, _size = struct.unpack_from("<II", data, at + 4)
        names = at + 16 + count * 24
        return {idx: _cstr(data, names + name_off)
                for idx, name_off in (struct.unpack_from("<H2xI", data,
                                                         at + 16 + i * 24)
                                      for i in range(count))}

    def _streams(self, data, at, count):
        """{group: [(start, length, chunk file or None)]}. A chunk is
        matched to its file by STORED SIZE, not name: sizes are unique
        where names are not -- a group's chunk numbering skips where one
        is split in two parts."""
        by_size = collections.defaultdict(list)
        for path in (self.root / "chunks").glob("*.ssrc"):
            by_size[path.stat().st_size].append(path)
        laid = collections.defaultdict(list)
        size = struct.calcsize(CHUNK_ENTRY)
        for i in range(count):
            cid, group, _u, length, stored, _chk = struct.unpack_from(
                CHUNK_ENTRY, data, at + i * size)
            files = by_size.get(stored, [])
            laid[group].append((cid, length,
                                files[0] if len(files) == 1 else None))
        out = {}
        for group, chunks in laid.items():
            start, spans = 0, []
            for _cid, length, path in sorted(chunks):
                spans.append((start, length, path))
                start += length
            out[group] = spans
        return out

    def read(self, name):
        """The file's bytes, decompressed."""
        group, offset, stored, length, compressed, encrypted = \
            self.files[name]
        if encrypted:
            raise ValueError(f"{name} is encrypted, which this does not "
                             f"read")
        if compressed and zstd is None:
            raise RuntimeError("reading the client needs Python 3.14's "
                               "compression.zstd")
        want = stored if compressed else length
        out = bytearray()
        for start, size, path in self.streams[group]:
            if start + size <= offset or offset + want <= start:
                continue
            if path is None:
                raise FileNotFoundError(
                    f"{name} is in group {self.groups.get(group)}, whose "
                    f"chunks are not installed")
            lo = max(offset, start) - start
            hi = min(offset + want, start + size) - start
            with open(path, "rb") as handle:
                handle.seek(lo)
                out += handle.read(hi - lo)
        blob = zstd.decompress(bytes(out)) if compressed else bytes(out)
        if len(blob) != length:
            raise ValueError(f"{name} read {len(blob)} bytes, its entry "
                             f"says {length}")
        return blob


def _header(data):
    """The manifest header's fields, checked for the layout this reads."""
    fields = struct.unpack_from(SSRA_HEADER, data, 0)
    if fields[0] != b"SSRA":
        raise ValueError(f"manifest.ssra starts {fields[0]!r}, not SSRA")
    if fields[1] != SSRA_VERSION:
        raise ValueError(
            f"manifest.ssra is version {fields[1]}; this reads "
            f"{SSRA_VERSION}. Compare the ripper's SSRArchive.cpp.")
    return fields


def build_of(install):
    """The game build an install's manifest states, or None.

    Reads the header alone, which is what lets a launch tell a cache
    still good from one a patch has outdated without reading the
    client.
    """
    try:
        with open(Path(install) / GAMERES / "manifest.ssra", "rb") as f:
            return _header(f.read(struct.calcsize(SSRA_HEADER)))[2]
    except (OSError, ValueError, struct.error):
        return None


def key_of(raw):
    """The repeating XOR key, aligned to `raw`'s start: the commonest
    byte at each of the 256 positions, a table being mostly zero bytes.
    Only a large table has enough of them at every position."""
    return bytes(collections.Counter(raw[k::256]).most_common(1)[0][0]
                 for k in range(256))


def _aligned(raw, key):
    """`key` turned to where `raw` starts: every table is XORed with the
    same 256 bytes, each from a position of its own."""
    for r in range(256):
        turned = key[r:] + key[:r]
        if all(raw[j] ^ turned[j] == MAGIC[j] for j in range(len(MAGIC))):
            return turned
    return None


def _decrypt(raw, key):
    key = _aligned(raw, key) if key else None
    key = key or key_of(raw)
    whole = (key * (len(raw) // 256 + 1))[:len(raw)]
    plain = (int.from_bytes(raw, "little")
             ^ int.from_bytes(whole, "little")).to_bytes(len(raw), "little")
    if not plain.startswith(MAGIC):
        raise ValueError("no rotation of the key turns this into a "
                         "PLPcK table: the cipher has changed")
    return plain


def _blobs(plain):
    """{name: data} of a decrypted table: a hash table of 40-bit
    offsets, each the head of a chain of (name, data) entries."""
    (_magic, _version, size, _u, _u1, _default, slots, hi, lo,
     _u5) = struct.unpack_from(TABLE_HEADER, plain, 0)
    if size != TABLE_HEADER_SIZE:
        raise ValueError(f"table header says {size:#x} bytes, not "
                         f"{TABLE_HEADER_SIZE:#x}: compare the ripper's "
                         f"DBParser.cpp")
    at = (hi << 32) + lo
    root_size, kind = struct.unpack_from("<IB", plain, at)
    if kind != 1 or root_size != 5 * (slots + 1):
        raise ValueError("a table's root entry is not its hash table")
    out = {}
    for i in range(slots):
        hi, lo = struct.unpack_from("<BI", plain, at + 5 + i * 5)
        entry = (hi << 32) + lo
        while entry:
            (_s, _k, name_len, data_len, nhi,
             nlo) = struct.unpack_from("<IBBIBI", plain, entry)
            start = entry + 15
            out[plain[start:start + name_len]] = plain[
                start + name_len:start + name_len + data_len]
            entry = (nhi << 32) + nlo
    return out


def table(raw, key=None):
    """(column names, rows as {column: text}) of a table's bytes. `key`
    is the master key (`key_of` a large table): a small table has too
    few bytes at each position to give its own."""
    blobs = _blobs(_decrypt(raw, key))
    count = struct.unpack_from("<I", blobs[b"\trows"])[0]
    width = struct.unpack_from("<I", blobs[b"\tcols"])[0]
    columns = [blobs[b"\t%d" % i].rstrip(b"\0").decode("utf-8", "replace")
               for i in range(width)]
    rows = []
    for r in range(count):
        values = blobs.get(blobs.get(b"\t\t%d" % r), b"").split(b"\0")
        rows.append({column: values[i].decode("utf-8", "replace")
                     if i < len(values) else ""
                     for i, column in enumerate(columns)})
    return columns, rows


class Client:
    """The archive, the master key and the English text, read once."""

    def __init__(self, install=DEFAULT_INSTALL):
        self.archive = Archive(install)
        self.key = key_of(self.archive.read(KEY_SOURCE))
        self._text = None

    def table(self, name):
        """`name` as the archive names it without `db/` and `.db`."""
        return table(self.archive.read(f"db/{name}.db"), self.key)

    def rows(self, name):
        """A table's rows alone."""
        return self.table(name)[1]

    def text(self):
        """{text id: English}. A text id is mostly `<table>@<column>@<row
        id>`, and a table's own text columns hold exactly that id."""
        if self._text is None:
            _columns, rows = table(self.archive.read(TEXT_TABLE), self.key)
            self._text = {row["id"]: row["text"] for row in rows}
        return self._text


def clean(text):
    """A name as the program can draw it: the game's markup taken out,
    and every character past U+FFFF, which costs Tk a search of every
    installed font the first time one is drawn
    (`checks/check_bmp_glyphs.py`)."""
    text = MARKUP.sub("", text or "")
    text = "".join(ch for ch in text if ord(ch) <= 0xFFFF)
    return " ".join(text.split())


def event_names(client):
    """{schedule id: English name} for every event the client names.

    Keyed by everything a row of `event@event` is the event OF, which
    is a superset of the schedule ids the wire sends. A key two rows
    share takes the live row's title over a deleted one's.
    """
    texts = client.text()
    names = {}

    def put(key, text_id):
        name = clean(texts.get(text_id))
        if key and key not in ("none", "-1") and name:
            names.setdefault(key, name)

    events = sorted(client.rows(EVENT_TABLE),
                    key=lambda row: row.get(EVENT_DELETED[0])
                    == EVENT_DELETED[1])
    for row in events:
        for column in EVENT_JOINS:
            put(row.get(column), row.get("title"))
    for row in client.rows(TRAUMA_CODE_TABLE):
        name = names.get(row.get("id"))
        if name:
            names.setdefault(row.get("link_trauma_code_schedule_id"), name)
    for name, key, title in EVENT_NAME_TABLES:
        for row in client.rows(name):
            put(row.get(key), row.get(title))
    trials = {}
    for row in client.rows(TRIAL_TABLE):
        trial = row.get("id") or ""
        lead = TRIAL_SLOT.match(row.get(TRIAL_LEAD) or "")
        who = clean(texts.get(COMBATANT_NAME % lead.group(1))) if lead \
            else ""
        base = names.get(trial) or family_name(trial, names)
        if base and who:
            trials[trial] = TRIAL_NAME % (base, who)
    names.update(trials)
    return names


def family_name(schedule_id, names):
    """The name every named schedule of `schedule_id`'s kind shares, or
    None. `event_combatant_trial_15` is a trial whatever its number."""
    stem = FAMILY_NUMBER.sub("", schedule_id)
    if stem == schedule_id:
        return None
    shared = {name for key, name in names.items()
              if FAMILY_NUMBER.sub("", key) == stem and key != stem}
    return shared.pop() if len(shared) == 1 else None


def excursion_types(client):
    """{combatant res_id: how many Excursion types it has}.

    A partner, and a combatant not yet released, has a single row,
    which is a placeholder rather than a list of one: those are left
    out.
    """
    out = collections.Counter()
    for row in client.rows(VISIT_TABLE):
        match = VISIT_GROUP.fullmatch(row.get("group") or "")
        if match:
            out[int(match.group(1))] += 1
    return {res_id: count for res_id, count in out.items() if count > 1}


def item_names(client):
    """{item res_id: English name} for every item the client names."""
    out = {}
    for key, text in client.text().items():
        match = ITEM_NAME.fullmatch(key)
        name = clean(text) if match else ""
        if name:
            out[int(match.group(1))] = name
    return out


def read_facts(install):
    """Everything this module reads off an install, as the cache holds
    it. Raises whatever the reading meets."""
    client = Client(install)
    return {
        "format": CACHE_FORMAT,
        "install": str(install),
        "build": client.archive.build,
        "event_names": event_names(client),
        "item_names": {str(res_id): name for res_id, name
                       in item_names(client).items()},
        "excursion_types": {str(res_id): count for res_id, count
                            in excursion_types(client).items()},
    }


def find_install(setting=None):
    """Where the game is installed, or None.

    `setting` first, a folder the user named; then the folder STOVE's
    uninstall entry names; then STOVE's default. The first holding a
    manifest wins.
    """
    for candidate in (setting, _registered(), DEFAULT_INSTALL):
        if candidate and build_of(candidate) is not None:
            return Path(candidate)
    return None


def _registered():
    """The install folder STOVE registered, or None."""
    try:
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, UNINSTALL_KEY) as key:
                    icon = winreg.QueryValueEx(key, "DisplayIcon")[0]
            except OSError:
                continue
            loader = Path(str(icon).split(",")[0].strip('"'))
            if loader.parent.name.lower() == "bin":
                return loader.parent.parent
    except ImportError:
        pass
    return None


def cached(settings_dir, install):
    """The cache's facts if they were read off this install at its
    current build, else None."""
    if install is None:
        return None
    try:
        held = json.loads((Path(settings_dir) / CACHE_FILE).read_text(
            encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (not isinstance(held, dict) or held.get("format") != CACHE_FORMAT
            or held.get("install") != str(install)
            or held.get("build") != build_of(install)):
        return None
    return held


def refresh(settings_dir, install):
    """Read the install and save what was read to the cache. Returns
    the facts. Raises whatever the reading meets; a cache that will not
    save is left, the facts being good for this session either way."""
    facts = read_facts(install)
    try:
        write_json(Path(settings_dir) / CACHE_FILE, facts)
    except OSError:
        pass
    return facts


# What this machine's client said, once read. Replaced whole, never
# changed in place: the worker that reads it hands it over by
# assignment, which a reader on the Tk thread can never see half done.
_facts = None


def use(facts):
    """Make `facts` (from `cached` or `refresh`) what the accessors
    read. None goes back to the shipped tables alone."""
    global _facts
    _facts = facts if isinstance(facts, dict) else None


def event_name(schedule_id):
    """An event's English name, or None where nothing names it."""
    from game_data import from_client
    own = (_facts or {}).get("event_names") or {}
    for names in (own, from_client.EVENT_NAMES):
        name = names.get(schedule_id)
        if name:
            return name
    for names in (own, from_client.EVENT_NAMES):
        name = family_name(schedule_id, names)
        if name:
            return name
    return None


def known_item_names():
    """{item res_id: English name}: the shipped table, with what this
    machine's client says over it. The program's own names go over
    both (`game_data.constants.item_names`)."""
    from game_data import from_client
    out = dict(from_client.ITEM_NAMES)
    for res_id, name in ((_facts or {}).get("item_names") or {}).items():
        if str(res_id).isdigit() and name:
            out[int(res_id)] = name
    return out


def visit_types(res_id):
    """How many Excursion types a combatant has, or None."""
    from game_data import from_client
    own = (_facts or {}).get("excursion_types") or {}
    count = own.get(str(res_id)) or from_client.EXCURSION_TYPES.get(res_id)
    return count if isinstance(count, int) and count > 0 else None
