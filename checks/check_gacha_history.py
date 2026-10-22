"""The Gacha History keeps what the game throws away, and reads it right.

Everything here fails quietly. A history write that loses records says
nothing -- the game stops listing a pull after about half a year, so a
record dropped from the file is gone for good, and nobody finds out
until they look for it. A unit read at the wrong rarity leaves every
pity after it wrong, which is exactly how hub-czn broke: each new 5-star
counted as a 3-star and the counter ran on through it. And the luck
figures rest on a pity schedule the wire never states.

So this holds:

* the pool and rarity readings, on the shapes the wire actually sends;
* the schedule, against the consolidated rates the game prints;
* pity and 50/50 outcomes, on a history built to exercise each rule;
* hub-czn's export, read with its rarities thrown away;
* both copies of the checked-copy write -- the app's and the addon's --
  including a copy that fails its check, which must leave the file
  untouched;
* the Card Skin Packs' records and pulls, kept beside the Rescue
  records the same way;
* and, where the maintainer's captures carry a history, the whole path:
  the real log replayed through the real addon must rebuild every pool's
  pity to the game's own counter.
"""

import gzip
import json
import tempfile
from pathlib import Path

from ._harness import SOURCE_ROOT, add_source_to_path, note

NAME = "gacha history"

# Units no table carries, so their rarity can only have come from the
# rate lists. Real ids would pass whichever source was read.
OFF_BANNER, FEATURED, LATER, IMPORTED_FIVE = 990001, 990002, 990003, 990004
FOUR, THREE, NOBODY = 990011, 990021, 990099
BANNER = "gacha_pickup_combatant_%d" % FEATURED
LATER_BANNER = "gacha_pickup_combatant_%d" % LATER

# The consolidated rates the Probabilities notices print, which the
# schedule has to reproduce: (base, stated).
PUBLISHED = ((0.01, 0.0214343), (0.03, 0.0352734))


def _rates(featured=FEATURED):
    """A rates reply in the wire's shape, pools and all."""
    return {
        "rates": {"total_ratio": 100000, "ssr_rate_up_success_ratio": 500,
                  "ssr_ratio": 500, "sr_rate_up_success_ratio": 3000,
                  "sr_ratio": 0, "sr_combatant_ratio": 1500,
                  "sr_supporter_ratio": 1500, "r_ratio": 93000},
        "total_rate_info": {
            "total_ssr_pool_pct": 714.48, "total_ssr_rate_up_pool_pct":
            1428.95, "total_sr_pool_pct": 0, "total_sr_rate_up_pool_pct":
            8655.42, "total_sr_combatant_pool_pct": 2163.86,
            "total_sr_supporter_pool_pct": 2163.86,
            "total_r_pool_pct": 84873.45},
        "pools": {
            "ssr_rate_up_success_pool_ids": [
                "pickup_c_16_rateup_ssr_c_%d" % featured],
            "ssr_pool_ids": ["general_ssr_c_%d" % OFF_BANNER,
                             "general_ssr_c_1052_1_%d" % LATER,
                             "general_ssr_c_%d" % IMPORTED_FIVE],
            "sr_combatant_pool_ids": ["pickup_c_16_sr_c_%d" % FOUR],
            "r_pool_ids": ["general_r_s_%d" % THREE],
            # A card item, not a unit: must not be read as one.
            "ssr_pool_ids_card": ["card_factor_ssr_5201083"],
        },
    }


def _record(rid, gacha_id, at, reward):
    return {"id": str(rid), "user_id": "1", "gacha_id": gacha_id,
            "count": len(reward), "reward": json.dumps(reward),
            "prism": json.dumps([0] * len(reward)), "createAt": str(at)}


def _pools_and_rarity(gh, failures):
    # **A Seasonal Rescue Rate-Up**: the rerun suffix on a unit no
    # Normal Rescue offers, and the release counter -- Sereniel's
    # records answered with the release banners'. The rates read, as
    # `load` notes them, say which units the Normal Rescues offer.
    gh.note_general_pool({
        "gacha_general": {"pools": {"ssr_pool_ids": [
            "general_ssr_c_1052", "general_ssr_c_30047"]}},
        "gacha_general_supporter": {"pools": {"ssr_pool_ids": [
            "general_ssr_s_20002"]}}})
    cases = {
        "gacha_pickup_combatant_30117": ("pickup_combatant", 30117),
        "gacha_pickup_combatant_1052_1": ("pickup_combatant_rerun", 1052),
        "gacha_pickup_supporter_20002_1": ("pickup_supporter_rerun", 20002),
        "gacha_pickup_combatant_30075_1": ("pickup_combatant", 30075),
        "gacha_pickup_supporter_30076_1": ("pickup_supporter", 30076),
        "gacha_general": ("general", None),
        "gacha_general_supporter": ("general_supporter", None),
        "gacha_card_factor": ("card_factor", None),
        "gacha_general_first_select_1": ("first_select", None),
        "gacha_partner_reform_1": ("partner_reform", None),
    }
    for gacha_id, want in cases.items():
        got = (gh.pool_of(gacha_id), gh.featured_of(gacha_id))
        if got != want:
            failures.append(
                f"{gacha_id} reads as pool/featured {got}, not {want}. Pulls "
                f"filed under the wrong pool advance the wrong pity counter "
                f"-- a rerun is a category of its own, with its own, but "
                f"a Seasonal one counts with the releases.")
    # Before any rates, the game client's own Normal Rescue pools say it
    # (`game_client.known_general_units`); with neither, every suffix is
    # a rerun: nothing says otherwise.
    import game_client
    gh.note_general_pool({})
    held_units = game_client.known_general_units
    game_client.known_general_units = lambda: None
    try:
        if gh.pool_of("gacha_pickup_combatant_30075_1") != \
                "pickup_combatant_rerun":
            failures.append(
                "with no rates read and no client pools, a suffixed banner "
                "is not filed as a rerun. Nothing but the Normal Rescues' "
                "list can say it is Seasonal, and without it the suffix is "
                "the only word.")
        game_client.known_general_units = lambda: {1052, 30047}
        if gh.pool_of("gacha_pickup_combatant_30075_1") != "pickup_combatant":
            failures.append(
                "with no rates read, the game client's Normal Rescue pools "
                "did not file a rerun of a unit they lack as Seasonal.")
    finally:
        game_client.known_general_units = held_units
    tiers = gh.tiers_from_rates({"x": _rates()})
    want = {FEATURED: 5, OFF_BANNER: 5, LATER: 5, IMPORTED_FIVE: 5,
            FOUR: 4, THREE: 3}
    if tiers != want:
        failures.append(
            f"the rate lists read as {tiers}, not {want}. They are the "
            f"only statement of a new unit's rarity; `card_factor_ssr_*` "
            f"entries are card items and must not be read as units.")


