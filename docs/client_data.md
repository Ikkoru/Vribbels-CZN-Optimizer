# The game client's own data

The client carries the tables the game runs on, and the English text for them, in its install folder: names, items, combatants, partners, events and their rewards, everything the wire refers to by id and never names. `Vribbels/game_client.py` reads them, without writing anything there; its docstring covers both file formats. The program runs it at launch, and `docs/client_tables.py` is the maintainer's tool over the same reader.

## Where it is

STOVE installs to `C:\ProgramData\Smilegate\Games\ChaosZeroNightmare` unless told otherwise; the data sits under `bin\appdata\cznlive\gameres`, as `manifest.ssra` and the `.ssrc` chunk files in `chunks` beside it. The manifest indexes every file the game has, in GROUPS: `base` for everything shared, one per language, one per platform. **Only the groups the player installed have chunks on disk**, so an English client holds `lang_en` and no other language.

The program finds an install through STOVE's uninstall entry (`Stove App STOVE_CHAOSZERO`), whose `DisplayIcon` is the loader in the install's `bin`, then the default folder. `game_client_dir` in `settings.json` names one neither finds (`game_client.find_install`), first of the three; Setup & Settings' `Client Status` sets it with `Browse...`, taking the install around any folder picked inside it (`game_client.install_at`). Where none is found, the program says so in Setup Status and in the Capture Log, and uses the copy it shipped with.

## What the program reads at launch

What changes every patch and the server never sends:

- each event's name, for the Checklist's Events block;
- how many rewards each event holds and whether it pays a final reward, for the same rows (`game_client.event_totals`);
- every item's name, for the Capture Log and the Checklist's shops;
- how many Excursion types each combatant has, for the Combatants tab;
- what each daily task counts to and pays toward the day's Activity, for the Checklist's Activities row (`game_client.daily_tasks`);
- each Memory Fragment set's effect, in the game's words: what a set shows where `game_data/sets.py` has no wording of the maintainer's for it (`game_client.set_effects`, `sets.set_bonus`);
- the game's words for each combatant's node 7 and node 5.1, the Combatants tab's tooltips on those two lines of the Character card (`game_client.potential_texts`);
- **every combatant and partner**, laid over `game_data/characters.py` and `partners.py` field by field (`game_client.combatants`, `game_client.partners`, `game_data/client_overlay.py`). A combatant's name, grade, class, attribute, level-60 stats and crit, node 50's and 60's stat, and what levels 61 and 62 add; a partner's name, grade, class, passive name, Ego name and cost, level-60 flat stats (`PARTNER_CLASS_STATS`), and its passive's plain stat lines (`stats`). The hand tables are the fallback for anything the client does not hold, such as a partner's conditional effects, and a unit only the client knows gets an entry from the client alone. The data check reads the hand tables as typed (`client_overlay.hand`), and `--audit` lists where they and the client disagree;
- each Chaos's name and season by its stage id, and each Zero System special option's name, for the Chaos runs (`game_client.chaos_names`, `zero_specials`). The program's own names (`chaos_estimate.CHAOS_NAMES`, `ZERO_SPECIALS`, the maintainer's spellings from the update notes) go over the client's where both name one; the client's fill what they lack (`chaos_estimate.chaos_names`, `zero_special_name`);
- which 5-stars the Normal Rescues offer (`game_client.general_units`, the `general_ssr_c`/`_s` pools), which tells a Seasonal rerun from a Normal Rescue Rate-Up in the Gacha History until a rates reply the account captured says it instead (`gacha_history.pool_of`);
- the exp each level and each Affinity level takes, swapped in whole for `game_data/constants.py`'s tables (`game_client.exp_tables`, `game_client.affinity`): `CHARACTER_EXP_TABLE` and `PARTNER_EXP_TABLE`, which turn a unit's exp into its level, and `AFFINITY_TO_NEXT` and `FRIENDSHIP_BONUSES`, Affinity's level and stats. A kind whose grades level apart, or a table with a level missing, leaves the hand table standing;
- each item's rarity, which draws the plate behind its icon over what the item tables derive (`game_client.item_rarities`, `constants.item_art`), and each class's name, which a combatant's and a partner's class are read in (`game_client.class_names`, `CLASS_NAMES` where the text has none);
- which main stats each Memory Fragment slot carries, swapped in whole for `constants.SLOT_MAIN_STATS`, for the Memory Fragments tab's main-stat filter, and each substat's weight in a new one's draw, for `constants.SUBSTAT_DRAW` (`game_client.fragment_stats`). A stat the program has no name for is left out, and a slot missing leaves the hand table standing. Each substat's roll bounds go over `STATS`', which the Gear Score divides by; where its max roll is not the one the shipped presets were derived with, the program re-works the presets (`preset_weights.md`, *When the game's rolls move*). The maxed main stats and top levels the same reader gives are held to `constants.py` by `checks/check_client_overlay.py` and never laid over.

