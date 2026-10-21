"""Deck weights and the deck-building rules, `decks.rules`, and the wire
import they read, `decks.wire`.

Which `savedata_point_define` row prices what is the program's own
reading, and every captured Save Data records what it weighed when made
(`define_point`): each made since RULES_SINCE must weigh exactly that.
Every one is a deck the game accepted, so none made since may raise a
warning either. Older ones, made under rules or cards since changed,
are counted in a note. The capture archive is read too: it holds the
Save Data deleted since, which no loose snapshot has.

The rules are also held to a small catalogue of their own, which needs
no client. A deck breaking each rule must warn with that rule and no
other, and every point rule there has a figure of its own, so a charge
read off the wrong row shows in the total.
"""

import json
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ._harness import SOURCE_ROOT, add_source_to_path, note

NAME = "deck weights and deck-building rules"

# Every Save Data made since this day weighs what `decks.rules` gives.
# Some made before it, in Seasons 1 and 2, weigh otherwise: made under
# rules since changed. A patch that reprices a row reweighs every deck
# made before it, so the day moves to the patch's.
RULES_SINCE = datetime(2026, 7, 1, tzinfo=timezone.utc)

ME = 1001
CLASS, OTHER_CLASS = "class_a", "class_c"
OWN = ("srt1", "srt2", "srt3", "srt4", "uni1", "uni2", "uni3", "uni4")


def _own(kind):
    return f"c_{ME}_{kind}"


# Every figure its own, so a charge read off the wrong row shows.
DISTINCT = {
    "god_r_spark": 2, "cd_get_job": 3, "cd_get_taboo": 5,
    "cd_remove_start": 7, "cd_get_sort_monster_common": 11,
    "cd_get_sort_monster_rare": 13, "cd_get_sort_monster_legend": 17,
    "cd_get_sort_monster_unique": 19, "cd_get_eidolon": 23,
    "cd_transform_default_point": 29, "cd_relic_hammer": 31,
    "relic_reinforce_lux": 37, "relic_reinforce_umbra": 41,
    "relic_reinforce_arena": 43, "cd_copy_revise_by_count": [0, 0, 47],
    "cd_remove_revise_by_count": [0, 53],
}
# Figures the size of the client's, so the warnings' decks stay under
# the cap but where one is built to reach it.
PLAIN = {
    "god_r_spark": 2, "cd_get_job": 2, "cd_get_taboo": 2,
    "cd_remove_start": 2, "cd_get_sort_monster_common": 2,
    "cd_get_sort_monster_rare": 5, "cd_get_sort_monster_legend": 8,
    "cd_get_sort_monster_unique": 10, "cd_get_eidolon": 2,
    "cd_transform_default_point": 0, "cd_relic_hammer": 1,
    "relic_reinforce_lux": 0, "relic_reinforce_umbra": 0,
    "relic_reinforce_arena": 0, "cd_copy_revise_by_count": [0, 0, 4],
    "cd_remove_revise_by_count": [0],
}


def _card(sort, category="CARD_SKILL", cost=1, **fields):
    return {"name": "", "sort": sort, "category": category, "rarity": "",
            "cost": cost, "talents": [], "classes": [], "replace_cost": [],
            "tags": [], "effects": [], **fields}


def _rule(god=None, **conditions):
    return {"god": god, "classes": [], "categories": [], "cost_min": -1,
            "cost_max": -1, "include_talents": [], "exclude_talents": [],
            "tags": [], "exclude_tags": [], **conditions}