def _schedule(gh, failures):
    for base, stated in PUBLISHED:
        got = 1 / gh.pulls_per_five(base)
        if abs(got - stated) > gh.SCHEDULE_TOLERANCE:
            failures.append(
                f"the pity schedule gives {got:.7f} at a {base:.0%} base; "
                f"the game prints {stated}. SOFT_PITY_FROM, SOFT_PITY_STEP "
                f"and HARD_PITY no longer describe the game, and every "
                f"expected-pity and luck figure would be drawn from them.")
    if not gh.schedule_matches(_rates()):
        failures.append("a rates reply stating the official consolidated "
                        "rate does not match the schedule")
    # The rank is named from the nearer end, so its number is always the
    # small one: a bare `Top 93%` reads as praise and means the reverse.
    ranks = {0.88: "Top 12%", 0.5: "Top 50%", 0.27: "Bottom 27%",
             0.996: "Top 0.4%", 0.001: "Bottom 0.1%",
             0.9996: "Top <0.1%", 0.992: "Top 0.8%", 0.994: "Top 0.6%",
             None: None}
    for share, want in ranks.items():
        if gh.luck_rank(share) != want:
            failures.append(f"a luckier-than share of {share} ranks as "
                            f"{gh.luck_rank(share)!r}, not {want!r}")
    middle = gh.luckier_than([47, 46], 0.01)
    worst = gh.luckier_than([70, 70], 0.01)
    best = gh.luckier_than([1, 1], 0.01)
    if not (best > middle > worst) or not 0.3 < middle < 0.7:
        failures.append(
            f"luckier-than reads {best:.2f} / {middle:.2f} / {worst:.2f} for "
            f"the best, a typical and the worst history. It must fall as "
            f"the pulls grow, and sit near the middle for a typical one.")


def _history(gh, folder, failures):
    """Pity and 50/50 outcomes on a history built to hit each rule."""
    pad = [THREE] * 29
    records = [
        # A lost 50/50 on pull 30, then the guarantee eleven later.
        _record(1, BANNER, 1000, pad + [OFF_BANNER]),
        _record(2, BANNER, 1010, [THREE] * 10 + [FEATURED]),
        # A won one, straight away.
        _record(3, BANNER, 1020, [FEATURED, FOUR, NOBODY]),
    ]
    later = [
        # After an unknown banner, the featured unit: a win or a
        # guarantee, and no telling which.
        _record(4, LATER_BANNER, 3000, [THREE, LATER]),
    ]
    store = {"kind": gh.STORE_KIND, "version": 1,
             "records": records + later,
             "rates": {BANNER: dict(_rates(), seen="2026-01-01T00:00:00")},
             "pity": {"gacha_pity_pickup_combatant": {
                 "res_id": "gacha_pity_pickup_combatant",
                 "pity_ssr_count": 0, "updateAt": "3000",
                 "createAt": "1000", "version": 9}},
             "read": {BANNER: "2026-01-01T00:00:00"}}
    store_dir = gh.folder_in(folder)
    store_dir.mkdir(parents=True)
    (store_dir / gh.CAPTURED).write_text(json.dumps(store), encoding="utf-8")
    # An import between them: a 5-star whose banner hub-czn threw away.
    hub = [{"banner_name": "Seasonal Combatant Rescue Rate-Up",
            "pulls": [{"pull_number": 2, "res_id": IMPORTED_FIVE,
                       "rarity": 3, "is_featured": False, "timestamp": 2000},
                      {"pull_number": 1, "res_id": THREE, "rarity": 3,
                       "is_featured": False, "timestamp": 2000}]}]
    batches, _skipped = gh.parse_import(hub, "hub.json")
    gh.merge_import(folder, batches)

    history = gh.load(folder, now=4000)
    pool = history.pools.get("pickup_combatant")
    if pool is None:
        failures.append("the built history has no Combatant rate-up pool")
        return
    fives = [(p.res_id, p.pity, p.outcome) for p in pool.pulls
             if p.stars == 5]
    want = [(OFF_BANNER, 30, gh.LOST), (FEATURED, 11, gh.GUARANTEED),
            (FEATURED, 1, gh.WON), (IMPORTED_FIVE, 4, gh.UNKNOWN),
            (LATER, 2, gh.RATE_UP)]
    if fives != want:
        failures.append(
            f"the 5-stars read as {fives}, not {want}. Pity must reset on "
            f"EVERY 5-star -- only that reproduces the game's published "
            f"rates -- and a lost 50/50 makes the next 5-star a guarantee.")
    # The import's 5-star was a 3-star in hub-czn's file. Read as one,
    # the counter would run on through it.
    unknown = [p for p in pool.pulls if p.stars is None]
    if [p.res_id for p in unknown] != [NOBODY]:
        failures.append(
            f"the pulls of unknown rarity are {[p.res_id for p in unknown]}"
            f", not [{NOBODY}]. A unit neither the rates nor the tables "
            f"know must read as unknown -- never as a 3-star.")
    s = pool.stats
    if (s.won, s.lost, s.guaranteed) != (1, 1, 1):
        failures.append(f"50/50 tally {(s.won, s.lost, s.guaranteed)}, "
                        f"not one won, one lost, one guaranteed")
    if s.pity_now != 0 or s.game_pity != 0:
        failures.append(f"pity now {s.pity_now}, game {s.game_pity}; both "
                        f"should be 0 after the last pull's 5-star")


def _dated(gh, folder, failures):
    """An imported pull that lost its banner is dated back to one.

    hub-czn files every Combatant rate-up under one name, so without the
    dates a whole export's 50/50s read `?`. Real units, so the rarity
    comes from the tables: Khalipe off-banner, then Narja on hers.
    """
    from datetime import datetime, timezone

    def at(text):
        return int(datetime.strptime(text, "%Y-%m-%d %H:%M").replace(
            tzinfo=timezone.utc).timestamp())

    cases = {
        # The changeover is 02:00 UTC on the day one closes and the next
        # opens -- both sides of it, and a week two releases shared.
        ("pickup_combatant", "2026-02-04 01:30"):
            "gacha_pickup_combatant_1052",
        ("pickup_combatant", "2026-02-04 02:30"):
            "gacha_pickup_combatant_30047",
        ("pickup_supporter", "2026-03-20 12:00"):
            "gacha_pickup_supporter_1025",
        ("pickup_combatant", "2026-05-01 12:00"): None,
        # A rerun open beside the release: either could have it.
        ("pickup_combatant", "2026-06-20 12:00"): None,
    }
    for (pool, when), want in cases.items():
        got = gh.dated_banner(pool, at(when))
        if got != want:
            failures.append(
                f"a {pool} pull at {when} UTC dates to {got}, not {want}. "
                f"A pull given the wrong banner reads its 50/50 backwards; "
                f"one where two banners were open must stay unknown.")

    store_dir = gh.folder_in(folder)
    store_dir.mkdir(parents=True)
    hub = [{"banner_name": "Seasonal Combatant Rescue Rate-Up", "pulls": [
        {"pull_number": 1, "res_id": 1008, "timestamp":
         at("2026-01-14 19:41")},
        {"pull_number": 2, "res_id": 1052, "timestamp":
         at("2026-01-14 19:43")},
        {"pull_number": 3, "res_id": 1052, "timestamp":
         at("2026-06-20 12:00")}]}]
    gh.merge_import(folder, gh.parse_import(hub, "hub.json")[0])
    history = gh.load(folder, now=at("2026-07-01 00:00"))
    pool = history.pools.get("pickup_combatant")
    outcomes = [(p.res_id, p.outcome) for p in pool.pulls] if pool else []
    want = [(1008, gh.LOST), (1052, gh.GUARANTEED), (1052, gh.UNKNOWN)]
    if outcomes != want:
        failures.append(
            f"a dated import reads {outcomes}, not {want}: Khalipe lost on "
            f"Narja's banner, Narja the guarantee, and a pull in a rerun "
            f"week unknown.")
    if not any("rerun" in line for line in history.notes):
        failures.append(
            "an imported pull made while a rerun ran beside the rate-up "
            "was counted toward the rate-up without a word. It may be the "
            "rerun's, whose pity is kept apart.")


