"""Everything a deck is made of, as the game client holds it: cards and
their effects and statuses, Signature, Neutral and Divine Epiphanies,
the season mechanics' cards, Equipment and its Buffs, Mutations,
partners, what Potential nodes and Ego Manifestation do to a deck, the
deck point rules and the battle's constants. `docs/decks.md` says which
table holds what.

`read(client)` reads it all off an open client into plain data: what
the cache holds, one file per game build beside `game_client.json`
(`load`, `save`, `for_install`), so only the first read after a patch
opens the client. `Catalogue` wraps that data with the lookups the
model and the rules use, and `problems` is the read checking itself: a
patch that renames or repurposes a column misreads quietly, and these
are the shapes such a misread breaks (plan.md D34).

Nothing Sortie-only is read: its cards, Equipment and Epiphanies never
enter a deck (D59).
"""

import gzip
import json
import os
import re
import tempfile
from pathlib import Path

CATALOGUE_FORMAT = 4
CACHE_FILE = "deck_catalogue.json.gz"

# The tables, as `game_client.Client.table` names them. Sortie's own
# copies, `(assault)`, are left out throughout, and so are its rows in
# the Epiphany table, `assault_r_spark_*`.
CARD_TABLE = re.compile(r"^(?:card\((?P<group>[^)]+)\)|memory_grade_define)@card$")
VERSION_TABLE = re.compile(r"^card\([^)]+\)@card_r_spark$")
EFFECT_TABLE = re.compile(r"@skill_eff$")
STATUS_TABLE = re.compile(r"@cs$")
SORTIE = "(assault)"
SORTIE_EPIPHANY = "assault_"
EQUIPMENT_TABLES = {"relic@relic": "relic", "relic(disaster)@relic": "disaster"}
EPIPHANY_TABLE = "r_spark@r_spark"
POINT_TABLE = "savedata_point_define@savedata_point_define"
COMBATANT_TABLE = "char_base@char_combatant"
UNIT_TABLE = "char_base@char_base"
CONSTANT_TABLE = "constant_metagame@constant_meta"
BUFF_TABLE = "relic_reinforce@relic_reinforce"
MUTATION_TABLE = "savedata_edit_corruption@savedata_edit_corruption"
PERSONA_SLOTS = "eidolon_card_define@eidolon_card_slot_info"
PERSONA_EFFECTS = "eidolon_card_define@eidolon_card_reward"
PERSONA_NAMES = "eidolon_card_define@eidolon_card_illust_comb"
ARCHIVE_TABLE = re.compile(r"^archive_card\([^)]+\)@archive_card$")
PARTNER_TABLE = "partner_base@char_partner"
PARTNER_UNIT_TABLE = "partner_base@char_base"
NODE_TABLE = "potential_node@potential_node"
NODE_EFFECT_TABLE = "potential_node@potential_node_effect"
MANIFESTATION_TABLE = "combatant_limit_break@combatant_limit_break"
# What a Potential node does to a deck: upgrade cards to their `pot`
# version, or put a status on for the battle. Every type the program has
# judged; the others change stats, Epiphany odds and Stress, which no
# deck figure reads. A type a patch adds is reported (`problems`).
NODE_UPGRADE = "NODE_CARD_R_SPARK"
NODE_STATUS = "NODE_CS_ADD"
KNOWN_NODE_TYPES = frozenset({
    NODE_UPGRADE, NODE_STATUS, "NODE_CARD_R_SPARK_UNLOCK",
    "NODE_FIRST_SPARK_CARD_SELECT_UNLOCK", "NODE_FIRST_SPARK_R_CARD_GET_UNLOCK",
    "NODE_REINFORCE_CARD_NEUTRAL", "NODE_REINFORCE_CARD_START",
    "NODE_REINFORCE_CARD_UNIQUE", "NODE_R_SPARK_GOD_ADD", "NODE_R_SPARK_PCT_ADD",
    "NODE_STAT_ADD", "NODE_STAT_ADD_ANOTHER_STAT", "NODE_STAT_ADD_SKILL_EFF_VALUE",
    "NODE_STRESS_GET_DECREASE_PCT"})
