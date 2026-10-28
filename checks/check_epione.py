"""The Epione tab reads each combatant's counseling right, end to end.

Four parts, each wrong without a sound:

* **The client reader** (`game_client.counseling`). An opener taken for
  a follow-up, a stability read off the story line where the choice
  table states another, or an older story table read in place of the
  newest, and every option, cure result and whiff count on the tab is
  someone else's.
* **The capture** (`Addon._note_counseling`). The login sends every
  combatant's records and who is broken down; after it, only a Chaos
  run's close and the counseling's own replies say what moved. One not
  folded in leaves the tab on the login's picks all session, a combatant
  counseled still red, or a breakdown never shown.
* **The model** (`epione.combatants`). Picked counts claimed or not; a
  reward waiting is one picked and not claimed; a record is played once
  listed. A count off by those reads a combatant done who is not.
* **The whiff count** (`epione.whiffs_to_come`, `epione.advice`). Held to
  a value iteration over every state, written apart from it: a wrong
  chance of a dead pair, or a wrong pick between two, sends the player
  the wrong way at every counseling.

No Tk, no snapshot and no client needed: the cases are synthetic.
"""

import json
import tempfile
from itertools import product
from pathlib import Path

from ._harness import add_source_to_path

NAME = "Epione counseling"

ID = "1003"
STORY = "counseling_1003_01"


# ----------------------------------------------------------- the reader

class _FakeClient:
    """Just enough of `game_client.Client` for `counseling`."""

    def __init__(self, tables, text):
        self.archive = type("A", (), {"files": {
            f"db/{name}.db": None for name in tables}})()
        self._tables, self._text = tables, text

    def rows(self, name):
        return self._tables[name]

    def text(self):
        return self._text


def _line(number, parent, side, opt, words, wire=True):
    return {"text_type": "SCORE_CHOICE_" + side, "choice": str(number),
            "use_choice": str(parent) if parent else "", "opt": str(opt),
            "text_en": words,
            "link_story_choice_id": f"{STORY}_{number}" if wire else ""}


