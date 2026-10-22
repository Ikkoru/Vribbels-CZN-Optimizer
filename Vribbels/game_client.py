"""The game client's own tables and English text, read from its install.

What changes every patch and the server never sends: each event's
English name and how many rewards it holds, every trial's slots and
every payment event's tiers, every item's name, how
many Excursion types each combatant has, what each daily task counts
to and pays toward the day's Activity, each Memory Fragment set's
effect, the words of each combatant's own Potential nodes, every
combatant's and partner's figures, the Chaos and Zero System names,
the Normal Rescues' 5-stars, the exp each level and each Affinity
level takes, the main stats each Memory Fragment slot carries, every
item's rarity and every class's name.
`docs/client_data.md` says where each is kept and how it was held
against what the program already knew; `docs/client_tables.py` is the
maintainer's tool over the same reader. Reads only: nothing here writes
inside the install.

**Read once per game build.** What is read goes to `CACHE_FILE` in the
settings folder, keyed by the build the client's manifest states, so
the launch after a patch reads the client again and every other launch
reads the cache. A read decompresses and decrypts the whole English
text table, so it runs on a worker (`OptimizerGUI._start_client_read`).

**Three sources, the first that knows an id winning**: what this
machine's client says, then `game_data/from_client.py` -- the same
reading as of the build the program shipped with, written by
`docs/client_tables.py --ship` -- then nothing, where the caller falls
back to the id. Where this build cannot be read, or the client is not
found, the cache of an earlier build stands in for the first while it
is newer than the shipped tables (`fallback`); otherwise the shipped
names show.

`client_archive` keeps every build's whole data besides, where the
maintainer opted in.

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
# what it holds. A cache of another format is read as no cache, so a
# reader that changes what it reads raises this: every install then
# reads its client again once, rather than at the next patch.
CACHE_FILE = "game_client.json"
CACHE_FORMAT = 19

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

# A special event, such as the 1st anniversary's Nightmare Carnival: a
# define row naming the whole's schedule, and a content row for each
# event inside it, `<the define's content key>_<n>`, naming that
# event's schedule and its title. The whole is named by the title of
# the top-menu page its contents open (`link_top_menu_id`), and each
# event inside it as `<the whole> - <its title>`: a title alone --
# Attendance Check, Exchange -- says nothing of which event it is.
SPECIAL_DEFINE_TABLE = "special_event@special_event_define"
SPECIAL_CONTENT_TABLE = "special_event@special_event_content"
SPECIAL_LINKS = ("multiple_link", "link_event_schedule_id")
TOP_MENU_TABLE = "top_menu@top_menu"
SPECIAL_PART_NAME = "%s - %s"    # the whole's name, then the part's
NO_LINK = ("", "none", "-1")

# A schedule numbered among others of its kind -- `event_combatant_
# trial_15` among the trials -- that no table names, named after its
# kind where every named member shares one name. A number at a time,
# nearest first: `event_combatant_trial_18_1` has no named `_18_`
# kin, and is a trial.
FAMILY_NUMBER = re.compile(r"_\d+$")

# Every Combatant Trial is called the same, and two run at once: each
# is named for the combatant it features, its first slot's.
TRIAL_TABLE = "event_combatant_trial@event_combatant_trial"
TRIAL_LEAD = "slot_1_link_event_combatant_trial_slot_id"
TRIAL_SLOT = re.compile(r"combatant_trial_(\d+)")
COMBATANT_NAME = "char_base@name@%s"
TRIAL_NAME = "%s - %s"           # the trial's name, then the combatant
# Every slot a trial offers, `slot_<n>_...`: a trial is as many rewards
# as it has slots, two for the ★4s beside a banner and one for its ★5.
TRIAL_SLOT_COLUMN = re.compile(r"slot_\d+_link_event_combatant_trial_slot_id")

# A combatant's own information page: a row each, `<res_id>_info`,
# naming the partner the game recommends for it.
COMBATANT_INFO_TABLE = "combatant_info@combatant_info"
COMBATANT_INFO_ROW = re.compile(r"(\d+)_info")

# Where a combatant's Excursion types are listed: one row each, and
# the row's `group` is `normal_visit_<res_id>`.
VISIT_TABLE = "town_visit@town_normal_visit"
VISIT_GROUP = re.compile(r"normal_visit_(\d+)")

# The text key most items' names sit under, `item@name@<res_id>`: what
# names an id no item row names (`item_names`, which reads each row's
# own `name` column first).
ITEM_NAME = re.compile(r"item@name@(\d+)")
# What a name holds that a placeholder does not: a letter or a digit.
# The client can name an unreleased item `???`, which is no name to put
# over one the program has.
NAMING = re.compile(r"\w")

# Where an event's rewards are listed. A mission row per reward, by the
# event's id; a step track's ladder, by its one mission's id; and the
# define row whose special reward is the final one, unlocking after
# every other.
MISSION_TABLE = "event_mission@event_mission"
STEP_TABLE = "event_mission@event_mission_reward"
DEFINE_TABLE = "event_mission@event_mission_define"
NO_REWARD = ("-1", "", "none")
# A check-in's days: a row per day, `<the define's key>_<day>`.
CHECK_IN_DEFINES = "event_daily_check@event_daily_check_define"
CHECK_IN_DAYS = "event_daily_check@event_daily_check"
# A countdown check-in's days, the same way: `<its day key>_<day>`.
COUNTDOWN_DEFINES = "countdown_attendance@countdown_attendance_define"
COUNTDOWN_DAYS = "countdown_attendance@countdown_attendance_day"
# A payment event, the Nightmare Carnival's Exchange: tiers of a token
# earned by spending money, a row per tier, `<the define's reward
# key>_<n>`, each with the tokens it takes (`point`). The define names
# the token (`link_item_id`) and the schedule.
PAYMENT_DEFINES = "event_payment_define@event_payment_define"
PAYMENT_TIERS = "event_payment_reward@event_payment_reward"
# A Trauma Code's event rewards: an achievement per reward, `<the
# code's achievement key>_<n>`, and its sticker (`style_link_item_id`)
# once every one is claimed. Its row is `TRAUMA_CODE_TABLE`'s.
TRAUMA_ACHIEVEMENTS = "trauma_code_achievement@trauma_code_achievement"

# What the Checklist counts up to, where the client states it: the
# day's Activity tiers, the weekly currencies' grants and caps, each
# Arkhianon Supply's weekly EXP, top level and daily missions, the
# Simulation Challenges' weekly runs, each Full-Scale Offensive's
# bosses and stars, each Zero System reward track's top level, each
# Galactic Disaster season's weekly score, the Great Rift's top weekly
# tier, each Overclock's daily runs, the Galactic Disaster's constants
# -- its shop pages' day offsets among them -- and the day's
# Communication Passes with the town research that raises them. See
# `limits`.
ACTIVITY_TIERS = "guide_daily@guide_daily"
WEEKLY_CHARGES = "currency_charge@currency_charge"
PASS_TABLE = "season_pass@season_pass"
PASS_MISSIONS = "season_pass_mission@season_pass_mission"
SIMULATION_TABLE = "simulation_content_define@simulation_content_define"
OFFENSIVE_DEFINES = "remnants_boss_penalty_define@remnants_boss_penalty_define"
OFFENSIVE_STAGES = "remnants_boss_penalty_list@remnants_boss_penalty_list"
OFFENSIVE_REWARDS = "remnants_reward@remnants_reward"
MATRIX_LISTS = "zero_reward@zero_reward_list"
MATRIX_LEVELS = "zero_reward@zero_reward"
DISASTER_SEASONS = "disaster_season@disaster_season"
RIFT_TIERS = "disaster_rank_score_reward@disaster_rank_score_reward"
OVERCLOCK_TABLE = "event_overclock@event_overclock"
DISASTER_CONSTANTS = "disaster_constant_meta@disaster_constant_meta"
# The passes Excursions and Counseling share: the town's base allowance,
# and the research nodes of the effect that raises it, one row per
# level.
TOWN_CONSTANTS = "town_constant_meta@town_constant_meta"
VISIT_TICKET_BASE = "town_visit_ticket_max"
RESEARCH_LEVELS = "town_research_node_level@town_research_node_level"
VISIT_TICKET_EFFECT = "VISIT_TICKET_MAX__NUM"
# The columns of `event@event` that carry a schedule's id. Its own `id`
# is the event's number, never a schedule, and kept out so a family
# worked out over these keys holds instalments and nothing else.
SCHEDULE_JOINS = ("link_event_schedule_id", "multiple_link", "multiple_key")

# An event that is a chapter of the story map: its `event@event` row's
# `multiple_link` names the chapter, the chapter's node key starts every
# one of its episodes' ids (`<key>_<n>`), and a node marked `no_use` is
# not one of them. The wire lists the episodes cleared by the same ids.
STORY_EVENT_TYPE = "EVENT_STORY_SHORTCUT"
STORY_CHAPTER_TABLE = "story_map@story_map_chapter"
STORY_NODE_TABLE = "story_map@story_map_node"
STORY_NODE_UNUSED = ("no_use", "YES")

# The daily tasks: a row per task, `count` what its score has to reach
# and `point_count` what it then adds to the day's Activity. The wire's
# `daily_achieve` rows carry the score and nothing else.
DAILY_TASK_TABLE = "daily_achievement@daily_achievement"

# The Memory Fragment sets: a row each, `set_public_<n>` for the wire's
# set id n. A row with an `order` is a set fragments drop in;
# `set_option_type` is how many pieces complete it, and the matching
# `set<pieces>_*` columns hold its effect -- a stat id and figure where
# the type is SET_STAT, its words in the text either way.
SET_TABLE = "piece_set_option@piece_set_option"
SET_ID = re.compile(r"set_public_(\d+)")
SET_STAT = "SET_TYPE_STAT"

# The potential tree: a row per node and level, `node_num` the wire's
# node as `<n>_<m>` (70 is `7_0`), `desc` its text, and
# `link_potential_node_effect_id` the effect rows it applies. Some
# combatants have two trees listed, and the one the game draws is the
# reworked one, whose rows have the higher ids (`live_nodes`).
NODE_TABLE = "potential_node@potential_node"
NODE_EFFECT_TABLE = "potential_node@potential_node_effect"
# The nodes whose effect is the combatant's own, by `node_num`, and the
# wire number the program knows each by. Every other node's text is
# shared, and the program words those itself.
OWN_TEXT_NODES = {"7_0": 70, "5_1": 51}

# The client's words for what `game_data` spells its own way: a class,
# an attribute (`link_ego_type_id`, a colour), a combatant's grade. A
# class's own name in the text (`class_names`) goes over CLASS_NAMES.
CLASS_NAMES = {"striker": "Striker", "vanguard": "Vanguard",
               "hunter": "Hunter", "ranger": "Ranger",
               "psionic": "Psionic", "controller": "Controller"}
ATTRIBUTE_NAMES = {"RED": "Passion", "PURPLE": "Void", "ORANGE": "Instinct",
                   "GREEN": "Order", "BLUE": "Justice"}
COMBATANT_GRADES = {"RARITY_SR": 4, "RARITY_SSR": 5}
# A partner's grade is in its level curve's name: `dev_level_<rank>`,
# with `_def` for the defensive classes. `ssr` is the 5-star Arkhianon
# Supply partner, which `game_data` grades 4.5.
PARTNER_GRADE = re.compile(r"dev_level_(r|sr|ssr|sssr)(?:_|$)")
PARTNER_GRADES = {"r": 3, "sr": 4, "ssr": 4.5, "sssr": 5}
# A combatant's level-60 stats: the level-1 figure, every level's step
# up to 60, and the five promotions; levels 61 and 62 step on from 60.
TOP_LEVEL = 60
PROMOTIONS = 5
ABOVE_TOP = (61, 62)
# A level or promotion row's stat ids, as `game_data` names the stats.
COMBATANT_STATS = {"S_ATK": "atk", "S_DEF": "def", "S_HP": "hp"}
PARTNER_FLAT_STATS = {"S_ATK_INC_ADD_OUT": "atk", "S_DEF_INC_ADD_OUT": "def",
                      "S_HP_INC_ADD_OUT": "hp"}
# A potential node's stat, as `game_data`'s `node_50`/`node_60` name it.
NODE_STATS = {"S_ATK_INC_RATE_OUT": "ATK%", "S_DEF_INC_RATE_OUT": "DEF%",
              "S_HP_INC_RATE_OUT": "HP%", "S_CRI_INC_ADD": "CRate",
              "S_CRI_DMG_RATE_INC_ADD": "CDmg"}
STAT_NODES = {"5_0": "node_50", "6_0": "node_60"}
# A partner passive's plain stat line: a `nb_eff` row of this kind names
# a `stat_up_eff` row, whose stat is one of these, in the names the
# optimizer reads (`PARTNER_STAT_NAMES`). A line any other way is
# conditional, and stays the maintainer's to encode.
PARTNER_STAT_LINE = "EFF_STAT_UP_PARTNER"
PARTNER_PASSIVE_STATS = {"S_ATK_INC_RATE_IN": "ATK%",
                         "S_DEF_INC_RATE_IN": "DEF%",
                         "S_HP_INC_RATE_IN": "HP%", "S_CRI": "CRate",
                         "S_CRI_DMG_RATE": "CDmg",
                         "S_DOT_ATK_DMG_RATE": "DoT%"}
PASSIVE_LINE = re.compile(r"partner_passive@description@(\d+)_c(\d+)_lv(\d+)")
PASSIVE_LEVELS = 5
# The exp from each level to the next: a row per level, a column per
# kind of unit and grade, -1 from the kind's top level on. The program
# holds one curve per kind, so a kind whose grades' columns disagree is
# left to the hand table.
EXP_TABLE = "char_growth@char_exp"
EXP_COLUMNS = {
    "combatant": ("combatant_rarity_ssr_require_exp",
                  "combatant_rarity_sr_require_exp"),
    "partner": ("supporter_rarity_ssr_require_exp",
                "supporter_rarity_sr_require_exp",
                "supporter_rarity_r_require_exp"),
}
# Affinity: the exp from each level to the next, -1 at the cap; and the
# stats each level adds, in the bonus group a combatant names, by the
# flat stat ids a partner's level rows use.
AFFINITY_LEVEL_TABLE = "friendship_level@friendship_level"
AFFINITY_BONUS_TABLE = "combatant_friendship_bonus@combatant_friendship_bonus"
AFFINITY_GROUP = "link_combatant_friendship_bonus_group"
# The Memory Fragment options: a row per main stat a slot can carry
# (`main_piece_<slot>`) and per substat (`random_option`), by stat id,
# with a figure list per rarity -- a main stat's level-0 value and what
# each level-up adds, a substat's every roll. `ratio` is how often a
# substat is drawn as a new one, against the others.
PIECE_OPTION_TABLE = "piece_option@piece_option"
PIECE_MAIN_GROUP = re.compile(r"main_piece_(\d+)")
PIECE_ROLL_GROUP = "random_option"
# A row per rarity and level a fragment can stand at, by the word the
# option table's columns use; and those words as the program's rarity
# tiers (`constants.RARITY`, Mythic 5).
PIECE_LEVEL_TABLE = "piece_reinforce@piece_reinforce"
PIECE_LEVEL_ROW = re.compile(r"reinforce_([a-z]+)_(\d+)")
PIECE_RARITIES = {"common": 1, "uncommon": 2, "rare": 3, "legend": 4,
                  "unique": 5}
# The classes, a row each in the game's order, `class_name` the text
# id of its English name; `CLASS_NAMES` stands in where the text holds
# none.
CLASS_TABLE = "base_class_define@base_class_define"
# An item's rarity, as the `item_*@item` tables' `rarity` says it, in
# the game's word (`constants.RARITY_PLATES`' keys).
ITEM_RARITY_WORDS = {"RARITY_COMMON": "Common", "RARITY_UNCOMMON": "Uncommon",
                     "RARITY_RARE": "Rare", "RARITY_LEGEND": "Legendary",
                     "RARITY_UNIQUE": "Mythic"}

# Markup the text carries for the game's own renderer: tags, a line
# break, and a keyword's marker `$Name#level$`, drawn as the name.
MARKUP = re.compile(r"<[^>]*>")
BREAK = re.compile(r"<br\s*/?>", re.I)
KEYWORD = re.compile(r"\$([^$#]*)(?:#\d*)?\$")


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


def passage(text):
    """A passage as the game draws it, for a tooltip: `<br>` as a new
    line, the colour and underline tags taken out, a keyword down to
    its name, and the typographic apostrophe as the plain one
    `game_data` types. What `clean` leaves out, this does too."""
    text = BREAK.sub("\n", text or "")
    text = KEYWORD.sub(r"\1", MARKUP.sub("", text))
    text = text.replace(chr(0x2019), "'")
    text = "".join(ch for ch in text if ord(ch) <= 0xFFFF)
    return "\n".join(" ".join(line.split()) for line in text.split("\n"))


def _figure(value):
    """A table's figure as a number, whole where it is whole; None for
    anything else."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


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
    for key, name in _special_events(client, texts).items():
        names.setdefault(key, name)
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