# An Ego Manifestation level upgrades cards to their `lbk` version, puts
# a battle status on, or replaces the battle statuses of the levels below
# it; raising Potential nodes' levels changes stats only.
UPGRADE_CARDS = "BREAK_TYPE_CARD_R_SPARK"
BATTLE_STATUS = "BREAK_TYPE_BATTLE_CS_ADD"
OVERWRITE = "BREAK_TYPE_BATTLE_CS_ADD_OVERWRITE"
KNOWN_BREAK_TYPES = frozenset({UPGRADE_CARDS, BATTLE_STATUS, OVERWRITE,
                               "BREAK_TYPE_POTENTIAL_LEVEL_UP", "none"})
# A condition (`@condition`) names a control key, whose rows in
# `@condition_control`, `<key>_<n>`, each test cards, units or a timing
# (`@cond_card`, `@cond_unit`, `@cond_timing`), or say when the count
# resets. Every `condition(<group>)` set is one table set of these.
CONDITION_TABLE = re.compile(
    r"^condition(?:\([^)]+\))?@(condition|condition_control|cond_card"
    r"|cond_unit|cond_timing)$")

# The battle's own figures (`constant_metagame`): a turn's draw and AP,
# and the hand's cap.
CONSTANTS = {"draw": "battle_base_draw_count", "energy": "battle_base_energy",
             "hand_max": "battle_base_hand_max_count"}

# A Signature card table's rows, by their id's first word: the five
# Signature Epiphanies, a Potential node's upgrade, Ego Manifestation's.
VERSION_ID = re.compile(r"^(rsp([1-5])|pot|lbk)_(.+)$")

# Every deck point rule the program prices (`rules`); a row a patch adds
# is one it does not know, and `problems` says so (D63).
KNOWN_POINT_ROWS = frozenset({
    "god_r_spark", "cd_get_taboo", "cd_remove_start", "cd_get_job",
    "cd_get_sort_monster_common", "cd_get_sort_monster_rare",
    "cd_get_sort_monster_legend", "cd_get_sort_monster_unique",
    "cd_transform_default_point", "cd_remove_revise_by_count",
    "cd_copy_revise_by_count", "cd_relic_hammer", "relic_reinforce_lux",
    "relic_reinforce_umbra", "cd_get_eidolon", "relic_reinforce_arena"})

# A value that means nothing set.
EMPTY = ("", "none", "None", "[]", "[none]", "TALENT_NONE", "[TALENT_NONE]")


def _list(value):
    """A table's `[a,b]` cell as ['a', 'b'], `none` entries and
    TALENT_NONE left out."""
    if value is None:
        return []
    items = (part.strip() for part in str(value).strip().strip("[]").split(","))
    return [item for item in items if item and item not in EMPTY]


def _number(value, default=None):
    """A figure as a whole number where it is whole, else a float;
    `default` for anything else."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return int(number) if number.is_integer() else number


def _value(value):
    """A rule's value: a number, a list of numbers, or the text as is."""
    text = str(value).strip()
    if text.startswith("["):
        return [_number(part, part) for part in _list(text)]
    number = _number(text)
    return text if number is None else number


def _compact(row):
    """A row with its empty cells left out: effect and status rows are
    mostly defaults, and the cache holds thousands."""
    return {key: value for key, value in row.items()
            if key != "id" and value not in EMPTY and value is not None}


def _tables(client):
    """Every table name the client holds, as `Client.table` takes them."""
    return sorted(name[3:-3] for name in client.archive.files
                  if name.startswith("db/") and name.endswith(".db")
                  and "@" in name)


def _text(texts, key):
    return texts.get(key, "") if key else ""


def _card(row, group, texts):
    from game_client import clean
    return {
        "group": group,
        "name": clean(_text(texts, row.get("name"))),
        "desc": _text(texts, row.get("desc")),
        "sort": row.get("sort") or "",
        "category": row.get("card_category") or "",
        "rarity": row.get("rarity") or "",
        "cost": _number(row.get("cost"), 0),
        "talents": _list(row.get("talent")),
        "classes": _list(row.get("ownable_link_base_class_define_id")),
        "replace_cost": [_number(v, 0) for v in _list(row.get("r_spark_replace_cost"))],
        "tags": _list(row.get("r_spark_tag_default")),
        # Whether a Neutral or Divine Epiphany can land on it: Signature
        # cards but the Mythic one (`uni4`), Neutral, Monster and Event
        # cards; never a Basic, Forbidden, Persona, Desire or Memory card.
        "epiphany": row.get("battle_r_spark_enable_flag") == "YES",
        "effects": _list(row.get("link_skill_eff_id")),
        "children": _list(row.get("child_link_card_id")),
        "reward_tags": _list(row.get("reward_tag")),
        "extra_tags": _list(row.get("link_extra_tag_id")),
        "usable_condition": "" if row.get("card_usable_link_condition_id") in EMPTY
        else row.get("card_usable_link_condition_id") or "",
    }


