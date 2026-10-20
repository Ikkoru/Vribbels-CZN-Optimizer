"""The deck catalogue, as `decks.catalogue` reads it off the game client.

A patch that renames or repurposes a column misreads quietly: the Deck
Builder then prices and warns from wrong data, and nothing fails.
`Catalogue.problems` is the read checking itself. This holds the
installed client's read to it, shows that each of its checks speaks up
about the misread it guards, and that nothing Sortie-only got in.

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
]
