# Plan: game-data validation on launch

Report, at launch, anything in the game-data files that won't parse or
sits outside expected parameters — so a maintainer's data-entry mistake
surfaces immediately instead of becoming a silently wrong build score.

Scope: `characters.py`, `partners.py`, `sets.py`. `constants.py` is out
of scope (no new data arrives in it).

---

## 1. Constraints

- **A syntax error in a data file kills the program before any of our
  code runs.** `game_data/__init__.py` imports all three modules, and
  every entry point imports `game_data`. To report a syntax error in a
  message box we must check the files as TEXT (`ast.parse`) *before* the
  package is imported, from a module that does not itself import
  `game_data`.
- **Frozen builds have no source files.** PyInstaller ships compiled
  modules, so the text-level checks can only run from source. This costs
  nothing: PyInstaller compiles the data files at build time, so a
  syntax error fails the BUILD. The maintainer edits data and runs from
  source; the syntax layer is for exactly that loop.
- **Nothing may block the Tk main thread** (see CLAUDE.md). Value checks
  run on a worker; the report is shown after the window is revealed.
- Rule thresholds must be trivial to find and edit: the game will
  eventually release a character outside today's ranges.

## 2. Design

One module, `Vribbels/game_data_validator.py`, top-level (NOT inside the
`game_data` package, per the import-order constraint above), stdlib-only
at import time.

Layout, top to bottom — all tunables first, in file/field order, so
widening a range is a one-line edit:

```
"""Docstring: what this checks, and how to widen a rule."""

# ---- characters.py rules ----
CHARACTERS_GRADES            = (4, 5)
CHARACTERS_BASE_ATK          = (300, 541)
CHARACTERS_BASE_DEF          = (133, 208)
CHARACTERS_BASE_HP           = (293, 423)
CHARACTERS_BASE_CRIT_RATE    = 3.0
CHARACTERS_BASE_CRIT_DMG     = 125.0
CHARACTERS_LEVEL_BONUS_ATK   = (4, 9)
CHARACTERS_LEVEL_BONUS_DEF   = (2, 7)
CHARACTERS_LEVEL_BONUS_HP    = (4, 10)
# ---- partners.py rules ----
PARTNERS_VALUES_PER_STAT     = 5          # one per limit break, E0..E4
PARTNERS_TIER_RATIO_RANGE    = (1.5, 2.0) # max/min, inclusive
PARTNERS_TIER_RATIO_EXTRA    = (4.0, 5.0) # plus these exact ratios
PARTNERS_EGO_COST            = (2, 4)
# ---- sets.py rules ----
SETS_PIECES                  = (2, 4)
SETS_TYPES                   = ("conditional", "unconditional")
# ---- then: check functions, in the same order ----
```

Vocabularies are NOT duplicated here — they're read from the data
modules themselves (`POTENTIAL_STAT_VALUES` keys, `ATTRIBUTE_COLORS`
keys, `PARTNER_CLASS_STATS` keys, `SET_STAT_NAME_MAP`). A new attribute
or class added to the game data therefore widens the validator
automatically, with no second place to edit. Each of those definitions
gets a one-line comment saying the validator reads it, so a maintainer
adding a newly-released attribute/class/stat finds the right place
without consulting the validator at all. The partner section of the
validator carries the matching note in the other direction: a new grade
tier means adding `(grade, class)` rows to `PARTNER_CLASS_STATS`, not
editing a range here.

**Two layers:**

1. **Syntax + duplicate-key layer** (text/AST, source builds only). Runs
   first thing in `main()`, before `OptimizerGUI` is constructed. Any
   failure → native `MessageBoxW` → exit. Message:
   `File: characters.py | Ln: 412 | Col: 9` plus the offending source
   line and a caret, straight from `SyntaxError.lineno/offset`.
2. **Value layer** (imported dicts + an AST line map). Runs on a worker
   thread started early in `OptimizerGUI.__init__`; the report is shown
   after `_reveal_window()`. Problems are warnings, not fatal: the data
   still loads, and a maintainer mid-edit shouldn't be locked out. Each
   problem line reads
   `characters.py | Ln: 412 | Hilde (30113) | base_atk 615 outside 300-541`.
   Line numbers come from a best-effort AST map of dict-key → lineno;
   without source, the entry key/name alone identifies it.

Every message names `game_data_validator.py` as the file to edit if the
game has legitimately moved outside a range.

## 3. Silent-failure inventory

From reading the three files. "Silent" = no traceback, wrong or missing
numbers in the UI. These are what the checker is actually for.

**All three files**

| Failure                                                           | Why it's silent                                  | Detect via    |
| ----------------------------------------------------------------- | ------------------------------------------------ | ------------- |
| Duplicate dict key (copy-paste an entry, forget to change the id) | Python keeps the last silently                   | AST only      |
| Key typed as `"1055"` instead of `1055`                           | res_id lookups are int-keyed; never matches      | imported dict |
| Entry value not a dict                                            | attribute access fails later, far from the cause | imported dict |

**characters.py**