def _epiphany(row, texts):
    return {
        # A Neutral Epiphany's cell reads `none`: no god.
        "god": None if row.get("god_type") in EMPTY else row["god_type"].lower(),
        "rarity": row.get("rarity") or "",
        "category": row.get("category") or "",
        "desc": _text(texts, row.get("description")),
        "classes": _list(row.get("target_link_base_class_define_id")),
        "categories": _list(row.get("target_card_category")),
        "cost_min": _number(row.get("target_card_cost_min"), -1),
        "cost_max": _number(row.get("target_card_cost_max"), -1),
        "include_talents": _list(row.get("target_card_include_talent")),
        "exclude_talents": _list(row.get("target_card_exclude_talent")),
        "tags": _list(row.get("r_spark_tag")),
        "exclude_tags": _list(row.get("r_spark_exclude_tag")),
        "add_cost": _number(row.get("add_cost_value"), 0),
        "add_cost_sign": row.get("add_cost_mathsign") or "",
        "effects": _list(row.get("add_link_skill_eff_id")),
        "talents": _list(row.get("add_talent")),
        # What a Divine Epiphany adds to the card's own effects, kept
        # whole for the damage calculator (T20).
        "adds": {key: row[key] for key in row
                 if key.startswith("add_") and row[key] not in EMPTY
                 and key not in ("add_cost_value", "add_cost_mathsign",
                                 "add_link_skill_eff_id", "add_talent")},
    }


def _persona_effect(row, texts):
    return {
        "slot_type": row.get("link_eidolon_slot_type_define_id") or "",
        "tags": _list(row.get("slot_tag")),
        "classes": _list(row.get("target_link_base_class_define_id")),
        "categories": _list(row.get("target_card_category")),
        "cost_min": _number(row.get("target_card_cost_min"), -1),
        "cost_max": _number(row.get("target_card_cost_max"), -1),
        "add_talents": _list(row.get("slot_add_card_talent")),
        "add_cost": _number(row.get("slot_add_cost"), 0),
        "add_cost_sign": row.get("slot_add_cost_mathsign") or "",
        "statuses": _list(row.get("link_cs_id")),
        "effects": _list(row.get("link_skill_eff_id")),
        "desc": _text(texts, row.get("desc")),
    }


def _equipment(row, table, texts):
    from game_client import clean
    stars = {}
    for star in range(1, 6):
        stars[str(star)] = {
            "desc": _text(texts, row.get(f"s{star}_description")),
            "statuses": _list(row.get(f"s{star}_link_cs_id")),
            "values": [_number(v, v) for v in _list(row.get(f"s{star}_cs_value"))],
            "nb_effects": _list(row.get(f"s{star}_link_nb_eff_id")),
        }
    return {
        "table": table,
        "name": clean(_text(texts, row.get("name"))),
        "rarity": row.get("rarity") or "",
        "type": row.get("relic_type") or "",
        "category": row.get("relic_category") or "",
        "reward_tags": _list(row.get("reward_tag")),
        "hammer": (row.get("hammer_use") or "").lower() == "y",
        "stars": stars,
    }


