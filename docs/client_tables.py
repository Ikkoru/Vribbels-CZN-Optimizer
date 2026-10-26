"""Read the game client's own data tables and English text. Reads only.

    python docs/client_tables.py                     what is installed
    python docs/client_tables.py --list REGEX        archived paths
    python docs/client_tables.py --table NAME        one table, as TSV
    python docs/client_tables.py --text REGEX        English text by id or words
    python docs/client_tables.py --grep REGEX        every table row holding it
    python docs/client_tables.py --season SEASON     what a season pays
    python docs/client_tables.py --renames [BUILD]   item names a patch moved
    python docs/client_tables.py --ship              the shipped copy, level
    python docs/client_tables.py --audit             game_data against the client
    python docs/client_tables.py --archive           keep this build's whole data
    python docs/client_tables.py --archived          the builds the archive holds
    python docs/client_tables.py --from-archive [N] ...   read an archived build

`--table` takes a table's archived name without `db/` and `.db`, such
as `event@event` or `char_base@char_combatant`; `--out FILE` writes the
TSV there instead of printing it, `--rows N` prints only the first N,
and `--client DIR` names an install other than the one the program
finds. What each table holds, and what was checked against it, is
`docs/client_data.md`.

`--grep` answers where an id lives when nothing says which table holds
it: a new event's schedule, a season's currency, an item a shop sells.
It prints each row with a cell matching REGEX, as its table, its first
column and every matching `column=value`.

`--renames 88` prints every item the client names otherwise than an
archived build did -- a patch can give an id another item, a
placeholder's `???` its real name among them -- with the program's own
name for each, and how many ids the newer build added and dropped. With
no build, the newest archived one older than the client.

`--season disaster_s05` prints what a Galactic Disaster season pays in
its own currency, term by term as `SEASON_ESTIMATE` in
`Vribbels/ui/tabs/checklist_tab.py` adds them up: the weekly rewards a
week, everything else once. A season's tables fill in by part, so it is
re-run after each patch; `docs/client_data.md`, *Where each fact is*,
says which table is which term.

`--ship` brings the program's own copy of the client's facts level
with the client, what a player whose client the program cannot read
sees instead: it rewrites `Vribbels/game_data/from_client.py`, and
writes the combatants and partners a patch added into `game_data`'s own
tables, marked as the client's (`Vribbels/game_data/client_sync.py`).
A launch from source and the build run it on their own; review its
diff. With `--audit` beside it, the audit runs after it, on the tables
it left.

`--audit` prints every place `game_data`'s combatants, partners, item
names, exp, Affinity and Memory Fragment tables disagree with the
client, and the ones either side lacks:
the tables are typed by hand, and a patch that rebalances one changes
nothing there. It writes nothing; a disagreement is for the maintainer
to settle, since the hand-typed figure can be the newer one. What
`--ship` wrote is left out, being the client's.

**What the program's own tables decide is never held to the client**:
a Memory Fragment set's name, pieces, model and wording, a partner's
Ego text, the names of the Rescue pools and shops. Those differ on
purpose. What is reported is the CLIENT changing them: `--ship` keeps
the client's own words for them in `from_client.py` (`SET_EFFECTS`,
`EGO_TEXTS`, `CLIENT_NAMES`), and both `--ship`, before it writes, and
`--audit` name each one a newer client changed (`client_changes`).

`--archive` keeps the installed build's every table and its English
text in `Vribbels/client_archive/` (`Vribbels/client_archive.py`),
creating the folder, which also opts the program in: from then on it
archives each new build at launch. `--archived` lists what the archive
holds. `--from-archive` reads an archived build instead of the client,
the newest unless a build is named, for `--list`, `--table`, `--text`,
`--audit` and `--ship`: what is left to read once a patch makes the
client unreadable.

The reader itself is `Vribbels/game_client.py`, the same one the
program runs at launch. Python 3.14, for `compression.zstd`.
"""

import argparse
import collections
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "Vribbels"))

import client_archive                                         # noqa: E402
import game_client                                            # noqa: E402
from game_client import Client                                # noqa: E402

SHIPPED = REPO / "Vribbels" / "game_data" / "from_client.py"

SHIPPED_HEAD = '''"""What the program reads off the game client (`game_client`), as of the build it shipped with.

Written by `python docs/client_tables.py --ship`, as of the game build
`BUILD`; never edited by hand. What a player's own client says wins
over these (`game_client`), so this is what a player sees whose client
the program could not find or read. The combatants and partners are not
here: `--ship` writes the ones the hand tables lack into
`characters.py` and `partners.py` themselves (`game_data.client_sync`).

ASCII throughout: a name's other characters are written as escapes.
"""

'''


def _tsv(columns, rows):
    clean = str.maketrans({"\t": " ", "\n": " ", "\r": " "})
    yield "\t".join(columns)
    for row in rows:
        yield "\t".join(row[c].translate(clean) for c in columns)


