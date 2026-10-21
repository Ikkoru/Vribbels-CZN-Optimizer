"""The deck catalogue, as `decks.catalogue` reads it off the game client.

A patch that renames or repurposes a column misreads quietly: the Deck
Builder then prices and warns from wrong data, and nothing fails.
`Catalogue.problems` is the read checking itself. This holds the
installed client's read to it, shows that each of its checks speaks up
about the misread it guards, and that nothing Sortie-only got in. It
also holds what plan D2 assumes, that no partner's passive draws or
gives AP: the turns read none.

The cache is held too. One that served another build's catalogue, or a
half-written file, would do so silently; a failed write must leave the
last good one, and no temp file beside it.
"""

import gzip
import json
import tempfile
from pathlib import Path

from ._harness import add_source_to_path, note

NAME = "the deck catalogue read off the game client"


def _playable(data):
    return next(rid for rid, held in sorted(data["combatants"].items())
                if held["playable"])


def _short_a_card(data):
    cards = dict(data["cards"])
    del cards[data["combatants"][_playable(data)]["starting"][0]]
    return dict(data, cards=cards)


def _constant_as_text(data):
    return dict(data, constants=dict(data["constants"], draw="5"))


def _unknown_row(data):
    return dict(data, points=dict(data["points"], cd_get_new_kind=2))


def _key_row_gone(data):
    points = dict(data["points"])
    del points["cd_get_job"]
    return dict(data, points=points)


def _effect_gone(data):
    effects = dict(data["effects"])
    effects.pop(next((effect for card in data["cards"].values()
                      for effect in card["effects"] if effect in effects),
                     None), None)
    return dict(data, effects=effects)


def _version_lost(data):
    base = next(iter(sorted(data["versions"])))
    cards = dict(data["cards"])
    del cards[next(iter(data["versions"][base].values()))]
    return dict(data, cards=cards)


def _nobody_playable(data):
    return dict(data, combatants={rid: dict(held, playable=False)
                                  for rid, held in data["combatants"].items()})


def _class_unknown(data):
    rid = _playable(data)
    held = dict(data["combatants"][rid], **{"class": "class_unheard_of"})
    return dict(data, combatants=dict(data["combatants"], **{rid: held}))


def _nothing_released(data):
    return dict(data, released={})


def _every_epiphany_a_gods(data):
    return dict(data, epiphanies={key: dict(held, god=held["god"] or "none")
                                  for key, held in data["epiphanies"].items()})


def _conditions_unread(data):
    return dict(data, conditions={})


def _no_partners(data):
    return dict(data, partners={})


def _partner_card_gone(data):
    cards = dict(data["cards"])
    del cards[next(held["card"] for _pid, held in sorted(data["partners"].items()))]
    return dict(data, cards=cards)


def _no_potential(data):
    return dict(data, potential={})


def _pot_versions_gone(data):
    return dict(data, upgrades={base: {kind: card for kind, card in kinds.items()
                                       if kind != "pot"}
                                for base, kinds in data["upgrades"].items()})


def _no_manifestation(data):
    return dict(data, manifestation={})


def _node_type_unjudged(data):
    return dict(data, kinds=dict(data["kinds"], node=data["kinds"]["node"] + ["NODE_NEW"]))


def _upgrade_with_versions(data):
    base = next(base for base, kinds in sorted(data["upgrades"].items()) if "lbk" in kinds)
    return dict(data, versions=dict(data["versions"], **{base: {"1": base}}))


def _follow_gone(data):
    from decks.catalogue import chained
    follows = {child for effect in data["effects"].values()
               for _condition, child in chained(effect)}
    return dict(data, effects={key: effect for key, effect in data["effects"].items()
                               if key not in follows})


def _every_card_able(data):
    return dict(data, cards={key: dict(card, epiphany=True)
                             for key, card in data["cards"].items()})


def _progress_statuses_gone(data):
    named = {status for rows in data["manifestation"].values() for held in rows
             for status in held["statuses"]}
    return dict(data, statuses={key: row for key, row in data["statuses"].items()
                                if key not in named})