def read(client):
    """Everything this module holds, read off an open
    `game_client.Client`, as plain data. Raises whatever the reading
    meets."""
    from game_client import clean
    texts = client.text()
    names = _tables(client)
    data = {"format": CATALOGUE_FORMAT, "build": client.archive.build,
            "cards": {}, "versions": {}, "upgrades": {}, "effects": {},
            "statuses": {}}
    for name in names:
        if SORTIE in name:
            continue
        found = CARD_TABLE.match(name)
        if found:
            group = found.group("group") or "memory"
            for row in client.rows(name):
                data["cards"][row["id"]] = _card(row, group, texts)
        elif VERSION_TABLE.match(name):
            for row in client.rows(name):
                kind = VERSION_ID.match(row["id"])
                base = row.get("link_card_id")
                target = row.get("change_link_card_id")
                if not kind or not base or not target:
                    continue
                if kind.group(2):
                    data["versions"].setdefault(base, {})[kind.group(2)] = target
                else:
                    data["upgrades"].setdefault(base, {})[kind.group(1)] = target
        elif EFFECT_TABLE.search(name):
            for row in client.rows(name):
                data["effects"][row["id"]] = _compact(row)
        elif STATUS_TABLE.search(name):
            for row in client.rows(name):
                data["statuses"][row["id"]] = _compact(row)
    # A version has no name of its own in the text: it goes by its base
    # card's, which a card made in battle as a version needs too.
    for base, kinds in list(data["versions"].items()) + list(data["upgrades"].items()):
        for target in kinds.values():
            held = data["cards"].get(target)
            if held is not None and not held["name"] and base in data["cards"]:
                held["name"] = data["cards"][base]["name"]

    data["epiphanies"] = {row["id"]: _epiphany(row, texts)
                          for row in client.rows(EPIPHANY_TABLE)
                          if not row["id"].startswith(SORTIE_EPIPHANY)}
    data["points"] = {row["id"]: _value(row.get("value"))
                      for row in client.rows(POINT_TABLE)}
    data["constants"] = {}
    constants = {row["id"]: row.get("value") for row in client.rows(CONSTANT_TABLE)}
    for key, row_id in CONSTANTS.items():
        figure = _number(constants.get(row_id))
        if figure is not None:
            data["constants"][key] = figure

    units = {row["id"]: row for row in client.rows(UNIT_TABLE)}
    data["combatants"] = {}
    for row in client.rows(COMBATANT_TABLE):
        unit = units.get(row["id"], {})
        data["combatants"][row["id"]] = {
            "class": row.get("link_base_class_define_id") or "",
            "playable": unit.get("char_use_playable") == "YES",
            "name": clean(_text(texts, unit.get("name"))),
            "starting": [row.get(f"start_{i}_link_card_id") or "" for i in range(1, 5)],
            "signature": [row.get(f"spark_card_{i}_link_card_id") or "" for i in range(1, 5)],
            "ego": row.get("collapse_skill_link_card_id") or "",
        }
    from game_client import class_names
    data["classes"] = class_names(client)
    partner_units = {row["id"]: row for row in client.rows(PARTNER_UNIT_TABLE)}
    data["partners"] = {}
    for row in client.rows(PARTNER_TABLE):
        unit = partner_units.get(row["id"], {})
        data["partners"][row["id"]] = {
            "name": clean(_text(texts, unit.get("name"))),
            "playable": unit.get("char_use_playable") == "YES",
            "card": row.get("link_card_id") or "",
            # Its passive works for a Combatant of this class only.
            "class": row.get("passive_condition_link_base_class_define_id") or "",
        }
    data["potential"] = _potential(client)
    data["manifestation"] = _manifestation(client)
    data["kinds"] = {
        "node": sorted({row.get("node_type") or ""
                        for row in client.rows(NODE_EFFECT_TABLE)}),
        "manifestation": sorted({row.get("break_type") or ""
                                 for row in client.rows(MANIFESTATION_TABLE)})}

    data["persona"] = {
        "slots": {row["link_card_id"]: {"count": _number(row.get("eidolon_card_slot"), 0),
                                        "tags": _list(row.get("slot_tag"))}
                  for row in client.rows(PERSONA_SLOTS) if row.get("link_card_id")},
        "effects": {row["id"]: _persona_effect(row, texts)
                    for row in client.rows(PERSONA_EFFECTS)},
        "names": {row["id"]: {"slots": [row.get("slot_type_0") or "",
                                        row.get("slot_type_1") or ""],
                              "category": row.get("card_category") or "",
                              "name": clean(_text(texts, row.get("name")))}
                  for row in client.rows(PERSONA_NAMES)},
    }
    data["equipment"] = {}
    for table, kind in EQUIPMENT_TABLES.items():
        for row in client.rows(table):
            data["equipment"][row["id"]] = _equipment(row, kind, texts)
    data["buffs"] = {row["id"]: {"type": row.get("reinforce_type") or "",
                                 "desc": _text(texts, row.get("description")),
                                 "statuses": _list(row.get("link_cs_id"))}
                     for row in client.rows(BUFF_TABLE)}
    data["mutations"] = {row["id"]: {"name": clean(_text(texts, row.get("name"))),
                                     "desc": _text(texts, row.get("desc")),
                                     "statuses": _list(row.get("link_cs_id")),
                                     "nb_effects": _list(row.get("link_nb_eff_id"))}
                         for row in client.rows(MUTATION_TABLE)}
    # The in-game deck builder's own catalogue: what "released" means
    # for every card that is not a Combatant's (D32, D55).
    data["released"] = {}
    for name in names:
        if ARCHIVE_TABLE.match(name) and SORTIE not in name:
            for row in client.rows(name):
                if row.get("visible_on_build_preset") == "YES" and row.get("link_card_id"):
                    data["released"][row["link_card_id"]] = _list(
                        row.get("link_archive_card_sub_category_id"))
    _keep_reachable(data)
    data["conditions"] = _conditions(client, names, data["effects"])
    return data