def shipped_source(client, partners=None):
    """The text of `from_client.py` for what `client` holds; `partners`
    its `game_client.partners`, where already read."""
    names = game_client.event_names(client)
    totals = game_client.event_totals(client)
    items = game_client.item_names(client)
    visits = game_client.excursion_types(client)
    tasks = game_client.daily_tasks(client)
    lines = [SHIPPED_HEAD, f"BUILD = {client.archive.build}", "",
             "# {schedule id: English name}. See game_client.event_names.",
             "EVENT_NAMES = {"]
    lines += [f"    {ascii(key)}: {ascii(name)},"
              for key, name in sorted(names.items())]
    lines += ["}", "",
              "# {schedule id: (rewards, final, steps)}. See "
              "game_client.event_totals.",
              "EVENT_TOTALS = {"]
    lines += [f"    {ascii(key)}: ({rewards}, {final}, {steps}),"
              for key, (rewards, final, steps) in sorted(totals.items())]
    lines += ["}", "",
              "# {trial id: (slot ids)}. See game_client.trial_slots.",
              "TRIAL_SLOTS = {"]
    lines += [f"    {ascii(key)}: {ascii(tuple(slots))},"
              for key, slots in sorted(game_client.trial_slots(client).items())]
    lines += ["}", "",
              "# {schedule id: {'define': define id, 'item': token res_id, "
              "'tiers': [[tier id, tokens], ...]}}.",
              "# See game_client.payment_events.",
              "PAYMENT_EVENTS = {"]
    lines += [f"    {ascii(key)}: {ascii(event)},"
              for key, event in sorted(
                  game_client.payment_events(client).items())]
    lines += ["}", "",
              "# {schedule id: {'event': event id, 'code': code id, "
              "'rewards': [[achievement id, gate schedule], ...], "
              "'final': 0 or 1}}.",
              "# See game_client.trauma_codes.",
              "TRAUMA_CODES = {"]
    lines += [f"    {ascii(key)}: {ascii(code)},"
              for key, code in sorted(
                  game_client.trauma_codes(client).items())]
    lines += ["}", "",
              "# {schedule id: {'id': wire row id, 'pulls': every pull}}. "
              "See game_client.free_gachas.",
              "FREE_GACHAS = {"]
    lines += [f"    {ascii(key)}: {ascii(event)},"
              for key, event in sorted(
                  game_client.free_gachas(client).items())]
    lines += ["}", "",
              "# {schedule id: {'define': define id, 'rewards': [reward id, "
              "...]}}. See game_client.login_rewards.",
              "LOGIN_REWARDS = {"]
    lines += [f"    {ascii(key)}: {ascii(event)},"
              for key, event in sorted(
                  game_client.login_rewards(client).items())]
    lines += ["}", "",
              "# {kind: figure or {id: figure}}: the Checklist's maximums. "
              "See game_client.limits.",
              "LIMITS = {"]
    for kind, value in sorted(game_client.limits(client).items()):
        if isinstance(value, dict):
            lines.append(f"    {ascii(kind)}: {{")
            lines += [f"        {ascii(key)}: {ascii(figure)},"
                      for key, figure in sorted(value.items())]
            lines.append("    },")
        else:
            lines.append(f"    {ascii(kind)}: {ascii(value)},")
    lines += ["}", "",
              "# {schedule id: (episode ids)}. See "
              "game_client.story_chapters.",
              "STORY_CHAPTERS = {"]
    lines += [f"    {ascii(key)}: {ascii(tuple(episodes))},"
              for key, episodes in sorted(
                  game_client.story_chapters(client).items())]
    lines += ["}", "",
              "# {item res_id: English name}. See game_client.item_names.",
              "ITEM_NAMES = {"]
    lines += [f"    {res_id}: {ascii(name)},"
              for res_id, name in sorted(items.items())]
    lines += ["}", "",
              "# {combatant res_id: Excursion types}. See "
              "game_client.excursion_types.",
              "EXCURSION_TYPES = {"]
    lines += [f"    {res_id}: {count}," for res_id, count
              in sorted(visits.items())]
    lines += ["}", "",
              "# {daily task res_id: (score it counts to, Activity it "
              "pays)}. See game_client.daily_tasks.",
              "DAILY_TASKS = {"]
    lines += [f"    {ascii(res_id)}: ({count}, {points}),"
              for res_id, (count, points) in sorted(tasks.items())]
    lines += ["}", "",
              "# {set id: (name, pieces, words, stat, value)}. See "
              "game_client.set_effects.",
              "SET_EFFECTS = {"]
    lines += [f"    {set_id}: {ascii(tuple(effect))},"
              for set_id, effect in sorted(
                  game_client.set_effects(client).items())]
    lines += ["}", "",
              "# {combatant res_id: {wire node: words}}. See "
              "game_client.potential_texts.",
              "POTENTIAL_TEXTS = {"]
    for res_id, nodes in sorted(game_client.potential_texts(client).items()):
        lines.append(f"    {res_id}: {{")
        lines += [f"        {wire}: {ascii(words)},"
                  for wire, words in sorted(nodes.items())]
        lines.append("    },")
    lines += ["}", "",
              "# {stage id: (English name, season)}. See "
              "game_client.chaos_names.",
              "CHAOS_NAMES = {"]
    lines += [f"    {stage}: {ascii(named)},"
              for stage, named in sorted(game_client.chaos_names(client).items())]
    lines += ["}", "",
              "# {Zero System special option id: the game's name}. See "
              "game_client.zero_specials.",
              "ZERO_SPECIALS = {"]
    lines += [f"    {ascii(special)}: {ascii(name)},"
              for special, name in sorted(game_client.zero_specials(client).items())]
    lines += ["}", "",
              "# The Normal Rescues' 5-stars. See game_client.general_units.",
              f"GENERAL_UNITS = {ascii(game_client.general_units(client))}",
              "",
              "# {kind: the exp to reach each level, from level 1}. See",
              "# game_client.exp_tables; game_data.client_overlay lays it "
              "over",
              "# CHARACTER_EXP_TABLE and PARTNER_EXP_TABLE.",
              "EXP_TABLES = {"]
    for kind, reached in sorted(
            game_client.exp_tables(client).items()):
        lines.append(f"    {ascii(kind)}: [")
        lines += _rows([str(exp) for exp in reached])
        lines.append("    ],")
    held = game_client.affinity(client)
    lines += ["}", "",
              "# Affinity: the exp from each level to the next, and the "
              "bonuses",
              "# to each level. See game_client.affinity; laid over",
              "# AFFINITY_TO_NEXT and FRIENDSHIP_BONUSES.",
              "AFFINITY = {",
              "    'to_next': {"]
    lines += _rows([f"{level}: {exp}" for level, exp
                    in sorted(held.get("to_next", {}).items())])
    lines += ["    },", "    'bonuses': ["]
    lines += [f"        {tuple(row)}," for row in held.get("bonuses", [])]
    lines += ["    ],", "}", ""]
    fragments = game_client.fragment_stats(client)
    lines += ["# Memory Fragment stats by stat id: each slot's main stats for a",
              "# Legendary (stat, level-0 value, each level-up's), every roll a",
              "# substat can give one, each substat's weight in a new one's",
              "# draw, and each rarity's top level. See",
              "# game_client.fragment_stats; game_data.client_overlay lays the",
              "# mains over SLOT_MAIN_STATS and the draws over SUBSTAT_DRAW.",
              "FRAGMENT_STATS = {", "    'mains': {"]
    for slot, options in sorted(fragments["mains"].items()):
        lines.append(f"        {slot}: [")
        lines += [f"            {ascii(option)}," for option in options]
        lines.append("        ],")
    lines += ["    },", "    'rolls': {"]
    lines += [f"        {ascii(stat)}: {ascii(values)},"
              for stat, values in fragments["rolls"].items()]
    lines += ["    },",
              f"    'draws': {ascii(fragments['draws'])},",
              f"    'max_levels': {ascii(fragments['max_levels'])},",
              "}", ""]
    rarities = {}
    for res_id, word in sorted(game_client.item_rarities(client).items()):
        rarities.setdefault(word, []).append(str(res_id))
    lines += ["# {rarity: its items' res_ids}. See game_client.item_rarities;",
              "# constants.item_art puts them over the item tables' own.",
              "ITEM_RARITIES = {"]
    for word in game_client.ITEM_RARITY_WORDS.values():
        if word in rarities:
            lines.append(f"    {ascii(word)}: [")
            lines += _rows(rarities[word])
            lines.append("    ],")
    lines += ["}", "",
              "# {item res_id: (how its clock runs, its days or None, the",
              "# schedule it lasts until or None)} for every item the game",
              "# deletes after a while. See game_client.period_items.",
              "ITEM_PERIODS = {"]
    lines += [f"    {res_id}: {ascii(tuple(rule))},"
              for res_id, rule in sorted(
                  game_client.period_items(client).items())]
    lines += ["}", "",
              "# {partner res_id: ((name, acts on the assigned combatant "
              "alone,",
              "# ((limit break, its text from then on), ...)), ...)}, in the",
              "# game's slot order. See game_client.exploration_passives.",
              "EXPLORATION_PASSIVES = {"]
    for res_id, passives in sorted(
            game_client.exploration_passives(client).items()):
        lines.append(f"    {res_id}: (")
        lines += [f"        ({ascii(p['name'])}, {p['assigned']}, "
                  f"{ascii(tuple(tuple(step) for step in p['steps']))}),"
                  for p in passives]
        lines.append("    ),")
    lines += ["}", "",
              "# {partner res_id: ((effect, ((limit break, value from then "
              "on), ...)),",
              "# ...)}: what each Exploration Passive does, in the game's "
              "slot order.",
              "# See game_client.exploration_effects.",
              "EXPLORATION_EFFECTS = {"]
    for res_id, passives in sorted(
            game_client.exploration_effects(client).items()):
        lines.append(f"    {res_id}: (")
        lines += [f"        ({ascii(effect)}, "
                  f"{ascii(tuple((at, float(value)) for at, value in steps))}),"
                  for effect, steps in passives]
        lines.append("    ),")
    skins = game_client.card_skins(client)
    lines += ["}", "",
              "# {Card Skin res_id: (name, rarity, the combatant it is for)}",
              "# and {pack id: (name, {rarity: the chance a pull is one}, the",
              "# combatant its Super Rare is for)}. See "
              "game_client.card_skins.",
              "CARD_SKINS = {"]
    lines += [f"    {res_id}: {ascii(tuple(skin))},"
              for res_id, skin in sorted(skins["skins"].items())]
    lines += ["}", "CARD_SKIN_PACKS = {"]
    lines += [f"    {ascii(pack)}: ({ascii(name)}, "
              f"{ascii(dict(sorted(chances.items())))}, {featured!r}),"
              for pack, (name, chances, featured)
              in sorted(skins["packs"].items())]
    lines += ["}", "",
              "# {season: (amplification nodes by the end of each part, "
              "...)}, each",
              "# read grown onto the copy it replaces. See "
              "game_client.season_nodes",
              "# and grown_season_nodes; chaos_estimate.season_nodes "
              "reads it.",
              "SEASON_NODES = {"]
    from game_data import from_client
    kept = getattr(from_client, "SEASON_NODES", {})
    trees = game_client.season_nodes(client)
    lines += [f"    {ascii(season)}: "
              f"{ascii(tuple(game_client.grown_season_nodes(kept.get(season), trees.get(season))))},"
              for season in sorted(set(kept) | set(trees))]
    words = client_words(client, partners)
    lines += ["}", "",
              "# The client's own words for what the program's tables "
              "decide, kept to",
              "# tell when a newer client changes them: {partner res_id: "
              "its Ego text}",
              "# and {what: the client's name}. See "
              "docs/client_tables.client_words.",
              "EGO_TEXTS = {"]
    lines += [f"    {res_id}: {ascii(text)},"
              for res_id, text in sorted(words["ego"].items())]
    lines += ["}", "CLIENT_NAMES = {"]
    lines += [f"    {ascii(what)}: {ascii(name)},"
              for what, name in sorted(words["names"].items())]
    lines += ["}", ""]
    return "\n".join(lines)