def _behind_by_counters(gh, folder, failures):
    """A pull the history lacks shows in the game's counters.

    The pity record's `updateAt` did not move on a captured single pull,
    so the stamp cannot be what finds it: here it stays on the newest
    record, and only the count since the last 5-star moves on.

    Behind turns urgent once the records were last read more than
    `URGENT_AFTER_DAYS` ago, and only behind: a pool with nothing to
    read has nothing to lose.
    """
    from datetime import datetime

    store_dir = gh.folder_in(folder)
    store_dir.mkdir(parents=True)
    records = [_record(1, BANNER, 1000, [THREE, FEATURED, THREE, THREE])]
    now = datetime(2026, 9, 23, 12).timestamp()

    def days_ago(days):
        # Local time, as the addon stamps a read.
        return datetime.fromtimestamp(now - days * 86400).isoformat(
            timespec="seconds")

    urgent_at = gh.URGENT_AFTER_DAYS
    for game_count, read_days, want in (
            (2, 1, (False, False)), (3, 1, (True, False)),
            (3, urgent_at - 1, (True, False)),
            (3, urgent_at + 1, (True, True)),
            (2, urgent_at + 1, (False, False))):
        store = {"kind": gh.STORE_KIND, "version": 1, "records": records,
                 "rates": {BANNER: _rates()},
                 "pity": {"gacha_pity_pickup_combatant": {
                     "res_id": "gacha_pity_pickup_combatant",
                     "pity_ssr_count": game_count, "createAt": "1",
                     "updateAt": "1000"}},
                 "read": {BANNER: days_ago(read_days)}}
        (store_dir / gh.CAPTURED).write_text(json.dumps(store),
                                             encoding="utf-8")
        stats = gh.load(folder, now=now).pools["pickup_combatant"].stats
        if (stats.behind, stats.urgent) != want:
            failures.append(
                f"with the history counting 2 pulls since its last 5-star, "
                f"the game counting {game_count} and the records last read "
                f"{read_days} days ago, (behind, urgent) reads "
                f"{(stats.behind, stats.urgent)}, not {want}. A pull made "
                f"since the records were read would go unnoticed, or "
                f"unhurried, until the game forgot it.")


def _behind_by_stamp(gh, folder, failures):
    """A pity stamp past the newest pull is a pull -- unless the last
    read explains it.

    Opening a banner's Probability Info re-stamps the record with no
    pull made, and every read of the records goes through that screen:
    a capture of one pull, then a read, left the stamp 50s past the
    pull and the banner orange with the counters agreeing.
    """
    from datetime import datetime

    store_dir = gh.folder_in(folder)
    store_dir.mkdir(parents=True)
    now = datetime(2026, 9, 23, 12).timestamp()
    newest = int(now) - 3600
    records = [_record(1, BANNER, newest, [THREE, FEATURED, THREE, THREE])]

    def local(at):
        # Local time, as the addon stamps a read.
        return datetime.fromtimestamp(at).isoformat(timespec="seconds")

    for stamp_after, read_after, want in ((50, 51, False),
                                          (50, -100, True),
                                          (200, 51, True)):
        store = {"kind": gh.STORE_KIND, "version": 1, "records": records,
                 "rates": {BANNER: _rates()},
                 "pity": {"gacha_pity_pickup_combatant": {
                     "res_id": "gacha_pity_pickup_combatant",
                     "pity_ssr_count": 2, "createAt": "1",
                     "updateAt": str(newest + stamp_after)}},
                 "read": {BANNER: local(newest + read_after)}}
        (store_dir / gh.CAPTURED).write_text(json.dumps(store),
                                             encoding="utf-8")
        behind = gh.load(folder, now=now).pools["pickup_combatant"] \
            .stats.behind
        if behind != want:
            failures.append(
                f"with the counters agreeing, the pity stamp {stamp_after}s "
                f"past the newest pull and the records read "
                f"{read_after}s past it, behind reads {behind}, not "
                f"{want}. A stamp the read itself made is not a pull; one "
                f"after the read is.")


def _across_math(gh, failures):
    """Luck across pools, against the sums it stands for.

    Pools on one base rate must come out as one history of all their
    5-stars, and two base rates as the full convolution the tail read
    shortcuts. The 50/50 share against the binomial it is on even odds.
    """
    from math import comb

    split = gh.luckier_than_across([(0.01, [50, 60]), (0.01, [40])])
    whole = gh.luckier_than([50, 60, 40], 0.01)
    if abs(split - whole) > 1e-12:
        failures.append(f"two pools on one base rate read {split} across "
                        f"them and {whole} as one history of the same "
                        f"5-stars; they are one sum of cycles.")
    low, high = [50, 60], [20, 30, 10]
    odds = gh._convolve(gh._sum_odds(0.01, len(low)),
                        gh._sum_odds(0.03, len(high)))
    took = sum(low) + sum(high)
    brute = sum(odds[took + 1:]) + odds[took] / 2
    got = gh.luckier_than_across([(0.03, high), (0.01, low)])
    if abs(got - brute) > 1e-12:
        failures.append(f"luck across a 1% and a 3% pool reads {got}, where "
                        f"the full convolution says {brute}.")
    want = (sum(comb(12, i) for i in range(4)) + comb(12, 4) / 2) / 2 ** 12
    got = gh.won_fewer([0.5] * 12, 4)
    if abs(got - want) > 1e-12:
        failures.append(f"4 50/50s won of 12 read {got} as the share who "
                        f"won fewer; the binomial says {want}.")


def _sum_tables(gh, failures):
    """The pull-sum tables, against the plain loop they shortcut.

    `_one_more_cycle` slices its way through each convolution so the
    multiply-adds run in C, and the slice bounds are where it can go
    wrong: an edge off by one still sums to about 1, still reads as a
    percentage, and moves every luck figure a little.
    """
    for base in (0.01, 0.03):
        step = gh.cycle_odds(base)
        want = [1.0]
        gh._SUM_ODDS.pop(base, None)
        for count in range(1, 9):
            nxt = [0.0] * (len(want) + gh.HARD_PITY)
            for total, p in enumerate(want):
                for n in range(1, gh.HARD_PITY + 1):
                    nxt[total + n] += p * step[n]
            want = nxt
            got = gh._sum_odds(base, count)
            worst = max((abs(a - b) for a, b in zip(got, want)),
                        default=0.0)
            if len(got) != len(want) or worst > 1e-15:
                failures.append(
                    f"the pulls {count} 5-stars took at a {base:.0%} base "
                    f"differ from the plain convolution (lengths "
                    f"{len(got)} and {len(want)}, worst {worst:.2e}). "
                    f"Every luck figure reads off these tables.")
                break
        gh._SUM_ODDS.pop(base, None)


def _prism_rates():
    """The Prism Module's rates: a 3% base, no 50/50."""
    return {"rates": {"total_ratio": 100000, "ssr_ratio": 3000},
            "total_rate_info": {"total_ssr_pool_pct": 3527.34},
            "pools": {}}


