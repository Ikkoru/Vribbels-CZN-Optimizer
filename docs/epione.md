# The Epione tab: counseling at the Epione Centre

A combatant broken down by a Chaos run is counseled at the Epione Centre before it fights again. A counseling plays one of the combatant's three scenarios: it opens on a caption, offers two of the scenario's four OPENERS, and the opener picked offers its two FOLLOW-UPS. The two picked add up to the cure result. Every option pays a reward the first time it is picked (5 Crystals), each scenario's record pays once the scenario is first played (50) and all three records once more (150). The tab lists every combatant held with its options picked against its total, and shows the selected one's scenarios, every opener a card holding its follow-ups and the cure each leads to. Marking the two openers the game offers says which to pick.

`Vribbels/epione.py` is the model, `Vribbels/ui/tabs/epione_tab.py` draws it, and `checks/check_epione.py` with a case in `check_tabs_build` hold both.

## Where each fact comes from

| Fact | Source |
| ---- | ------ |
| A combatant's scenarios, each one's title, the line it opens on, its twelve options' words and the stability each adds | the client: `game_client.counseling`, shipped as `from_client.COUNSELING` (`docs/client_data.md`) |
| The options picked, and which of their rewards are claimed | the wire: `counseling_archive`, in the login's roster payload |
| Who is broken down, and so counseled next | the wire: a roster row's `psychosis_id` |
| Which scenario is being played, and which two openers are offered | nothing: the game deals them, and tells the server only what was picked. The player marks them on the tab |

### The client's tables

- `counseling_archive@counseling_archive`: a row per scenario (`<combatant>_<n>`), naming its story (`counseling_<combatant>_0<n>`), its title's text and its record's reward. `counseling_archive_set@counseling_archive_set`: a row per combatant, its three scenarios and the reward for all three.
- `story_counseling_<date>@story`: the stories, the table named for the patch that last wrote it; the newest is read. A scenario's story holds its caption (the first `CAPTION` line, English in `text_en`) and its twelve options: `choice` 1-4 the openers, two filed `SCORE_CHOICE_L` and two `SCORE_CHOICE_R`; 5-12 the follow-ups, each naming its opener in `use_choice`, one L and one R an opener (1: 5, 6; 2: 7, 8; 3: 9, 10; 4: 11, 12). An option's `text_en` is `Label<br>Words`.
- An option's wire id is its story's id and its number, `counseling_1003_01_5`. The newer combatants' lines (30115, 30117, 1012, 30134 on build 133) leave `link_story_choice_id` empty, so the id is built, never read.
- `counseling_story_choice@counseling_story_choice`: each option's `counseling_stability`, which goes over the story line's `opt`; the two agree on build 133. `counseling_archive_contents@counseling_archive_contents`: each option's reward, `<combatant>_0<n>_<choice>`.
- `story_content_counseling@story_component_counseling` and `counseling_result@counseling_result`: the cure's tiers. `story_compo_<combatant>_end_<n>` holds a range of the stability total (70-79, 80-89, 90-110 and 0-69 on build 133), and the result whose `stability_point` falls in it pays `reward_friendship` Affinity (5, 10, 15, 1). A total past 100 shows as 100%.

**The cure result is the two options' stabilities added.** Every counseling in the captures from 2026-09-22 to 2026-10-27, 26 of them, sent the end component whose range holds the sum, and the server answered with that tier's result.

Affinity rose by 10 more than `reward_friendship` in each of those captured: 25 for a result of 90, 15 for 70. The tab does not show Affinity for that reason.

### The wire

