"""The game client's stat tables agree with what the server said in
battle.

The program reads a combatant's base stats at levels 60 to 62 and a
partner's flat stats at every level off the client
(`game_client.combatants`, `game_client.partner_curves`). The readings
battles give, which the program ships in
`default_settings/shared_facts/shared_facts.json`, are the server's own
word for the same figures. A client table that disagrees has happened
(a combatant whose client figure the server did not use), and where it
does the program takes the reading (`game_data.learned`), so nothing
else would say it.

This holds every shipped reading against the tables as the client lays
them, and the partner curve's rule -- the level steps, plus a promotion
step per ten-level cap passed below the level -- against a curve of the
check's own.

**And each banner's rates** (`game_client.banner_rates`) against every
rates reply the maintainer's captures hold: the ratios and the rates
screen's shares exactly, each pool holding at least every unit the
reply listed. The game adds units to a standing pool with a patch, so
a reply read before one lists fewer.
"""

import json

from ._harness import REPO_ROOT, add_source_to_path, note

NAME = "client stat tables agree with the server's readings"

SHIPPED = (REPO_ROOT / "Vribbels" / "default_settings" / "shared_facts"
           / "shared_facts.json")


class _Client:
    """Three level rows and two promotion rows: a partner whose curve
    the check works out by hand."""

    @staticmethod
    def rows(table):
        stats = ("S_ATK_INC_ADD_OUT", "S_DEF_INC_ADD_OUT",
                 "S_HP_INC_ADD_OUT")

        def row(key, at, values):
            out = {key: str(at), "group": "g"}
            for i, (stat, value) in enumerate(zip(stats, values, strict=True), 1):
                out[f"stat{i}_link_stat_list_id"] = stat
                out[f"stat{i}_value"] = str(value)
            return out
        if table == "partner_base@partner_level":
            return [row("level", level, (level, 0, 2 * level))
                    for level in range(1, 61)]
        if table == "partner_base@partner_ascend":
            return [row("ascend", n, (100, 10, 1000)) for n in (1, 2, 3, 4, 5)]
        if table == "gacha_pool@gacha_pool":
            return [{"id": f"ssr_{n}", "group": "ssr"} for n in (1, 2, 3)]
        if table == "gacha_pity@gacha_pity":
            return [{"id": "p", "ssr_rate_up_pct": "50000",
                     "sr_rate_up_pct": "-1"}]
        if table == "gacha_list@gacha_list":
            return [{"id": "b", "link_gacha_pity_id": "p",
                     "ssr_rate_up_link_gacha_pool_id": "up_1",
                     "ssr_pool_link_gacha_pool_group": "ssr",
                     "ssr_pool_pct": "1000", "sr_pool_pct": "0",
                     "sr_combatant_pool_pct": "0",
                     "sr_supporter_pool_pct": "0", "r_pool_pct": "99000",
                     "total_ssr_pool_pct": "500"}]
        if table == "partner_base@char_partner":
            return [{"id": "1", "link_partner_level_group": "g",
                     "link_partner_ascend_group": "g",
                     "default_atk_add": "7", "default_def_add": "0",
                     "default_hp_add": "0"}]
        return []


def _curve_rule(game_client):
    out = []
    held = game_client.partner_curves(_Client)
    curve = held["curves"][held["partners"][1]]
    for level, promoted in ((1, 0), (10, 0), (11, 1), (20, 1), (21, 2),
                            (60, 5)):
        steps = level * (level + 1) // 2
        want = [7 + steps + 100 * promoted, 10 * promoted,
                2 * steps + 1000 * promoted]
        if curve[level - 1] != want:
            out.append(
                f"`game_client.partner_curves` reads level {level} as "
                f"{curve[level - 1]}, not {want}: the level steps up to "
                f"it plus {promoted} promotion step(s), one per ten-level "
                f"cap passed below it. Every partner reading a battle has "
                f"given follows that rule.")
    return out


def _rates_rule(game_client):
    """A banner of the check's own: half the 5-star rate to the rate-up,
    three units in its standing pool."""
    got = game_client.banner_rates(_Client)["b"]
    want_rates = {"ssr_ratio": 500, "ssr_rate_up_success_ratio": 500,
                  "r_ratio": 99000, "total_ratio": 100000}
    rates = {key: got["rates"].get(key) for key in want_rates}
    out = []
    if rates != want_rates:
        out.append(f"`game_client.banner_rates` gives {rates}, not "
                   f"{want_rates}: a rarity's ratio is its pool's "
                   f"percentage less the rate-up's share.")
    pools = {key: got["pools"][key] for key in
             ("ssr_pool_ids", "ssr_rate_up_success_pool_ids")}
    want_pools = {"ssr_pool_ids": ["ssr_1", "ssr_2", "ssr_3"],
                  "ssr_rate_up_success_pool_ids": ["up_1"]}
    if pools != want_pools:
        out.append(f"`game_client.banner_rates` lists the pools as "
                   f"{pools}, not {want_pools}: which the client's pool "
                   f"lacks units its group names.")
    return out


