"""What each shop sells, and what is left to buy of it.

Two payloads, and both are needed:

* **`shop_res_data`** is the shop's own DEFINITIONS, one per product:
  what item it gives (`product_link_item_id`) and how many
  (`product_count`), the per-period cap (`limit_count`), which period
  (`limit_type`), the price (`price_link_item_id`, `price_count`), the
  display order (`sort`), and **which screen it is on**
  (`link_shop_sub_category_id`). Sent once at login.
* **`shop_list`** is what the ACCOUNT has done with them, one row per
  product: `{count, reset_time, total_count}`.

All three of a row's fields are settled, by a capture that bought the
same product twice in separate purchases and read the shop's own figure
either side:

* **`count` is how many were bought in the CURRENT PERIOD**, so what is
  left is `limit_count - count`. Two purchases of `town_shop_goods_014`
  took it 0 -> 1 -> 2 while the shop read 20/20 -> 19/20 -> 18/20.
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
because the month rolls at 18:00 UTC on the LAST day and cannot be
derived from a date.

No Tk and no managers: this takes the snapshot dict and returns data.
"""

import schedules
import weekly_reset

DEFINITIONS_FIELD = "shop_res_data"
STOCK_FIELD = "shop_list"
MONTH_START_FIELD = "month_start"

# `(category, sub-category)` -> what the game calls that shop. **The
# SUB-category is what a screen in the game actually is**: one category
# holds several, and reading the category alone folds neighbours into
# one list -- the Traveler exchange with the Combatant and Partner
# duplicate shops, the Prism Module bench with the Anchor and Spectral
# Cube ones, and the Seasonal Supply Store's three supplies as one.
#
# A shop absent here gets no rows, which is what keeps the tab to the
# shops the maintainer tracks rather than every product table the login
# sends. `none` is the sub-category of a category with only one shop.
#
# `ALL_SCREENS` stands where a category's screens are one shelf to the
# person shopping: the Galactic Disaster's three pages share a purse
# and a deadline, and sell the same item on two or three of them.
ALL_SCREENS = "all"

SHOPS = {
    ("shop_town", "none"): "Nono's Shop",
    ("shop_gacha_dup", "shop_gacha_dup_legend"):
        "Shop - Memory Archive - Traveler",
    ("shop_hyperspace", "none"): "Shop - Zeronium Shop",
    ("shop_chaos", "none"): "Shop - Blackhorn Trade",
    ("shop_exchange_product", "shop_card_factor"):
        "Shop - Exchange Shop - Prism Module",
    ("shop_disaster", "shop_disaster_1"): "Seasonal Shop",
    ("shop_disaster", ALL_SCREENS): "Seasonal Shop",
    ("shop_assault", "none"): "Sortie - Chaos Analysis Lab",
}

# The wire's `limit_type` -> which Checklist column the product belongs
# in. **`NONE` is absent on purpose**: a product with no cap has nothing
# to count down and nothing to finish, so it is not a checklist row.
#
# `LIMIT_ACCOUNT` names a cap the game itself never refreshes, which is
# the Sortie shop, so it sits under Other rather than under a period.
PERIOD_BY_LIMIT = {
    "LIMIT_WEEK": "weekly",
    "LIMIT_MONTH": "monthly",
    "LIMIT_ACCOUNT": "account",
}

# **What refreshes the `account` shelves is the SEASON ending**, and
# the season is only in `event_schedules`. `LIMIT_ACCOUNT` reads as a
# lifetime cap, and taking it at its word left last season's purchases
# standing: three cores read as bought when the shelves were full,
# their tallies stamped weeks before the live season began.
#
# The rotations inside a season are their own group, so this one holds
# nothing but the seasons themselves.
ACCOUNT_SEASON_GROUP = "ASSAULT_SCHEDULE"

# **And a shop whose season is not that one says so.** A Galactic
# Disaster season spans four Sortie seasons, so measuring its shelves
# against the Sortie boundary read every purchase made before the last
# three weeks as never made -- the shelf full, the bill for clearing it
# the whole catalogue. Its products are keyed per season
# (`disaster_s04_*`), so a row that exists at all belongs to the live
# one and the boundary only has to be no later than the season's start.
SEASON_GROUP_BY_SHOP = {"shop_disaster": "DISASTER_SEASON"}