def ship(client):
    """Bring the program's own copy of the client's facts level with
    `client`: `from_client.py`, and the marked lines of `game_data`'s
    tables, a unit they lack added (`game_data.client_sync`). Returns
    lines saying what changed, and what `client` changed of what the
    program's own tables decide (`client_changes`) -- said here, against
    the copy it replaces, since the audit after it reads the new one.
    Nothing is written where a table would come out wrong
    (`client_sync.SyncError`, raised)."""
    from game_data import client_sync, from_client
    partners = game_client.partners(client)
    said, changed = client_sync.sync(
        {"combatants": game_client.combatants(client),
         "partners": partners,
         "recommended": game_client.recommended_partners(client)},
        write=False)
    said += client_changes(client, partners)
    source = shipped_source(client, partners)
    client_sync.write_out(changed)
    held = SHIPPED.read_text(encoding="utf-8") if SHIPPED.exists() else ""
    if source != held:
        SHIPPED.write_text(source, encoding="utf-8", newline="\n")
        said.append(f"{SHIPPED.relative_to(REPO).as_posix()}: build "
                    f"{getattr(from_client, 'BUILD', '?')} -> "
                    f"{client.archive.build}")
    return said


def renames(before, after):
    """Lines naming each item `after`'s client names otherwise than
    `before`'s, with the program's own name for it, then how many ids
    `after` added and dropped. Placeholders count as names here: a
    `???` taking its real name is the commonest move."""
    from game_data.constants import hand_item_names

    def named(client):
        out = {}
        for key, text in client.text().items():
            match = game_client.ITEM_NAME.fullmatch(key)
            name = game_client.clean(text) if match else ""
            if name:
                out[int(match.group(1))] = name
        return out

    old, new, own = named(before), named(after), hand_item_names()
    lines = [f"item {rid}: {old[rid]!r} at build {before.archive.build}, "
             f"{new[rid]!r} at {after.archive.build}; the program's own: "
             f"{own.get(rid, 'none')!r}"
             for rid in sorted(set(old) & set(new)) if old[rid] != new[rid]]
    lines.append(f"{len(set(new) - set(old))} ids new at build "
                 f"{after.archive.build}, {len(set(old) - set(new))} gone")
    return lines


def _rows(items, per=10):
    """`items` as the lines of a literal, `per` to a line: a long table
    on a single line hides a patch's change in the diff `--ship` asks
    to be reviewed."""
    return ["        " + ", ".join(items[i:i + per]) + ","
            for i in range(0, len(items), per)]


# A season's achievement categories, in `SEASON_ESTIMATE`'s words. The
# `score` rows reset weekly; the rest pay once.
SEASON_TERMS = {"score": "Chaos weekly progress, a week",
                "penalty": "Annihilation Rewards",
                "disaster_battle": "Battle Report",
                "disaster_collection": "Mission Records",
                "disaster_ingame": "Chaos Investigation"}
# A reward column and the count beside it: `reward_1_link_item_id` with
# `item_1_count` in the Galactic Disaster tables, `reward_0_count` in
# the story map's.
REWARD_COLUMN = re.compile(r"(.*?)(\d+)_link_item_id")


def _pays(row, item):
    """What one reward row pays in `item`, a res_id as the tables write
    it."""
    total = 0
    for column, value in row.items():
        match = REWARD_COLUMN.fullmatch(column)
        if not match or value != item:
            continue
        prefix, n = match.groups()
        for count in (f"{prefix}{n}_count", f"item_{n}_count"):
            if count in row:
                total += game_client._figure(row[count]) or 0
                break
    return total


def season_payouts(client, season):
    """(the season's currency, [(term, what it pays, a note)]) for one
    Galactic Disaster season, the terms `SEASON_ESTIMATE` adds up.
    Raises KeyError for a season the client does not hold."""
    seasons = {row["id"]: row
               for row in client.rows("disaster_season@disaster_season")}
    item = seasons[season]["material_link_item_id"]
    currencies = {row.get("material_link_item_id") for row in seasons.values()}
    out = []
    achievements = client.rows("disaster_achievement(%s)@disaster_achievement"
                               % season.rsplit("_", 1)[1])
    by_term = collections.Counter()
    for row in achievements:
        by_term[row.get("main_category")] += _pays(row, item)
    for category, words in SEASON_TERMS.items():
        out.append((f"{words} ({category})", by_term.pop(category, 0), ""))
    out += [(f"other achievements ({category})", paid, "")
            for category, paid in sorted(by_term.items()) if paid]
    clears = [row for row in client.rows(
        "disaster_chaos_reward@disaster_chaos_reward")
        if row.get("id", "").startswith(season + "_")]
    out.append(("Seasonal Chaos first clears",
                sum(_pays(row, item) for row in clears),
                f"{len(clears)} difficulties"))
    for table, words in (("story_map_reward@story_map_reward",
                          "Story nodes"),
                         ("story_map_collect_star_reward@"
                          "story_map_collect_star_reward",
                          "Story star tiers")):
        paying = [paid for paid in map(lambda r: _pays(r, item),
                                       client.rows(table)) if paid]
        out.append((words, sum(paying), f"{len(paying)} rows"))
    records = [row for row in client.rows(
        "disaster_rank_record_reward@disaster_rank_record_reward")
        if row.get("id", "").startswith(season + "_")]
    out.append(("Great Rift records", sum(_pays(r, item) for r in records),
                f"{len(records)} records"))
    tiers = client.rows("disaster_rank_score_reward@disaster_rank_score_reward")
    named = {r.get(c) for r in tiers for c in r
             if REWARD_COLUMN.fullmatch(c) and r.get(c) in currencies}
    out.append(("Great Rift weekly tiers, a week",
                sum(_pays(r, i) for r in tiers for i in named),
                f"{len(tiers)} tiers, in {', '.join(sorted(named))}: the "
                f"table is every season's"))
    out.append(("(the week's top score, in points)",
                game_client._figure(seasons[season].get("max_clear_score"))
                or 0, "not a payout"))
    return item, out


# Each rescue pool of `gacha_history`'s, by the banner type the client
# names it under (`gacha_type@gacha_type`).
POOL_TYPES = {
    "pickup_combatant": "gacha_type_pickup_combatant",
    "pickup_supporter": "gacha_type_pickup_supporter",
    "pickup_combatant_rerun": "gacha_type_genal_p_combatant",
    "pickup_supporter_rerun": "gacha_type_genal_p_supporter",
    "general": "gacha_type_general",
    "general_supporter": "gacha_type_general_supporter",
    "card_factor": "gacha_type_card_factor",
    "partner_reform": "gacha_type_partner_reform",
    "first_select": "gacha_type_first_select",
}

# The client's words for what `game_data` spells its own way: the
# reader's own maps, so the audit and the program read alike. A
# class's name in the text goes over CLASSES (`game_client.class_names`).
CLASSES = game_client.CLASS_NAMES
ATTRIBUTES = game_client.ATTRIBUTE_NAMES
GRADES = game_client.COMBATANT_GRADES
# A combatant's stats at level 60: its level-1 stat, every level's step
# up to it, and the five promotions on the way.
AUDIT_LEVEL = 60
ABOVE_AUDIT_LEVEL = (61, 62)
PROMOTIONS = 5
STATS = (("base_atk", "s_atk", "S_ATK"), ("base_def", "s_def", "S_DEF"),
         ("base_hp", "s_hp", "S_HP"))
NUMBER = re.compile(r"\d+(?:\.\d+)?")
PASSIVE_TEXT = re.compile(r"partner_passive@description@(\d+)_c\d+_lv(\d+)")


def _steps(rows, group, upto, key):
    """{stat id: the sum of every step `rows` give `group` up to `upto`}
    -- a level table or a promotion table, both three stats a row."""
    out = {}
    for row in rows:
        if row.get("group") == group and 1 <= int(row.get(key) or 0) <= upto:
            for i in (1, 2, 3):
                stat = row.get(f"stat{i}_link_stat_list_id")
                out[stat] = out.get(stat, 0) + int(row.get(f"stat{i}_value")
                                                   or 0)
    return out


def _plain(value):
    """`value` with the client's typographic apostrophe written as the
    plain one `game_data` types: the same word, spelt two ways."""
    return value.replace(chr(0x2019), "'") if isinstance(value, str) \
        else value


def _numbers(text):
    """The figures in a passage, markup aside, as sorted floats. A
    keyword's level (`$Name#level$`) is not one of them."""
    return sorted(float(n) for n in
                  NUMBER.findall(game_client.passage(text)))