| Failure                                            | Why it's silent                                                                    | Detect                                             |
| -------------------------------------------------- | ---------------------------------------------------------------------------------- | -------------------------------------------------- |
| `node_50`/`node_60` misspelled                     | `get_potential_stat_bonus` returns `(None, 0.0)`; the node bonus silently vanishes | must be a `POTENTIAL_STAT_VALUES` key              |
| Duplicate `name` between two characters            | `CHARACTERS_BY_NAME` is a comprehension — one entry is lost from every name lookup | imported dict                                      |
| `attribute` / `class` misspelled                   | element damage silently mis-attributed; class is cosmetic but wrong                | must be in `ATTRIBUTE_COLORS` / observed class set |
| `level_61_bonus` key typo (`"attack"` not `"atk"`) | `.get("atk", 0)` → bonus silently 0                                                | key whitelist                                      |
| Missing `base_*`                                   | `.get(..., 0)` → a 0-stat character that still scores                              | required-key check                                 |
| Grade/base stats out of range                      | plausible-looking but wrong scores                                                 | ranges above                                       |

**partners.py**

| Failure                                                           | Why it's silent                                                                                                                                                                          | Detect                                          |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| **`(grade, class)` absent from `PARTNER_CLASS_STATS`**            | `get_partner_base_stats` falls back to `{"atk": 85, "def": 5, "hp": 90}` — plausible numbers, wrong for every build using that partner. The single worst silent failure in the data set. | tuple must be a `PARTNER_CLASS_STATS` key       |
| `stats` / `stats_conditional` key misspelled                      | documented as silently ignored; the whole bonus disappears                                                                                                                               | 8-name vocabulary                               |
| A `{placeholder}` in `passive_desc` with no matching `values` key | the literal `{ATK%}` is shown to the user                                                                                                                                                | compare desc placeholders against `values` keys |
| Tier tuple not 5 long                                             | `get_value_for_ego_level` returns 0 for <5 — the entire passive silently reads zero                                                                                                      | length check                                    |
| Tier tuple non-numeric                                            | arithmetic fails later or coerces oddly                                                                                                                                                  | type check                                      |
| `ego_cost` out of range                                           | cosmetic but visible                                                                                                                                                                     | range                                           |

**sets.py**

| Failure                                          | Why it's silent                                                                         | Detect                                      |
| ------------------------------------------------ | --------------------------------------------------------------------------------------- | ------------------------------------------- |
| `stat` misspelled (`CDmg` instead of `Crit DMG`) | ignored while the set still counts for set-locking — a bonus quietly worth nothing      | `SET_STAT_NAME_MAP` + `DMG multi`/`DMG add` |
| `DMG multi`/`DMG add` on an `unconditional` set  | the score's card-multiplier walk skips unconditional sets; contributes nothing anywhere | type/stat cross-check                       |
| `type` misspelled                                | falls through every branch; bonus never applies                                         | `SETS_TYPES`                                |
| `elements` entry misspelled                      | Set Configuration row silently mis-coloured                                             | `ATTRIBUTE_COLORS` keys                     |
| `pieces` not 2 or 4                              | set-completion logic never triggers                                                     | `SETS_PIECES`                               |

## 4. Two stated rules revised against the current data

Both accepted. The reasoning is kept because it matters if either is
revisited.

**(a) `partners.py` grade is not 3-5 — `4.5` exists.** Anteia, Eishlen,
Nyx, Priscilla, Serithea and Solia are `grade: 4.5` (a seasonal-pass
tier — nominally 5-star in game, statted slightly below a real 5★), and
`PARTNER_CLASS_STATS` carries a full set of `(4.5, class)` rows for it.
Partner grade therefore gets NO range check. Instead `(grade, class)`
must be a `PARTNER_CLASS_STATS` key. That catches strictly more — a
valid grade paired with a class that has no row still falls back to
wrong stats — and needs no editing when a new tier ships, because adding
those rows is already mandatory for the feature to work.

**(b) A tier tuple's max/min ratio must be 1.5-2 inclusive, or exactly 4,
or exactly 5.** "Exactly double" alone would have flagged about half the
file: `(16, 18, 20, 22, 24)` (every 5★ partner's main % stat, ratio
1.5), `(12, 14, 16, 18, 20)` (every 4.5★, 1.667), `(8, 9, 10, 11, 12)`
Arwen, `(3, 3.5, 4, 4.5, 5)` Serithea, `(40, 45, 50, 55, 60)` Clara,
plus `(5, 10, 15, 20, 25)` Marianne at 5 and `(50, 88, 125, 163, 200)`
Janet at 4.

Verified against every tuple in `values`, `stats` and
`stats_conditional`: the widened rule passes all of them except Tina's
`OrderExtra%` and Zeta's `InstDMG%`, both `(15, 19, 23, 27, 31)` at
2.067 — inherited data-entry errors, which is precisely what the check
is for. The correct sibling tuples appearing elsewhere in the file are
`(15, 19, 23, 26, 30)` and `(15, 19, 23, 27, 30)`, so the bad digit is
the trailing `31`.

Also checked per tuple: exactly `PARTNERS_VALUES_PER_STAT` entries, all
numeric, non-decreasing. A zero minimum skips the ratio test rather than
dividing by zero.