# (what the misread is, the misread, a piece of what `problems` must say)
MISREADS = [
    ("a Combatant short of a starting card", _short_a_card,
     "lacks its eight starting cards"),
    ("a battle constant read as text", _constant_as_text,
     "did not read as a whole number"),
    ("a deck point rule the program does not price", _unknown_row,
     "does not price"),
    ("the Neutral card's point rule gone", _key_row_gone, "is gone"),
    ("an effect a card names gone", _effect_gone, "in no skill_eff table"),
    ("a Signature Epiphany's card gone", _version_lost,
     "Signature Epiphanies turn it into"),
    ("no Combatant playable", _nobody_playable, "reads as playable"),
    ("a Combatant's class unknown", _class_unknown,
     "is not one of base_class_define's"),
    ("the in-game deck builder offering nothing", _nothing_released,
     "offers no card"),
    ("every Epiphany read as a god's", _every_epiphany_a_gods,
     "no Neutral one"),
    ("the condition tables unread", _conditions_unread,
     "are in no condition table"),
    ("no partner read", _no_partners, "no partner reads"),
    ("a partner's Ego skill card gone", _partner_card_gone,
     "Ego skill cards are in no card table"),
    ("no Potential node read", _no_potential, "no Potential node upgrades a card"),
    ("the Potential upgrades' cards gone", _pot_versions_gone, "with no `pot` version"),
    ("no Ego Manifestation read", _no_manifestation, "no Ego Manifestation level reads"),
    ("a Potential node type nobody judged", _node_type_unjudged,
     "types the program has not judged"),
    ("an upgraded card with Signature Epiphanies", _upgrade_with_versions,
     "both an upgrade and Signature Epiphanies"),
    ("the progress statuses gone", _progress_statuses_gone, "are in no status table"),
    ("a follow-up effect gone", _follow_gone, "follow-up effects"),
    ("every card read as able to take an Epiphany", _every_card_able, "every card or none"),
]


def _misreads_report(catalogue, data):
    """Each of `problems`' checks speaks up about the misread it
    guards, put into a copy of a good read. Returns complaints."""
    out = []
    for what, misread, says in MISREADS:
        found = " ".join(catalogue.Catalogue(misread(data)).problems())
        if says not in found:
            out.append(f"{what} goes unreported by Catalogue.problems "
                       f"(it said: {found[:200]!r}), so a patch causing it "
                       f"would misprice decks silently. See "
                       f"decks/catalogue.py.")
    return out


def _sortie_report(data):
    """Nothing Sortie-only is in the read (plan.md D59)."""
    out = []
    groups = sorted({card["group"] for card in data["cards"].values()
                     if "assault" in card["group"]})
    if groups:
        out.append(f"Sortie's cards are in the deck catalogue (groups "
                   f"{groups}); no Save Data can hold one. See CARD_TABLE "
                   f"and SORTIE in decks/catalogue.py.")
    epiphanies = sorted(key for key in data["epiphanies"] if "assault" in key)
    if epiphanies:
        out.append(f"Sortie's Epiphanies are in the deck catalogue, such as "
                   f"{epiphanies[:3]}. See SORTIE_EPIPHANY in "
                   f"decks/catalogue.py.")
    tables = sorted({piece["table"] for piece in data["equipment"].values()}
                    - {"relic", "disaster"})
    if tables:
        out.append(f"Equipment from {tables} is in the deck catalogue; only "
                   f"a Chaos's Equipment enters a deck. See EQUIPMENT_TABLES "
                   f"in decks/catalogue.py.")
    return out


def _passive_gains(cat, statuses):
    """(status, what) for each draw, AP gain or made card that changes a
    sum among what `statuses` give, read as a unit's battle statuses."""
    from decks import turns
    from decks.catalogue import _list
    from decks.created import status_cards
    out = []
    for status in statuses:
        reader = turns._Reader(cat, turns.Figure())
        reader.walk(_list(cat.statuses.get(status, {}).get("link_skill_eff_id")),
                    holder=turns.UNIT, lasting=True)
        out += [(status, f"gives {which} ({mode})")
                for (mode, which), figure in reader.figures.items()
                if figure.value or figure.unknown]
        out += [(status, f"makes {made.card}")
                for made in status_cards(status, status, [status], cat) if not made.idle]
    return out


