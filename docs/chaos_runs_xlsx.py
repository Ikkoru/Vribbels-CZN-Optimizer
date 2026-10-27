"""Turn a Chaos runs table (`docs/chaos_runs.py`'s) into a spreadsheet.

    python docs/chaos_runs_xlsx.py                        # docs/chaos_runs.tsv -> docs/chaos_runs.xlsx
    python docs/chaos_runs_xlsx.py my_runs.tsv            # my_runs.tsv -> my_runs.xlsx
    python docs/chaos_runs_xlsx.py my_runs.tsv --out x.xlsx

`docs/chaos_runs_xlsx.cmd` runs it from Explorer, passing on any of
these. Three sheets, each opening with what its rows or columns mean:

- **Results**: every rate, worked out by formulas over Raw, so it
  follows any row edited there -- Senectus a run, the Aether Eater a
  battle and the Rare Species a fight, each over every map, each
  season's Effect, hand-played runs and delegated ones; Senectus a run
  by the HP held; then the fixed facts the client gives, with their
  source.
- **Raw**: the table, every column, after numeric columns worked out
  from it for Results' formulas. A rate is counted the way
  `docs/chaos_runs.py` counts it (`identities`, `counted_over`).
- **Senectus test**: the hand-played whole runs, against a community
  test's rules: Zero System level 80+ or Galactic Disaster 8+, party HP
  kept at 75-100% or at 25-50% of its most, Nightmare Mode on, no
  1-HP opening bonus.

The file holds formulas with no values worked out: Excel and LibreOffice
work them out on opening (`fullCalcOnLoad`).
"""
import argparse
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
parser.add_argument("table", nargs="?", default=str(HERE / "chaos_runs.tsv"))
parser.add_argument("--out")
args = parser.parse_args()
TABLE = Path(args.table).resolve()
OUT = Path(args.out).resolve() if args.out else TABLE.with_suffix(".xlsx")

# docs/chaos_runs.py moves to the source folder as it loads, so the
# paths are fixed above first.
sys.argv = [sys.argv[0]]
sys.path.insert(0, str(HERE))
import chaos_runs as tool                                     # noqa: E402

ce = tool.chaos_estimate
tool.OUT = TABLE
header, rows = tool.existing()
if not rows:
    sys.exit("No runs in %s." % TABLE)
rows = [rows[date] for date in sorted(rows)]
whole = {row["date"] for row in tool._whole_runs(
    {row["date"]: row for row in rows})}
met_in = tool._met_in([row for row in rows if row["date"] in whole])


def _invasion_partners():
    """The names of the partners whose Exploration Passive raises the
    Invasion chance (`chaos_estimate.INVASION_EFFECT`), off the client's
    effects: Sig and Peko so far."""
    from game_data.partners import PARTNERS
    import game_client
    return {(PARTNERS.get(res_id) or {}).get("name")
            for res_id, passives in game_client.known_exploration_effects()
            .items() for effect, _steps in passives
            if effect == ce.INVASION_EFFECT} - {None}


RAISERS = _invasion_partners()
RAISERS_SAID = "/".join(sorted(RAISERS)) or "Invasion partners"

FONT = "Arial"
BOLD = Font(name=FONT, bold=True)
PLAIN = Font(name=FONT)
NOTE = Font(name=FONT, italic=True, color="555555")
HEAD_FILL = PatternFill("solid", start_color="DDE7F0")
WRAP = Alignment(wrap_text=True, vertical="top")


def marks(row, mark):
    return sum(n for key, n in tool.counts_of(row.get("marked")).items()
               if mark in tool.identities(key))


def derived(row):
    """A row's numeric columns, for Results' formulas."""
    fought = tool.counts_of(row.get("fought"))
    hp = re.match(r"(\d+)-(\d+)%", row.get("hp") or "")
    partners = [p.strip().rsplit(" LB", 1)[0]
                for p in (row.get("partners") or "").split(",") if p.strip()]
    return {
        "whole run": int(row["date"] in whole),
        "season's own Chaos": int(tool.current(row)),
        "Effect": tool.effect_season(row),
        "Invasion raised": int(bool(tool.raise_of(row))),
        # Before the passives came, no partner raised anything.
        RAISERS_SAID + " taken": (sum(1 for p in partners if p in RAISERS)
                                  if ce.had_passives(
                                      {"client": row.get("client")}) else 0)
        if row.get("partners") not in (None, "", "?") else "",
        "Senectus met": int(tool.met_of(row)),
        "Senectus on a Rare Species": tool.counts_of(
            row.get("marked")).get("b1+k5", 0),
        "Aether Eaters": marks(row, "e"),
        "Rare Species": marks(row, "k5"),
        "battles": fought.get("battle", 0),
        "Elites": fought.get("elite", 0),
        "fights": fought.get("battle", 0) + fought.get("elite", 0),
        "Aether Eater possible": int(row["chaos"] in met_in.get("e", ())),
        "Rare Species possible": int(row["chaos"] in met_in.get("k5", ())),
        "HP lowest %": int(hp.group(1)) if hp else "",
        "HP highest %": int(hp.group(2)) if hp else "",
    }