def _figures(numbers):
    """Sorted figures as a passage would print them."""
    return "[" + " ".join(f"{n:g}" for n in numbers) + "]"


def audit(client):
    """Lines saying where `game_data`'s hand tables and `client`
    disagree: the tables as typed, not with the client's facts laid over
    them (`game_data.client_overlay`), which would agree with anything.
    What `--ship` wrote from the client is left out (`client_sync`): an
    entry it fills whole, and a value marked `# client-based`."""
    from game_data import client_sync
    from game_data.characters import table_stats_at_level
    from game_data.client_overlay import hand
    CHARACTERS, PARTNERS = hand("CHARACTERS"), hand("PARTNERS")
    marked_c = client_sync.marked("CHARACTERS")
    marked_p = client_sync.marked("PARTNERS")
    marked_s = client_sync.marked("PARTNER_CLASS_STATS")
    texts = client.text()
    combat = {r["id"]: r for r in client.rows("char_base@char_combatant")}
    base = {r["id"]: r for r in client.rows("char_base@char_base")}
    levels = client.rows("char_base@combatant_level")
    ascends = client.rows("char_base@combatant_ascend")
    derived = game_client.combatants(client)
    derived_partners = game_client.partners(client)
    classes = {**CLASSES, **game_client.class_names(client)}
    out = []
    marks = {}

    def differ(who, field, ours, theirs):
        # `field` reads `base_atk at 60` where it is a figure at a level:
        # the mark is on its first word.
        if field.split(" ")[0] not in marks:
            _differ_into(out, who, field, ours, theirs)

    for rid, ours in sorted((r, c) for r, c in CHARACTERS.items()
                            if isinstance(r, int) and r > 0
                            and isinstance(c, dict)):
        row = combat.get(str(rid))
        who = f"combatant {rid} {ours.get('name')}"
        if row is None:
            out.append(f"{who}: not in the client")
            continue
        if ours.get(client_sync.FROM_CLIENT):
            continue
        marks = marked_c.get(rid, {})
        differ(who, "name", ours.get("name"),
               texts.get(f"char_base@name@{rid}"))
        differ(who, "grade", ours.get("grade"),
               GRADES.get(base.get(str(rid), {}).get("rarity")))
        differ(who, "class", ours.get("class"),
               classes.get(row["link_base_class_define_id"]))
        differ(who, "attribute", ours.get("attribute"),
               ATTRIBUTES.get(row["link_ego_type_id"]))
        stepped = _steps(levels, row["link_combatant_level_group"],
                         AUDIT_LEVEL, "level")
        promoted = _steps(ascends, row["link_combatant_ascend_group"],
                          PROMOTIONS, "ascend")
        for field, start, stat in STATS:
            differ(who, f"{field} at {AUDIT_LEVEL}", ours.get(field),
                   int(row[start]) + stepped.get(stat, 0)
                   + promoted.get(stat, 0))
        # Past 60, the level steps the client also holds, against what
        # the tables add there (`table_stats_at_level`).
        for level in ABOVE_AUDIT_LEVEL:
            past = _steps(levels, row["link_combatant_level_group"],
                          level, "level")
            table = table_stats_at_level(ours, level)
            for field, start, stat in STATS:
                differ(who, f"{field} at {level}", table[field],
                       int(row[start]) + past.get(stat, 0)
                       + promoted.get(stat, 0))
        differ(who, "base_crit_rate", ours.get("base_crit_rate"),
               float(row["s_cri"]))
        differ(who, "base_crit_dmg", ours.get("base_crit_dmg"),
               float(row["s_cri_dmg_rate"]))
        # Node 50's and 60's stat, as the program reads them laid over
        # (`game_client.combatants`).
        theirs = derived.get(rid) or {}
        for field in ("node_50", "node_60"):
            differ(who, field, ours.get(field), theirs.get(field))
    marks = {}
    for rid in sorted(combat, key=int):
        if int(rid) not in CHARACTERS and base.get(rid, {}).get(
                "char_use_playable") == "YES":
            out.append(f"combatant {rid} "
                       f"{texts.get(f'char_base@name@{rid}')}: in the "
                       f"client, not in game_data/characters.py")

    out += level_problems(client)
    out += fragment_problems(client)
    out += item_problems(client)
    out += module_problems(client)

    partner = {r["id"]: r for r in client.rows("partner_base@char_partner")}
    cards = {r["id"]: r for r in client.rows("card(partner)@card")}
    # {(partner id, level): its passive's lines}, one line a class.
    passives = {}
    for key, text in texts.items():
        match = PASSIVE_TEXT.fullmatch(key)
        if match:
            passives.setdefault((match.group(1), int(match.group(2))),
                                []).append(text)
    for rid, ours in sorted((r, c) for r, c in PARTNERS.items()
                            if isinstance(r, int) and r > 0
                            and isinstance(c, dict)):
        row = partner.get(str(rid))
        who = f"partner {rid} {ours.get('name')}"
        if row is None:
            out.append(f"{who}: not in the client")
            continue
        if ours.get(client_sync.FROM_CLIENT):
            continue
        marks = marked_p.get(rid, {})
        differ(who, "name", ours.get("name"),
               texts.get(f"char_base@name@{rid}"))
        differ(who, "class", ours.get("class"), classes.get(
            row["passive_condition_link_base_class_define_id"]))
        differ(who, "passive_name", ours.get("passive_name"),
               texts.get(f"partner_passive@name@{rid}"))
        card = cards.get(row["link_card_id"], {})
        differ(who, "ego_name", ours.get("ego_name"),
               texts.get(card.get("name")))
        differ(who, "ego_cost", ours.get("ego_cost"),
               int(card["cost"]) if card.get("cost") else None)
        # The passive's plain stat lines and the level-60 flat stats, as
        # the program reads them laid over (`game_client.partners`).
        theirs = derived_partners.get(int(rid)) or {}
        for stat, steps in sorted((theirs.get("stats") or {}).items()):
            differ(who, f"stats {stat}",
                   tuple((ours.get("stats") or {}).get(stat, ())), steps)
        if (ours.get("grade"), ours.get("class")) not in marked_s:
            differ(who, "level-60 stats (PARTNER_CLASS_STATS)",
                   hand("PARTNER_CLASS_STATS").get((ours.get("grade"),
                                                     ours.get("class"))),
                   theirs.get("level_60"))
        values = {key: steps for key, steps
                  in (ours.get("values") or {}).items()
                  if isinstance(steps, (list, tuple))}
        # The figures each level's text holds, ours with the values put
        # in, against the client's every line for that level: one line
        # for the partner, naming the levels that differ.
        apart = []
        for level in range(1, 1 + max(map(len, values.values()),
                                      default=0)):
            said = (ours.get("passive_desc") or "")
            for key, steps in values.items():
                if len(steps) >= level:
                    said = said.replace("{%s}" % key, str(steps[level - 1]))
            theirs = " ".join(passives.get((str(rid), level), ()))
            if _numbers(said) != _numbers(theirs):
                apart.append((level, _numbers(said), _numbers(theirs)))
        if apart and not {"passive_desc", "values"} & set(marks):
            level, here, there = apart[0]
            out.append(
                f"{who}: passive figures differ at level"
                f"{'s' if len(apart) > 1 else ''} "
                f"{', '.join(str(a[0]) for a in apart)}; at {level} "
                f"{_figures(here)} here, {_figures(there)} in the client")
    marks = {}
    for rid in sorted(partner, key=int):
        if int(rid) not in PARTNERS:
            out.append(f"partner {rid} "
                       f"{texts.get(f'char_base@name@{rid}')}: in the "
                       f"client, not in game_data/partners.py")
    # A 5-star's signature partner is the one the game recommends for it
    # (`client_sync.pairings`); a 4-star's exception is the maintainer's
    # own choice, so it is no disagreement.
    from game_data.partners import SIGNATURE_PARTNERS
    marked_sig = client_sync.marked("SIGNATURE_PARTNERS")
    recommended = game_client.recommended_partners(client)
    for rid, ours in sorted((r, c) for r, c in CHARACTERS.items()
                            if isinstance(r, int) and isinstance(c, dict)):
        name, held = ours.get("name"), SIGNATURE_PARTNERS.get(ours.get("name"))
        theirs = (PARTNERS.get(recommended.get(rid)) or {}).get("name")
        if ours.get("grade") == 5 and held and theirs and held != theirs \
                and name not in marked_sig:
            out.append(f"combatant {rid} {name}: SIGNATURE_PARTNERS pairs "
                       f"it with {held}, the client recommends {theirs}")

    # The client's item names go over the program's own, so a name that
    # differs is one of the program's tables gone stale. Its tables
    # alone (`hand_item_names`): `item_names` holds the shipped table's
    # names too, which are an older build's reading of the client.
    from game_data.constants import hand_item_names
    theirs = game_client.item_names(client)
    for rid, name in sorted(hand_item_names().items()):
        if rid in theirs:
            differ(f"item {rid}", "name", name, theirs[rid])

    # The client's names for a Chaos and a Zero System special go over
    # the program's own, which name what no client read holds. A
    # rescue's pool keeps the program's label (the maintainer's, from
    # the Probabilities notices), so only the client renaming it is said
    # (`client_changes`).
    import chaos_estimate
    for stage, (name, season) in sorted(game_client.chaos_names(client).items()):
        held = chaos_estimate.CHAOS_NAMES.get(stage)
        if held is None:
            out.append(f"Chaos {stage} {name!r}: in the client, not in "
                       f"chaos_estimate.CHAOS_NAMES (the client's name shows)")
            continue
        differ(f"Chaos {stage}", "name", held[0], name)
        differ(f"Chaos {stage}", "season", held[1], season)
    for special, name in sorted(game_client.zero_specials(client).items()):
        if special not in chaos_estimate.ZERO_SPECIALS:
            out.append(f"Zero System special {special} {name!r}: in the "
                       f"client, not in chaos_estimate.ZERO_SPECIALS (the "
                       f"client's name shows)")
        else:
            differ(f"Zero System special {special}", "name",
                   chaos_estimate.ZERO_SPECIALS[special], name)

    effects = game_client.set_effects(client)
    out += set_problems(effects)
    out += unlisted_sets(effects)
    out += client_changes(client, derived_partners)
    out += potential_7_problems(client)
    out += node_51_problems(client)
    out += limit_problems(client)
    return out


