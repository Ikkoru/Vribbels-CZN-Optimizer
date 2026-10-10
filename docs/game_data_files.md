# Game data files

Read before editing `game_data/{characters,partners,sets,constants}.py` or `game_data_validator.py`.

These tables are hand-maintained and most mistakes in them are silent: a misspelled stat name is ignored, an unlisted (grade, class) pair quietly gets stand-in base stats, a duplicated dict key throws away the entry above it. The program keeps running and the scores are simply wrong. That is what the validator exists for.

## Launch-time validation: two layers

`game_data_validator.py` lives at the top level, NOT inside `game_data/`, and reports problems in a message box.

**Text/AST layer** (`check_data_files()`) — syntax errors with `File | Ln | Col` and a caret, plus duplicate dict keys at any depth. Called from `czn_optimizer_gui.py` **above the `from game_data import *` line**: a syntax error is raised while that module imports, so this is the last point at which it can be a message box instead of a traceback. **Keep that call above the project imports if they are ever reordered.** Source runs only — a frozen build has no `.py` files, and the build
would fail first anyway.

**Value layer** (`find_data_problems()`) — ranges, vocabularies and shapes, run on a worker from `_start_data_validation()` and reported by `_report_data_problems()` after `_reveal_window()`. Advisory; the data still loads.

Every threshold is a named constant in that file's RULES block, ordered by data file then field, and every message names the file to edit.

Vocabularies are deliberately NOT duplicated in the validator: `CLASSES` (constants.py), `ATTRIBUTE_COLORS` and `POTENTIAL_STAT_VALUES` (characters.py), `PARTNER_STAT_NAMES` and `PARTNER_CLASS_STATS` (partners.py), `SET_STAT_NAME_MAP` and `SET_CARD_MULT_STATS` (sets.py) are each the single source of truth, carry an "ADD A NEWLY-RELEASED ... HERE" comment, and widen the checks automatically when extended.

**When a new KIND of data is added — a new field or a new table — ask the maintainer whether it needs a verifier and what the rule should be. Do not infer bounds from the current values.** Rules derived that way have been contradicted by data already in the files.

## `partners.py` stat vocabulary is exact-match

The optimizer consumes ONLY the keys in that module docstring's vocabulary table: `ATK%`, `DEF%`, `HP%`, `CRate`, `CDmg`, `Extra DMG%` (with the space), `DoT%`, `Ego`. Wrong spellings are silently ignored.

