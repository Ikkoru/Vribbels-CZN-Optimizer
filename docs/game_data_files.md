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

**When a new KIND of data is added — a new field or a new table — ask the maintainer whether it needs a verifier and what the rule should be. Do not infer bounds from the current values.** Rules derived that way have twice been contradicted by data already in the files.

## `partners.py` stat vocabulary is exact-match

The optimizer consumes ONLY the keys in that module docstring's vocabulary table: `ATK%`, `DEF%`, `HP%`, `CRate`, `CDmg`, `Extra DMG%` (with the space), `DoT%`, `Ego`. Wrong spellings are silently ignored.

- Conditional / stacking effects go in `stats_conditional`, scored at full encoded value and invisible to the Have-at-least gate and the Potential 7 rows.
- `# this` markers flag uncaptured stat effects.
- `# EST` marks interpolated values.
- Negative res_id keys are TODO placeholders.

## `sets.py` stat vocabulary is exact-match too

And deliberately spelled differently from everywhere else: a set's `stat` field says `Crit DMG` / `Crit Rate` where the program and `partners.py` say `CDmg` / `CRate`.

Only the names in that module's docstring table reach the formulas — the five in `SET_STAT_NAME_MAP` (`optimizer/core.py`) plus `DMG multi` and `DMG add`, which feed the damage card multiplier and apply to CONDITIONAL sets only. Anything else is silently ignored while the set still counts for set-locking, so a typo costs a bonus with no visible error.

Where each value lands: `game_formulas.md` §5.

## Finding a newly released unit's res_id

A capture is ownership-scoped, so a unit you do not have appears nowhere — hence the negative placeholder keys. Two exceptions:

**The gacha schedule.** Each pickup banner is named `gacha_pickup_<combatant|supporter>_<res_id>[_<rerun>]`, a server-side definition indifferent to what the account owns. Banners come in Combatant/Supporter pairs sharing a window, so a release names both halves the day it opens. A capture records the schedule under the snapshot's `gacha_banners` key and logs `Banner ... names res_id N, which is not in game_data` for anything the tables cannot place. See `capture_pipeline.md`.

**The duplicate-exchange shop**, which also gives a class: `shop_res_data.shop_gacha_dup`, sub-category `shop_gacha_dup_unique_2`, one product per grade-5 supporter, tagged `..._supporter_<class>`. It says `knight` where `partners.py` says `Vanguard`, and it reaches further back than the schedule.

Only the later products name their unit as `char_base@name@<res_id>`. Earlier ones are named by their selector item instead (`item@name@4500019`), and that item id appears nowhere else on the wire, so those units have no res_id in a capture at all. Item id does not order by res_id (`4500020` is Tina 20039; the higher `4500027` is Scarlet 20034), so the gap cannot be interpolated. Reading the shop in `sort` order and matching positions against the in-game list is what resolves them, and only for units already placed.