def limit_problems(client):
    """Lines naming each of the Checklist's maximums the client states
    otherwise, over every id the client holds
    (`checklist_tab.limit_mismatches` with no snapshot): the tab reads
    the client's, and the constant wants updating."""
    from ui.tabs import checklist_tab
    try:
        game_client.use({"limits": game_client.limits(client)})
        return [f"Checklist {line}"
                for line in checklist_tab.limit_mismatches()]
    finally:
        game_client.use(None)


# The column naming a combatant's own Affinity rows, beside the group
# they all share. They hold special rewards; a stat in one is what
# FRIENDSHIP_BONUSES, one table for every combatant, cannot hold.
OWN_AFFINITY_ROWS = "extend_link_combatant_friendship_bonus_id"


def level_problems(client):
    """Where the exp and Affinity tables as typed (`game_data.constants`)
    and the client's disagree: a level reached at another exp, a level
    only one side has, and what the program could not hold -- a kind
    whose grades level apart, or a combatant's own Affinity row that
    adds a stat."""
    from game_data.client_overlay import EXP_TABLES, hand
    out = []
    columns = game_client.exp_columns(client)
    tables = game_client.exp_tables(client)
    for kind, name in EXP_TABLES.items():
        theirs = tables.get(kind)
        if theirs is None:
            unread = [column for column in game_client.EXP_COLUMNS[kind]
                      if not columns.get(column)]
            out.append(f"{name}: not read off the client, whose grades' "
                       f"columns disagree (unreadable: {unread or 'none'}); "
                       f"the hand table stands")
            continue
        ours = {level: exp for exp, level in hand(name)}
        for level, exp in sorted(ours.items()):
            if level > len(theirs):
                out.append(f"{name}: level {level} at {exp} here, past the "
                           f"client's top level, {len(theirs)}")
            elif theirs[level - 1] != exp:
                out.append(f"{name}: level {level} is reached at {exp} here, "
                           f"{theirs[level - 1]} in the client")
        top = max(ours)
        if len(theirs) > top:
            beyond = ", ".join(f"{level} at {theirs[level - 1]}"
                               for level in range(top + 1, len(theirs) + 1))
            out.append(f"{name}: the client's levels past this table's top, "
                       f"{top}: {beyond}")

    held = game_client.affinity(client)
    for name, key in (("AFFINITY_TO_NEXT", "to_next"),
                      ("FRIENDSHIP_BONUSES", "bonuses")):
        theirs = held.get(key)
        if theirs is None:
            out.append(f"{name}: not read off the client (a level missing, "
                       f"or its combatants name more than one bonus group); "
                       f"the hand table stands")
            continue
        if key == "to_next":
            ours = hand(name)
        else:
            ours = {row[0]: tuple(row[1:]) for row in hand(name)}
            theirs = {row[0]: tuple(row[1:]) for row in theirs}
        apart = [(level, ours.get(level), theirs.get(level))
                 for level in sorted(set(ours) | set(theirs))
                 if ours.get(level) != theirs.get(level)]
        if apart:
            out.append(f"{name}: {len(apart)} level(s) differ; at "
                       f"{apart[0][0]} {apart[0][1]} here, {apart[0][2]} in "
                       f"the client")

    rows = {r.get("id"): r
            for r in client.rows(game_client.AFFINITY_BONUS_TABLE)}
    for combatant in client.rows("char_base@char_combatant"):
        for own in str(combatant.get(OWN_AFFINITY_ROWS) or "") \
                .strip("[]").split(","):
            row = rows.get(own.strip()) or {}
            if any(game_client.PARTNER_FLAT_STATS.get(
                    row.get(f"stat{i}_link_stat_list_id"))
                   and (game_client._figure(row.get(f"stat{i}_value")) or 0) > 0
                   for i in range(3)):
                out.append(f"combatant {combatant.get('id')}: its own "
                           f"Affinity row {own.strip()} adds a stat, which "
                           f"FRIENDSHIP_BONUSES holds for every combatant "
                           f"alike")
    return out


def _decimals(figure):
    """How many decimals `figure` is typed with."""
    text = repr(figure)
    return len(text.split(".")[1]) if "." in text else 0


def fragment_problems(client):
    """Where the Memory Fragment tables as typed (`game_data.constants`)
    and the client's disagree: a slot's main stats, a main stat's
    Legendary ceiling as the game draws it, a substat's roll bounds, a
    rarity's top level; and the substats' draw weights (`SUBSTAT_DRAW`,
    which the client's replace)."""
    from game_data.client_overlay import hand
    from game_data.constants import MAIN_STAT_VALUES, MAX_LEVEL_PER_RARITY
    STATS = hand("STATS")
    held = game_client.fragment_stats(client)
    names = {stat: info[0] for stat, info in STATS.items()}
    ours, top, out = hand("SLOT_MAIN_STATS"), held["max_levels"].get(4), []
    for slot, options in sorted(held["mains"].items()):
        theirs = [names.get(stat, stat) for stat, _start, _step in options]
        if set(theirs) != set(ours.get(slot, ())):
            out.append(f"slot {slot}: main stats {ours.get(slot)} here, "
                       f"{theirs} in the client")
        for stat, start, step in options:
            typed = MAIN_STAT_VALUES.get((slot, names.get(stat, stat)))
            ceiling = start + (top or 0) * step
            if typed is None or round(ceiling, _decimals(typed)) != typed:
                out.append(f"slot {slot} {names.get(stat, stat)}: a maxed "
                           f"Legendary's main is {typed} here (the game "
                           f"draws it rounded), {ceiling:g} in the client")
    for stat, rolls in held["rolls"].items():
        info = STATS.get(stat)
        if not info or info[3] <= 0:
            out.append(f"substat {stat}: rolls {rolls} in the client, which "
                       f"STATS has no roll for")
        elif (info[4], info[3]) != (min(rolls), max(rolls)):
            out.append(f"substat {info[0]}: rolls {info[4]} to {info[3]} "
                       f"here, {min(rolls)} to {max(rolls)} in the client")
    for stat, info in STATS.items():
        if info[3] > 0 and stat not in held["rolls"]:
            out.append(f"substat {info[0]}: rolls here, and is no substat "
                       f"in the client")
    for tier, level in sorted(MAX_LEVEL_PER_RARITY.items()):
        if held["max_levels"].get(tier) != level:
            out.append(f"rarity {tier}: top level {level} here, "
                       f"{held['max_levels'].get(tier)} in the client")
    ours = hand("SUBSTAT_DRAW")
    for stat in sorted(set(ours) | set(held["draws"])):
        if ours.get(stat) != held["draws"].get(stat):
            out.append(f"substat {names.get(stat, stat)}: drawn new at "
                       f"weight {ours.get(stat)} here (SUBSTAT_DRAW), "
                       f"{held['draws'].get(stat)} in the client")
    return out