def _catalogue(points):
    from decks.catalogue import Catalogue
    # As in the client, the Basic cards and the Mythic one take no Epiphany.
    cards = {_own(kind): _card("SORT_START", "CARD_ATK", epiphany=False)
             for kind in OWN[:3]}
    cards.update({_own(kind): _card("SORT_UNIQUE", epiphany=kind != "uni4")
                  for kind in OWN[3:]})
    cards.update({
        _own("srt4_rsp1"): _card("SORT_UNIQUE", "CARD_ATK", 2,
                                 talents=["TALENT_ORIGIN"]),
        _own("srt4_rsp2"): _card("SORT_UNIQUE"),
        "card_ne_a": _card("SORT_NEUTRAL", "CARD_ATK", replace_cost=[0],
                           classes=[CLASS, "class_b"]),
        "card_ne_c": _card("SORT_NEUTRAL", classes=[OTHER_CLASS]),
        "card_enc_a": _card("SORT_ETC"),
        "card_mon_rare": _card("SORT_MONSTER_UNIQUE", rarity="RARITY_RARE"),
        "card_ta_a": _card("SORT_TABOO"),
        "card_eid_a": _card("SORT_EIDOLON", talents=["TALENT_ORIGIN"]),
        "card_eid_b": _card("SORT_EIDOLON", talents=["TALENT_ORIGIN"]),
        "card_ds04_des_10012": _card("SORT_DESIRE"),
        "card_ds04_des_20011": _card("SORT_DESIRE"),
        "card_ds05_a_b1_1_1": _card("SORT_MEMORY", "CARD_POWER", 0,
                                    talents=["TALENT_MEMORY"]),
        "card_ds05_a_b2_1_1": _card("SORT_MEMORY", "CARD_POWER", 0,
                                    talents=["TALENT_MEMORY"]),
        "card_new_a": _card("SORT_NEW_SEASON"),
    })
    effect = {"classes": [], "categories": [], "cost_min": -1, "cost_max": -1}
    return Catalogue({
        "cards": cards,
        "versions": {_own("srt4"): {"1": _own("srt4_rsp1"),
                                    "2": _own("srt4_rsp2")}},
        "epiphanies": {
            "c_atk_free": _rule(categories=["CARD_ATK"], cost_max=0),
            "c_skill": _rule(categories=["CARD_SKILL"]),
            "c_retain": _rule(include_talents=["TALENT_RETAIN"]),
            "c_tagged": _rule(tags=["tag_x"]),
            "c_class_b": _rule(classes=["class_b"]),
            "add_r_spark_vitor_1": _rule("vitor", categories=["CARD_ATK"],
                                         cost_min=2),
            "add_r_spark_vitor_free": _rule("vitor", categories=["CARD_ATK"],
                                            cost_max=0),
            "add_r_spark_vitor_skill": _rule("vitor", categories=["CARD_SKILL"]),
        },
        "persona": {
            "slots": {"card_eid_a": {"count": 2, "tags": []},
                      "card_eid_b": {"count": 2, "tags": []}},
            "effects": {"ds03_lux_0001": dict(effect, tags=["tag_y"]),
                        "ds03_umbra_0002": dict(effect, tags=[],
                                                categories=["CARD_ATK"])},
        },
        "points": points,
        "combatants": {str(ME): {"class": CLASS, "playable": True,
                                 "name": "Fixture"}},
        "classes": {CLASS: "Striker", "class_b": "Vanguard",
                    OTHER_CLASS: "Ranger"},
        "equipment": {"eq_a": {}, "eq_b": {}},
        "buffs": {"rr_lux_1": {"type": "LUX"}, "rr_arena_1": {"type": "ARENA"}},
        "mutations": {"mut_a": {}},
        # A partner whose passive works with the fixture's class, and one
        # whose passive needs another.
        "partners": {"7": {"name": "Same", "class": CLASS, "card": "p_7"},
                     "8": {"name": "Other", "class": OTHER_CLASS, "card": "p_8"}},
    })


def _deck(*extra, drop=(), removed=(), equipment=(), combatant=ME,
          mutation=None, partner=None):
    """The fixture Combatant's eight starting cards but `drop`, then
    `extra`, each a card id or a `DeckCard`."""
    from decks.model import Deck, DeckCard
    cards = [DeckCard(_own(kind)) for kind in OWN if kind not in drop]
    cards += [card if isinstance(card, DeckCard) else DeckCard(card)
              for card in extra]
    return Deck(combatant=combatant, cards=cards, removed=list(removed),
                equipment=list(equipment), mutation=mutation, partner=partner)


