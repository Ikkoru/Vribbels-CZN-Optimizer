# Gacha History

Read before touching `Vribbels/gacha_history.py`, `ui/tabs/gacha_history_tab.py`, or the addon's `_merge_gacha` in `capture/manager.py`.

**The game lists about half a year of pulls and then drops them for good.** A longer history exists only if someone read it while it was still listed, so everything here is built around keeping what was read and never losing it.

## What the wire sends

Nothing arrives by itself. The records are sent only when the player opens a banner's records in game, one page per request.

| Command | Reply | What it is |
| ------- | ----- | ---------- |
| `gacha/history {"id": <banner>, "last_db_id": <cursor>}` | `gacha_history_list`, `next_page_exists` | one page of records, newest first. The cursor is the previous page's last record `id`; `0` is the first page |
| `gacha/get_rate {"gacha_id": <banner>}` | `rates`, `total_rate_info`, `pools` | the banner's base rates, its consolidated rates (pity included), and every unit it can pay, grouped by tier |
| `gacha/get_list` | `gacha_pity_entity_list` | one pity record per category. Sent at every login |
| `gacha/run`, `gacha/pity_target` | `gacha_pity_entity` | the one pity record the pull or the target change moved |

A record is `{"id", "user_id", "gacha_id", "count", "reward", "prism", "createAt"}`, and **`reward` and `prism` are JSON TEXT**, `"[1009,30117]"`, not lists.

**Asking for one banner's history returns its whole category.** The request for Olga's banner answers with every Combatant rate-up's records; a rerun's request answers with the reruns'.

**Neither a rates reply nor a history page says which banner it answers**, so the addon remembers each request by qid (`gacha_requests`) like its other intents, and forgets them with the rest on `helo`.

**`prism` is not a 50/50 flag.** It is set on every 4-star and 5-star out of the Observe Prism Module (`gacha_card_factor`), which pays Prism Film for them. hub-czn read it as "won the 50/50", which is why its win rate read 100% on that banner and 0% everywhere else.

`gacha/run`'s own reply is not kept: the records restate every pull in it, with an id, the next time they are read.