def _special_events(client, texts):
    """{schedule id: name} for every special event and the events inside
    it (`SPECIAL_DEFINE_TABLE`). A special event whose page has no
    title names nothing, its parts included."""
    menus = {row.get("id"): clean(texts.get(row.get("scene_name")))
             for row in client.rows(TOP_MENU_TABLE)}
    contents = client.rows(SPECIAL_CONTENT_TABLE)
    out = {}
    for define in client.rows(SPECIAL_DEFINE_TABLE):
        parts = _numbered(contents,
                          define.get("link_special_event_content_key"))
        whole = next((menus[row.get("link_top_menu_id")] for row in parts
                      if menus.get(row.get("link_top_menu_id"))), "")
        if not whole:
            continue
        if define.get("link_event_schedule_id") not in NO_LINK:
            out[define["link_event_schedule_id"]] = whole
        for row in parts:
            title = clean(texts.get(row.get("title")))
            for column in SPECIAL_LINKS:
                if title and row.get(column) not in NO_LINK:
                    out.setdefault(row[column],
                                   SPECIAL_PART_NAME % (whole, title))
    return out


def family_name(schedule_id, names):
    """The name every named schedule of `schedule_id`'s kind shares, or
    None. `event_combatant_trial_15` is a trial whatever its number.

    The kind is the id with a number taken off, and its members every
    id that adds numbers back: `event_combatant_trial_18_1` is first
    of `event_combatant_trial_18`, which no table names, and then of
    `event_combatant_trial`, the trials. The first kind with a named
    member answers."""
    stem = schedule_id
    while True:
        shorter = FAMILY_NUMBER.sub("", stem)
        if shorter == stem:
            return None
        stem = shorter
        member = re.compile(re.escape(stem) + r"(?:_\d+)+")
        shared = {name for key, name in names.items()
                  if member.fullmatch(key)}
        if shared:
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