def _weight_cases():
    from decks.model import DeckCard as C, Equipment
    copies = [C(_own("uni1"), copy=True) for _ in range(4)]
    neutral_and_copies = ["card_ne_a", C("card_ne_a", copy=True),
                          C("card_ne_a", copy=True)]
    return [
        ("the starting deck", _deck(), 0, []),
        ("a Basic card deleted", _deck(drop=["srt1"]), 7, []),
        ("the preset Signature card deleted", _deck(drop=["srt4"]), 7, []),
        ("another Signature card deleted", _deck(drop=["uni1"]), 0, []),
        ("a preset card listed as removed yet back in the deck",
         _deck(removed=[_own("srt4")]), 0, []),
        ("a preset card listed with the cards as out",
         _deck(C(_own("srt1"), removed=True), drop=["srt1"]), 7, []),
        ("a Neutral card", _deck("card_ne_a"), 3, []),
        ("an Event Neutral card", _deck("card_enc_a"), 3, []),
        ("a Rare Monster card", _deck("card_mon_rare"), 13, []),
        ("a Forbidden card", _deck("card_ta_a"), 5, []),
        ("a Persona card", _deck("card_eid_a"), 23, []),
        ("a Desire card", _deck("card_ds04_des_10012"), 0, []),
        ("a Memory card", _deck("card_ds05_a_b1_1_1"), 0, []),
        ("a card of a kind nothing prices", _deck("card_new_a"), 0,
         ["card_new_a"]),
        ("a card the client lacks", _deck("card_zz"), 0, ["card_zz"]),
        ("a Divine Epiphany",
         _deck(C(_own("srt4"), version=1, divine="add_r_spark_vitor_1"),
               drop=["srt4"]), 2, []),
        ("three duplicates of a Signature card", _deck(*copies[:3]), 47, []),
        ("four duplicates of a Signature card", _deck(*copies), 94, []),
        ("a Neutral card and two copies of it", _deck(*neutral_and_copies),
         9, []),
        ("three Basic cards deleted, a Neutral card and two copies of it",
         _deck(*neutral_and_copies, drop=OWN[:3]), 30, []),
        ("a converted card", _deck(C("card_ne_a", converted=True)), 32, []),
        ("two removals of its own and an added card's",
         _deck(drop=["srt1", "srt2"],
               removed=[_own("srt1"), _own("srt2"), "card_ne_a"]), 67, []),
        ("a hammer blessing",
         _deck(equipment=[Equipment("eq_a", blessings=("eq_b",))]), 31, []),
        ("two Equipment Buffs",
         _deck(equipment=[Equipment("eq_a", buffs=("rr_lux_1",
                                                   "rr_arena_1"))]), 80, []),
    ]


def _weights_report():
    """Each charge comes off its own row, and only where it is due."""
    from decks import rules
    catalogue = _catalogue(DISTINCT)
    out = []
    for what, deck, total, assumed in _weight_cases():
        weighs = rules.weight(deck, catalogue)
        if weighs.total != total:
            out.append(f"{what}: weighs {weighs.total}, not {total} "
                       f"({weighs.parts}). See `weight` in decks/rules.py "
                       f"and docs/decks.md, Deck points.")
        if weighs.assumed != assumed:
            out.append(f"{what}: priced as free by assumption "
                       f"{weighs.assumed}, not {assumed}. See FREE_SORTS "
                       f"in decks/rules.py.")
        if weighs.points != weighs.total * 10:
            out.append(f"{what}: {weighs.points} points shown for "
                       f"{weighs.total} in the client's unit, tens.")
    return out