def _across(gh, folder, failures):
    """The Overall figures, on a history laid out to give each one a
    known answer.

    Combatant rate-up, oldest first -- the history starts mid-cycle,
    so its first 5-star's pity and the cost of the rate-up after it are
    unknown:

        pull  1  off-banner  Lost        pity 1, only a floor
        pull  4  featured    Guaranteed  cost unknown: started before
        pull 14  featured    Won         pity 10, cost 10
        pull 16  off-banner  Lost        pity 2
        pull 20  featured    Guaranteed  pity 4, cost 2 + 4 = 6
        pull 24  off-banner  Lost        pity 4

    Pulls 14 to 23 and 16 to 25 hold three 5-stars each, so both are
    the record, the earlier first; an 11-pull window would find four.
    The Prism Module pays a 5-star on each of its three pulls, which
    must reach none of the figures without it, and its last two tie at
    a pity of 1 -- both the fastest and the slowest, the earlier first.
    """
    store_dir = gh.folder_in(folder)
    store_dir.mkdir(parents=True)
    prism = "gacha_card_factor"
    records = [
        _record(1, BANNER, 1000, [OFF_BANNER]),
        _record(2, BANNER, 2000, [THREE] * 2 + [FEATURED]),
        _record(3, BANNER, 3000, [THREE] * 9 + [FEATURED]),
        _record(4, BANNER, 4000, [THREE] + [OFF_BANNER]),
        _record(5, BANNER, 5000, [THREE] * 3 + [FEATURED]),
        _record(6, BANNER, 5500, [THREE] * 3 + [OFF_BANNER]),
        _record(7, prism, 6000, [FEATURED, FEATURED]),
        _record(8, prism, 7000, [FEATURED]),
    ]
    store = {"kind": gh.STORE_KIND, "version": 1, "records": records,
             "rates": {BANNER: _rates(), prism: _prism_rates()}}
    (store_dir / gh.CAPTURED).write_text(json.dumps(store),
                                         encoding="utf-8")
    o = gh.load(folder).overall

    def said(records):
        return [(r.count, [p.res_id for p in r.pulls], r.pulls[-1].at)
                for r in records]

    want = {
        "pulls_without_prism": 24,
        "fifty_won": 1, "fifty_lost": 3,
        "rate_up_avg": 8.0,
        "fastest": [(2, [OFF_BANNER], 4000)],
        "slowest": [(10, [FEATURED], 3000)],
        "fastest_rate_up": [(6, [FEATURED], 5000)],
        "slowest_rate_up": [(10, [FEATURED], 3000)],
        "streak": [(3, [FEATURED, OFF_BANNER, FEATURED], 5000),
                   (3, [OFF_BANNER, FEATURED, OFF_BANNER], 5500)],
        "prism_fastest": [(1, [FEATURED], 6000), (1, [FEATURED], 7000)],
        "prism_slowest": [(1, [FEATURED], 6000), (1, [FEATURED], 7000)],
        "prism_streak": [(3, [FEATURED] * 3, 7000)],
    }
    for field, expected in want.items():
        value = getattr(o, field)
        got = said(value) if isinstance(value, list) else value
        if got != expected:
            failures.append(f"Overall's {field} reads {got}, not "
                            f"{expected}, on a history laid out to give "
                            f"{expected}.")
    expected = gh.won_fewer([0.5] * 4, 1)
    if o.fifty_luck != expected:
        failures.append(f"Overall's 50/50 luck reads {o.fifty_luck} for 1 "
                        f"won of 4, not {expected}.")
    rates = _rates()
    per = gh.pulls_per_five(gh.base_rate(rates)) * 1.5
    if o.rate_up_expected is None or abs(o.rate_up_expected - per) > 1e-9:
        failures.append(f"Overall's expected avg per rate-up reads "
                        f"{o.rate_up_expected}, not {per}: a cycle, and "
                        f"another after each lost 50/50.")
    fives = [3, 10, 2, 4, 4]
    without = gh.luckier_than_across([(0.01, fives)])
    with_prism = gh.luckier_than_across([(0.01, fives), (0.03, [1, 1])])
    if (o.luck_without_prism, o.luck_with_prism) != (without, with_prism):
        failures.append(
            f"Overall's luck reads {o.luck_without_prism} without the "
            f"Prism Module and {o.luck_with_prism} with it, not {without} "
            f"and {with_prism}: the first must leave the Module out, and "
            f"both must leave out every pool's first cycle cut short.")


def _supersede(gh, folder, failures):
    """An import covering pulls the game's own records hold is dropped."""
    store_dir = gh.folder_in(folder)
    store_dir.mkdir(parents=True)
    general_supporter = "gacha_general_supporter"
    store = {"kind": gh.STORE_KIND, "version": 1, "records": [
        _record(10, BANNER, 5000, [THREE, THREE]),
        _record(11, general_supporter, 6000, [THREE, FOUR])],
        "rates": {BANNER: _rates()}, "pity": {}, "read": {}}
    (store_dir / gh.CAPTURED).write_text(json.dumps(store), encoding="utf-8")
    hub = [{"banner_name": "Seasonal Combatant Rescue Rate-Up", "pulls": [
                {"pull_number": 1, "res_id": THREE, "timestamp": 5000},
                {"pull_number": 2, "res_id": THREE, "timestamp": 5000},
                {"pull_number": 3, "res_id": THREE, "timestamp": 7000}]},
           # hub-czn filed the Normal Partner Rescue under the Partner
           # rate-up's name; the units are what say it is the same batch.
           {"banner_name": "Gacha Pickup Supporter", "pulls": [
                {"pull_number": 1, "res_id": THREE, "timestamp": 6000},
                {"pull_number": 2, "res_id": FOUR, "timestamp": 6000}]}]
    gh.merge_import(folder, gh.parse_import(hub, "hub.json")[0])
    history = gh.load(folder, now=8000)
    if history.total != 5:
        failures.append(
            f"a history of 4 captured pulls and 1 new imported one holds "
            f"{history.total}. An import that overlaps the game's own "
            f"records must give way to them, or those pulls count twice.")


def _verified_write(gh, folder, failures):
    target = folder / "file.json"
    key = lambda row: row["n"]                              # noqa: E731
    first = {"batches": [{"n": 1}]}
    gh.write_verified(target, first, "batches", first["batches"], key)
    second = {"batches": [{"n": 1}, {"n": 2}]}
    gh.write_verified(target, second, "batches", second["batches"], key)
    bak = gh.backup_of(target)
    if not bak.exists() or json.loads(bak.read_text(encoding="utf-8")) \
            != first:
        failures.append(
            f"after two writes {bak.name} does not hold the first. The "
            f"backup is the file as it stood before the last write.")
    try:
        gh.write_verified(target, {"batches": [{"n": 2}]}, "batches",
                          second["batches"], key)
        failures.append(
            "a write that drops a row it must keep went through. The "
            "check on the copy is what stops a merge bug erasing history "
            "the game no longer lists.")
    except gh.StoreError:
        pass
    if json.loads(target.read_text(encoding="utf-8")) != second:
        failures.append("a refused write changed the file")
    if gh.temp_of(target).exists():
        failures.append("a refused write left its copy behind")
    target.unlink()
    data, why = gh.read_store(target)
    if data != first or not why:
        failures.append(
            "with the file gone and its backup there, the history reads "
            "as empty. The write renames the file to its backup first, so "
            "a crash between the renames leaves only the backup.")


# ------------------------------------------------------------ the addon

class _Message:
    def __init__(self, text, from_client):
        self.from_client = from_client
        self.is_text = True
        self.text = text
        self.content = text.encode("utf-8")


class _Flow:
    def __init__(self, message):
        self.websocket = type("_WS", (), {"messages": [message]})()


def _build_addon(output_dir, log):
    from capture.manager import CaptureManager

    manager = CaptureManager(output_dir, log_callback=lambda *_a, **_k: None)
    script = manager._generate_addon_script()
    namespace = {"__name__": "_generated_addon_under_check"}
    exec(compile(script.read_text(encoding="utf-8"), str(script), "exec"),
         namespace)
    addon = namespace["addons"][0]
    addon.log_callback = log.append
    return addon, namespace


def _send(addon, request, reply):
    addon.websocket_message(_Flow(_Message(json.dumps([request]), True)))
    addon.websocket_message(_Flow(_Message(json.dumps(reply), False)))


def _ask(qid, cmd, **params):
    return {"cmd": "gacha", "qid": qid, "params": dict(cmd=cmd, **params)}


def _page(qid, records, more):
    return {"res": "ok", "qid": qid, "result": True,
            "gacha_history_list": records, "next_page_exists": more}