def _conditions(client, names, effects):
    """{condition id: its controls, in order} for every condition a kept
    effect names. A control is {"type", "and_or", "cards", "units",
    "timings", "battle_timing"}: "stack" ones test their parts, "reset"
    ones say at which `battle_timing` the count starts over."""
    rows = {kind: {} for kind in ("condition", "condition_control",
                                  "cond_card", "cond_unit", "cond_timing")}
    for name in names:
        found = CONDITION_TABLE.match(name)
        if found:
            for row in client.rows(name):
                rows[found.group(1)].setdefault(row["id"], row)
    controls = {}
    for key, row in rows["condition_control"].items():
        controls.setdefault(key.rsplit("_", 1)[0], []).append(row)
    wanted = {held for effect in effects.values()
              for held in _list(effect.get("eff_link_condition_id"))}
    wanted |= {condition for effect in effects.values()
               for condition, _child in chained(effect) if condition}
    out = {}
    for condition_id in sorted(wanted):
        condition = rows["condition"].get(condition_id)
        if condition is None:
            continue
        key = condition.get("link_condition_control_key") or condition_id
        out[condition_id] = [{
            "type": control.get("type") or "",
            "and_or": control.get("and_or") or "",
            "cards": [_compact(rows["cond_card"][part])
                      for part in _list(control.get("link_cond_card_id"))
                      if part in rows["cond_card"]],
            "units": [_compact(rows["cond_unit"][part])
                      for part in _list(control.get("link_cond_unit_id"))
                      if part in rows["cond_unit"]],
            "timings": [_compact(rows["cond_timing"][part])
                        for part in _list(control.get("link_cond_timing_id"))
                        if part in rows["cond_timing"]],
            "battle_timing": [timing for timing in (control.get("battle_timing_0"),
                                                    control.get("battle_timing_1"))
                              if timing and timing != "TIMING_NONE"],
        } for control in sorted(controls.get(key, ()), key=_control_order)]
    return out