def _warning_cases():
    from decks.model import DeckCard as C, Equipment
    srt4 = _own("srt4")
    return [
        ("the starting deck", _deck(), set()),
        ("an unknown Combatant", _deck(combatant=9999), {"unknown"}),
        ("a card the client lacks", _deck("card_zz"), {"unknown"}),
        ("a Signature Epiphany the card lacks",
         _deck(C(srt4, version=5), drop=["srt4"]), {"unknown"}),
        ("an unknown Neutral Epiphany",
         _deck(C("card_ne_a", neutral="c_zz")), {"unknown"}),
        ("an unknown Divine Epiphany",
         _deck(C(srt4, divine="add_r_spark_zz"), drop=["srt4"]), {"unknown"}),
        ("an unknown Persona effect",
         _deck(C("card_eid_a", persona=("ds03_zz",))), {"unknown"}),
        ("unknown Equipment", _deck(equipment=[Equipment("eq_zz")]),
         {"unknown"}),
        ("an unknown Equipment Buff",
         _deck(equipment=[Equipment("eq_a", buffs=("rr_zz",))]), {"unknown"}),
        ("an unknown hammer blessing",
         _deck(equipment=[Equipment("eq_a", blessings=("eq_zz",))]),
         {"unknown"}),
        ("an unknown Mutation", _deck(mutation="mut_zz"), {"unknown"}),
        ("a deck over the cap",
         _deck(*["card_ne_a"] * 5, drop=OWN[:4],
               equipment=[Equipment("eq_a", blessings=("eq_b",))]), {"cap"}),
        ("a deck at the cap", _deck(*["card_ne_a"] * 5, drop=OWN[:4]), set()),
        ("a card the class may not hold", _deck("card_ne_c"), {"class"}),
        ("a Neutral Epiphany fitting only by the replace cost",
         _deck(C("card_ne_a", neutral="c_atk_free")), set()),
        ("a Neutral Epiphany for another card type",
         _deck(C("card_ne_a", neutral="c_skill")), {"neutral"}),
        ("a Neutral Epiphany needing a keyword the card lacks",
         _deck(C(_own("uni1"), neutral="c_retain"), drop=["uni1"]),
         {"neutral"}),
        ("a Neutral Epiphany needing a tag the card lacks",
         _deck(C(_own("uni1"), neutral="c_tagged"), drop=["uni1"]),
         {"neutral"}),
        ("a Neutral Epiphany for another class",
         _deck(C("card_ne_a", neutral="c_class_b")), {"neutral"}),
        ("an unknown Combatant's class-bound Epiphany",
         _deck(C("card_ne_a", neutral="c_class_b"), combatant=9999),
         {"unknown"}),
        ("a Divine Epiphany fitting the Signature Epiphany version",
         _deck(C(srt4, version=1, divine="add_r_spark_vitor_1"),
               drop=["srt4"]), set()),
        ("a Divine Epiphany on a base card it does not fit",
         _deck(C(srt4, divine="add_r_spark_vitor_1"), drop=["srt4"]),
         {"divine"}),
        ("a Divine Epiphany the replace cost would fit",
         _deck(C("card_ne_a", divine="add_r_spark_vitor_free")), {"divine"}),
        ("a Neutral Epiphany on a card that takes one",
         _deck(C(_own("uni1"), neutral="c_skill"), drop=["uni1"]), set()),
        ("a Neutral Epiphany on a card that takes none",
         _deck(C(_own("uni4"), neutral="c_skill"), drop=["uni4"]), {"neutral"}),
        ("a Divine Epiphany on a card that takes one",
         _deck(C(_own("uni1"), divine="add_r_spark_vitor_skill"), drop=["uni1"]),
         set()),
        ("a Divine Epiphany on a card that takes none",
         _deck(C(_own("uni4"), divine="add_r_spark_vitor_skill"), drop=["uni4"]),
         {"divine"}),
        ("a Persona with one effect twice",
         _deck(C("card_eid_a", persona=("ds03_lux_0001",) * 2)), set()),
        ("a Persona with three effects",
         _deck(C("card_eid_a", persona=("ds03_lux_0001",) * 3)), {"persona"}),
        ("a Persona effect for another card type",
         _deck(C("card_eid_a", persona=("ds03_umbra_0002",))), {"persona"}),
        ("a Desire card at its level",
         _deck(C("card_ds04_des_10012", desire={48: 1, 49: 1})), set()),
        ("a Desire card short of its level",
         _deck(C("card_ds04_des_10012", desire={48: 1})), {"desire"}),
        ("two Persona cards", _deck("card_eid_a", "card_eid_b"),
         {"one_per_deck"}),
        ("two Desire cards",
         _deck(C("card_ds04_des_10012", desire={48: 2}),
               C("card_ds04_des_20011", desire={49: 1})), {"one_per_deck"}),
        ("two Memory cards", _deck("card_ds05_a_b1_1_1", "card_ds05_a_b2_1_1"),
         {"one_per_deck"}),
        ("three duplicates",
         _deck(*[C(_own("uni1"), copy=True) for _ in range(3)]), set()),
        ("four duplicates",
         _deck(*[C(_own("uni1"), copy=True) for _ in range(4)]), {"copies"}),
        ("a duplicate of a Memory card",
         _deck("card_ds05_a_b1_1_1", C("card_ds05_a_b1_1_1", copy=True)),
         {"no_copy", "one_per_deck"}),
        ("a Unique version twice",
         _deck(C(srt4, version=1), C(srt4, version=1, copy=True),
               drop=["srt4"]), {"unique"}),
        ("a Unique version beside one that is not",
         _deck(C(srt4, version=1), C(srt4, version=2, copy=True),
               drop=["srt4"]), set()),
        ("six removals of its own",
         _deck(drop=["srt1", "srt2", "uni1", "uni2", "uni3", "uni4"],
               removed=[_own(k) for k in ("srt1", "srt2", "uni1", "uni2",
                                          "uni3", "uni4")]), {"removals"}),
        ("five removals of its own and an added card's",
         _deck(drop=["srt1", "uni1", "uni2", "uni3", "uni4"],
               removed=[_own(k) for k in ("srt1", "uni1", "uni2", "uni3",
                                          "uni4")] + ["card_ne_a"]), set()),
        ("a partner of the Combatant's class", _deck(partner=7), set()),
        ("a partner whose passive needs another class", _deck(partner=8),
         {"partner"}),
        ("an unknown partner", _deck(partner=99), {"unknown"}),
        ("no partner, by the deck's own choice", _deck(partner=0), set()),
    ]


