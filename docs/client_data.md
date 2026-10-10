# The game client's own data

The client carries the tables the game runs on, and the English text for them, in its install folder: names, items, combatants, partners, events and their rewards, everything the wire refers to by id and never names. `Vribbels/game_client.py` reads them, without writing anything there; its docstring covers both file formats. The program runs it at launch, and `docs/client_tables.py` is the maintainer's tool over the same reader.

## Where it is

STOVE installs to `C:\ProgramData\Smilegate\Games\ChaosZeroNightmare` unless told otherwise; the data sits under `bin\appdata\cznlive\gameres`, as `manifest.ssra` and the `.ssrc` chunk files in `chunks` beside it. The manifest indexes every file the game has, in GROUPS: `base` for everything shared, one per language, one per platform. **Only the groups the player installed have chunks on disk**, so an English client holds `lang_en` and no other language.

The program finds an install through STOVE's uninstall entry (`Stove App STOVE_CHAOSZERO`), whose `DisplayIcon` is the loader in the install's `bin`, then the default folder. `game_client_dir` in `settings.json` names one neither finds (`game_client.find_install`).

## What the program reads at launch

What changes every patch and the server never sends: each event's name, for the Checklist's Events block; every item's name, for the Capture Log and the Checklist's shops; and how many Excursion types each combatant has, for the Combatants tab. The first source that knows an id wins:

1. what this machine's client says, saved to `settings/game_client.json` with the install and build it was read at, so the client is read again only after a patch;
2. `Vribbels/game_data/from_client.py`, the same reading as of the build the program shipped with: `python docs/client_tables.py --ship` after a patch, before a release, and review the diff;
3. nothing: the Checklist shows the event's id, the Capture Log the item's, the Combatants tab `7?`, the floor every combatant has, for the total.

**An item name of the program's own goes over all three** (`game_data.constants.item_names`): its tables and `RECORDED_NAMES` override the client, and `--audit` lists where they disagree. The capture addon takes its names when it is written, so a client read that lands after a capture starts reaches the next capture.

`check_event_names` holds the readers, the cache, the shipped table and the order of the sources.

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
| Affinity, Ego Manifestation | `combatant_friendship_bonus@combatant_friendship_bonus`, `combatant_limit_break@combatant_limit_break` | stats and rewards per level; each manifestation's effect, with its text |
| A partner | `partner_base@char_partner`, `partner_base@partner_level`, `partner_passive@partner_passive`, `card(partner)@card` | flat stats and their steps; the passive per class and level, its text `partner_passive@description@<id>_c<class>_lv<level>`; the Ego card's name and cost |
| Potential | `potential_node@potential_node`, `potential_node@potential_node_effect` | each combatant's nodes and maxima; an effect is `NODE_STAT_ADD` with a stat and value, or a card or skill hook; text `potential_node@desc@...` |
| Memory Fragment sets | `piece_set_option@piece_set_option`, `item_piece@item` | the 2, 4 and 6 piece effects, each a stat and value or a skill hook, with names and descriptions in text; every fragment item |
| Items | the `item_*@item` tables | `item_type`, `rarity`, `icon` and where each is found; text `item@name@<id>`, `item@desc@<id>` |
| Equipment | `relic(disaster)@relic`, `relic@skill_eff` | what the game's text calls Equipment is a `relic`: names `relic@name@...`, effects `relic@s1_description@...`, whose `#rev_..#` values are in the `skill_eff` tables |
| Excursion types | `town_visit@town_normal_visit` | one row per type, `group` `normal_visit_<combatant id>`. A partner, and a combatant not yet released, has one placeholder row |
| Galactic Disasters | `disaster_season@disaster_season`, `disaster_chaos_list@disaster_chaos_list`, `chaos@chaos` | a season's title is text `chaos@title@disaster_sNN`, its Chaos's `chaos@title@chaos_NN` |

## What it was held against

The derivations above were checked against what the program already knows, and they agree except where marked:

- **Combatants and partners**: `python docs/client_tables.py --audit` lists every field of `game_data`'s combatants and partners that disagrees with the client, and the ones either side lacks. Combatant stats at 60, derived as the table above says, reproduce `game_data.characters` for every combatant but Haru, which is what vouches for the derivation. A partner's passive is compared by the figures in its text at each level, so a difference of a lone 1 or 2 is usually wording, a turn or stack count one side spells out; the rest are the maintainer's to settle, since the hand-typed figure can be the newer.
- **Event totals**: `event_bartender_1` reads 24 missions and a final reward, and the summer event 10 puzzle and 15 story rewards. Those are the totals worked out from the wire and the game's own screens, and so are the seven-day story events', the policy, stock and arena events', the check-ins' and the later Node Lists'. **The three story-map Node Lists differ by one**: the client gives `event_nodelist_001`, `003` and `004` 15, 16 and 19 mission rows and a final reward besides, where the captures held 15, 16 and 19 rewards in all, the final among them. A capture of the next one settles which.
- **Galactic Disaster challenge missions** (`event_chaos_mission_*`) are not in the client's event tables at all: only their schedules are.

## What a patch can break

| Change | How it shows | Way back |
| ------ | ------------ | -------- |
| The archive's format, as the 2026-09-30 patch's switch from `data.pack` to SSRA did | the manifest's version: the tool stops, naming it | the ripper's `SSRArchive.cpp`, which follows the client |
| Entries encrypted | the tool stops, naming the file. The flag exists in the manifest and nothing sets it yet | none without the key |
| The tables' key | nothing: the key is read off the data on every run | |
| The tables' cipher or header | the tool stops: no key rotation yields the magic, or the header size differs | the ripper's `DBParser.cpp` |
| A table or column renamed | whatever reads that name fails on it | the table's new name, from `--list` and `--table` |
| A new install path | the manifest is not found | `game_client_dir`, or `--client` |

The program meets each of these as a read that fails, and keeps the shipped names; `debug_perf_log` records why.
