"""Every item's icon and rarity plate resolve to a file that exists.

Both failures here are SILENT. A missing icon falls back to text, so a
mistyped filename shows a name and a number where a picture should be
and nothing says why. A rarity that resolves to no plate draws the icon
with no background at all, which looks like a deliberately plateless
item rather than a typo.

The rarity is DERIVED for 57 of the ids: a shaped row states a tier and
`TIER_RARITY` prices the word. So one unpriced tier word costs a whole
family its plates at once, and the only thing that would show it is
opening the tab and noticing.

No Tk: the tables and the files are all this needs.
"""

from ._harness import add_source_to_path, SOURCE_ROOT

NAME = "item art"


def run():
    add_source_to_path()
    from game_data.constants import (
        ITEM_TABLES, NAME_RARITY, RARITY_PLATES, TIER_RARITY, item_art,
    )
    from ui.utils.image_utils import RARITY_DIR

    images = SOURCE_ROOT / "images"
    failures = []

    # Every rarity word anyone can produce has a plate, and the plate
    # is on disk.
    for source, words in (("TIER_RARITY", set(TIER_RARITY.values())),
                          ("NAME_RARITY", set(NAME_RARITY.values()))):
        for word in sorted(words):
            plate = RARITY_PLATES.get(word)
            if plate is None:
                failures.append(
                    f"{source} gives the rarity {word!r}, which "
                    f"RARITY_PLATES does not name a plate for. The icon "
                    f"would draw with no background and nothing would say "
                    f"the word was wrong."
                )
            elif not (images / RARITY_DIR / f"bg_item_rarity_{plate}.png").exists():
                failures.append(
                    f"the {word!r} plate is bg_item_rarity_{plate}.png, "
                    f"which is not in images/{RARITY_DIR}/."
                )

    # Every id in every table resolves, and its icon is on disk.
    seen = set()
    for table in ITEM_TABLES:
        for res_id, row in table.items():
            if res_id in seen:
                failures.append(f"res_id {res_id} appears in two tables")
            seen.add(res_id)
            art = item_art(res_id)
            if art is None:
                failures.append(
                    f"res_id {res_id} is in a table as {row!r} but names no "
                    f"`.png`, so `item_art` cannot find its icon."
                )
                continue
            if not (images / art.icon).exists():
                failures.append(
                    f"res_id {res_id} names {art.icon!r}, which is not in "
                    f"images/. A missing icon falls back to text rather "
                    f"than raising."
                )

    # A tier word no table prices costs its whole family their plates.
    for table in ITEM_TABLES:
        for res_id, row in table.items():
            icons = [i for i, f in enumerate(row)
                     if isinstance(f, str) and f.endswith(".png")]
            if not icons or icons[0] < 2 or len(row) > icons[0] + 1:
                continue                     # named, or states its own
            tier = row[1]
            if tier not in TIER_RARITY:
                failures.append(
                    f"res_id {res_id} is tier {tier!r}, which TIER_RARITY "
                    f"does not price. Every id of that tier draws with no "
                    f"plate, and only opening the tab would show it."
                )

    return failures
