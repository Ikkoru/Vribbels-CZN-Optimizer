# v2.0.0

> **The Checklist tab and the UI changes are still incomplete.** They ship because what is there works, not because they are finished. Expect both to keep changing.

A big one. The version jump is overdue — this fork has drifted a long way from where it started.

## New

**Checklist tab.** Four columns — Daily, Weekly, Monthly, Other — listing everything that resets and what you have left to do. Green is done, red is not, a dash means the capture has not seen it yet. Each heading counts its own period down. Shop rows come from the game, so new products turn up on their own, and you can untick the ones you never buy.

**Materials tab.** Counts your upgrade material against what promoting and levelling actually costs — per class, per Element, and per level target.

**Combatants tab: missing characters.** A checkbox lists every combatant in the game you have not obtained, alongside the ones you have.

## Changed

**Agony damage now crits.** The game changed and the optimizer follows, so crit gear is worth more to Agony combatants than it was — their results will re-rank.

**Your region is detected, not chosen.** The dropdown is gone; a capture works out which server your game uses.

**The Combatants tab is faster to move through**, and it keeps the combatant you are looking at.

**Typing more than one letter narrows any list**, the way Windows Explorer does.

## Fixed

- The built program starts on Python 3.14 again.
- Snapshots are never read half-written.
- A capture that records nothing says so, instead of reporting the previous one.
- The app reloads on every save, not just the first.
- Gear Score weights hold what you type.
- Nothing flashes light grey when a tab first opens.
- Escape closes every window the app opens.

Full detail in [CHANGELOG.md](CHANGELOG.md).