def _warnings_report():
    """Each rule speaks up about the deck built to break it, and about
    nothing else."""
    from decks import rules
    catalogue = _catalogue(PLAIN)
    out = []
    for what, deck, expected in _warning_cases():
        found = rules.warnings(deck, catalogue)
        raised = {warning.rule for warning in found}
        if raised != expected:
            out.append(f"{what}: warns {sorted(raised) or 'nothing'}, not "
                       f"{sorted(expected) or 'nothing'} "
                       f"({[warning.text for warning in found]}). See "
                       f"`warnings` in decks/rules.py and docs/decks.md, "
                       f"Deck-building rules.")
    placed = [warning.card for warning in
              rules.warnings(_deck("card_ne_c"), catalogue)]
    if placed != [len(OWN)]:
        out.append(f"the class warning points at card {placed}, not at the "
                   f"card that breaks it ({len(OWN)}).")
    from decks.model import CombatantState
    owned = {ME: CombatantState(partner=8)}
    if {w.rule for w in rules.warnings(_deck(), catalogue, owned)} != {"partner"}:
        out.append("an owned Combatant's captured partner, whose passive needs "
                   "another class, raises no warning where the deck names no "
                   "partner of its own (plan D8, D61). See `Deck.state`.")
    if rules.warnings(_deck(partner=7), catalogue, owned):
        out.append("the deck's own partner does not stand over the owned "
                   "Combatant's captured one.")
    return out