def event_totals(client):
    """{schedule id: [rewards, final, steps]} for every event whose
    rewards the client lists.

    `rewards` is what the Checklist counts claims against: an event's
    mission rows, or a step track's steps where its one mission carries
    a ladder (`steps` is then 1). `final` is 1 where a reward unlocks
    after all the others, the game's Special Reward, which is not one
    of the rows. A check-in's days are its rewards, with neither.

    An event that pays outside its mission rows is counted by its rows
    alone, those being the rewards the wire records claims for: the
    summer event's puzzles and stories are not in its 20.
    """
    missions = collections.defaultdict(list)
    for row in client.rows(MISSION_TABLE):
        missions[row.get("link_event_id")].append(row.get("id"))
    steps = collections.Counter(row.get("link_event_mission_id")
                                for row in client.rows(STEP_TABLE))
    finals = {row.get("link_event_id") for row in client.rows(DEFINE_TABLE)
              if row.get("special_reward_link_item_id") not in NO_REWARD}
    out = {}
    events = sorted(client.rows(EVENT_TABLE),
                    key=lambda row: row.get(EVENT_DELETED[0])
                    == EVENT_DELETED[1])
    for row in events:
        ids = missions.get(row.get("id")) or []
        if not ids:
            continue
        ladder = sum(steps.get(mission, 0) for mission in ids)
        entry = [ladder or len(ids), int(row.get("id") in finals),
                 int(bool(ladder))]
        for column in SCHEDULE_JOINS:
            key = row.get(column)
            if key and key not in NO_REWARD:
                out.setdefault(key, entry)
    days = collections.Counter(row.get("id", "").rsplit("_", 1)[0]
                               for row in client.rows(CHECK_IN_DAYS))
    for row in client.rows(CHECK_IN_DEFINES):
        if days.get(row.get("key")):
            out.setdefault(row.get("id"), [days[row["key"]], 0, 0])
    countdown = client.rows(COUNTDOWN_DAYS)
    for row in client.rows(COUNTDOWN_DEFINES):
        held = _numbered(countdown, row.get("link_countdown_attendance_day_key"))
        if held:
            out.setdefault(row.get("id"), [len(held), 0, 0])
    for schedule, event in payment_events(client).items():
        out.setdefault(schedule, [len(event["tiers"]), 0, 0])
    rewards = client.rows(TRAUMA_ACHIEVEMENTS)
    for row in client.rows(TRAUMA_CODE_TABLE):
        held = _numbered(rewards, row.get("link_trauma_code_achievement_key"))
        if held and row.get("link_trauma_code_schedule_id") not in NO_LINK:
            out.setdefault(row["link_trauma_code_schedule_id"], [
                len(held), int(row.get("style_link_item_id") not in NO_LINK),
                0])
    return out


def _numbered(rows, key):
    """The rows of `rows` numbered under `key`, `<key>_<n>`: a define's
    days, tiers or rewards. None for a key that is none."""
    if key in NO_LINK or key is None:
        return []
    prefix = key + "_"
    return [row for row in rows
            if (row.get("id") or "").startswith(prefix)
            and row["id"][len(prefix):].isdigit()]


def payment_events(client):
    """{schedule id: {"define": its define's id, "item": its token's
    res_id, "tiers": [[tier id, tokens it takes], ...]}} for every
    payment event, tiers in order.

    The wire files the claims under the define's id and names each by
    its tier id; whether one can be claimed now is the tokens held
    against the cheapest unclaimed tier's."""
    tiers = client.rows(PAYMENT_TIERS)
    out = {}
    for row in client.rows(PAYMENT_DEFINES):
        schedule = row.get("link_event_schedule_id")
        held = _numbered(tiers, row.get("link_event_payment_reward_key"))
        item = _figure(row.get("link_item_id"))
        if (schedule in NO_LINK or not held or not isinstance(item, int)
                or not row.get("id")):
            continue
        out[schedule] = {
            "define": row["id"],
            "item": item,
            "tiers": [[tier["id"], _figure(tier.get("point")) or 0]
                      for tier in sorted(held, key=lambda t: int(
                          t["id"].rsplit("_", 1)[1]))]}
    return out


def limits(client):
    """{kind: figure or {id: figure}}: the maximums the Checklist counts
    against, where the client states them (`ACTIVITY_TIERS` and the
    rest). Each kind is read alone, and one whose table is missing or
    reads wrong is left out: the Checklist's own figure stands for it.

    * `activity`: the day's Activity, its top tier's points;
    * `charges`: {res_id: [what a week adds, the cap]};
    * `passes`: {pass id: [weekly EXP, top level, daily missions]};
    * `simulation`: {content id: weekly runs};
    * `offensives`: {define id: [bosses, stars]};
    * `matrix`: {reward list id: top level};
    * `disaster_weekly`: {season: the week's top score};
    * `rift_target`: the Great Rift's top weekly tier;
    * `overclocks`: {event id: daily runs};
    * `disaster_constants`: {constant id: figure}, the Galactic
      Disaster's, its shop pages' days into the season's schedule among
      them (`unlock_disaster_shop_<page>`);
    * `visit_tickets`: the Communication Passes a day grants before
      town research;
    * `visit_research`: {research node: [what the node adds at level
      1, 2, ...]}.
    """
    readers = {
        "activity": lambda: max(_figure(row.get("point_count")) or 0
                                for row in client.rows(ACTIVITY_TIERS)),
        "charges": lambda: {
            row["id"]: [_figure(row["add_value"]), _figure(row["max"])]
            for row in client.rows(WEEKLY_CHARGES)
            if row.get("charge_type") == "CHARGE_WEEK"},
        "passes": lambda: _passes(client),
        "simulation": lambda: {
            row["id"]: _figure(row["limit_count"])
            for row in client.rows(SIMULATION_TABLE)
            if row.get("limit_type") == "LIMIT_WEEK"},
        "offensives": lambda: _offensives(client),
        "matrix": lambda: _matrix_levels(client),
        "disaster_weekly": lambda: {
            row["id"]: _figure(row["max_clear_score"])
            for row in client.rows(DISASTER_SEASONS)},
        "rift_target": lambda: max(_figure(row.get("total_reward")) or 0
                                   for row in client.rows(RIFT_TIERS)),
        "overclocks": lambda: {
            row["id"]: _figure(row["limit_count"])
            for row in client.rows(OVERCLOCK_TABLE)
            if row.get("limit_type") == "LIMIT_DAY"},
        "disaster_constants": lambda: {
            row["id"]: _figure(row["value"])
            for row in client.rows(DISASTER_CONSTANTS)
            if isinstance(_figure(row.get("value")), int)},
        "visit_tickets": lambda: _constant(client, TOWN_CONSTANTS,
                                           VISIT_TICKET_BASE),
        "visit_research": lambda: _research_levels(client,
                                                   VISIT_TICKET_EFFECT),
    }
    out = {}
    for kind, read in readers.items():
        try:
            value = read()
        except (KeyError, ValueError, TypeError):
            continue
        if isinstance(value, dict):
            value = {key: figure for key, figure in value.items()
                     if _whole(figure)}
        if value and (isinstance(value, dict) or _whole(value)):
            out[kind] = value
    return out


def _whole(figure):
    """Whether a limit's figure is a count, or a list of them."""
    if isinstance(figure, list):
        return bool(figure) and all(_whole(f) for f in figure)
    return isinstance(figure, int) and not isinstance(figure, bool) \
        and figure > 0


def _passes(client):
    """{pass id: [weekly EXP, top level, daily missions]} for every pass
    not retired. A pass's missions are `<its mission key>_<n>`; the
    daily ones reset daily."""
    missions = client.rows(PASS_MISSIONS)
    out = {}
    for row in client.rows(PASS_TABLE):
        if row.get("delete_flag") == "YES":
            continue
        daily = sum(1 for mission in _numbered(missions, row.get("mission_key"))
                    if mission.get("reset_type") == "RESET_DAILY")
        out[row["id"]] = [_figure(row.get("weekly_max_exp")),
                          _figure(row.get("max_level")), daily]
    return out


def _offensives(client):
    """{define id: [bosses, stars]} for every Full-Scale Offensive: its
    stages, and the most stars its reward track pays for."""
    stages = client.rows(OFFENSIVE_STAGES)
    rewards = client.rows(OFFENSIVE_REWARDS)
    out = {}
    for row in client.rows(OFFENSIVE_DEFINES):
        bosses = sum(1 for stage in stages
                     if stage.get("link_remnants_boss_penalty_define_id")
                     == row["id"])
        # `ink_` is the table's own spelling of `link_`, and the plain
        # one stands by for a patch that corrects it.
        track = _numbered(rewards, row.get("ink_remnants_reward_key")
                          or row.get("link_remnants_reward_key"))
        stars = max((_figure(tier.get("total_star_count")) or 0
                     for tier in track), default=0)
        out[row["id"]] = [bosses, stars]
    return out


def _constant(client, table, key):
    """One figure of a constants table, its row `key`'s `value`, or
    None."""
    for row in client.rows(table):
        if row.get("id") == key:
            return _figure(row.get("value"))
    return None


def _research_levels(client, effect):
    """{town research node: [its figure at level 1, 2, ...]} for every
    node of one effect, the figure `opt_1`'s first.

    A level's row states the effect AT that level, not what the level
    adds: a Stamina node's five read 5, 10, 15, 20 and 25. A node whose
    levels do not run unbroken from 1 is left out rather than read with
    a hole in it."""
    held = {}
    for row in client.rows(RESEARCH_LEVELS):
        if row.get("town_research_eff") != effect:
            continue
        level = _figure(row.get("node_level"))
        figures = _figure_list(row.get("opt_1"))
        if isinstance(level, int) and figures and isinstance(figures[0], int):
            held.setdefault(row.get("link_town_research_id"), {})[level] = \
                figures[0]
    return {node: [levels[n] for n in sorted(levels)]
            for node, levels in held.items()
            if node and sorted(levels) == list(range(1, len(levels) + 1))}


def _matrix_levels(client):
    """{reward list id: its top level}: a list names its track's key, and
    the track's rows are `<key>_<n>`, each a level."""
    levels = client.rows(MATRIX_LEVELS)
    out = {}
    for row in client.rows(MATRIX_LISTS):
        track = _numbered(levels, row.get("link_zero_reward_key"))
        out[row["id"]] = max((_figure(level.get("reward_level")) or 0
                              for level in track), default=0)
    return out