def _addon(gh, root, failures):
    from capture.manager import GACHA_MARKER

    log = []
    addon, namespace = _build_addon(root, log)
    path = gh.folder_in(root) / gh.CAPTURED
    rates = _rates()
    _send(addon, _ask(5, "get_rate", gacha_id=BANNER, clean_rate=True),
          dict({"res": "ok", "qid": 5, "result": True}, **rates))
    newest = [_record(22, BANNER, 1200, [THREE, FOUR]),
              _record(21, BANNER, 1100, [THREE])]
    _send(addon, _ask(6, "history", id=BANNER, last_db_id=0),
          _page(6, newest, True))
    _send(addon, {"cmd": "gacha", "qid": 7, "params": {"cmd": "get_list"}},
          {"res": "ok", "qid": 7, "gacha_pity_entity_list": [
              {"res_id": "gacha_pity_pickup_combatant",
               "pity_ssr_count": 3, "updateAt": "1200", "version": 4}]})
    if not path.exists():
        failures.append(
            f"the addon wrote no {gh.CAPTURED} for a history page. The "
            f"game's records would be kept nowhere.")
        return
    store = json.loads(path.read_text(encoding="utf-8"))
    if sorted(r["id"] for r in store.get("records", [])) != ["21", "22"]:
        failures.append(f"{gh.CAPTURED} holds records "
                        f"{[r['id'] for r in store.get('records', [])]}")
    if store.get("rates", {}).get(BANNER, {}).get("pools") != rates["pools"]:
        failures.append(
            "a rates reply was not kept under the banner that asked for "
            "it. The reply does not name its banner; the request does, "
            "and it is the rate lists that give new units their rarity.")
    if "gacha_pity_pickup_combatant" not in store.get("pity", {}):
        failures.append("the pity counters were not kept")
    if BANNER not in store.get("read", {}):
        failures.append("reading a banner's first page did not record it "
                        "as read")
    if not any(GACHA_MARKER == line for line in log):
        failures.append(
            f"the addon never printed {GACHA_MARKER!r}. The Gacha History "
            f"tab would sit on what it read at startup all capture.")

    first = path.read_text(encoding="utf-8")
    older = [_record(21, BANNER, 1100, [THREE]),
             _record(20, BANNER, 1000, [OFF_BANNER])]
    _send(addon, _ask(8, "history", id=BANNER, last_db_id=21),
          _page(8, older, False))
    bak = gh.backup_of(path)
    if not bak.exists() or bak.read_text(encoding="utf-8") != first:
        failures.append(
            f"the second write left no {bak.name} holding the file as it "
            f"was. Every write keeps the one before it.")
    if not any(line.startswith("[GACHA]") and "+1 pulls" in line
               for line in log):
        failures.append(
            f"the Capture Log did not report the one new pull: "
            f"{[l for l in log if l.startswith('[GACHA]')]}")

    # A page holding nothing new, and not the first, changes nothing.
    held = path.read_text(encoding="utf-8")
    markers = log.count(GACHA_MARKER)
    _send(addon, _ask(9, "history", id=BANNER, last_db_id=21),
          _page(9, older, False))
    if path.read_text(encoding="utf-8") != held or \
            log.count(GACHA_MARKER) != markers:
        failures.append(
            "a page with nothing new rewrote the file. Every write turns "
            "the backup over, so a write for nothing replaces the backup "
            "with a copy of the file.")

    # A copy that fails its check leaves the file alone.
    real_json = namespace["json"]

    class _Dropping:
        def __getattr__(self, name):
            return getattr(real_json, name)

        @staticmethod
        def load(f):
            data = real_json.load(f)
            if isinstance(data, dict) and data.get("records"):
                data["records"] = data["records"][1:]
            return data

    namespace["json"] = _Dropping()
    try:
        _send(addon, _ask(10, "history", id=BANNER, last_db_id=20),
              _page(10, [_record(19, BANNER, 900, [THREE])], False))
    finally:
        namespace["json"] = real_json
    if path.read_text(encoding="utf-8") != held:
        failures.append(
            "a copy that lost a record on its way to disk replaced the "
            "file anyway. The read-back check is what stops that.")
    if not any(line.startswith("[X] Gacha History") for line in log):
        failures.append("a refused history write said nothing")
    if (path.parent / (path.name + ".tmp")).exists():
        failures.append("a refused history write left its copy behind")

    # The file lost and its backup there: the backup is built on.
    path.write_text("{ not json", encoding="utf-8")
    _send(addon, _ask(11, "history", id=BANNER, last_db_id=0),
          _page(11, [_record(23, BANNER, 1300, [THREE])], True))
    try:
        store = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        store = {}
    ids = sorted(r["id"] for r in store.get("records", []))
    if not {"21", "22", "23"} <= set(ids):
        failures.append(
            f"with {gh.CAPTURED} unreadable the addon kept {ids or 'nothing'}"
            f". It must build on the backup: the file is renamed to it "
            f"before each new copy lands, so a capture killed between the "
            f"two leaves only the backup.")