EXPLAIN_RAW = {
    "date": "When the run was cleared (UTC).",
    "season": "Galactic Disaster season it was played in.",
    "part": "Season part (shop page) it was played in.",
    "chaos": "Which Chaos map.",
    "door": "Galactic Disaster = the season's own Chaos; Zero System = a "
            "Zero System map; own screen = a base-game Chaos.",
    "difficulty": "Chaos level (8, 11) or Zero System map level (lv80).",
    "floors": "Map floors as the game sends them; the last is the 2nd "
              "boss's floor.",
    "special": "Zero System special options (a past season's Effect).",
    "options": "Zero System map bonus/penalty option ids.",
    "rolled": "Bonus/penalties the run rolled, as effects.",
    "amplified": "Season currency +1% nodes owned.",
    "partners": "Each combatant's partner and limit break.",
    "invasion": "Senectus chance raise from Danger Intuition, in the game's "
                "words (+8% LB0, +16% LB2 per partner). Empty: none.",
    "mode": "delegated = Delegation Module played it; ordinary = by hand.",
    "client": "Game client version.",
    "total": "Season currency paid.",
    "payouts": "Each payout: floor:spot:amount+mark.",
    "marked": "Marked fights: k5 Rare Species, e Aether Eater, b1 "
              "Senectus (b1+k5 = Senectus on a Rare Species spot).",
    "marked_at": "spot.mark:count, the count being how many in the run.",
    "fought": "Fights by spot type (break_in = Senectus).",
    "route": "Every spot entered, by type.",
    "map": "Each area's map as first sent (delegated runs get the route "
           "only: `path`). kw. = Rare Species spots, ev. = spot events.",
    "hp": "Party HP at each fight's start, lowest-highest % of max.",
    "nightmare": "Nightmare Mode on or off.",
    "opening": "Option picked at the opening event (Kyrken's Messenger).",
    "1hp_start": "yes = that pick carried the bonus setting the first 3 "
                 "normal battles' enemies to 1 HP.",
    "lost": "Where a lost run was lost.",
    "gaps": "Parts of the run the capture did not see.",
    "log": "Capture log it was read from.",
    "missed": "What a lost run would have paid.",
    "notes": "Player's notes.",
}


def widths(ws, values):
    for column, width in values.items():
        ws.column_dimensions[column].width = width


wb = Workbook()
wb.calculation.fullCalcOnLoad = True
res = wb.active
res.title = "Results"
raw = wb.create_sheet("Raw")
test = wb.create_sheet("Senectus test")

# ---------------- Raw ----------------
spot_cols = [c for c in header if c.startswith(tool.SPOT_COLUMN)]
plain_cols = [c for c in header if c not in spot_cols]
derived_cols = list(derived(rows[0]))
raw_cols = derived_cols + plain_cols
raw.append(["Worked out from the table's own columns, for Results' "
            "formulas." if c in derived_cols else EXPLAIN_RAW.get(c, "")
            for c in raw_cols])
raw.append(raw_cols)
for row in rows:
    held = derived(row)
    raw.append([held[c] for c in derived_cols]
               + [row.get(c, "") for c in plain_cols])
for cell in raw[1]:
    cell.font, cell.alignment = NOTE, WRAP
for cell in raw[2]:
    cell.font, cell.fill = BOLD, HEAD_FILL
raw.row_dimensions[1].height = 90
raw.freeze_panes = "B3"
for i, column in enumerate(raw_cols, 1):
    raw.column_dimensions[get_column_letter(i)].width = (
        12 if column in derived_cols else 18)
last = len(rows) + 2


def col(name):
    """An absolute Raw range for a column, rows 3 to the last."""
    letter = get_column_letter(raw_cols.index(name) + 1)
    return "Raw!$%s$3:$%s$%d" % (letter, letter, last)


