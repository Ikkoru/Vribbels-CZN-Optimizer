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
    cases = {
        "gacha_pickup_combatant_30117": ("pickup_combatant", 30117),
        "gacha_pickup_combatant_1052_1": ("pickup_combatant_rerun", 1052),
        "gacha_pickup_supporter_20002_1": ("pickup_supporter_rerun", 20002),
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
                f"-- a rerun is a category of its own, with its own.")
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


# ------------------------------------------------------------ real data

def _history_log():
    """The newest loose debug log that carries a history page, or None."""
    logs = sorted((SOURCE_ROOT / "snapshots").glob(
        "websocket_debug_*.jsonl.gz"), reverse=True)
    for path in logs:
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                if "gacha_history_list" in f.read():
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
        _across_math(gh, failures)
        _across(gh, tmp / "across", failures)
        _supersede(gh, tmp / "supersede", failures)
        (tmp / "write").mkdir()
        _verified_write(gh, tmp / "write", failures)
        (tmp / "addon").mkdir()
        _addon(gh, tmp / "addon", failures)
        (tmp / "replay").mkdir()
        _replay(gh, tmp / "replay", failures)
    return failures