# Openers 1-4, follow-ups 5-12 two an opener; every line naming its
# wire id but one, as the newer combatants' lines do not.
STORY_LINES = [
    {"text_type": "EMPTY"},
    {"text_type": "CAPTION", "text_en": "Nia is <b>drowning</b>."},
    {"text_type": "CAPTION", "text_en": "Not the opening line."},
    _line(1, 0, "L", 50, "Empathize<br>Sing Nia's song."),
    _line(2, 0, "L", 45, "Suggest<br>Ask for an autograph."),
    _line(3, 0, "R", 45, "Empathize<br>Play Nia's song.", wire=False),
    _line(4, 0, "R", 35, "Stimulate<br>Ask about the song."),
] + [_line(n, (n - 3) // 2, "L" if n % 2 else "R", 40, f"F{n}<br>Words {n}.")
     for n in range(5, 13)]

CLIENT_TABLES = {
    "counseling_archive@counseling_archive": [
        {"id": "1003_1", "link_story_id": STORY,
         "title": "counseling_archive_1003_title_1",
         "reward_link_item_id": "2000004", "reward_item_count": "50"},
        {"id": "1003_2", "link_story_id": "counseling_1003_02",
         "title": "counseling_archive_1003_title_2",
         "reward_link_item_id": "2000004", "reward_item_count": "50"}],
    "counseling_archive_set@counseling_archive_set": [
        {"link_char_base_id": ID, "link_counseling_archive_id":
         "[1003_1,1003_2]", "reward_link_item_id": "2000004",
         "reward_item_count": "150"}],
    "counseling_story_choice@counseling_story_choice": [
        {"id": f"{STORY}_{n}", "counseling_stability":
         "48" if n == 1 else STORY_LINES[n + 2]["opt"]}
        for n in range(1, 13)],
    "counseling_archive_contents@counseling_archive_contents": [
        {"id": f"1003_01_{n}", "reward_link_item_id": "2000004",
         "reward_item_count": "5"} for n in range(1, 13)],
    "story_content_counseling@story_component_counseling": [
        {"id": "story_compo_1003_start_1", "stability_min": "0",
         "stability_max": "0"},
        {"id": "story_compo_1003_end_1", "stability_min": "70",
         "stability_max": "79"},
        {"id": "story_compo_1003_end_3", "stability_min": "90",
         "stability_max": "110"}],
    "counseling_result@counseling_result": [
        {"id": "1003_1", "link_char_base_id": ID, "stability_point": "70",
         "reward_friendship": "5"},
        {"id": "1003_3", "link_char_base_id": ID, "stability_point": "90",
         "reward_friendship": "15"}],
    # The newest by its date is read; the second scenario's story has an
    # option under a follow-up there, a shape the whiff count does not
    # cover, and so is left out.
    "story_counseling_261021@story": [
        {"id": STORY, "info": json.dumps(STORY_LINES)},
        {"id": "counseling_1003_02", "info": json.dumps(
            STORY_LINES + [_line(13, 5, "L", 40, "Deeper<br>Words.")])}],
    "story_counseling_250101@story": [
        {"id": STORY, "info": json.dumps(STORY_LINES[:3])}],
}
CLIENT_TEXT = {"counseling_archive_1003_title_1": "Forget Me Not"}


def _reader_failures():
    import game_client
    out = []
    read = game_client.counseling(_FakeClient(CLIENT_TABLES, CLIENT_TEXT))
    held = read.get(int(ID))
    if held is None:
        return [f"the reader gave no counseling for {ID} ({read}): no "
                f"scenario of the right shape, as when the older dated story "
                f"table is read in place of the newest"]
    scenarios = held["scenarios"]
    if [s["id"] for s in scenarios] != ["1003_1"]:
        out.append(f"the reader kept scenarios {[s['id'] for s in scenarios]}, "
                   f"not 1003_1 alone: a story an option short, or the "
                   f"older dated story table read in place of the newest, "
                   f"puts a scenario of the wrong shape on the tab")
        return out
    first = scenarios[0]
    choices = {c[0]: c for c in first["choices"]}
    if choices.get(1, [None] * 6)[5] != 48:
        out.append(f"opener 1's stability read as {choices.get(1)}: the "
                   f"choice table's 48 goes over the story line's 50, and "
                   f"every cure result through it is off by the "
                   f"difference")
    if (choices.get(3) or [None] * 5)[3:5] != ["Empathize", "Play Nia's song."]:
        out.append(f"opener 3 reads {choices.get(3)}: its label and words "
                   f"are split at the <br>, and a line with no wire id of "
                   f"its own is still an option")
    if (choices.get(7) or [None] * 3)[1:3] != [2, "L"] \
            or (choices.get(4) or [None] * 3)[1:3] != [0, "R"]:
        out.append(f"options 7 and 4 read {choices.get(7)} and "
                   f"{choices.get(4)}: a follow-up names its opener, an "
                   f"opener none, each on its side")
    if first["line"] != "Nia is drowning.":
        out.append(f"the opening line reads {first['line']!r}: the "
                   f"scenario's first caption, its markup out")
    if first["title"] != "Forget Me Not" or first["reward"] != [2000004, 50]:
        out.append(f"the record reads {first['title']!r} {first['reward']}")
    if held["tiers"] != [[90, 110, 15], [70, 79, 5]]:
        out.append(f"the cure tiers read {held['tiers']}: each result's "
                   f"stability point inside an end component's range, "
                   f"best first")
    if held["set"] != [2000004, 150]:
        out.append(f"the set reward reads {held['set']}")
    return out


# ---------------------------------------------------------- the capture

class _Message:
    def __init__(self, payload, from_client=False):
        self.from_client = from_client
        self.is_text = True
        self.text = json.dumps(payload)
        self.content = self.text.encode()


class _Flow:
    def __init__(self, payload, from_client=False):
        self.websocket = type(
            "W", (), {"messages": [_Message(payload, from_client)]})()


def _addon():
    import capture.manager as manager
    from .check_capture_history import addon_tables
    namespace = {}
    exec(compile(manager.ADDON_TEMPLATE, "<ADDON_TEMPLATE>", "exec"),
         namespace)
    namespace.update(addon_tables())
    return namespace["Addon"](Path(tempfile.mkdtemp()),
                              log_callback=lambda *a, **k: None)


def _entry(res_id, picks):
    return {"res_id": res_id,
            "counseling_list": [{"counseling_id": f"{res_id}_1",
                                 "reward_get": True}],
            "counseling_choice_list": [{"counseling_id": f"{res_id}_1",
                                        "counseling_story_choice_list":
                                        picks}],
            "all_reward_get": False}


def _row(addon, res_id):
    return next((row for row in addon.character_data["characters"]
                 if row.get("res_id") == res_id and "id" not in row), None)


def _capture_failures():
    out = []
    addon = _addon()
    addon.inventory_data = {"piece_items": []}
    addon.character_data = {
        "characters": [
            # A partner card sharing the res_id, ahead of the combatant:
            # never patched.
            {"res_id": 1003, "id": 9, "lock": False},
            {"res_id": 1003, "exp": 1, "potential_node_ids": "[]",
             "friendship_exp": 100, "psychosis_id": None,
             "psychosis_recover_price_id": None}],
        "counseling_archive": [_entry(1003, {f"{STORY}_1": True})]}
    qid = [100]

    def ask(command, params, reply):
        qid[0] += 1
        cmd, _, inner = command.partition("/")
        addon.websocket_message(_Flow(
            [{"cmd": cmd, "qid": qid[0], "params": dict(params, cmd=inner)}],
            from_client=True))
        addon.websocket_message(_Flow([dict(reply, res="ok", qid=qid[0])]))

    # A Chaos run's close: 1003 broken down.
    ask("stage/clear_stage", {}, {
        "changed_counseling_archive_array": [
            _entry(1003, {f"{STORY}_1": True, f"{STORY}_5": True})],
        "psychosis_chars": [{"res_id": 1003, "psychosis_id": "psychosis_1",
                             "psychosis_recover_price_id": 61}]})
    if (_row(addon, 1003) or {}).get("psychosis_id") != "psychosis_1":
        out.append("a run's psychosis_chars did not reach the roster: a "
                   "combatant broken down is not shown awaiting counseling "
                   "until the next login")
    picks = addon.character_data["counseling_archive"][0][
        "counseling_choice_list"][0]["counseling_story_choice_list"]
    if f"{STORY}_5" not in picks:
        out.append("a run's changed_counseling_archive_array did not "
                   "replace its combatant's records")
    # The counseling, then its claim.
    ask("mentalclinic/recover_char_counseling", {"char_res_id": 1003}, {
        "counseling_archive": _entry(1003, {f"{STORY}_1": True,
                                            f"{STORY}_5": True,
                                            f"{STORY}_2": False,
                                            f"{STORY}_7": False}),
        "friendship_exp": 115})
    row = _row(addon, 1003) or {}
    if row.get("psychosis_id") or row.get("psychosis_recover_price_id"):
        out.append("a counseling's reply left the breakdown on the roster: "
                   "the combatant stays red after it is cured")
    if row.get("friendship_exp") != 115:
        out.append(f"a counseling's friendship_exp did not reach the roster "
                   f"(it reads {row.get('friendship_exp')})")
    partner = next(r for r in addon.character_data["characters"] if "id" in r)
    if set(partner) != {"res_id", "id", "lock"}:
        out.append("a counseling patched a partner card's row sharing the "
                   "combatant's res_id")
    picks = addon.character_data["counseling_archive"][0][
        "counseling_choice_list"][0]["counseling_story_choice_list"]
    if picks.get(f"{STORY}_7") is not False:
        out.append("a counseling's counseling_archive did not replace its "
                   "combatant's records: the options just picked read new")
    ask("mentalclinic/get_counseling_reward", {"char_res_id": 30115}, {
        "counseling_archive": _entry(30115, {"counseling_30115_01_1": True})})
    if [e["res_id"] for e in addon.character_data["counseling_archive"]] \
            != [1003, 30115]:
        out.append("a combatant's first record was not added to the list")
    addon._save_data()
    saved = json.loads(Path(addon.saved_path).read_text(encoding="utf-8"))
    if len(saved["characters"].get("counseling_archive") or ()) != 2:
        out.append("the snapshot does not carry the folded records")
    return out


# ------------------------------------------------------------ the model

def _held(stabilities=None):
    """One combatant's counseling, two scenarios, in the reader's shape:
    every follow-up adds 40 to its opener's stability, follow-up 5 adds
    60 (a cure past 100)."""
    def scenario(n):
        choices = []
        for number in range(1, 13):
            parent = 0 if number <= 4 else (number - 3) // 2
            side = ("L" if number <= 2 else "R") if not parent \
                else ("L" if number % 2 else "R")
            stability = (stabilities or {}).get(number, 60 if number == 5
                                                else 40 if parent else 45)
            choices.append([number, parent, side, f"label{number}",
                            f"words{number}", stability, 2000004, 5])
        return {"id": f"{ID}_{n}", "story": f"counseling_{ID}_0{n}",
                "title": f"Scenario {n}", "line": "", "reward": [2000004, 50],
                "choices": choices}
    return {"scenarios": [scenario(1), scenario(2)],
            "tiers": [[90, 110, 15], [0, 89, 1]], "set": [2000004, 150]}


def _model_failures():
    import epione
    out = []
    first = f"counseling_{ID}_01"
    raw = {"characters": {
        "characters": [{"res_id": 1003, "psychosis_id": "p"},
                       {"res_id": 1003, "id": 1, "psychosis_id": "p"}],
        "counseling_archive": [{
            "res_id": 1003,
            "counseling_list": [{"counseling_id": f"{ID}_1",
                                 "reward_get": False}],
            "counseling_choice_list": [{
                "counseling_id": f"{ID}_1", "counseling_story_choice_list": {
                    f"{first}_1": True, f"{first}_5": True,
                    f"{first}_3": False, f"{first}_9": False}}],
            "all_reward_get": False}]}}
    people = epione.combatants(raw, {"Nia": 1003, "Nobody": 1}, {1003: _held()})
    if [p.name for p in people] != ["Nia"]:
        return [f"combatants listed {[p.name for p in people]}: one the "
                f"client gives no counseling has nothing to list"]
    nia = people[0]
    if (nia.done, nia.total) != (4, 24):
        out.append(f"Nia counts {nia.done}/{nia.total}, not 4/24: an option "
                   f"picked counts whether or not its reward is claimed")
    if nia.unclaimed != {2000004: 60}:
        out.append(f"Nia's rewards waiting read {nia.unclaimed}, not 60 (two "
                   f"options picked unclaimed, and the record played "
                   f"unclaimed)")
    if nia.left != {2000004: 20 * 5 + 50 + 150}:
        out.append(f"Nia's rewards left read {nia.left}: twenty options, the "
                   f"unplayed record and the set")
    if not nia.awaiting:
        out.append("a combatant whose roster row carries a psychosis_id "
                   "does not read awaiting counseling")
    scenario = nia.scenarios[0]
    opener = scenario.openers[0]
    if [k.result for k in opener.follow_ups] != [105, 85] \
            or opener.left != 1:
        out.append(f"opener 1's follow-ups read results "
                   f"{[k.result for k in opener.follow_ups]} and "
                   f"{opener.left} left: a cure is the two stabilities "
                   f"added, and a picked follow-up is not left")
    if [o.left for o in scenario.openers] != [1, 2, 1, 2]:
        out.append(f"the openers' follow-ups left read "
                   f"{[o.left for o in scenario.openers]}")
    if epione.tier(105, nia.tiers) != 0 or epione.tier(85, nia.tiers) != 1:
        out.append("a cure result's tier is not the band it falls in")
    # A partner card's row breaking down says nothing of the combatant.
    raw["characters"]["characters"][0]["psychosis_id"] = None
    if epione.combatants(raw, {"Nia": 1003}, {1003: _held()})[0].awaiting:
        out.append("a partner card's psychosis_id reads its combatant as "
                   "awaiting counseling")
    return out


# --------------------------------------------------------- the whiffs

def _value_iteration(offers):
    """{left: whiffs to come} for every state, by iterating the
    expectation to a fixed point -- the same quantity `whiffs_to_come`
    solves in closed form, reached another way."""
    states = list(product(range(3), repeat=4))
    value = {state: 0.0 for state in states}
    # A dead pair is at most half the offers, so each round halves what
    # is left to converge at worst.
    for _ in range(300):
        new = {}
        for state in states:
            if not any(state):
                new[state] = 0.0
                continue
            total = 0.0
            for pair in offers:
                moves = [value[state[:k] + (state[k] - 1,) + state[k + 1:]]
                         for k in pair if state[k]]
                total += (min(moves) if moves else 1 + value[state]) \
                    / len(offers)
            new[state] = total
        value = new
    return value


def _whiff_failures():
    import epione
    out = []
    for pairing in (epione.ONE_PER_SIDE, epione.ANY_TWO):
        offers = tuple(epione.pairs("LLRR", pairing))
        if len(offers) != (4 if pairing == epione.ONE_PER_SIDE else 6):
            out.append(f"{pairing} offers {len(offers)} pairs")
            continue
        truth = _value_iteration(offers)
        wrong = [state for state, value in truth.items()
                 if abs(epione.whiffs_to_come(state, offers) - value) > 1e-6]
        if wrong:
            state = wrong[0]
            out.append(f"{pairing}: the whiffs to come at {state} read "
                       f"{epione.whiffs_to_come(state, offers):.4f} where "
                       f"iterating the expectation gives {truth[state]:.4f} "
                       f"({len(wrong)} states disagree)")
    # Advice, one per side: openers 1 and 2 on the left.
    stab = {n: 45 for n in range(1, 5)}
    stab.update({n: 40 for n in range(5, 13)})
    stab[10] = 50        # opener 3's second follow-up cures best
    held = _held(stab)
    first = f"counseling_{ID}_01"

    def advise(picked, offered):
        raw = {"characters": {"counseling_archive": [{
            "res_id": 1003, "counseling_choice_list": [{
                "counseling_id": f"{ID}_1", "counseling_story_choice_list":
                {f"{first}_{n}": True for n in picked}}]}]}}
        nia = epione.combatants(raw, {"Nia": 1003}, {1003: held})[0]
        return epione.advice(nia.scenarios[0], offered)

    # Left (1, 2, 2, 2): picking opener 1 strands the left side on one
    # opener; picking 3 keeps both sides two openers deep.
    got = advise((1, 5), (1, 3))
    if got.opener != 3 or got.whiff:
        out.append(f"with opener 1 a follow-up short and opener 3 untouched, "
                   f"offered both, the advice picks {got.opener}: the pick "
                   f"leaving fewer whiffs to come is 3")
    elif got.follow_up != 10:
        out.append(f"the advised follow-up is {got.follow_up}, not 10: of "
                   f"the follow-ups not yet picked, the one curing most")
    # Fresh: 1 and 2 leave as many whiffs; 3 is the right side's.
    got = advise((), (2, 3))
    if got.opener != 3:
        out.append(f"with two openers leaving as many whiffs, the advice "
                   f"picks {got.opener}, not the one whose best new "
                   f"follow-up cures more (3)")
    # Nothing new on either: the best cure.
    got = advise((1, 5, 6, 3, 9, 10), (1, 3))
    if not got.whiff or (got.opener, got.follow_up) != (3, 10):
        out.append(f"offered two openers with nothing left, the advice reads "
                   f"{got}: a whiff, picking the best cure")
    return out


def run():
    add_source_to_path()
    return (_reader_failures() + _capture_failures() + _model_failures()
            + _whiff_failures())


FAULTS = [
    ("the story line's stability over the table's", "game_client:_counseling_scenario",
     "held if isinstance(held, int) else _figure(row.get(\"opt\")) or 0",
     "_figure(row.get(\"opt\")) or 0", "opener 1's stability"),
    ("the oldest story table read", "game_client:counseling",
     "dated[-1][1]", "dated[0][1]", "no scenario of the right shape"),
    ("a short scenario kept", "game_client:_counseling_scenario",
     "or len(choices) != 12", "or False", "the reader kept scenarios"),
    ("the last caption read", "game_client:_counseling_scenario",
     "line = next((clean(row.get(\"text_en\")) for row in lines",
     "line = next((clean(row.get(\"text_en\")) for row in lines[::-1]",
     "the opening line"),
    ("a run's breakdowns ignored", "capture.manager:ADDON_TEMPLATE",
     '        broken = data.get("psychosis_chars")',
     "        broken = None", "psychosis_chars did not reach"),
    ("a run's changed records ignored", "capture.manager:ADDON_TEMPLATE",
     '        entries = data.get("changed_counseling_archive_array")',
     "        entries = None", "changed_counseling_archive_array did not"),
    ("a counseling not ending the breakdown", "capture.manager:ADDON_TEMPLATE",
     '            fields = {"psychosis_id": None, "psychosis_recover_price_id": None}',
     "            fields = {}", "left the breakdown"),
    ("a counseling never tracked", "capture.manager:ADDON_TEMPLATE",
     "                    self.pending_counselings[qid] = int(res_id)",
     "                    pass", "left the breakdown"),
    ("a partner card patched", "capture.manager:ADDON_TEMPLATE",
     '            if (isinstance(row, dict) and "id" not in row\n',
     "            if (isinstance(row, dict)\n", "partner card's row"),
    ("an unclaimed pick not counted", "epione:_combatant",
     "wire in picked, picked.get(wire) is True",
     "picked.get(wire) is True, picked.get(wire) is True",
     "Nia counts"),
    ("a record played counted as left", "epione:_combatant",
     "is_played = scenario[\"id\"] in played",
     "is_played = False", "rewards waiting read"),
    ("a partner's breakdown read", "epione:combatants",
     'if isinstance(row, dict) and "id" not in row\n',
     "if isinstance(row, dict)\n", "a partner card's psychosis_id"),
    ("a dead pair's chance halved", "epione:whiffs_to_come",
     "dead = sum(share for i, j in offers if not left[i] and not left[j])",
     "dead = sum(share / 2 for i, j in offers if not left[i] and not left[j])",
     "whiffs to come at"),
    ("the worse pick taken", "epione:advice",
     "opener = min(open_, key=lambda n: (round(whiffs[n], 9), -best_new(n),",
     "opener = max(open_, key=lambda n: (round(whiffs[n], 9), -best_new(n),",
     "the advice picks"),
    ("the tie broken the wrong way", "epione:advice",
     "-best_new(n),", "best_new(n),", "leaving as many whiffs"),
    ("a whiff's pick not the best cure", "epione:advice",
     "key=lambda pick: pick[1].result)", "key=lambda pick: -pick[1].result)",
     "nothing left, the advice"),
]
