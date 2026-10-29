# Vribbels CZN Optimizer (Ikkoru)

A fork of Vribbels, a Fribbels-inspired gear management and optimization tool for the game **Chaos Zero Nightmare**. It reads your Memory Fragments from the game and works out the best six for a combatant. Features a **Pull Tracker** that shows your luck.

## Installation & Usage

You need Windows, the STOVE client, and Python with mitmproxy (`pip install mitmproxy`).

1. Download the latest release from the [Releases page](https://github.com/Ikkoru/Vribbels-CZN-Optimizer/releases).
2. Run `Vribbels_CZN_Optimizer_Ikkoru.exe` as Administrator.
3. Open the **Setup & Settings** tab and follow `Setup Instructions`.
4. Open the **Capture** tab and click Start Capture.
5. Launch the game. Keep the program open: in-game changes are captured LIVE.

Note: On first run SmartScreen may pop up. Press More info → Run anyway. Some antiviruses flag one-file programs that ask for Administrator, too.

Instructions if you wish to run from source are [further down](#running-from-source).

## Optimizing

The latest snapshot loads on startup. Pick a combatant, fill in **Important Settings** (optional), then press Start.

Most of the settings are self-explanatory. These are the ones that aren't:

- **The three damage sliders** — Extra, Agony and Fracture — how much of the combatant's damage is of that type. Fracture slider includes Scorched. Based on your deck, not damage numbers: add up the `DMG%/turn` of each type and take the fractions. Everything left over counts as Card damage.

  > Don't stress about getting these super accurate. Dealing 3 more damage per turn isn't going to save you from the Nightmare.

- **Have at Least** floors are measured the way the game's Potential 7 checks measure them, so clearing one here means clearing it in-game. Builds that miss any floor are dropped entirely.

- **Maximum Flex Slots** is how many of the six slots may sit outside the sets you ticked.

- **A conditional set's percentage** is how much of this combatant's damage actually benefits from that set's effect. At 0 the fragments still count for their stats and only the effect is ignored.

- **Exclude Combatant's MFs** starts with everyone excluded. Unticking someone lets the optimizer take the gear they are wearing. The combatant you are optimizing is never excluded from their own gear.

In the results, scores run 0–100 with the run's best build at 100. `(E)` marks the build you already equipped. `(F)` marks a set the flex slots completed by accident rather than one you picked — its bonus counts either way. Click a row to compare it against your current build; right-click that comparison for a full breakdown of where every number comes from.

## Other things worth knowing

- **Gear Score** weights are per-combatant presets. Assign them on the **Combatants** tab, edit the weights on the **Gear Score** tab.
- **Double-click** or select a preset and press Apply in the **Gear Score** tab to change the GS and Potential values in the **Memory Fragments** tab. Useful for finding good MFs to level and bad MFs to dismantle.
- **The optimizer uses every CPU core.** Change that with **Optimizer cores** in the **Setup & Settings** tab's Settings panel. It applies on the next launch.
- **Affinity, potential nodes and Partner bonuses** are all counted in the stats the optimizer scores.
- **The Combatants tab lists every potential node**, and its `Nodes` column is a combatant's node levels summed against the maximum.
- **The Materials tab** counts your promotion and levelling material by class, and your growth stones by Element. Each row's figures are that row's own holdings in bottom-tier equivalents, then what share that is of what a target costs.
- **The Checklist tab** shows what resets when — daily, weekly, monthly and seasonal — and what is left to do on each, updating while the game is captured. Tick or untick a shop's products to track only what you actually buy: the shop's heading then reads what you hold against what clearing it costs, and hovering it says what that currency earns in a rotation.
- **The Galactic Disaster tab** lists what is left on the season's Challenge Mission pages, a column per page with its done/total count, and how many achievements are still locked by when they open. A page with nothing left moves to the right in green; an orange count means a reward is waiting to be claimed.
- **The Stats & Gacha History tab** keeps every pull the game has listed, which the game itself does for only about half a year, and says how lucky each banner type has been for you. Open each banner's Probability Info → Rescue Records in game while capturing to add them. The program can capture pulls live as well. The history lives in `snapshots/gacha_history/`. Beside the pulls' figures, your Sortie, Great Rift and Full-Scale Offensive standings, a column per season; the note beside each list says what to open while capturing to fill it.
- **The Epione tab** tracks each combatant's Therapy Counseling at the Epione Centre: which dialogue options you have picked (each pays Crystals the first time), and the cure each pair of options gives. Click the two options the game offers and it says which to pick to run into fewer counselings offering nothing new. A combatant broken down by a Chaos run shows red and is selected for you while capturing.
- Everything the program saves sits beside the exe in `settings/` and `snapshots/`. Keep the exe in its own folder; back up or move that folder, and put new versions in it.

## Contributing

Bug reports, character and partner data corrections, and feature ideas are all welcome via GitHub Issues.

## Privacy

Nothing leaves your machine except:

- A request to GitHub at each launch, and when you press the `Check Now` button, to check for updates. Choosing `Ignore Until Updated` when it announces one stops the launch's request until you update.

- Pressing the `Export Facts` button opens the GitHub Issues webpage, and asks you to upload the file it makes to it. None of your personal data is included.

While capturing, the game's server names are pointed at your PC in the Windows hosts file, between `# CZN-CAPTURE-START/END`. Stop removes them, and so does the next launch after a crash. In case of a crash, relaunch the program so they are removed.

Pressing `Generate & Install Cert` adds a mitmproxy certificate to your trusted roots. If someone gets their hands on its private key and manages to get between you and the internet, they can impersonate any website. Be wary of accidentally sharing `%USERPROFILE%\.mitmproxy` with others. Delete the certificate and generate a new one if you accidentally upload/share that folder. Consider deleting the certificate when you are done with CZN.

## Running from source

1. Download the source code, or clone this project using GitHub Desktop, or a similar program.

2. Install Python 3.12 or newer (developed on 3.14).

3. Open a command line terminal in the folder where `requirements.txt` is and run `pip install -r requirements.txt`.

4. Run the program using `zRUN.bat`.

## Tracking Chaos runs

While capture is on, every Chaos run is recorded: what it paid, every fight and what it carried (Rare Species, Aether Eater, Senectus), where a Senectus broke in, your partners and their limit breaks, Nightmare Mode, Distortion Adaptation, the opening pick at Kyrken's Messenger, the party's HP at each fight's start, and the map. Ticking **Debug WS** on the Capture tab also keeps a log of each session, which lets the scripts read old runs again for anything they learn to record later.

**The easy way**, with the program's exe or from source:

1. Download the source code (on GitHub, **Code → Download ZIP**) and unzip it anywhere.
2. Double-click `zRUN Chaos Runs Spreadsheet.cmd` in it. It checks for Python and the one add-on it needs, and says what to do if either is missing.
3. When it asks, drag the folder holding `Vribbels_CZN_Optimizer_Ikkoru.exe` into the window and press Enter. Running the program from source, just press Enter.

`my_chaos_runs.tsv` and `my_chaos_runs.xlsx` land on your Desktop. Run it again after more runs to add them. To combine several players' runs, paste every line but the first of one `.tsv` under another's and make the spreadsheet from that.

**By hand**, in the downloaded source, with Python 3.12 or newer and `pip install openpyxl` (the scripts need nothing from `requirements.txt`):

1. Make your table, and see its report:

   ```
   docs\chaos_runs.cmd --out "%USERPROFILE%\Desktop\my_chaos_runs.tsv"
   ```

   `docs/chaos_runs.tsv` holds the maintainer's runs, so give `--out`, or your runs join theirs. `--all` reads every debug log again; `--full` shows the report without pooling; `--data "<folder>\snapshots"` reads the data a built program keeps beside its exe.
2. Make the spreadsheet beside it (`my_chaos_runs.xlsx`):

   ```
   docs\chaos_runs_xlsx.cmd "%USERPROFILE%\Desktop\my_chaos_runs.tsv"
   ```

How each column and rate is worked out is at the top of `docs/chaos_runs.py`.

## Credits

Original by [Vorbroker](https://github.com/Vorbroker/Vribbels-CZN-Optimizer).

Inspired by [Fribbels Epic 7 Gear Optimizer](https://github.com/fribbels/Fribbels-Epic-7-Optimizer).

Thanks to [EpicSevenAssetRipper](https://github.com/CeciliaBot/EpicSevenAssetRipper) for asset extraction tools.

The Stats & Gacha History tab's pull history takes its idea from [hub-czn](https://github.com/sostenesfreitas/hub-czn)'s Rescue Records, and reads its Export JSON.

## License

MIT License — see [LICENSE](LICENSE) file for details.

Chaos Zero Nightmare and all related assets are property of their respective owners.

---

**Note**: This is a third-party tool and is not affiliated with or endorsed by the developers of Chaos Zero Nightmare.

## Support

This is free and stays free. If it saved you time and you'd like to say thanks, a tip is welcome but never expected:

<a href="https://ko-fi.com/eepycoding"><img src=".github/support_me_on_kofi_blue.webp" alt="Support me on Ko-fi" width="245"></a>

To thank the original creator of this project as well: https://ko-fi.com/H2H21PHYKW
