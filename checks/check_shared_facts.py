"""Game facts shared between players, and what must never be among them.

`shared_facts.py` gathers facts about the GAME out of an account's
captures, ships the maintainer's with the program, and writes the file
a player sends in -- which is published in a GitHub issue. So this holds
first that **nothing about an account reaches either file**: no id, no
name, no rank or score of its own, whatever the captures beside the
facts hold. A leak there is silent in the worst way; nothing in the
program ever reads the fields it should not have copied.

Then the rules a merge and a reader live by: a malformed or hostile
entry is dropped rather than trusted, folding is idempotent, keeps the
better of two readings and never drops anything, a later reading is
news only for a season that is over, and every reader takes a shipped
fact only where the account has none of its own -- the rankings only
from the account's own server.

No Tk and no snapshot needed.
"""

import importlib.util
import json
import tempfile
from pathlib import Path

from ._harness import SOURCE_ROOT, add_source_to_path, note

NAME = "shared game facts carry nothing about an account"

USER_ID = 300001105178
# The account's own standing, planted beside the facts. None of these
# may appear in anything `collect` returns.
OWN_RANK, OWN_SCORE = 987654, 1115731
PLANTED = (str(USER_ID), "Ikkoru", "Stranger", str(OWN_RANK),
           str(OWN_SCORE), "182120591", "user_id", "name", "seen",
           "2026-09-23", "score_record", "condition_type", "tracked",
           "currency", "evil", "rank_percent", "0.83", "reward_count")

RATES = {"rates": {"total_ratio": 100000, "ssr_ratio": 500},
         "total_rate_info": {"total_ssr_pool_pct": 714.48},
         "pools": {"ssr_rate_up_success_pool_ids":
                   ["pickup_c_16_rateup_ssr_c_30117"],
                   "sr_pool_ids": []}}
SEASON, HALF = "disaster_s04", "disaster_s04_rank_02"
NEXT_SEASON, NEXT_HALF = "disaster_s05", "disaster_s05_rank_01"
MASTER_I, DIAMOND_I = "disaster_s04_rank_best_2_30", "disaster_s04_rank_best_2_25"
OFFENSIVE = "remnants_boss_penalty_005"


def _planted_inputs():
    """(raw, history, captured, checklist), each carrying account
    fields beside the facts, the way the real files do."""
    raw = {
        "detected_region": "global",
        "user": {"user_id": USER_ID, "name": "Ikkoru"},
        "combatant_trial_slots": {
            "event_combatant_trial_4": ["combatant_trial_1052",
                                        "https://evil.example/x"],
            "not an id": ["combatant_trial_1021"]},
        "disaster_boss_rank_tops": {SEASON: {HALF: {MASTER_I: [
            {"rank": 1, "best_score": 1635631,
             "score_record": 163563143483397, "read_at": 1790272379,
             "region": "global", "user_id": USER_ID, "name": "Stranger"}]}}},
        "disaster_boss_rank_entities": {SEASON: {HALF: {
            "rank": OWN_RANK, "best_score": OWN_SCORE, "user_id": USER_ID}}},
        "mission_accumulate": [{"res_id": "ac_collection_003",
                                "score": 182120591, "user_id": USER_ID,
                                "condition_type": "GET_ITEM__ID"}],
        "chaos_assault_rankings": {"assault_1_s7": {"readings": [
            {"rank": OWN_RANK, "score": OWN_SCORE, "total_count": 19552,
             "top_score": 65084, "read_at": 1790262663,
             "region": "global"}]}},
        # The Offensive's field comes from the account's own rank and
        # percentage -- 441 at 0.83% -- and only the field may leave.
        "remnants_rankings": {OFFENSIVE: {"readings": [
            {"rank": 441, "rank_percent": 0.83, "reward_count": 9,
             "score": OWN_SCORE, "read_at": 1790000100}]}},
    }
    # An old debug log's sample: no server of its own, so it takes the
    # snapshot's.
    history = {"disaster_boss_rank_tops": {SEASON: {HALF: {DIAMOND_I: [
        {"rank": 948, "best_score": 1219348, "read_at": 1790291693}]}}}}
    captured = {"rates": {"gacha_pickup_combatant_30117": dict(
        RATES, seen="2026-09-23T14:48:33", user_id=USER_ID)},
        "records": [{"id": "1", "user_id": USER_ID}]}
    checklist = {"events": {"event_stock": {"event_stock_01": 17}},
                 "finals": {"event_stock": ["event_stock_01"]},
                 "tracked": {"town_shop_goods_005": True},
                 "currency": {"2000031": {"kind": "total",
                                          "points": [[1027, 0]]}},
                 "finished": {"event_schedule_devil_001": [21, 21]}}
    return raw, history, captured, checklist