def _pulls_and_reach(gh, root, failures):
    """A pull is kept off its own reply until its record comes, and a
    read of the records that misses what was kept is said to.

    A pull's reply (`gacha/run`, `websocket_debug_20260930_233315`)
    names every unit, in the record's order, at the record's `createAt`
    to the second. Unkept, a pull made while capturing is only a
    counter the history disagrees with until someone opens the records.
    """
    log = []
    addon, _namespace = _build_addon(root, log)

    def pull(qid, at, units):
        _send(addon, _ask(qid, "run", id=BANNER, count=len(units)),
              {"res": "ok", "qid": qid, "service_server_time": at,
               "list": [{"index": i, "res_id": unit, "is_prism": 0}
                        for i, unit in enumerate(units)]})

    def gap(now=6000):
        # A `now` near the records: they are stamped in 1970, which a
        # real clock puts far past what the game keeps.
        entry = gh.load(root, now=now).pools.get("pickup_combatant")
        return entry.stats.gap if entry else None

    _send(addon, _ask(30, "history", id=BANNER, last_db_id=0),
          _page(30, [_record(31, BANNER, 1000, [THREE])], False))
    pull(40, 2000, [FOUR, THREE])
    pull(40, 2000, [FOUR, THREE])          # the same reply seen twice
    history = gh.load(root)
    pulled = [b for b in history.batches if b.get("from") == "pull"]
    if history.total != 3 or len(pulled) != 1:
        failures.append(
            f"after one recorded page and one pull of two seen twice, the "
            f"history holds {history.total} pulls, {len(pulled)} of them "
            f"kept off the pull's reply -- not 3 and 1.")
    if not any(line == "[GACHA] Pulls recorded: +2" for line in log):
        failures.append(
            f"a pull reached no Capture Log line: "
            f"{[l for l in log if l.startswith('[GACHA]')]}")
    _send(addon, _ask(41, "history", id=BANNER, last_db_id=0),
          _page(41, [_record(32, BANNER, 2000, [FOUR, THREE]),
                     _record(31, BANNER, 1000, [THREE])], False))
    store = json.loads((gh.folder_in(root) / gh.CAPTURED).read_text(
        encoding="utf-8"))
    history = gh.load(root)
    if store.get("pulls") or history.total != 3:
        failures.append(
            f"the pull's own record arrived and the file still keeps "
            f"{len(store.get('pulls') or [])} pull(s) off replies, the "
            f"history {history.total} pulls, not 0 and 3. The record "
            f"replaces the reply's copy; both counted is a pull twice.")
    if gap() is not None:
        failures.append(f"a read that met the kept records reports a gap "
                        f"{gap()}")

    # Pulls made with no capture running: the first page is all new and
    # the read stops there, short of what was kept.
    _send(addon, _ask(42, "history", id=BANNER, last_db_id=0),
          _page(42, [_record(35, BANNER, 5000, [THREE] * 10)], True))
    if gap() != (2000, 5000):
        failures.append(
            f"a read whose pages met nothing kept reads gap {gap()}, not "
            f"(2000, 5000): the pulls between the two may be missing.")
    # The same gap once the game has stopped listing all of it: nothing
    # can fill it, and a warning would stand for good.
    expired = 5000 + gh.GAME_KEEPS_DAYS * 86400 + 1
    if gap(expired) is not None:
        failures.append(
            f"a gap whose every pull is past what the game keeps still "
            f"reads {gap(expired)}: no read can fill it.")
    # Opening the records again finds the last read's page kept, and
    # still has not reached back past the gap.
    _send(addon, _ask(43, "history", id=BANNER, last_db_id=0),
          _page(43, [_record(35, BANNER, 5000, [THREE] * 10)], True))
    if gap() != (2000, 5000):
        failures.append(
            f"a second read of the same first page closed the gap "
            f"({gap()}): it met only the last read's records, and the "
            f"pulls between are as unread as before.")
    _send(addon, _ask(44, "history", id=BANNER, last_db_id=35),
          _page(44, [_record(34, BANNER, 4000, [THREE]),
                     _record(32, BANNER, 2000, [FOUR, THREE])], True))
    if gap() is not None:
        failures.append(
            f"a read that went back past where the gap opens still "
            f"reports it: {gap()}.")

    # A banner pulled on while capturing and never opened is watched by
    # the counters all the same: one whose pulls are all captured may
    # never be opened, and a pull made without the capture would then
    # go unflagged.
    unread = gh.folder_in(root / "unread")
    unread.mkdir(parents=True)
    kept = {key: value for key, value in _record(
        0, BANNER, 1000, [FOUR, THREE]).items() if key != "id"}
    (unread / gh.CAPTURED).write_text(json.dumps(
        {"kind": gh.STORE_KIND, "version": 1, "records": [],
         "rates": {BANNER: dict(_rates(), seen="1970-01-01T00:00:00")},
         "pity": {"gacha_pity_pickup_combatant": {
             "res_id": "gacha_pity_pickup_combatant", "pity_ssr_count": 7,
             "pity_sr_count": 4, "updateAt": "1000", "version": 3}},
         "pulls": [dict(kept, **{"from": "pull"})]}), encoding="utf-8")
    entry = gh.load(root / "unread", now=2000).pools.get("pickup_combatant")
    if entry is None or not entry.stats.behind:
        failures.append(
            f"a banner pulled on while capturing, never opened, whose "
            f"counter says 4 pulls since the last 4-star against the "
            f"history's 1, reads behind="
            f"{entry.stats.behind if entry else None}, not True.")

    # The loader matches a kept pull to its record too: a file holding
    # both -- written by a capture that never saw the record come --
    # counts the pull once.
    both = gh.folder_in(root / "both")
    both.mkdir(parents=True)
    record = _record(50, BANNER, 7000, [THREE, FOUR])
    kept = {key: value for key, value in record.items() if key != "id"}
    (both / gh.CAPTURED).write_text(json.dumps(
        {"kind": gh.STORE_KIND, "version": 1, "records": [record],
         "pulls": [dict(kept, **{"from": "pull"})]}), encoding="utf-8")
    if gh.load(root / "both").total != 2:
        failures.append(
            f"a file holding a pull and its own record loads as "
            f"{gh.load(root / 'both').total} pulls, not 2.")

    from ui.tabs.gacha_history_tab import BEHIND_TAG, GachaHistoryTab
    stats = gh.PoolStats()
    stats.gap = (2000, 5000)
    if GachaHistoryTab._summary_tags(type("P", (), {"stats": stats})) != (
            BEHIND_TAG,):
        failures.append("a banner with a gap is not drawn orange")


def _skin_ask(qid, cmd, **params):
    return {"cmd": "card_skin", "qid": qid, "params": dict(cmd=cmd, **params)}


# A Card Skin Pack pull's reply and the record the game makes of it, as
# `websocket_debug_20261021_140402` has them, cut down: the record lists
# the skins in the reply's `index` order, `dup` marking the one not new.
SKIN_PACK = "card_skin_pack_s001_2"
SKIN_PULL = {"res": "ok", "service_server_time": 1792591054, "reward_list": [
    {"index": 0, "card_skin_id": 9800001, "is_new": 1},
    {"index": 2, "card_skin_id": 9800004, "is_new": 1},
    {"index": 1, "card_skin_id": 9800001, "is_new": 0,
     "dup_item_id": 2000056, "dup_item_count": 1}]}
SKIN_RECORD = {"id": "91334", "user_id": "1",
               "card_skin_package_id": SKIN_PACK, "count": 3,
               "reward": "[9800001,9800001,9800004]", "dup": "[0,1,0]",
               "createAt": "1792591054"}


def _card_skins(gh, root, failures):
    """The Card Skin Packs' records are kept beside the Rescue records,
    and the same way: a pull off its own reply until its record comes,
    the records by their `id`, a page with nothing new writing nothing,
    and a copy that would lose one refused. The game erases these as it
    does the Rescue records, and lists every pack's in one list."""
    from capture.manager import GACHA_MARKER

    log = []
    addon, namespace = _build_addon(root, log)
    path = gh.folder_in(root) / gh.CAPTURED
    _send(addon, _ask(5, "history", id=BANNER, last_db_id=0),
          _page(5, [_record(22, BANNER, 1200, [THREE])], False))
    _send(addon, _skin_ask(6, "gacha_run", id=SKIN_PACK, count=3),
          dict(SKIN_PULL, qid=6))
    store = json.loads(path.read_text(encoding="utf-8")) \
        if path.exists() else {}
    want = [{key: SKIN_RECORD[key] for key in (
        "card_skin_package_id", "count", "reward", "dup", "createAt")}]
    got = [{key: row.get(key) for key in want[0]}
           for row in store.get("skin_pulls", [])]
    if got != want:
        failures.append(
            f"a Card Skin Pack pull was kept as {got}, not {want}: the "
            f"reply's skins in `index` order, the one not new marked, at "
            f"the reply's second -- the record the game will make of it.")
    _send(addon, _skin_ask(7, "history", last_db_id=0),
          {"res": "ok", "qid": 7, "result": True, "next_page_exists": False,
           "card_skin_gacha_history_list": [SKIN_RECORD]})
    store = json.loads(path.read_text(encoding="utf-8"))
    if (store.get("skin_records"), store.get("skin_pulls"),
            bool(store.get("skin_read"))) != ([SKIN_RECORD], [], True):
        failures.append(
            f"after a Card Skin records page the file holds records "
            f"{store.get('skin_records')}, pulls {store.get('skin_pulls')}, "
            f"read {store.get('skin_read')!r}: the record kept as sent, the "
            f"pull it covers gone, the first page dated.")
    if [r.get("id") for r in store.get("records", [])] != ["22"]:
        failures.append("a Card Skin page changed the Rescue records: "
                        f"{store.get('records')}")

    # A rewrite of the same text shows only in what the write says.
    held = path.read_text(encoding="utf-8")
    markers = log.count(GACHA_MARKER)
    _send(addon, _skin_ask(8, "history", last_db_id=91334),
          {"res": "ok", "qid": 8, "result": True, "next_page_exists": False,
           "card_skin_gacha_history_list": [SKIN_RECORD]})
    if path.read_text(encoding="utf-8") != held \
            or log.count(GACHA_MARKER) != markers:
        failures.append("a Card Skin page with nothing new rewrote the "
                        "file, turning its backup over for nothing.")

    real_json = namespace["json"]

    class _Dropping:
        def __getattr__(self, name):
            return getattr(real_json, name)

        @staticmethod
        def load(f):
            data = real_json.load(f)
            if isinstance(data, dict) and data.get("skin_records"):
                data["skin_records"] = data["skin_records"][1:]
            return data

    namespace["json"] = _Dropping()
    try:
        older = dict(SKIN_RECORD, id="91000", createAt="1792500000")
        _send(addon, _skin_ask(9, "history", last_db_id=91334),
              {"res": "ok", "qid": 9, "result": True,
               "next_page_exists": False,
               "card_skin_gacha_history_list": [older]})
    finally:
        namespace["json"] = real_json
    if path.read_text(encoding="utf-8") != held:
        failures.append(
            "a copy that lost a Card Skin record on its way to disk "
            "replaced the file anyway: the read-back check holds the Card "
            "Skin records as it does the Rescue ones.")
    # The guard behind it: a store that has itself lost a record held
    # before, which reads back as written.
    if addon._write_gacha_store(dict(json.loads(held), skin_records=[]), [],
                                [SKIN_RECORD]) \
            or path.read_text(encoding="utf-8") != held:
        failures.append(
            "a write that would drop a Card Skin record held before went "
            "through: `_write_gacha_store` holds `skin_before` as it holds "
            "`before`.")