**Not in the client:** a banner's or a season's dates (`gacha_list` and `disaster_season` hold no schedule; the server sends it), and the maintainer's names for a Great Rift's parts (`stats_history.RIFT_CODENAMES`). What a Chaos run pays (`chaos_estimate.SHIPPED`, from captures) and the leaderboards' tops are the server's alone. The shops' stock comes off the wire (`shop_stock`); their names (`shop_stock.SHOPS`, which also picks the shops the Checklist tracks) are the program's, with `--audit` listing where they and the game's part.

The first source that knows an id wins:

1. what this machine's client says, saved to `settings/game_client.json` with the install and build it was read at, so the client is read again only after a patch. **Where this build will not read, or the client is not found, that file's read of an earlier build stands in, while it is newer than the shipped table** (`game_client.fallback`);
2. `Vribbels/game_data/from_client.py`, the same reading as of the build the program shipped with: `python docs/client_tables.py --ship` after a patch, before a release, and review the diff. The release procedure runs it (`.claude/skills/release/SKILL.md`);
3. nothing: the Checklist shows the event's id and reads its rewards off the wire alone (`events.md`, *An event the client does not hold*). The Capture Log shows the item's id, and the Combatants tab `7?`, the floor every combatant has, for the total.

**An item name of the program's own goes over all three** (`game_data.constants.item_names`): its tables and `RECORDED_NAMES` override the client, and `--audit` lists where they disagree. The capture addon takes its names when it is written, so a client read that lands after a capture starts reaches the next capture.

`check_event_names` holds the readers, the cache, the shipped table and the order of the sources.

## The archive

**Every build's whole data, kept for when a patch makes the client unreadable**: every table the reader decodes and all the English text, not only the facts the launch read keeps. It is the game's own data, so it stays on the maintainer's machine: `Vribbels/client_archive/`, gitignored.

- **The folder is the opt-in.** The program archives a build at launch only where `client_archive/` exists in its data folder, on a worker, once per build (`OptimizerGUI._start_client_archive`). `python docs/client_tables.py --archive` creates the folder and archives the installed build. A build that will not read leaves the last one archived standing.
- **`latest.zip` holds the newest build**, one deflated entry per table and per text group, read a table at a time. **`history.xz` holds every older one** in a single file at xz's strongest setting, one stream per build, appended when a newer build takes the newest's place. A blob no patch changed is stored once across all builds, so an older build costs only what its patch changed. On build 88, the newest build's file came to 17 MB, and xz turned the build's 194 MB of decoded JSON into 9 MB, where zstd's level 22 managed 9.4 MB in three times the time. The module docstring (`Vribbels/client_archive.py`) has the formats.
- **Reading it back**: `--archived` lists the builds held; `--from-archive [BUILD]` reads one in place of the client for `--list`, `--table`, `--text`, `--audit` and `--ship`, the newest unless a build is named. `client_archive.open_build` gives code the same, read the way `game_client.Client` is. `checks/check_client_archive.py` holds three builds through the round trip.

## The text

`text/en/text.db` holds the English for everything, keyed by a text id of the form `<table>@<column>@<row id>`: `item@name@3000003` is that item's name, `event@title@event_161` that event's title. **A table's text column holds the id itself**, so the join is a lookup, never a guess from the row's own id.

Not every text is a player-facing name. `event_schedule`'s `content_desc` is a description, and some are notes for the developers (`260429 - Free Rescues`); the name the game shows an event under is `event`'s `title`, and an event row names its schedule in `link_event_schedule_id`.