def module_problems(client):
    """A Time-Limited Command Delegation Module the client holds that
    `period_items.MODULE_ITEMS` does not name. It is counted in the
    Checklist's module rows and the Materials tab's icons all the same
    (`period_items.module_items`); the line asks the maintainer to
    approve that by naming it there, or to treat it otherwise."""
    import period_items
    names = game_client.item_names(client)
    rules = game_client.period_items(client)
    out = []
    for res_id, rule in sorted(rules.items()):
        if (res_id not in period_items.MODULE_ITEMS
                and rule[0] != period_items.NOT_A_MODULE_CLOCK
                and period_items.MODULE_NAME.search(names.get(res_id, ""))):
            out.append(
                f"item {res_id} {names[res_id]!r}: a Delegation Module the "
                f"program does not know ({rule[0]}, {rule[1]} days), "
                f"counted with the others in the Checklist's Delegation "
                f"Module rows and the Materials tab -- add it to "
                f"period_items.MODULE_ITEMS to keep that")
    return out


def item_problems(client):
    """Where the classes, the item tables' art and the shops' names as
    typed disagree with the client's: a class either side lacks, or in
    another order than the Materials tab's; an item's rarity or icon;
    a tracked shop whose name holds none of the game's for it (the
    program's own goes over it, as with the Chaos names)."""
    from game_data import constants
    from game_data.constants import ITEM_TABLES, table_art
    import shop_stock
    from ui.tabs.materials_tab import CLASS_ORDER
    out = []
    classes = game_client.class_names(client)
    if set(classes.values()) != set(constants.CLASSES):
        out.append(f"classes: {sorted(constants.CLASSES)} here, "
                   f"{sorted(classes.values())} in the client")
    elif tuple(classes.values()) != tuple(CLASS_ORDER):
        out.append(f"classes: the Materials tab lists {CLASS_ORDER}, the "
                   f"game {tuple(classes.values())}")
    rarities = game_client.item_rarities(client)
    icons = {}
    for path in client.archive.files:
        if path.startswith("db/item_") and path.endswith("@item.db"):
            icons.update({r.get("id"): r.get("icon")
                          for r in client.rows(path[3:-3])})
    for table in ITEM_TABLES:
        for res_id in table:
            art = table_art(res_id)
            if art is None:
                continue
            _differ_into(out, f"item {res_id}", "rarity", art.rarity,
                         rarities.get(res_id))
            if art.icon:
                _differ_into(out, f"item {res_id}", "icon",
                             Path(art.icon).stem, icons.get(str(res_id)))
    # A shop's name is the program's; only one the client no longer has
    # is said here, and one it renames by `client_changes`.
    names = shop_names(client)
    for (cat, sub), ours in sorted(shop_stock.SHOPS.items()):
        if f"shop {cat}/{sub}" not in names:
            out.append(f"shop {cat}/{sub} {ours!r}: not in the client")
    return out


def shop_names(client):
    """{`shop <category>/<sub>`: the client's name for it} for every shop
    `shop_stock.SHOPS` names, its category's and sub-category's names
    joined; a shop the client has neither row for is left out."""
    import shop_stock
    texts = client.text()
    cats = {r["id"]: r for r in client.rows("shop_category@shop_category")}
    subs = {r["id"]: r
            for r in client.rows("shop_category@shop_sub_category")}
    out = {}
    for cat, sub in shop_stock.SHOPS:
        rows = [(row, column) for row, column in (
            (cats.get(cat), "main_category_name"),
            (subs.get(sub), "sub_category_name")) if row]
        if rows:
            out[f"shop {cat}/{sub}"] = " - ".join(
                name for name in (_plain(game_client.clean(texts.get(
                    row.get(column)))) for row, column in rows) if name)
    return out


def client_words(client, partners=None):
    """{"ego": {partner res_id: its Ego text}, "names": {what: the
    client's name}}: the client's own words for what the program's
    tables decide -- the partners' Ego texts (`game_client.ego_text`),
    and the names of the Rescue pools and shops the program names its
    own way. The sets' are `SET_EFFECTS`. What `--ship` keeps, and what
    a newer client is held to (`word_changes`)."""
    texts = client.text()
    partners = game_client.partners(client) if partners is None else partners
    types = {r["id"]: game_client.clean(texts.get(r.get("name")))
             for r in client.rows("gacha_type@gacha_type")}
    names = {f"rescue pool {pool}": types[kind]
             for pool, kind in POOL_TYPES.items() if types.get(kind)}
    names.update(shop_names(client))
    return {"ego": {rid: fact["ego_desc"] for rid, fact in partners.items()
                    if fact.get("ego_desc")},
            "names": names}


def word_changes(before, after):
    """Lines naming each Ego text and name `after` gives otherwise than
    `before` (both as `client_words` gives them, `before` the copy the
    program shipped). The program's own stands: a partner whose entry
    `--ship` writes takes the new text by itself, so only a hand entry's
    is said."""
    from game_data import client_sync
    from game_data.client_overlay import hand
    partners = hand("PARTNERS")
    out = []
    old, new = before.get("ego") or {}, after.get("ego") or {}
    for rid in sorted(set(old) & set(new)):
        ours = partners.get(rid) or {}
        if old[rid] != new[rid] and isinstance(ours, dict) \
                and not ours.get(client_sync.FROM_CLIENT):
            out.append(f"partner {rid} {ours.get('name')}: the client's Ego "
                       f"text moved from {old[rid]!r} to {new[rid]!r} "
                       f"(ego_desc stands)")
    old, new = before.get("names") or {}, after.get("names") or {}
    for what in sorted(set(old) & set(new)):
        if old[what] != new[what]:
            out.append(f"{what}: the client renamed it {old[what]!r} to "
                       f"{new[what]!r} (the program's name stands)")
    return out


def client_changes(client, partners=None):
    """Lines naming everything the program's tables decide that `client`
    gives otherwise than the copy the program shipped: its sets
    (`set_changes`), the partners' Ego texts and the pools' and shops'
    names (`word_changes`). Empty for the build the copy came from."""
    from game_data import from_client
    shipped = {"ego": getattr(from_client, "EGO_TEXTS", {}),
               "names": getattr(from_client, "CLIENT_NAMES", {})}
    return (set_changes(from_client.SET_EFFECTS,
                        game_client.set_effects(client))
            + word_changes(shipped, client_words(client, partners)))


def _differ_into(out, who, field, ours, theirs):
    """A line added to `out` where `ours` and `theirs` disagree, the
    client's typographic apostrophe read as the plain one."""
    if _plain(ours) != _plain(theirs):
        out.append(f"{who}: {field} is {ours!r} here, {theirs!r} in the "
                   f"client")


# The client's stat ids for the plain stats a set's `stat` names.
SET_STATS = {"S_ATK_INC_RATE_OUT": "ATK%", "S_DEF_INC_RATE_OUT": "DEF%",
             "S_HP_INC_RATE_OUT": "HP%",
             "S_CRI_DMG_RATE_INC_ADD": "Crit DMG",
             "S_CRI_INC_ADD": "Crit Rate"}


def set_problems(effects, typed=None):
    """Lines naming each set of `game_data/sets.py` (or `typed`) that
    `effects`, the client's sets as `game_client.set_effects` gives
    them, lacks; `unlisted_sets` names the ones `sets.py` lacks. An
    entry's name, pieces, model and wording are the maintainer's and go
    over the client's, so none is held to it: `set_changes` says where a
    client changes them."""
    from game_data import SETS
    return [f"set {set_id} {ours.get('name')}: not in the client"
            for set_id, ours in sorted((typed or SETS).items())
            if set_id not in effects]


def unlisted_sets(effects):
    """Lines naming each of the client's sets `game_data/sets.py` lacks.
    The program shows it in the game's name and words, and the optimizer
    cannot weigh it."""
    from game_data import SETS
    return [f"set {set_id} {effects[set_id][0]}: in the client, not in "
            f"game_data/sets.py" for set_id in sorted(set(effects) - set(SETS))]


