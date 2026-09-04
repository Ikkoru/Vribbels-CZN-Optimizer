"""The Materials tab prices two different things per level number.

A `Level 50:` under a class row is the cost of PROMOTING far enough to
unlock that ceiling, paid in Manuals or Certificates. A `Level 50:`
under the EXP row is the cost of the levelling itself, paid in Battle
Memory or Support Data. The two rows once shared one tuple of targets
and read the same percentage for both questions -- a wrong number under
a right label, which nothing but knowing the game would catch.

Three more silent ones live here:

* `_render_stats` prices a tier with `weights.get(tier, 1)`, so a tier
  word the weights do not name counts as ONE bottom-tier unit. The row
  still totals, just low.
* The two weight tables both name `Premium` and disagree about it -- 9
  in a promotion family, 20 in an EXP one. A row handed the wrong table
  totals off by a factor and reads like an ordinary figure.
* An EXP target is DERIVED from an exp table, so a level that table
  does not document costs None and its row reads `-` forever. That
  reads as "nobody has priced it" when it means "no such level".

No Tk: the tables and the column specs are all this needs.
"""

from ._harness import add_source_to_path

NAME = "materials targets"


def run():
    add_source_to_path()
    from game_data import CHARACTER_EXP_TABLE, PARTNER_EXP_TABLE
    from ui.tabs.materials_tab import (
        COLUMNS, EXP_PER_TIER, EXP_WEIGHTS, TIER_WEIGHTS,
    )

    failures = []

    # The hazard the fallback creates: every tier a row draws has to be
    # priced by the table that row is priced with.
    for spec in COLUMNS:
        for tier in spec.tiers:
            if tier not in TIER_WEIGHTS:
                failures.append(
                    f"the {spec.key} column draws a {tier!r} tier, which "
                    f"TIER_WEIGHTS does not price. It would count as one "
                    f"bottom-tier unit and the row would total low."
                )
        if spec.levelling:
            for tier in spec.levelling[3]:
                if tier not in EXP_WEIGHTS:
                    failures.append(
                        f"the {spec.key} column's EXP row draws a {tier!r} "
                        f"tier, which EXP_WEIGHTS does not price."
                    )

    # The two tables have to keep disagreeing, or handing a row the
    # wrong one stops being visible in any figure.
    shared = set(TIER_WEIGHTS) & set(EXP_WEIGHTS)
    if not shared:
        failures.append(
            "TIER_WEIGHTS and EXP_WEIGHTS no longer share a tier word, so "
            "nothing here can tell a row priced by the wrong one."
        )
    elif all(TIER_WEIGHTS[tier] == EXP_WEIGHTS[tier] for tier in shared):
        failures.append(
            f"TIER_WEIGHTS and EXP_WEIGHTS agree about {sorted(shared)}, so "
            f"a row handed the wrong table would total the same. They are "
            f"separate tables because the two families price alike-spelled "
            f"tiers differently."
        )

    # A promotion target and an EXP target for the same level are two
    # different questions and cannot be one number.
    tables = {"combatant": CHARACTER_EXP_TABLE, "partner": PARTNER_EXP_TABLE}
    for spec in COLUMNS:
        if not spec.levelling:
            continue
        promotion = dict(spec.targets)
        levelling = dict(spec.levelling[4])
        for label, cost in levelling.items():
            # `in` first: a label only one of the two carries reads as
            # a match through `.get`, both sides being None.
            if label in promotion and promotion[label] == cost:
                failures.append(
                    f"the {spec.key} column prices {label!r} at {cost} on "
                    f"both its promotion rows and its EXP row. Unlocking a "
                    f"ceiling and levelling to it are paid for with "
                    f"different items."
                )

        # A derived None means the level does not exist for this kind,
        # not that it is unpriced -- and the row cannot say which.
        documented = {level: exp for exp, level in tables[spec.key]}
        for label, cost in levelling.items():
            level = int(label.strip(":").split()[-1])
            if cost is None:
                failures.append(
                    f"the {spec.key} column's EXP row names {label!r}, which "
                    f"its exp table does not document -- the figure reads "
                    f"`-` forever and looks unpriced rather than absent."
                )
            elif cost * EXP_PER_TIER["Basic"] != documented.get(level):
                failures.append(
                    f"the {spec.key} column prices {label!r} at {cost} "
                    f"bottom-tier materials, which is not the "
                    f"{documented.get(level)} exp its table documents for "
                    f"level {level}."
                )

    failures.extend(_advanced_accumulates_per_item())
    return failures


def _advanced_accumulates_per_item():
    """The Advanced row's costs run DOWN a column and never across one.

    Two ways it draws a plausible wrong number:

    * a row states what that STEP alone costs, and what it reports is
      the running total from the top. Reporting the step alone makes a
      later row look cheaper than an earlier one, which reads as a
      target being easier rather than as a bug.
    * the three items do not substitute for each other, so a total
      taken across them would price a swap that cannot be made. Summed
      that way every column reads the same figure, which looks like
      three items costing alike.

    `None` is a step needing none of that item, adding nothing -- not
    an unpriced figure, which the tab has no way left to show here.
    """
    from ui.tabs.materials_tab import (
        ADVANCED_ITEMS, ADVANCED_TARGETS, advanced_costs,
    )

    out = []
    running = advanced_costs()
    if [label for label, _ in running] != [label for label, _ in
                                           ADVANCED_TARGETS]:
        out.append("advanced_costs() dropped or reordered a target row")
        return out

    for position, res_id in enumerate(ADVANCED_ITEMS):
        totals = [costs[position] for _label, costs in running]
        own = [costs[position] or 0 for _label, costs in ADVANCED_TARGETS]
        wanted = [sum(own[:n + 1]) for n in range(len(own))]
        if totals != wanted:
            out.append(
                f"item {res_id}'s column runs {totals}, where its own "
                f"steps {own} accumulate to {wanted}. A row reports what "
                f"reaching it costs, everything above it included."
            )
        if any(a > b for a, b in zip(totals, totals[1:])):
            out.append(
                f"item {res_id}'s column falls from one row to the next: "
                f"{totals}. A later target cannot cost less than an "
                f"earlier one it contains."
            )

    # Cross-contamination shows as columns that cannot be told apart.
    # The costs differ per item today, so identical columns mean one
    # item's total reached another's.
    columns = {tuple(costs[p] for _l, costs in running)
               for p in range(len(ADVANCED_ITEMS))}
    if len(columns) == 1 and len(ADVANCED_ITEMS) > 1:
        out.append(
            "every Advanced column reports the same totals. The three "
            "items are priced separately, so one figure across all of "
            "them means a total crossed between items."
        )
    return out
