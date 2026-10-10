"""Read the game client's own data tables and English text. Reads only.

    python docs/client_tables.py                     what is installed
    python docs/client_tables.py --list REGEX        archived paths
    python docs/client_tables.py --table NAME        one table, as TSV
    python docs/client_tables.py --text REGEX        English text by id or words
    python docs/client_tables.py --ship              rewrite the shipped names
    python docs/client_tables.py --audit             game_data against the client

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

The reader itself is `Vribbels/game_client.py`, the same one the
program runs at launch. Python 3.14, for `compression.zstd`.
"""

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "Vribbels"))

import game_client                                            # noqa: E402
from game_client import Client                                # noqa: E402

SHIPPED = REPO / "Vribbels" / "game_data" / "from_client.py"

SHIPPED_HEAD = '''"""Event and item names and Excursion type counts read off the game client.

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
    items = game_client.item_names(client)
    visits = game_client.excursion_types(client)
    lines = [SHIPPED_HEAD, f"BUILD = {client.archive.build}", "",
             "# {schedule id: English name}. See game_client.event_names.",
             "EVENT_NAMES = {"]
    lines += [f"    {ascii(key)}: {ascii(name)},"
              for key, name in sorted(names.items())]
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
    lines += ["}", ""]
    return "\n".join(lines)


# The client's words for what `game_data` spells its own way.
CLASSES = {"striker": "Striker", "vanguard": "Vanguard",
           "hunter": "Hunter", "ranger": "Ranger", "psionic": "Psionic",
           "controller": "Controller"}
ATTRIBUTES = {"RED": "Passion", "PURPLE": "Void", "ORANGE": "Instinct",
              "GREEN": "Order", "BLUE": "Justice"}
GRADES = {"RARITY_SR": 4, "RARITY_SSR": 5}
# A combatant's stats at level 60: its level-1 stat, every level's step
# up to it, and the five promotions on the way.
AUDIT_LEVEL = 60
PROMOTIONS = 5
STATS = (("base_atk", "s_atk", "S_ATK"), ("base_def", "s_def", "S_DEF"),
         ("base_hp", "s_hp", "S_HP"))
NUMBER = re.compile(r"\d+(?:\.\d+)?")
BREAK = re.compile(r"<br\s*/?>", re.I)
MARKUP = re.compile(r"<[^>]*>")
KEYWORD = re.compile(r"\$([^$#]*)(?:#\d*)?\$")
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


def passage(text):
    """A passage of the client's as the game draws it: `<br>` as a new
    line, colour tags taken out, and a keyword's marker `$Name#level$`
    down to its name -- the level in it is not one of the figures."""
    text = BREAK.sub("\n", text or "")
    text = MARKUP.sub("", text)
    text = KEYWORD.sub(r"\1", text)
    text = text.replace(chr(0x2019), "'")
    return "\n".join(" ".join(line.split()) for line in text.split("\n"))


def _numbers(text):
    """The figures in a passage, markup aside, as sorted floats."""
    return sorted(float(n) for n in NUMBER.findall(passage(text)))


def _figures(numbers):
    """Sorted figures as a passage would print them."""
    return "[" + " ".join(f"{n:g}" for n in numbers) + "]"


def audit(client):
    """Lines saying where `game_data` and `client` disagree."""
    from game_data import CHARACTERS, PARTNERS
    texts = client.text()
    combat = {r["id"]: r for r in client.rows("char_base@char_combatant")}
    base = {r["id"]: r for r in client.rows("char_base@char_base")}
    levels = client.rows("char_base@combatant_level")
    ascends = client.rows("char_base@combatant_ascend")
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
        differ(who, "base_crit_rate", ours.get("base_crit_rate"),
               float(row["s_cri"]))
        differ(who, "base_crit_dmg", ours.get("base_crit_dmg"),
               float(row["s_cri_dmg_rate"]))
    for rid in sorted(combat, key=int):
        if int(rid) not in CHARACTERS and base.get(rid, {}).get(
                "char_use_playable") == "YES":
            out.append(f"combatant {rid} "
                       f"{texts.get(f'char_base@name@{rid}')}: in the "
                       f"client, not in game_data/characters.py")

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
    args = parser.parse_args(argv)
    install = game_client.find_install(args.client)
    if install is None:
        print("no game client found: name one with --client")
        return 1
    client = Client(install)
    archive = client.archive
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