def definitions(raw_data):
    """{category: {product id: definition}} from a snapshot."""
    out = (raw_data or {}).get(DEFINITIONS_FIELD)
    return out if isinstance(out, dict) else {}


def stock(raw_data):
    """{product id: the account's row} from a snapshot."""
    out = (raw_data or {}).get(STOCK_FIELD)
    return out if isinstance(out, dict) else {}


def products(shop, period, raw_data, prefix=None):
    """[(product id, definition)] in one shop and one period, in order.

    `shop` is the `(category, sub-category)` pair -- the sub-category
    being what a screen in the game is, or `ALL_SCREENS` for every
    screen of the category at once. Sorted by the shop's own `sort`,
    which is the order the game lists them in, screen by screen. A
    product with no cap is left out: `PERIOD_BY_LIMIT` has no entry
    for `NONE`.

    `prefix` keeps only products whose id starts with it. **The
    seasonal shop needs it**: every season the account has played keeps
    its products in the table, so one screen offering one Tear of God
    reads as three.
    """
    category, sub = shop
    rows = []
    for product_id, define in definitions(raw_data).get(category, {}).items():
        if not isinstance(define, dict):
            continue
        if sub != ALL_SCREENS and define.get(
                "link_shop_sub_category_id") != sub:
            continue
        if prefix and not str(product_id).startswith(prefix):
            continue
        limit = define.get("limit_count")
        if PERIOD_BY_LIMIT.get(define.get("limit_type")) != period:
            continue
        if not isinstance(limit, int) or limit <= 0:
            continue
        rows.append((product_id, define))
    # Screen first, then the shop's own order within it: `sort` counts
    # from 1 again on each screen, so ordering by it alone interleaves
    # the pages of a shop read whole.
    return sorted(rows, key=lambda pair: (
        pair[1].get("link_shop_sub_category_id") or "",
        pair[1].get("sort", 0), pair[0]))


def season_group_of(category):
    """Which `event_schedules` group refreshes one shop's `account`
    shelves. See `SEASON_GROUP_BY_SHOP`."""
    return SEASON_GROUP_BY_SHOP.get(category, ACCOUNT_SEASON_GROUP)


def season_group(define):
    """The same, for a product that states its own shop."""
    return season_group_of((define or {}).get("link_shop_category_id"))


def period_start(period, raw_data, now, group=ACCOUNT_SEASON_GROUP):
    """When the current period began, epoch seconds, or None.

    The `account` boundary is a SEASON's own start, and which season
    depends on the shop -- see `season_group`. The monthly boundary is
    the wire's own `month_start`; without it there is no honest answer.
    """
    if period == "account":
        return schedules.season_start(group, raw_data, now)
    if period == "weekly":
        # The reset BEFORE now: `next_reset` looks forward.
        return weekly_reset.next_reset(now) - 7 * 24 * 3600
    start = (raw_data or {}).get(MONTH_START_FIELD)
    return start if isinstance(start, int) else None


def remaining(product_id, define, raw_data, now):
    """(left to buy, cap), or (None, cap) where it cannot say.

    None is a reading, not a failure. Three ways to get one: the
    snapshot never carried the product's row, the row's `count` is not
    a number, or the boundary its period is measured from is unknown.

    A `count` last touched BEFORE the period began is not stale data to
    reject -- it is last period's tally, which says the shelf is full.
    """
    limit = define.get("limit_count")
    if not isinstance(limit, int) or limit <= 0:
        return None, None
    # **No row means nothing bought.** `shop_list` carries a row only
    # once a product has been bought from at least once, so an absent
    # one is a full shelf rather than an unknown -- and reading it as
    # unknown drew a dash beside every product the account has never
    # touched.
    row = stock(raw_data).get(product_id)
    if not isinstance(row, dict):
        return (limit, limit) if stock(raw_data) else (None, limit)
    count = row.get("count")
    if not isinstance(count, int) or isinstance(count, bool):
        return None, limit
    started = period_start(
        PERIOD_BY_LIMIT.get(define.get("limit_type")), raw_data, now,
        season_group(define))
    if started is None:
        return None, limit
    touched = row.get("reset_time")
    if _is_time(touched) and touched < started:
        return limit, limit
    return max(0, limit - count), limit


def _is_time(value):
    """True for something comparable against an epoch second.

    A float counts; `bool` does not, being an int that would compare as
    0 or 1 against a timestamp and mark every row stale.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)