`counseling_archive` comes with `load/user`, a list of every combatant with a record, and the capture keeps it in the roster payload (the snapshot's `characters`):

```
{"res_id": 1052,
 "counseling_list": [{"counseling_id": "1052_1", "reward_get": true}, ...],
 "counseling_choice_list": [{"counseling_id": "1052_3",
     "counseling_story_choice_list": {"counseling_1052_03_1": true,
                                      "counseling_1052_03_3": false, ...}}],
 "all_reward_get": true}
```

- `counseling_list` lists the scenarios played, each with its record's reward claimed or not.
- An option in `counseling_story_choice_list` is picked: `true` once its reward is claimed in the game's Counseling Records, `false` until then.
- `all_reward_get` is the reward for all three records.

**The record of options picked begins with the 2026-07-29 patch**, which backfilled some of the options picked before it and not all: Tressa's three records were claimed in May, and her record holds one pair. The game pays by the server's record, so an option the record lacks pays again, whatever was played before it.

**What moves it in a session**, folded in by `Addon._note_counseling`:

- A Chaos run's close (`stage/clear_stage`) sends, for each combatant it broke down, the combatant's whole record under `changed_counseling_archive_array`, and its breakdown under `psychosis_chars` (`psychosis_id`, `psychosis_recover_price_id` and the rest of `PSYCHOSIS_FIELDS`), which the capture lays on the roster row.
- `mentalclinic/recover_char_counseling` is the counseling. Its request names the combatant (`char_res_id`) and the two options picked, under the start component the game dealt; its reply sends the combatant's record, the new options `false`, and its `friendship_exp`. The reply carries no roster row, so the capture takes the breakdown off the combatant its request named, and sets the Affinity.
- `mentalclinic/get_counseling_reward` claims a scenario's waiting rewards and sends the record again, `true` now.
- `mentalclinic/enter_recover_char_counseling` opens the Centre and says nothing of what is dealt.

A combatant whose roster row carries a `psychosis_id` awaits counseling. It stays set between logins: on 2026-10-21 three combatants broken down in the afternoon were still so at the evening's login.

## What the tab counts

- **Completed** is the options picked, claimed or not, against twelve a scenario.
- **A reward waiting**: an option picked and not claimed, a scenario played whose record is not claimed, or all three claimed without the set's. The combatant's count goes orange, its row in the list too, and its options waiting are orange on their cards.
- **Left to earn**: the options not picked, the scenarios not played, and the set's reward while not taken.
- A combatant awaiting counseling is red in the list, and its status line says so. **One newly broken down is selected**: a refresh finding a combatant awaiting that was not at the last one shows it, the first by name where a run broke down two.
- A combatant held whom the client gives no counseling is listed with `-`.

## The whiffs

**A whiff is a counseling offering nothing new**: both offered openers picked, with both their follow-ups. A counseling offering an opener with a follow-up left picks one, and every such counseling takes one follow-up off its opener, so a scenario takes exactly as many productive counselings as it has follow-ups left. What a pick changes is how many whiffs come before them. A follow-up's own choice changes nothing there: either takes one off the same opener. So it goes to the better cure.

The state of a scenario is each opener's follow-ups left, `(2, 1, 0, 2)`. With `w` the chance a counseling offers only openers with none left, and the pairs it may offer each as likely:

```
E(left) = (w + sum over the other pairs of chance * min(E(left after picking either))) / (1 - w)
E(nothing left) = 0
```

`epione.whiffs_to_come` solves it, memoised over the 81 states; `check_epione` holds it to a value iteration over all of them. Each offered card says `E` after picking it, and the fewer is the pick. Between two leaving as many, the one whose best new follow-up cures more; then the one not yet picked itself. Offered two with nothing left, the pick is the pair curing most.

**The count is per scenario.** Which scenario a counseling plays is the game's, and a finished scenario's counselings are whiffs whatever is picked, so nothing chosen in one scenario moves another's.

### Which openers come together

**The tab takes a counseling to offer one opener of each side**, four pairs each as likely (`epione.PAIRING`, `ONE_PER_SIDE`): the client files two openers under the left button and two under the right, and nothing else says how the two are dealt. `ANY_TWO`, any two of the four, is the other reading, six pairs; it changes the counts and lets a card mark replace any earlier one instead of its side's. The maintainer has not yet seen which: two openers of one side offered together would settle it for `ANY_TWO`.

## The tab

The list (`Combatant`, `Completed`) sorts by either heading; a letter jumps to a name. To its right, the selected combatant's name and count, and its status: awaiting counseling, Crystals left to earn, and what waits to be claimed. Under it a row per scenario: its title, its options picked against twelve, the line it opens on, then four cards, the two left-button openers and, past a wider gap, the two right-button ones. A card holds its opener, bold, then each follow-up with the cure its path gives. Picked options are dimmed; options whose reward waits are orange.

Clicking a card marks its opener offered, taking its side's mark from the other opener on that side; clicking it again unmarks it. Once one each side is marked, both cards end on their whiffs to come, the pick green with its follow-up. A combatant changing, or its options picked moving, unmarks them: the next counseling deals anew.
