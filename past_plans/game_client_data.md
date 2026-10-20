# The game client as the source of the program's game data (T24)

**[IMPLEMENTED] 2026-10-20.** Every family below reads the installed client first, the hand tables kept as the fallback. The maintainer chose every family, "with fallbacks" (2026-10-18), said go (2026-10-19), and settled each difference the readers found (*Decisions*). How the program reads the client now: `docs/client_data.md`, *What the program reads at launch*.

## The rule

**Client first, the hand tables the fallback.** For each fact a family covers, the first source that holds it wins:

1. this client's read, cached per build (`settings/game_client.json`), or where this build will not read, the last cache of an earlier one while it is newer than the shipped extract (`game_client.fallback`);
2. the shipped extract, `game_data/from_client.py`, written by `docs/client_tables.py --ship` at each release;
3. the hand table.

The server's readings still win over all three where they exist (`game_data.learned`: combatant and partner stats).

**A family switched only once its derivation reproduced the hand table** for every entry both hold; the differences went to the maintainer first, since a hand figure can be the newer. `docs/client_tables.py --audit` lists them, and `checks/check_client_overlay.py` holds the derivation to the hand table on the installed client.

## The mechanism

- **Readers in `game_client`**, beside `event_names` and the rest: one per family, each returning plain dicts keyed by res_id. `read_facts` caches them; `CACHE_FORMAT` goes up so every launch rereads once.
- **The overlay**, `game_data/client_overlay.py`: `apply(facts)` restores the hand tables from a pristine copy taken at import, overlays the shipped extract, then the client's facts, field by field and only where a fact is known, then rebuilds what is derived from the tables (`CHARACTERS_BY_NAME`). `game_client.use` calls it, so the launch read, the cache, the fallback and `reread_game_client` all land the same way. In place, so every module that imported the dicts sees it (T24-D1).
- **What stays the program's own** in an entry the client fills: the maintainer's encodings (a partner's `stats`, `stats_conditional`, `passive_desc` templates, Potential wording, `# this`/`# EST` markers) and anything the client does not hold.
- **A unit only the client knows** (released after the program) gets an entry built from the client alone, shaped to pass `game_data_validator`, so it shows by name with its stats instead of as Unknown.

## The families

### 1. Combatants and partners

- **Combatants**, `char_base@char_base`/`@char_combatant`/`@combatant_level`/`@combatant_ascend`: name, grade, class, attribute, level-60 ATK/DEF/HP, crit rate and damage, the steps to 61 and 62. Node 50's and 60's stat from `potential_node@potential_node_effect` (`5_0`, `6_0`; `NODE_STAT_ADD`, the stat id mapped as `set_effects` maps it). Playable ones only (`char_use_playable`).
- **Partners**, `partner_base@char_partner`/`@partner_level`, `card(partner)@card`, `partner_passive`: name, grade, class, passive name, Ego name and cost; `PARTNER_CLASS_STATS` from the level table.
- Every field agreed with the hand tables but Tiphera's node 50/60, swapped against the client's tree: the client was right (T24-D3).
- A partner's plain stat lines (`nb_eff` `EFF_STAT_UP_PARTNER` → `stat_up_eff`) reproduce all its hand `stats`; conditional lines (`link_cs_id`) stay hand. Grade from the level curve's name: `r` 3, `sr` 4, `ssr` 4.5, `sssr` 5.
- Blanche and Capri, in the client and unreleased at build 88, show from the client's facts: grade 4.5, their plain DEF%/ATK% lines, passives drawn from the client's lines. They stay out of `partners.py` (T24-D6).

### 2. Banners, pools, seasons

- `game_client.chaos_names`, `zero_specials`, `general_units`; `chaos_estimate.chaos_names`/`zero_special_name` and `gacha_history.pool_of` read them; `checks/check_client_fallbacks.py`.
- The program's own spellings (`CHAOS_NAMES`, `ZERO_SPECIALS`, `POOL_LABELS`) go over the client's where both name one. The Chaos names and Zero System specials took the game's spellings; the pool labels stay the program's (T24-D5).
- Not in the client: banner and season dates (`gacha_list` and `disaster_season` hold no schedule); `RIFT_CODENAMES`, the maintainer's own names; `SEASON_ESTIMATE`'s weekly amounts, which need the season's length.

### 3. EXP, Affinity, Memory Fragment stats

- **Exp and Affinity.** `game_client.exp_tables` (`char_growth@char_exp`, each kind's grade columns accumulated; -1 marks the kind's top) and `affinity` (`friendship_level`; the bonus group every playable combatant names, accumulated). `client_overlay` swaps them into `constants`' four tables whole, keeping the objects; `affinity_level` works its cap out of the table; the Materials tab's EXP targets read the live table (`_LiveExpTargets`).
  - Every level agreed but combatant level 51: hand 346000 (read off Amir), client 345900. The client's was taken (T24-D2).
  - The partner table's estimated rows (5, 15, 20, 25) were wrong by up to 11800; the hand table took the client's figures (55's estimate was right).
  - The client adds combatant level 62 (840500). Every max combatant on file at the time sat at exactly 778200 (level 61).
  - Candidate, not started: partner stats below 60 from `partner_base@partner_level`'s exact curve, where `partners.table_partner_stats` scales level 60 linearly.
- **Memory Fragment stats.** `game_client.fragment_stats` (`piece_option`: each slot's mains with level-0 value and step, the substats' rolls and draw weights, Legendary columns; `piece_reinforce` row ids: each rarity's top level). `client_overlay` swaps `SLOT_MAIN_STATS` (client order; a stat `STATS` lacks left out; a slot missing → hand), `SUBSTAT_DRAW` (only a full set) and `STATS`' roll bounds. The inventory filter reads `SLOT_MAIN_STATS` live (its own `FILTER_SLOT_MAIN_STATS` copy removed; its "DEF% on IV/V" reason no longer held).
  - Everything agreed: slots, ceilings (HP 20 + 5 × 3.33 = 36.65, drawn 37), roll bounds, top levels (common 2, uncommon 3, rare 4, legend 5, unique 5).
  - `piece_option.ratio` weighs a new substat's draw (flat 100, ATK%/DEF%/HP% 90, Extra/DoT 80, CRate/CDmg/Ego 70), where the Average Potential and its band drew one alike: they draw by weight now (T24-D4).
  - The roll bounds are laid over, and the shipped presets re-worked where a top roll moves (T24-D7). `MAIN_STAT_VALUES` (nothing reads it) and `MAX_LEVEL_PER_RARITY` (tied to the substat-count rules) are held to the client, not laid over: the check fails when a patch moves one.
  - `equip_stat_define` (6 rows: `s_atk`/`s_def`/`s_hp` by an id 1–5 and 9999) is not Memory Fragment data; unidentified.

### 4. Items, shops, Zero System, classes

- `game_client.item_rarities` (every `item_*@item` row's `rarity`, as the plates' words) goes over the item tables' own in `constants.item_art`; `table_art` is the tables alone, for the check. `known_item_rarities` is worked out once per `use`. `game_client.class_names` (`base_class_define` and its text) goes over `CLASS_NAMES` in `combatants`/`partners`.
- Every item table's rarity and icon agreed; the classes are `CLASSES`, in the Materials tab's `CLASS_ORDER`.
- Shops: the stock is the wire's, and `SHOPS` is a whitelist with the maintainer's composed names ("Shop - <category> - <screen>"), so nothing is laid over. Two named none of the game's words: the Seasonal Shop became the Galactic Disaster Shop, and Sortie - Chaos Analysis Lab (game: Sortie Shop) stays (T24-D5).
- The Zero System's specials went with family 2.

## Per family, the steps

1. Reader in `game_client`, into `read_facts` and `--ship`.
2. Compare against the hand table on the installed client: every difference listed, none switched silently.
3. Overlay, with the consumer changes it needs.
4. A check: the overlay's order on synthetic facts, and the derivation against the hand table on the installed client.
5. Docs (`docs/client_data.md`, `docs/game_data_files.md`, the module docstrings), CHANGELOG where a player would notice, `run_all`, commit.

## Decisions

- **T24-D1.** The overlay writes into the existing dicts rather than replacing every reader: the tables are read in many places, and a reader's code stays as it is.
- **T24-D2 (2026-10-19).** Combatant level 51 takes the client's 345900 over the hand 346000 read off Amir.
- **T24-D3 (2026-10-19).** Tiphera's node 50 is DEF% and node 60 Crit Rate, as the client's tree has them: "Client is correct."
- **T24-D4 (2026-10-19).** A new substat is drawn by `piece_option.ratio`'s weights (`SUBSTAT_DRAW`), doc first (`docs/game_formulas.md`).
- **T24-D5 (2026-10-19).** The game's spellings for the three Chaos names and the nine Zero System specials; the Seasonal Shop becomes the Galactic Disaster Shop. The Rescue pool labels and the other shop names stay the program's, listed in `docs/client_tables.py`'s `INTENDED` so the audit leaves them out (2026-10-20).
- **T24-D6 (2026-10-20).** Unreleased partners are not added to `partners.py`: their figures could still change, and the client's facts show them meanwhile.
- **T24-D7 (2026-10-19).** The roll bounds are read from the client, and the shipped presets re-worked automatically where a top roll moves (`preset_derivation.rework`), with a run from source telling the maintainer. The defaults a player never changed then follow each release: `docs/settings_architecture.md`, *Three-stage sync*.