def trial_slots(client):
    """{trial id: [slot ids]}: every slot a Combatant Trial offers, in
    its order. The wire names a slot only when it is claimed."""
    out = {}
    for row in client.rows(TRIAL_TABLE):
        slots = [row[column] for column in row
                 if TRIAL_SLOT_COLUMN.fullmatch(column)
                 and row[column] not in NO_LINK]
        if row.get("id") and slots:
            out[row["id"]] = slots
    return out


def story_chapters(client):
    """{schedule id: [episode ids]} for every event that is a chapter
    of the story map, such as a Galactic Disaster's prologue: the
    chapter's episodes, which is what the game's Progress counts.

    Such an event pays as each episode is cleared and has nothing to
    claim, so it has no rewards for `event_totals` to list.
    """
    episodes = collections.defaultdict(list)
    for row in client.rows(STORY_NODE_TABLE):
        node = row.get("id") or ""
        if (row.get(STORY_NODE_UNUSED[0]) != STORY_NODE_UNUSED[1]
                and "_" in node):
            episodes[node.rsplit("_", 1)[0]].append(node)
    keys = {row.get("id"): row.get("link_story_map_node_key")
            for row in client.rows(STORY_CHAPTER_TABLE)}
    out = {}
    events = sorted(client.rows(EVENT_TABLE),
                    key=lambda row: row.get(EVENT_DELETED[0])
                    == EVENT_DELETED[1])
    for row in events:
        listed = episodes.get(keys.get(row.get("multiple_link")))
        key = row.get("link_event_schedule_id")
        if (row.get("type") == STORY_EVENT_TYPE and listed and key
                and key not in NO_REWARD):
            out.setdefault(key, list(listed))
    return out


def daily_tasks(client):
    """{daily task res_id: [score it counts to, Activity it pays]}."""
    out = {}
    for row in client.rows(DAILY_TASK_TABLE):
        try:
            count, points = int(row.get("count")), int(row.get("point_count"))
        except (TypeError, ValueError):
            continue
        if row.get("id") and count > 0 and points > 0:
            out[row["id"]] = [count, points]
    return out


def set_effects(client):
    """{set id: [name, pieces, words, stat, value]} for every set
    fragments drop in. `words` is the effect's text as `passage` draws
    it; `stat` and `value` the client's stat id and figure where the
    effect is a plain stat, else "" and None."""
    texts = client.text()
    out = {}
    for row in client.rows(SET_TABLE):
        match = SET_ID.fullmatch(row.get("id") or "")
        order = _figure(row.get("order"))
        pieces = _figure(row.get("set_option_type"))
        if not match or not order or order <= 0 or not pieces:
            continue
        words = passage(texts.get(row.get(f"set{pieces}_description")))
        name = passage(texts.get(row.get("name")))
        if not words or not name:
            continue
        stat, value = "", None
        if row.get(f"set{pieces}_type") == SET_STAT:
            stat = row.get(f"set{pieces}_option_multiple_link") or ""
            value = _figure(row.get(f"set{pieces}_value"))
        out[int(match.group(1))] = [name, pieces, words, stat, value]
    return out


def live_nodes(client):
    """{(combatant res_id, node_num): the node's first-level row}, off
    the tree the game draws: where a combatant has two listed, the
    reworked one, whose rows have the higher ids."""
    out = {}
    for row in client.rows(NODE_TABLE):
        rid, row_id = _figure(row.get("link_char_combatant_id")), \
            _figure(row.get("id"))
        if not isinstance(rid, int) or not isinstance(row_id, int) \
                or _figure(row.get("node_level")) != 1:
            continue
        key = (rid, row.get("node_num"))
        held = out.get(key)
        if held is None or row_id > _figure(held.get("id")):
            out[key] = row
    return out


def potential_texts(client):
    """{combatant res_id: {wire node: words}} for the nodes whose effect
    is the combatant's own (`OWN_TEXT_NODES`), as `passage` draws them."""
    texts = client.text()
    out = {}
    for (rid, num), row in live_nodes(client).items():
        wire = OWN_TEXT_NODES.get(num)
        words = passage(texts.get(row.get("desc"))) if wire else ""
        if words:
            out.setdefault(rid, {})[wire] = words
    return out


def class_names(client):
    """{class id: the game's English name}, in the game's order: the ids
    a combatant's `link_base_class_define_id` and a partner's passive
    condition name."""
    texts = client.text()
    out = {}
    for row in client.rows(CLASS_TABLE):
        name = passage(texts.get(row.get("class_name")))
        if row.get("id") and name:
            out[row["id"]] = name
    return out


def item_rarities(client):
    """{item res_id: the game's rarity word} for every item the
    `item_*@item` tables hold."""
    out = {}
    for path in client.archive.files:
        if path.startswith("db/item_") and path.endswith("@item.db"):
            for row in client.rows(path[3:-3]):
                rid = _figure(row.get("id"))
                word = ITEM_RARITY_WORDS.get(row.get("rarity"))
                if isinstance(rid, int) and word:
                    out[rid] = word
    return out


def item_names(client):
    """{item res_id: English name} for every item the client names, a
    placeholder (`NAMING`) not being a name.

    **An item's name is the text its row's `name` column holds**, in
    whichever `item_*@item` table carries the row -- not the text
    `item@name@<its id>`. Most rows hold that very key, but some point
    elsewhere, and the text under their own id is then one the game no
    longer shows: every season's Memory of Light (3000007, 3000009,
    3000010) holds `item@name@3000006`, the text under 3000010 reading
    `Tactical Manual Processor`; a package can hold a kit's; two
    stickers hold each other's. A text no row uses names its id last,
    for an id a payload carries that no item table holds -- the ids a
    patch later gives to items of its own carry such leftovers until
    then."""
    texts = client.text()
    out = {}
    for key, text in texts.items():
        match = ITEM_NAME.fullmatch(key)
        name = clean(text) if match else ""
        if NAMING.search(name):
            out[int(match.group(1))] = name
    for path in client.archive.files:
        if path.startswith("db/item_") and path.endswith("@item.db"):
            for row in client.rows(path[3:-3]):
                rid = _figure(row.get("id"))
                name = clean(texts.get(row.get("name")) or "")
                if isinstance(rid, int) and NAMING.search(name):
                    out[rid] = name
    return out


def _percent(value):
    """A crit figure as `game_data` types it: a float, 3.0 not 3."""
    number = _figure(value)
    return float(number) if number is not None else None


def _steps(rows, group, low, high, key, names):
    """{stat: the sum of the steps `rows` give `group` from `low` to
    `high`} -- a level or promotion table, three stats a row, the stats
    named by `names`."""
    out = dict.fromkeys(names.values(), 0)
    for row in rows:
        at = _figure(row.get(key))
        if row.get("group") == group and isinstance(at, int) \
                and low <= at <= high:
            for i in (1, 2, 3):
                stat = names.get(row.get(f"stat{i}_link_stat_list_id"))
                if stat:
                    out[stat] += _figure(row.get(f"stat{i}_value")) or 0
    return out


def combatants(client):
    """{combatant res_id: what `game_data.characters` holds of it}, for
    every combatant the game lets a player use: name, grade, class,
    attribute, the level-60 stats and crit, node 50's and 60's stat,
    and what levels 61 and 62 each add (`level_gains`)."""
    texts = client.text()
    base = {r["id"]: r for r in client.rows("char_base@char_base")}
    levels = client.rows("char_base@combatant_level")
    ascends = client.rows("char_base@combatant_ascend")
    effects = {r["id"]: r for r in client.rows(NODE_EFFECT_TABLE)}
    nodes = live_nodes(client)
    classes = {**CLASS_NAMES, **class_names(client)}
    out = {}
    for row in client.rows("char_base@char_combatant"):
        rid = _figure(row.get("id"))
        if not isinstance(rid, int) or \
                base.get(row["id"], {}).get("char_use_playable") != "YES":
            continue
        level_group = row.get("link_combatant_level_group")
        promoted = _steps(ascends, row.get("link_combatant_ascend_group"),
                          1, PROMOTIONS, "ascend", COMBATANT_STATS)
        top = _steps(levels, level_group, 1, TOP_LEVEL, "level",
                     COMBATANT_STATS)
        entry = {
            "name": passage(texts.get(f"char_base@name@{rid}")) or None,
            "grade": COMBATANT_GRADES.get(base[row["id"]].get("rarity")),
            "class": classes.get(row.get("link_base_class_define_id")),
            "attribute": ATTRIBUTE_NAMES.get(row.get("link_ego_type_id")),
            "base_crit_rate": _percent(row.get("s_cri")),
            "base_crit_dmg": _percent(row.get("s_cri_dmg_rate")),
            "level_gains": {level: _steps(levels, level_group, level,
                                          level, "level", COMBATANT_STATS)
                            for level in ABOVE_TOP},
        }
        for stat, start in (("atk", "s_atk"), ("def", "s_def"),
                            ("hp", "s_hp")):
            first = _figure(row.get(start))
            entry[f"base_{stat}"] = (first + top[stat] + promoted[stat]
                                     if isinstance(first, (int, float))
                                     else None)
        for num, field in STAT_NODES.items():
            node = nodes.get((rid, num)) or {}
            entry[field] = None
            for effect_id in str(node.get("link_potential_node_effect_id")
                                 or "").strip("[]").split(","):
                effect = effects.get(effect_id.strip()) or {}
                if effect.get("node_type") == "NODE_STAT_ADD":
                    entry[field] = NODE_STATS.get(
                        effect.get("link_stat_list_id"))
                    break
        out[rid] = entry
    return out