def _wire_report():
    """A Save Data's fields land where the model holds them, its
    account id nowhere, and the newest capture of each wins, the
    archive's included."""
    from decks import wire
    out = []
    card = wire.deck_card({"res_id": _own("srt4"),
                           "r_spark_res_id": f"rsp3_{_own('srt4')}",
                           "r_spark_category": "CATEGORY_UNIQUE",
                           "r_spark_god": "add_r_spark_vitor_1",
                           "copy_by_count": True})
    if (card.version, card.neutral, card.divine, card.copy) != (
            3, None, "add_r_spark_vitor_1", True):
        out.append(f"a Signature Epiphany 3 with a Divine one, a duplicate, "
                   f"reads as {card}. See `deck_card` in decks/wire.py.")
    card = wire.deck_card({"res_id": "card_ne_a", "r_spark_res_id": "c04011",
                           "r_spark_category": "CATEGORY_PUBLIC"})
    if (card.version, card.neutral) != (0, "c04011"):
        out.append(f"a Neutral Epiphany reads as {card}.")
    # A run over its cap is saved under it: a removed card put back
    # keeps the run's `remove_by_count`, and is in the deck all the same.
    back = wire.deck_card({"res_id": _own("srt1"), "remove_by_count": True,
                           "apply_log": {"restore_reason": "pt_overflow"}})
    gone = wire.deck_card({"res_id": _own("srt2"), "remove_by_count": True})
    if back.removed or not gone.removed:
        out.append(f"a Basic card the game put back over the cap reads "
                   f"removed={back.removed}, and one the run removed "
                   f"removed={gone.removed}: a card put back is in the deck "
                   f"(`wire.RESTORED`), and read as removed it is charged as "
                   f"a preset card deleted.")
    if wire.deck_card({"res_id": "card_ds04_des_20011"}).desire != {49: 1}:
        out.append("a level-1 Desire card the run never raised records no "
                   "points, and does not read as holding its own keyword's "
                   "one, so its team's Desire sums come out short. See "
                   "`_desire` in decks/wire.py.")
    if wire.deck_card({"res_id": "card_ds04_des_20012",
                       "desire_talent_counts": {"48": 1, "49": 1}}
                      ).desire != {48: 1, 49: 1}:
        out.append("a Desire card's recorded points do not read as "
                   "recorded.")
    account = 987654321
    deck = wire.deck_from_savedata({
        "id": 5, "user_id": account, "char_res_id": ME, "name": "Mine",
        "card_datas": [{"res_id": _own("srt1"), "user_id": account}],
        "equip_datas": [{"res_id": "eq_a", "star_grade": 3}]})
    if str(account) in repr(deck):
        out.append("the account's id (a Save Data's user_id) was carried "
                   "into a deck, which the program saves and may share. "
                   "See `deck_from_savedata` in decks/wire.py.")

    def snapshot(name):
        return {"inventory": {"savedata": [{"id": 1, "char_res_id": ME,
                                            "name": name}]}}
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        older = folder / "memory_fragments_20260101_000000.json"
        older.write_text(json.dumps({"inventory": {"savedata": [
            {"id": 9, "char_res_id": ME, "name": "deleted since"}]}}),
            encoding="utf-8")
        with tarfile.open(folder / "archived_captures.tar.xz", "w:xz") as tf:
            tf.add(older, arcname=older.name)
        older.unlink()
        for stamp, name in (("20260201_000000", "first"),
                            ("20260301_000000", "newest")):
            (folder / f"memory_fragments_{stamp}.json").write_text(
                json.dumps(snapshot(name)), encoding="utf-8")
        loose = wire.captured_decks(folder)
        if {key: deck.name for key, deck in loose.items()} != {"1": "newest"}:
            out.append(f"the loose snapshots give "
                       f"{ {k: d.name for k, d in loose.items()} }, not the "
                       f"newest capture of each Save Data. See "
                       f"`captured_decks` in decks/wire.py.")
        both = wire.captured_decks(folder, archived=True)
        if {key: deck.name for key, deck in both.items()} != {
                "1": "newest", "9": "deleted since"}:
            out.append(f"with the capture archive, the Save Data read are "
                       f"{ {k: d.name for k, d in both.items()} }: the "
                       f"archive's are not read, or not as older than the "
                       f"loose ones. See `_snapshots` in decks/wire.py.")
    return out


def _day(stamp):
    return datetime.fromtimestamp(stamp or 0, timezone.utc).date()


