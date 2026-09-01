# UI unionization — what the spacing work has left

Scratch file. Everything here either points at where a fact lives or
gives the command that re-derives it. The finished parts are not
recorded: `docs/ui_spacing.md` holds every rule, mechanism and caveat
the work produced, and the registry holds the numbers.

Read in order: `CLAUDE.md`, `docs/ui_spacing.md`.

## Where it stands

Every registered gap is on its target and confirmed against a hand
reading. Nothing is provisional and nothing is unruled.

| Fact                                                | Command                                                                                                                                                                             |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rules, constants and markers agree; all checks pass | `python checks/run_all.py`                                                                                                                                                          |
| How many gaps are registered, and under which rule  | `cd Vribbels && python -c "import collections;from ui import spacing_audit as sa,spacing_registry;print(len(sa.REGISTRY));print(collections.Counter(g.rule for g in sa.REGISTRY))"` |
| How many markers there are                          | `grep -rc "# spacing:" Vribbels --include="*.py"`                                                                                                                                   |

`register_all()` runs at import: importing `spacing_registry` fills
`REGISTRY`; importing only `spacing_audit` leaves it empty, and calling
`register_all()` again doubles every entry.

**All-green is the state to protect.** Outside a batch in flight, a run
that is not all-green has found something, and the first question is
whether the RESOLVER or the UI is wrong — `TrackedGap.hand` exists to
answer exactly that, and has been right about it more often than the eye
has.

## Open questions, none blocking

- Combatants > Equipped MF, set description to the bottom edge. Should
  be 5 and is not, but the longest description may reach a fourth line
  one day.
- Whether to deal with the other `label row -> label row` at all.
- What to do with the HAL gap.

## Audit the app in its EMPTY states too

Every reading so far was taken with the maintainer's snapshot loaded and
a combatant selected. Two other states ship to users and neither has
ever been measured:

1. **No snapshot loaded.** Panels that size to their content are at
   their narrowest, lists are empty, the Character and Partner panels
   hold placeholder text, and the Equipped MF cells all read `Empty`.
   Several resolvers already refuse in this state and say so, which is
   the correct behaviour — but nothing has confirmed that the gaps that
   CAN still be read are on target.
2. **A fresh install.** Default settings, no presets assigned, no
   per-combatant configuration. Different again from (1): the panels
   have their shipped defaults rather than the maintainer's.

Expect rows to skip rather than fail, and read a skip as an answer. What
this is looking for is the opposite: a gap that MEASURES in one state
and is wrong there, because a panel sized to absent content puts its
inset somewhere else.

Run it against a COPY of the settings folder, never the live one.

## Open, needing the app

**Two games at once**, for the capture guards: two accounts on one
region should trip the account guard, two regions should trip the region
one. Both are believed impossible to reach in practice; the guards stay
as insurance.

## Last, after everything else

**Go through the `out of scope` markers and ponder.** Each was written
as a boundary rather than as a decision to revisit, and none has been
read since. Grep them
(`grep -rn "# spacing: out of scope" Vribbels --include="*.py"`), read
each with the panel it sits in, and ask whether the boundary is still
where it belongs — a dialog that grew into a real panel, or a tab left
out because nobody had measured it yet, is a different answer from one
that is genuinely not this work's business.

Deliberately the LAST item: the rules and their numbers have to have
stopped moving before "is this in scope" can be asked honestly.