## 5. Open questions

1. There is no canonical list of the six classes anywhere in the code.
   `attribute` validates against `ATTRIBUTE_COLORS`, node stats against
   `POTENTIAL_STAT_VALUES`, set stats against `SET_STAT_NAME_MAP` — but
   `class` appears only inline in individual entries. Options: (i) add
   `CLASSES = ("Controller", "Hunter", "Psionic", "Ranger", "Striker",
   "Vanguard")` to `constants.py` as the single source both files
   validate against; (ii) derive it from `PARTNER_CLASS_STATS` keys — no
   new data, but validating characters against a partner table is odd
   and breaks if the two ever diverge; (iii) hardcode the list in the
   validator, against the no-duplicate-vocabularies principle above.
   Recommendation: (i).
2. Same gap for the eight partner `stats` names — they exist only in the
   `partners.py` docstring table, not as code. Recommendation: add
   `PARTNER_STAT_NAMES` to `partners.py` beside that table, with the
   "add newly-released stats here" comment, and validate `stats` /
   `stats_conditional` keys against it.
3. The validator's set-stat vocabulary would import `SET_STAT_NAME_MAP`
   from `optimizer/core.py`, making the validator depend on the
   optimizer package. Harmless for the value layer (it runs after the
   app is imported) and it keeps a single source of truth, but it does
   mean the validator is no longer stdlib-only past its syntax layer.
   Alternative: move `SET_STAT_NAME_MAP` into `game_data/sets.py`, where
   the vocabulary it describes actually lives, and have `core.py` import
   it from there. Recommendation: the move — but it touches the
   optimizer, so it needs a ruling.

## 6. Phases

- **C** — [IMPLEMENTED 2026-07-30] vocabulary single-sources and their
  "add new entries here" comments: `CLASSES` added to `constants.py`,
  `PARTNER_STAT_NAMES` added to `partners.py` (replacing the docstring
  table, with the where-it-lands notes moved onto the entries),
  `SET_STAT_NAME_MAP` + `SET_CARD_MULT_STATS` moved from
  `optimizer/core.py` into `game_data/sets.py` (core re-exports),
  pointer comments on `ATTRIBUTE_COLORS`, `POTENTIAL_STAT_VALUES` and
  `PARTNER_CLASS_STATS`, all three exported via `game_data/__init__.py`.
- **A** — [IMPLEMENTED 2026-07-30] `game_data_validator.py` text/AST layer:
  syntax errors as `File | Ln: | Col:` with the source line and a caret,
  plus duplicate dict keys at any nesting depth (a repeated res_id AND a
  repeated field inside one entry). Called from `czn_optimizer_gui.py`
  above the `from game_data import *` line — NOT from `main()`, which
  runs after the imports that would already have raised. Skipped in
  frozen builds, where the sources don't exist and a data syntax error
  would have failed the build instead.
- **B** — [IMPLEMENTED 2026-07-30] value layer: `find_data_problems()` on
  a worker started in `setup_ui`, reported by `_report_data_problems()`
  after `_reveal_window()`. Line numbers from a best-effort AST key map,
  including negative keys (the placeholder partner ids parse as unary
  minus, not constants). Advisory only.
- **D** — [IMPLEMENTED 2026-07-30] CLAUDE.md "Game-data validation"
  section, including the rule that a new KIND of data in these files
  needs a maintainer ruling on whether and how to verify it, and the
  warning against inferring bounds from current values.
- **E** — [IMPLEMENTED 2026-07-30] `characters.py` docstring fixed: the
  `"class"` example said `"DPS"` with roles "Tank / DPS / Support /
  Healer", which don't exist in the game. Now points at
  `constants.CLASSES`. Inherited from upstream.

## Maintainer decisions

- **2026-07-30** — A new grade tier is added to `PARTNER_CLASS_STATS`;
  `CLASSES` lives in `constants.py`; `PARTNER_STAT_NAMES` lives in
  `partners.py`; `SET_STAT_NAME_MAP` moves from `optimizer/core.py` into
  `game_data/sets.py`.
- **2026-07-30** — §4(a) accepted: no partner grade range; validate
  `(grade, class)` against `PARTNER_CLASS_STATS`, and note in the
  validator's partner section that a new grade tier is added there.
- **2026-07-30** — §4(b) accepted with the ratio widened to 1.5-2, 4, or
  5. Tina's `OrderExtra%` and Zeta's `InstDMG%` are confirmed inherited
  errors and should be reported.
- **2026-07-30** — Report BOTH directions of the `values` /
  `passive_desc` mismatch: a `{placeholder}` with no value, and a value
  with no placeholder. Eunie's unused `ATK%` is a confirmed mistake.
- **2026-07-30** — The negative-res_id partner placeholders are checked
  normally, with no exemption and no separate informational notice.
- **2026-07-30** — The value layer only shows the message box; it does
  not write to `perf_log.txt`.
- **2026-07-30** — Vocabulary definition sites get one-line comments
  pointing maintainers at them, so the validator never has to be opened
  to add a newly-released attribute, class or stat.