A pity record carries `pity_ssr_count` (pulls since the last 5-star), `pity_sr_count` (since the last 4-star -- **a 5-star does not reset it**), `createAt` (the category's first pull ever), `updateAt` -- which moves with some pulls and not others -- and `version`, the record's write counter.

## The files

`snapshots/gacha_history/`, a subfolder because the snapshots folder is the one users empty, and `capture/archive.py` only ever sweeps its top level.

| File | Written by | Holds |
| ---- | ---------- | ----- |
| `captured.json` | the capture addon | the records as the wire sent them, keyed by `id`; each banner's rates and when they were seen; the pity records; when each banner's first page was last read |
| `imported.json` | the Import JSON button | batches read out of other files, each marked with the file it came from |

**One writer per file** is what makes an import mid-capture safe: neither process can write over what the other just wrote.

**Every write goes through a checked copy**, and keeps the file it replaces:

1. The merged data is written to `<name>.tmp`.
2. It is read back. It must equal what was meant, and every row the file held before must still be in it, unchanged.
3. `<name>` is renamed to `<name>.bak`. The rename replaces the older backup, which is how that one goes -- there is only ever one.
4. The copy is renamed to `<name>`.

A failure before step 3 leaves the file exactly as it was. **Readers fall back to the backup** where the file is missing or unreadable, which is the state a crash between steps 3 and 4 leaves; starting fresh there would write a one-page history over the whole of it at the next write.

The addon cannot import the app's code, so the procedure exists twice: `gacha_history.write_verified` and the addon's `_write_gacha_store`. `checks/check_gacha_history.py` drives both, including a copy that loses a record on its way to disk.

A reply only ever ADDS. A record the game has stopped listing stays in the file, which is the point of the file.

## Categories

**Pulls are grouped by the pity counter they advance, not by banner** -- `pool_of`. The Probabilities notices put every banner in a category and say one category shares one 5-star counter, and the in-game records group the same way.

A pickup banner names its unit in its id, `gacha_pickup_combatant_30117`, and **a rerun appends a suffix**, `gacha_pickup_combatant_1052_1`. A rerun is its own category -- "Normal Combatant Rate-Up" -- with its own counter, so the suffix moves it to a pool of its own rather than being dropped.

The names the tab shows are the notices' spelling, in `POOL_LABELS`. Players call the rate-ups the release or limited banners and the reruns the rerun banners; the Normal Rescues the permanent or normal banner; and the Observe Prism Module -- its banner is Eternal Moment, the wire's `card_factor` -- the animation or card banner.

**Two families are not named after their banner's id**, which `PREFIX_POOLS` maps: the Special Rescue Request -- the beginner banner, `gacha_general_first_select_1` -- counts on `gacha_pity_first_select`, and the Partner Special Rescue event, `gacha_partner_reform_1`, on `gacha_pity_partner_reform`. Both guarantee a 5-star within 50 pulls, so the shared schedule below does not describe them, and neither can be opened once over: their rates are never read, and no luck figure is drawn for them.

**Whether a category has a 50/50 is read from its rates**, not from its name: a Combatant rate-up splits the 5-star chance between `ssr_rate_up_success_ratio` and `ssr_ratio`, where a Partner rate-up and the Prism Module put all of it on the target and a Normal Rescue has no target. Until a banner's rates have been read, `FIFTY_FIFTY_POOLS` holds the notices' answer, so an import read before any capture still counts its 50/50s.

## Rarity

**The rate lists are the only statement of a unit's rarity the game makes**, and they name a unit the week it is released: `general_ssr_c_1004`, `pickup_c_16_rateup_ssr_c_30117`, `general_r_s_20010`. `stars_of` reads them first, the `CHARACTERS` and `PARTNERS` tables second, and **returns None where neither knows** -- drawn red in the tab, a colour no rarity has, never defaulted.

The default is the thing to never reintroduce. hub-czn read an unknown unit as a 3-star, so every 5-star released after it stopped being updated counted as a 3-star and its pity ran on through them.

The Prism Module lists card items (`card_factor_ssr_5201083`), not units, and its entries never match. The rates are kept per banner in the file, so a unit keeps its tier after its banner closes. Every 3-star is a Partner.

**A unit's stars index `RARITY_COLORS` directly** -- 5 Mythic, 4 Legendary, 3 Rare -- which is what the tab draws its rows in.

## Pity and the 50/50

**Every 5-star resets the count.** The rate-up notices describe a lost 50/50 as the count running on to a guaranteed rate-up at the 140th pull, which reads like a count only a rate-up resets. Only a count reset by every 5-star reproduces the consolidated rates printed beside that text, where the other reading gives 2.78%.

The schedule is the notices': the base rate to the 57th pull, 4.5 points more on each pull from the 58th through the 69th, certain on the 70th -- `SOFT_PITY_FROM`, `SOFT_PITY_STEP`, `HARD_PITY`. It is not on the wire, so `schedule_matches` holds it to what is: a banner whose stated consolidated rate the schedule does not reproduce gets no expected pity and no luck figure. The check pins it to the two published rates, 2.14343% at a 1% base and 3.52734% at 3%.

**After a lost 50/50 the next 5-star is the rate-up**, whichever banner it lands on. The rate-up share the game prints, two thirds of the 5-star rate, is exactly what that guarantee gives.

A 5-star's outcome is `Won`, `Lost`, `Guaranteed`, `Rate-up` -- the featured unit after a stretch where nobody can say whether the last 50/50 was lost -- or `?` where the banner is unknown. A loss still makes the next 5-star a known guarantee even where its banner is unknown; one the history shows was NOT the rate-up is reported as the loss it is.

**The first 5-star of a history that starts mid-cycle has a pity that is only a floor**, so it is left out of the averages and the luck figure -- unless the history reaches back to the category's first pull, which the pity record's `createAt` dates.

## Luck

**Luck** starts from `luckier_than`: the chance that a player needed MORE pulls for as many 5-stars, with half of any tie counting as luckier. Exact under the schedule: the pulls behind k 5-stars are a sum of k independent cycles, built one 5-star at a time and kept per base rate for the session (`_SUM_ODDS`).

**It is shown as a rank from the nearer end** -- `luck_rank`, `Top 12%` or `Bottom 27%` -- so the number is always the small one and the word says which way is good. A bare `Top 93%` reads as praise and means the reverse.

**The tab reads nothing until it is first shown**, so that cost never lands on startup.

A category is **behind** when the game's counters have moved past its history: the count since the last 5-star or the last 4-star disagreeing with what the history adds up to. **Not the pity record's `updateAt`** -- a captured single pull ticked the counters and the record's `version` and left it where it was -- though a stamp that does move past the newest record counts too, while it is within `GAME_KEEPS_DAYS`. Only for a category that has been read at least once: a finished beginner selection may have no screen left to open.

**Behind is urgent once the category's records were last read more than `URGENT_AFTER_DAYS` ago**: the pulls it is missing were made since that read, so the oldest may already be past halfway to `GAME_KEEPS_DAYS`. The tab draws a behind banner orange and an urgent one red, with a line for each colour at the toolbar's right end. A category that is not behind is never urgent, however long ago it was read: it has nothing left to lose.

**No Crystals-spent figure.** hub-czn showed pulls times 160, which is wrong for the Prism Module: it spends Prism Lens.

## Across categories

The Overall Gacha Stats sheet under the Banners list is `across_pools`, into `Overall`. The tab is Stats & Gacha History: the lists beside this sheet are the account's Sortie, Great Rift and Full-Scale Offensive standings, which `docs/unread_stats.md` covers. **The Observe Prism Module is kept apart**: it spends its own currency and pays a 5-star three times as often, so a figure it would dominate is given without it, and its records are its own. The two 50-pull categories never reach a luck figure, having no schedule to compare against.

- **Luck across categories is `luckier_than_across`**: the chance that a player who pulled the same categories and got as many 5-stars on each needed more pulls IN TOTAL. It is not an average of the categories' own figures -- a little unlucky on each adds up, and the whole can sit further out than any one of them. Categories on one base rate are one sum of cycles; different base rates are convolved.
- **The 50/50 record** counts every Combatant rate-up's wins and losses, reruns included, and ranks them with `won_fewer`: the share of players who won fewer, each 50/50 at the chance its rates give.
- **A rate-up Combatant's cost** is the pulls since the rate-up before it, a lost 50/50 included -- `_rate_up_costs`. Only where the start is known: a history starting mid-cycle does not know the first one's, and a 5-star of unknown outcome may have been the rate-up, so the one after it is unknown too. The expected average beside it is `pulls_per_five` times `2 - p`, `p` the chance of winning the 50/50: one cycle, and a second after each loss.
- **The records rest on the same pulls as the averages** -- a first 5-star whose pity is only a floor is never the fastest or the slowest -- and **a record is every pull that ties for it**, oldest first. The tab shows as many ties as fit beside it and drops the newest. A streak is any `STREAK_PULLS` pulls in a row on one category, not only a single 10-pull, read forward from each 5-star so that no two tied streaks hold the same 5-stars.

## Importing

`parse_import` says which files it reads. hub-czn's `Export JSON` is the one that loses things:

- **Each pull's banner is gone.** Every Combatant rate-up, reruns included, became one name, and anything with `supporter` in its id became another -- which files the Normal Partner Rescue under the Partner rate-up.
- **Its `rarity`, `pity` and `is_featured` are ignored**, and worked out again: the rarity was the default above, the pity followed it, and `is_featured` is `prism` masked to what it believed were 5-stars.

**A pull with no banner is dated back to one** -- `dated_banner`, over `RELEASE_BANNERS` and `RERUN_BANNERS`. A release banner changes over at 02:00 UTC, on the day one closes and the next opens, and a pull gets a banner only where exactly one release of its kind was open and no rerun ran beside it. Where two releases overlapped, the pull stays unknown; where a rerun was open too, it could be the rerun's, whose pity is kept apart, and the tab says how many such pulls there are. Only imports need this: the game's own records name their banner.

**The game's own records win wherever they cover the same pulls.** An import is matched to them by record `id`, by category and second, or by second and every unit in the batch -- the last because only the units can say that two batches filed under different categories are one.

## Not yet confirmed

- The pity record's name for a rerun category. `pity_record_name` guesses `gacha_pity_<pool>`; until a rerun is pulled on during a capture, a rerun shows no game counter.