def set_changes(before, after):
    """Lines naming each set `after` gives otherwise than `before`
    (both as `game_client.set_effects` gives them, `before` the copy the
    program shipped): a new name, piece count or plain stat, or new words
    -- and whether only their figures moved, when the maintainer's
    wording wants new figures, or the words did, when it wants
    rewording. The program's entry stands either way."""
    from game_data import SETS
    out = []
    for set_id in sorted(set(before) & set(after)):
        was, now = before[set_id], after[set_id]
        who = f"set {set_id} {(SETS.get(set_id) or {}).get('name') or now[0]}"
        if was[0] != now[0]:
            out.append(f"{who}: the client renamed it {was[0]!r} to "
                       f"{now[0]!r} (the program's name stands)")
        if was[1] != now[1]:
            out.append(f"{who}: the client's pieces moved from {was[1]} to "
                       f"{now[1]}")
        if tuple(was[3:5]) != tuple(now[3:5]):
            out.append(f"{who}: the client's plain stat moved from "
                       f"{SET_STATS.get(was[3], was[3])} {was[4]} to "
                       f"{SET_STATS.get(now[3], now[3])} {now[4]}")
        old, new = was[2], now[2]
        if old == new:
            continue
        if NUMBER.sub("#", old) == NUMBER.sub("#", new):
            out.append(f"{who}: only its figures moved, "
                       f"{_figures(_numbers(old))} to "
                       f"{_figures(_numbers(new))}: {new!r}")
        else:
            out.append(f"{who}: reworded, from {old!r} to {new!r}")
    return out


# A node 7 effect's stat ids, in `potential_7.py`'s words: what it
# grants, and what its check reads. An attribute's damage is Element%.
NODE_GRANTS = {"S_ATK_INC_RATE_OUT": "ATK%", "S_DEF_INC_RATE_OUT": "DEF%",
               "S_CRI_INC_ADD": "CRate", "S_CRI_DMG_RATE_INC_ADD": "CDmg",
               "S_ADDI_ATK_DMG_RATE_INC_ADD": "Extra DMG%",
               "S_WEAK_EGO_DMG_RATE": "weakness"}
NODE_ELEMENT = re.compile(r"S_([A-Z]+)_DMG_RATE_INC_ADD")
NODE_CHECKS = {"S_ATK": "ATK", "S_DEF": "DEF", "S_HP": "HP", "S_CRI": "CRate",
               "S_CRI_DMG_RATE": "CDmg", "S_ADDI_ATK_DMG_RATE": "Extra DMG%",
               "S_DOT_ATK_DMG_RATE": "DoT%", "S_CHARGING_POWER": "Ego"}
# How a node effect row applies: a stat always, a stat once a check
# passes, a card's figures once it passes, or an in-battle effect whose
# figures are in another table (so only its check is compared).
NODE_STAT, NODE_CHECKED, NODE_CARD, NODE_BATTLE = (
    "NODE_STAT_ADD", "NODE_STAT_ADD_ANOTHER_STAT",
    "NODE_STAT_ADD_SKILL_EFF_VALUE", "NODE_CS_ADD")


def _node_effects(rows, attribute):
    """A live node 7's effect rows as `potential_7` states effects:
    [{grants, check, at, value, rate, most}]. A row past its check's
    threshold grants its limit; one using the EXCESS grants value/100
    for each point past it, up to its limit, and is folded into the
    plain row of the same check as that row's growth. `grants` is None
    for an in-battle effect, which may be any."""
    found = {}
    for row in rows:
        kind = row.get("node_type")
        stat = row.get("link_stat_list_id") or ""
        element = NODE_ELEMENT.fullmatch(stat)
        if kind == NODE_CARD:
            grants = "card"
        elif kind == NODE_BATTLE:
            grants = None
        elif element and element.group(1) in ATTRIBUTES:
            grants = "Element%" if ATTRIBUTES[element.group(1)] \
                == attribute else f"{ATTRIBUTES[element.group(1)]}%"
        else:
            grants = NODE_GRANTS.get(stat, stat)
        at = game_client._figure(row.get("stat_check_threshold")) or None
        check = NODE_CHECKS.get(row.get("check_link_stat_list_id")) \
            if at else None
        key = (grants, check, at)
        effect = found.setdefault(key, {"grants": grants, "check": check,
                                        "at": at, "value": None,
                                        "rate": None, "most": None})
        value = game_client._figure(row.get("value"))
        limit = game_client._figure(row.get("stat_add_limit"))
        if kind == NODE_STAT:
            effect["value"] = value
        elif kind == NODE_BATTLE:
            pass
        elif row.get("stat_check_use_excess") == "TRUE":
            effect["rate"], effect["most"] = value / 100, limit
            if effect["value"] is None:
                effect["value"] = 0
        else:
            effect["value"] = limit
    return list(found.values())


def _program_effects(effects):
    """`potential_7.py`'s effects in `_node_effects`' shape, an any-of
    check standing as one effect per stat it reads."""
    from game_data.potential_7 import conditions
    out = []
    for effect in effects:
        rate = effect["add"] / effect["per"] if effect.get("per") else None
        for check, at in conditions(effect) or ((None, None),):
            out.append({"grants": effect["grants"], "check": check,
                        "at": at, "value": effect["value"], "rate": rate,
                        "most": effect.get("max")})
    return out


def _same_effect(ours, theirs):
    """Whether a program effect and a client one say the same; where
    the client's grants or value is in another table, those aside."""
    if (ours["check"], ours["at"]) != (theirs["check"], theirs["at"]):
        return False
    if theirs["grants"] is None:
        return True
    if ours["grants"] != theirs["grants"]:
        return False
    return all(theirs[k] is None or abs((ours[k] or 0) - theirs[k]) < 1e-9
               for k in ("value", "rate", "most"))


def _effect_words(effect):
    """One effect as a short phrase, for a report line."""
    words = f"{effect['grants'] or 'an in-battle effect'}"
    if effect["value"] is not None:
        words += f" {effect['value']:g}"
    if effect["check"]:
        words += f" at {effect['check']} {effect['at']:g}"
    if effect["rate"]:
        words += f", +{effect['rate']:g} a point past it to {effect['most']:g}"
    return words


def _shown_words(rid, wire, raw, who, out):
    """A node's text as the Combatants tab shows it, `TEXT_FIXES`
    applied. A fix whose words the text no longer holds is a patch
    having rewritten it, and goes in `out` with what to do."""
    from game_data.potential_7 import TEXT_FIXES
    words = game_client.passage(raw)
    for wrong, right in TEXT_FIXES.get((rid, wire), ()):
        if wrong not in words:
            out.append(
                f"{who}: a patch rewrote the text TEXT_FIXES corrects. It "
                f"no longer holds {wrong!r}, and reads {words!r}. If it "
                f"now states the data's figures, the patch corrected it: "
                f"delete the fix in game_data/potential_7.py. If not, the "
                f"text and the data disagree anew, and a battle settles "
                f"which the server uses (tasks.md, I36)")
        words = words.replace(wrong, right)
    return words


def node_51_problems(client):
    """Lines naming each node 5.1 whose text does not state its data's
    figures -- the flat bonus, the threshold, the bonus past it -- and
    a stale `TEXT_FIXES` entry. The program prices no node 5.1; its
    text is what the Combatants tab's tooltip shows. An in-battle
    effect's figures are in another table, and only its threshold is
    held."""
    from game_data import CHARACTERS
    effect_rows = {r["id"]: r for r
                   in client.rows(game_client.NODE_EFFECT_TABLE)}
    texts = client.text()
    out = []
    for (rid, num), node in sorted(game_client.live_nodes(client).items()):
        char = CHARACTERS.get(rid)
        if num != "5_1" or not isinstance(char, dict):
            continue
        who = f"combatant {rid} {char.get('name')}: node 5.1"
        words = _shown_words(rid, 51, texts.get(node.get("desc")), who, out)
        links = (node.get("link_potential_node_effect_id") or "")
        rows = [effect_rows[k] for k in links.strip("[]").split(",")
                if k in effect_rows]
        stated = {float(n) for e in _node_effects(rows, char.get("attribute"))
                  for n in (e["value"], e["at"], e["most"])
                  if isinstance(n, (int, float)) and n}
        missing = stated - set(_numbers(words))
        if missing:
            out.append(f"{who}: the data's {_figures(sorted(missing))} are "
                       f"not in its text: {words!r}. A TEXT_FIXES entry in "
                       f"game_data/potential_7.py puts them in the tooltip")
    return out