- Conditional / stacking effects go in `stats_conditional`, scored at full encoded value and invisible to the Have-at-least gate and the Potential 7 rows.
- `# this` markers flag uncaptured stat effects.
- `# EST` marks interpolated values.
- Negative res_id keys are TODO placeholders, for a unit whose res_id is not yet known (*Finding a newly released unit's res_id*).

## `sets.py` stat vocabulary is exact-match too

And deliberately spelled differently from everywhere else: a set's `stat` field says `Crit DMG` / `Crit Rate` where the program and `partners.py` say `CDmg` / `CRate`.

Only the names in that module's docstring table reach the formulas — the five in `SET_STAT_NAME_MAP` (`game_data/sets.py`) plus `DMG multi` and `DMG add`, which feed the damage card multiplier and apply to CONDITIONAL sets only. Anything else is silently ignored while the set still counts for set-locking, so a typo costs a bonus with no visible error.

Where each value lands: `game_formulas.md` §5.

## The item tables in `constants.py`

Six tables name every item the Materials tab draws, and `ITEM_TABLES` is the tuple of them. Two shapes:

- **Shaped** rows are `(group, tier, icon)` — the group is a class for a promotion family and an Element for growth stones, and `TIER_RARITY` prices the tier word into a rarity.
- **Named** rows are `(name, icon)`, for items belonging to no family. `NAME_RARITY` prices those.

`item_art(res_id)` is the one accessor that knows both shapes: it takes the icon as the first field ending `.png`, reads a rarity stated after it, and otherwise derives one. **Read art through it, never off a row** — the tables disagree about what their leading fields mean.

A rarity that no table prices costs a whole family its plates at once, and the only symptom is icons drawn with no background. `checks/check_item_art.py` is what catches that, along with a filename naming a file that is not there.

### The three id tables

`docs/items_id_dump.py` rewrites three tables from the newest snapshot, and which one an id lands in says what is left to do with it:

| file | means |
| ---- | ----- |
| `items_id_known_in_materials.tsv` | a table names it and the program USES it |
| `items_id_known_not_in_materials.tsv` | identified, and the program does nothing with it — **the worklist** |
| `items_id_unknown.tsv` | not identified, not even by the game client; where it came from and what it reads, for diffing against the next capture |

The last two share their hand-added columns (`Name`, `Type`, `Name Candidate`, …), so a row crosses between them by gaining or losing its `Name` without anything being retyped. **The script owns the leftmost columns and nothing else** — everything typed to the right of them is read back and rewritten untouched, and it refuses to write at all if the header has moved under it. A blank `Name` takes the game client's (`docs/client_data.md`), and a typed one that differs from it is printed.

An id counts as "known" to the program only when an ITEM table names it. **`RECORDED_NAMES` is not one of those tables** — it is a plain id→name map, kept out of `ITEM_TABLES` because those items have no art and no established rarity. `RECORDED_ONLY` is its key set, and that is what keeps its ids on the worklist rather than promoting them.

**The game client names every item**, and `item_names()` puts its names under the tables' and `RECORDED_NAMES`, so those only override. That map is what the running program names items with: the capture generator writes it into the addon's `ITEM_NAMES`, so a Capture Log line reads `Traces of Memory +40` rather than `3210001 +40`. An id nothing names stays a number there, and the Capture Log paints it dark yellow — a note that the line has just put a capture's worth of context beside a row of `items_id_unknown.tsv`. `python docs/client_tables.py --audit` lists every override that disagrees with the client, and `checks/check_capture_rewards.py` holds the worklist's names to the program's.

**A res_id's shape is `FFFF0GT`** — family, group, tier. The group digit is the CLASS in a promotion family (0 Striker, 1 Vanguard, 2 Hunter, 3 Ranger, 4 Psionic, 5 Controller) and the ELEMENT in a growth stone. The asset filenames disagree with the game's words in two places: `defender` draws Vanguard and `psionics` draws Psionic.

## `POTENTIAL_NODES` in `characters.py`

The whole potential tree in one tuple — display order, the game's numbering, the wire's, the maxima, and what each node does. `POTENTIAL_MAX_TOTAL` sums the maxima, which is what the Combatants tab's `Nodes` column counts against.

**The two numberings disagree** and `game_formulas.md` §1 is the table of both. Per-character wording lives in `POTENTIAL_NODE_OVERRIDES`; a stat node states none, its line being built from the stat instead, and node 7's line names what `potential_7.py` says it raises.

## `potential_7.py`

Node 7 per combatant: the bonus, the check and its growth, in the shape the module docstring gives; the rules they follow are `game_formulas.md` §1, *Potential 7*. A new combatant needs an entry: the validator reports one without, and its node 7 scores as nothing until it has one. **Check stats are the Have-at-least names** (`CHECK_STATS`) and a misspelt one never passes, which the validator reports too. A new entry's numbers are held to the server by the next plain battle the combatant fights with node 7 taken (`check_base_stats_on_wire`).

**A balance patch that rewrites a node 7**: move the old effects into `POTENTIAL_7_BEFORE`, with the first second the new one was live, and write the new ones in `POTENTIAL_7`. The readings keep sheets from both sides of the patch, and each is held to the node 7 it was stated under.

## Base stats in `characters.py`, against the server

**The in-game stat screen shows the base with Affection mixed in**, so a base typed in from it is wrong by the Affection bonus unless that is taken off first. The server sends the true figure instead: every battle's entry carries each combatant's `BASE_S_ATK/DEF/HP` at their level, and each partner's own flat stats. The capture files these (`capture_pipeline.md`, *The base stat readings are kept in a file of their own*), and `checks/check_base_stats_on_wire.py` fails on:

- a combatant the readings settle differently from `characters.py`, or one it lacks;
- a level-60 partner unlike `PARTNER_CLASS_STATS`;
- a build whose sheet the program's stat formula does not reproduce.

**How a reading is settled** (`base_stats_store.resolve`):

1. A battle without Zero System effects -- a Simulation stage, a Battle Mission, the Great Rift, the Full-Scale Offensive, the Basin, the Tower -- states the base as it is.
2. A Chaos battle states `potential_base_status`, the Potential 7 check's stat computed without the Chaos's bonus, and the inner formula has exactly one base that gives it. It covers only the stat or stats that check reads.
3. A Chaos adds the same amount to everyone in it, so a combatant settled by 1 or 2 gives the bonus, and it comes off the rest. A battle whose combatants disagree on it gives nothing more.

A plain reading wins over a worked-out one. A Sortie settles nothing: the week's buffs move its buffed combatants' bases, partner flats and Potential 7 values, and which combatants and what buff never ride the wire. Combatant trials and event stories field level-20 copies and never count either.

**The program uses what the server says** where its tables are silent or wrong: `game_data.learned`, filled on every snapshot load from the account's readings and the shipped shared facts, newest first. The order `get_character_stats_at_level` answers in:

1. The reading at the level asked.
2. Else the nearest reading, walked there by the level gains: the combatant's own, read off two readings; else their `level_6N_bonus` key; else the gain every reading of their class and grade agrees on; else `LEVEL_BONUS_BY_CLASS`.
3. Else the tables alone, as `table_stats_at_level` gives them.

`get_partner_stats` takes the partner's reading at that level, else one of a partner of the same grade and class, else the linear table. The tables are still worth correcting: they are what a player without readings gets, and what the check holds the server against.

- **To verify a combatant**, take them into any battle but a Sortie during a capture. One outside the Chaos modes settles all three stats directly; a Chaos settles them only beside someone already settled.
- **To read what the logs hold**, `python docs/base_stats_backfill.py` reports: who is wrong or missing, a level gain the tables lack, a base that changed between plain readings, the Chaos battles set aside, the partners and the formula against the server, and who nothing has settled yet. `--write` files the debug logs' battles, the archived ones included; `--battles` lists every battle with its mode.
- **A level-61 or 62 reading gives a pair's gain** where `LEVEL_BONUS_BY_CLASS` lacks it: the server's base at that level minus the level-60 base. The check names it; the program uses it meanwhile.
- **`UNEXPLAINED` in the check** holds a reading that differs for a reason nobody has pinned down. It is noted rather than failed while the reading stays exactly that.

## Finding a newly released unit's res_id

**The game client names every unit by res_id** (`char_base@name@<res_id>`), owned or not, and `python docs/client_tables.py --audit` lists each one the tables lack (`docs/client_data.md`). That is the first place to look; what follows is what the wire alone offers.

A capture is ownership-scoped, so a unit you do not have appears nowhere on the wire — hence the negative placeholder keys. Two exceptions:

**The gacha schedule.** Each pickup banner is named `gacha_pickup_<combatant|supporter>_<res_id>[_<rerun>]`, a server-side definition indifferent to what the account owns. Banners come in Combatant/Supporter pairs sharing a window, so a release names both halves the day it opens. A capture records the schedule under `event_schedules.GACHA` and logs `Banner ... names res_id N, which is not in game_data` for anything the tables cannot place. See `capture_pipeline.md`, *The gacha schedule names unreleased units*.

**The duplicate-exchange shop**, which also gives a class: `shop_res_data.shop_gacha_dup`, sub-category `shop_gacha_dup_unique_2`, one product per grade-5 supporter, tagged `..._supporter_<class>`. It says `knight` where `partners.py` says `Vanguard`, and it reaches further back than the schedule.

Only the later products name their unit as `char_base@name@<res_id>`. Earlier ones are named by their selector item instead (`item@name@4500019`), and that item id appears nowhere else on the wire, so those units have no res_id in a capture at all. Item id does not order by res_id (`4500020` is Tina 20039; the higher `4500027` is Scarlet 20034), so the gap cannot be interpolated. Reading the shop in `sort` order and matching positions against the in-game list is what resolves them, and only for units already placed.
