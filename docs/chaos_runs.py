"""Write `docs/chaos_runs.tsv`: one Chaos run per row, and report what
pays in a run and whether it has moved.

    python docs/chaos_runs.py          # the runs' file, snapshots, and logs since the newest row
    python docs/chaos_runs.py --all    # the same, and every log, loose and archived

`docs/chaos_runs.cmd` runs the first from Explorer.

**A run comes from three places, and is one row.** The capture files
every Chaos run into a file of its own (`Vribbels/chaos_store.py`);
snapshots from before that file carry theirs as `chaos_runs`; and a
debug log replays through the same capture code to the same records --
see `Addon._note_chaos` in `Vribbels/capture/manager.py`. A run is
keyed by the second it cleared, which all three give alike, so a run
several hold is one row, whose `log` names the debug log.

**A run can span captures**, and the logs replay in order into one
folder, so a run one leaves open is taken up by the next, as the
capture does. What was played while no capture watched -- on another
device, or between two captures -- is in `gaps`: what the clear's own
restatement recovers, placed by the amounts the season's runs were
seen paying, and what stays unknown, which makes the run partial and
leaves it out of the mark rates.

**Only the live season's own Chaos is averaged for what it pays.** A
past season's Chaos -- entered through the Zero System -- pays the live
season's currency too, but less, so the means, the report and the
shipped figures read the season's own Chaos alone, and every other
Chaos gets its own lines after them. **How often a fight carries a mark
is read over every Chaos**: nothing found so far sets one Chaos's rate
apart, and the figures are rebuilt from the rows whenever that changes.
Each mark is counted over the Chaoses it has been met in, so a season's
own mark is not thinned by runs that cannot meet it.

Re-run it after any capture that holds a run. **By default it reads
every loose snapshot, and only the logs from the one that holds the
newest log-read row onward** -- that log is read again, since a run may
have been added to it after the last pass -- and keeps every older row
as the file has it. The archive is opened only when that log is no
longer loose. `--all` rebuilds every row, which is what a change to how
a run is read needs.

**Columns to the RIGHT of `log` are yours and are kept**, matched to
the run by its `date`: what happened in a run that the wire cannot say,
such as a boss lost to.

**`missed` is the one of yours this script reads**, and is always
there to fill in: what a run would have paid but for a mistake -- a
floor lost to a boss, a reward left behind. What a run pays, as the
report prints it, counts `total + missed`, since it stands for what a
run pays played through; `total` stays what was paid. Say in `notes`
what was missed.

**A lost run that still counts as whole fills its own `missed`** where
the cell is empty: the lost fight's payout and every boss after it, as
the latest cleared run of that season part paid them --
`chaos_estimate.missed`, which also says when a lost run counts. A
cell you filled is kept, and flagged where the two disagree.

The columns this script owns:

| column    | what it says                                                  |
| --------- | --------------------------------------------------------------- |
| `date`    | when the run was cleared, UTC                                   |
| `season`  | the Galactic Disaster season it ran in                          |
| `part`    | which part of the season: the shop page open when it cleared   |
| `chaos`   | which Chaos it was, by the stage id its clear names -- `chaos_estimate.CHAOS_NAMES`, else the game client's name (`chaos_estimate.chaos_names`) |
| `door`    | how it was entered: `Galactic Disaster`, `Zero System` or `own screen` (a base-game Chaos's) |
| `difficulty` | the number ending the list id it was entered with (`6`), or a Zero System map's level (`lv80`) |
| `floors`  | the map's floors as its entry gives them (`floor_info`): `0-28`, the last being the second boss's; `?` for a run filed before runs kept them |
| `special` | a Zero System map's special options, by `chaos_estimate.ZERO_SPECIALS` where named, else the game client's name (`zero_special_name`) |
| `options` | a Zero System map's bonus and penalty options: `b001 p112` |
| `rolled`  | the bonus and penalties the run rolled, any door, as effects: `ELITE_ADD:p008 CREDIT_DOWN:p016` |
| `amplified` | how many of the season's `Memory Resonance Amplification` nodes were in force: each pays +1% of the season's currency (`chaos_estimate.run_nodes`); `?` for a run filed before runs kept their effects |
| `partners` | each combatant's partner and its limit break, in team order: `Sig LB2, Peko LB0, Nyx LB4`; `?` for a run filed before runs kept them |
| `invasion` | what the partners' Exploration Passives raised the Invasion chance by, in the game's words: `+16%` of the base chance (`chaos_estimate.run_raise`); empty for none, and for a run played before the passives came; `?` where `partners` is |
| `mode`    | `delegated`, played by the Delegation Module down one path, or `ordinary` |
| `client`  | the game client and data patch it ran on: `cznlive 1.464 r688`  |
| `total`   | what the run paid in the season's currency                      |
| `payouts` | every payout in order, `floor:spot:amount`, `+mark` for a mark; one no capture saw, which the clear restated, after them with `~` (`?` for a floor unknown) |
| `marked`  | the fights carrying a mark, paid or not: `k5:2 e:1`             |
| `marked_at` | the same by the spot each was met on: `battle.k5:1 elite.k5:1` |
| `fought`  | the fights, by spot: `battle:11 elite:4 boss:3`; `unknown` is a fight a `?` encounter offered, `break_in` a hidden mini-boss |
| `lost`    | where a lost run was lost: `floor:spot:non-boss fights left`, `+mark` for a mark |
| `gaps`    | how much of the run a capture saw: empty for all of it; else `started elsewhere` and `resumed N`, what the clear's restatement `recovered`, and `partial:` what stays unknown -- `chaos_estimate.recovery` |
| `SPOT_*`  | the payouts at each kind of spot, `+` between them              |
| `log`     | the capture it was read from                                    |

**What pays is the fight, and the wire names what makes one pay.** A
boss pays a set amount for its floor. Any other fight pays only where
it carries a mark -- the Rare Species, `keyword_tag` 5 (`k5`), or the
Aether Eater, a battle id ending `_e` (`e`) -- and each mark pays a set
amount. So a run's take is set but for how many marked fights it
meets. A hidden mini-boss is a break-in (`b1` is Senectus), paying
nothing of itself; one that breaks in on a Rare Species carries its
keyword, `b1+k5`, and pays as one. A mark the report has never seen is
flagged.

**The report after the table reads every amount at 0 nodes**, each
payout read back at its run's own `amplified` nodes
(`chaos_estimate.base_of`), the third boss as paid: what a node bought
is not a change, and the report is there to catch the game's own.

**A boss is named by its place in the run**, not its floor, since
each season's map puts them elsewhere: `boss 1` ends the first area,
`boss 2` the last floor the entry's `floors` names, `boss 3` is the
first past it (`boss_orders`). Every map captured fits: season 4's 17,
34 and its hidden area's 37, season 5's 17, 28 and 31, the first two
paying 144 at 0 nodes and the third an unscaled 60. The 60 is the
check on the order: a third boss paying otherwise, another boss paying
60, and a boss outside the order are flagged.

Its tables, in order: what a whole run pays played through, by part
and season; each set amount that differs at 0 nodes from the last run
that paid it, with what else changed between the two; what pays and
how often a fight met each mark, by season part and game version; each
season's own Chaos from one game version to the next -- a part always
opens with a version, so a part is never compared on its own -- and
where each Chaos puts its bosses. Flagged above them, besides the
bosses: a payout no whole amount at 0 nodes comes to, which would be
the 1% a node rule failing, a payout with no mark, and a mark never
seen before.

**A mark's rate is also tested for a shift in time**, taking a change
to be sudden and lasting, as a balance patch is: across the whole runs
in order, the split into a before and an after that fits best, kept
only if shuffling the runs rarely fits as well (`shifts`). Senectus,
met once a run at most, is tested run by run, met or not; every other
mark fight by fight. A run inside one of `chaos_estimate.RATE_EVENTS`
-- something that raised the rates for a while -- is left out. Last,
the figures `chaos_estimate.SHIPPED` wants, for the release step to
copy, each line green where it says what is shipped.

**A rate a run is not a rate a fight, and a map's own mix of fights can
move the first alone.** Season 5's Chaos -- and any Chaos given its
special option in the Zero System -- makes every floor after the first
boss an Elite or an Unidentified Area floor. Elite floors turn up as
often as before, so a run holds fewer ordinary battles and meets fewer
marks, with no mark's rate a fight moving. Read across that change, the
per-run figures and `shipped_figures` fall, and the shift test, which
takes battle and Elite fights together, can report a shift for a mark
met more on one kind than the other: the Aether Eater has only been met
on battles. That is the map, not the rates. The rates table's `on
battles` and `on Elites` read each kind of fight apart, and `special`
says which runs
had the option. Expect it at the end of season 5, against season 4's
runs, and again at the end of season 6, against season 5's.

**The skill trees move rates as they are levelled, and a Zero System
map's penalties move the mix of fights.** Every run records the Zero
System effects in force (`Addon._chaos_setup`): the account's Zero
System improvements, `ZERO_BREAK_IN_RATEUP__*` among them, in every
run; the season's own tree in its Galactic Disaster runs, where season
4's `ZERO_ENCOUNTER_RATEUP__COUNT_RARITY` node was taken between 09-07
and 09-17 -- none of the season's encounter-rate nodes is for a mark,
as read in game; and a map's penalties. A shift that lines up with one
of these is theirs.

**A partner can raise the Invasion chance.** The Exploration Passives,
which came with Rossweisse's patch (`chaos_estimate.PASSIVES_FROM`),
give some partners Danger Intuition --
Sig and Peko -- adding to Senectus's chance each time the run checks
for one. A run meets Senectus at most once and each missed check raises
the next one's chance, so the raise moves a run's chance by less than
the game's "+8%" says (`chaos_estimate.invasion_chance`). `invasion`
says each run's raise. The rates table and its shift test leave the
raised runs out of the break-in marks, the Senectus table after it
reads every run at its own raise, and `shipped_figures` reads the
break-in marks back to no raise, as `chaos_estimate.SHIPPED` keeps them.

**A Galactic Disaster run rolls a bonus and penalties as a codex
does**, with no choice of three, and `rolled` names every run's,
whichever door. `ELITE_ADD` among them adds Elite spaces to the map by
its level: `p005` to `p008` add 2, 4, 6 and 8, the client's
`zero_system_eff` says (`ELITE_ADD_SPACES`). Taking ordinary battles
away is what would move the Aether Eater, met only on them, so the
mark rates end with the fights a run met at each level and without it,
for each Chaos, special and mode that has runs at more than one. On
season 4's own Chaos the runs with it fought as many ordinary battles
as those without, and more Elites: on a path of fixed length, the
Elites took the place of spots that were not ordinary battles.

**How a run's rolls and path were chosen.** A Galactic Disaster run's
rolls are as the game dealt them: the maintainer does not reroll its
codex. A Zero System map is picked from three, so how often its runs
carry a penalty says nothing about how often one is rolled, though a
run's fights with it still compare. The Delegation Module takes the
path with the most floors carrying the season's effect, favouring the
floors that open the special boss on floor 17 and the extra boss on
36; season 3's effect sits only on fights, so its delegated runs meet
more of them. A manual run follows the player's aim for it -- Events
and Elites sought, rests without a shop avoided. So a figure a run
belongs to its mode, which `mode` keeps apart, and a rate a fight is
what every run shares.

**A season is named by the run, not by its currency.** Each season pays
in an item id of its own, and the capture names the season a run
cleared in from the Great Rift standings; the currency is then whatever
that run was paid most of. `CURRENCY` places only a run no standings
had been read before. A season's parts are dated the way the Checklist
dates its shop pages, for the season live in the newest snapshot; a
row keeps the part it was given once the season is over.

Nothing here writes to `snapshots/`; the archive is read in place.
"""
import collections
import datetime
import glob
import gzip
import importlib.util
import io
import json
import math
import os
import random
import re
import shutil
import sys
import tarfile
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Vribbels"
sys.path.insert(0, str(SOURCE))
os.chdir(SOURCE)

