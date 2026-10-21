"""The decks the capture keeps, as `model.Deck`s.

A Save Data (a deck kept after a Chaos run) arrives whole in every
snapshot's `inventory.savedata`, one entry per deck; `docs/decks.md`,
*The wire*, says what each field holds. The account's own id rides on
every one (`user_id`) and is never read.

Build Presets (the in-game deck builder's) are not captured yet.
"""

import json
from pathlib import Path

from .model import Deck, DeckCard, Equipment, desire_of

# A Signature Epiphany's id on the wire: `rsp<N>_<card>`.
SIGNATURE_PREFIX = "rsp"
SNAPSHOT_PREFIX = "memory_fragments_"
# **A card the game put back when the deck was saved is in it**, whatever
# else it carries. A run that ends over its cap (`max_define_point`) is
# saved with cards put back and others taken out, each saying why in its
# `apply_log` (`pt_overflow`): a removed card it restores keeps the
# `remove_by_count` it had in the run, and read by that alone it is a
# preset card deleted, charged for and missing from the deck.
RESTORED = "restore_reason"


def _signature(card_data):
    """The Signature Epiphany a card carries, 1 to 5, else 0."""
    held = card_data.get("r_spark_res_id") or ""
    if card_data.get("r_spark_category") != "CATEGORY_UNIQUE" \
            or not held.startswith(SIGNATURE_PREFIX):
        return 0
    try:
        return int(held[len(SIGNATURE_PREFIX)])
    except (ValueError, IndexError):
        return 0


def _desire(card_id, card_data):
    """A Desire card's points per keyword. One the run never raised
    records none: at level 1 it holds its own keyword's one."""
    points = {int(key): int(value) for key, value
              in (card_data.get("desire_talent_counts") or {}).items()}
    held = desire_of(card_id)
    if not points and held and held[1] == 1:
        points = {held[0]: 1}
    return points


def deck_card(card_data):
    """A Save Data's `card_datas` entry as a `DeckCard`."""
    public = card_data.get("r_spark_category") == "CATEGORY_PUBLIC"
    card_id = str(card_data.get("res_id") or "")
    return DeckCard(
        card=card_id,
        version=_signature(card_data),
        neutral=(card_data.get("r_spark_res_id") or None) if public else None,
        divine=card_data.get("r_spark_god") or None,
        copy=bool(card_data.get("copy_by_count")),
        removed=bool(card_data.get("remove_by_count"))
        and not (card_data.get("apply_log") or {}).get(RESTORED),
        persona=tuple(card_data.get("eidolon_reward_ids") or ()),
        desire=_desire(card_id, card_data),
        added_talents=tuple(int(t) for t in card_data.get("add_talents") or ()),
        converted=bool(card_data.get("is_transform_card")),
        converted_away=bool(card_data.get("is_erased_transform_card")),
        conversion=card_data.get("transform_card_id"),
    )


def deck_from_savedata(savedata):
    """A Save Data as a `Deck`."""
    return Deck(
        combatant=int(savedata.get("char_res_id") or 0),
        cards=[deck_card(c) for c in savedata.get("card_datas") or ()],
        removed=[str(c.get("res_id") or "")
                 for c in savedata.get("remove_card_datas") or ()],
        equipment=[Equipment(relic=str(e.get("res_id") or ""),
                             stars=int(e.get("star_grade") or 1),
                             buffs=tuple(e.get("reinforce_res_ids") or ()),
                             blessings=tuple(e.get("bless_relic_res_ids") or ()))
                   for e in savedata.get("equip_datas") or ()],
        mutation=savedata.get("corruption_res_id") or None,
        name=str(savedata.get("name") or ""),
        source="save data",
        source_id=str(savedata.get("id") or ""),
        chaos=savedata.get("chaos_res_id") or None,
        recorded_weight=savedata.get("define_point"),
        recorded_cap=savedata.get("max_define_point"),
        created_at=savedata.get("createAt"),
    )


def savedata_decks(snapshot):
    """Every Save Data in one snapshot, as `Deck`s."""
    held = (snapshot.get("inventory") or {}).get("savedata") or ()
    return [deck_from_savedata(sd) for sd in held if isinstance(sd, dict)]


def _snapshots(folder, archived):
    """Every snapshot in `folder`, oldest first: with `archived`, the
    capture archive's first (stored oldest first), then the loose ones,
    whose names are their capture times. One that does not read is
    passed over."""
    if archived:
        from capture import archive
        for _name, handle in archive.stream_members(folder, SNAPSHOT_PREFIX):
            try:
                yield json.loads(handle.read().decode("utf-8"))
            except ValueError:
                continue
    for path in sorted(folder.glob(SNAPSHOT_PREFIX + "*.json")):
        try:
            yield json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue


def captured_decks(snapshots_dir, archived=False):
    """{Save Data id: Deck}, each Save Data as the newest snapshot
    holding it has it: across the loose snapshots, and with `archived`
    the capture archive's too, which hold the Save Data deleted since."""
    out = {}
    for snapshot in _snapshots(Path(snapshots_dir), archived):
        for deck in savedata_decks(snapshot):
            out[deck.source_id] = deck
    return out
