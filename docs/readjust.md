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
- **Build Score**: the Optimizer's score (`core.compute_score_components`, blended as the preset derivation blends it), as the per cent it rises over the combatant's **Top build**: the Optimizer's best under the settings the Optimizer tab would run with (`optimizer/run_settings.saved_run_settings`: the combatant's own settings, the global filters, Exclude Combatant's MFs). It answers whether a readjustment could make the fragment part of a better build than the best there is, so a fragment that is fine but never good enough gains nothing.

**The Gear Score cut** (`gear_cut`, beside each Top build): the build score reads only the fragments whose Gear Score at their very best (`top_gs`: their starting values, every upgrade a top roll on their best substat) reaches the top `CUT_SHARE` (a third) of their slot's candidates as they stand, under the combatant's preset, and that the run's filters let in. One that cannot reach the top third even at its best is not worth a rare Quartz, and its two Optimizer runs are saved. It never cuts a fragment of the Top build.

How `read_build` reads one fragment:

1. **Its build**: the Optimizer's best build with the fragment pinned in its slot (`optimize(pinned=...)`). The pin is held to the run's filters, so a fragment the run could never use (an off-element Slot V, a main stat the settings rule out, an excluded combatant's) has no build and is left out of the list.
2. **A second build**, for a much better roll: the fragment pinned at the outcome a plain readjustment beats only `HIGH_SHARE` of the time. A big roll can make other fragments the better company, as when crit passes its cap.
3. **Sampling**: `BUILD_SAMPLES` readjustments per option, every exclusion included, each scored on the real score in whichever of the two builds does more with it.

Before (**Now**) is the fragment as it stands in its own build. What after has to beat is that or the Top build, whichever is higher. Now above 0 is a fragment that already beats the Top build unreadjusted: the Optimizer keeps only the top `TOP_PERCENT` of each slot by Gear Score before it searches (`run_settings.TOP_PERCENT`, with a 10-fragment floor), and the pin is exempt from that cut.

The score is not linear: crit is capped and multiplies, and set changes move it. That is why the build score samples where the Gear Score counts out.

## What a row says

- **Avg**: the average of Now after a plain readjustment, the outcomes worse than Now included, as if After were always kept. Now below Avg is a fragment that rolled below its own average, which is where most of a large Reroll gain comes from.
- **Reroll**: a plain readjustment's expected gain, and its chance of any gain.
- **Exclude**: the substat whose exclusion gains most, and that gain and chance.
- **Best**: the most either can gain, every upgrade a top roll on one substat.
- **Use**: the option with the higher gain per Quartz, and **Per Quartz** that gain.
- With several combatants, **For** names the one the fragment does most for (gain per Quartz times weight), and **Weighted** is that product, which the list is ranked by.

Per Quartz is greedy: it compares one Quartz's worth. An exclusion can beat two plain readjustments and still lose to one per Quartz, since a second plain readjustment adds less than the first.

The **Slots**, **Sets** and **MFs** filters only narrow what is drawn, from answers already worked out. The Quartz count is red at 0, orange at 1, yellow at 2 and green above. With several combatants, **Set weight** over the Weights list sets the weight of every combatant picked in it (Shift and Ctrl pick several), and shows the one last clicked.

## Where the work runs

**The work is the app's**, `readjust_work.ReadjustWork`, made at startup, so it can run before the tab is first opened; the tab draws what it has. It plans from the settings the tab's controls save (`readjust_measure`, `readjust_mode`, `readjust_combatant`, `readjust_weights`), and works out every combatant, in this order: with one combatant chosen, that one, then the weighted ones by weight, heaviest first, then everyone else; with several weighted, the weighted by weight, then everyone else. The list draws as soon as the combatants it shows are worked out, while the work goes on past them. Only `AHEAD` jobs per worker wait at a time, so a new choice is taken up within a job or two.

**Two speeds.** With **Work in the background** on (`readjust_background`, the default), the work starts as soon as a capture loads, in one worker at Windows' idle priority, which only gets the time nothing else wants: the game and the window are not slowed. **Full speed** moves it to every core but one at normal priority until everything is worked out, then back to the background. With the switch off, it runs only while the tab shows, only for the combatants it shows, at full speed. A spacing audit's run starts no worker.

**The progress**, under the counts: Loading... with the speed, or Done; then For one (with one combatant chosen), For weighted and For all, each as how many of its combatants' readings are in out of how many, or Complete. A reading counts once worked out or left unread (cut, or no build can wear it).

**Saved between launches**: the answers go to `cache/readjust_answers.pickle` in the data folder (`CACHE_NAME`, a folder with a `CACHEDIR.TAG`, kept out of git), at most `SAVE_EVERY` seconds after they come in and when the window closes, and are read back at startup when `CACHE_VERSION` matches. Change it whenever an answer would be worked out differently.

The jobs run in worker processes (`readjust.submit`), never on a thread: Python arithmetic on a thread takes the interpreter lock in turns with Tk's event loop, and the window answers only between turns. A job is one combatant, one measure and a chunk of fragments, and carries what a fresh process lacks: `STATS` with the game client's rolls laid over it, and for the build score the Optimizer itself (`lean_optimizer`: without the capture's raw data, enumerating in the worker's own process) and the combatant's run settings. The build score asks for each combatant's Top build first (a job of kind `top`), then its fragments `BUILD_CHUNK` at a time; each is two Optimizer runs, each about a tenth of a full run since one slot holds one fragment, and its sampling.

The work keeps every answer by what it was worked out from: the fragment's own rolls (`readjust.content`: its id, slot, set, level, main stat, and each substat's starting value and upgrades), and the signature of what it is read against: the roll grids, and the preset's weights or, for the build score, everything the combatant's builds are made of (`build_signature`: the run settings, the combatant's stats at the Optimizer's level, the fragments a run searches, each slot's after the Top % cut, and whose each readjustable fragment is, which decides whether it may be pinned). Equal inputs give an equal answer whichever capture they came from, so a new capture works out again only what it changed:

- a fragment readjusted, or newly at its top level: that fragment alone, under the Gear Score;
- a fragment a combatant's runs search changed, gained or lost (one the per-slot cut leaves out changes nothing), a readjustable fragment moved to another combatant, or the combatant's level or settings changed: everything for that combatant, under the build score;
- a preset's weights changed, or another preset assigned: every fragment for the combatants it scores, under the Gear Score, and under the build score where the preset orders the Optimizer's per-slot cut;
- a client update that changes the roll grids: everything.

A deleted fragment's answers, and a readjusted one's old ones, are dropped when the capture loads (`_forget`); a Top build is kept by its signature alone. Past `KEEP_ANSWERS` the oldest are dropped. Switching back to a measure or a combatant already worked out draws at once.

## Settings

`readjust_measure`, `readjust_mode`, `readjust_combatant`, `readjust_weights` ({name: weight}), `readjust_owner` and `readjust_background` in `settings.json`, under the Substat Readjustment heading of `SettingsManager.LAYOUT`. The Slots and Sets ticks are not kept, as on the Memory Fragments tab.
