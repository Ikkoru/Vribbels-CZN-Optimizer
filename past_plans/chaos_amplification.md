# The season estimate and the Environment Variables' amplification — [IMPLEMENTED] 2026-10-22

Each Memory Resonance Amplification node of a Galactic Disaster season's skill tree, the Environment Variables, adds 1% to what its Chaos pays in the season's currency, rounded up: `ceil(base * (100 + n) / 100)`. The estimate now ships payouts at base and counts every run of a part at the nodes the part's tree holds (`chaos_estimate`'s docstring has the model; `docs/client_data.md` the client reading).

## Measurements

- **Every Galactic Disaster payout captured reads back to a whole base** at its run's node count. Season 4: 172 a boss at 19 nodes and 180 at 25 over a base of 144; its Rare Species 60 and Aether Eater 90 at 25, bases 48 and 72. Season 5: 144 and 48 at 0 nodes, 152 and 51 at 5. `docs/chaos_runs.py`'s shipped block, reading each payout back at its run's `amplified`, gave season 4's and season 5's bases exactly.
- **The third boss is not amplified**: season 5's floor-31 boss paid 60 at 0 nodes and at 5, season 4's floor-37 boss 60 at 25.
- **The client says which part a node opens with**: a layout per part in `zero_orb_season_circle`. Amplification nodes by the end of each part: season 2 15 and 25; seasons 3 and 4 13, 19 and 25; season 5 13 in part 1 so far, its one layout listing 35 numbers, 19 with rows.
- **Season 5's part 1 tree** is a 200 root with six branches; twelve amplification nodes at 50 sit right behind it, the thirteenth behind a 200 node: 1,050 for all thirteen, 2,150 for the whole part. Bought with item 3000010, Memory of Light, which Chaos fights drop (27 to 109 a drop, not amplified): 137 for a run lost on floor 28, 336 and 284 for the two cleared on 10-21. The maintainer bought the root and 11 nodes that day, holding 7 after.
- **Memory of Light is capped at the part's tree**, the maintainer says; the captures had not reached the cap by 10-22.

## Rejected

**Ramping each part's first runs with the Memory of Light they earn**, the maintainer's first model. With the cap, each part does ramp: at about 310 a cleared run, cheapest amplification first, season 5's part 1 holds 0, 2, 8 and 12 nodes over its first four runs, 30 node-runs short of 13; on season 4's whole tree its parts come 44, 18 and 6 node-runs short, a node-run being 1% of a run's amplified pay. About half a run's take over a season, under 1% of it at a run a day: left out, at the maintainer's word.

**Working out the account's nodes from the currency it earned and spent.** Every run records the Zero System effects in force, its own season's amplification nodes among them, so a run's node count is on the wire as it stands.

**Shipping payouts as seen**, at the maintainer's own nodes. A run at 5 nodes then stood for a part at 13, and a part's figures were the node count of whoever measured it.

## Decided with it

- A part the season's tree lists no nodes for yet adds what the season before added at that part; a season with no tree takes the season before's whole; with no tree read, the shipped `nodes` stand in the same way. A part's own runs raise its count to the most nodes one had.
- **Rule 5**: a season the program ships no figures for borrows another map's mark rates (season 4 met 1.43 Rare Species a run, season 5 3.0), so the player's own take over after `UNSHIPPED_RATE_RUNS` whole runs of it, where rule 4 waits two seasons and 200 runs.
- A season dated by nothing runs as many parts as its node counts reach, the season before's carried in: three for season 5.

- **One layout for the whole season from season 5 on**, the game's patch notes say, each part's nodes arriving as rows under it. A read gives the total so far, grown onto the counts kept before as the next part's (`game_client.grown_season_nodes`), by `--ship` into `from_client.SEASON_NODES` and by a launch over it. It rests on each patch opening one part.