def _passive_stats(client):
    """{partner res_id: {stat: (a figure per level)}}: each passive line
    that is a plain stat (`PARTNER_STAT_LINE`), in the optimizer's
    names. A stat the client does not give at every level is left out."""
    tables = [path[3:-3] for path in client.archive.files
              if path.startswith("db/partner_passive")
              and path.endswith(".db")]
    passive, effects = [], {}
    for name in tables:
        if name.endswith("@partner_passive"):
            passive += client.rows(name)
        elif name.endswith("@nb_eff"):
            effects.update({r["id"]: r for r in client.rows(name)})
    stat_ups = {r["id"]: r for r in client.rows("stat_up_eff@stat_up_eff")}
    found = {}
    for row in passive:
        match = re.fullmatch(r"(\d+)_c\d+_lv(\d+)", row.get("id", ""))
        if not match:
            continue
        rid, level = int(match.group(1)), int(match.group(2))
        for effect_id in str(row.get("link_nb_eff_id") or "") \
                .strip("[]").split(","):
            effect = effects.get(effect_id.strip()) or {}
            if effect.get("nb_eff") != PARTNER_STAT_LINE:
                continue
            stat_up = stat_ups.get(effect.get("opt_multiple_link")) or {}
            stat = PARTNER_PASSIVE_STATS.get(
                str(stat_up.get("link_stat_list_id")).strip("[]"))
            if stat:
                found.setdefault(rid, {}).setdefault(stat, {})[level] = \
                    _figure(stat_up.get("stat_max"))
    return {rid: {stat: tuple(by_level[level]
                              for level in range(1, PASSIVE_LEVELS + 1))
                  for stat, by_level in stats.items()
                  if all(level in by_level
                         for level in range(1, PASSIVE_LEVELS + 1))}
            for rid, stats in found.items()}


# A partner Ego card's text holds its figures as `#kind_N#` or
# `#kind_N_M#`, N the card's Nth effect (`link_skill_eff_id`):
# `result_damage` and `result_coeff_ev` a percentage of it, `result_ev`
# it bare, `cs_ev` the Mth effect of the status it applies, `during_ev`
# its `during_eff_<M>` effect. `match_comb_char` and `own_char` name the
# assigned combatant, and `final_ectc` and `result_vt_mul` are counts
# taken in battle, which the out-of-battle text leaves out.
EGO_FIGURE = re.compile(r"#([a-z_]+?)_(\d+)(?:_(\d+))?#")
EGO_OWNER = re.compile(r"#(?:match_comb_char|own_char)#")
EGO_COUNTER = re.compile(r"\(?#(?:final_ectc|result_vt_mul)_\d+(?:_\d+)?#\)?")
EGO_ASSIGNED = "the assigned Combatant"
EGO_PERCENT = ("result_damage", "result_coeff_ev")
# Three kinds name what they read: `ecdv<N>_<M>` the Nth effect's
# `eff_condition_value_<M>`, `cs_tv_max_<status>` a status's most
# stacks (`overlay_value_max`), and `skill_eff_ev_<effect>` an effect by
# its own id, which can sit in a combatant's card table.
EGO_CONDITION = re.compile(r"#ecdv(\d+)_(\d+)#")
EGO_STATUS_MAX = re.compile(r"#cs_tv_max_([A-Za-z0-9_]+?)#")
EGO_NAMED = re.compile(r"#skill_eff_ev_([A-Za-z0-9_]+?)#")
EFFECT_TABLE = re.compile(r"^card\([^)]+\)@skill_eff$")
# What is left of any other kind: a figure this does not read.
EGO_UNREAD = re.compile(r"#[^#\s<>]+#")
# The statuses an Ego card applies, and their effects: the partners'
# own and the shared ones (`cs(card1)`).
STATUS_TABLE = re.compile(r"^cs(?:\([^)]+\))?@(cs|skill_eff)$")


def _ids(cell):
    """A table's `[a,b]` cell as ['a', 'b']."""
    return [part.strip() for part in str(cell or "").strip("[]").split(",")
            if part.strip() and part.strip() != "none"]


def _statuses(client):
    """({status id: row}, {status effect id: row}) over every status
    table the client holds."""
    statuses, effects = {}, {}
    for path in client.archive.files:
        match = STATUS_TABLE.fullmatch(path[3:-3]) \
            if path.startswith("db/") and path.endswith(".db") else None
        if match:
            held = statuses if match.group(1) == "cs" else effects
            held.update({r["id"]: r for r in client.rows(path[3:-3])})
    return statuses, effects


def _hits(raw, links, effects):
    """`raw` with each damage figure that hits more than once given its
    hits after the word Damage that follows it on its line, as the game
    draws them: `60% Defense-Based Damage x 4`. The template does not
    say them; the effect's `eff_count_value` does."""
    out, at = [], 0
    for match in EGO_FIGURE.finditer(raw):
        n = int(match.group(2))
        if match.group(1) not in EGO_PERCENT or match.group(3) is not None \
                or n >= len(links):
            continue
        hits = _figure((effects.get(links[n]) or {}).get("eff_count_value"))
        line_end = BREAK.search(raw, match.end())
        word = raw.find("Damage", match.end(),
                        line_end.start() if line_end else len(raw))
        if isinstance(hits, int) and hits > 1 and word >= 0:
            out.append(raw[at:word + len("Damage")] + f" x {hits}")
            at = word + len("Damage")
    return "".join(out) + raw[at:]


def _named_effects(client, wanted):
    """{effect id: row} for the effects in `wanted`, out of every card
    table: only read where an Ego text names one (`EGO_NAMED`)."""
    found = {}
    for path in client.archive.files:
        name = path[3:-3] if path.startswith("db/") and path.endswith(".db") \
            else ""
        if wanted - set(found) and EFFECT_TABLE.fullmatch(name):
            found.update({r["id"]: r for r in client.rows(name)
                          if r.get("id") in wanted})
    return found


def ego_text(card, texts, effects, statuses, status_effects, named=None):
    """A partner's Ego card text as the game shows it out of battle,
    every figure read off its effects (`EGO_FIGURE`, `_hits`, and the
    kinds that name their source, `named` the effects `EGO_NAMED`
    names); None where the card has no text or holds a figure this does
    not read. `card@desc_outgame` is that text where the card has one;
    without, `card@desc` is, the assigned combatant named and the
    battle's counts taken out."""
    raw = texts.get(card.get("desc_outgame")) or texts.get(card.get("desc"))
    if not raw:
        return None
    links = _ids(card.get("link_skill_eff_id"))
    raw = _hits(raw, links, effects)

    def condition(match):
        n = int(match.group(1))
        effect = effects.get(links[n]) if n < len(links) else None
        value = _figure((effect or {}).get(
            "eff_condition_value_%s" % match.group(2)))
        return match.group() if value is None else str(value)

    def most(match):
        value = _figure((statuses.get(match.group(1)) or {}).get(
            "overlay_value_max"))
        return match.group() if value is None else str(value)

    def by_id(match):
        value = _figure(((named or {}).get(match.group(1)) or {}).get(
            "eff_value"))
        return match.group() if value is None else str(value)

    raw = EGO_CONDITION.sub(condition, raw)
    raw = EGO_STATUS_MAX.sub(most, raw)
    raw = EGO_NAMED.sub(by_id, raw)
    unread = []

    def figure(match):
        kind, n, m = match.group(1), int(match.group(2)), match.group(3)
        effect = effects.get(links[n]) if n < len(links) else None
        value, suffix = None, ""
        if effect is None:
            pass
        elif kind in EGO_PERCENT and m is None:
            value, suffix = effect.get("eff_value"), "%"
        elif kind == "result_ev" and m is None:
            value = effect.get("eff_value")
        elif kind == "cs_ev" and m is not None:
            status = statuses.get(next(iter(_ids(effect.get("link_cs_id"))),
                                       None)) or {}
            inner = _ids(status.get("link_skill_eff_id"))
            if int(m) < len(inner):
                value = (status_effects.get(inner[int(m)]) or {}).get(
                    "eff_value")
        elif kind == "during_ev" and m is not None:
            value = (effects.get(effect.get(
                f"during_eff_{m}_link_skill_eff_id")) or {}).get("eff_value")
        number = _figure(value)
        if number is None:
            unread.append(match.group())
            return match.group()
        return f"{number}{suffix}"

    text = EGO_COUNTER.sub("", raw)
    text = EGO_OWNER.sub(EGO_ASSIGNED, text)
    text = EGO_FIGURE.sub(figure, text)
    if unread or EGO_UNREAD.search(text):
        return None
    # A left quote stands for the apostrophe after a name in a few.
    return passage(text.replace(chr(0x2018), "'"))


def partners(client):
    """{partner res_id: what `game_data.partners` holds of it}: name,
    grade, class, passive name, the passive's plain stats (`stats`, as
    `_passive_stats` reads them), its lines at each level as the game
    draws them (`passive_lines`), the Ego card's name, cost and text
    (`ego_text`), and the flat stats at level 60 (`level_60`)."""
    texts = client.text()
    levels = client.rows("partner_base@partner_level")
    ascends = client.rows("partner_base@partner_ascend")
    cards = {r["id"]: r for r in client.rows("card(partner)@card")}
    card_effects = {r["id"]: r for r in client.rows("card(partner)@skill_eff")}
    statuses, status_effects = _statuses(client)
    named = _named_effects(client, {
        match.group(1) for card in cards.values()
        for key in ("desc", "desc_outgame")
        for match in EGO_NAMED.finditer(texts.get(card.get(key)) or "")})
    stats = _passive_stats(client)
    classes = {**CLASS_NAMES, **class_names(client)}
    lines = {}
    for key, text in texts.items():
        match = PASSIVE_LINE.fullmatch(key)
        if match:
            rid, line, level = map(int, match.groups())
            lines.setdefault(rid, {}).setdefault(line, {})[level] = \
                passage(text)
    out = {}
    for row in client.rows("partner_base@char_partner"):
        rid = _figure(row.get("id"))
        if not isinstance(rid, int):
            continue
        grade = PARTNER_GRADE.match(row.get("link_partner_level_group") or "")
        flat = _steps(levels, row.get("link_partner_level_group"), 1,
                      TOP_LEVEL, "level", PARTNER_FLAT_STATS)
        promoted = _steps(ascends, row.get("link_partner_ascend_group"), 1,
                          PROMOTIONS, "ascend", PARTNER_FLAT_STATS)
        card = cards.get(row.get("link_card_id")) or {}
        out[rid] = {
            "name": passage(texts.get(f"char_base@name@{rid}")) or None,
            "grade": PARTNER_GRADES.get(grade.group(1)) if grade else None,
            "class": classes.get(
                row.get("passive_condition_link_base_class_define_id")),
            "passive_name": passage(
                texts.get(f"partner_passive@name@{rid}")) or None,
            "stats": stats.get(rid, {}),
            "passive_lines": [
                [by_level.get(level, "")
                 for level in range(1, PASSIVE_LEVELS + 1)]
                for _line, by_level in sorted(lines.get(rid, {}).items())],
            "ego_name": passage(texts.get(card.get("name"))) or None,
            "ego_cost": _figure(card.get("cost")),
            "ego_desc": ego_text(card, texts, card_effects, statuses,
                                 status_effects, named),
            "level_60": {stat: (_figure(row.get(f"default_{stat}_add")) or 0)
                         + flat[stat] + promoted[stat]
                         for stat in ("atk", "def", "hp")},
        }
    return out


