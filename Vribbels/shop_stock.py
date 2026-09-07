"""What a snapshot says about each shop product.

`shop_list` is one row per product id: `{count, reset_time,
total_count}`. Two of the three are settled, one is not.

* **`total_count` counts UP for the life of the account.** Buying one
  moved it by exactly one, twice.
* **`reset_time` is written on every PURCHASE**, not on the shop's
  period boundary -- it came back as the server time of the buy in all
  three purchases captured.
* **`count` is NOT the stock remaining.** It survived a purchase
  unchanged twice, and one row read 5 before a purchase and 1 after.

The reading that fits every observation is that `count` is the number
BOUGHT in the current period, reset LAZILY -- a row untouched since
last period still carries last period's tally, and the client works out
the stock from `reset_time` against the shop's own period. **That is a
hypothesis.** It makes a login capture's `count` unreliable, which is
why `remaining` returns None rather than a number for a row whose
period has rolled over since it was last touched. See
`docs/wire_hunt.md`.

Nothing on the wire has been found that says which products reset
weekly and which monthly, so `PERIODS` below is hand-written from the
game's own screens.

No Tk and no managers: this takes the snapshot dict and returns data.
"""

FIELD = "shop_list"

# Product id prefix -> the shop it belongs to. The Checklist groups its
# sub-rows by these.
SHOPS = {
    "town_shop_goods": "Nono's Shop",
    "gacha_duplicate_legend": "$hop - Memory Archive - Traveler",
    "season_pass": "Seasonal Shop",
}

# What each product is and how many of it a period allows, as
# `(name, per period, period)`. **Hand-written from the game's screens
# and INCOMPLETE**: only the two marked `confirmed` in
# `docs/wire_hunt.tsv` are backed by a captured purchase. A product
# absent here still gets a row, labelled by its id, so what is missing
# is visible rather than silently dropped.
PRODUCTS = {
    # Nono's Shop. `town_shop_goods_005` and `_006` are confirmed by
    # what a purchase added; the rest are matched by the stock figure
    # the maintainer read off the shop against the row's `count`, which
    # is suggestive and not proof.
    "town_shop_goods_003": ("Research Notes", 35, "weekly"),
    "town_shop_goods_005": ("A-Grade Policy Report", 1, "weekly"),
    "town_shop_goods_006": ("B-Grade Policy Report", 2, "weekly"),
    "town_shop_goods_007": ("Exquisite Slice of Cake", 3, "weekly"),
    "town_shop_goods_008": ("Sweet Choconilla", 3, "weekly"),
    "town_shop_goods_009": ("Unit", 40, "weekly"),
}


def rows(raw_data):
    """{product id: the row} for every product a snapshot carries."""
    out = (raw_data or {}).get(FIELD)
    return out if isinstance(out, dict) else {}


def products_of(shop_prefix, raw_data):
    """Every product id under one shop, sorted.

    Sorted by id, which is the order the game lists them in for every
    shop seen so far.
    """
    return sorted(key for key in rows(raw_data)
                  if key.rsplit("_", 1)[0] == shop_prefix)


def remaining(product_id, raw_data):
    """(left to buy, per-period max), or (None, max) where it cannot say.

    None is a reading, not a failure: `count` is the purchases made in
    the current period and it is reset lazily, so a row nobody has
    touched since the period rolled over carries a stale tally and no
    honest subtraction can be made from it. The Checklist draws that
    as `-`.
    """
    named = PRODUCTS.get(product_id)
    limit = named[1] if named else None
    row = rows(raw_data).get(product_id)
    if not isinstance(row, dict) or limit is None:
        return None, limit
    count = row.get("count")
    if not isinstance(count, int) or isinstance(count, bool):
        return None, limit
    return max(0, limit - count), limit


def label(product_id):
    """What to call a product: its name, or its id where none is known."""
    named = PRODUCTS.get(product_id)
    return named[0] if named else product_id


def period_of(product_id):
    """`weekly`, `monthly`, or None where nothing says."""
    named = PRODUCTS.get(product_id)
    return named[2] if named else None