**Content can be in the tables before its English is.** The live Galactic Disaster's Chaos has a row in `chaos` and no `chaos@title` text yet, while the season's own title has one.

## Where each fact is

A table's name below is its archived name without its `db` folder and `.db` ending, as `--table` takes it.

| Fact | Tables | How |
| ---- | ------ | --- |
| An event's name | `event@event` | `title`. The wire's schedule id is in `id`, `link_event_schedule_id`, `multiple_link` or `multiple_key`, depending on the kind (`type`) |
| A name `event@event` does not give | `event_trauma_code@event_trauma_code`, `life_cycle_event_content@life_cycle_event_content`, `countdown_attendance@countdown_attendance_define`, `event_combatant_trial@event_combatant_trial` | a Trauma Code's schedule reaches its event row through the code's own id; the returning players' events and the countdown check-ins are named in their own tables. Every Combatant Trial is called the same, so each is named for its first slot's combatant (`char_base@name@<id>`) |
| An event's rewards | `event_mission@event_mission`, `event_mission@event_mission_define` | a mission row per reward, by `link_event_id`; a define row's `special_reward_*` is the final reward that unlocks after the rest |
| Other reward shapes | `event_mission@event_mission_reward`, `event_daily_check@event_daily_check`, `event_nodelist_define@event_nodelist_define`, `event_summer@event_summer_reward`, `event_summer@event_summer_story` | a step track's steps by `mission_value`; a check-in's days; a Node List's nodes; the summer puzzle's and stories' rewards |
| A combatant | `char_base@char_base`, `char_base@char_combatant` | name and rarity; class (`link_base_class_define_id`), attribute (`link_ego_type_id`, a colour), level-1 stats and crit |
| Its stats at a level | `char_base@combatant_level`, `char_base@combatant_ascend` | **steps, not totals**: level 60 is the level-1 stat, plus every level's step up to 60, plus the five promotions' |
| A level's exp | `char_growth@char_exp` | **the exp from each level to the next**, not the total: a row per level, a column per kind and grade (`combatant_rarity_ssr_require_exp`, `supporter_rarity_r_require_exp` and the rest), -1 from the kind's top level on. Accumulated, they are the thresholds |
| Affinity, Ego Manifestation | `friendship_level@friendship_level`, `combatant_friendship_bonus@combatant_friendship_bonus`, `combatant_limit_break@combatant_limit_break` | the exp from each Affinity level to the next, -1 at the cap; the stats and rewards each level adds, in the group every combatant names (`link_combatant_friendship_bonus_group`), with a combatant's own special rewards in rows of their own (`extend_link_combatant_friendship_bonus_id`); each manifestation's effect, with its text |
| A partner | `partner_base@char_partner`, `partner_base@partner_level`, `partner_passive@partner_passive`, `card(partner)@card` | flat stats and their steps; the passive per class and level, its text `partner_passive@description@<id>_c<class>_lv<level>`; the Ego card's name and cost |
| Potential | `potential_node@potential_node`, `potential_node@potential_node_effect` | each combatant's nodes and maxima, text `potential_node@desc@...`. Where a combatant has two trees listed, the game draws the reworked one, whose rows have the higher ids (`game_client.live_nodes`). An effect row is `NODE_STAT_ADD`, a stat always; `NODE_STAT_ADD_ANOTHER_STAT`, a stat once its check reaches `stat_check_threshold`; `NODE_STAT_ADD_SKILL_EFF_VALUE`, a card's figures the same way; or `NODE_CS_ADD`, an in-battle effect whose figures are elsewhere. A checked row grants `stat_add_limit`, and with `stat_check_use_excess` grants `value`/100 for each point past the threshold instead, up to that limit |
| Memory Fragment stats | `piece_option@piece_option`, `piece_reinforce@piece_reinforce` | a row per main stat a slot can carry (`main_piece_<slot>`) and per substat (`random_option`), by stat id, with a figure list per rarity (`common`, `uncommon`, `rare`, `legend`, `unique`): a main stat's level-0 value and what each level-up adds (`*_reinforce_value`), a substat's every roll. `ratio` is a substat's weight against the others, read as how often it is drawn new. A `piece_reinforce` row per rarity and level a fragment can stand at, `reinforce_<rarity>_<level>` |
| Memory Fragment sets | `piece_set_option@piece_set_option`, `item_piece@item` | a row per set, `set_public_<n>` for the wire's set id. A row with an `order` is one fragments drop in: `set_option_type` is its piece count, and the matching `set<n>_*` columns its effect, a stat and figure (`SET_TYPE_STAT`) or a skill hook, with its words in text. The other piece counts' columns and texts are left from older sets. Every fragment item |
| Items | the `item_*@item` tables | `item_type`, `rarity` (`RARITY_COMMON` to `RARITY_UNIQUE`, Mythic), `icon` (the image's name, without `.png`) and where each is found; text `item@name@<id>`, `item@desc@<id>` |
| Classes | `base_class_define@base_class_define` | a row per class in the game's order, by the id a combatant's `link_base_class_define_id` names: its name and description in text (`base_class_define@class_name@<word>`, the word `knight` for Vanguard) |
| Shops | `shop_category@shop_category`, `shop_category@shop_sub_category` | a category per shop menu and a sub-category per screen in it, each with its title in text (`shop_category@category_title@<id>`); what a shop sells comes off the wire |
| Equipment | `relic(disaster)@relic`, `relic@skill_eff` | what the game's text calls Equipment is a `relic`: names `relic@name@...`, effects `relic@s1_description@...`, whose `#rev_..#` values are in the `skill_eff` tables |
| A lifetime counter, and the achievements on it | `accumulate_condition@accumulate_condition`, `achievement@achievement` | a row per counter, the wire's `ac_collection_<n>`: its `condition_type`, and the `opt_*` columns that split a type several counters share (combatant or partner and rarity, a level band, a faction, the Simulation stages counted). An achievement's `link_accumulate_condition_id` names the counter it counts off and `count` its target, with its name and description in text (`achievement@name@<id>`, `@desc@`) |
| A daily task | `daily_achievement@daily_achievement` | one row per task, the wire's `daily_achieve` res_id: `count`, the score it has to reach, and `point_count`, what it then adds to the day's Activity |
| A Mutation | `savedata_edit_corruption@savedata_edit_corruption` | one row per `corruption_option_<n>`, the number a Save Data carries: its name and effect in text (`savedata_edit_corruption@name@corruption_option_<n>`, `@desc@`), and `ratio`, its weight in a roll |
| Excursion types | `town_visit@town_normal_visit` | one row per type, `group` `normal_visit_<combatant id>`. A partner, and a combatant not yet released, has one placeholder row |
| Galactic Disasters | `disaster_season@disaster_season`, `disaster_chaos_list@disaster_chaos_list`, `chaos@chaos` | a season's title is text `chaos@title@disaster_sNN`, its Chaos's `chaos@title@chaos_NN` |

## What it was held against

The derivations above were checked against what the program already knows, and they agree except where marked:

- **Combatants, partners, item names and art, sets, node 7s, exp, Affinity, Memory Fragment stats, classes and shop names**: `python docs/client_tables.py --audit` lists every field of `game_data`'s that disagrees with the client, and the units and levels either side lacks. The disagreements are the maintainer's to settle, since the hand-typed figure can be the newer.
  - Combatant stats at 60, derived as the table above says, reproduce `game_data.characters` for every combatant, which is what vouches for the derivation; so do levels 61 and 62, crit, and every node 50 and 60.
  - A partner's plain stat lines are its `partner_passive` rows whose `nb_eff` is `EFF_STAT_UP_PARTNER`, naming a `stat_up_eff` row (stat, figure); they reproduce every partner's hand `stats`. A line through a status (`link_cs_id`) is conditional, and stays the maintainer's to encode. A partner's grade is in its level curve's name (`dev_level_r`, `sr`, `ssr` for the 4.5 Arkhianon Supply, `sssr`), and its flat stats at 60 reproduce `PARTNER_CLASS_STATS`. `checks/check_client_overlay.py` holds all of it to the hand tables on every run.
  - A partner's passive is compared by the figures in its text at each level, read as the game draws it (`game_client.passage`): a keyword's marker carries a level number, which is not one of the figures.
  - A set's wording in `sets.py` is the maintainer's own, so only its figures are compared with the game's, as a set of figures: a short wording states once what the game's repeats. `checks/check_set_wordings.py` runs the same comparison on every run, and after a patch says whether a set's figures moved or its words did.
  - Node 7 is compared both ways: each effect row, read as the table above says, against `potential_7.py`, and `potential_7.py`'s figures against the node's text. **The data is the source** where the two disagree, the text being written for the player. Tenebria's data adds 2% per 20 ATK past 600, where her text says 1%. Sereniel's ramps her second +5% from 20% Crit Chance to 40%, where her text adds it at 40%, as the developer note on her rework also does (`page.onstove.com/chaoszeronightmare/en/view/14536071`). A battle settled both for the data: on 2026-10-12 a Tower battle had Tenebria at 759 ATK and Sereniel at 34.5% Crit Chance. Their sheets' Passion and Instinct damage, 31 and 13.625, are the data's to the decimal, and 2.05 and 3.625 above the texts'. `potential_7.py` follows the data, and its `TEXT_FIXES` rewrite those words in the text the Combatants tab shows; the audit names a fix whose words a patch has since rewritten.
  - Node 5.1 is held the same way, its data's figures against its text. The program prices no node 5.1, so there is nothing of its own to compare; the text is the tooltip.
- **Exp and Affinity**: the client's thresholds reproduce every level the game was read at for `constants.py`, which takes the rest from the client. Each kind's grades level alike. Its Affinity tables reproduce `AFFINITY_TO_NEXT` and `FRIENDSHIP_BONUSES`, and a combatant's own rows hold special rewards and no stat. `checks/check_client_overlay.py` holds them to the hand tables on every run.
- **Memory Fragment stats**: the client's slot options reproduce `SLOT_MAIN_STATS`, a Legendary's level-0 main plus five level-ups each `MAIN_STAT_VALUES` ceiling as the game draws it, the legend column's lowest and highest roll each substat's `STATS` bounds, and each rarity's top level `MAX_LEVEL_PER_RARITY`. The substats' draw weights (`ratio`) are `SUBSTAT_DRAW`, which the Average and Likely Potential draw a new substat by (`game_formulas.md` §2).
- **Classes, item art and shops**: the client's classes are `CLASSES`, in the Materials tab's order (`CLASS_ORDER`), and every item table's rarity and icon is the client's. A tracked shop's name holds the game's for it, the Sortie shop's aside, which `--audit` lists.
- **Event totals**: `event_bartender_1` reads 24 missions and a final reward, and the summer event 10 puzzle and 15 story rewards. The seven-day story events, the policy, stock and arena events, the check-ins and the later Node Lists agree with what the wire and the game's own screens gave too.
- **The three story-map Node Lists**: the client gives `event_nodelist_001`, `003` and `004` 15, 16 and 19 mission rows and a final reward besides. So do the game's update notices for them (`page.onstove.com/chaoszeronightmare/en/view/12012929`, `12945661` and `13168282`: per chapter its achievements, then one for the lot). The captures held one row fewer each.
- **Galactic Disaster challenge missions** (`event_chaos_mission_*`) are not in the client's event tables at all: only their schedules are.

## What a patch can break

| Change | How it shows | Way back |
| ------ | ------------ | -------- |
| The archive's format, as the 2026-09-30 patch's switch from `data.pack` to SSRA did | the manifest's version: the tool stops, naming it | the ripper's `SSRArchive.cpp`, which follows the client |
| Entries encrypted | the tool stops, naming the file. The flag exists in the manifest and nothing sets it yet | none without the key. The last archived build stays readable (`--from-archive`), and the launch facts fall back to the last cache |
| The tables' key | nothing: the key is read off the data on every run | |
| The tables' cipher or header | the tool stops: no key rotation yields the magic, or the header size differs | the ripper's `DBParser.cpp` |
| A table or column renamed | whatever reads that name fails on it | the table's new name, from `--list` and `--table` |
| A new install path | the manifest is not found: Setup Status and the Capture Log say the client was not found | `Browse...` in `Client Status`, which sets `game_client_dir`; `--client` for the tool |

The program meets each of these as a read that fails, and keeps the last cache's names and totals where it is newer than the shipped ones, else the shipped; `debug_perf_log` records why.
