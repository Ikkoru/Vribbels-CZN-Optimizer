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
a combatant selected. Two other states ship to users, and
`zRUN Spacing Audit States.bat` runs both; neither has been read yet:

1. **`empty`: the maintainer's settings, nothing captured.** The
   Combatants list still lists the roster, because `Show missing
   characters` is on, so a combatant is selected and the detail pane
   holds the placeholders: `No character data available`, `No partner
   data`, cells reading `Empty`.
2. **`fresh`: a first launch.** The shipped defaults, nothing captured.
   Those defaults do assign presets and carry per-combatant settings,
   but none of it shows until a capture. `Show missing characters` is
   off, so the Combatants list is empty and the detail pane blank.

Measured headlessly, the panels that change size with nothing captured
are few, and the same in both: Exclude Combatant's MFs (its checkbox
block empty, so everything under it rises), Memory Fragments' Sets (no
counts) and the Stats & Gacha History standings. The Combatants detail
pane and the Sets list hold their loaded size.

Expect rows to skip rather than fail, and read a skip as an answer. What
this is looking for is the opposite: a gap that MEASURES in one state
and is wrong there, because a panel sized to absent content puts its
inset somewhere else.

Each state runs in a scratch copy rebuilt for the run, so the live
settings are only read: `Vribbels/audit_states.py`.

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