def _whitelist(sf):
    out = []
    facts = sf.collect(*_planted_inputs())
    text = json.dumps(facts)
    leaked = [p for p in PLANTED if p in text]
    if leaked:
        out.append(
            f"`collect` let {leaked} through. The file it feeds is "
            f"published in a GitHub issue, and an account's id, name, "
            f"own standing or a field the whitelist does not name must "
            f"never reach it.")
    tops = facts[sf.TOPS].get("global", {}).get(SEASON, {}).get(HALF, {})
    want = {
        "the banner's rates": "gacha_pickup_combatant_30117"
        in facts[sf.RATES],
        "the trial slot": facts[sf.SLOTS].get("event_combatant_trial_4")
        == ["combatant_trial_1052"],
        "the instalment total": facts[sf.TOTALS]
        == {"event_stock": {"event_stock_01": 17}},
        "the final reward": facts[sf.FINALS]
        == {"event_stock": ["event_stock_01"]},
        "the stamped top": tops.get(MASTER_I, {}).get("rank") == 1,
        "the old log's top, on the snapshot's server": DIAMOND_I in tops,
        "the Sortie's field": facts[sf.SORTIE] == {"global": {
            "assault_1_s7": {"players": 19552, "top_score": 65084,
                             "read_at": 1790262663}}},
        "the Offensive's field, to the hundred": facts[sf.OFFENSIVE] == {
            "global": {OFFENSIVE: {"players": 53100,
                                   "read_at": 1790000100}}},
    }
    missed = [what for what, ok in want.items() if not ok]
    if missed:
        out.append(
            f"`collect` lost {missed} from planted captures. A whitelist "
            f"that drops the facts too passes the leak test above for "
            f"the wrong reason.")
    return out


def _clean_refuses(sf):
    hostile = {
        sf.RATES: {"gacha_a": {"rates": {"r": 1}, "total_rate_info": {}},
                   "gacha b": RATES},
        sf.TOTALS: {"event_stock": {"event_stock_01": "17",
                                    "event_stock_02": 5000,
                                    "event_stock_03": True,
                                    "event_stock_04": 17}},
        sf.FINALS: {"event_stock": ["event_stock_01", 7, "a b"]},
        sf.TOPS: {"moon": {SEASON: {HALF: {MASTER_I: {
            "rank": 1, "read_at": 5}}}},
                  "global": {SEASON: {HALF: {
                      MASTER_I: {"rank": 0, "read_at": 5},
                      DIAMOND_I: {"rank": 9, "read_at": 5,
                                  "best_score": 7, "name": "Stranger"}}}}},
        sf.SORTIE: {"global": {"assault_1_s6": {"players": "24684",
                                                "read_at": 5},
                               "assault_1_s7": {"players": 19716,
                                                "read_at": 5, "rank": 739,
                                                "top_score": -1}}},
        sf.OFFENSIVE: {"global": {OFFENSIVE: {"players": 57500},
                                  "remnants 6": {"players": 1,
                                                 "read_at": 5}}},
    }
    got = sf.clean(hostile)
    want = {sf.RATES: {}, sf.SLOTS: {},
            sf.TOTALS: {"event_stock": {"event_stock_04": 17}},
            sf.FINALS: {"event_stock": ["event_stock_01"]},
            sf.TOPS: {"global": {SEASON: {HALF: {DIAMOND_I: {
                "rank": 9, "read_at": 5, "best_score": 7}}}}},
            sf.SORTIE: {"global": {"assault_1_s7": {
                "players": 19716, "read_at": 5, "top_score": None}}},
            sf.OFFENSIVE: {}}
    if got != want:
        return [f"`clean` kept {got!r} of a hostile file, not {want!r}. "
                f"A rates entry missing a part, an id that is not one, a "
                f"count that is not a whole number in range, an unknown "
                f"server, a reading with no time, and every field the "
                f"whitelist does not name must all go -- a contributed "
                f"file is anyone's."]
    return []