def _banner_rates(game_client):
    """The client's rates against the captured replies."""
    import gacha_history
    snapshots = REPO_ROOT / "Vribbels" / "snapshots"
    captured, _note = gacha_history.read_store(
        gacha_history.folder_in(snapshots) / gacha_history.CAPTURED)
    replies = (captured or {}).get("rates") or {}
    if not replies:
        note("no captured rates reply, so the client's banner rates were "
             "held to nothing")
        return []
    client = game_client.known_banner_rates()
    out = []
    for banner, reply in sorted(replies.items()):
        mine = client.get(banner)
        if mine is None:
            continue
        for part in ("rates", "total_rate_info"):
            want = reply.get(part) or {}
            got = {key: mine[part].get(key, 0) for key in want}
            if got != want:
                out.append(
                    f"{banner}'s {part}: the client gives {got}, the "
                    f"server answered {want}. See "
                    f"`game_client.banner_rates`: a rarity's ratio is its "
                    f"pool's percentage less the rate-up's share.")
        for pool, ids in sorted((reply.get("pools") or {}).items()):
            gone = sorted(set(ids) - set(mine["pools"].get(pool, ())))
            if gone:
                out.append(
                    f"{banner}'s {pool}: the server listed {gone}, which "
                    f"the client's pool lacks. A pool only grows; look at "
                    f"the banner's pool group in `gacha_list`.")
    return out


def run():
    add_source_to_path()
    import game_client
    from game_data.characters import CHARACTERS, table_stats_at_level
    from game_data.partners import PARTNER_CURVES, table_partner_stats

    out = (_curve_rule(game_client) + _rates_rule(game_client)
           + _banner_rates(game_client))
    facts = json.loads(SHIPPED.read_text(encoding="utf-8"))["facts"]
    for rid, levels in sorted(facts.get("base_stats", {}).items()):
        char = CHARACTERS.get(int(rid))
        if not isinstance(char, dict):
            continue
        for level, reading in sorted(levels.items()):
            got = table_stats_at_level(char, int(level))
            got = [got["base_atk"], got["base_def"], got["base_hp"]]
            if got != reading["base"]:
                out.append(
                    f"{char.get('name')} ({rid}) at level {level}: the "
                    f"client's tables give {got}, a battle read "
                    f"{reading['base']}. The program uses the reading; "
                    f"look at the client's `char_base` row, or at a patch "
                    f"the shipped extract has not caught up with.")
    for pid, levels in sorted(facts.get("partner_stats", {}).items()):
        if int(pid) not in PARTNER_CURVES:
            continue
        for level, reading in sorted(levels.items()):
            got = table_partner_stats(int(pid), int(level))
            got = [got["atk"], got["def"], got["hp"]]
            if got != reading["flat"]:
                out.append(
                    f"partner {pid} at level {level}: the client's curve "
                    f"gives {got}, a battle read {reading['flat']}. The "
                    f"program uses the reading; look at "
                    f"`game_client.partner_curves` and the partner's "
                    f"level and promotion groups.")
    return out


FAULTS = [
    ("promotions counted at the cap itself", "game_client:partner_curves",
     "                caps = min(-(-level // 10) - 1, PROMOTIONS)",
     "                caps = min(level // 10, PROMOTIONS)",
     "ten-level cap passed below it"),
    ("the partner's own starting stats left out",
     "game_client:partner_curves",
     "        base = [_figure(row.get(f\"default_{stat}_add\")) or 0",
     "        base = [0 * (_figure(row.get(f\"default_{stat}_add\")) or 0)",
     "the level steps up to"),
    ("the rate-up's share left in the rarity's ratio",
     "game_client:banner_rates",
     '        rates = {"ssr_ratio": figures["ssr_pool_pct"] - ssr_share,',
     '        rates = {"ssr_ratio": figures["ssr_pool_pct"],',
     "a rarity's ratio is its pool's percentage"),
    ("a standing pool read short", "game_client:banner_rates",
     "            pools[key] = (list(groups.get(group, ()))",
     "            pools[key] = (list(groups.get(group, ()))[:-1]",
     "which the client's pool lacks"),
    ("the curve not consulted", "game_data.partners:table_partner_stats",
     "    if curve and 1 <= level <= len(curve):\n"
     "        atk, def_, hp = curve[level - 1]",
     "    if False:\n"
     "        atk, def_, hp = curve[level - 1]",
     "the client's curve gives"),
]
