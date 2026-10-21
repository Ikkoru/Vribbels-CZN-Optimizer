# Decks

`Vribbels/decks/` is the Deck Builder's model, with no UI in it. None of it needs Tk.

- `catalogue.py` reads everything a deck is made of off the game client.
- `model.py` holds a deck and a team.
- `wire.py` turns the captured Save Data into decks.
- `rules.py` weighs a deck and lists the deck-building rules it breaks.
- `turns.py` reads what each card costs, draws and gives in AP, and which turns it counts in, and sums a deck's turn and the team's.
- `created.py` finds the cards a deck's cards make in battle, and places each in a list.
- `exceptions.py` is the maintainer's table of cards whose play differs from their data.

## The client's tables

Read with `game_client.Client` (`docs/client_data.md`), each table named as `--table` takes it. **Nothing Sortie-only is read**: no `(assault)` table, and no `assault_r_spark_*` row of the Epiphany table. Sortie gives no Save Data, so none of its cards, Equipment or Epiphanies can be in a deck.

| What | Tables | The catalogue's key |
| --- | --- | --- |
| Cards | every `card(<group>)@card`, and season 5's `memory_grade_define@card` | `cards`, by id: its group, name, text, kind (`sort`), category, rarity, cost, keywords (`talent`), classes, `r_spark_replace_cost`, Epiphany tags (`r_spark_tag_default`), effects, child cards |
| A card's versions | every `card(<group>)@card_r_spark` | `versions`, the five Signature Epiphanies (`rsp1`–`rsp5_<card>`); `upgrades`, a Potential node's (`pot_`) and Ego Manifestation's (`lbk_`). A version with no name of its own in the text goes by its base card's |
| Effects and statuses | every `@skill_eff` and `@cs` | `effects`, `statuses`: only those a card, an Epiphany, a Persona effect, a piece of Equipment, a Buff, a Mutation, a Potential node or an Ego Manifestation level reaches, through `link_cs_id`, `link_skill_eff_id` and `show_link_cs_id` |
| Conditions | every `condition(<group>)` set's `@condition`, `@condition_control`, `@cond_card`, `@cond_unit` and `@cond_timing` | `conditions`: for each condition an effect names (`eff_link_condition_id`), its control rows in order, `<key>_<n>`. A `stack` row tests its card, unit and timing parts; a `reset` row says at which battle timing the count starts over |
| Neutral and Divine Epiphanies | `r_spark@r_spark` | `epiphanies`: a Divine one names its god (`god_type`), a Neutral one none, and each holds the conditions below |
| Persona effects | `eidolon_card_define@eidolon_card_slot_info`, `@eidolon_card_reward`, `@eidolon_card_illust_comb` | `persona`: a Persona card's slots, each Lux and Umbra effect, and the names that follow two effects |
| Equipment and its Buffs | `relic@relic`, `relic(disaster)@relic`; `relic_reinforce@relic_reinforce` | `equipment`, each star level's effect; `buffs`, of kind `ARENA`, `LUX` or `UMBRA` |
| Mutations | `savedata_edit_corruption@savedata_edit_corruption` | `mutations` |
| Deck point rules | `savedata_point_define@savedata_point_define` | `points`, in the client's unit, tens of the points the game shows |
| A turn's draw and AP, and the hand's cap | `constant_metagame@constant_meta` | `constants`: `draw`, `energy`, `hand_max` |
| Combatants | `char_base@char_combatant`, `char_base@char_base` | `combatants`: class, whether released (`char_use_playable`), the four starting and four Signature cards, the Ego skill |
| Partners | `partner_base@char_partner`, `partner_base@char_base` | `partners`: name, whether released, the Ego skill's card (`link_card_id`, `p_<res_id>`), and the class its passive needs (`passive_condition_link_base_class_define_id`) |
| Potential nodes | `potential_node@potential_node`, `@potential_node_effect` | `potential`: per Combatant, node (`node_num`, `<n>_<m>`, which the wire numbers `<n><m>`) and level, the cards it upgrades (`NODE_CARD_R_SPARK`) and the statuses it puts on (`NODE_CS_ADD`). Where a Combatant has two trees listed, the game draws the reworked one, whose rows have the higher ids |
| Ego Manifestation | `combatant_limit_break@combatant_limit_break` | `manifestation`: per Combatant (`group`, `limit_<res_id>`), each level naming cards or putting a status on, by its `break_type` |
| What the in-game deck builder offers | every `archive_card(<kind>)@archive_card` | `released`: the cards it lists (`visible_on_build_preset`), each with its sub-categories |