# ---------------- Results ----------------
res.append(["What it is", "Stat", "Pool", "Met", "Out of", "Rate"])
for cell in res[1]:
    cell.font, cell.fill = BOLD, HEAD_FILL
effects = sorted({tool.effect_season(row) for row in rows})
POOLS = ([("every map", [])]
         + [("%s maps" % effect if effect == "no Effect"
             else "season %d Effect maps" % int(effect[1:]),
             [(col("Effect"), '"%s"' % effect)]) for effect in effects]
         + [("hand-played runs", [(col("mode"), '"ordinary"')]),
            ("delegated runs", [(col("mode"), '"delegated"')])])


def cond(extra):
    return "".join(",%s,%s" % pair for pair in extra)


def add(explain, stat, pool, met, out_of, fmt="0.000"):
    r = res.max_row + 1
    res.append([explain, stat, pool, met, out_of,
                "=IFERROR(D%d/E%d,\"\")" % (r, r)])
    res.cell(r, 6).number_format = fmt


base = [(col("whole run"), "1")]
for pool, extra in POOLS:
    c = cond(base + [(col("Invasion raised"), "0")] + extra)
    add("Share of whole runs that met a Senectus (at most one a run). Runs "
        "with a partner raising the chance left out." if pool == "every map"
        else "", "Senectus a run", pool,
        "=COUNTIFS(%s,1%s)" % (col("Senectus met"), c),
        "=COUNTIFS(%s,1%s)" % (col("whole run"), c), "0.00")
for pool, extra in POOLS:
    c = cond(base + [(col("Aether Eater possible"), "1")] + extra)
    add("Aether Eaters per ordinary battle (they never appear on Elites), "
        "over maps where one has been met." if pool == "every map" else "",
        "Aether Eater a battle", pool,
        "=SUMIFS(%s%s)" % (col("Aether Eaters"), c),
        "=SUMIFS(%s%s)" % (col("battles"), c))
for pool, extra in POOLS:
    c = cond(base + [(col("Rare Species possible"), "1")] + extra)
    add("Rare Species per battle or Elite fight, over maps where one has "
        "been met. A Senectus on a Rare Species spot is not counted again."
        if pool == "every map" else "", "Rare Species a fight", pool,
        "=SUMIFS(%s%s)" % (col("Rare Species"), c),
        "=SUMIFS(%s%s)" % (col("fights"), c))
add("How many Senectus broke in on a Rare Species spot: it then pays a "
    "second Rare Species payout.", "Senectus on a Rare Species spot",
    "every map", "=SUMIFS(%s%s)" % (col("Senectus on a Rare Species"),
                                     cond(base)),
    "=COUNTIFS(%s,1%s)" % (col("Senectus met"), cond(base)), "0.00")
hand = base + [(col("mode"), '"ordinary"'), (col("Invasion raised"), "0")]
for label, extra in (
        ("HP stayed 75-100%", [(col("HP lowest %"), '">=75"')]),
        ("HP stayed 25-50%", [(col("HP lowest %"), '">=25"'),
                              (col("HP highest %"), '"<=50"')]),
        ("HP went below 75% (any)", [(col("HP lowest %"), '"<75"')])):
    add("Senectus a run by the party HP held at every fight's start, "
        "hand-played whole runs only." if label.startswith("HP stayed 75")
        else "", "Senectus a run, " + label, "hand-played runs",
        "=COUNTIFS(%s,1%s)" % (col("Senectus met"), cond(hand + extra)),
        "=COUNTIFS(%s,1%s)" % (col("whole run"), cond(hand + extra)),
        "0.00")

res.append([])
res.append(["Fixed facts (not formulas)", "Fact", "Value", "Source"])
for cell in res[res.max_row]:
    cell.font, cell.fill = BOLD, HEAD_FILL
fitted = ce.invasion_fit([(tool.met_of(row), tool.raise_of(row) or 0.0)
                          for row in rows if row["date"] in whole])
