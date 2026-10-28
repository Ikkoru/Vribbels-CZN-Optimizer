"""What is left of each combatant's counseling at the Epione Centre, and
which option to pick next.

A combatant broken down by a Chaos run is counseled before it fights
again. A counseling plays one of the combatant's three scenarios: two of
its four OPENERS are offered, and the one picked offers its two
FOLLOW-UPS. The two picked add up to the cure result. Every option pays
a reward the first time it is picked, each scenario's record pays once
it is first played, and all three records once more. `combatants` reads
how far each combatant has got; `advice` says which of the two offered
openers leaves the fewest WHIFFS to come -- counselings of this scenario
offering nothing new.

**The game client holds the options; the wire which were picked.**
`game_client.known_counseling` gives each scenario's twelve options, in
the game's words, with the stability each adds to the cure. The login's
`counseling_archive` (inside the snapshot's `characters`) has a
combatant's records, each with the options picked in it: `true` once
the option's reward is claimed, `false` picked and not yet claimed.
`docs/epione.md` has the rest, the whiff count's arithmetic among it.

No Tk and no managers: this takes the snapshot dict and returns data.
"""

from collections import namedtuple
from functools import lru_cache
from itertools import combinations

# Where the snapshot keeps the records: inside the login's roster
# payload, beside the roster.
ARCHIVE_FIELD = "counseling_archive"
ROSTER_FIELD = "characters"

# **Which openers the game offers together.** The client files two
# openers of each scenario under the left button and two under the right
# (`SCORE_CHOICE_L` / `_R`), so a counseling is taken to offer one of
# each: four pairs, each as likely. `ANY_TWO` is any two of the four, six
# pairs. Nothing on the wire says which: the game deals them, and tells
# the server only what was picked. Whether a pair from one side has ever
# been offered is the maintainer's to watch for (`docs/epione.md`).
ONE_PER_SIDE = "one per side"
ANY_TWO = "any two"
PAIRING = ONE_PER_SIDE

# `picked`: on the wire, claimed or not; `claimed`: its reward taken.
# `result`: a follow-up's cure result with its opener, None for an
# opener. `reward`: (item, count).
Option = namedtuple("Option", "number wire side label words stability "
                              "picked claimed result reward")
# `left`: the follow-ups not yet picked, which is what a whiff counts.
Opener = namedtuple("Opener", "option follow_ups left")
# `played`: the scenario's record is unlocked, which its first counseling
# does; `claimed`: the record's own reward taken.
Scenario = namedtuple("Scenario", "id title line openers done total "
                                  "played claimed reward")
# `awaiting`: broken down, so counseled before it fights again.
# `unclaimed`: rewards earned and not taken, by item; `left`: rewards
# not yet earned, by item.
Combatant = namedtuple("Combatant", "res_id name scenarios done total "
                                    "awaiting unclaimed left tiers")
# `whiffs`: {opener number: the whiffs to come in this scenario if it is
# picked now}, None for an opener with nothing left. `opener` and
# `follow_up` are the numbers to pick; `whiff` says nothing offered is
# new, and the pick is then the best cure.
Advice = namedtuple("Advice", "whiffs opener follow_up whiff")


def combatants(raw, owned, counseling=None):
    """[Combatant] for each owned combatant the client gives counseling,
    by name. `owned` is {name: res_id}; `counseling` is
    `game_client.known_counseling()`, read off the client where not
    given."""
    if counseling is None:
        import game_client
        counseling = game_client.known_counseling()
    roster = (raw or {}).get(ROSTER_FIELD)
    roster = roster if isinstance(roster, dict) else {}
    records = {}
    for entry in roster.get(ARCHIVE_FIELD) or ():
        if isinstance(entry, dict) and str(entry.get("res_id")).isdigit():
            records[int(entry["res_id"])] = entry
    broken = {int(row["res_id"]) for row in roster.get("characters") or ()
              if isinstance(row, dict) and "id" not in row
              and row.get("psychosis_id")
              and str(row.get("res_id")).isdigit()}
    out = []
    for name, res_id in sorted(owned.items(), key=lambda pair: pair[0]):
        held = counseling.get(res_id)
        if not held:
            continue
        out.append(_combatant(res_id, name, held, records.get(res_id) or {},
                              res_id in broken))
    return out