def chaos_names(client):
    """{stage id: (English name, season)}: every Chaos the client names,
    by the stage id a run's clear carries, with the Galactic Disaster
    season it came with (`disaster_sNN`, from its Save Data season
    `savedata_sNN`) or None for the base game's."""
    texts = client.text()
    out = {}
    for row in client.rows("chaos@chaos"):
        stage = _figure(row.get("link_stage_component_id"))
        name = clean(texts.get(row.get("title")))
        if not isinstance(stage, int) or stage <= 0 or not name:
            continue
        season = re.fullmatch(r"savedata_s(\d+)",
                              row.get("link_savedata_season_id") or "")
        out[stage] = (name, f"disaster_s{season.group(1)}" if season
                      else None)
    return out


# A partner's Exploration Passives (`partner_ego_passive`): its
# `link_partner_ego_passive_key` names a row per slot for each limit
# break its passive rises at, and the passive's level there names its
# text (`partner_ego_passive_eff`, `<passive>_<level>`). The one whose
# `belong_character_eff` is YES acts on the assigned combatant alone;
# the rest on every combatant and the run.
EXPLORATION_SLOTS = "partner_ego_passive@partner_ego_passive"
EXPLORATION_TEXTS = "partner_ego_passive@partner_ego_passive_eff"


def exploration_passives(client):
    """{partner res_id: [{name, assigned, steps}]}: a partner's
    Exploration Passives in the game's slot order, each one's name,
    whether it acts on the assigned combatant alone, and [limit break,
    its text from then on] for each limit break it rises at."""
    texts = client.text()
    effects = {r["id"]: r for r in client.rows(EXPLORATION_TEXTS)}
    slots = {}
    for row in client.rows(EXPLORATION_SLOTS):
        key = row.get("id", "").rpartition("_")[0]
        slots.setdefault(key, {}).setdefault(row.get("eff_class"),
                                             []).append(row)
    out = {}
    for partner in client.rows("partner_base@char_partner"):
        rid = _figure(partner.get("id"))
        held = slots.get(partner.get("link_partner_ego_passive_key") or "")
        if not isinstance(rid, int) or not held:
            continue
        passives = []
        for slot in sorted(held):
            rows = sorted(held[slot],
                          key=lambda r: _figure(r.get("limit_break")) or 0)
            name, steps = None, []
            for row in rows:
                level, at = _figure(row.get("level")), _figure(
                    row.get("limit_break"))
                effect = effects.get("%s_%02d" % (
                    row.get("link_partner_ego_passive_eff_key"), level)) \
                    if isinstance(level, int) else None
                text = passage(texts.get((effect or {}).get("description")))
                name = name or passage(texts.get((effect or {}).get("name")))
                if text and isinstance(at, int):
                    steps.append([at, text])
            if name and steps:
                passives.append({"name": name, "steps": steps, "assigned":
                                 rows[0].get("belong_character_eff") == "YES"})
        if passives:
            out[rid] = passives
    return out


# The Card Skin Packs: each skin's rarity and pack (`card_skin`), and each
# pack's two pools (`card_skin_package`), each pool a share of 10,000
# (`common_ratio`, `special_ratio`) split over its skins by their weights
# (`card_skin_pool`, rows `<pool>_<n>`).
CARD_SKIN_TABLE = "card_skin@card_skin"
CARD_SKIN_PACKS = "card_skin_package@card_skin_package"
CARD_SKIN_POOLS = "card_skin_pool@card_skin_pool"


def card_skins(client):
    """{"skins": {skin res_id: [name, rarity, the combatant it is for]},
    "packs": {pack id: [name, {rarity: the chance a pull is one}, the
    combatant its Super Rare is for]}}: every Card Skin and every pack,
    the chances from the pools' shares and weights."""
    texts = client.text()
    skins = {}
    for row in client.rows(CARD_SKIN_TABLE):
        rid = _figure(row.get("id"))
        if isinstance(rid, int) and row.get("rarity"):
            skins[rid] = [passage(texts.get(row.get("name"))
                                  or row.get("name")) or None,
                          row["rarity"], _figure(row.get("link_char_base_id"))]
    pools = {}
    for row in client.rows(CARD_SKIN_POOLS):
        weight, skin = _figure(row.get("ratio")), _figure(
            row.get("link_card_skin_id"))
        if isinstance(weight, (int, float)) and skin in skins:
            pools.setdefault(row.get("id", "").rpartition("_")[0], []).append(
                (skins[skin][1], weight, skins[skin][2]))
    packs = {}
    for row in client.rows(CARD_SKIN_PACKS):
        chances, featured = {}, None
        for pool, share in (("common_link_card_skin_pool_key", "common_ratio"),
                            ("special_link_card_skin_pool_key",
                             "special_ratio")):
            held, share = pools.get(row.get(pool)) or [], _figure(row.get(share))
            total = sum(weight for _rarity, weight, _who in held)
            if not held or not isinstance(share, (int, float)) or not total:
                continue
            for rarity, weight, who in held:
                chances[rarity] = chances.get(rarity, 0) \
                    + share / 10000 * weight / total
                if rarity == "SUPER_RARE":
                    featured = who
        if row.get("id") and chances:
            packs[row["id"]] = [passage(texts.get(row.get("product_name"))
                                        or row.get("product_name")) or None,
                                {r: round(c, 6) for r, c in chances.items()},
                                featured]
    return {"skins": skins, "packs": packs}


# A Galactic Disaster season's skill tree, the Environment Variables:
# its nodes (`@zero_orb_season_node`, `disaster_s04_skilltree_<n>`, each
# at a `node_num` on screen), each node's levels (`@zero_orb_season_
# skill`) and their Zero System effects. **A layout per season part**
# (`@zero_orb_season_circle`, `ds_s04_skilltree_circle_1` to `_3`; season
# 2's first is `disaster_s02_skilltree_circle`) lists every node number
# on screen by then, so a part's nodes are those its layout lists and the
# one before did not. A number with no node row is one shown locked,
# opening with a later part: season 5's one layout lists all 35, and
# `_uk` names the lines drawn to those. A Memory Resonance Amplification
# node's effect is `AMPLIFY_GROUP`'s, 1% of the season's currency a node.
SEASON_NODES_TABLE = "zero_orb_season_skilltree@zero_orb_season_node"
SEASON_SKILLS_TABLE = "zero_orb_season_skilltree@zero_orb_season_skill"
SEASON_LAYOUTS_TABLE = "zero_orb_season_skilltree@zero_orb_season_circle"
ZERO_EFFECTS_TABLE = "zero_system_eff@zero_system_eff"
AMPLIFY_GROUP = "ZERO_ITEM_GET_INCREASE__AREA_VALUE_ID"
SEASON_LAYOUT = re.compile(r"(?:ds|disaster)_s(\d+)_skilltree_circle(?:_(\d+))?")


def season_nodes(client):
    """{season: [amplification nodes by the end of each part, part 1
    first]}: each season's tree, a part's count taking in the parts
    before it and only the nodes the client has rows for."""
    amplify = {r["id"] for r in client.rows(ZERO_EFFECTS_TABLE)
               if r.get("zero_eff") == AMPLIFY_GROUP}
    amplifies = {r["id"] for r in client.rows(SEASON_SKILLS_TABLE)
                 if set(_ids(r.get("link_zero_system_eff_id"))) & amplify}
    nodes = {}
    for row in client.rows(SEASON_NODES_TABLE):
        season = row.get("id", "").partition("_skilltree_")[0]
        number = str(row.get("node_num") or "").rpartition("_")[2]
        if season and number.isdigit():
            nodes.setdefault(season, {})[int(number)] = bool(
                set(_ids(row.get("link_zero_orb_season_skill_id")))
                & amplifies)
    layouts = {}
    for row in client.rows(SEASON_LAYOUTS_TABLE):
        match = SEASON_LAYOUT.fullmatch(row.get("id") or "")
        if not match:
            continue
        listed = {int(n) for key, cell in row.items()
                  if key.endswith("node_num_list") for n in _ids(cell)
                  if n.isdigit()}
        layouts.setdefault("disaster_s%s" % match.group(1), {})[
            int(match.group(2) or 1)] = listed
    out = {}
    for season, parts in layouts.items():
        held, shown, counts = nodes.get(season) or {}, set(), []
        for part in sorted(parts):
            shown |= parts[part]
            counts.append(sum(1 for number in shown if held.get(number)))
        if counts and counts[-1]:
            out[season] = counts
    return out