def _captured_report():
    """Every captured Save Data made since RULES_SINCE weighs what it
    recorded and breaks no rule."""
    import game_client
    from decks import catalogue, rules, wire
    install = game_client.find_install()
    if install is None:
        note("no game client installed, so no captured Save Data was "
             "weighed against its record")
        return []
    decks = wire.captured_decks(SOURCE_ROOT / "snapshots", archived=True)
    if not decks:
        note("no captured Save Data, so no deck was weighed against its "
             "record")
        return []
    cat = catalogue.Catalogue(catalogue.read(game_client.Client(install)))
    out = []
    older = 0
    for deck in sorted(decks.values(), key=lambda d: d.created_at or 0):
        weighs = rules.weight(deck, cat)
        warned = rules.warnings(deck, cat)
        if (deck.created_at or 0) < RULES_SINCE.timestamp():
            older += weighs.total != deck.recorded_weight or bool(warned)
            continue
        held = cat.combatant(deck.combatant) or {}
        who = (f"Save Data {deck.source_id} ({held.get('name') or deck.combatant}, "
               f"made {_day(deck.created_at)})")
        if weighs.total != deck.recorded_weight:
            out.append(f"{who} weighs {weighs.points} points by decks.rules "
                       f"but recorded {(deck.recorded_weight or 0) * 10}: "
                       f"{weighs.parts}. A patch repricing a row reweighs "
                       f"every deck made before it (move RULES_SINCE to its "
                       f"day); otherwise decks/rules.py misreads which row "
                       f"prices what. docs/decks.md, Deck points.")
        for warning in warned:
            out.append(f"{who} raises the {warning.rule!r} warning, yet the "
                       f"game accepted it: {warning.text} See decks/rules.py "
                       f"and docs/decks.md, Deck-building rules.")
    if older:
        note(f"{older} Save Data made before {RULES_SINCE.date()} weigh "
             f"otherwise than they recorded, or raise a warning: made under "
             f"rules or cards since changed")
    return out


def run():
    add_source_to_path()
    return (_weights_report() + _warnings_report() + _wire_report()
            + _captured_report())