def _combatant(res_id, name, held, record, awaiting):
    picked = {}
    for listed in record.get("counseling_choice_list") or ():
        choices = listed.get("counseling_story_choice_list") \
            if isinstance(listed, dict) else None
        if isinstance(choices, dict):
            picked.update(choices)
    played = {listed.get("counseling_id"): bool(listed.get("reward_get"))
              for listed in record.get("counseling_list") or ()
              if isinstance(listed, dict)}
    unclaimed, left = {}, {}

    def add(table, reward):
        item, count = reward
        if item is not None and count:
            table[item] = table.get(item, 0) + count

    scenarios = []
    for scenario in held["scenarios"]:
        options = {}
        for number, opener, side, label, words, stability, item, count \
                in scenario["choices"]:
            wire = "%s_%d" % (scenario["story"], number)
            options[number] = (opener, Option(
                number, wire, side, label, words, stability,
                wire in picked, picked.get(wire) is True, None,
                (item, count)))
        openers = []
        for number, (parent, option) in sorted(options.items()):
            if parent:
                continue
            follow_ups = tuple(
                kid._replace(result=option.stability + kid.stability)
                for parent_of, kid in (options[n] for n in sorted(options))
                if parent_of == number)
            openers.append(Opener(option, follow_ups,
                                  sum(not kid.picked for kid in follow_ups)))
        every = [o.option for o in openers] + [
            kid for o in openers for kid in o.follow_ups]
        for option in every:
            add(unclaimed if option.picked and not option.claimed
                else left if not option.picked else {}, option.reward)
        is_played = scenario["id"] in played
        add(unclaimed if is_played and not played[scenario["id"]]
            else left if not is_played else {}, tuple(scenario["reward"]))
        scenarios.append(Scenario(
            scenario["id"], scenario["title"], scenario["line"],
            tuple(openers), sum(o.picked for o in every), len(every),
            is_played, played.get(scenario["id"], False),
            tuple(scenario["reward"])))
    every_played = all(s.played for s in scenarios)
    every_claimed = every_played and all(s.claimed for s in scenarios)
    add(unclaimed if every_claimed and not record.get("all_reward_get")
        else left if not record.get("all_reward_get") else {},
        tuple(held["set"]))
    return Combatant(res_id, name, tuple(scenarios),
                     sum(s.done for s in scenarios),
                     sum(s.total for s in scenarios), awaiting, unclaimed,
                     left, tuple(tuple(t) for t in held.get("tiers") or ()))


def tier(result, tiers):
    """The index in `tiers` of the band `result` falls in, best first;
    None for none."""
    for index, (low, high, _affinity) in enumerate(tiers):
        if low <= result <= high:
            return index
    return None


# ----------------------------------------------------------- the whiffs

def pairs(sides, pairing=PAIRING):
    """[(i, j)]: the openers' indices each counseling may offer together,
    every pair as likely. `sides` is each opener's side, `L` or `R`."""
    indices = range(len(sides))
    if pairing == ANY_TWO:
        return list(combinations(indices, 2))
    return [(i, j) for i in indices for j in indices
            if sides[i] == "L" and sides[j] == "R"]


@lru_cache(maxsize=None)
def whiffs_to_come(left, offers):
    """How many counselings of a scenario are expected to offer nothing
    new before every option in it is picked, picking well every time.

    `left` is each opener's follow-ups not yet picked, (2, 1, 0, 2);
    `offers` the pairs it may offer (`pairs`). A counseling offering an
    opener with any left picks one of them and leaves the next state; one
    offering only openers with none left is a whiff and leaves the state
    as it was. So, with `w` the chance of a whiff:

        E(left) = (w + sum over the other pairs of
                   chance * min(E(left after picking either))) / (1 - w)

    and E is 0 once nothing is left. A follow-up's own choice moves
    nothing here: either takes one off its opener."""
    if not any(left):
        return 0.0
    share = 1 / len(offers)
    dead = sum(share for i, j in offers if not left[i] and not left[j])
    if dead >= 1:
        return float("inf")
    total = dead
    for pair in offers:
        after = [whiffs_to_come(_less(left, k), offers)
                 for k in pair if left[k]]
        if after:
            total += share * min(after)
    return total / (1 - dead)


def _less(left, index):
    return left[:index] + (left[index] - 1,) + left[index + 1:]


def advice(scenario, offered, pairing=PAIRING):
    """An `Advice` for the two openers `offered` (their numbers) in
    `scenario`.

    The opener whose pick leaves the fewest whiffs to come; between two
    leaving as many, the one whose best follow-up not yet picked cures
    the most, then the one not yet picked itself (a reward more). Then
    its follow-up not yet picked that cures the most. Where nothing
    offered is new, the pair that cures the most."""
    openers = {o.option.number: o for o in scenario.openers}
    order = [o.option.number for o in scenario.openers]
    left = tuple(openers[n].left for n in order)
    offers = tuple(pairs([openers[n].option.side for n in order], pairing))
    whiffs = {}
    for number in offered:
        index = order.index(number)
        whiffs[number] = (whiffs_to_come(_less(left, index), offers)
                          if left[index] else None)
    open_ = [n for n in offered if whiffs[n] is not None]
    if not open_:
        best = max(((n, kid) for n in offered
                    for kid in openers[n].follow_ups),
                   key=lambda pick: pick[1].result)
        return Advice(whiffs, best[0], best[1].number, True)

    def best_new(number):
        return max(kid.result for kid in openers[number].follow_ups
                   if not kid.picked)

    opener = min(open_, key=lambda n: (round(whiffs[n], 9), -best_new(n),
                                        openers[n].option.picked, n))
    follow_up = max((kid for kid in openers[opener].follow_ups
                     if not kid.picked), key=lambda kid: kid.result)
    return Advice(whiffs, opener, follow_up.number, False)
