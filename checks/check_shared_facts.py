"""Game facts shared between players, and what must never be among them.

`shared_facts.py` gathers facts about the GAME out of an account's
captures, ships the maintainer's with the program, and writes the file
a player sends in -- which is published in a GitHub issue. So this holds
first that **nothing about an account reaches either file**: no id, no
name, no rank or score of its own, whatever the captures beside the
facts hold. A leak there is silent in the worst way; nothing in the
program ever reads the fields it should not have copied.

Then the rules a merge and a reader live by: a malformed or hostile
entry is dropped rather than trusted, folding is idempotent and keeps
the better of two readings, and every reader takes a shipped fact only
where the account has none of its own -- the Great Rift's tops only
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
           "currency", "evil")

RATES = {"rates": {"total_ratio": 100000, "ssr_ratio": 500},
         "total_rate_info": {"total_ssr_pool_pct": 714.48},
         "pools": {"ssr_rate_up_success_pool_ids":
                   ["pickup_c_16_rateup_ssr_c_30117"],
                   "sr_pool_ids": []}}
SEASON, HALF = "disaster_s04", "disaster_s04_rank_02"
MASTER_I, DIAMOND_I = "disaster_s04_rank_best_2_30", "disaster_s04_rank_best_2_25"


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
            {"rank": OWN_RANK, "score": OWN_SCORE, "total_count": 19552}]}},
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
    want = {
        "the banner's rates": "gacha_pickup_combatant_30117"
        in facts[sf.RATES],
        "the trial slot": facts[sf.SLOTS].get("event_combatant_trial_4")
        == ["combatant_trial_1052"],
        "the instalment total": facts[sf.TOTALS]
        == {"event_stock": {"event_stock_01": 17}},
        "the final reward": facts[sf.FINALS]
        == {"event_stock": ["event_stock_01"]},
        "the stamped top": facts[sf.TOPS].get("global", {}).get(
            SEASON, {}).get(HALF, {}).get(MASTER_I, {}).get("rank") == 1,
        "the old log's top, on the snapshot's server":
            DIAMOND_I in facts[sf.TOPS].get("global", {}).get(
                SEASON, {}).get(HALF, {}),
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
    }
    got = sf.clean(hostile)
    want = {sf.RATES: {}, sf.SLOTS: {},
            sf.TOTALS: {"event_stock": {"event_stock_04": 17}},
            sf.FINALS: {"event_stock": ["event_stock_01"]},
            sf.TOPS: {"global": {SEASON: {HALF: {DIAMOND_I: {
                "rank": 9, "read_at": 5, "best_score": 7}}}}}}
    if got != want:
        return [f"`clean` kept {got!r} of a hostile file, not {want!r}. "
                f"A rates entry missing a part, an id that is not one, a "
                f"count that is not a whole number in range, an unknown "
                f"server, a rank of 0 and every field the whitelist does "
                f"not name must all go -- a contributed file is anyone's."]
    return []


def _fold_rules(sf):
    out = []
    top = {"rank": 1, "best_score": 10, "read_at": 100}
    first = {sf.RATES: {"gacha_a": RATES},
             sf.SLOTS: {"event_t": ["slot_1"]},
             sf.TOTALS: {"event_f": {"event_f_1": 17}},
             sf.FINALS: {"event_f": ["event_f_1"]},
             sf.TOPS: {"global": {SEASON: {HALF: {MASTER_I: top}}}}}
    held, added, _refused = sf.fold(sf.empty(), first)
    again, added_again, refused_again = sf.fold(held, first)
    if again != held or added_again or refused_again:
        out.append(f"folding the same facts twice changed the result or "
                   f"reported {added_again + refused_again}. The build "
                   f"folds the maintainer's own facts on every run, so a "
                   f"fold that is not idempotent rewrites the shipped "
                   f"file each time.")
    later = dict(top, read_at=200, best_score=12)
    earlier = dict(top, read_at=50, best_score=9)
    other = dict(RATES, rates={"total_ratio": 1})
    held, _added, refused = sf.fold(held, {
        sf.RATES: {"gacha_a": other},
        sf.SLOTS: {"event_t": ["slot_2"]},
        sf.TOTALS: {"event_f": {"event_f_1": 21}},
        sf.TOPS: {"global": {SEASON: {HALF: {MASTER_I: later}}}}})
    held, _added, _refused = sf.fold(held, {
        sf.TOTALS: {"event_f": {"event_f_1": 12}},
        sf.TOPS: {"global": {SEASON: {HALF: {MASTER_I: earlier}}}}})
    want = {"rates kept": held[sf.RATES]["gacha_a"] == sf.clean(
                {sf.RATES: {"gacha_a": RATES}})[sf.RATES]["gacha_a"],
            "rates refused": len(refused) == 1,
            "slots unioned": held[sf.SLOTS]["event_t"] == ["slot_1",
                                                           "slot_2"],
            "the bigger total": held[sf.TOTALS]["event_f"]["event_f_1"] == 21,
            "the later top": held[sf.TOPS]["global"][SEASON][HALF][
                MASTER_I]["read_at"] == 200}
    wrong = [what for what, ok in want.items() if not ok]
    if wrong:
        out.append(
            f"folding broke {wrong}. A banner read two ways is refused "
            f"rather than replaced, slots are unioned, and the bigger "
            f"instalment total and the later top win in either order.")
    return out


def _missing_rules(sf):
    top = {"rank": 1, "best_score": 10, "read_at": 100}
    shipped = sf.clean({
        sf.RATES: {"gacha_a": RATES},
        sf.TOTALS: {"event_f": {"event_f_1": 17, "event_f_2": 17}},
        sf.TOPS: {"global": {SEASON: {HALF: {MASTER_I: top}}}}})
    mine = sf.clean({
        sf.RATES: {"gacha_a": RATES, "gacha_b": RATES},
        sf.TOTALS: {"event_f": {"event_f_1": 17, "event_f_2": 21}},
        sf.TOPS: {"global": {SEASON: {HALF: {
            MASTER_I: dict(top, read_at=900),
            DIAMOND_I: dict(top, rank=948)}}},
                  "asia": {SEASON: {HALF: {MASTER_I: top}}}}})
    counts = sf.tally(sf.missing(mine, shipped))
    want = {sf.RATES: 1, sf.SLOTS: 0, sf.TOTALS: 1, sf.FINALS: 0, sf.TOPS: 2}
    if counts != want:
        return [f"`missing` counts {counts}, not {want}. A banner or a "
                f"subdivision the shipped facts lack is new, and so is a "
                f"bigger total; a later sample of a top they hold is not "
                f"-- or every active account reads yellow every week. "
                f"The other server's top is new: they rank different "
                f"players."]
    if sf.describe(counts) != ("1 banner's rates, 1 event reward total, "
                               "2 Great Rift division tops"):
        return [f"the panel would say {sf.describe(counts)!r}."]
    return []


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
    if set(data) != {"kind", "version", "facts"} \
            or sf.read_document(data) != data["facts"]:
        out.append(
            f"the shipped {path.name} is not exactly what `clean` keeps: "
            f"it holds keys {sorted(data)}, or entries the whitelist "
            f"drops. It ships to every player -- fold into it with "
            f"`fold_shared_facts.py`, never by hand.")
    leaked = [p for p in ("user_id", "name", "nickname", "seen")
              if '"%s"' % p in text]
    if leaked:
        out.append(f"the shipped {path.name} carries {leaked}.")
    return out


def _fold_script_finds_its_target(sf):
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
    return []


def _regions_agree(sf):
    from capture.constants import SERVERS
    if tuple(sf.REGIONS) != tuple(SERVERS):
        return [f"shared_facts.REGIONS is {sf.REGIONS} and the capture's "
                f"servers are {tuple(SERVERS)}. A top stamped with a "
                f"server `clean` does not know is dropped."]
    return []


def _readers(sf):
    out = []
    import checklist_manager
    import gacha_history as gh
    import stats_history as sh

    # The Great Rift: the shipped tops fill the account's half -- on
    # its own server only.
    shipped = sf.clean({sf.TOPS: {"global": {SEASON: {HALF: {
        DIAMOND_I: {"rank": 948, "best_score": 1219348,
                    "read_at": 1790291693}}}}}})
    raw = {"detected_region": "global", "disaster_boss_rank_entities": {
        SEASON: {HALF: {"rank": 2474, "best_score": 1115731}}}}
    rows, columns = sh.rift_table(raw, None, shipped)
    field = dict(zip(rows, columns[0][1])) if columns else {}
    if not field.get("Out of"):
        out.append(f"the Great Rift list left `Out of` empty with a "
                   f"shipped top for the account's half: {field}.")
    rows, columns = sh.rift_table(dict(raw, detected_region="asia"), None,
                                  shipped)
    if columns and dict(zip(rows, columns[0][1])).get("Out of"):
        out.append("an Asia account's Great Rift list took a Global "
                   "top. The two servers rank different players.")

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
                 _documents, _shipped_file, _fold_script_finds_its_target,
                 _regions_agree, _readers):
        failures.extend(part(sf))
    return failures