def _partner_passive_report(catalogue, client, data):
    """No partner's passive draws, gives AP or makes a card that changes
    a sum (plan D2), so the turns read none: a patch adding one is
    reported. The client's every status and effect is read for it, the
    partner passives' own tables included; and the guard is shown to
    fire on a passive that draws. Returns complaints."""
    names = catalogue._tables(client)
    full = dict(data, statuses=dict(data["statuses"]), effects=dict(data["effects"]))
    passives = []
    for name in names:
        if catalogue.SORTIE in name:
            continue
        if catalogue.STATUS_TABLE.search(name):
            for row in client.rows(name):
                full["statuses"].setdefault(row["id"], catalogue._compact(row))
        elif catalogue.EFFECT_TABLE.search(name):
            for row in client.rows(name):
                full["effects"].setdefault(row["id"], catalogue._compact(row))
        elif name.startswith("partner_passive") and name.endswith("@partner_passive"):
            passives += client.rows(name)
    full["conditions"] = catalogue._conditions(client, names, full["effects"])
    statuses = sorted({status for row in passives
                       for status in catalogue._list(row.get("link_cs_id"))})
    out = [f"partner passive status {status} {what}: plan D2 counts no partner's "
           f"passive, so a deck's turns miss it. Read the partner's passive as a "
           f"bonus (`bonuses` in decks/turns.py)."
           for status, what in _passive_gains(catalogue.Catalogue(full), statuses)]
    if not statuses:
        out.append("no partner passive's status was read, so the plan D2 guard checks "
                   "nothing. See partner_passive@partner_passive.")
    probe = dict(full, statuses=dict(full["statuses"], st_probe={
        "link_skill_eff_id": "[probe_draw]", "term_type_1": "TERM_BATTLE"}),
        effects=dict(full["effects"], probe_draw={
            "eff": "SKILL_EFF_CARD_DRAW", "eff_value": "1",
            "operation": "OPERATION_PASSIVE", "eff_value_type_1": "VALUE_COMMON"}))
    if not _passive_gains(catalogue.Catalogue(probe), ["st_probe"]):
        out.append("the partner passive guard misses a status that draws, so it proves "
                   "nothing.")
    return out


def _cache_report(catalogue):
    """The cache serves its own build and format only, and a failed
    write leaves the last good file and no temp file. Returns
    complaints."""
    out = []
    data = {"format": catalogue.CATALOGUE_FORMAT, "build": "1.0.0",
            "cards": {"c_1_srt1": {"name": "A card"}}}
    # A save that fails holding its temp file open leaves a file Windows
    # will not delete; the complaint below says so, not the cleanup.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        try:
            catalogue.save(folder, data)
        except Exception as e:
            out.append(f"saving the cache failed: {type(e).__name__}: {e}. "
                       f"See `save` in decks/catalogue.py.")
        if catalogue.load(folder, "1.0.0") != data:
            out.append("the cache does not load back what was saved. See "
                       "`save` and `load` in decks/catalogue.py.")
        if catalogue.load(folder) != data:
            out.append("the cache does not load with no build asked for.")
        if catalogue.load(folder, "1.0.1") is not None:
            out.append("the cache serves another build's catalogue, so a "
                       "patch's new cards would never be read. See `load` "
                       "in decks/catalogue.py.")
        try:
            catalogue.save(folder, dict(data, cards={"bad": {1, 2}}))
        except Exception:
            pass
        else:
            out.append("saving data JSON cannot hold raised nothing, so "
                       "the failed-save test below proves nothing.")
        if catalogue.load(folder, "1.0.0") != data:
            out.append("a failed save destroyed the last good cache: the "
                       "write must go through a temp file. See `save` in "
                       "decks/catalogue.py.")
        left = [p.name for p in Path(folder).iterdir()
                if p.name != catalogue.CACHE_FILE]
        if left:
            out.append(f"a failed save left its temp file behind: {left}.")
        path = catalogue.path_in(folder)
        path.write_bytes(path.read_bytes()[:20])
        if catalogue.load(folder) is not None:
            out.append("a truncated cache file loads as a catalogue.")
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(dict(data, format=catalogue.CATALOGUE_FORMAT + 1), fh)
        if catalogue.load(folder) is not None:
            out.append("a cache of another format loads, so a format "
                       "change would read old files as new.")
    return out


def run():
    add_source_to_path()
    import game_client
    from decks import catalogue
    failures = _cache_report(catalogue)
    install = game_client.find_install()
    if install is None:
        note("no game client installed, so the catalogue's read and its "
             "self-check were not exercised")
        return failures
    client = game_client.Client(install)
    data = catalogue.read(client)
    failures += [f"{problem} -- build {data['build']}, installed. A patch "
                 f"changed what the deck catalogue reads: see "
                 f"decks/catalogue.py and docs/decks.md."
                 for problem in catalogue.Catalogue(data).problems()]
    failures += _sortie_report(data)
    failures += _misreads_report(catalogue, data)
    failures += _partner_passive_report(catalogue, client, data)
    return failures


