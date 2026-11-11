# Substat Readjustment

The Substat Readjustment tab ranks every fully upgraded Legendary Memory Fragment by what readjusting it is expected to gain per Shuffling Quartz (item 3210004). The model is `Vribbels/readjust.py`, the tab `Vribbels/ui/tabs/readjust_tab.py`, and `checks/check_readjust.py` holds both.

## What the game does

From the client's `ui_piece_readjust_desc_*` texts:

- A readjustment keeps every substat's type, and the value it started at. The fragment's upgrades are dealt out again, each to one of its substats with a fresh roll.
- One substat may be excluded first. It takes no upgrade and goes back to its starting value.
- It costs 1 Shuffling Quartz, or 2 with an exclusion.
- The game shows Before and After, and the player keeps either one.

So **a readjustment never loses anything**: its worth is the expected `max(0, after - before)`.

A fragment's `stat_list` keeps each substat's starting value (type 1, or type 2 for the substat added at level 1) apart from its upgrades (type 3); `MemoryFragment.from_json` reads them into `base_value` and `upgrade_values`. Every fully upgraded Legendary has four substats and four upgrades.

**Two parts of this are assumed, not yet seen on the wire**: each upgrade picks its substat with equal chance and its roll anywhere on the stat's grid with equal chance, as the Potential's model assumes; and the starting values survive. A capture of one readjustment would confirm both, and the readjustment command's reply has not been read yet.

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

## Settings

`readjust_measure`, `readjust_mode`, `readjust_combatant`, `readjust_weights` ({name: weight}), `readjust_owner` and `readjust_slot` in `settings.json`, under the Substat Readjustment heading of `SettingsManager.LAYOUT`.
