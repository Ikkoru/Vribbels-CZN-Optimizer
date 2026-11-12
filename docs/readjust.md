# Substat Readjustment

The Substat Readjustment tab, beside Memory Fragments, ranks every fully upgraded Legendary Memory Fragment by what readjusting it is expected to gain per Shuffling Quartz (item 3210004). The model is `Vribbels/readjust.py`, the tab `Vribbels/ui/tabs/readjust_tab.py`, and `checks/check_readjust.py` holds both.

## What the game does

From the game's *Memory Fragment Upgrade Probabilities* notice on STOVE, and the client's `ui_piece_readjust_desc_*` texts:

- A readjustment keeps every substat's type and the value it started at, and performs 4 upgrades again, whatever the fragment had. Each upgrade picks one of the substats with equal chance and rolls a value anywhere on that stat's Legendary grid with equal chance (`roll_values`, the client's rolls).
- One substat may be excluded first. It takes no upgrade and goes back to its starting value.
- It costs 1 Shuffling Quartz, or 2 with an exclusion.
- The game shows Before and After, and the player keeps either one.

So **a readjustment never loses anything**: its worth is the expected `max(0, after - before)`.

A fragment's `stat_list` keeps each substat's starting value (type 1, or type 2 for the substat added at level 1) apart from its upgrades (type 3); `MemoryFragment.from_json` reads the first into `base_value`.

The readjustment command's reply has not been captured yet, so the tab cannot yet show a readjustment's After beside its Before.

## The two measures

- **Gear Score**: the fragment's GS under the combatant's assigned preset, unclamped, in GS points. It is linear in the rolls, so `read` works out the exact distribution of four upgrades by convolution, at `BINS` bins across its span.
- **Build Score**: the Optimizer's score (`core.compute_score_components`, blended as the preset derivation blends it) of the combatant's equipped build with the fragment in its slot, as the per cent it rises over the build as worn. What after has to beat is the better of the build as worn and the build with the fragment as it stands. `read` uses the linear distribution, from what one max roll of each stat adds to the equipped build (`BuildValuer.worths`). `refine` then samples the real score, `REFINE_SAMPLES` readjustments each, for the top `REFINE_TOP` fragments, every exclusion included. The real score is not linear: crit is capped and multiplies, and set changes move it.

A build-score combatant's settings are their Optimizer settings, its level the one the Optimizer would use.

## What a row says

- **Reroll**: a plain readjustment's expected gain, and its chance of any gain.
- **Exclude**: the substat whose exclusion gains most, and that gain and chance.
- **Best**: the most either can gain, every upgrade a top roll on one substat.
- **Use**: the option with the higher gain per Quartz, and **Per Quartz** that gain.
- With several combatants, **For** names the one the fragment does most for (gain per Quartz times weight), and **Weighted** is that product, which the list is ranked by.

Per Quartz is greedy: it compares one Quartz's worth. An exclusion can beat two plain readjustments and still lose to one per Quartz, since a second plain readjustment adds less than the first.

The **Slots**, **Sets** and **MFs** filters only narrow what is drawn, from answers already worked out. The Quartz count is red at 0, orange at 1, yellow at 2 and green above. With several combatants, **Set weight** over the Weights list sets the weight of every combatant picked in it (Shift and Ctrl pick several), and shows the one last clicked.

## Where the work runs

In worker processes (`readjust.submit`), never on a thread: Python arithmetic on a thread takes the interpreter lock in turns with Tk's event loop, and the window answers only between turns. A job is one combatant, one measure and a chunk of fragments, and carries what a fresh process lacks: `STATS` with the game client's rolls laid over it, and the build score's inputs already resolved (`build_inputs`).

The tab keeps every answer by what it was worked out from: the fragment's own rolls (`readjust.content`: its id, slot, set, level, main stat, and each substat's starting value and upgrades), and the signature of what it is read against: the roll grids, and the preset's weights or, for the build score, the combatant's build as `build_inputs` resolves it (its stats at the Optimizer's level, its settings, the fragments it wears). Equal inputs give an equal answer whichever capture they came from, so a new capture works out again only what it changed:

- a fragment readjusted, or newly at its top level: that fragment alone;
- a combatant's gear, level or Optimizer settings changed: every fragment for that combatant, under the build score only;
- a preset's weights changed, or another preset assigned: every fragment for the combatants it scores, under the Gear Score;
- a client update that changes the roll grids: everything.

A deleted fragment's answers, and a readjusted one's old ones, are dropped when the capture loads (`_forget`); past `KEEP_ANSWERS`, all but those of the signatures on show. The build score's top `REFINE_TOP` are worked out again as their membership changes. Switching back to a measure or a combatant already worked out draws at once, and a change of mind drops the jobs not started yet whose answers nothing on show waits on. While anything is still being worked out the list shows `Loading...`. A tab that is not showing starts no worker; showing it (`<Map>`) catches up.

## Settings

`readjust_measure`, `readjust_mode`, `readjust_combatant`, `readjust_weights` ({name: weight}) and `readjust_owner` in `settings.json`, under the Substat Readjustment heading of `SettingsManager.LAYOUT`. The Slots and Sets ticks are not kept, as on the Memory Fragments tab.