def zero_specials(client):
    """{Zero System special option id: the game's name for it}."""
    texts = client.text()
    out = {}
    for row in client.rows("zero_orb_special@zero_orb_special"):
        name = clean(texts.get(row.get("name")))
        if row.get("id") and name:
            out[row["id"]] = name
    return out


def recommended_partners(client):
    """{combatant res_id: the partner res_id the game recommends for it},
    `combatant_info`'s `<res_id>_info` rows. A 5-star's is the partner it
    was released with, which `partners.SIGNATURE_PARTNERS` pairs it with;
    a 4-star's is the game's suggestion, which `PARTNER_EXCEPTIONS` is
    free to differ from."""
    out = {}
    for row in client.rows(COMBATANT_INFO_TABLE):
        match = COMBATANT_INFO_ROW.fullmatch(row.get("id") or "")
        partner = _figure(row.get("recommend_partner_link_char_base_id"))
        if match and isinstance(partner, int) and partner > 0:
            out[int(match.group(1))] = partner
    return out


def general_units(client):
    """The 5-stars the Normal Rescues offer, as res_ids: the client's
    own `general_ssr_c`/`general_ssr_s` pools, the ids a banner's rates
    reply lists under `ssr_pool_ids`."""
    return sorted({_figure(row.get("multiple_link"))
                   for row in client.rows("gacha_pool@gacha_pool")
                   if row.get("group") in ("general_ssr_c", "general_ssr_s")
                   and isinstance(_figure(row.get("multiple_link")), int)})


def exp_columns(client):
    """{column: [the exp to reach each level, from level 1]}: each of
    `EXP_COLUMNS`' columns accumulated, up to the level whose step is
    -1, that kind's top. A column with a level missing or unreadable
    below its top is left out: summed across the gap, every threshold
    above it would come out short."""
    by_level = {}
    for row in client.rows(EXP_TABLE):
        level = _figure(row.get("level"))
        if isinstance(level, int):
            by_level[level] = row
    out = {}
    for column in (name for names in EXP_COLUMNS.values() for name in names):
        reached, level = [0], 1
        while reached is not None:
            step = _figure((by_level.get(level) or {}).get(column))
            if not isinstance(step, int):
                reached = None
            elif step < 0:
                break
            else:
                reached.append(reached[-1] + step)
                level += 1
        if reached and len(reached) > 1:
            out[column] = reached
    return out


def exp_tables(client):
    """{"combatant": [...], "partner": [...]}: the exp to reach each
    level from level 1 to the kind's top, where every grade's column for
    the kind agrees (`exp_columns`)."""
    columns = exp_columns(client)
    out = {}
    for kind, names in EXP_COLUMNS.items():
        tables = [columns.get(name) for name in names]
        if tables[0] and all(table == tables[0] for table in tables):
            out[kind] = tables[0]
    return out


def affinity(client):
    """Affinity as `game_data.constants` holds it: `to_next`, {level:
    the exp from it to the next} for every level below the cap; and
    `bonuses`, [(level, ATK, DEF, HP)], each the total from level 1 up
    to that level. The bonuses are the group every playable combatant
    names, and are left out where they name more than one: the program
    holds one table for all."""
    to_next = {}
    for row in client.rows(AFFINITY_LEVEL_TABLE):
        level, exp = _figure(row.get("id")), _figure(row.get("exp"))
        if isinstance(level, int) and isinstance(exp, int) and exp > 0:
            to_next[level] = exp
    out = {}
    # A level missing would end `constants.affinity_level`'s walk down
    # from the cap there, and every level below it would read as 1.
    if to_next and sorted(to_next) == list(range(1, len(to_next) + 1)):
        out["to_next"] = to_next
    base = {r["id"]: r for r in client.rows("char_base@char_base")}
    groups = {row.get(AFFINITY_GROUP)
              for row in client.rows("char_base@char_combatant")
              if base.get(row.get("id"), {}).get("char_use_playable") == "YES"}
    if len(groups) != 1:
        return out
    group, rows = groups.pop(), {}
    for row in client.rows(AFFINITY_BONUS_TABLE):
        level = _figure(row.get("level"))
        if row.get("group") == group and isinstance(level, int):
            rows[level] = row
    totals, bonuses = dict.fromkeys(("atk", "def", "hp"), 0), []
    for level in range(1, max(rows, default=0) + 1):
        row = rows.get(level) or {}
        for i in range(3):
            stat = PARTNER_FLAT_STATS.get(row.get(f"stat{i}_link_stat_list_id"))
            value = _figure(row.get(f"stat{i}_value"))
            if stat and isinstance(value, int) and value > 0:
                totals[stat] += value
        bonuses.append((level, totals["atk"], totals["def"], totals["hp"]))
    if len(bonuses) > 1:
        out["bonuses"] = bonuses
    return out


def _figure_list(value):
    """A table's `[a,b,...]` cell as numbers; None where any is not one."""
    figures = [_figure(part)
               for part in str(value or "").strip("[]").split(",")]
    return figures if all(isinstance(f, (int, float)) for f in figures) \
        else None


def fragment_stats(client):
    """Memory Fragment stats as the game rolls them, by stat id:
    `mains`, {slot: [[stat, level-0 value, what each level-up adds],
    ...]} for a Legendary, in the table's order; `rolls`, {stat: every
    value one roll gives a Legendary}; `draws`, {stat: its weight in
    the draw of a new substat}; and `max_levels`, {rarity tier: its top
    level}."""
    mains, rolls, draws = {}, {}, {}
    for row in client.rows(PIECE_OPTION_TABLE):
        stat, group = row.get("link_stat_list_id"), row.get("group") or ""
        slot = PIECE_MAIN_GROUP.fullmatch(group)
        start = _figure_list(row.get("legend_value"))
        step = _figure_list(row.get("legend_reinforce_value"))
        if slot and start and step and len(start) == len(step) == 1:
            mains.setdefault(int(slot.group(1)), []).append(
                [stat, start[0], step[0]])
        elif group == PIECE_ROLL_GROUP and start:
            rolls[stat] = start
            share = _figure(row.get("ratio"))
            if isinstance(share, (int, float)) and share > 0:
                draws[stat] = share
    max_levels = {}
    for row in client.rows(PIECE_LEVEL_TABLE):
        match = PIECE_LEVEL_ROW.fullmatch(str(row.get("id")))
        tier = PIECE_RARITIES.get(match.group(1)) if match else None
        if tier:
            max_levels[tier] = max(max_levels.get(tier, 0),
                                   int(match.group(2)))
    return {"mains": mains, "rolls": rolls, "draws": draws,
            "max_levels": max_levels}