`kinds` holds every Potential node type and Ego Manifestation type the client uses, for `Catalogue.problems` to hold to the ones the program has judged (`catalogue.KNOWN_NODE_TYPES`, `KNOWN_BREAK_TYPES`). Of the node types, only a card upgrade and a status reach a deck's figures: the rest change stats, Epiphany odds and Stress. An Ego Manifestation level upgrades cards (`BREAK_TYPE_CARD_R_SPARK`), puts a battle status on (`BREAK_TYPE_BATTLE_CS_ADD`), replaces the battle statuses of the levels below it (`_OVERWRITE`), or raises Potential nodes' levels, which changes stats only.

**A Combatant's cards are `c_<res_id>_<kind>`**: `srt1`–`srt3` the Basic cards, `srt4` the preset Signature card, `uni1`–`uni4` the other Signature cards, `<card>_rsp1`–`_rsp5` a card's Signature Epiphany versions, `<card>_pot` a card a Potential node upgrades (a Basic card, or Renoa's Dirge Bullet), `<card>_lbk` one an Ego Manifestation level upgrades (`uni4` at level 1, the Ego skill at 3 or 4), `eps` the Ego skill, `cre<n>` the cards it creates in battle. No upgraded card has Signature Epiphanies: `uni4` has none, nor do the Basic cards. A deck starts from the eight `srt` and `uni` cards. A card's kind (`sort`) is `SORT_START` or `SORT_UNIQUE` for those, `SORT_NEUTRAL`, `SORT_ETC` (an Event Neutral card), `SORT_MONSTER_UNIQUE`, `SORT_TABOO` (Forbidden), `SORT_EIDOLON` (Persona), `SORT_DESIRE` or `SORT_MEMORY`; its category `CARD_ATK`, `CARD_SKILL` or `CARD_POWER`, the game's Upgrade.

**The read checks itself** (`Catalogue.problems`). A patch that renames or repurposes a column breaks one of these shapes rather than misreading quietly:

- every released Combatant has its eight cards and a known class;
- every effect a card names is read;
- every Signature Epiphany turns its card into one the tables hold;
- the battle constants are whole numbers;
- Neutral and Divine Epiphanies both exist;
- the in-game deck builder offers something;
- no deck point rule is missing or unknown to the program;
- every condition an effect names is read, each with its control rows;
- the partners are read, each with its Ego skill's card;
- Potential nodes upgrade cards, each to a `pot` version the tables hold, and Ego Manifestation reads;
- the statuses Potential nodes and Ego Manifestation put on are read;
- every node and Ego Manifestation type is one the program has judged;
- no upgraded card also has Signature Epiphanies, since which of the two plays is unread.

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

- **`unknown`**: a Combatant, card, Signature Epiphany, Neutral or Divine Epiphany, Persona effect, Equipment, Buff, hammer blessing, Mutation or partner the client's tables lack.
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
- **`partner`**: a partner whose passive works only with another class (`passive_condition_link_base_class_define_id`). The partner is the deck's own, else the owned Combatant's captured one (*The turn*, a Combatant's progress).

The readings set aside, each failing decks the game accepted:

- a Divine Epiphany held to the base card;
- the replace cost applied to Divine Epiphanies too, or a Neutral Epiphany's cost read without it or after a Divine one's change;
- include keywords all required;
- a Persona effect's tags as a condition;
- every removal counted.

**Before `RULES_SINCE`, a warning can be the card's change rather than the deck's.** One deck made in February 2026 holds a Neutral Epiphany its card's cost no longer fits: 0 AP in the client today. The client archive holds no build from then to show the cost it had.

## The turn

`turns.played` reads what a card in a deck costs, draws and gives in AP each time it is played, as a `Played`. It reads the version the card plays as, with its Neutral or Divine Epiphany's added effects, keywords and cost change, and its Persona effects'.

**A card's effects are walked as the client chains them.** An effect can put a status on the card itself, on other cards or on a unit, and a status holds effects of its own; what an effect does depends on who holds it. A figure is plain only where nothing on the way to it waits for the battle:

- every effect on the way works on play (`OPERATION_ACTIVE`), while its status is held (`OPERATION_PASSIVE`), or on a trigger whose condition is only a time (`turns.fires`);
- every other condition on the way only asks for a matching card in the draw pile, or the draw and discard piles (`turns.available`): "Draw 1 Attack Card of this unit";
- nothing on the way fires by chance (`run_pct` under 100);
- its value is a plain figure (`VALUE_COMMON`), not a count the battle makes, such as one per card discarded.

**A trigger whose condition is only a time** fires at the start of every turn or at the start of battle. A condition's `stack` rows are checked at their battle timing, and its `reset` rows start over at theirs. So a condition with nothing to test fires at the start of every turn when it is checked or starts over then, before or after the draw. It fires at the start of battle when it is checked at the battle's start (`TIMING_BATTLE_START`) or tests for turn 1 (`TIMING_TURN` 1). What it gives counts:

- **at the next turn's start, once per play**, through a status that does not last the battle: "At the start of the next turn, Draw 2" draws 2 a play, a turn late;
- **each regular turn**, through a status lasting the battle that a setup card puts on once (`Played.turn_draw`, `turn_ap`; plan D42), from the turn after its play. A regular card would put such a status on again with each play, so for it the figure is the battle's;
- **in turn 1 only**, at the start of battle (`Played.start_draw`, `start_ap`), for a card that procs then (an Opener); for any other card the battle's.

**Anything else shows as ?** and counts as 0 (plan D12). The figure keeps the part with its amount where the data gives one, so the user sees what to type.

- **A draw** is a `SKILL_EFF_CARD_DRAW`, or a card moved from the draw pile to hand: "Check 3 cards, select and draw one". A card that moves itself to hand needs no draw, so it counts as 1 drawn (plan D69).
- **AP gained** is a `SKILL_EFF_ENERGY_CHANGE`, or another card's cost cut (plan D68): on each card a status sits on, or on every card a unit's status covers.
- **The cost** is the version's printed cost, with the Epiphanies' and the Persona effects' changes. An X card's (−1) and one with none (−2) are the battle's. So is a cost the battle lowers: a cut the card's own status makes, Ignition and Lead (plan D19).
- **A Quietus card costs 0** (plan D67): a deck procs it by discarding it. Quietus is the keyword, or an effect of the card's own (`SKILL_EFF_CARD_TESTAMENT`): the Persona effect "When this card is Discarded, proc this card" is one. `Played.printed_cost` keeps its own.
- **A free play** (`SKILL_EFF_CARD_USE`, plan D49) of a card from the draw pile is a card drawn; from among several piles, one the battle may grant. What it saves, the cost of the card it plays, is always `?` AP: which card that is, the battle decides. A card that plays itself again counts once, with a note.
- **A status that lasts a number of uses** takes them from the effect that puts it on ("the next 2 times"), and its figures count once per use.
- **A choice** takes its first option, and a note says so (plan D44).

**Which turns a card counts in** (plan 3.2): setup for an Upgrade (`CARD_POWER`), any Exhaust keyword and Remove; neither for a card both Unusable and Ephemeral; regular for the rest. An Opener card is marked (`Played.opener`), since its cost also comes out of the setup turn (plan D18).

**The user's own figures** stand over what is read: a `DeckCard`'s `overrides` give a cost, draw or AP gain for a figure the battle decides, and move a card between the lists (plan D12, 3.2). A card moved to setup is played once, so its lasting status gives each turn after, as an Upgrade's does.

**A Combatant's progress** (plan D8) is a `model.CombatantState`: its Potential nodes, its Ego Manifestation level and its partner. A deck sets its own (`Deck.potential`, `manifestation`, `partner`); where it sets none, it plays with the owned Combatant's captured state, which the caller passes as `owned` (`CombatantState.of` reads one off a `CharacterInfo`), and an unowned Combatant has none.

- **Cards it upgrades** (`turns.upgrades_of`) play as their upgrade: Potential 3.1's Basic cards as their `pot` version, Ego Manifestation level 1's `uni4` and level 3 or 4's Ego skill as their `lbk` one. A level names some cards it has no version of, the cards its status makes or strengthens: those play as they are. A card made in battle is made as its upgrade, and an exception for a card holds for its upgrade too.
- **What it puts on for the battle** is read as Equipment is (*Bonuses*): each node at the highest level reached, each Ego Manifestation level reached. A level that overwrites replaces the battle statuses of every level below it, which the client says in words only; the overwrites that keep an earlier status list it again (Diana's and Arabella's level 6). No node's status gives draw or AP today; the Ego Manifestation statuses that do wait for the battle.

**The Ego skills** (`turns.ego_skills`, plan D2, D40) count behind two team options, off by default: the partner's (`partners`) and the Combatant's, upgraded by its Ego Manifestation. Each is used once, in setup turn 1 (`Played.ego`). It costs Ego Points, never AP ("Partner skill that consumes Ego Points", `tooltip@desc@card_tactic_skill`), and is never drawn; its draw and AP count in turn 1, and its lasting statuses each turn after, as a setup card's do. What it makes is made once (*Created cards*): a card leaving after use goes to setup, one that stays to the regular list.

**A deck's turn** (`turns.deck_turns`) sums its regular and its setup cards apart, with the cards they make (*Created cards*); each card needs one draw, but one made into hand. Its nets are what it adds to the team's regular turn (plan D71): its draws less its cards, its AP gain less its cost, and what it gets each turn besides (`DeckTurns.turn_draw`, `turn_ap`): its setup cards' lasting effects, its bonuses, and the user's own corrections, each with a note (`model.Adjustment`; plan D22).

**Bonuses** (`turns.bonuses`, plan D21) are what a deck's Equipment, at its star level, its Buffs and hammer blessings, its Mutation and its Combatant's progress give, read through the same walk as a card's lasting statuses: plainly each turn, plainly at the start of battle, or as the battle decides, which the user can type in as a correction. A hammer blessing adds another piece's effect, read at that piece's first star. The cards a bonus makes join the lists (*Created cards*).

**A Combatant's own AP pool** (`turns.POOLS`, plan D47): Rita's Chronal Ascension, which her Chronicle stacks become at the start of the turn, pays for her Basic and Signature cards before the team's AP, once Chrono Archon is in the deck. Its cap is the client's (the Chronicle status's `overlay_value_max`); the user can set the deck's own (`Deck.ap_pool`). A regular turn's pool pays what her cards cost up to the cap (`DeckTurns.pool_saving`), and in the setup turns it starts the turn after Chrono Archon is played.

**The team's regular turn** (`turns.team_turns`) has a surplus of the turn's own draw and AP plus every deck's nets (plan 3.1). The turn's figures are the client's battle constants (`catalogue.CONSTANTS`). A "?" figure counts as 0 in the sums, and the sum says some part is the battle's. **Ravages a turn** are the user's, 0 until set (plan D48): each adds 1 AP (`turns.RAVAGE_AP`, which the client says in words only), and the On-Ravage effects stay the battle's, shown "on Ravage" with their figures.

**The team's Desire points** (`TeamTurns.desire`, plan D26) sum each Desire card's points per keyword across the three decks. What their passives bring to the turn is the battle's and shows as notes (`TeamTurns.notes`): Inquiry's draw at 5 points, and the Desire Manifestation cards a keyword's 7 points start making (`turns.INQUIRY_DRAW_AT`, `MANIFESTATION_AT`, from the maintainer's account; the client gives them in words only).

**The setup turns** (`turns.plan_setup`, plan D72) assume a perfect draw. Each turn starts with the turn's cards in hand and its AP, the bonuses and corrections each turn, the start-of-battle bonuses in turn 1, and the lasting effects of the setup cards played in earlier turns:

1. every regular card that gains without costing is played: a 0-AP draw, a free AP gain;
2. among the regular cards that trade one for the other, such as a 1-AP card that draws 2, the mix that lets the most setup cards be played is chosen, ties going to what leaves the most over;
3. the setup cards that fit are played, those that give the most first;
4. the rest wait for the next turn, which starts afresh.

An Opener card procs at the start of battle for its AP, without a card in hand, and an Ego skill the options count is used then too, for no AP. A setup card no turn can afford is reported (`SetupPlan.stuck`). Each turn keeps what it played and what it left over: turn 1's and turn 2's surplus (plan D20).

### Created cards

`created.created_cards` finds what a card makes in battle: a `SKILL_EFF_CARD_GET` effect, on the card or on a status it puts on, and what it makes: its cards (`target_card_set_opt_multiple_link`), how many (`eff_value`), and where (`eff_card_place`). Each made card is placed by three questions (plan D14):

- **Does it leave after use?** It does when it is an Upgrade, has an Exhaust or Remove keyword, or has a status keeping it in the Graveyard on Shuffle (`SKILL_EFF_CARD_NOT_SHUFFLE`; plan D51). The keywords its maker gives it count: the effects right after a creation, aimed at the card just made (`CARD_SET_BEFORE_EFF_TARGET`), add keywords (`SKILL_EFF_CARD_TALENT_ADD`) and cut its cost.
- **Is it made once or every time?** Once when its maker leaves after its play (a setup card) and makes it on play; every time when the maker stays, or it is made on a trigger or by a status lasting the battle.
- **Does it go to hand?** Then it needs no draw (plan D15).

| Made card | once, to hand | once, to the deck | every time |
| --- | --- | --- | --- |
| leaves after use | setup, no draw | setup | regular (no draw if to hand) |
| stays | regular | regular | regular, and the deck grows each turn (plan D16) |

**A status held for the battle makes cards too** (`created.status_cards`): Equipment's, a Buff's, the Mutation's, a Potential node's or an Ego Manifestation level's. A card it makes when it is put on, or at the start of battle, is made once; one it makes on any other trigger, once a turn, as plan D14 counts a maker that is not a card, with a note naming the trigger.

A list counts a made card once per copy a creation makes, one turn's worth for a maker that makes it every time. **One of several made**, chosen or at random, takes the first, with a note (plan D44). **A made card that changes no sum** is set apart (`idle`; plan D43): made into hand, free, gone by the turn's end, with no draw, AP or creation of its own. A made card's own creations count too, a step deep.

**The maintainer's exceptions** (`exceptions.EXCEPTIONS`, plan D45, D50) stand over the data where play differs: a card ignored outright (Homing Arrow), one hidden by default (Homing Laser L), a practical cost (Hew (Flash) at 0), or a card that cycles back though its keywords say it leaves (Dirge Bullet). A user can still set any card per deck.

### Held to the maintainer's figures

The maintainer's deck spreadsheet prices the cards of each of its teams, by hand, on its Deck Calcs tab. The cards the program reads exactly as the sheet does are the check's fixture (`DECK_CALCS` in `checks/check_deck_turns.py`); the rest go to the maintainer for review.

## Checks

- `checks/check_deck_catalogue.py`: the installed client's read passes `Catalogue.problems`, each of its shapes speaks up when broken in a copy of the read, nothing Sortie-only got in, and the cache serves only its own build and survives a failed write. No partner's passive draws, gives AP or makes a card that changes a sum, which plan D2 assumes: a patch adding one fails it.
- `checks/check_deck_rules.py`:
  - every captured Save Data made since `RULES_SINCE` weighs what it recorded and raises no warning;
  - on a catalogue of the check's own, with a figure per row, each charge comes off its row, and each rule warns about the deck built to break it and nothing else;
  - the wire import fills, drops and orders what it should.
- `checks/check_deck_turns.py`:
  - on a catalogue of the check's own, each reading rule above holds for the card built to exercise it, and the user's figures stand over it;
  - a deck's lists and nets, and the team's surplus off the catalogue's own turn figures;
  - each timing of a trigger, and what Equipment at its star level, a Buff and a Mutation give;
  - Rita's pool, with its cap read off the client and the user's own, in a regular turn and in setup, and the Ravages a turn;
  - the setup plan on cards built for each of its steps;
  - each cell of the created-card table, and what moves a made card between cells, on a maker built for it, and the cards statuses held for the battle make;
  - a Combatant's progress, the deck's own and the owned Combatant's: the upgrades, what nodes and Ego Manifestation levels give, an overwrite;
  - the Ego skills behind the team's options, in setup turn 1, and what the Combatant's makes;
  - the cards whose figures the Deck Calcs tab gives read the same off the installed client.