for row in (
        ("Senectus (client table break_in, row bi_0001)",
         "Base chance per check", "%d%%" % ce.INVASION_BASE,
         "Game client data, break_in_col_cnt_revise"),
        ("", "Added per missed check", "+%d%%" % ce.INVASION_STEP,
         "Game client data, break_in_ck_fail_revise"),
        ("", "Most per run", "1",
         "Client break_in_max_cnt; no captured run met two"),
        ("", "Earliest floor", "5", "Client break_in_first_spot"),
        ("Danger Intuition (%s)" % ", ".join(sorted(RAISERS)),
         "Added to every check, per partner", "+0.56% at LB0, +1.12% at LB2",
         "Client partner_ego_passive nb_eff; the game text's +8%/+16% is "
         "of the 7% base"),
        ("What a 'check' is", "Not in the client",
         "%.1f checks a run fits these runs" % fitted if fitted is not None
         else "", "Fitted to every whole run (chaos_estimate.invasion_fit), "
                  "not a game value"),
        ("Amplification nodes", "Each node",
         "+1% of the season's currency, rounded up",
         "Captured payouts; client zero_orb_season_skilltree")):
    res.append(list(row))
widths(res, {"A": 46, "B": 36, "C": 30, "D": 34, "E": 10, "F": 8})
for row in res.iter_rows(min_row=2):
    for cell in row:
        if not cell.font.bold:
            cell.font = PLAIN
        cell.alignment = WRAP
for cell in res["A"][1:]:
    cell.font = NOTE
res.freeze_panes = "B2"

# ---------------- Senectus test ----------------
taken = RAISERS_SAID + " taken"
test_cols = ["date", "chaos", "door", "difficulty", taken, "HP lowest %",
             "HP highest %", "HP group", "Nightmare", "1-HP start buff",
             "Senectus met", "fights", "Fits"]
explain = {
    "date": "Whole hand-played runs only (the test's rule: no delegated "
            "runs).",
    "chaos": "Chaos map.",
    "door": "How it was entered.",
    "difficulty": "Galactic Disaster Chaos level (8, 11) or Zero System "
                  "map level (lv80).",
    taken: "Invasion-raising partners in the team (0 before the "
           "Exploration Passives came).",
    "HP lowest %": "Lowest party HP at a fight's start, % of max.",
    "HP highest %": "Highest party HP at a fight's start, % of max.",
    "HP group": "75-100, 25-50, or mixed (the test's two groups).",
    "Nightmare": "Nightmare Mode on or off, as the run was entered.",
    "1-HP start buff": "yes = the run's opening pick (Kyrken's Messenger) "
                       "was the one option of three carrying the bonus "
                       "'first 3 normal battles' enemies at 1 HP', on top "
                       "of its own reward.",
    "Senectus met": "1 = a Senectus spawned in the run.",
    "fights": "Battles and Elites fought.",
    "Fits": "Zero System level 80+ or Galactic Disaster 8+, one of the "
            "test's HP groups, Nightmare on, no 1-HP start buff.",
}
test.append([explain[c] for c in test_cols])
test.append(test_cols)
r = 3
for row in rows:
    if row["date"] not in whole or row.get("mode") != "ordinary":
        continue
    held = derived(row)
    level = row["difficulty"]
    high = (level.startswith("lv") and level[2:].isdigit()
            and int(level[2:]) >= 80) or (
        row["door"] == "Galactic Disaster" and level.isdigit()
        and int(level) >= 8)
    test.append([row["date"], row["chaos"], row["door"], level, held[taken],
                 held["HP lowest %"], held["HP highest %"],
                 '=IF(F%d="","?",IF(F%d>=75,"75-100",IF(AND(F%d>=25,'
                 'G%d<=50),"25-50","mixed")))' % (r, r, r, r),
                 row.get("nightmare", "?"), row.get("1hp_start", "?"),
                 held["Senectus met"], held["fights"],
                 '=IF(AND(%s,OR(H%d="75-100",H%d="25-50"),I%d="on",'
                 'J%d="no"),"yes","no")' % (
                     "TRUE" if high else "FALSE", r, r, r, r)])
    r += 1
for cell in test[1]:
    cell.font, cell.alignment = NOTE, WRAP
for cell in test[2]:
    cell.font, cell.fill = BOLD, HEAD_FILL
test.row_dimensions[1].height = 75
widths(test, {get_column_letter(i): w for i, w in enumerate(
    (17, 26, 18, 10, 12, 11, 11, 10, 10, 12, 10, 8, 34), 1)})
for sheet in (raw, test):
    for row in sheet.iter_rows(min_row=3):
        for cell in row:
            cell.font = PLAIN
test.freeze_panes = "A3"
wb.save(OUT)
print("%d run(s), %d whole, %d hand-played whole -> %s"
      % (len(rows), len(whole), r - 3, OUT))