OUT = ROOT / "docs" / "chaos_runs.tsv"

# The season currencies seen so far. Only a run no standings named a
# season for is placed by this; see the module docstring.
CURRENCY = {3920001: "s01", 3920002: "s02", 3920006: "s03", 3920031: "s04",
            3920032: "s05"}

# What this script fills in. Anything after them in an existing file
# is the maintainer's and is carried over by `date`.
OWNED = ["date", "season", "part", "chaos", "door", "difficulty",
         "floors", "special", "options", "rolled", "amplified", "partners",
         "invasion", "mode", "client", "total", "payouts", "marked",
         "marked_at", "fought", "lost", "gaps"]
# The effect ids a run's rolled bonus and penalties come as, whichever
# door it was entered by.
ROLLED = (("zero_orb_bonus_", "b"), ("zero_orb_penalty_", "p"))
# **A season's skill tree raises what its Chaos pays.** The Environment
# Variables tree, bought with Memory of Light, holds small nodes called
# Memory Resonance Amplification, each `Increase <the season's
# currency> Gain Amount by 1%`: an effect of `game_client.AMPLIFY_GROUP`,
# the % its second option and the currency its third (the client's
# `zero_orb_season_skilltree` and `zero_system_eff` tables). A season's
# own nodes are `zero_season_s<N>_skill_...`, and only they raise its
# currency, so a run counts its own season's alone
# (`chaos_estimate.run_nodes`).

# Colour for a terminal; none where the output goes to a file or a pipe,
# or NO_COLOR is set.
COLOUR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
if COLOUR and sys.platform == "win32":
    # NOT dead code: an empty command is what switches a Windows console
    # to reading the colour codes rather than printing them.
    os.system("")
HEADING, FLAG, GOOD, QUIET = "1;36", "33", "32", "90"


def paint(text, code):
    """`text` in an ANSI colour, where `COLOUR` allows one."""
    return "\033[%sm%s\033[0m" % (code, text) if COLOUR else text
# The maintainer's column the summary reads: see the module docstring.
MISSED = "missed"
SPOT_COLUMN = "SPOT_TYPE_"
# What a payout no capture saw carries in `payouts` and the `SPOT_*`
# cells: the clear restated it (`gaps_of`). Read back by nothing that
# measures a payout -- it is placed by those, not seen.
RECOVERED = "~"

# The marks by the game's names; one missing here is new, and flagged.
MARKS = {"k5": "Rare Species", "e": "Aether Eater", "b1": "Senectus"}

# A rate comparison with fewer fights than this on either side says
# nothing, and one whose difference is under this many standard errors
# is chance.
FEWEST_FIGHTS = 30
Z_DIFFERS = 2.0

# A shift in a mark's rate needs this many whole runs on each side of
# it, and holds when fewer than this share of shuffled orders split as
# well. The shuffles are seeded, so a run of the script is repeatable.
FEWEST_RUNS = 5
SHIFT_ALPHA = 0.01
SHIFT_TRIALS = 999

from capture.manager import CaptureManager                    # noqa: E402
import chaos_estimate                                          # noqa: E402
import chaos_store                                             # noqa: E402
import game_client                                             # noqa: E402

# Each Chaos's season, by name, for telling the live season's own
# Chaos from a past one: `current`.
CHAOS_SEASONS = {name: season for name, season
                 in chaos_estimate.chaos_names().values()}


class _Flow:
    """The one thing `websocket_message` reads: the last message."""

    def __init__(self, payload, from_client):
        text = json.dumps(payload)

        class _Msg:
            content = text.encode("utf-8")
            is_text = True
        msg = _Msg()
        msg.text = text
        msg.from_client = from_client

        class _WS:
            messages = [msg]
        self.websocket = _WS()


def stamp(name):
    """A log's `YYYYMMDD_HHMMSS`, which sorts as its start time does."""
    found = re.search(r"websocket_debug_(\d{8}_\d{6})", name or "")
    return found.group(1) if found else ""


def logs(since=""):
    """(name, lines) for every debug log started at `since` or later,
    oldest first: a run one log leaves open is taken up by the next.

    The archive, then the loose logs -- and the archive only when
    `since` is older than every loose log. Compaction archives the
    oldest logs and leaves the newest loose, so the archive holds
    nothing newer than a loose log, and when `since` is loose walking
    it (a solid stream, decompressed end to end) would find nothing to
    read.
    """
    loose = sorted(glob.glob("snapshots/websocket_debug_*.jsonl.gz"))
    archive = "snapshots/archived_captures.tar.xz"
    if os.path.exists(archive) and not (since and loose
                                        and since >= stamp(loose[0])):
        print(paint("   opening the archive...", QUIET), flush=True)
        with tarfile.open(archive) as tf:
            for member in tf:
                if ("websocket_debug" not in member.name
                        or stamp(member.name) < since):
                    continue
                handle = tf.extractfile(member)
                if handle is None:
                    continue
                raw = handle.read()
                if member.name.endswith(".gz"):
                    raw = gzip.decompress(raw)
                yield os.path.basename(member.name), io.StringIO(
                    raw.decode("utf-8", "replace")).readlines()
    for path in loose:
        if stamp(path) >= since:
            with gzip.open(path, "rt", encoding="utf-8",
                           errors="replace") as fh:
                yield os.path.basename(path), list(fh)


