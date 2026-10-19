"""Read the game client's own data tables and English text. Reads only.

    python docs/client_tables.py                     what is installed
    python docs/client_tables.py --list REGEX        archived paths
    python docs/client_tables.py --table NAME        one table, as TSV
    python docs/client_tables.py --text REGEX        English text by id or words
    python docs/client_tables.py --ship              rewrite the shipped names
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

`--ship` rewrites `Vribbels/game_data/from_client.py`, what a player
whose client the program cannot read sees instead: run it after a
patch, before a release, and review its diff.

`--audit` prints every place `game_data`'s combatants, partners and
item names disagree with the client, and the ones either side lacks:
the tables are typed by hand, and a patch that rebalances one changes
nothing there. It writes nothing; a disagreement is for the maintainer
to settle, since the hand-typed figure can be the newer one.

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
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "Vribbels"))

import client_archive                                         # noqa: E402
import game_client                                            # noqa: E402
from game_client import Client                                # noqa: E402

SHIPPED = REPO / "Vribbels" / "game_data" / "from_client.py"

SHIPPED_HEAD = '''"""Event names and totals, item names, Excursion types, daily tasks, set effects, Potential texts, combatants and partners, off the game client.

Written by `python docs/client_tables.py --ship`, as of the game build
`BUILD`; never edited by hand. What a player's own client says wins
over these (`game_client`), so this is what a player sees whose client
the program could not find or read.