FAULTS = [
    ("a copy pays no add cost", "decks.rules:weight",
     "if held.own:", "if held.own or held.copy:",
     "a Neutral card and two copies of it"),
    ("the copy surcharge's last figure not reused", "decks.rules:_by_count",
     "figures[min(i, len(figures) - 1)]",
     "(figures[i] if i < len(figures) else 0)",
     "four duplicates of a Signature card"),
    ("a preset card back in the deck charged", "decks.rules:weight",
     "if card_id not in held_ids:",
     "if card_id not in held_ids or card_id in deck.removed:",
     "listed as removed yet back in the deck"),
    ("Event Neutral cards free", "decks.rules:NEUTRAL_SORTS",
     '"SORT_NEUTRAL", "SORT_ETC"', '"SORT_NEUTRAL",',
     "an Event Neutral card"),
    ("Desire cards free by assumption", "decks.rules:FREE_SORTS",
     '"SORT_DESIRE",', "", "a Desire card: priced as free by assumption"),
    ("a Monster priced as Common", "decks.rules:add_cost",
     'row = f"cd_get_sort_monster_{rarity}"',
     'row = "cd_get_sort_monster_common"', "a Rare Monster card"),
    ("a Divine Epiphany free", "decks.rules:weight",
     'charge("divine", held.card, catalogue.point("god_r_spark"))',
     'charge("divine", held.card, 0)', "a Divine Epiphany"),
    ("every Buff priced as Lux", "decks.rules:weight",
     'catalogue.point(f"relic_reinforce_{kind.lower()}")',
     'catalogue.point("relic_reinforce_lux")', "two Equipment Buffs"),
    ("every removal counted", "decks.rules:own_removals",
     ' if card_id.startswith("c_")]', "]",
     "five removals of its own and an added card's"),
    ("a Neutral Epiphany reads the printed cost", "decks.rules:warnings",
     'card["replace_cost"] or [card["cost"]]', '[card["cost"]]',
     "fitting only by the replace cost"),
    ("a Divine Epiphany held to the base card", "decks.rules:warnings",
     'misfit = _misfits(rule, version, klass, [version["cost"]])',
     'misfit = _misfits(rule, card, klass, [card["cost"]])',
     "fitting the Signature Epiphany version"),
    ("a Divine Epiphany reads the replace cost", "decks.rules:warnings",
     'misfit = _misfits(rule, version, klass, [version["cost"]])',
     'misfit = _misfits(rule, version, klass, version["replace_cost"] '
     'or [version["cost"]])', "the replace cost would fit"),
    ("a Persona effect's tags made a condition", "decks.rules:warnings",
     "tags=False)", "tags=True)", "a Persona with one effect twice"),
    ("Unique read off the base card", "decks.rules:warnings",
     'if UNIQUE in version.get("talents", ()):',
     'if UNIQUE in card.get("talents", ()):', "a Unique version twice"),
    ("the cap let through", "decks.rules:warnings",
     "if weighs.total > CAP:", "if weighs.total > CAP + 1:",
     "a deck over the cap"),
    ("the cap reached counts as over", "decks.rules:warnings",
     "if weighs.total > CAP:", "if weighs.total >= CAP:",
     "a deck at the cap"),
    ("a fourth duplicate let through", "decks.rules:warnings",
     "if copies > MAX_COPIES:", "if copies > MAX_COPIES + 1:",
     "four duplicates"),
    ("a second Persona let through", "decks.rules:warnings",
     'if kinds[card["sort"]] == 2:', 'if kinds[card["sort"]] == 3:',
     "two Persona cards"),
    ("Desire points unchecked", "decks.rules:warnings",
     "if desire and sum(held.desire.values()) != desire[1]:", "if False:",
     "short of its level"),
    ("an Epiphany's class unchecked", "decks.rules:_misfits",
     'if rule.get("classes") and klass and klass not in rule["classes"]:',
     "if False:", "a Neutral Epiphany for another class"),
    ("an Epiphany's class held with no class known", "decks.rules:_misfits",
     'if rule.get("classes") and klass and klass not in rule["classes"]:',
     'if rule.get("classes") and klass not in rule["classes"]:',
     "an unknown Combatant's class-bound Epiphany"),
    ("the class unchecked", "decks.rules:warnings",
     'if klass and card["classes"] and klass not in card["classes"]:',
     "if False:", "a card the class may not hold"),
    ("a card put back read as removed", "decks.wire:deck_card",
     'and not (card_data.get("apply_log") or {}).get(RESTORED),', ",",
     "a card put back is in the deck"),
    ("a level-1 Desire card's point left out", "decks.wire:_desire",
     "if not points and held and held[1] == 1:", "if False:",
     "level-1 Desire card"),
    ("the account's id carried into a deck",
     "decks.wire:deck_from_savedata",
     'name=str(savedata.get("name") or ""),',
     'name=str(savedata.get("name") or ""), '
     'note=str(savedata.get("user_id")),', "the account's id"),
    ("the capture archive not read", "decks.wire:_snapshots",
     "if archived:", "if False:", "the archive's are not read"),
    ("the oldest capture wins", "decks.wire:_snapshots",
     'for path in sorted(folder.glob(SNAPSHOT_PREFIX + "*.json")):',
     'for path in sorted(folder.glob(SNAPSHOT_PREFIX + "*.json"), '
     'reverse=True):', "not the newest capture"),
    ("every deck one heavier", "decks.rules:weight",
     "    return out", "    out.total += 1\n    return out",
     "but recorded"),
    ("a partner's class unchecked", "decks.rules:warnings",
     'elif partner and klass and partner["class"] and partner["class"] != klass:',
     "elif False:", "a partner whose passive needs another class"),
    ("an unknown partner let through", "decks.rules:warnings",
     "if partner_id and partner is None:", "if False:", "an unknown partner"),
    ("the owned Combatant's partner ignored", "decks.rules:warnings",
     "partner_id = deck.state(owned).partner", "partner_id = deck.partner",
     "an owned Combatant's captured partner"),
    ("a Neutral Epiphany let onto a card that takes none", "decks.rules:warnings",
     'elif not card.get("epiphany", True):\n                warn("neutral"',
     'elif False:\n                warn("neutral"',
     "a Neutral Epiphany on a card that takes none"),
    ("a Divine Epiphany let onto a card that takes none", "decks.rules:warnings",
     'elif not card.get("epiphany", True):\n                warn("divine"',
     'elif False:\n                warn("divine"',
     "a Divine Epiphany on a card that takes none"),
]