def _fold_rules(sf):
    out = []
    top = {"rank": 1, "best_score": 10, "read_at": 100}
    field = {"players": 19000, "top_score": 60000, "read_at": 100}
    first = {sf.RATES: {"gacha_a": RATES},
             sf.SLOTS: {"event_t": ["slot_1"]},
             sf.TOTALS: {"event_f": {"event_f_1": 17}},
             sf.FINALS: {"event_f": ["event_f_1"]},
             sf.TOPS: {"global": {SEASON: {HALF: {MASTER_I: top}}}},
             sf.SORTIE: {"global": {"assault_1_s7": field}}}
    held, added, _refused = sf.fold(sf.empty(), first)
    again, added_again, refused_again = sf.fold(held, first)
    if again != held or added_again or refused_again:
        out.append(f"folding the same facts twice changed the result or "
                   f"reported {added_again + refused_again}. The build "
                   f"folds the maintainer's own facts on every run, so a "
                   f"fold that is not idempotent rewrites the shipped "
                   f"file each time.")
    other = dict(RATES, rates={"total_ratio": 1})
    held, _added, refused = sf.fold(held, {
        sf.RATES: {"gacha_a": other},
        sf.SLOTS: {"event_t": ["slot_2"]},
        sf.TOTALS: {"event_f": {"event_f_1": 21}},
        sf.TOPS: {"global": {SEASON: {HALF: {MASTER_I: dict(
            top, read_at=200, best_score=12)}}}},
        sf.SORTIE: {"global": {"assault_1_s7": dict(
            field, read_at=300)}}})
    held, _added, _refused = sf.fold(held, {
        sf.TOTALS: {"event_f": {"event_f_1": 12}},
        sf.TOPS: {"global": {SEASON: {HALF: {MASTER_I: dict(
            top, read_at=50, best_score=9)}}}}})
    want = {"rates kept": held[sf.RATES]["gacha_a"] == sf.clean(
                {sf.RATES: {"gacha_a": RATES}})[sf.RATES]["gacha_a"],
            "rates refused": len(refused) == 1,
            "slots unioned": held[sf.SLOTS]["event_t"] == ["slot_1",
                                                           "slot_2"],
            "the bigger total": held[sf.TOTALS]["event_f"]["event_f_1"] == 21,
            "the later top": held[sf.TOPS]["global"][SEASON][HALF][
                MASTER_I]["read_at"] == 200,
            "a later field saying the same left alone": held[sf.SORTIE][
                "global"]["assault_1_s7"]["read_at"] == 100}
    wrong = [what for what, ok in want.items() if not ok]
    if wrong:
        out.append(
            f"folding broke {wrong}. A banner read two ways is refused "
            f"rather than replaced, slots are unioned, the bigger total "
            f"and a later reading that says something new win in either "
            f"order, and one that says the same changes nothing -- or "
            f"every build rewrites the shipped file for a new timestamp.")
    return out