ASCII throughout: a name's other characters are written as escapes.
"""

'''


def _tsv(columns, rows):
    clean = str.maketrans({"\t": " ", "\n": " ", "\r": " "})
    yield "\t".join(columns)
    for row in rows:
        yield "\t".join(row[c].translate(clean) for c in columns)


def shipped_source(client):
    """The text of `from_client.py` for what `client` holds."""
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
              "# {combatant res_id: what game_data.characters holds of it}. "
              "See",
              "# game_client.combatants; game_data.client_overlay lays it "
              "over CHARACTERS.",
              "COMBATANTS = {"]
    lines += [f"    {res_id}: {ascii(entry)},"
              for res_id, entry in sorted(game_client.combatants(client).items())]
    lines += ["}", "",
              "# {partner res_id: what game_data.partners holds of it}. See",
              "# game_client.partners; game_data.client_overlay lays it "
              "over PARTNERS.",
              "PARTNERS = {"]
    lines += [f"    {res_id}: {ascii(entry)},"
              for res_id, entry in sorted(game_client.partners(client).items())]
    lines += ["}", ""]
    return "\n".join(lines)


# The client's words for what `game_data` spells its own way: the
# reader's own maps, so the audit and the program read alike.
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
    them (`game_data.client_overlay`), which would agree with anything."""
    from game_data.characters import table_stats_at_level
    from game_data.client_overlay import hand
    CHARACTERS, PARTNERS = hand("CHARACTERS"), hand("PARTNERS")
    texts = client.text()
    combat = {r["id"]: r for r in client.rows("char_base@char_combatant")}
    base = {r["id"]: r for r in client.rows("char_base@char_base")}
    levels = client.rows("char_base@combatant_level")
    ascends = client.rows("char_base@combatant_ascend")
    derived = game_client.combatants(client)
    derived_partners = game_client.partners(client)
    out = []

    def differ(who, field, ours, theirs):
        if _plain(ours) != _plain(theirs):
            out.append(f"{who}: {field} is {ours!r} here, {theirs!r} in "
                       f"the client")

    for rid, ours in sorted((r, c) for r, c in CHARACTERS.items()
                            if isinstance(r, int) and r > 0
                            and isinstance(c, dict)):
        row = combat.get(str(rid))
        who = f"combatant {rid} {ours.get('name')}"
        if row is None:
            out.append(f"{who}: not in the client")
            continue
        differ(who, "name", ours.get("name"),
               texts.get(f"char_base@name@{rid}"))
        differ(who, "grade", ours.get("grade"),
               GRADES.get(base.get(str(rid), {}).get("rarity")))
        differ(who, "class", ours.get("class"),
               CLASSES.get(row["link_base_class_define_id"]))
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
    for rid in sorted(combat, key=int):
        if int(rid) not in CHARACTERS and base.get(rid, {}).get(
                "char_use_playable") == "YES":
            out.append(f"combatant {rid} "
                       f"{texts.get(f'char_base@name@{rid}')}: in the "
                       f"client, not in game_data/characters.py")

    # Affinity's exp from each level to the next; the cap's row is -1.
    from game_data.constants import AFFINITY_TO_NEXT
    exp = {int(r["id"]): int(r["exp"])
           for r in client.rows("friendship_level@friendship_level")
           if r.get("id", "").isdigit() and int(r.get("exp") or -1) > 0}
    if exp != AFFINITY_TO_NEXT:
        out.append(f"Affinity: exp to the next level is "
                   f"{AFFINITY_TO_NEXT} here, {exp} in the client")

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
        differ(who, "name", ours.get("name"),
               texts.get(f"char_base@name@{rid}"))
        differ(who, "class", ours.get("class"), CLASSES.get(
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
        if apart:
            level, here, there = apart[0]
            out.append(
                f"{who}: passive figures differ at level"
                f"{'s' if len(apart) > 1 else ''} "
                f"{', '.join(str(a[0]) for a in apart)}; at {level} "
                f"{_figures(here)} here, {_figures(there)} in the client")
    for rid in sorted(partner, key=int):
        if int(rid) not in PARTNERS:
            out.append(f"partner {rid} "
                       f"{texts.get(f'char_base@name@{rid}')}: in the "
                       f"client, not in game_data/partners.py")

    # The program's own item names go over the client's, so a name that
    # differs is one of its tables overriding the game.
    from game_data.constants import item_names
    theirs = game_client.item_names(client)
    for rid, name in sorted(item_names().items()):
        if rid in theirs:
            differ(f"item {rid}", "name", name, theirs[rid])

    effects = game_client.set_effects(client)
    out += set_problems(effects)
    out += unlisted_sets(effects)
    from game_data import from_client
    out += set_changes(from_client.SET_EFFECTS, effects)
    out += potential_7_problems(client)
    out += node_51_problems(client)
    return out


# The client's stat ids for the plain stats a set's `stat` names.
SET_STATS = {"S_ATK_INC_RATE_OUT": "ATK%", "S_DEF_INC_RATE_OUT": "DEF%",
             "S_HP_INC_RATE_OUT": "HP%",
             "S_CRI_DMG_RATE_INC_ADD": "Crit DMG",
             "S_CRI_INC_ADD": "Crit Rate"}


# The game's words for a limit that carry no figure, and how the
# maintainer's wordings state the same limit: as a `max N`.
LIMIT_PHRASES = (("cannot stack", "max 1"),)


def set_problems(effects):
    """Lines saying where `game_data/sets.py` and `effects`, the
    client's sets as `game_client.set_effects` gives them, disagree: a
    name, a piece count, a plain stat or its figure, the figures in the
    maintainer's own wording against the game's, and a set the client
    lacks (`unlisted_sets` names the ones `sets.py` lacks). The wording
    itself is the maintainer's, and not compared."""
    from game_data import SETS
    out = []
    for set_id, ours in sorted(SETS.items()):
        who = f"set {set_id} {ours.get('name')}"
        theirs = effects.get(set_id)
        if theirs is None:
            out.append(f"{who}: not in the client")
            continue
        name, pieces, words, stat, value = theirs
        if _plain(ours.get("name")) != name:
            out.append(f"{who}: named {name!r} in the client")
        if ours.get("pieces") != pieces:
            out.append(f"{who}: {ours.get('pieces')} pieces here, {pieces} "
                       f"in the client")
        if stat and (SET_STATS.get(stat), value) != (ours.get("stat"),
                                                    ours.get("value")):
            out.append(f"{who}: {ours.get('stat')} {ours.get('value')} "
                       f"here, {SET_STATS.get(stat, stat)} {value} in the "
                       f"client")
        # Which figures, not how often: a short wording states a figure
        # once where the game's repeats it.
        bonus = ours.get("bonus")
        stated = words
        for theirs_, ours_ in LIMIT_PHRASES:
            stated = stated.replace(theirs_, ours_)
        here, there = set(_numbers(bonus)), set(_numbers(stated))
        if bonus and here != there:
            out.append(f"{who}: its wording states "
                       f"{_figures(sorted(here))}, the game's "
                       f"{_figures(sorted(there))}: {words!r}")
    return out


def unlisted_sets(effects):
    """Lines naming each of the client's sets `game_data/sets.py` lacks.
    The program shows it by number, in the game's words."""
    from game_data import SETS
    return [f"set {set_id} {effects[set_id][0]}: in the client, not in "
            f"game_data/sets.py" for set_id in sorted(set(effects) - set(SETS))]


def set_changes(before, after):
    """Lines naming each set whose effect `after` words differently
    from `before` (both as `game_client.set_effects` gives them), and
    whether only its figures moved -- then the maintainer's wording
    wants new figures -- or its words did, and it wants rewording."""
    out = []
    for set_id in sorted(set(before) & set(after)):
        old, new = before[set_id][2], after[set_id][2]
        if old == new:
            continue
        who = f"set {set_id} {after[set_id][0]}"
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


def potential_7_problems(client):
    """Lines saying where `potential_7.py` and the client's node 7s
    disagree: an effect one side states and the other does not, the
    figures `potential_7.py` holds that the game's text never states,
    a `TEXT_FIXES` entry whose words the text no longer holds, and a
    combatant either side lacks. The data is the source; the text is
    compared as the Combatants tab shows it, its fixes applied."""
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
                out.append(f"{who} is in the client, not in "
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
    elif args.audit:
        found = audit(client)
        print("\n".join(found) if found else
              "game_data agrees with the client")
        print(f"build {archive.build}: {len(found)} disagreement(s)")
    elif args.ship:
        SHIPPED.write_text(shipped_source(client), encoding="utf-8",
                           newline="\n")
        print(f"build {archive.build} to {SHIPPED.relative_to(REPO)}")
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