def _card_skins_replayed(gh, root, failures):
    """The newest capture holding a Card Skin records page, its Card
    Skin frames replayed through the real addon: every record kept, and
    no pull left that a record covers. Those frames alone -- the
    requests, and the replies carrying records or a pull's skins: the
    whole capture through the addon takes most of a minute, its login
    replies most of that, and they name card skins too."""
    log_path = _history_log("card_skin_gacha_history_list")
    if log_path is None:
        note("no debug log carries a Card Skin records page, so the real "
             "records were not replayed")
        return
    addon, _namespace = _build_addon(root, [])
    seen = set()
    with gzip.open(log_path, "rt", encoding="utf-8") as f:
        for line in f:
            if not ("card_skin" in line if '"client_to_server"' in line
                    else "card_skin_gacha_history_list" in line
                    or "card_skin_id" in line):
                continue
            frame = json.loads(line)
            for reply in frame["data"] if isinstance(frame["data"], list) \
                    else [frame["data"]]:
                if isinstance(reply, dict):
                    seen |= {str(r.get("id")) for r in reply.get(
                        "card_skin_gacha_history_list") or ()
                        if isinstance(r, dict)}
            addon.websocket_message(_Flow(_Message(
                json.dumps(frame["data"]),
                frame.get("direction") == "client_to_server")))
    path = gh.folder_in(root) / gh.CAPTURED
    store = json.loads(path.read_text(encoding="utf-8")) \
        if path.exists() else {}
    kept = {str(r.get("id")) for r in store.get("skin_records", [])}
    covered = {(r.get("createAt"), r.get("reward"))
               for r in store.get("skin_records", [])}
    left = [r for r in store.get("skin_pulls", [])
            if (r.get("createAt"), r.get("reward")) in covered]
    if not seen or kept != seen or left:
        failures.append(
            f"{log_path.name} replayed keeps Card Skin records {sorted(kept)} "
            f"of {sorted(seen)}, with {len(left)} pull(s) left that a record "
            f"covers.")


def _card_skin_luck(gh, folder, failures):
    """The Card Skin Packs read as one pool with no pity: a Super Rare
    where a 5-star stands, the pulls since the one before as its count,
    a duplicate marked, the pack's rate-up its Super Rare's combatant,
    and the luck a flat chance's -- alone, and beside a Rescue's in the
    overall figure that says it holds them."""
    from game_data import from_client
    skins = sorted(from_client.CARD_SKINS.items())
    by = {skin[1]: res_id for res_id, skin in skins}
    pack, (_name, chances, featured) = sorted(
        from_client.CARD_SKIN_PACKS.items())[0]
    chance = chances["SUPER_RARE"]
    # Geometric: one Super Rare at 77 pulls is beaten by every player
    # who needed more, (1 - p)^77, and half of those who needed as many.
    want = (1 - chance) ** 77 + chance * (1 - chance) ** 76 / 2
    got = gh.luckier_than_flat([77], chance)
    if got is None or abs(got - want) > 1e-9:
        failures.append(f"one Super Rare at 77 pulls reads luckier than "
                        f"{got}, not {want}: the flat chance's odds are the "
                        f"negative binomial (`gacha_history._flat_odds`).")
    # Two at 80 pulls: beaten by everyone with at most one in 80, and
    # half of those whose second landed on the 80th.
    q = 1 - chance
    want = q ** 80 + 80 * chance * q ** 79 + 79 * chance ** 2 * q ** 78 / 2
    two = gh.luckier_than_flat([30, 50], chance)
    alone = gh.luckier_than_across([((gh.FLAT, chance), [30, 50])])
    if two is None or alone is None or abs(two - want) > 1e-9 \
            or abs(alone - want) > 1e-9:
        failures.append(f"two Super Rares in 80 pulls read luckier than "
                        f"{two} on their own and {alone} across pools, not "
                        f"{want}.")
    commons = [by["COMMON"]] * 9
    # A Rescue's record beside them, with no rates to draw its luck from:
    # the packs list after it.
    store = {"kind": gh.STORE_KIND, "version": 1,
             "records": [_record(1, BANNER, 900, [THREE])],
             "skin_records": [
                 {"id": "1", "card_skin_package_id": pack, "createAt": "1000",
                  "reward": json.dumps(commons + [by["SUPER_RARE"]]),
                  "dup": json.dumps([0] + [1] * 9)},
                 {"id": "2", "card_skin_package_id": pack, "createAt": "2000",
                  "reward": json.dumps([by["RARE"], by["SUPER_RARE"]]),
                  "dup": "[0,1]"}],
             "skin_read": "2026-10-22T00:00:00"}
    store_dir = gh.folder_in(folder)
    store_dir.mkdir(parents=True)
    (store_dir / gh.CAPTURED).write_text(json.dumps(store), encoding="utf-8")
    history = gh.load(folder)
    pool = history.pools.get(gh.SKIN_POOL)
    if pool is None or history.ordered()[-1] is not pool:
        failures.append("the Card Skin Packs are not the history's last "
                        "pool: the tab lists them under every Rescue.")
        return
    s = pool.stats
    got = (s.pulls, s.fives, s.fours, s.five_pities, s.pity_now,
           [p.outcome for p in pool.pulls].count(gh.DUPLICATE),
           pool.pulls[-1].featured)
    want = (12, 2, 1, [10, 2], 0, 10, featured)
    if got != want:
        failures.append(f"the Card Skin Packs read pulls, Super Rares, "
                        f"Rares, their counts, since the last, duplicates "
                        f"and the rate-up as {got}, not {want}: the first "
                        f"Super Rare's count is whole -- a flat chance has "
                        f"no partial cycle.")
    if s.luckier_than is None or abs(
            s.luckier_than - gh.luckier_than_flat([10, 2], chance)) > 1e-12:
        failures.append(f"the Card Skin Packs' luck reads {s.luckier_than}: "
                        f"the flat chance's over their Super Rares.")
    o = history.overall
    own = gh.luckier_than_flat([10, 2], chance)
    if o.luck_with_prism is not None or o.luck_with_skins is None \
            or abs(o.luck_with_skins - own) > 1e-12 \
            or not o.skin_fastest or o.skin_fastest[0].count != 2:
        failures.append(f"with only the Card Skin Packs, the overall luck "
                        f"reads {o.luck_with_prism} with the Prism Module "
                        f"and {o.luck_with_skins} with the packs, the "
                        f"fastest Super Rare {o.skin_fastest}: only the "
                        f"figures that say they hold the packs do.")