def potential_7_problems(client, to_write=None):
    """Lines saying where `potential_7.py` and the client's node 7s
    disagree: an effect one side states and the other does not, the
    figures `potential_7.py` holds that the game's text never states,
    a `TEXT_FIXES` entry whose words the text no longer holds, and a
    combatant either side lacks. The data is the source; the text is
    compared as the Combatants tab shows it, its fixes applied.

    A combatant whose entry `--ship` wrote from the client
    (`client_sync`) and that has no node 7 goes to `to_write` where one
    is given: an entry still to write, not one typed wrong."""
    from game_data import CHARACTERS
    from game_data.potential_7 import POTENTIAL_7
    effect_rows = {r["id"]: r for r
                   in client.rows(game_client.NODE_EFFECT_TABLE)}
    texts = client.text()
    nodes = {rid: row for (rid, num), row
             in game_client.live_nodes(client).items() if num == "7_0"}
    out = []
    for rid in sorted(set(nodes) | set(POTENTIAL_7)):
        char = CHARACTERS.get(rid)
        name = char.get("name") if isinstance(char, dict) else "?"
        who = f"combatant {rid} {name}: Potential 7"
        if rid not in nodes:
            out.append(f"{who} is not in the client")
            continue
        node = nodes[rid]
        words = _shown_words(rid, 70, texts.get(node.get("desc")), who, out)
        if rid not in POTENTIAL_7:
            if isinstance(char, dict):
                written = to_write is not None and char.get("from_client")
                (to_write if written else out).append(
                    f"{who} is in the client, not in "
                    f"game_data/potential_7.py: {words!r}")
            continue
        links = (node.get("link_potential_node_effect_id") or "")
        rows = [effect_rows[k] for k in links.strip("[]").split(",")
                if k in effect_rows]
        theirs = _node_effects(rows, char.get("attribute"))
        ours = _program_effects(POTENTIAL_7[rid])
        apart_ours = [e for e in ours
                      if not any(_same_effect(e, t) for t in theirs)]
        apart_theirs = [t for t in theirs
                        if not any(_same_effect(e, t) for e in ours)]
        if apart_ours or apart_theirs:
            out.append(
                f"{who}: here "
                f"{'; '.join(map(_effect_words, apart_ours)) or 'nothing'}"
                f", in the client's data "
                f"{'; '.join(map(_effect_words, apart_theirs)) or 'nothing'}"
                f". Its text: {words!r}")
        said = set(_numbers(words))
        held = {float(n) for e in POTENTIAL_7[rid] for n in
                (e.get("value"), e.get("per"), e.get("add"), e.get("max"),
                 *(e.get("at") if isinstance(e.get("at"), tuple)
                   else (e.get("at"),)))
                if isinstance(n, (int, float)) and n}
        if held - said:
            out.append(f"{who}: {_figures(sorted(held - said))} here are "
                       f"not in its text: {words!r}. Where the data "
                       f"states them, a TEXT_FIXES entry in "
                       f"potential_7.py puts them in the tooltip")
    return out


def main(argv=None):
    # The text holds characters a cp932 console cannot encode, and the
    # failure would land as a UnicodeEncodeError from print().
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--client")
    parser.add_argument("--list", metavar="REGEX")
    parser.add_argument("--table", metavar="NAME")
    parser.add_argument("--text", metavar="REGEX")
    parser.add_argument("--grep", metavar="REGEX")
    parser.add_argument("--season", metavar="SEASON")
    parser.add_argument("--renames", nargs="?", const="previous",
                        metavar="BUILD")
    parser.add_argument("--ship", action="store_true")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--rows", type=int)
    parser.add_argument("--out")
    parser.add_argument("--archive", action="store_true")
    parser.add_argument("--archived", action="store_true")
    parser.add_argument("--from-archive", nargs="?", const="newest",
                        metavar="BUILD")
    args = parser.parse_args(argv)
    folder = client_archive.folder_of(REPO / "Vribbels")
    if args.archived:
        held = client_archive.builds(folder)
        if not held:
            print(f"nothing archived in {folder.relative_to(REPO)}")
            return 0
        sizes = {name: (folder / name).stat().st_size
                 for name in (client_archive.LATEST, client_archive.HISTORY)
                 if (folder / name).exists()}
        print(f"builds {', '.join(map(str, held))}; newest in "
              f"{client_archive.LATEST}, the rest in "
              f"{client_archive.HISTORY}; "
              + ", ".join(f"{name} {size / 1e6:.1f} MB"
                          for name, size in sizes.items()))
        return 0
    if args.from_archive:
        build = None if args.from_archive == "newest" \
            else int(args.from_archive)
        client = client_archive.open_build(folder, build)
        print(f"archived build {client.archive.build}", file=sys.stderr)
    else:
        install = game_client.find_install(args.client)
        if install is None:
            print("no game client found: name one with --client")
            return 1
        client = Client(install)
    archive = client.archive
    if args.archive:
        if args.from_archive:
            print("--archive reads the installed client, not the archive")
            return 1
        print(client_archive.archive(client, folder))
        return 0
    if args.list:
        pattern = re.compile(args.list, re.I)
        for name in sorted(archive.files):
            if pattern.search(name):
                print(name)
    elif args.table:
        columns, rows = client.table(args.table)
        lines = list(_tsv(columns, rows[:args.rows] if args.rows else rows))
        if args.out:
            Path(args.out).write_text("\n".join(lines) + "\n",
                                      encoding="utf-8")
            print(f"{len(rows)} rows to {args.out}")
        else:
            print("\n".join(lines))
    elif args.text:
        pattern = re.compile(args.text, re.I)
        for key, value in client.text().items():
            if pattern.search(key) or pattern.search(value):
                print(f"{key}\t{value}")
    elif args.grep:
        pattern = re.compile(args.grep, re.I)
        stubs, unread = 0, []
        for name in sorted(archive.files):
            if not (name.startswith("db/") and name.endswith(".db")):
                continue
            try:
                columns, rows = client.table(name[3:-3])
            except Exception as exc:                     # noqa: BLE001
                # A file without an `@` is a stub with no rows to it, as
                # `client_archive` finds; a table that fails is news.
                if "@" in name:
                    unread.append(f"{name[3:-3]} ({exc!r})")
                else:
                    stubs += 1
                continue
            for row in rows:
                hits = [f"{c}={row[c]}" for c in columns
                        if pattern.search(row[c])]
                if hits:
                    print("\t".join([name[3:-3], row[columns[0]], *hits]))
        for name in unread:
            print(f"did not read: {name}", file=sys.stderr)
        print(f"{stubs} stub files with no rows skipped", file=sys.stderr)
    elif args.renames:
        held = [b for b in client_archive.builds(folder) if b < archive.build]
        if args.renames != "previous":
            held = [int(args.renames)]
        if not held:
            print(f"no archived build older than {archive.build}")
            return 1
        print("\n".join(renames(client_archive.open_build(folder, held[-1]),
                                client)))
    elif args.season:
        item, terms = season_payouts(client, args.season)
        name = client.text().get(f"item@name@{item}", "?")
        print(f"{args.season} pays in {item} ({name}), build {archive.build}:")
        for words, paid, note in terms:
            print(f"  {words:42} {paid:>8,}  {note}")
    elif args.ship or args.audit:
        # Shipped first, so the audit holds the tables as `--ship` left
        # them: a unit it just added is no disagreement.
        if args.ship:
            from game_data.client_sync import SyncError
            try:
                said = ship(client)
            except SyncError as exc:
                print(f"nothing written: {exc}")
                return 1
            print("\n".join(said) if said else
                  f"already level with build {archive.build}")
            if args.audit and said:
                # This process holds the tables as they were before
                # `--ship` wrote them: the audit reads them afresh.
                sys.stdout.flush()
                again = [sys.executable, __file__, "--audit"]
                again += ["--client", args.client] if args.client else []
                again += ["--from-archive", args.from_archive] \
                    if args.from_archive else []
                return subprocess.call(again)
        if args.audit:
            found = audit(client)
            print("\n".join(found) if found else
                  "game_data agrees with the client")
            print(f"build {archive.build}: {len(found)} disagreement(s)")
    elif args.from_archive:
        tables = sum(1 for n in archive.files if n.startswith("db/"))
        print(f"archived build {archive.build}: {tables} tables, "
              f"{len(client.text())} English texts")
    else:
        installed = sorted({archive.groups[g] for g, spans
                            in archive.streams.items()
                            if all(path for _s, _l, path in spans)})
        tables = sum(1 for n in archive.files if n.startswith("db/"))
        print(f"{install}: build {archive.build}, groups installed: "
              f"{', '.join(installed)}; {len(archive.files)} files, "
              f"{tables} tables, {len(client.text())} English texts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