def _missing_rules(sf):
    out = []
    top = {"rank": 1, "best_score": 10, "read_at": 100}
    shipped = sf.clean({
        sf.RATES: {"gacha_a": RATES},
        sf.TOTALS: {"event_f": {"event_f_1": 17, "event_f_2": 17}},
        sf.TOPS: {"global": {SEASON: {HALF: {MASTER_I: top}}}}})
    mine = sf.clean({
        sf.RATES: {"gacha_a": RATES, "gacha_b": RATES},
        sf.TOTALS: {"event_f": {"event_f_1": 17, "event_f_2": 21}},
        sf.TOPS: {"global": {SEASON: {HALF: {
            MASTER_I: dict(top, read_at=900, best_score=12),
            DIAMOND_I: dict(top, rank=948)}}},
                  "asia": {SEASON: {HALF: {MASTER_I: top}}}}})
    counts = sf.tally(sf.missing(mine, shipped))
    want = dict.fromkeys(sf.KINDS, 0)
    want.update({sf.RATES: 1, sf.TOTALS: 1, sf.TOPS: 2})
    if counts != want:
        out.append(
            f"`missing` counts {counts}, not {want}. A banner or a "
            f"subdivision the shipped facts lack is new, and so is a "
            f"bigger total; a later reading of the season RUNNING is "
            f"not, or every active account reads yellow every week. The "
            f"other server's top is new: they rank different players.")
    # A later half known: the one before is over, and a later reading
    # of it that says something new is worth sending. One that says
    # the same is not.
    later = {sf.TOPS: {"global": {NEXT_SEASON: {NEXT_HALF: {
        "disaster_s05_rank_best_1_30": top}}}}}
    for says, want_tops in ((12, 1), (10, 0)):
        mine_now = sf.clean(dict(later, **{sf.TOPS: {"global": dict(
            later[sf.TOPS]["global"], **{SEASON: {HALF: {MASTER_I: dict(
                top, read_at=900, best_score=says)}}})}}))
        got = sf.tally(sf.missing(mine_now, sf.fold(shipped, later)[0]))
        if got[sf.TOPS] != want_tops:
            out.append(
                f"a later reading of a half that is over, scoring "
                f"{says} where the shipped one scored 10, counts "
                f"{got[sf.TOPS]} tops to send, not {want_tops}. A "
                f"season's final figures arrive only this way.")
    # The same for the Sortie: season 6 is over once 7 is known.
    shipped = sf.clean({sf.SORTIE: {"global": {
        "assault_1_s6": {"players": 20000, "top_score": 60000,
                         "read_at": 100},
        "assault_1_s7": {"players": 15000, "top_score": 50000,
                         "read_at": 100}}}})
    mine = sf.clean({sf.SORTIE: {"global": {
        "assault_1_s6": {"players": 24684, "top_score": 66265,
                         "read_at": 900},
        "assault_1_s7": {"players": 19716, "top_score": 65084,
                         "read_at": 900}}}})
    news = sf.missing(mine, shipped)[sf.SORTIE].get("global", {})
    if sorted(news) != ["assault_1_s6"]:
        out.append(f"of a Sortie season over and one running, `missing` "
                   f"finds {sorted(news)} worth sending, not the one "
                   f"that is over.")
    if sf.describe({sf.RATES: 1, sf.TOPS: 2, sf.OFFENSIVE: 1}) != (
            "1 banner's rates, 2 Great Rift division tops, "
            "1 Full-Scale Offensive"):
        out.append(f"the export would say "
                   f"{sf.describe({sf.RATES: 1, sf.TOPS: 2})!r}.")
    return out


def _documents(sf):
    facts = sf.clean({sf.TOTALS: {"event_f": {"event_f_1": 17}}})
    data = sf.document(facts, app_version="9.9.9", region="global",
                       exported="2026-09-25")
    out = []
    if sf.read_document(json.loads(json.dumps(data))) != facts:
        out.append("an exported file does not read back as the facts "
                   "written into it.")
    if sf.read_document(dict(data, kind="vribbels gacha history")) \
            is not None:
        out.append("a file of another kind reads as shared facts.")
    return out


def _shipped_file(sf):
    path = sf.shipped_path(SOURCE_ROOT / "default_settings")
    if not path.exists():
        note("no default_settings/shared_facts.json to check; "
             "`fold_shared_facts.py` writes it")
        return []
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    out = []
    if set(data) != {"kind", "version", "facts"} or not sf.whole(data):
        out.append(
            f"the shipped {path.name} is not exactly what `clean` keeps: "
            f"it holds keys {sorted(data)}, or entries the whitelist "
            f"drops. It ships to every player -- fold into it with "
            f"`fold_shared_facts.py`, never by hand.")
    leaked = [p for p in ("user_id", "name", "nickname", "seen",
                          "rank_percent") if '"%s"' % p in text]
    if leaked:
        out.append(f"the shipped {path.name} carries {leaked}.")
    return out