def fresh_addon(work):
    """The real generated addon, built the way a capture builds it."""
    manager = CaptureManager(work, log_callback=lambda *a, **k: None)
    script = manager._generate_addon_script(debug_mode=False)
    spec = importlib.util.spec_from_file_location("_chaos_addon", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return type(module.addons[0])(
        work, dict_path=module.DICT_PATH, log_callback=lambda *a, **k: None,
        debug_mode=False, catalogue_path=work / "cat.json")


def runs_in(lines, addon):
    """Every whole run one log holds, as the capture records them."""
    for line in lines:
        if not line.strip():
            continue
        try:
            frame = json.loads(line)
        except ValueError:
            continue
        try:
            addon.websocket_message(_Flow(
                frame.get("data"),
                frame.get("direction") == "client_to_server"))
        except Exception:                                     # noqa: BLE001
            pass
    return list(addon.chaos_runs)


def snapshots():
    """(runs, newest snapshot): (source, run) for every run the runs'
    own file and the loose snapshots hold, and the newest snapshot's
    contents."""
    stored, note = chaos_store.read("snapshots")
    if note:
        print(paint("   ! the runs' file: %s" % note, FLAG))
    runs = [(chaos_store.FILE, run) for run in stored if run.get("closed")]
    newest = None
    for path in sorted(glob.glob("snapshots/memory_fragments_*.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        newest = data
        for run in data.get("chaos_runs") or ():
            if isinstance(run, dict) and run.get("closed"):
                runs.append((os.path.basename(path), run))
    return runs, newest


def season_parts(raw):
    """{season: [when each part opened, first to last]} for the season
    live in `raw`, dated the way the Checklist dates its shop pages; {}
    where nothing dates it."""
    if not raw:
        return {}
    try:
        import schedules
        import shop_stock
        from ui.tabs import checklist_tab
        group = shop_stock.season_group_of(
            checklist_tab.SEASONAL_SHOP_CATEGORY)
        name, season = schedules.live(group, raw, time.time())
        starts = checklist_tab._page_openings(raw, name, season)
    except Exception:                                         # noqa: BLE001
        return {}
    return {name: list(starts)} if name and starts else {}


def short(season):
    """`disaster_s04` as `s04`; None stays None."""
    return str(season).rsplit("_", 1)[-1] if season else None


def part_of(when, season, parts):
    """Which part of `season` a run clearing at `when` fell in, or `?`."""
    starts = parts.get(season)
    if not starts:
        return "?"
    opened = sum(1 for start in starts if start <= when)
    return "part %d" % opened if opened else "preseason"


def currency_of(run):
    """The item a run was paid most of, which is its season's currency."""
    paid = collections.Counter()
    for _floor, _spot, _mark, item, amount in run.get("paid") or ():
        paid[item] += amount
    return paid.most_common(1)[0][0] if paid else None


def token(floor, spot, mark, amount):
    """One payout as the `payouts` column writes it."""
    return "%s:%s:%s%s" % (floor, str(spot).lower(), amount,
                           "+" + mark if mark else "")


def payouts_of(cell, recovered=False):
    """(floor, spot, amount, mark) per payout in a `payouts` cell, one
    no capture saw (`RECOVERED`) left out unless `recovered`."""
    out = []
    for part in (cell or "").split():
        if part.endswith(RECOVERED):
            if not recovered:
                continue
            part = part[:-len(RECOVERED)]
        where, _, mark = part.partition("+")
        pieces = where.split(":")
        if len(pieces) != 3 or not pieces[2].isdigit():
            continue
        out.append((pieces[0], pieces[1], int(pieces[2]), mark))
    return out


def counts_of(cell):
    """{name: n} from a `marked` or `fought` cell."""
    out = {}
    for part in (cell or "").split():
        name, _, n = part.rpartition(":")
        if n.isdigit():
            out[name] = int(n)
    return out


def lost_token(lost):
    """A run's `lost` as the column writes it: `floor:spot:left`, and
    `+mark` for a mark; '' for a cleared run."""
    if not isinstance(lost, (list, tuple)) or len(lost) < 4:
        return ""
    floor, spot, mark, left = lost[:4]
    return "%s:%s:%s%s" % (floor, str(spot).lower(), left,
                           "+" + mark if mark else "")


def lost_of(cell):
    """A `lost` cell back as the capture's [floor, SPOT, mark, left], or
    None."""
    where, _, mark = (cell or "").partition("+")
    pieces = where.split(":")
    if (len(pieces) != 3 or not pieces[0].lstrip("-").isdigit()
            or not pieces[2].isdigit()):
        return None
    return [int(pieces[0]), pieces[1].upper(), mark, int(pieces[2])]


# The doors a run comes in by, as the `door` column names them.
DOORS = {"disaster": "Galactic Disaster", "zero_orb": "Zero System",
         "chaos": "own screen"}


def difficulty_of(run):
    """A run's difficulty as the `difficulty` column writes it: the
    number ending the list id a base-game or Galactic Disaster Chaos is
    entered with (`embody_chaos_04_06` is 6), a Zero System map's level
    (`lv80`), '?' where the record holds neither: season 4's runs at
    difficulty 8 entered `disaster_s04_08`. A Zero System map's
    difficulty is set when it is made and is not on the map; its level
    rises with each clear (`docs/capture_pipeline.md`, *The Zero
    System's codex*)."""
    codex = run.get("codex")
    if isinstance(codex, dict) and codex.get("lv") is not None:
        return "lv%s" % codex["lv"]
    tail = str(run.get("difficulty") or "").rsplit("_", 1)[-1]
    return str(int(tail)) if tail.isdigit() else "?"


def short_option(option):
    """A codex option as the `options` column writes it:
    `zero_orb_bonus_001` as `b001`, `zero_orb_penalty_112` as `p112`."""
    for prefix, letter in (("zero_orb_bonus_", "b"),
                           ("zero_orb_penalty_", "p")):
        if str(option).startswith(prefix):
            return letter + str(option)[len(prefix):]
    return str(option)


def rolled_of(run):
    """A run's rolled bonus and penalties as the `rolled` column writes
    them: `ELITE_ADD:p008`, the effect's group and its id, in the
    order the run's effects were filed. `?` for a run filed before
    runs kept their effects."""
    if "effects" not in run:
        return "?"
    out = []
    for group, eid, _values in run.get("effects") or ():
        for prefix, letter in ROLLED:
            if str(eid).startswith(prefix):
                name = str(group).split("__")[0]
                name = name[len("ZERO_"):] if name.startswith("ZERO_") \
                    else name
                out.append("%s:%s%s" % (name, letter,
                                        str(eid)[len(prefix):]))
    return " ".join(out)


def amplified_of(run, season):
    """How many of `season`'s amplification nodes a run had in force,
    as the `amplified` column writes it (`chaos_estimate.run_nodes`);
    `?` for a run filed before runs kept their effects, 0 for a season
    the row cannot name."""
    number = int(season[1:]) if str(season)[1:].isdigit() else -1
    held = chaos_estimate.run_nodes(run, number)
    return "?" if held is None else str(held)


def partners_of(run):
    """A run's partners as the `partners` column writes them, in team
    order: `Sig LB2, Peko LB0, Nyx LB4`; `?` for a run filed before runs
    kept their partners."""
    if "partners" not in run:
        return "?"
    from game_data.partners import PARTNERS
    return ", ".join(
        "%s LB%s" % ((PARTNERS.get(res_id) or {}).get("name") or res_id,
                     limit_break or 0)
        for res_id, limit_break, *_rest in run["partners"])


def invasion_of(run):
    """What a run's partners raised its Invasion chance by, as the
    `invasion` column writes it: in the game's words, a share of the
    base chance (`+16%`); empty for no raise, `?` where the run kept no
    partners (`chaos_estimate.run_raise`)."""
    raised = chaos_estimate.run_raise(run)
    if raised is None:
        return "?"
    return "+%g%%" % round(raised * 100 / chaos_estimate.INVASION_BASE, 2) \
        if raised else ""


def raise_of(row):
    """A row's Invasion raise in points, off its `invasion` cell: 0 for
    none, None for `?`."""
    cell = (row.get("invasion") or "").strip()
    if cell == "?":
        return None
    found = re.fullmatch(r"\+([\d.]+)%", cell)
    return float(found.group(1)) * chaos_estimate.INVASION_BASE / 100 \
        if found else 0.0


def met_of(row):
    """Whether a row's run met Senectus: a break-in mark in `marked`."""
    return any(chaos_estimate.is_invasion(mark) and n
               for mark, n in counts_of(row.get("marked")).items())


def rolled_counts(cell):
    """{group: effect id} from a `rolled` cell, or None for `?`."""
    if (cell or "?") == "?":
        return None
    return dict(part.split(":", 1) for part in cell.split() if ":" in part)


def marked_at_of(cell):
    """{spot: {mark: n}} from a `marked_at` cell."""
    out = collections.defaultdict(dict)
    for part in (cell or "").split():
        where, _, n = part.rpartition(":")
        spot, _, mark = where.partition(".")
        if n.isdigit() and mark:
            out[spot][mark] = int(n)
    return out


def run_of_row(row):
    """A row in the shape the capture records a run, for
    `chaos_estimate`'s readers. A payout the clear restated counts: a
    boss paid while no capture watched still paid, and a lost run is
    whole or not by it."""
    paid = [[int(floor) if floor.lstrip("-").isdigit() else floor,
             spot.upper(), mark, None, amount]
            for floor, spot, amount, mark
            in payouts_of(row["payouts"], recovered=True)]
    end = _map_end(row)
    return {"paid": paid, "lost": lost_of(row.get("lost")),
            "marked": counts_of(row.get("marked")),
            "floors": None if end is None else [0, end]}


def gaps_of(run, recovered, unknown):
    """The `gaps` cell: how much of a run a capture saw. Empty for one
    seen whole; else whether it was taken up again and how often, or
    entered while no capture watched, then what the clear's restatement
    `recovered` (`chaos_estimate.recovery`) and what stays unknown, the
    run then `partial`."""
    said = []
    if run.get("started_elsewhere"):
        said.append("started elsewhere")
    resumed = [when for when in run.get("resumed") or () if when]
    if resumed:
        said.append("resumed %d" % len(resumed))
    if recovered:
        said.append("recovered " + " ".join(
            token("?" if floor is None else floor, spot, mark, amount)
            for floor, spot, mark, amount in recovered))
    if unknown:
        said.append("partial: " + "; ".join(unknown))
    return ", ".join(said)


def row_of(run, source, parts, kinds=None):
    """One run as {column: cell}, over the columns this script owns.
    `kinds` is {season: `chaos_estimate.payout_kinds`}, which places a
    payout no capture saw (`gaps_of`); without it nothing is placed."""
    currency = currency_of(run)
    season = short(run.get("season")) or CURRENCY.get(currency, "?")
    paid = [p for p in run.get("paid") or () if p[3] == currency]
    recovered, unknown = chaos_estimate.recovery(
        run, (kinds or {}).get(run.get("season")) or {})
    part = part_of(run["closed"], run.get("season"), parts)
    # The capture's own stamp, for a season no longer live.
    if part == "?" and isinstance(run.get("part"), int):
        part = "part %d" % run["part"] if run["part"] else "preseason"
    row = {
        "date": datetime.datetime.fromtimestamp(
            run["closed"], datetime.UTC).strftime("%Y-%m-%d %H:%M"),
        "season": season,
        "part": part,
        "chaos": chaos_estimate.chaos_name(run),
        "door": DOORS.get(run.get("via", "disaster"), run.get("via")),
        "difficulty": difficulty_of(run),
        "floors": "-".join(map(str, run["floors"]))
                  if isinstance(run.get("floors"), list)
                  and len(run["floors"]) == 2 else "?",
        "special": "+".join(chaos_estimate.zero_special_name(s)
                            for s in (run.get("codex") or {}).get(
                                "special") or ()),
        "options": " ".join(
            short_option(o) for kind in ("bonus", "penalty")
            for o in (run.get("codex") or {}).get(kind) or ()),
        "rolled": rolled_of(run),
        "amplified": amplified_of(run, season),
        "partners": partners_of(run),
        "invasion": invasion_of(run),
        "mode": ("delegated" if run.get("delegated") else "ordinary")
                if "delegated" in run else "?",
        "client": run.get("client") or "?",
        "total": str(sum(amount for *_rest, amount in paid)
                     + sum(amount for *_rest, amount in recovered)),
        # A payout the clear restated and no capture saw carries `~`.
        "payouts": " ".join(
            [token(floor, spot, mark, amount)
             for floor, spot, mark, _item, amount in paid]
            + [token("?" if floor is None else floor, spot, mark, amount)
               + RECOVERED for floor, spot, mark, amount in recovered]),
        "marked": " ".join("%s:%d" % item for item in
                           sorted((run.get("marked") or {}).items())),
        "marked_at": " ".join(
            "%s.%s:%d" % (spot.lower(), mark, n)
            for spot, marks in sorted((run.get("marked_at") or {}).items())
            for mark, n in sorted(marks.items())),
        "fought": " ".join("%s:%d" % (spot.lower(), n) for spot, n in
                           sorted((run.get("fought") or {}).items())),
        "lost": lost_token(run.get("lost")),
        "gaps": gaps_of(run, recovered, unknown),
        "log": source,
    }
    by_spot = collections.defaultdict(list)
    for _floor, spot, _mark, _item, amount in paid:
        by_spot[SPOT_COLUMN + str(spot)].append(str(amount))
    for _floor, spot, _mark, amount in recovered:
        by_spot[SPOT_COLUMN + str(spot)].append(str(amount) + RECOVERED)
    for column, amounts in by_spot.items():
        row[column] = "+".join(amounts)
    return row


def current(row):
    """Whether a row is a run of its own season's Chaos -- what the
    means, the report and the shipped figures are about. A base-game
    Chaos never is. A row that cannot name its Chaos came the Galactic
    Disaster's way unless its stage is a bare number, which only an
    unnamed Chaos leaves."""
    name = row.get("chaos") or "?"
    if name in CHAOS_SEASONS and CHAOS_SEASONS[name] is None:
        return False
    season = CHAOS_SEASONS.get(name)
    if season is None:
        return not name.isdigit()
    return season == "disaster_" + row["season"]


def merge(rows, found, parts, theirs, full):
    """{date: row}: the file's `rows` with each run `found` -- (run, the
    log or snapshot it came from) -- written over its own, the
    maintainer's columns `theirs` kept. `full` rebuilds every row from
    what was found."""
    kept = {} if full else dict(rows)
    found = list(found)
    every = [run for run, _source in found]
    kinds = {season: chaos_estimate.payout_kinds(every, season)
             for season in {run.get("season") for run in every}}
    for run, source in found:
        row = row_of(run, source, parts, kinds)
        old = rows.get(row["date"], {})
        # A row a log was replayed into stays as it is against the
        # capture's own record of the same run: the replay runs today's
        # capture code, and the record kept whatever the code of its day
        # did -- a break-in it could not see, fields it did not keep.
        if not full and stamp(old.get("log")) and not stamp(source):
            continue
        # A part is dated only while its season is live; a row read
        # again after keeps the one it was given.
        if row["part"] == "?" and old.get("part") not in (None, "", "?"):
            row["part"] = old["part"]
        if stamp(old.get("log")) and not stamp(source):
            row["log"] = old["log"]
        kept[row["date"]] = {**{c: old.get(c, "") for c in theirs}, **row}
    return kept


def existing():
    """(header, {date: {column: cell}}) from the file as it stands."""
    if not OUT.exists():
        return [], {}
    lines = OUT.read_text(encoding="utf-8").splitlines()
    if not lines or "log" not in lines[0].split("\t"):
        return [], {}
    header = lines[0].split("\t")
    rows = {}
    for line in lines[1:]:
        cells = line.split("\t")
        if cells and cells[0]:
            cells += [""] * (len(header) - len(cells))
            rows[cells[0]] = dict(zip(header, cells))
    return header, rows


def missed_of(row):
    """What a run lost to a mistake: the `missed` cell, blank for none."""
    cell = (row.get(MISSED) or "").strip()
    if not cell:
        return 0
    try:
        return int(cell)
    except ValueError:
        print(paint("   ! %s: `%s` is %r, not a number -- counted as 0"
                    % (row["date"], MISSED, cell), FLAG))
        return 0


# -------------------- the report's tables --------------------

# What an amount and a count are painted in.
AMOUNT, COUNT = "32", "35"
# The marks' order in the tables, before any other.
MARK_ORDER = ("e", "b1", "k5", "b1+k5")
# How many whole runs a Chaos needs for the Senectus table to read its
# checks; those with fewer are summed on one line.
FEWEST_INVASION_RUNS = 3
# What every third boss captured has paid, at any nodes: what
# `changes` holds a third boss to, and a 60 from any other boss is
# flagged.
THIRD_BOSS_PAYS = 60


def _segments(cell):
    """A grid cell as [(text, colour or None)]."""
    return cell if isinstance(cell, list) else [(str(cell), None)]


def _visible(cell):
    return sum(len(text) for text, _code in _segments(cell))


def _numeric(text):
    """Whether a cell reads as a number, and is right-aligned."""
    return bool(re.fullmatch(r"[-+]?[\d.,/%]+", text.strip()))


def grid(rows, head=(), indent="   ", align=None, joins=None):
    """Print `rows` -- lists of cells, each a string or [(text, colour)]
    segments -- as columns as wide as their widest cell, `head` above
    them in bold. A heading may be (text, span), over several columns.
    `align` is {column: "l" or "r"}, where unset a number right and all
    else left; `joins` {column: the gap after it}, two spaces where
    unset."""
    body = [list(row) for row in rows]
    heads = [cell if isinstance(cell, tuple) else (cell, 1) for cell in head]
    count = max([len(row) for row in body] + [sum(s for _t, s in heads)])
    if not count:
        return
    for row in body:
        row += [""] * (count - len(row))
    gaps = [(joins or {}).get(i, "  ") for i in range(count - 1)] + [""]
    widths = [max([_visible(row[i]) for row in body] + [0])
              for i in range(count)]
    spans, at = [], 0
    for text, span in heads:
        spans.append((text, range(at, at + span)))
        at += span
    for text, columns in spans:
        room = sum(widths[i] for i in columns) + sum(
            len(gaps[i]) for i in columns[:-1])
        widths[columns[-1]] += max(0, len(text) - room)

    def side(i, plain):
        return (align or {}).get(i) or ("r" if _numeric(plain) else "l")

    if spans:
        out = []
        for text, columns in spans:
            room = sum(widths[i] for i in columns) + sum(
                len(gaps[i]) for i in columns[:-1])
            right = len(columns) == 1 and all(
                side(columns[0], "".join(t for t, _c in _segments(row[
                    columns[0]]))) == "r" for row in body
                if _visible(row[columns[0]]))
            pad = " " * (room - len(text))
            out.append((pad + paint(text, "1") if right and body
                        else paint(text, "1") + pad) + gaps[columns[-1]])
        print((indent + "".join(out)).rstrip())
    for row in body:
        out = []
        for i, cell in enumerate(row):
            segments = _segments(cell)
            plain = "".join(t for t, _c in segments)
            text = "".join(paint(t, c) if c else t for t, c in segments)
            pad = " " * (widths[i] - _visible(cell))
            out.append((pad + text if side(i, plain) == "r" else text + pad)
                       + gaps[i])
        print((indent + "".join(out)).rstrip())


def heading(text):
    print()
    print(paint("   " + text, HEADING))


def _number(value):
    """An amount as printed: whole where it is whole."""
    return "%d" % value if float(value).is_integer() else "%.1f" % value


def _amounts(values):
    return [("/".join(_number(v) for v in sorted(values)), AMOUNT)]


def _count(k, n):
    return [("%d/%d" % (k, n), COUNT)]


def _version(client):
    """`cznlive 1.837 r126` as `1.837 r126`."""
    return str(client or "?").replace("cznlive ", "")


def _map_end(row):
    """The last floor a row's `floors` names -- the second boss's -- or
    None."""
    found = re.fullmatch(r"-?\d+-(\d+)", row.get("floors") or "")
    return int(found.group(1)) if found else None


def boss_orders(row):
    """{floor: name}: each boss floor a row paid on, by its place in the
    run, wherever the map puts it (`chaos_estimate.boss_places`, the
    estimate's own rule): `boss 1` to `boss 3`. A row with no `floors`
    -- a run filed before runs kept them -- is read by the order of its
    boss floors. A boss outside the order is `boss x<floor>`, and
    `changes` flags it."""
    floors = [int(floor) for floor, spot, _a, _m
              in payouts_of(row["payouts"], recovered=True)
              if spot == "boss" and floor.isdigit()]
    return {floor: "boss %d" % place if place else "boss x%d" % floor
            for floor, place in chaos_estimate.boss_places(
                floors, _map_end(row)).items()}


def base_payouts(row, recovered=False):
    """(key, spot, amount at 0 nodes, mark, amount as paid) for each
    payout a row was paid, read back at its run's own nodes
    (`chaos_estimate.base_of`), the third boss as paid: it has never
    moved with the nodes. A boss is keyed by its place in the run
    (`boss_orders`), a mark by itself (`_key`). With `recovered`, the
    payouts the clear restated too. None for a row whose nodes are
    `?`."""
    nodes = str(row.get("amplified") or "")
    if not nodes.isdigit():
        return None
    orders = boss_orders(row)
    out = []
    for floor, spot, amount, mark in payouts_of(row["payouts"], recovered):
        key = _key(floor, spot, mark, orders)
        out.append((key, spot, amount if key == "boss 3"
                    else chaos_estimate.base_of(amount, int(nodes)), mark,
                    amount))
    return out


def _key(floor, spot, mark, orders):
    """What a set amount is kept under: a mark by itself, a boss by its
    place in the run (`boss_orders`), a payout with no mark by its spot
    and floor."""
    if mark:
        return mark
    if spot == "boss":
        return orders.get(int(floor)) if floor.isdigit() else "boss ?"
    return "%s %s, no mark" % (spot, floor)


def _order(keys):
    """Keys in the tables' order: bosses by their place, then the marks
    in `MARK_ORDER`, then the rest."""
    def rank(key):
        found = re.fullmatch(r"boss (x?)(\d+)", key)
        if found:
            return (0, int(bool(found.group(1))), int(found.group(2)), key)
        if key in MARK_ORDER:
            return (1, 0, MARK_ORDER.index(key), key)
        return (2, 0, 0, key)
    return sorted(keys, key=rank)


def _named(key):
    """A set amount's or a mark's name as the report prints it; a fight
    carrying several marks, each by its name."""
    return " + ".join(MARKS.get(part, part) for part in key.split("+"))


def _group_facts(rows):
    """For one group of rows: ({key: its amounts at 0 nodes}, {mark:
    marked fights}, fights)."""
    amounts = collections.defaultdict(set)
    marked = collections.Counter()
    fights = 0
    for row in rows:
        for key, _spot, amount, _mark, _raw in base_payouts(row) or ():
            amounts[key].add(amount)
        marked.update(counts_of(row.get("marked")))
        fought = counts_of(row.get("fought"))
        fights += fought.get("battle", 0) + fought.get("elite", 0)
    return amounts, marked, fights


def _pays_cells(keys, amounts, marked, fights):
    """One row's cells for a what-pays grid: a boss's amounts at 0
    nodes, one column; a mark's in three -- its amounts, then how often
    a fight met it, `(k` and `/n)`, so the counts align on their `/`. A
    mark met and never paid pays nothing (`0`): Senectus alone."""
    cells = []
    for key in keys:
        if _single(key):
            cells.append(_amounts(amounts[key]) if key in amounts else "")
        elif key in marked:
            cells += [_amounts(amounts[key]) if key in amounts
                      else [("0", AMOUNT)],
                      [("(", None), (str(marked[key]), COUNT)],
                      [("/%d" % fights, COUNT), (")", None)]]
        else:
            cells += [""] * 3
    return cells


def _single(key):
    """Whether a what-pays key takes one column: a boss, or a payout
    with no mark. A mark takes three."""
    return key.startswith("boss") or key.endswith("no mark")


def _pays_layout(keys, lead):
    """(head, align, joins) for a what-pays grid whose first `lead`
    columns are the row's own: a boss one column, a mark three."""
    head, align, joins, at = [], {}, {}, lead
    for key in keys:
        if _single(key):
            head.append(_named(key))
            at += 1
        else:
            head.append((_named(key), 3))
            align.update({at: "r", at + 1: "r", at + 2: "l"})
            joins.update({at: " ", at + 1: ""})
            at += 3
    return head, align, joins


def changes(rows):
    """(rows for the changes grid, flags). A row for each set amount,
    read at 0 nodes, that differs from the last run that paid it, with
    what else changed between the two: what a node bought cannot move
    it. A boss is compared by its place in the run, whatever the map.

    Flagged: a third boss paying other than `THIRD_BOSS_PAYS`, and
    another boss paying it -- the two would mean the order and the pay
    no longer agree; a boss outside the map's order; a payout no whole
    amount at 0 nodes comes to; a payout with no mark; and a mark never
    seen before."""
    out, flags, last, unnamed = [], [], {}, set()
    for date in sorted(rows):
        row = rows[date]
        where = ("%s %s" % (row["season"], row["part"]),
                 _version(row.get("client")))
        for mark in counts_of(row.get("marked")):
            for part in mark.split("+"):
                if part not in MARKS and part not in unnamed:
                    unnamed.add(part)
                    flags.append("%s: a mark never seen before, %s -- add "
                                 "it to MARKS once named" % (date, part))
        paid = base_payouts(row)
        if paid is None:
            continue
        for key, spot, amount, mark, raw in paid:
            if not mark and spot != "boss":
                flags.append("%s: %s paid %d -- a paying fight nothing "
                             "names yet" % (date, key, raw))
                continue
            what = _named(key)
            if key.startswith("boss x"):
                flags.append("%s: a boss outside the map's order, on floor "
                             "%s (the map ends on %s), paid %d"
                             % (date, key[6:], _map_end(row), raw))
            elif key == "boss 3" and raw != THIRD_BOSS_PAYS:
                flags.append("%s: the third boss paid %d, not the %d every "
                             "third boss has" % (date, raw, THIRD_BOSS_PAYS))
            elif spot == "boss" and key != "boss 3" \
                    and raw == THIRD_BOSS_PAYS:
                flags.append("%s: %s paid %d, as only third bosses have"
                             % (date, what, raw))
            if not float(amount).is_integer():
                flags.append("%s: %s paid %d at %s nodes, which no whole "
                             "amount at 0 nodes comes to"
                             % (date, what, raw, row["amplified"]))
            if key in last and last[key][0] != amount:
                was, when, there = last[key]
                moved = ["%s -> %s" % (a, b) for a, b in zip(there, where)
                         if a != b]
                out.append([date, what, _amounts([was]), _amounts([amount]),
                            [(when, QUIET)], ", ".join(moved)
                            or "nothing else"])
            last[key] = (amount, date, where)
    return out, flags


def _rate_moved(a, b):
    """(cell, moved) comparing one mark's rate a fight between two
    groups, each (marked fights, fights); a `too few` cell where either
    has fewer than FEWEST_FIGHTS fights."""
    (ka, na), (kb, nb) = a, b
    text = _count(ka, na) + [(" -> ", None)] + _count(kb, nb)
    if min(na, nb) < FEWEST_FIGHTS:
        return text + [(" too few", QUIET)], False
    pa, pb = ka / na, kb / nb
    pooled = (ka + kb) / (na + nb)
    spread = math.sqrt(pooled * (1 - pooled) * (1 / na + 1 / nb)) or 1
    moved = abs((pb - pa) / spread) >= Z_DIFFERS
    return text + [(" MOVED", FLAG) if moved else (" same", GOOD)], moved


def bosses_table(rows):
    """Print where each Chaos puts its bosses, by their place in the run
    (`boss_orders`), and what each pays at 0 nodes, the third as paid:
    one row per season, Chaos, door and special option, over every row
    that paid a boss. What the order rule rests on, laid out for
    checking."""
    groups = collections.defaultdict(list)
    for row in rows.values():
        if any(spot == "boss" for _f, spot, _a, _m in payouts_of(
                row["payouts"], recovered=True)):
            groups[(row["season"], row["chaos"], row.get("door") or "",
                    row.get("special") or "")].append(row)
    if not groups:
        return
    found = collections.defaultdict(lambda: collections.defaultdict(set))
    keys = set()
    for group, members in groups.items():
        for row in members:
            orders = boss_orders(row)
            for key, spot, amount, _mark, _raw in base_payouts(
                    row, recovered=True) or ():
                if spot != "boss":
                    continue
                floor = next((f for f, k in orders.items() if k == key), "?")
                found[group][key].add((floor, amount))
                keys.add(key)
    keys = _order(keys)
    heading("Bosses by their place in the run: floor, then pay at 0 nodes "
            "(the third boss as paid)")
    table = []
    for group in sorted(groups, key=lambda g: (g[0], g[2], g[1], g[3])):
        season, chaos, door, special = group
        ends = sorted({_map_end(row) for row in groups[group]} - {None})
        row = [season, chaos, door, special, str(len(groups[group])),
               "/".join(map(str, ends)) or "?"]
        for key in keys:
            seen = sorted(found[group].get(key, ()))
            row.append(", ".join("%s" % floor for floor in sorted(
                {floor for floor, _a in seen})) if seen else "")
            row.append(_amounts({amount for _f, amount in seen})
                       if seen else "")
        table.append(row)
    head = ["season", "Chaos", "door", "special", "runs", "map ends"]
    head += [(_named(key), 2) for key in keys]
    grid(table, head=head,
         joins={6 + 2 * n: " " for n in range(len(keys))},
         align={6 + 2 * n: "r" for n in range(len(keys))})


def report(rows):
    """The changes run by run, what pays by season part and game version,
    and what moved between one game version and the next."""
    found, flags = changes(rows)
    heading("Changes run by run, at 0 nodes%s" % ("" if found or flags
                                                   else ": none"))
    for line in flags:
        print(paint("   ! " + line, FLAG))
    grid(found, head=["date", "what", "was", "now", "last paid",
                      "since then"] if found else ())

    groups, first = collections.defaultdict(list), {}
    for date in sorted(rows):
        row = rows[date]
        key = ("%s %s" % (row["season"], row["part"]),
               _version(row.get("client")))
        groups[key].append(row)
        first.setdefault(key, date)
    facts = {key: _group_facts(members) for key, members in groups.items()}
    keys = _order({key for amounts, marked, _f in facts.values()
                   for key in set(amounts) | set(marked)})
    heading("What pays, by season part and game version, at 0 nodes "
            "(and how often a fight met each mark)")
    head, align, joins = _pays_layout(keys, 4)
    grid([[part, version, str(len(groups[(part, version)])), str(fights)]
          + _pays_cells(keys, amounts, marked, fights)
          for (part, version), (amounts, marked, fights)
          in sorted(facts.items(), key=lambda item: first[item[0]])],
         head=["part", "version", "runs", "fights"] + head,
         align=align, joins=joins)

    # Each season's own Chaos, one version against the next: a part
    # always opens with a version, so a part on its own says nothing.
    pairs = []
    by_season = collections.defaultdict(list)
    for key in sorted(groups, key=lambda key: first[key]):
        by_season[key[0].split()[0]].append(key)
    for season, held in sorted(by_season.items()):
        pairs += [(season, a, b) for a, b in zip(held, held[1:])]
    marks = _order({mark for _season, a, b in pairs
                    for mark in set(facts[a][1]) | set(facts[b][1])})
    steps = []
    for season, a, b in pairs:
        (amounts_a, marked_a, fights_a) = facts[a]
        (amounts_b, marked_b, fights_b) = facts[b]
        moved = ["%s %s -> %s" % (_named(key), "/".join(
            map(_number, sorted(amounts_a[key]))), "/".join(
            map(_number, sorted(amounts_b[key]))))
            for key in _order(set(amounts_a) & set(amounts_b))
            if amounts_a[key] != amounts_b[key]]
        row = [season, "%s -> %s" % (a[1], b[1]),
               [("; ".join(moved), FLAG)] if moved else [("same", GOOD)]]
        for mark in marks:
            row.append(_rate_moved((marked_a[mark], fights_a),
                                   (marked_b[mark], fights_b))[0]
                       if marked_a[mark] or marked_b[mark] else "")
        steps.append(row)
    if steps:
        heading("From one game version to the next, each season's own "
                "Chaos: set amounts at 0 nodes, and each mark a fight")
        grid(steps, head=["season", "versions", "set amounts"]
             + [_named(mark) for mark in marks])



def _reference(rows, row):
    """({boss place: amount}, {mark: amount}) to price a lost run's
    `missed` by: its part's bosses as the latest cleared run of that
    season part paid them, and each mark as last paid -- the shipped
    figures where no run has. Each is taken to the lost run's own nodes
    (`chaos_estimate.amplified`): a shipped figure from base, a run's
    from base at that run's nodes (`base_of`), the `flat` bosses as
    they are."""
    season = "disaster_" + row["season"]
    entry = chaos_estimate.shipped_entry(season)
    nodes = _nodes(row)
    flat = chaos_estimate.flat_places(season)

    def at(amount, was, place=None):
        if place in flat:
            return amount
        return chaos_estimate.amplified(
            chaos_estimate.base_of(amount, was), nodes)

    marks = {mark: at(amount, 0)
             for mark, (amount, _rate) in (entry.get("marks") or {}).items()}
    found = re.match(r"part (\d+)$", row.get("part") or "")
    bosses = {place: at(amount, 0, place)
              for place, amount in (chaos_estimate.shipped_bosses(
                  entry, int(found.group(1))) if found else {}).items()}
    for date in sorted(rows):
        other = rows[date]
        for _floor, spot, amount, mark in payouts_of(other["payouts"]):
            if mark and spot != "boss":
                marks[mark] = at(amount, _nodes(other))
        if (other is row or other.get("lost")
                or (other["season"], other["part"], other.get("chaos"))
                != (row["season"], row["part"], row.get("chaos"))):
            continue
        places = chaos_estimate.run_places(run_of_row(other))
        table = {places[int(floor)]: at(amount, _nodes(other),
                                        places[int(floor)])
                 for floor, spot, amount, _mark
                 in payouts_of(other["payouts"])
                 if spot == "boss" and floor.isdigit()
                 and places.get(int(floor))}
        if table:
            bosses = table
    return bosses, marks


def _nodes(row):
    """A row's `amplified` nodes as a number, 0 where it says `?`."""
    cell = str(row.get("amplified") or "")
    return int(cell) if cell.isdigit() else 0


def fill_missed(rows):
    """Fill each whole lost run's empty `missed`; flag one filled by
    hand that the loss does not come to. The dates filled, in order."""
    filled = []
    for date in sorted(rows):
        row = rows[date]
        run = run_of_row(row)
        if not run["lost"] or not chaos_estimate.is_full(run):
            continue
        due = chaos_estimate.missed(run, *_reference(rows, row))
        cell = (row.get(MISSED) or "").strip()
        if not cell:
            if due:
                row[MISSED] = str(due)
                filled.append("%s +%d" % (date, due))
        elif missed_of(row) != due:
            print(paint("   ! %s: `missed` says %s; the loss comes to %d"
                        % (date, cell, due), FLAG))
    return filled


def _whole_runs(rows):
    """The rows a rate is counted over, oldest first: whole runs, none
    inside a `chaos_estimate.RATE_EVENTS` window."""
    out = []
    for date in sorted(rows):
        row = rows[date]
        when = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M").replace(
            tzinfo=datetime.UTC).timestamp()
        # A partial run's fights are not all known, so neither are its
        # marks (`chaos_estimate.is_partial`).
        if (chaos_estimate.is_full(run_of_row(row))
                and "partial" not in (row.get("gaps") or "")
                and not chaos_estimate.in_rate_event(when)):
            out.append(row)
    return out


def _log_likelihood(k, n):
    """Of k marked fights in n, at their own rate."""
    if k <= 0 or k >= n:
        return 0.0
    p = k / n
    return k * math.log(p) + (n - k) * math.log(1 - p)


def _best_split(ks, ns):
    """(what the best before-and-after split gains in log-likelihood
    over one rate throughout, where it falls), with `FEWEST_RUNS` a
    side; (0.0, None) where no split gains."""
    total_k, total_n = sum(ks), sum(ns)
    whole = _log_likelihood(total_k, total_n)
    best, at, k_left, n_left = 0.0, None, 0, 0
    for i in range(1, len(ks)):
        k_left += ks[i - 1]
        n_left += ns[i - 1]
        if min(i, len(ks) - i) < FEWEST_RUNS:
            continue
        gain = (_log_likelihood(k_left, n_left)
                + _log_likelihood(total_k - k_left, total_n - n_left)
                - whole)
        if gain > best:
            best, at = gain, i
    return best, at


def split_test(ks, ns, rng):
    """(where the best split falls, the share of shuffled orders that
    split as well), or (None, None) where there is no split to test."""
    gain, at = _best_split(ks, ns)
    if at is None:
        return None, None
    pairs = list(zip(ks, ns))
    beaten = 0
    for _ in range(SHIFT_TRIALS):
        rng.shuffle(pairs)
        if _best_split([k for k, _n in pairs],
                       [n for _k, n in pairs])[0] >= gain:
            beaten += 1
    return at, (beaten + 1) / (SHIFT_TRIALS + 1)


def shifts(ks, ns, rng, offset=0):
    """[(index, p)] for every shift in a rate over runs in order: the
    best split where it holds, then each side searched again."""
    at, p = split_test(ks, ns, rng)
    if at is None or p >= SHIFT_ALPHA:
        return []
    return (shifts(ks[:at], ns[:at], rng, offset) + [(offset + at, p)]
            + shifts(ks[at:], ns[at:], rng, offset + at))


def _met_in(runs):
    """{mark: the Chaoses it has been met in}, over `runs`."""
    out = collections.defaultdict(set)
    for row in runs:
        for key in counts_of(row.get("marked")):
            for one in key.split("+"):
                out[one].add(row["chaos"])
    return out


def rate_shifts(rows):
    """Print each mark's rate over the whole runs of every Chaos it has
    been met in -- a fight, a run, on each kind of ordinary fight (see
    the module docstring's note on a map's own mix of fights) -- and
    any shift in it. Senectus is met once a run at most, so its shift
    is looked for run by run, met or not; raised runs are
    `invasion_rates`' alone."""
    runs = _whole_runs(rows)
    met_in = _met_in(runs)
    # A run that does not say where its marks were met is left out of
    # the by-spot counts.
    told = {row["date"] for row in runs
            if row.get("marked_at") or not row.get("marked")}
    heading("Mark rates over time, over %d whole run(s)%s; each mark over "
            "the Chaoses it has been met in" % (
                len(runs), "" if len(runs) == len(rows)
                else " (%d left out)" % (len(rows) - len(runs))))
    table = []
    for mark in _order(met_in):
        invasion = chaos_estimate.is_invasion(mark)
        among = [row for row in runs if row["chaos"] in met_in[mark]
                 and not (invasion and raise_of(row))]
        fights, ks = [], []
        for row in among:
            fought = counts_of(row.get("fought"))
            fights.append(fought.get("battle", 0) + fought.get("elite", 0))
            ks.append(sum(n for key, n in counts_of(row.get("marked")).items()
                          if mark in key.split("+")))
        tested = ([min(1, k) for k in ks], [1] * len(ks)) if invasion \
            else (ks, fights)
        found = shifts(*tested, random.Random(0))
        if found:
            edges = [0] + [at for at, _p in found] + [len(ks)]
            shift = [("shifted: " + ", ".join(
                "%.3f %s from %s" % (
                    sum(tested[0][a:b]) / max(1, sum(tested[1][a:b])),
                    "a run" if invasion else "a fight",
                    among[a]["date"][:10]) for a, b in zip(edges, edges[1:]))
                + " (p %s)" % ", ".join("%.3f" % p for _at, p in found),
                FLAG)]
        else:
            _at, p = split_test(*tested, random.Random(0))
            shift = [("none (p %.2f)" % p, GOOD)] if p is not None \
                else [("too few runs (%d a side)" % FEWEST_RUNS, QUIET)]
        spots = []
        for spot in ("battle", "elite"):
            on = [row for row in among if row["date"] in told]
            n = sum(counts_of(row.get("fought")).get(spot, 0) for row in on)
            k = sum(count for row in on for key, count in marked_at_of(
                row.get("marked_at")).get(spot, {}).items()
                if mark in key.split("+"))
            spots.append(_count(k, n) + [(" %.3f" % (k / n), None)]
                         if n and k else "")
        total, met = sum(ks), sum(1 for k in ks if k)
        table.append([_named(mark), _count(total, sum(fights)),
                      "%.3f" % (total / max(1, sum(fights))),
                      "%.2f" % (total / max(1, len(among))),
                      _count(met, len(among)), str(len(met_in[mark]))]
                     + spots + [shift])
    grid(table, head=["mark", "met / fights", "a fight", "a run",
                      "runs met", "Chaos", "on battles", "on Elites",
                      "shift over time"])
    penalty_mix(runs)
    invasion_rates(runs)


def _setting(row):
    """A row's Chaos, special and mode, as the tables group them."""
    return ", ".join(cell for cell in (
        row["chaos"], row.get("special"), row["mode"]) if cell)


def invasion_rates(runs):
    """Print, for each Chaos, special and mode with enough whole runs,
    how often a run met Senectus, and what the client's rule makes of it
    (`chaos_estimate.invasion_chance`): the checks a run gets, fitted to
    every run at its own raise, and a run's chance at no raise and at
    each Danger Intuition step. A run that kept no partners counts as
    raising nothing, and is flagged where the game had the passives by
    then. Raised runs meeting Senectus more or less often than the rule
    says, over enough runs, is the rule being wrong, and is for the doc
    first."""
    unknown = [row["date"] for row in runs if raise_of(row) is None
               and chaos_estimate.had_passives({"client": row.get("client")})]
    by = collections.defaultdict(list)
    for row in runs:
        by[_setting(row)].append((met_of(row), raise_of(row) or 0.0))
    if not by:
        return
    steps = sorted({value for passives in
                    game_client.known_exploration_effects().values()
                    for effect, values in passives
                    if effect == chaos_estimate.INVASION_EFFECT
                    for _at, value in values})
    raised = any(value for held in by.values() for _met, value in held)

    def pct(value):
        return "+%g%%" % round(value * 100 / chaos_estimate.INVASION_BASE, 2)

    heading("Senectus a run, one at most (`chaos_estimate.invasion_chance`), "
            "Chaos with %d whole runs or more" % FEWEST_INVASION_RUNS)
    if unknown:
        print(paint("   ! played with Exploration Passives but no partners "
                    "kept, counted as no raise: %s" % ", ".join(unknown),
                    FLAG))
    table, few = [], []
    for key, held in sorted(by.items()):
        if len(held) < FEWEST_INVASION_RUNS:
            few.extend(held)
            continue
        met = sum(1 for hit, _value in held if hit)
        row = [key, _count(met, len(held))]
        if raised:
            row.append("; ".join("%s %d/%d" % (
                pct(value) if value else "none",
                sum(1 for hit, v in held if hit and v == value),
                sum(1 for _hit, v in held if v == value))
                for value in sorted({v for _hit, v in held})))
        if 0 < met < len(held):
            checks = chaos_estimate.invasion_fit(held)
            row.append("%.1f" % checks)
            row += ["%.2f" % chaos_estimate.invasion_chance(checks, value)
                    for value in [0.0] + steps]
        else:
            row += [[("every run met one" if met else "none met", QUIET)]]
        table.append(row)
    grid(table, head=["Chaos", "met", *(["by raise"] if raised else []),
                      "checks", "no raise", *map(pct, steps)])
    if few:
        print(paint("   the rest, under %d run(s) each: %d of %d met one" % (
            FEWEST_INVASION_RUNS, sum(1 for hit, _v in few if hit),
            len(few)), QUIET))


# ELITE_ADD's levels by the penalty id a run rolls, as the Elite spaces
# each adds to the map: the client's `zero_system_eff` rows, `opt_1`.
ELITE_ADD_SPACES = {"p005": 2, "p006": 4, "p007": 6, "p008": 8}


def penalty_mix(runs, group="ELITE_ADD"):
    """Print the fights a whole run met at each level of a rolled `group`
    penalty and without it, for each Chaos, special and mode that has
    runs at more than one: whether it takes ordinary battles away is
    what moves a mark met only on them. A Chaos's map and a mode's
    choice of path set a run's mix of fights too, so runs are only
    compared among their own. A run filed before runs kept their
    effects is left out."""
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for row in runs:
        rolled = rolled_counts(row.get("rolled"))
        if rolled is not None:
            by[_setting(row)][rolled.get(group)].append(
                counts_of(row.get("fought")))
    compared = {key: levels for key, levels in by.items() if len(levels) > 1}
    if not compared:
        return
    heading("Fights a whole run, by the %s level rolled (the Elite spaces "
            "it adds)" % group)
    table = []
    for key, levels in sorted(compared.items()):
        for level in sorted(levels, key=lambda level: (level is not None,
                                                       level or "")):
            fought = levels[level]
            spaces = ELITE_ADD_SPACES.get(level)
            table.append([
                key, "none" if level is None else "%s (+%s)" % (
                    level, spaces if spaces is not None else "?"),
                str(len(fought)),
                "%.1f" % (sum(f.get("battle", 0) for f in fought)
                          / len(fought)),
                "%.1f" % (sum(f.get("elite", 0) for f in fought)
                          / len(fought))])
            key = ""
    grid(table, head=["Chaos", group, "runs", "battles", "Elites"])


def shipped_figures(rows):
    """Print, per season, what `chaos_estimate.SHIPPED` wants, at 0
    nodes: each part's bosses as its latest cleared run paid them, each
    mark's amount as last paid, each read back at its run's own nodes
    (`chaos_estimate.base_of`, the season's `flat` bosses as paid); each
    mark per whole run, the break-in marks' at no Invasion raise
    (`chaos_estimate.base_rates`); and the most nodes a part's runs had,
    beside the shipped `nodes` to compare. A line is green where it
    says what is shipped, yellow, with what is, where it differs."""
    by_season = collections.defaultdict(dict)
    for date, row in rows.items():
        if row["season"] != "?":
            by_season[row["season"]][date] = row
    heading("For chaos_estimate.SHIPPED (green: as shipped)")
    for season in sorted(by_season):
        members = by_season[season]
        flat = chaos_estimate.flat_places("disaster_" + season)
        bosses, amounts, most = {}, {}, {}
        for date in sorted(members):
            row = members[date]
            nodes = _nodes(row)
            for _floor, spot, amount, mark in payouts_of(row["payouts"]):
                if mark and spot != "boss":
                    amounts[mark] = chaos_estimate.base_of(amount, nodes)
            found = re.match(r"part (\d+)$", row["part"] or "")
            places = chaos_estimate.run_places(run_of_row(row))
            table = {places[int(floor)]: amount
                     if places[int(floor)] in flat
                     else chaos_estimate.base_of(amount, nodes)
                     for floor, spot, amount, _mark
                     in payouts_of(row["payouts"])
                     if spot == "boss" and floor.isdigit()
                     and places.get(int(floor))}
            if found:
                part = int(found.group(1))
                most[part] = max(most.get(part, 0), nodes)
                if table and not row.get("lost"):
                    bosses[part] = table
        whole = _whole_runs(members)
        counted = collections.Counter()
        for row in whole:
            for key, n in counts_of(row.get("marked")).items():
                counted[key] += n
        # The break-in marks at no Invasion raise, as SHIPPED keeps them.
        rates = chaos_estimate.base_rates(
            {mark: counted[mark] / len(whole) for mark in counted},
            [(met_of(row), raise_of(row) or 0.0) for row in whole]) \
            if whole else {}
        marks = {mark: (amounts.get(mark, 0), round(rates.get(mark, 0), 2))
                 for mark in sorted(set(amounts) | set(counted))}
        tree = game_client.known_season_nodes().get("disaster_" + season)
        shipped = chaos_estimate.SHIPPED.get("disaster_" + season) or {}

        def line(key, value, note=""):
            same = shipped.get(key) == value
            text = '           "%s": %s,%s' % (key, value, note)
            if not same:
                text += "  # shipped: %s" % (shipped.get(key),)
            print(paint(text, GOOD if same else FLAG))

        print('       "disaster_%s": {' % season)
        line("bosses", dict(sorted(bosses.items())))
        line("flat", tuple(sorted(flat)))
        line("nodes", tuple(tree or ()), "  # the client's tree; runs had "
             "at most %s" % dict(sorted(most.items())))
        line("marks", marks, "  # %d whole run(s)" % len(whole))
        print('       },')


def others_table(others):
    """Print every Chaos other than the season's own, a row each: what
    it paid at 0 nodes, and how often a fight met each mark."""
    heading("Other Chaos, left out of everything above but the mark rates")
    table = []
    for label in sorted(others):
        rows = others[label]
        amounts, marked, fights = _group_facts(rows)
        chaos, door, special, mode = label
        pays = []
        for key in _order(amounts):
            pays += [("%s " % _named(key), None)] + _amounts(amounts[key]) \
                + [("  ", None)]
        met = []
        for key in _order(marked):
            met += [("%s " % _named(key), None)] + _count(marked[key], fights) \
                + [("  ", None)]
        table.append([chaos, door, special, mode, str(len(rows)),
                      pays or [("nothing", QUIET)],
                      met or [("none", QUIET)]])
    grid(table, head=["Chaos", "door", "special", "mode", "runs",
                      "pays, at 0 nodes", "marks met a fight"])


def main():
    full = "--all" in sys.argv[1:]
    header, rows = existing()
    theirs = header[header.index("log") + 1:] if header else []
    if MISSED not in theirs:
        theirs.insert(0, MISSED)
    from_logs = [row["log"] for row in rows.values() if stamp(row["log"])]
    since = "" if full or not from_logs else max(map(stamp, from_logs))
    if since:
        print(paint("Reading Chaos runs from the snapshots, and from "
                    "websocket_debug_%s on (the newest row's log); --all "
                    "reads every log." % since, QUIET), flush=True)
    else:
        print(paint("Reading Chaos runs from the snapshots and every log, "
                    "loose and archived.", QUIET), flush=True)

    held, newest = snapshots()
    parts = season_parts(newest)
    # By the second each run cleared: a run a snapshot and a log both
    # hold is one run, and the log, read second, names it.
    found = {run["closed"]: (run, name) for name, run in held}
    seen = 0
    # **One folder for every log, in order**, each through a fresh addon
    # as a restart does: a run one capture leaves open is taken up by
    # the next from what the first kept there (`Addon._resume_chaos`).
    work = Path(tempfile.mkdtemp(prefix="chaos_"))
    try:
        filed = set()
        for name, lines in logs(since):
            seen += 1
            got = [run for run in runs_in(lines, fresh_addon(work))
                   if run.get("closed") not in filed]
            filed.update(run.get("closed") for run in got)
            print(paint("   %s: %d run(s)" % (name, len(got)), QUIET),
                  flush=True)
            for run in got:
                found[run["closed"]] = (run, name)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    kept = merge(rows, found.values(), parts, theirs, full)
    new = len({row_of(run, s, parts)["date"] for run, s in found.values()}
              - set(rows))
    filled = fill_missed(kept)

    spots = {c for row in kept.values() for c in row
             if c.startswith(SPOT_COLUMN)}
    header = OWNED + sorted(spots) + ["log"] + theirs
    lines = ["\t".join(header)]
    for date in sorted(kept):
        lines.append("\t".join(kept[date].get(c, "") for c in header))
    # LF, as git keeps it: a plain write_text writes CRLF on Windows.
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(paint("%d snapshot run(s), %d log(s) read, %d new run(s), %d "
                "row(s) -> %s" % (len(held), seen, new, len(kept),
                                  OUT.relative_to(ROOT)), GOOD))
    if filled:
        print("   filled `missed` for whole lost runs: %s" % ", ".join(filled))
    if any(row["season"] == "?" for row in kept.values()):
        print(paint("   ! a run with no season: no standings were read "
                    "before it cleared, and its currency is not in "
                    "CURRENCY", FLAG))
    if not kept:
        return
    own = {date: row for date, row in kept.items() if current(row)}
    by_part = collections.defaultdict(list)
    others = collections.defaultdict(list)
    tally = collections.Counter()
    unplayed = []
    for row in kept.values():
        if not current(row):
            others[(row["chaos"], row.get("door") or "",
                    row.get("special") or "", row["mode"])].append(row)
            continue
        for _key_, _spot, amount, _mark, _raw in base_payouts(row) or ():
            tally[amount] += 1
        # A run lost before its last fight paid what it paid, not what a
        # run pays (`chaos_estimate.is_full`).
        if not chaos_estimate.is_full(run_of_row(row)):
            unplayed.append(row["date"])
            continue
        paid = base_payouts(row, recovered=True)
        nodes = _nodes(row)
        by_part["%s %s" % (row["season"], row["part"])].append((
            int(row["total"] or 0) + missed_of(row),
            None if paid is None else sum(amount for _k, _s, amount, _m, _r
                                          in paid)
            + chaos_estimate.base_of(missed_of(row), nodes)))

    # What a run of the season's own Chaos pays played through, by part
    # and by season, at 0 nodes and as paid. The estimate is built from
    # its parts instead -- `shipped_figures`.
    by_season = collections.defaultdict(list)
    for part, got in by_part.items():
        by_season[part.split()[0] + " whole"].extend(got)
    groups = sorted(by_part.items()) + sorted(by_season.items())
    if by_part:
        groups.append(("all", [pair for got in by_part.values()
                               for pair in got]))
    heading("What a run of the season's own Chaos pays, played through "
            "(with `missed`)")
    table = []
    for label, got in groups:
        base = [b for _paid, b in got if b is not None]
        table.append([label, str(len(got))]
                     + ([_amounts([round(sum(base) / len(base))]),
                         _amounts([round(min(base))]),
                         _amounts([round(max(base))])] if base
                        else ["", "", ""])
                     + [str(round(sum(p for p, _b in got) / len(got)))])
    grid(table, head=["part", "runs", "mean", "min", "max",
                      "as paid, mean"])
    if unplayed:
        print(paint("   left out, lost before their last fight: %s"
                    % ", ".join(sorted(unplayed)), QUIET))
    print("   each payout at 0 nodes, and how often: " + "  ".join(
        paint(_number(value), AMOUNT) + paint(" x%d" % n, COUNT)
        for value, n in sorted(tally.items())))
    report(own)
    bosses_table(kept)
    rate_shifts(kept)
    shipped_figures(own)
    if others:
        others_table(others)


if __name__ == "__main__":
    main()