FAULTS = [
    ("a Combatant short of its eight cards passes",
     "decks.catalogue:Catalogue.problems",
     "if len(eight) != 8 or missing:", "if False:",
     "a Combatant short of a starting card"),
    ("a constant read as text passes",
     "decks.catalogue:Catalogue.problems",
     "if not isinstance(self.constants.get(key), int):", "if False:",
     "a battle constant read as text"),
    ("a rule the program does not price passes",
     "decks.catalogue:Catalogue.problems",
     "new = sorted(set(self.points) - KNOWN_POINT_ROWS)", "new = []",
     "the program does not price goes unreported"),
    ("a key rule's loss passes",
     "decks.catalogue:Catalogue.problems",
     "if row not in self.points:", "if False:",
     "the Neutral card's point rule gone"),
    ("the Neutral-or-Divine check passes",
     "decks.catalogue:Catalogue.problems",
     "if not divine or divine == len(self.epiphanies):", "if False:",
     "every Epiphany read as a god's"),
    ("a Neutral Epiphany's god read as the text none",
     "decks.catalogue:_epiphany",
     'None if row.get("god_type") in EMPTY else row["god_type"].lower()',
     '(row.get("god_type") or "").lower() or None', "no Neutral one"),
    ("the reachable walk keeps no effect",
     "decks.catalogue:_keep_reachable",
     "kept_effects.add(key)", "pass", "in no skill_eff table"),
    ("Sortie's Epiphanies read",
     "decks.catalogue:read",
     'if not row["id"].startswith(SORTIE_EPIPHANY)}', "}",
     "Sortie's Epiphanies are in the deck catalogue"),
    ("the unread-condition check passes",
     "decks.catalogue:Catalogue.problems",
     "if unread:", "if False:", "the condition tables unread"),
    ("a condition's control rows not found",
     "decks.catalogue:_conditions",
     'controls.setdefault(key.rsplit("_", 1)[0], []).append(row)', "pass",
     "read with no condition_control rows"),
    ("the cache serves another build",
     "decks.catalogue:load",
     'if build is not None and data.get("build") != build:', "if False:",
     "serves another build's catalogue"),
    ("a failed save writes over the last cache",
     "decks.catalogue:save",
     'os.fdopen(handle, "wb")', 'open(target, "wb")',
     "a failed save destroyed the last good cache"),
    ("a failed save leaves its temp file",
     "decks.catalogue:save",
     "if os.path.exists(temp):", "if False:",
     "left its temp file behind"),
    ("a missing partner table passes", "decks.catalogue:Catalogue._progress_problems",
     "if not self.partners:", "if False:", "no partner read"),
    ("a lost Ego skill card passes", "decks.catalogue:Catalogue._progress_problems",
     "if lost:", "if False:", "a partner's Ego skill card gone"),
    ("a missing Potential tree passes", "decks.catalogue:Catalogue._progress_problems",
     "if not upgraded:", "if False:", "no Potential node read"),
    ("an upgrade to no card passes", "decks.catalogue:Catalogue._progress_problems",
     "if bare:", "if False:", "the Potential upgrades' cards gone"),
    ("a missing Ego Manifestation table passes",
     "decks.catalogue:Catalogue._progress_problems",
     "if not self.manifestation:", "if False:", "no Ego Manifestation read"),
    ("an unjudged node type passes", "decks.catalogue:Catalogue._progress_problems",
     "if new:", "if False:", "a Potential node type nobody judged"),
    ("an upgrade beside Signature Epiphanies passes",
     "decks.catalogue:Catalogue._progress_problems",
     "if both:", "if False:", "an upgraded card with Signature Epiphanies"),
    ("Ego Manifestation's statuses not kept", "decks.catalogue:_keep_reachable",
     'for rows in data["manifestation"].values():', "for rows in ():",
     "statuses Potential nodes and Ego Manifestation put on"),
    ("the gone statuses' check passes", "decks.catalogue:Catalogue._progress_problems",
     "if gone:", "if False:", "the progress statuses gone"),
    ("follow-up effects not kept", "decks.catalogue:_keep_reachable",
     "todo_effects.update(child for _condition, child in chained(effects[key]))", "pass",
     "follow-up effects"),
    ("the follow-up check passes", "decks.catalogue:Catalogue.problems",
     "if follows:", "if False:", "a follow-up effect gone"),
    ("the Epiphany flag unread", "decks.catalogue:_card",
     '"epiphany": row.get("battle_r_spark_enable_flag") == "YES",', '"epiphany": True,',
     "every card or none"),
    ("the Epiphany flag check passes", "decks.catalogue:Catalogue.problems",
     "if not able or able == len(self.cards):", "if False:",
     "every card read as able to take an Epiphany"),
]