def read_facts(install):
    """Everything this module reads off an install, as the cache holds
    it. Raises whatever the reading meets."""
    client = Client(install)
    return {
        "format": CACHE_FORMAT,
        "install": str(install),
        "build": client.archive.build,
        "event_names": event_names(client),
        "event_totals": event_totals(client),
        "trial_slots": trial_slots(client),
        "payment_events": payment_events(client),
        "limits": limits(client),
        "story_chapters": story_chapters(client),
        "item_names": {str(res_id): name for res_id, name
                       in item_names(client).items()},
        "excursion_types": {str(res_id): count for res_id, count
                            in excursion_types(client).items()},
        "daily_tasks": daily_tasks(client),
        "set_effects": {str(set_id): effect for set_id, effect
                        in set_effects(client).items()},
        "potential_texts": {
            str(res_id): {str(wire): words for wire, words in nodes.items()}
            for res_id, nodes in potential_texts(client).items()},
        "combatants": {str(res_id): entry for res_id, entry
                       in combatants(client).items()},
        "partners": {str(res_id): entry for res_id, entry
                     in partners(client).items()},
        "chaos_names": {str(stage): list(named) for stage, named
                        in chaos_names(client).items()},
        "zero_specials": zero_specials(client),
        "general_units": general_units(client),
        "exp_tables": exp_tables(client),
        "affinity": affinity(client),
        "fragment_stats": fragment_stats(client),
        "item_rarities": {str(res_id): word for res_id, word
                          in item_rarities(client).items()},
        "exploration_passives": {str(res_id): passives for res_id, passives
                                 in exploration_passives(client).items()},
        "card_skins": card_skins(client),
        "season_nodes": season_nodes(client),
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


def install_at(folder):
    """The install a folder the user picked belongs to, or None.

    The folder itself, or the nearest folder above it holding the
    manifest -- someone picking `bin` or `gameres` means the install
    around it -- or a `ChaosZeroNightmare` folder directly inside it.
    """
    if not folder:
        return None
    start = Path(folder)
    for candidate in (start, *list(start.parents)[:4],
                      start / DEFAULT_INSTALL.name):
        if build_of(candidate) is not None:
            return candidate
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


def fallback(settings_dir):
    """The cache read at an earlier build, where it is newer than the
    shipped tables: what a launch uses when this build cannot be read,
    or the client is not found. None otherwise, and the shipped tables
    stand.

    `cached` takes a cache only for the build it was read at, so without
    this a patch that made the client unreadable would drop the last
    good read for the older one the program shipped with."""
    from game_data import from_client
    try:
        held = json.loads((Path(settings_dir) / CACHE_FILE).read_text(
            encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(held, dict) or held.get("format") != CACHE_FORMAT:
        return None
    build = held.get("build")
    if not isinstance(build, int) or build <= from_client.BUILD:
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
# `known_item_rarities`, worked out once per `use`: `item_art` asks it
# for every tile it draws.
_rarities = None
# How many times `use` has run: see `generation`.
_generation = 0
# `known_limits`, worked out once per `use`.
_limits = None


def use(facts):
    """Make `facts` (from `cached`, `refresh` or `fallback`) what the
    accessors read, and lay its combatants, partners, exp tables,
    Affinity and slot options over the hand tables
    (`game_data.client_overlay`). None goes back to the shipped tables
    alone."""
    global _facts, _rarities, _generation, _limits
    _facts = facts if isinstance(facts, dict) else None
    _rarities = None
    _limits = None
    _generation += 1
    from game_data import client_overlay
    client_overlay.apply(_facts)


def facts_build():
    """The build the facts in use were read at, or None where the
    shipped tables alone stand."""
    return (_facts or {}).get("build")


def generation():
    """How many times `use` has replaced the facts. Whatever keeps a
    table worked out from them builds it again once this moves: on the
    first launch after a patch the client is read on a worker, and the
    read lands after the tabs that show it were built."""
    return _generation


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


def known_event_totals():
    """{schedule id: (rewards, final, steps)}: the shipped table, with
    what this machine's client says over it. See `event_totals`."""
    from game_data import from_client
    out = {key: tuple(value) for key, value
           in from_client.EVENT_TOTALS.items()}
    for key, value in ((_facts or {}).get("event_totals") or {}).items():
        if (isinstance(value, (list, tuple)) and len(value) == 3
                and all(isinstance(n, int) and n >= 0 for n in value)):
            out[key] = tuple(value)
    return out


def known_limits():
    """{kind: figure or {id: figure}}: the shipped table, with what this
    machine's client says over it, kind by kind and, within a kind, id
    by id. See `limits`. Worked out once per `use`: the Checklist asks
    for one on every row it reads."""
    global _limits
    if _limits is None:
        from game_data import from_client
        out = {}
        for source in (getattr(from_client, "LIMITS", {}),
                       (_facts or {}).get("limits") or {}):
            for kind, value in (source.items() if isinstance(source, dict)
                                else ()):
                if isinstance(value, dict):
                    held = out.setdefault(kind, {})
                    if isinstance(held, dict):
                        held.update({key: figure for key, figure
                                     in value.items() if _whole(figure)})
                elif _whole(value):
                    out[kind] = value
        _limits = out
    return _limits


def known_trial_slots():
    """{trial id: (slot ids)}: the shipped table, with what this
    machine's client says over it. See `trial_slots`."""
    from game_data import from_client
    out = {key: tuple(value) for key, value
           in getattr(from_client, "TRIAL_SLOTS", {}).items()}
    for key, value in ((_facts or {}).get("trial_slots") or {}).items():
        if (isinstance(value, (list, tuple)) and value
                and all(isinstance(s, str) for s in value)):
            out[key] = tuple(value)
    return out


def known_payment_events():
    """{schedule id: (define id, token res_id, ((tier id, tokens),
    ...))}: the shipped table, with what this machine's client says
    over it. See `payment_events`."""
    from game_data import from_client
    out = {}
    for source in (getattr(from_client, "PAYMENT_EVENTS", {}),
                   (_facts or {}).get("payment_events") or {}):
        for key, event in source.items():
            if not isinstance(event, dict):
                continue
            tiers = event.get("tiers")
            if (isinstance(event.get("define"), str)
                    and isinstance(event.get("item"), int) and tiers
                    and all(isinstance(t, (list, tuple)) and len(t) == 2
                            and isinstance(t[0], str)
                            and isinstance(t[1], int) for t in tiers)):
                out[key] = (event["define"], event["item"],
                            tuple(tuple(t) for t in tiers))
    return out


def known_story_chapters():
    """{schedule id: (episode ids)}: the shipped table, with what this
    machine's client says over it. See `story_chapters`."""
    from game_data import from_client
    out = {key: tuple(value) for key, value
           in from_client.STORY_CHAPTERS.items()}
    for key, value in ((_facts or {}).get("story_chapters") or {}).items():
        if (isinstance(value, (list, tuple)) and value
                and all(isinstance(e, str) for e in value)):
            out[key] = tuple(value)
    return out


def known_daily_tasks():
    """{daily task res_id: (score it counts to, Activity it pays)}: the
    shipped table, with what this machine's client says over it. See
    `daily_tasks`."""
    from game_data import from_client
    out = {key: tuple(value) for key, value
           in from_client.DAILY_TASKS.items()}
    for key, value in ((_facts or {}).get("daily_tasks") or {}).items():
        if (isinstance(value, (list, tuple)) and len(value) == 2
                and all(isinstance(n, int) and n > 0 for n in value)):
            out[key] = tuple(value)
    return out


def known_item_names():
    """{item res_id: English name}: the shipped table, with what this
    machine's client says over it, a placeholder in either not being a
    name (`NAMING`). These go over the program's own names, which stand
    where neither names an item (`game_data.constants.item_names`)."""
    from game_data import from_client
    out = {res_id: name for res_id, name in from_client.ITEM_NAMES.items()
           if NAMING.search(name)}
    for res_id, name in ((_facts or {}).get("item_names") or {}).items():
        if str(res_id).isdigit() and isinstance(name, str) \
                and NAMING.search(name):
            out[int(res_id)] = name
    return out


def known_item_rarities():
    """{item res_id: the game's rarity word}: the shipped table, with
    what this machine's client says over it. `constants.item_art` puts
    these over the item tables' own."""
    global _rarities
    if _rarities is None:
        from game_data import from_client
        out = {res_id: word for word, ids
               in getattr(from_client, "ITEM_RARITIES", {}).items()
               for res_id in ids}
        for res_id, word in ((_facts or {}).get("item_rarities")
                             or {}).items():
            if str(res_id).isdigit() and word in ITEM_RARITY_WORDS.values():
                out[int(res_id)] = word
        _rarities = out
    return _rarities


def known_chaos_names():
    """{stage id: (English name, season)}: the shipped table, with what
    this machine's client says over it. These go over `chaos_estimate`'s
    own names, which stand where neither names a stage."""
    from game_data import from_client
    out = dict(getattr(from_client, "CHAOS_NAMES", {}))
    for stage, named in ((_facts or {}).get("chaos_names") or {}).items():
        if str(stage).isdigit() and isinstance(named, (list, tuple)):
            out[int(stage)] = tuple(named)
    return out


def known_zero_specials():
    """{special option id: the game's name}: the shipped table, with
    what this machine's client says over it. These go over
    `chaos_estimate.ZERO_SPECIALS`."""
    from game_data import from_client
    out = dict(getattr(from_client, "ZERO_SPECIALS", {}))
    out.update((_facts or {}).get("zero_specials") or {})
    return out


def known_exploration_passives():
    """{partner res_id: ((name, acts on the assigned combatant alone,
    ((limit break, its text from then on), ...)), ...)}: the shipped
    table, with what this machine's client says over it, partner by
    partner. See `exploration_passives`."""
    from game_data import from_client
    out = dict(getattr(from_client, "EXPLORATION_PASSIVES", {}))
    for key, passives in ((_facts or {}).get("exploration_passives")
                          or {}).items():
        try:
            out[int(key)] = tuple(
                (str(p["name"]), bool(p["assigned"]),
                 tuple((int(at), str(text)) for at, text in p["steps"]))
                for p in passives)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def known_card_skins():
    """({skin res_id: (name, rarity, the combatant it is for)}, {pack
    id: (name, {rarity: the chance a pull is one}, the combatant its
    Super Rare is for)}): the shipped tables, with what this machine's
    client says over them. See `card_skins`."""
    from game_data import from_client
    skins = dict(getattr(from_client, "CARD_SKINS", {}))
    packs = dict(getattr(from_client, "CARD_SKIN_PACKS", {}))
    held = (_facts or {}).get("card_skins") or {}
    for key, skin in (held.get("skins") or {}).items():
        if str(key).isdigit() and isinstance(skin, (list, tuple)) \
                and len(skin) == 3:
            skins[int(key)] = tuple(skin)
    for key, pack in (held.get("packs") or {}).items():
        if isinstance(pack, (list, tuple)) and len(pack) == 3 \
                and isinstance(pack[1], dict):
            packs[key] = (pack[0], dict(pack[1]), pack[2])
    return skins, packs


def known_season_nodes():
    """{season: (amplification nodes by the end of each part, ...)}: the
    shipped table, with what this machine's client says over it, season
    by season. See `season_nodes`."""
    from game_data import from_client
    out = {season: tuple(counts) for season, counts
           in getattr(from_client, "SEASON_NODES", {}).items()}
    for season, counts in ((_facts or {}).get("season_nodes") or {}).items():
        if isinstance(counts, list) and counts and all(
                isinstance(n, int) for n in counts):
            out[str(season)] = tuple(counts)
    return out


def known_general_units():
    """The Normal Rescues' 5-stars by the client, this machine's read
    over the shipped one; None where neither holds a list. A rates reply
    the account captured goes over both (`gacha_history`)."""
    from game_data import from_client
    units = (_facts or {}).get("general_units") \
        or getattr(from_client, "GENERAL_UNITS", None)
    return set(units) if units else None


def visit_types(res_id):
    """How many Excursion types a combatant has, or None."""
    from game_data import from_client
    own = (_facts or {}).get("excursion_types") or {}
    count = own.get(str(res_id)) or from_client.EXCURSION_TYPES.get(res_id)
    return count if isinstance(count, int) and count > 0 else None


def known_set_effects():
    """{set id: (name, pieces, words, stat, value)}: the shipped table,
    with what this machine's client says over it. See `set_effects`."""
    from game_data import from_client
    out = {set_id: tuple(effect) for set_id, effect
           in from_client.SET_EFFECTS.items()}
    for set_id, effect in ((_facts or {}).get("set_effects") or {}).items():
        if (str(set_id).isdigit() and isinstance(effect, (list, tuple))
                and len(effect) == 5 and effect[2]):
            out[int(set_id)] = tuple(effect)
    return out


def potential_text(res_id, wire):
    """The game's own words for node `wire` (70, 51) of a combatant, or
    None. See `potential_texts`."""
    from game_data import from_client
    own = ((_facts or {}).get("potential_texts") or {}).get(str(res_id))
    words = (own or {}).get(str(wire)) or \
        (from_client.POTENTIAL_TEXTS.get(res_id) or {}).get(wire)
    return words if isinstance(words, str) and words else None
