# Decks

`Vribbels/decks/` is the Deck Builder's model, with no UI in it. `catalogue.py` reads everything a deck is made of off the game client, `model.py` holds a deck and a team, `wire.py` turns the captured Save Data into decks, and `rules.py` weighs a deck and lists the deck-building rules it breaks. None of it needs Tk.

## The client's tables

Read with `game_client.Client` (`docs/client_data.md`), each table named as `--table` takes it. **Nothing Sortie-only is read**: no `(assault)` table, and no `assault_r_spark_*` row of the Epiphany table. Sortie gives no Save Data, so none of its cards, Equipment or Epiphanies can be in a deck.

| What | Tables | The catalogue's key |
| --- | --- | --- |
| Cards | every `card(<group>)@card`, and season 5's `memory_grade_define@card` | `cards`, by id: its group, name, text, kind (`sort`), category, rarity, cost, keywords (`talent`), classes, `r_spark_replace_cost`, Epiphany tags (`r_spark_tag_default`), effects, child cards |
| A card's versions | every `card(<group>)@card_r_spark` | `versions`, the five Signature Epiphanies (`rsp1`–`rsp5_<card>`); `upgrades`, a Potential node's (`pot_`) and Ego Manifestation's (`lbk_`) |
| Effects and statuses | every `@skill_eff` and `@cs` | `effects`, `statuses`: only those a card, an Epiphany, a Persona effect, a piece of Equipment, a Buff or a Mutation reaches, through `link_cs_id`, `link_skill_eff_id` and `show_link_cs_id` |
| Neutral and Divine Epiphanies | `r_spark@r_spark` | `epiphanies`: a Divine one names its god (`god_type`), a Neutral one none, and each holds the conditions below |
| Persona effects | `eidolon_card_define@eidolon_card_slot_info`, `@eidolon_card_reward`, `@eidolon_card_illust_comb` | `persona`: a Persona card's slots, each Lux and Umbra effect, and the names that follow two effects |
| Equipment and its Buffs | `relic@relic`, `relic(disaster)@relic`; `relic_reinforce@relic_reinforce` | `equipment`, each star level's effect; `buffs`, of kind `ARENA`, `LUX` or `UMBRA` |
| Mutations | `savedata_edit_corruption@savedata_edit_corruption` | `mutations` |
| Deck point rules | `savedata_point_define@savedata_point_define` | `points`, in the client's unit, tens of the points the game shows |
| A turn's draw and AP, and the hand's cap | `constant_metagame@constant_meta` | `constants`: `draw`, `energy`, `hand_max` |
| Combatants | `char_base@char_combatant`, `char_base@char_base` | `combatants`: class, whether released (`char_use_playable`), the four starting and four Signature cards, the Ego skill |
| What the in-game deck builder offers | every `archive_card(<kind>)@archive_card` | `released`: the cards it lists (`visible_on_build_preset`), each with its sub-categories |

**A Combatant's cards are `c_<res_id>_<kind>`**: `srt1`–`srt3` the Basic cards, `srt4` the preset Signature card, `uni1`–`uni4` the other Signature cards, `<card>_rsp1`–`_rsp5` a card's Signature Epiphany versions, `srtN_pot` a Basic card a Potential node upgrades, `eps` the Ego skill, `cre<n>` the cards it creates in battle. A deck starts from the eight `srt` and `uni` cards. A card's kind (`sort`) is `SORT_START` or `SORT_UNIQUE` for those, `SORT_NEUTRAL`, `SORT_ETC` (an Event Neutral card), `SORT_MONSTER_UNIQUE`, `SORT_TABOO` (Forbidden), `SORT_EIDOLON` (Persona), `SORT_DESIRE` or `SORT_MEMORY`; its category `CARD_ATK`, `CARD_SKILL` or `CARD_POWER`, the game's Upgrade.

**The read checks itself** (`Catalogue.problems`): every released Combatant has its eight cards and a known class, every effect a card names is read, every Signature Epiphany turns its card into one the tables hold, the battle constants are whole numbers, both Neutral and Divine Epiphanies exist, the in-game deck builder offers something, and no deck point rule is missing or unknown to the program. A patch that renames or repurposes a column breaks one of those shapes rather than misreading quietly.

**The cache**, `deck_catalogue.json.gz` beside the settings, holds one build's read as gzipped JSON, replaced whole through a temp file. `catalogue.for_install` serves it while it holds the installed build, and reads the client again once a patch moves the build on.

## The wire

