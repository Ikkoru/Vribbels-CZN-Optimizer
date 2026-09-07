"""What a snapshot says about each shop product, and what is left to buy.

`shop_list` is one row per product id: `{count, reset_time,
total_count}`. All three are settled, by a capture that bought the same
product twice in separate purchases and read the shop's own figure
either side:

* **`count` is how many were bought in the CURRENT PERIOD**, so what is
  left is `max - count`. Two purchases of `town_shop_goods_014` took it
  0 -> 1 -> 2 while the shop read 20/20 -> 19/20 -> 18/20.
* **`total_count` counts UP for the life of the account**, +1 per unit.
* **`reset_time` is written on every PURCHASE**, not on the period
  boundary. It is the last time `count` moved.

**`count` is reset LAZILY, and that is the trap.** A row nobody has
bought from since the period rolled over still carries the previous
period's tally: `town_shop_goods_014` read 20 hours after the weekly
reset had refilled it, and only the next purchase took it to 1. So a
`count` whose `reset_time` predates the current period means NOTHING
BOUGHT, not a shop bought out -- and reading it straight draws a full
shop as empty.

`period_start` is what tells the two apart. The weekly boundary comes
from `weekly_reset`; the monthly one is on the wire as `month_start`,
which the snapshot carries.

Nothing on the wire says which products reset weekly and which monthly,
or what a product's per-period MAX is, so `PRODUCTS` below is
hand-written from the game's own screens.

No Tk and no managers: this takes the snapshot dict and returns data.
"""

import weekly_reset

FIELD = "shop_list"
MONTH_START_FIELD = "month_start"

# Product id prefix -> the shop it belongs to. Established by buying
# something in each and reading the product id off the request.
SHOPS = {
    "town_shop_goods": "Nono's Shop",
    "gacha_duplicate_legend": "$hop - Memory Archive - Traveler",
    "hyperspace": "$hop - Zeronium Shop",
    "chaos": "$hop - Blackhorn Trade",
    "card_factor": "$hop - Exchange Shop - Prism Module",
    "season_pass": "Seasonal Shop",
}

# What each product is, how many of it a period allows, and which
# period, as `(name, per period, period)`.
#
# **Hand-written and INCOMPLETE.** Every row here was established by
# buying one and reading what arrived, or by matching the shop's own
# figure against `count`; the products nobody has bought are not here
# and get no row on the Checklist, so what is missing stays visible.
#
# `period` is `weekly`, `monthly`, or `none` for a product with a
# lifetime cap that never refills.
PRODUCTS = {
    # Nono's Shop, bought with Policy Point (2000031).
    "town_shop_goods_003": ("Research Notes", 35, "weekly"),
    "town_shop_goods_005": ("A-Grade Policy Report", 1, "weekly"),
    "town_shop_goods_006": ("B-Grade Policy Report", 2, "weekly"),
    "town_shop_goods_007": ("Exquisite Slice of Cake", 3, "weekly"),
    "town_shop_goods_008": ("Sweet Choconilla", 3, "weekly"),
    "town_shop_goods_009": ("Unit", 40, "weekly"),
    "town_shop_goods_014": ("Traces of Memory", 20, "weekly"),
    # Zeronium Shop, bought with Zeronium (2000020).
    "hyperspace_10": ("Advanced Battle Memory", 10, "monthly"),
    # Blackhorn Trade, bought with Crystal of Discord (2000032). A
    # LIFETIME cap: its `reset_time` has not moved since 2025.
    "chaos_22": ("Advanced Battle Memory", 400, "none"),
    # Prism Module exchange, bought with Prism Film (2000024).
    "card_factor_2": ("Prism Lens", None, "none"),
}

# Which boundary a period's `count` is measured from. `none` never
# resets, so its tally is a lifetime one and always current.
PERIODS = ("weekly", "monthly", "none")


def rows(raw_data):
    """{product id: the row} for every product a snapshot carries."""
    out = (raw_data or {}).get(FIELD)
    return out if isinstance(out, dict) else {}


def products_of(shop_prefix, raw_data):
    """Every product id under one shop, sorted by id."""
    return sorted(key for key in rows(raw_data)
                  if key.rsplit("_", 1)[0] == shop_prefix)


def period_start(period, raw_data, now):
    """When the current period began, epoch seconds, or None.

    `none` has no boundary: the tally is a lifetime one, so anything
    before now counts and 0 serves. The monthly boundary is the wire's
    own `month_start`; without it there is no honest answer, because
    the month rolls at 18:00 UTC on the LAST day of the month rather
    than at midnight on the first.
    """
    if period == "none":
        return 0
    if period == "weekly":
        # The reset BEFORE now: `next_reset` looks forward.
        return weekly_reset.next_reset(now) - 7 * 24 * 3600
    start = (raw_data or {}).get(MONTH_START_FIELD)
    return start if isinstance(start, int) else None


def remaining(product_id, raw_data, now):
    """(left to buy, per-period max), or (None, max) where it cannot say.

    None is a reading, not a failure. Three ways to get one: the
    product is not in `PRODUCTS`, the snapshot never carried its row,
    or the row's `count` is STALE -- last touched before the current
    period began, which says nothing about what has been bought since.

    A product with no cap reads (None, None): it is unlimited, and a
    subtraction from nothing is not a number.
    """
    named = PRODUCTS.get(product_id)
    if named is None:
        return None, None
    _name, limit, period = named
    row = rows(raw_data).get(product_id)
    if limit is None or not isinstance(row, dict):
        return None, limit
    count = row.get("count")
    if not isinstance(count, int) or isinstance(count, bool):
        return None, limit
    started = period_start(period, raw_data, now)
    if started is None:
        return None, limit
    # A time, so a float is as good as an int -- but NOT a bool, which
    # is an int and would compare as 0 or 1 against an epoch second.
    touched = row.get("reset_time")
    if _is_time(touched) and touched < started:
        # Nobody has bought from it since the period rolled, so the
        # tally is last period's and the shelf is full.
        return limit, limit
    return max(0, limit - count), limit


def _is_time(value):
    """True for something that can be compared against an epoch second.

    A float counts; `bool` does not, being an int that would compare as
    0 or 1 against a timestamp and mark every row stale.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def label(product_id):
    """What to call a product: its name, or its id where none is known."""
    named = PRODUCTS.get(product_id)
    return named[0] if named else product_id


def period_of(product_id):
    """`weekly`, `monthly`, `none`, or None where nothing says."""
    named = PRODUCTS.get(product_id)
    return named[2] if named else None