# ------------------------------------------------------------ real data

def _history_log(marker="gacha_history_list"):
    """The newest loose debug log that carries `marker` -- a history
    page by default -- or None."""
    logs = sorted((SOURCE_ROOT / "snapshots").glob(
        "websocket_debug_*.jsonl.gz"), reverse=True)
    for path in logs:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                if marker in f.read():
                    return path
        except (OSError, EOFError, ValueError):
            continue
    return None


def _replay(gh, root, failures):
    log_path = _history_log()
    if log_path is None:
        note("no debug log carries a gacha history page, so the real "
             "records were not replayed")
        return
    addon, _namespace = _build_addon(root, [])
    with gzip.open(log_path, "rt", encoding="utf-8") as f:
        for line in f:
            frame = json.loads(line)
            addon.websocket_message(_Flow(_Message(
                json.dumps(frame["data"]),
                frame.get("direction") == "client_to_server")))
    history = gh.load(root)
    compared = 0
    for pool in history.pools.values():
        s = pool.stats
        if not s.fives or s.game_pity is None or s.behind:
            continue
        compared += 1
        if s.pity_now != s.game_pity:
            failures.append(
                f"{log_path.name} replayed rebuilds {pool.label}'s pity as "
                f"{s.pity_now}; the game's own counter says {s.game_pity}. "
                f"A unit is being read at the wrong rarity, or the pity "
                f"rule no longer matches the game's.")
    if not compared:
        note(f"{log_path.name} carries history but no pool reached a "
             f"5-star, so no pity was compared")


def run():
    failures = []
    add_source_to_path()
    import gacha_history as gh

    _pools_and_rarity(gh, failures)
    _schedule(gh, failures)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _history(gh, tmp / "history", failures)
        _dated(gh, tmp / "dated", failures)
        _behind_by_counters(gh, tmp / "behind", failures)
        _behind_by_stamp(gh, tmp / "stamp", failures)
        _across_math(gh, failures)
        _sum_tables(gh, failures)
        _across(gh, tmp / "across", failures)
        _supersede(gh, tmp / "supersede", failures)
        (tmp / "write").mkdir()
        _verified_write(gh, tmp / "write", failures)
        (tmp / "addon").mkdir()
        _addon(gh, tmp / "addon", failures)
        (tmp / "pulls").mkdir()
        _pulls_and_reach(gh, tmp / "pulls", failures)
        (tmp / "skins").mkdir()
        _card_skins(gh, tmp / "skins", failures)
        (tmp / "replay").mkdir()
        _replay(gh, tmp / "replay", failures)
        (tmp / "skins_replay").mkdir()
        _card_skins_replayed(gh, tmp / "skins_replay", failures)
        _card_skin_luck(gh, tmp / "skin_luck", failures)
        _seasonal_on_load(gh, tmp / "seasonal", failures)
    return failures


def _seasonal_on_load(gh, folder, failures):
    """A Seasonal rerun's pulls land in the release pool off the rates
    the store holds, with nothing noted beforehand: `load` has to note
    the Normal Rescues' list before it files a single record."""
    gh.note_general_pool({})
    store = {"kind": gh.STORE_KIND, "version": 1,
             "records": [
                 _record(1, "gacha_pickup_combatant_30075_1", 1000, [1005]),
                 _record(2, "gacha_pickup_combatant_1052_1", 1001, [1005])],
             "rates": {"gacha_general": {"pools": {"ssr_pool_ids": [
                 "general_ssr_c_1052"]}, "seen": "2026-09-30T00:00:00"}}}
    store_dir = gh.folder_in(folder)
    store_dir.mkdir(parents=True)
    (store_dir / gh.CAPTURED).write_text(json.dumps(store), encoding="utf-8")
    pools = {b["gacha_id"]: b["pool"] for b in gh.load(folder).batches}
    gh.note_general_pool({})         # no list left behind for other checks
    want = {"gacha_pickup_combatant_30075_1": "pickup_combatant",
            "gacha_pickup_combatant_1052_1": "pickup_combatant_rerun"}
    if pools != want:
        failures.append(
            f"loaded, the two reruns' pulls are filed {pools}, not "
            f"{want}. Sereniel is in no Normal Rescue's list and Narja "
            f"is, which is what the rates say and the pity follows.")


# What this check must catch, for `checks/faults.py`.
FAULTS = [
    ("a Card Skin request not followed", "capture.manager:ADDON_TEMPLATE",
     '"history", "gacha_run"):', '"history_not", "gacha_run_not"):',
     "a Card Skin Pack pull was kept as"),
    ("a Card Skin records page not kept", "capture.manager:ADDON_TEMPLATE",
     'records = data.get("card_skin_gacha_history_list")',
     'records = data.get("card_skin_history_not")',
     "after a Card Skin records page the file holds"),
    ("a Card Skin pull not kept off its reply",
     "capture.manager:ADDON_TEMPLATE",
     'if asked[0] == "skin_gacha_run" else None)', "if False else None)",
     "a Card Skin Pack pull was kept as"),
    ("a pull's skins kept in the reply's order",
     "capture.manager:ADDON_TEMPLATE",
     "for row in sorted(pulled, key=lambda r: self._gacha_int(",
     "for row in sorted(pulled, key=lambda r: 0 * self._gacha_int(",
     "a Card Skin Pack pull was kept as"),
    ("a duplicate not marked", "capture.manager:ADDON_TEMPLATE",
     'dup.append(0 if row.get("is_new") else 1)', "dup.append(0)",
     "a Card Skin Pack pull was kept as"),
    ("a pull kept after its record came", "capture.manager:ADDON_TEMPLATE",
     "                 and self._gacha_key(row) not in listed]",
     "                 ]", "after a Card Skin records page the file holds"),
    ("a Card Skin page with nothing new written",
     "capture.manager:ADDON_TEMPLATE",
     'changed = bool(added) or pulls != store["skin_pulls"]',
     "changed = True", "a Card Skin page with nothing new rewrote"),
    ("Card Skin records unguarded on write", "capture.manager:ADDON_TEMPLATE",
     '("skin_records", skin_before)):', '("skin_records", ())):',
     "a write that would drop a Card Skin record"),
    ("the negative binomial's step wrong", "gacha_history:_flat_odds",
     "log_p += math.log(t / (t + 1 - count)) + log_miss",
     "log_p += log_miss", "two Super Rares in 80 pulls"),
    ("the first Super Rare cut as partial", "gacha_history:_skin_pool",
     "stats.first_partial = False", "stats.first_partial = True",
     "the overall luck reads"),
    ("a Super Rare not a 5-star", "gacha_history:SKIN_STARS",
     '"SUPER_RARE": 5', '"SUPER_RARE": 4', "the Card Skin Packs read pulls"),
    ("a duplicate pull not marked in the pool", "gacha_history:_skin_pool",
     "outcome=DUPLICATE if i < len(dup) and dup[i] else None,",
     "outcome=None,", "the Card Skin Packs read pulls"),
    ("the Card Skin Packs listed first", "gacha_history:History.ordered",
     "return known + [self.pools[p] for p in rest] + skins",
     "return skins + known + [self.pools[p] for p in rest]",
     "not the history's last pool"),
    ("the packs counted with the Prism Module", "gacha_history:across_pools",
     "[groups[e.pool] for e in others + prism if groups[e.pool]])",
     "[g for g in groups.values() if g])", "the overall luck reads"),
]