**Save Data**, the decks kept after a Chaos run, arrive whole in every snapshot's `inventory.savedata`, one entry per deck. `wire.captured_decks` reads them across the loose snapshots, each Save Data as its newest capture has it; with `archived=True` it reads the capture archive too (`Vribbels/capture/archive.py`), which holds the Save Data deleted since.

- **`user_id` is the account's own id**, on every Save Data. It is never read.
- `char_res_id` the Combatant, `name` the player's, `chaos_res_id`, `createAt`, `corruption_res_id` the Mutation.
- `define_point` the weight the game recorded when the deck was made, and `max_define_point` the run's cap, both in tens.
- `card_datas`, the cards, each by its **base** id (`res_id`), whatever was done to it:
  - `r_spark_res_id` with `r_spark_category`: `CATEGORY_UNIQUE` a Signature Epiphany, `rsp<N>_<card>`; `CATEGORY_PUBLIC` a Neutral one, an `r_spark@r_spark` id. A card holds one or the other;
  - `r_spark_god`, a Divine Epiphany;
  - `copy_by_count`, a duplicate;
  - `remove_by_count`, listed yet out of the deck, and absent from the removal record: the card a Conversion (the game's "Convert") replaced is one, flagged `is_erased_transform_card`. `is_transform_card` flags the card a Conversion made, and `transform_card_id` is a number that is no card's id;
  - `add_talents`, keywords the run added, by numbers the client's tables never use (`model.WIRE_TALENTS`): the Duplicated keyword every copy carries, and season 4's four Desire keywords;
  - `desire_talent_counts`, a Desire card's points per Desire keyword, adding up to its level. **A level-1 card records none**: it holds its own keyword's one, which `wire` fills in (`model.desire_of` reads the keyword and the level off the id, `card_ds04_des_<keyword><card><level>`);
  - `eidolon_reward_ids`, a Persona's effects, one per slot;
  - a season 5 Memory card's grade and variant are its id: `card_ds05_a_b<memory>_<grade>_<variant>`.
- `remove_card_datas`, the removal record, may be missing. It lists the Combatant's own cards and added ones, and a card listed there can be back in the deck.
- `equip_datas`: per piece `res_id`, `star_grade`, `reinforce_res_ids` (its Buff) and `bless_relic_res_ids` (season 2's hammer: another piece's effect added).

**Build Presets**, the in-game deck builder's, arrive per Combatant from `build_preset/load_preset`; the capture does not keep them.

## Deck points

`rules.weight` prices a deck by `savedata_point_define`'s figures, read from the client, so a patch that reprices a row moves the program with it. The weight and every figure are in tens of the points the game shows (`rules.POINT_UNIT`); a deck may weigh `rules.CAP`, the 180 points the game's help gives for editing a Save Data (`tt_pg@desc@savedata@020`).

| Charge | Row | How |
| --- | --- | --- |
| A preset card deleted (`srt1`–`srt4`) | `cd_remove_start` | each one not in the deck, whatever the removal record says: a card listed there and back in the deck costs nothing |
| Another Signature card deleted | — | free |
| A card that is not the Combatant's own | by its kind: `cd_get_job` for Neutral and Event Neutral cards; `cd_get_sort_monster_<rarity>` for a Monster card; `cd_get_<kind>` for the rest, such as `cd_get_taboo` and `cd_get_eidolon` | every one, copies too |
| A duplicate | `cd_copy_revise_by_count` | the n-th duplicate in the deck pays the list's n-th figure, the last figure standing for every one past it, whatever card it copies |
| A Divine Epiphany | `god_r_spark` | each |
| A Conversion | `cd_transform_default_point` | each card one made, besides the deleted card's and the new card's own charges |
| A removal | `cd_remove_revise_by_count` | as duplicates are, over the removals `rules.MAX_REMOVALS` counts; the row holds only zeros, so nothing shows which removals the game reads |
| A hammer blessing | `cd_relic_hammer` | each piece that has one |
| An Equipment Buff | `relic_reinforce_<kind>` | each |
| Signature and Neutral Epiphanies, Persona effects, Desire levels, Memory grades | — | free |

**Where the points come from.** No table names the card kind a row prices, so the program maps kinds to rows itself: a kind's row is `cd_get_<sort>`, so a future season's cards find theirs by name. **A kind with no row is free**: confirmed for Desire and Memory cards and the Combatant's own (`rules.FREE_SORTS`), assumed for any other, which `Weight.assumed` names until a Save Data holding one settles it. A row the program does not price is reported by `Catalogue.problems`. The game's help states each rule in words, on its Save Data pages (`tt_pg@desc@savedata@<nnn>` under `tt_outgame@title@ref@savedata_<nnn>`): 013 card types, 014 Divine Epiphany, 015 duplication, 016 removal, 017 Forbidden, 018 Refinement and God's Hammer, 020 editing, 021 Persona, 022 Desire.

**How it holds.** Every Save Data made since `RULES_SINCE` in `checks/check_deck_rules.py` weighs exactly what these rules give, the capture archive's included. Some made before it, in Seasons 1 and 2, weigh otherwise: a deck's weight is fixed when it is made, under the rules of the day. A patch that reprices a row reweighs every deck made before it, and the date moves to the patch's.

## Deck-building rules

`rules.warnings` lists what a deck breaks, each a `DeckWarning` naming its rule. They warn and never block. No captured Save Data made since `RULES_SINCE` breaks any of them, and where a rule reads more than one way, the reading kept is the one no accepted deck breaks.

- **`unknown`**: a Combatant, card, Signature Epiphany, Neutral or Divine Epiphany, Persona effect, Equipment, Buff, hammer blessing or Mutation the client's tables lack.
- **`cap`**: a deck weighing more than `rules.CAP`.
- **`class`**: a card whose classes (`ownable_link_base_class_define_id`) lack the Combatant's. Only Neutral, Persona and Desire cards may carry classes; a card with none, as every other kind is, any Combatant may hold.
- **`neutral`** and **`divine`**: an Epiphany whose conditions the card fails: class, category, cost range (−1 for no bound), keywords (`target_card_include_talent` needs any one of its list, `_exclude_talent` none), and tags (`r_spark_tag` and `r_spark_exclude_tag` against the card's `r_spark_tag_default`, the same way).
  - **The cost is the card's printed cost**: no cost change counts, neither another Epiphany's nor one made in battle.
  - **A Neutral Epiphany reads `r_spark_replace_cost` in its place** where the card sets one: Olga's two 1-AP Attack cards count as 0-cost for it. A Divine Epiphany never does.
  - **A Divine Epiphany is held to the card's Signature Epiphany version**; a Neutral one to the base card, since a card holds one or a Signature Epiphany, not both.
- **`persona`**: more effects than the Persona has slots, or an effect whose class, category or cost the card fails. An effect's own tags are no condition: Save Data hold effects that share a tag with their card. The same effect twice is allowed.
- **`desire`**: a Desire card whose points do not add up to its level.
- **`one_per_deck`**: a second Persona, Desire or Memory card. The client says so in words only of Persona and Desire cards (`disaster_s03_guide_1_desc`, `disaster_s04_guide_1_desc`, help 021 and 022).
- **`copies`**: more than `rules.MAX_COPIES` duplicates.
- **`no_copy`**: a duplicate of a card whose keywords forbid one, Memory (`TALENT_MEMORY`, "cannot … be Duplicated") or Memory Shard. A Forbidden card's kind reads the same way (`tooltip@desc@sort_taboo`), yet the client has a reward that copies one, so a Forbidden duplicate is no warning.
- **`unique`**: a Unique card (`TALENT_ORIGIN`, "Only 1 of each Unique card can be included in the Deck") more than once, counted by its base card and read off each copy's own version: two versions of one card may not both be in a deck when both are Unique.
- **`removals`**: more than `rules.MAX_REMOVALS` removals, counting only the Combatant's own cards in the removal record (`rules.own_removals`). A Desire card's removal never counts (help 022), nor a removed card the run had added.

The readings set aside, each failing decks the game accepted: a Divine Epiphany held to the base card; the replace cost applied to Divine Epiphanies too, or a Neutral Epiphany's cost read without it or after a Divine one's change; include keywords all required; a Persona effect's tags as a condition; every removal counted.

**Before `RULES_SINCE`, a warning can be the card's change rather than the deck's.** One deck made in February 2026 holds a Neutral Epiphany that its card's cost, 0 AP in the client now, no longer fits, and the client archive holds no build from then to show the cost it had.

## Checks

- `checks/check_deck_catalogue.py`: the installed client's read passes `Catalogue.problems`, each of its shapes speaks up when broken in a copy of the read, nothing Sortie-only got in, and the cache serves only its own build and survives a failed write.
- `checks/check_deck_rules.py`: every captured Save Data made since `RULES_SINCE` weighs what it recorded and raises no warning; a catalogue of the check's own, with a figure per row, shows each charge comes off its row and each rule warns about the deck built to break it and nothing else; and the wire import fills, drops and orders what it should.