def _control_order(row):
    """A control row's place in its condition: `<key>_<n>` by n, as a
    number, so `_10` comes after `_2`."""
    tail = row["id"].rsplit("_", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _potential(client):
    """{Combatant res_id: {node: {level: {"cards", "statuses"}}}} for the
    Potential nodes that upgrade cards or put a status on. A node is the
    client's `node_num`, `<n>_<m>`. Where a Combatant has two trees
    listed, the game draws the reworked one, whose rows have the higher
    ids, so the highest id stands for each node and level."""
    effects = {row["id"]: row for row in client.rows(NODE_EFFECT_TABLE)}
    newest = {}
    for row in client.rows(NODE_TABLE):
        key = (row.get("link_char_combatant_id"), row.get("node_num"),
               row.get("node_level"))
        held = newest.get(key)
        if held is None or _number(row["id"], 0) > _number(held["id"], 0):
            newest[key] = row
    out = {}
    for (rid, node, level), row in sorted(newest.items()):
        cards, statuses = [], []
        for effect_id in _list(row.get("link_potential_node_effect_id")):
            effect = effects.get(effect_id, {})
            if effect.get("node_type") == NODE_UPGRADE:
                cards += _list(effect.get("link_card_id"))
            elif effect.get("node_type") == NODE_STATUS:
                statuses += _list(effect.get("link_cs_id"))
        if cards or statuses:
            out.setdefault(rid, {}).setdefault(node, {})[level] = {
                "cards": cards, "statuses": statuses}
    return out


def _manifestation(client):
    """{Combatant res_id: [{"level", "type", "cards", "statuses"}]}, by
    level: each Ego Manifestation level naming cards or putting a status
    on. A named card is upgraded where the client has its `lbk` version,
    else only named: one the level's status makes or strengthens."""
    out = {}
    for row in client.rows(MANIFESTATION_TABLE):
        group = row.get("group") or ""
        cards, statuses = _list(row.get("link_card_id")), _list(row.get("link_cs_id"))
        if group.startswith("limit_") and (cards or statuses):
            out.setdefault(group[len("limit_"):], []).append({
                "level": _number(row.get("break_level"), 0),
                "type": row.get("break_type") or "", "cards": cards,
                "statuses": statuses})
    for rows in out.values():
        rows.sort(key=lambda held: held["level"])
    return out


# The columns that link an effect or a status onward.
EFFECT_LINKS = ("link_cs_id",)
STATUS_LINKS = ("link_skill_eff_id", "show_link_cs_id")
# An effect's follow-ups, run as it works, each on a condition about what
# it did: "If a card was Discarded, create 1 Adagio" is a discard's
# `during_eff_0_link_skill_eff_id`, on `during_eff_0_link_condition_id`.
DURING = re.compile(r"^during_eff_(\d+)_link_skill_eff_id$")


def chained(effect):
    """[(condition id or "", effect id)], in their order: the effects
    `effect` runs as it works."""
    slots = sorted((int(found.group(1)), key) for key in effect
                   for found in [DURING.match(key)] if found)
    out = []
    for slot, key in slots:
        condition = effect.get(f"during_eff_{slot}_link_condition_id")
        for child in _list(effect[key]):
            out.append(("" if condition in EMPTY or condition is None else condition, child))
    return out


def _keep_reachable(data):
    """Drop the effects and statuses nothing in a deck can reach. The
    client's skill_eff and cs tables also serve monsters and every other
    system, several times what a deck needs."""
    effects, statuses = data["effects"], data["statuses"]
    todo_effects = set()
    todo_statuses = set()
    for card in data["cards"].values():
        todo_effects.update(card["effects"])
    for epiphany in data["epiphanies"].values():
        todo_effects.update(epiphany["effects"])
        todo_statuses.update(_list(epiphany["adds"].get("add_link_cs_id")))
    for effect in data["persona"]["effects"].values():
        todo_effects.update(effect["effects"])
        todo_statuses.update(effect["statuses"])
    for piece in data["equipment"].values():
        for star in piece["stars"].values():
            todo_statuses.update(star["statuses"])
    for held in list(data["buffs"].values()) + list(data["mutations"].values()):
        todo_statuses.update(held["statuses"])
    for nodes in data["potential"].values():
        for levels in nodes.values():
            for held in levels.values():
                todo_statuses.update(held["statuses"])
    for rows in data["manifestation"].values():
        for held in rows:
            todo_statuses.update(held["statuses"])
    kept_effects, kept_statuses = set(), set()
    while todo_effects or todo_statuses:
        while todo_effects:
            key = todo_effects.pop()
            if key in kept_effects or key not in effects:
                continue
            kept_effects.add(key)
            for column in EFFECT_LINKS:
                todo_statuses.update(_list(effects[key].get(column)))
            todo_effects.update(child for _condition, child in chained(effects[key]))
        while todo_statuses:
            key = todo_statuses.pop()
            if key in kept_statuses or key not in statuses:
                continue
            kept_statuses.add(key)
            todo_effects.update(_list(statuses[key].get("link_skill_eff_id")))
            todo_statuses.update(_list(statuses[key].get("show_link_cs_id")))
    data["effects"] = {key: effects[key] for key in sorted(kept_effects)}
    data["statuses"] = {key: statuses[key] for key in sorted(kept_statuses)}


# -------------------- the cache --------------------

def path_in(settings_dir):
    return Path(settings_dir) / CACHE_FILE


def load(settings_dir, build=None):
    """The cached catalogue, or None where there is none of this format
    -- or of `build`, where one is given."""
    try:
        with gzip.open(path_in(settings_dir), "rt", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError, EOFError):
        return None
    if not isinstance(data, dict) or data.get("format") != CATALOGUE_FORMAT:
        return None
    if build is not None and data.get("build") != build:
        return None
    return data


def save(settings_dir, data):
    """Write `data` as the cache, whole or not at all: through a temp
    file beside it, so a killed write leaves the last one."""
    target = path_in(settings_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(prefix=CACHE_FILE + ".", suffix=".tmp",
                                    dir=target.parent)
    try:
        with os.fdopen(handle, "wb") as raw, \
                gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as fh:
            fh.write(json.dumps(data, separators=(",", ":")).encode("utf-8"))
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def for_install(settings_dir, install):
    """The catalogue for `install`'s build: the cache where it holds
    that build, else read off the client and cached. None where neither
    can be had."""
    import game_client
    build = game_client.build_of(install) if install else None
    if build is not None:
        held = load(settings_dir, build)
        if held is not None:
            return held
        data = read(game_client.Client(install))
        save(settings_dir, data)
        return data
    return load(settings_dir)


# -------------------- reading it --------------------

class Catalogue:
    """The read catalogue's lookups."""

    def __init__(self, data):
        self.data = data
        self.cards = data.get("cards", {})
        self.versions = data.get("versions", {})
        self.upgrades = data.get("upgrades", {})
        self.epiphanies = data.get("epiphanies", {})
        self.points = data.get("points", {})
        self.combatants = data.get("combatants", {})
        self.persona = data.get("persona", {})
        self.equipment = data.get("equipment", {})
        self.buffs = data.get("buffs", {})
        self.mutations = data.get("mutations", {})
        self.released = data.get("released", {})
        self.constants = data.get("constants", {})
        self.effects = data.get("effects", {})
        self.statuses = data.get("statuses", {})
        self.conditions = data.get("conditions", {})
        self.partners = data.get("partners", {})
        self.potential = data.get("potential", {})
        self.manifestation = data.get("manifestation", {})

    @property
    def build(self):
        return self.data.get("build")

    def card(self, card_id):
        return self.cards.get(card_id)

    def version(self, card_id, number):
        """The card a Signature Epiphany turns `card_id` into: its
        `number`th, 1 to 5. None where there is no such version."""
        return self.versions.get(card_id, {}).get(str(number)) if number else None

    def combatant(self, res_id):
        return self.combatants.get(str(res_id))

    def partner(self, res_id):
        return self.partners.get(str(res_id)) if res_id else None

    def class_of(self, res_id):
        held = self.combatant(res_id)
        return held.get("class") if held else None

    def class_name(self, class_id):
        """A class's English name, else its id."""
        return self.data.get("classes", {}).get(class_id) or class_id

    def point(self, row, default=0):
        """A deck point rule's value, in the client's unit (tens of the
        points the game shows)."""
        return self.points.get(row, default)

    def problems(self):
        """What a misread would break, as sentences; [] for a read that
        adds up (D34)."""
        out = []
        for key in CONSTANTS:
            if not isinstance(self.constants.get(key), int):
                out.append(f"the battle constant {CONSTANTS[key]} did not read "
                           f"as a whole number.")
        playable = {rid: c for rid, c in self.combatants.items() if c.get("playable")}
        if not playable:
            out.append("no Combatant reads as playable (char_use_playable).")
        classes = self.data.get("classes", {})
        for rid, held in sorted(playable.items()):
            eight = held.get("starting", []) + held.get("signature", [])
            missing = [card for card in eight if card not in self.cards]
            if len(eight) != 8 or missing:
                out.append(f"Combatant {rid} {held.get('name')!r} lacks its eight "
                           f"starting cards in the card tables: {missing or eight}.")
            if held.get("class") not in classes:
                out.append(f"Combatant {rid}'s class {held.get('class')!r} is not "
                           f"one of base_class_define's {sorted(classes)}.")
        effects = self.data.get("effects", {})
        unknown = sorted({eff for card in self.cards.values()
                          for eff in card.get("effects", ()) if eff not in effects})
        if unknown:
            out.append(f"{len(unknown)} effect ids the cards name are in no "
                       f"skill_eff table, such as {unknown[:3]}.")
        for base, numbered in sorted(self.versions.items()):
            lost = [card for card in numbered.values() if card not in self.cards]
            if lost:
                out.append(f"{base}'s Signature Epiphanies turn it into cards the "
                           f"tables lack: {lost}.")
        new = sorted(set(self.points) - KNOWN_POINT_ROWS)
        if new:
            out.append(f"deck point rules the program does not price: {new}. "
                       f"See `decks.rules` and docs/decks.md.")
        for row in ("cd_get_job", "cd_remove_start", "god_r_spark",
                    "cd_copy_revise_by_count"):
            if row not in self.points:
                out.append(f"the deck point rule {row} is gone from "
                           f"savedata_point_define.")
        if not self.released:
            out.append("the in-game deck builder's catalogue (archive_card) "
                       "offers no card.")
        follows = sorted({follow for effect in effects.values()
                          for _condition, follow in chained(effect) if follow not in effects})
        if follows:
            out.append(f"{len(follows)} follow-up effects (during_eff_*) the read effects name "
                       f"are in no skill_eff table, such as {follows[:3]}: what they do is "
                       f"lost.")
        able = sum(1 for card in self.cards.values() if card.get("epiphany"))
        if not able or able == len(self.cards):
            out.append(f"{able} cards of {len(self.cards)} read as able to take an "
                       f"Epiphany (battle_r_spark_enable_flag): every card or none.")
        divine = sum(1 for held in self.epiphanies.values() if held.get("god"))
        if not divine or divine == len(self.epiphanies):
            out.append(f"the Epiphany table reads as {divine} Divine "
                       f"Epiphanies of {len(self.epiphanies)}: no "
                       f"{'Divine' if not divine else 'Neutral'} one "
                       f"(r_spark's god_type).")
        named = {held for effect in self.effects.values()
                 for held in _list(effect.get("eff_link_condition_id"))}
        unread = sorted(named - set(self.conditions))
        if unread:
            out.append(f"{len(unread)} conditions effects name are in no "
                       f"condition table, such as {unread[:3]}: decks.turns "
                       f"reads each such draw or AP gain as the battle's.")
        hollow = sorted(key for key, controls in self.conditions.items() if not controls)
        if hollow:
            out.append(f"{len(hollow)} conditions read with no condition_control "
                       f"rows, such as {hollow[:3]}: what they test is lost.")
        out += self._progress_problems()
        return out

    def _progress_problems(self):
        """The partners', Potential nodes' and Ego Manifestation's part of
        `problems`."""
        out = []
        if not self.partners:
            out.append("no partner reads (partner_base@char_partner).")
        lost = sorted(pid for pid, held in self.partners.items()
                      if held.get("card") not in self.cards)
        if lost:
            out.append(f"{len(lost)} partners' Ego skill cards are in no card table, "
                       f"such as {lost[:3]}.")
        upgraded = [card for nodes in self.potential.values() for levels in nodes.values()
                    for held in levels.values() for card in held["cards"]]
        if not upgraded:
            out.append(f"no Potential node upgrades a card ({NODE_UPGRADE}): every "
                       f"Basic card would play as it starts.")
        bare = sorted({card for card in upgraded if "pot" not in self.upgrades.get(card, {})})
        if bare:
            out.append(f"Potential nodes upgrade cards with no `pot` version, such as "
                       f"{bare[:3]}.")
        if not self.manifestation:
            out.append("no Ego Manifestation level reads (combatant_limit_break).")
        named = {status for rows in self.manifestation.values() for held in rows
                 for status in held["statuses"]}
        named |= {status for nodes in self.potential.values() for levels in nodes.values()
                  for held in levels.values() for status in held["statuses"]}
        gone = sorted(named - set(self.statuses))
        if gone:
            out.append(f"{len(gone)} statuses Potential nodes and Ego Manifestation put on "
                       f"are in no status table, such as {gone[:3]}.")
        kinds = self.data.get("kinds", {})
        for kind, known in (("node", KNOWN_NODE_TYPES), ("manifestation", KNOWN_BREAK_TYPES)):
            new = sorted(set(kinds.get(kind, ())) - known)
            if new:
                out.append(f"{kind} types the program has not judged: {new}. What "
                           f"each does to a deck: docs/decks.md, *The turn*.")
        both = sorted(card for card in self.upgrades if card in self.versions)
        if both:
            out.append(f"cards with both an upgrade and Signature Epiphanies, such as "
                       f"{both[:3]}: which of them plays is unread (decks.turns).")
        return out