def _fold_script(sf):
    """The build's fold: it finds its target, and it stops rather than
    lose anything."""
    script = (SOURCE_ROOT / "default_settings" / "normalize"
              / "fold_shared_facts.py")
    spec = importlib.util.spec_from_file_location("_fold", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    want = sf.shipped_path(SOURCE_ROOT / "default_settings")
    if Path(module.TARGET) != want:
        return [f"fold_shared_facts.py writes {module.TARGET}, not "
                f"{want}. It finds its target by walking up from its own "
                f"file, so a move points the build at nothing."]
    out = []
    work = Path(tempfile.mkdtemp(prefix="shared_facts_fold_"))
    saved = module.TARGET
    module.TARGET = work / sf.FILE_NAME
    whole = sf.document({sf.TOTALS: {"event_f": {"event_f_1": 17}}})
    older = dict(whole, facts={sf.TOTALS: whole["facts"][sf.TOTALS]})
    try:
        for text, refuse in (
                ("{ not json", True),
                (json.dumps(dict(whole, facts=dict(
                    whole["facts"], future_kind={"x": 1}))), True),
                (json.dumps(dict(whole, facts=dict(
                    whole["facts"], **{sf.TOTALS: {
                        "event_f": {"event_f_1": "17"}}}))), True),
                (json.dumps(older), False)):
            module.TARGET.write_text(text, encoding="utf-8")
            try:
                module._read_shipped()
                refused = False
            except SystemExit:
                refused = True
            if refused != refuse:
                out.append(
                    f"the fold {'read' if refuse else 'refused'} a "
                    f"shipped file of {text[:60]!r}. One that will not "
                    f"read or would lose entries has to stop the build: "
                    f"folding into it rebuilds it from the maintainer's "
                    f"captures alone. One merely older than the code is "
                    f"fine.")
    finally:
        module.TARGET = saved
    before = sf.clean({sf.RATES: {"gacha_a": RATES},
                       sf.TOPS: {"global": {SEASON: {HALF: {MASTER_I: {
                           "rank": 1, "read_at": 200}}}}}})
    after = sf.clean({sf.TOPS: {"global": {SEASON: {HALF: {MASTER_I: {
        "rank": 1, "read_at": 100}}}}}})
    if len(sf.lost(before, after)) != 2 or sf.lost(before, before):
        out.append(f"`lost` finds {sf.lost(before, after)} between a file "
                   f"and one missing its banner and holding an older "
                   f"top. It is the fold's last guard against dropping "
                   f"what players sent.")
    return out


def _regions_agree(sf):
    from capture.constants import SERVERS
    if tuple(sf.REGIONS) != tuple(SERVERS):
        return [f"shared_facts.REGIONS is {sf.REGIONS} and the capture's "
                f"servers are {tuple(SERVERS)}. A reading stamped with a "
                f"server `clean` does not know is dropped."]
    return []


def _readers(sf):
    out = []
    import checklist_manager
    import gacha_history as gh
    import stats_history as sh

    # The Great Rift: shipped tops fill the account's half, and a half
    # it never played gets a column of its own -- on its server only.
    shipped = sf.clean({sf.TOPS: {"global": {
        SEASON: {HALF: {DIAMOND_I: {"rank": 948, "best_score": 1219348,
                                    "read_at": 1790291693}}},
        NEXT_SEASON: {NEXT_HALF: {"disaster_s05_rank_best_1_25": {
            "rank": 900, "best_score": 1300000, "read_at": 1791000000}}}}}})
    raw = {"detected_region": "global", "disaster_boss_rank_entities": {
        SEASON: {HALF: {"rank": 2474, "best_score": 1115731}}}}
    rows, columns = sh.rift_table(raw, None, shipped)
    cells = {heading: dict(zip(rows, values)) for heading, values in columns}
    if not cells.get("4 p2", {}).get("Out of") \
            or cells.get("5 p1", {}).get("Top #") is not None \
            or not cells.get("5 p1", {}).get("Out of"):
        out.append(f"the Great Rift list reads {cells}: the account's "
                   f"half has to take its field from a shipped top, and "
                   f"a shipped half it never played gets a column of the "
                   f"field's figures alone.")
    rows, columns = sh.rift_table(dict(raw, detected_region="asia"), None,
                                  shipped)
    if [heading for heading, _v in columns] != ["4 p2"] or dict(
            zip(rows, columns[0][1])).get("Out of"):
        out.append("an Asia account's Great Rift list took Global tops. "
                   "The two servers rank different players.")

    # The Sortie: a shipped season the account never read is a column
    # of its field; one it read keeps its own reading whole.
    shipped = sf.clean({sf.SORTIE: {"global": {
        "assault_1_s6": {"players": 24684, "top_score": 66265,
                         "read_at": 900},
        "assault_1_s7": {"players": 1, "top_score": 1, "read_at": 900}}}})
    raw = {"detected_region": "global", "chaos_assault_rankings": {
        "assault_1_s7": {"readings": [{"rank": 739, "total_count": 19552,
                                       "score": 45512, "top_score": 65084,
                                       "read_at": 5}]}}}
    rows, columns = sh.sortie_table(raw, None, shipped)
    cells = {heading: dict(zip(rows, values)) for heading, values in columns}
    if cells.get("6", {}).get("Out of") != "24,684" \
            or cells.get("6", {}).get("Top #") is not None \
            or cells.get("7", {}).get("Out of") != "19,552":
        out.append(f"the Sortie list reads {cells}: a shipped season the "
                   f"account never read is a column of its field, and a "
                   f"season it read keeps its own figures.")

    # The Offensive: the same, and a reading that never stated its
    # percentage takes the shipped field.
    shipped = sf.clean({sf.OFFENSIVE: {"global": {
        OFFENSIVE: {"players": 57500, "read_at": 900},
        "remnants_boss_penalty_004": {"players": 41000, "read_at": 900}}}})
    raw = {"detected_region": "global", "remnants_rankings": {
        OFFENSIVE: {"readings": [{"rank": 506, "rank_percent": None,
                                  "read_at": 5}]}}}
    rows, columns = sh.offensive_table(raw, None, shipped)
    cells = {heading: dict(zip(rows, values)) for heading, values in columns}
    if cells.get("5", {}).get("Out of") != "~57,500" \
            or cells.get("5", {}).get("Top #") != "506" \
            or cells.get("4", {}).get("Out of") != "~41,000":
        out.append(f"the Offensive list reads {cells}.")

    # The Checklist's store: shipped instalments vote.
    work = Path(tempfile.mkdtemp(prefix="shared_facts_"))
    manager = checklist_manager.ChecklistManager(work)
    shipped = sf.clean({sf.TOTALS: {"event_f": {"event_f_1": 25,
                                                "event_f_2": 25}},
                        sf.FINALS: {"event_f": ["event_f_1"]}})
    if manager.event_total("event_f", shipped=shipped) != 25 \
            or not manager.pays_final("event_f", shipped=shipped):
        out.append("the Checklist's store ignored shipped instalments: "
                   "a family's pattern has to reach an account that "
                   "missed its past instalments.")
    if manager.event_total("event_f") is not None:
        out.append("an instalment total appeared with nothing recorded "
                   "and nothing shipped.")

    # The Gacha History: a banner never read here takes shipped rates,
    # and one read here keeps its own.
    folder = gh.folder_in(work)
    folder.mkdir(parents=True)
    own = dict(RATES, rates={"total_ratio": 7})
    (folder / gh.CAPTURED).write_text(json.dumps({
        "kind": gh.STORE_KIND, "records": [],
        "rates": {"gacha_a": own}}), encoding="utf-8")
    shipped = sf.clean({sf.RATES: {"gacha_a": RATES, "gacha_b": RATES}})
    rates = gh.load(folder, shipped=shipped).rates
    if rates.get("gacha_a") != own or "gacha_b" not in rates:
        out.append(f"the Gacha History's rates read {sorted(rates)}: a "
                   f"banner read here keeps its own rates, and one never "
                   f"read takes the shipped ones.")
    return out


def run():
    add_source_to_path()
    import shared_facts as sf
    failures = []
    for part in (_whitelist, _clean_refuses, _fold_rules, _missing_rules,
                 _documents, _shipped_file, _fold_script, _regions_agree,
                 _readers):
        failures.extend(part(sf))
    return failures
