"""The Substat Readjustment tab: which fully upgraded Legendary Memory
Fragments a Shuffling Quartz does most for.

A readjustment deals a fragment's upgrades out again and the player
keeps Before or After, so it can only gain; `readjust` works out what
it is expected to, plainly (1 Quartz) and with the best substat
excluded (2 Quartz), and the list ranks every fragment by the better
of the two per Quartz.

**Score** picks the measure: Gear Score, under the combatant's assigned
preset, or Build Score, the Optimizer's score against the combatant's
Top build, each fragment in the best build the Optimizer finds around
it, under the combatant's Optimizer tab settings. **For** picks whose: one
combatant, or several, each weighted, every fragment read for the one
whose weighted gain is highest. **Slots**, **Sets** and **MFs**
narrow the list without working anything out again.

**The work is the app's** (`readjust_work.ReadjustWork`): it works out
every combatant's readings in worker processes, the ones this tab shows
first, in the background from launch or at full speed, and keeps them
between launches. The tab draws what it has: its list once the
combatants it shows are worked out, and how far the rest have got under
the counts. `docs/readjust.md` has the model.
"""

import tkinter as tk
from tkinter import ttk

import item_amounts
import readjust as rj
from game_data import EQUIPMENT_SLOTS, SETS
from readjust_work import (BACKGROUND_KEY, COMBATANT_KEY, MEASURE_KEY,
                           MODE_KEY, WEIGHTS_KEY, ReadjustWork)
from game_data.characters import ATTRIBUTE_COLORS
from game_data.sets import named_sets, set_named, set_pieces
from game_data.sets import set_name as set_name_of

from ..base_tab import BaseTab
from ..scaling import px, px_after
from ..utils.all_none_row import make_all_none_row
from ..utils.checkbox import FOCUS_INSET, make_checkbox
from ..utils.combobox_nav import bind_combobox_nav
from ..utils.spinbox_clamp import clamp_on_commit, step_on_wheel
from ..utils.tooltip import Tooltip

# The dropdowns' words, each beside what it stands for.
MEASURES = (("Gear Score", rj.GEAR), ("Build Score", rj.BUILD))
MODES = (("One combatant", "one"), ("Several, weighted", "weighted"))
OWNERS = (("All", "all"), ("Worn by them", "theirs"),
          ("Unequipped", "unequipped"))

# The settings each control is kept under (`settings_manager.LAYOUT`);
# the rest, which the work reads too, are `readjust_work`'s.
OWNER_KEY = "readjust_owner"
# The Weights list's sort: [column, descending].
WEIGHTS_SORT_KEY = "readjust_weights_sort"

# A combatant's weight runs 0 (left out) to this.
WEIGHT_MAX = 10

# The list: (column, heading, the widest it holds, anchor). Sized off
# the heading and the samples in the list's own fonts.
COLUMNS = (
    ("slot", "Slot", ("VI",), tk.CENTER),
    ("set", "Set", ("Offering of the Void",), tk.W),
    ("main", "Main", ("Instinct DMG%",), tk.W),
    ("worn", "Equipped", ("Heidemarie",), tk.W),
    ("subs", "Substats",
     ("Extra DMG% 12.6% (+3)  CDmg 12.4% (+3)  DoT% 15.3% (+4)  "
      "Flat DEF 14 (+3)",), tk.W),
    ("for", "For", ("Heidemarie",), tk.W),
    ("now", "Now", ("-10.00%", "100.0"), tk.E),
    ("avg", "Avg", ("-10.00%", "100.0"), tk.E),
    ("gain", "Reroll", ("+10.00%",), tk.E),
    ("chance", "Chance", ("100%",), tk.E),
    ("excl", "Exclude", ("Extra DMG%",), tk.W),
    ("xgain", "Gain", ("+10.00%",), tk.E),
    ("xchance", "Chance", ("100%",), tk.E),
    ("best", "Best", ("+10.00%", "+100.0"), tk.E),
    ("use", "Use", ("Exclude",), tk.W),
    ("per", "Per Quartz", ("10.00%",), tk.E),
    ("weighted", "Weighted", ("100.00",), tk.E),
)
# Shown with several combatants only.
WEIGHTED_ONLY = ("for", "weighted")
# A cell's text in from its edges, each side.
TEXT_INSET = 4
LIST_ROWS = 30
WEIGHT_ROWS = 30
# The Sets panel's columns, as many as the Memory Fragments tab's.
SET_COLUMNS = 5

# The note beside the filters, by measure.
_KEEPS = ("Readjustment keeps each substat type and starting value, "
          "re-shuffles the 4 upgrades and rerolls their values; you "
          "choose to keep Before or After.\n\n")
_COLUMNS = ("\n\nAvg: Now's average after a Reroll, kept or not.\n"
            "Chance: of a rise.\n"
            "Best: the most it can rise.\n"
            "Use, Per Quartz: the better option per Quartz.")
NOTES = {
    rj.GEAR: _KEEPS + (
        "Gain: the average rise in Gear Score under the combatant's "
        "assigned preset.") + _COLUMNS,
    rj.BUILD: _KEEPS + (
        "Gain: the average rise over the combatant's Top build, the MF "
        "in the best build around it.") + _COLUMNS,
}
LOADING = "Loading..."
NO_BUILD = "The Optimizer finds no build for %s under their settings."
NO_DATA = "No capture loaded: log in with the capture running."
NOBODY = "Give a combatant a weight above 0."
NO_PRESET = "%s has no Gear Score preset: assign one on the Combatants tab."
FAILED = "Could not work it out: %s"
HELD = "%d Shuffling Quartz"
COUNT = "%d MFs"
# The Quartz count's colour by how many readjustments it pays for: the
# palette's, red at none up to green past an exclusion's two.
HELD_COLOURS = ((0, "red"), (1, "orange"), (2, "yellow"))
HELD_PLENTY = "green"

# The progress under the counts (`progress_lines`).
WORKING = "Loading..."
SPEEDS = {rj.BACKGROUND: "(background)", rj.FULL: "(full speed)"}
DONE = "Done"
GROUPS = (("one", "For one:"), ("weighted", "For weighted:"),
          ("all", "For all:"))
OUT_OF = "%d out of %d"
COMPLETE = "Complete %d"
NONE_WEIGHTED = "None weighted"
# For one, with several weighted.
NOT_ONE = "N/A"
NO_PROGRESS = "No data"
# How long the weight spinbox has to hold still before a new reading.
SETTLE_MS = 400

# Between the stacked dropdowns' rows.
DROPDOWN_ROW_GAP = 4   # spacing: TBD -- the Substat Readjustment tab's stacked dropdowns


def _words(pairs, value):
    return next((word for word, v in pairs if v == value), pairs[0][0])


def _value(pairs, word):
    return next((v for w, v in pairs if w == word), pairs[0][1])


def held_colour(count):
    """The palette key the Quartz count is drawn in."""
    for most, colour in HELD_COLOURS:
        if count <= most:
            return colour
    return HELD_PLENTY


def substat_words(fragment):
    """`CDmg 12.4 (+3)  DoT% 3.2`: each substat, its upgrades counted."""
    out = []
    for sub in fragment.substats:
        ups = len(sub.upgrade_values)
        out.append("%s %s%s" % (sub.name, sub.format_value(),
                                " (+%d)" % ups if ups else ""))
    return "  ".join(out)


def figures(measure):
    """(gain, now) formats for `measure`: GS points, or per cent."""
    if measure == rj.BUILD:
        return "+%.2f%%", "%+.2f%%"
    return "+%.1f", "%.1f"


def row_values(reading, measure):
    """The list's cells for one Reading, in `COLUMNS` order."""
    gain, now = figures(measure)
    f = reading.fragment
    plain, exclude, best = reading.plain, reading.exclude, reading.best
    per = best.per_quartz
    return (
        EQUIPMENT_SLOTS.get(f.slot_num, str(f.slot_num)).split()[0],
        f.set_name,
        f.main_stat.name if f.main_stat else "",
        f.equipped_to or "",
        substat_words(f),
        reading.combatant,
        now % reading.now,
        now % plain.avg,
        gain % plain.mean,
        "%d%%" % round(plain.chance * 100),
        exclude.excluded or "",
        gain % exclude.mean,
        "%d%%" % round(exclude.chance * 100),
        gain % max(plain.best, exclude.best),
        "Exclude" if best is exclude else "Reroll",
        (gain % per)[1:],
        "%.2f" % reading.value,
    )


def progress_lines(groups, statuses, speed):
    """The progress under the counts, a line each: Loading... and the
    speed under it, or Done; then, for each group of combatants `groups` names
    (`ReadjustWork.groups`, "one" None with several weighted), its title
    and how many of its readings are in, counted over its combatants'
    `statuses` -- or Complete and how many; For one reads N/A with
    several weighted."""
    lines = []
    for key, title in GROUPS:
        names = groups.get(key)
        if names is None:
            lines += [title, NOT_ONE]
            continue
        got = [statuses[n] for n in names if n in statuses]
        done = sum(s.done for s in got)
        total = sum(s.total for s in got) if len(got) == len(names) \
            else None
        lines.append(title)
        if not names and key == "weighted":
            lines.append(NONE_WEIGHTED)
        elif total is not None and done >= total:
            lines.append(COMPLETE % total)
        else:
            lines.append(OUT_OF % (done, total if total is not None
                                   else done))
    every = groups.get("all") or []
    finished = every and all(n in statuses and statuses[n].complete
                             for n in every)
    return ([DONE] if finished else [WORKING, SPEEDS[speed]]) + lines


# The Before / After panel: a readjustment the game has dealt, read for
# every combatant (`readjust_work.ReadjustWork.set_deal`). Each column's
# figure is per cent of the combatant's Top build.
DEAL_TITLE = "Before / After"
DEAL_COLUMNS = (
    ("name", "Combatant", ("Heidemarie",), tk.W),
    ("weight", "Weight", ("10",), tk.E),
    ("change", "Top Δ", ("+10.00%",), tk.E),
    ("weighted", "Weighted", ("+100.00%",), tk.E),
    ("gap_before", "Gap Before", ("-10.00%",), tk.E),
    ("gap_after", "Gap After", ("-10.00%",), tk.E),
    ("gs_before", "GS Before", ("100.0",), tk.E),
    ("gs_after", "GS After", ("100.0",), tk.E),
    ("in_top", "In Top", ("Before",), tk.W),
)
DEAL_ROWS = 6
NO_DEAL = ("No readjustment waiting. With a capture running, one shows "
           "here as the game deals it, its Before and After read for "
           "every combatant.")
DEAL_WORKING = "Working out Before and After: %d of %d combatants"
# A change smaller than this, in per cent of a Top build, is none.
DEAL_EPS = 0.005

# What each heading means, on hover.
HEAD_TIPS = {
    "now": "The MF's score as it stands. Gear Score: its GS under the "
           "combatant's preset. Build Score: the best build wearing it, "
           "in per cent over the combatant's Top build.",
    "avg": "Now's average after a Reroll, the outcomes worse than Now "
           "included, as if After were always kept.",
    "gain": "A Reroll's average rise: After where it beats Now (or the "
            "Top build), nothing where it does not, since you keep "
            "Before then.",
    "chance": "The chance a Reroll rises at all.",
    "excl": "The substat whose exclusion gains most: it takes no upgrade "
            "and goes back to its starting value.",
    "xgain": "That exclusion's average rise, as Reroll's.",
    "xchance": "The chance that exclusion rises at all.",
    "best": "The most either can rise: every upgrade a top roll on one "
            "substat.",
    "use": "Which option does more per Quartz: Reroll costs 1, Exclude 2.",
    "per": "That option's average rise per Quartz.",
    "for": "The combatant the MF does most for, by Weighted.",
    "weighted": "Per Quartz times the combatant's weight: what the list "
                "is ranked by with several combatants.",
    "change": "How much the combatant's best build changes if you keep "
              "After: 0 where the MF is in neither version of it.",
    "gap_before": "The best build wearing Before, against the Top build: "
                  "how near it is to being worth wearing.",
    "gap_after": "The same for After.",
    "gs_before": "Before's Gear Score under the combatant's preset.",
    "gs_after": "After's Gear Score under the combatant's preset.",
    "in_top": "Which versions the combatant's best build wears.",
}


def deal_verdict(rows, scope, total):
    """The Before / After panel's verdict. `rows` {combatant:
    `read_deal`'s answer} in so far, `scope` {combatant: weight} the
    list is read for, `total` how many combatants there are.

    Keep After where the weighted Top Δ of `scope` comes to more than
    0, Before where to less; where it comes to none, whichever version
    stands closer to their Top builds. A Top Δ outside `scope` is named
    after it."""
    if len(rows) < total:
        return DEAL_WORKING % (len(rows), total)
    read = {n: r for n, r in rows.items() if r is not None}
    mine = {n: (w, read[n]) for n, w in scope.items() if n in read}
    total_change = sum(w * r["change"] for w, r in mine.values())
    if total_change > DEAL_EPS:
        words = "Keep After: " + ", ".join(
            "%+.2f%% for %s" % (r["change"], n)
            for n, (_w, r) in sorted(mine.items(),
                                     key=lambda i: -i[1][1]["change"])
            if r["change"] > DEAL_EPS)
    elif total_change < -DEAL_EPS:
        words = "Keep Before: After costs " + ", ".join(
            "%+.2f%% for %s" % (r["change"], n)
            for n, (_w, r) in sorted(mine.items(),
                                     key=lambda i: i[1][1]["change"])
            if r["change"] < -DEAL_EPS)
    else:
        closer = sum(w * (r["after"] - r["before"]) for w, r in mine.values()
                     if r["after"] is not None and r["before"] is not None)
        if closer > DEAL_EPS:
            words = "Keep After: no Top build changes, and After stands closer to it"
        elif closer < -DEAL_EPS:
            words = "Keep Before: no Top build changes, and After stands further from it"
        else:
            words = "Either: no Top build changes, and neither stands closer"
    elsewhere = sorted(((n, r["change"]) for n, r in read.items()
                        if n not in scope and abs(r["change"]) > DEAL_EPS),
                       key=lambda i: -abs(i[1]))
    if elsewhere:
        words += ". Elsewhere: " + ", ".join(
            "%s %+.2f%%" % (n, c) for n, c in elsewhere[:3])
    return words


def best_readings(fragments, readings, weights):
    """[Reading], best first: each fragment read for the combatant whose
    weighted gain per Quartz is highest. `readings` {combatant: {id:
    (now, plain, exclude)}}, `weights` {combatant: weight}."""
    out = []
    for fragment in fragments:
        best = None
        for name, weight in weights.items():
            got = readings.get(name, {}).get(fragment.id)
            if got is None:
                continue
            now, plain, exclude = got
            reading = rj.Reading(fragment, name, now, plain, exclude,
                                 weight=weight)
            if best is None or reading.value > best.value:
                best = reading
        if best is not None:
            out.append(best)
    out.sort(key=lambda r: (-r.value, r.fragment.id))
    return out


class ReadjustTab(BaseTab):
    """Fully upgraded Legendaries, ranked by what a readjustment of each
    is expected to gain per Shuffling Quartz."""

    def __init__(self, parent, context):
        super().__init__(parent, context)
        # The app's work; a check's build has none, and keeps one of its
        # own that never starts a worker (`ReadjustWork.enabled`).
        self.work = getattr(context, "readjust_work", None) \
            or ReadjustWork(context, self.frame.after)
        self.work.listeners.append(self._show_work)
        self._shown = None
        self._words = None              # see `_draw`
        self._sort = ("weighted", True)
        self._settle = None
        self.slot_vars = {}
        self.set_vars = {}
        self._sets_drawn = None
        self.setup_ui()
        self.refresh_readjust()
        # Every time the tab is shown: a preset or an Optimizer setting
        # changed on another tab is read here, and a tab hidden through
        # a load caught up on.
        self.frame.bind("<Map>", lambda _e: self.refresh_readjust(),
                        add="+")
        self.frame.bind("<Unmap>", lambda _e: self._hidden(), add="+")

    # ------------------------------------------------------------ build

    def setup_ui(self):
        content = ttk.Frame(self.frame)
        top = ttk.Frame(content)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        top.pack(fill=tk.X, padx=(px_after(2, 2), px_after(2, 2)),
                 pady=px((0, 0)))
        settings = self._settings()
        self.measure_var = tk.StringVar(value=_words(
            MEASURES, settings.get(MEASURE_KEY, rj.GEAR)))
        self.mode_var = tk.StringVar(value=_words(
            MODES, settings.get(MODE_KEY, "one")))
        self.combatant_var = tk.StringVar(
            value=settings.get(COMBATANT_KEY, "") or "")
        self.owner_var = tk.StringVar(value=_words(
            OWNERS, settings.get(OWNER_KEY, "all")))

        # The dropdowns stacked, and under them, at the foot of the row,
        # the weight of the combatant picked in the Weights list -- right
        # over that list's title.
        controls = ttk.Frame(top)
        # spacing: tab list -> first element -- tab, dropdown ↕
        controls.pack(side=tk.LEFT, anchor=tk.N, fill=tk.Y,
                      pady=(px_after(1, 5), 0))
        boxes = [
            self._dropdown(controls, 0, "Score:", self.measure_var,
                           [w for w, _v in MEASURES]),
            self._dropdown(controls, 1, "For:", self.mode_var,
                           [w for w, _v in MODES])]
        self.combatant_box = ttk.Combobox(
            controls, textvariable=self.combatant_var, state="readonly",
            width=1)
        # spacing: label ↔ its element -- label, dropdown ↔
        # spacing: TBD -- the Substat Readjustment tab's stacked dropdowns
        self.combatant_box.grid(row=2, column=1, sticky=tk.EW,
                                padx=px((2, 0)),
                                pady=px((DROPDOWN_ROW_GAP, 0)))
        self.combatant_box.bind("<<ComboboxSelected>>",
                                lambda _e: self._changed())
        bind_combobox_nav(self.combatant_box)
        boxes.append(self.combatant_box)
        boxes.append(self._dropdown(controls, 3, "MFs:", self.owner_var,
                                    [w for w, _v in OWNERS]))
        self._size_dropdowns(controls, boxes)
        controls.grid_rowconfigure(4, weight=1)
        self.weight_row = ttk.Frame(controls)
        self.weight_row.grid(row=5, column=0, columnspan=2, sticky=tk.SW)
        self._build_weight_spin(self.weight_row)

        slots_column = self._build_slots(top)
        # At the Slots column's foot, the buttons' bottom on the Sets
        # panel's and their left on the Slots border's: whether the work
        # runs from launch, for every combatant (`readjust_work`), or
        # only while this tab shows, and how fast.
        speed = ttk.Frame(slots_column)
        speed.pack(side=tk.BOTTOM, anchor=tk.W)
        self.background_var = tk.BooleanVar(value=self.work.background())
        # The box's ink on the Slots border's left: no padding, and the
        # focus inset Tk keeps whatever the padding (`FOCUS_INSET`, a
        # fixed pixel) taken back by placing the box that far left in a
        # holder its own size less that pixel.
        holder = ttk.Frame(speed)
        holder.pack(anchor=tk.W)
        self.background_box = make_checkbox(
            holder, self.colors, text="Work in the background",
            variable=self.background_var, command=self._on_background,
            padx=px(0))
        holder.configure(
            width=self.background_box.winfo_reqwidth() - FOCUS_INSET,
            height=self.background_box.winfo_reqheight())
        self.background_box.place(x=-FOCUS_INSET, y=0)
        buttons = ttk.Frame(speed)
        # spacing: checkbox block -> All/None row -- checkbox, button ↕
        buttons.pack(anchor=tk.W, pady=(px(5), 0))
        self.full_button = ttk.Button(buttons, text="Full speed",
                                      command=self._full_speed)
        self.full_button.pack(side=tk.LEFT)
        self.slow_button = ttk.Button(buttons, text="Background",
                                      command=self._background_speed)
        # spacing: button -> button -- button, button ↔
        self.slow_button.pack(side=tk.LEFT, padx=(px(4), 0))

        self._build_sets(top)

        # The counts, stacked at the row's right end.
        status = ttk.Frame(top)
        # spacing: tab list -> first element -- tab, label ↕
        status.pack(side=tk.RIGHT, anchor=tk.N, pady=(px_after(1, 0), 0))
        # The negative padding takes back the label's own 2px inset at
        # each side, which pack's padx cannot: the text ends the
        # window-edge rule's distance in, as the list's box under it
        # does, and starts exactly the note's pad past the note.
        # spacing: content frame -> content frame -- label, frame ↔
        self.held_label = ttk.Label(status, text="",
                                    padding=px((-2, 0, -2, 0)))
        self.held_label.pack(anchor=tk.E)
        self.count_label = ttk.Label(status, text="",
                                     foreground=self.colors["fg_dim"],
                                     padding=px((-2, 0, -2, 0)))
        self.count_label.pack(anchor=tk.E)
        # How far the work has got, for the list and past it.
        self.progress_label = ttk.Label(status, text="", justify=tk.LEFT,
                                        foreground=self.colors["fg_dim"],
                                        padding=px((-2, 0, -2, 0)))
        # spacing: label row -> label row -- label, label ↕
        self.progress_label.pack(anchor=tk.E, pady=(px(6), 0))

        # No inset at the right, and wrapped at its box's edge
        # (`_rewrap`): its trailing pad is then the least distance from
        # its text to the counts', reached by a line that fills the
        # wrap. A line broken short of that stands further off.
        self.note_label = ttk.Label(top, text="", justify=tk.LEFT,
                                    foreground=self.colors["fg_dim"],
                                    padding=px((0, 0, -2, 0)))
        # The note reads as one more panel beside Sets, at the rule's
        # 4 less the label's own 2px inset; the counts are a group of
        # their own past it.
        # spacing: content frame -> content frame -- panel, label ↔
        # spacing: control group ↔ control group -- label, label ↔
        # spacing: tab list -> first element -- tab, label ↕
        self.note_label.pack(side=tk.LEFT, anchor=tk.N, fill=tk.X,
                             expand=True, padx=px((2, 10)),
                             pady=(px_after(1, 0), 0))
        self.note_label.bind("<Configure>", self._rewrap)

        body = ttk.Frame(content)
        body.pack(fill=tk.BOTH, expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.weights_frame = ttk.LabelFrame(
            body, text="Weights", padding=px(0),
            style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- panel, title ↕
        self.weights_frame.grid(row=0, column=0, rowspan=2, sticky="ns",
                                padx=(px_after(2, 2), px(2)),
                                pady=(px_after(2, 7), px(2)))
        self._build_weights(self.weights_frame)

        lists = ttk.LabelFrame(body, text="Memory Fragments", padding=px(0),
                               style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- panel, title ↕
        lists.grid(row=0, column=1, sticky="nsew",
                   padx=(px_after(2, 2), px_after(2, 2)),
                   pady=(px_after(2, 7), px(2)))
        self._build_list(lists)

        deal = ttk.LabelFrame(body, text=DEAL_TITLE, padding=px(0),
                              style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- panel, title ↕
        deal.grid(row=1, column=1, sticky="nsew",
                  padx=(px_after(2, 2), px_after(2, 2)),
                  pady=(px_after(2, 5), px_after(2, 2)))
        self._build_deal(deal)
        self._tips = Tooltip(self.colors)
        for tree in (self.tree, self.deal_tree):
            tree.bind("<Motion>", lambda e, t=tree: self._head_tip(t, e),
                      add="+")
            tree.bind("<Leave>", lambda _e: self._tips.hide(), add="+")
        self._tip_at = None

        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        content.pack(fill=tk.BOTH, expand=True, padx=px(2),
                     pady=px((1, 2)))
        self._show_mode()

    def _dropdown(self, parent, row, words, var, values):
        ttk.Label(parent, text=words).grid(row=row, column=0, sticky=tk.W)
        box = ttk.Combobox(parent, textvariable=var, state="readonly",
                           values=values,
                           width=max(len(v) for v in values) + 1)
        # spacing: label ↔ its element -- label, dropdown ↔
        # spacing: TBD -- the Substat Readjustment tab's stacked dropdowns
        box.grid(row=row, column=1, sticky=tk.EW, padx=px((2, 0)),
                 pady=px((DROPDOWN_ROW_GAP if row else 0, 0)))
        box.bind("<<ComboboxSelected>>", lambda _e: self._changed())
        bind_combobox_nav(box)
        return box

    @staticmethod
    def _size_dropdowns(parent, boxes):
        """Every dropdown as wide as the widest option shows whole, to the
        pixel: that option's text ends at the field's inner padding.

        A Combobox's `width` counts characters of the font's `0`, so its
        text area is a whole number of those; the column's minimum size
        sets the pixel instead, and each box fills the column. What the
        box adds around its text -- border, padding, arrow -- is read off
        one box's request, which is its characters' width and that."""
        from tkinter import font as tkfont
        box = boxes[0]
        spec = str(box.cget("font")) or ttk.Style().lookup(
            "TCombobox", "font") or "TkTextFont"
        font = tkfont.Font(font=spec)
        chars = int(str(box.cget("width")))
        extra = box.winfo_reqwidth() - chars * font.measure("0")
        widest = max(font.measure(word) for word, _v
                     in MEASURES + MODES + OWNERS)
        for each in boxes:
            each.configure(width=1)
        # Measured, so no `px()` on the text or the box's own parts; the
        # box's pad is a distance and takes it.
        # spacing: label ↔ its element -- label, dropdown ↔
        parent.grid_columnconfigure(1, minsize=widest + extra + px(2))

    def _build_slots(self, parent):
        """The Slots panel, atop a column as tall as the row: the
        column, for what stands at its foot."""
        column = ttk.Frame(parent)
        # spacing: content frame -> content frame -- dropdown, panel ↔
        # spacing: tab list -> first element -- tab, title ↕
        column.pack(side=tk.LEFT, fill=tk.Y, padx=px((4, 2)),
                    pady=(px_after(1, 2), 0))
        # spacing: border edge -> first non-button element -- panel, checkbox ↔↕
        frame = ttk.LabelFrame(column, text="Slots",
                               padding=px((0, 2, 0, 3)))
        frame.pack(side=tk.TOP, anchor=tk.W)
        inner = ttk.Frame(frame)
        inner.pack()
        # Left column 3, 2, 1 top to bottom; right 4, 5, 6: the Memory
        # Fragments tab's order.
        for row, pair in enumerate(((3, 4), (2, 5), (1, 6))):
            for col, slot in enumerate(pair):
                var = tk.BooleanVar(value=True)
                self.slot_vars[slot] = var
                # spacing: element and its label ↔ element and its label -- checkbox, checkbox ↔
                # spacing: checkbox/slider ↕ checkbox/slider rows -- checkbox, checkbox ↕
                make_checkbox(inner, self.colors,
                              text=EQUIPMENT_SLOTS[slot], variable=var,
                              command=self._filtered).grid(
                    row=row, column=col, sticky=tk.W, padx=px(2),
                    pady=px((0 if row == 0 else 3, 0)))
        make_all_none_row(frame, lambda: self._all(self.slot_vars, True),
                          lambda: self._all(self.slot_vars, False))
        return column

    def _build_sets(self, parent):
        # spacing: border edge -> first non-button element -- panel, checkbox ↔↕
        frame = ttk.LabelFrame(parent, text="Sets",
                               padding=px((0, 2, 0, 3)))
        # spacing: content frame -> content frame -- panel, panel ↔
        # spacing: tab list -> first element -- tab, title ↕
        frame.pack(side=tk.LEFT, anchor=tk.N, padx=px((2, 0)),
                   pady=(px_after(1, 2), 0))
        self.sets_inner = ttk.Frame(frame)
        self.sets_inner.pack()
        make_all_none_row(frame, lambda: self._all(self.set_vars, True),
                          lambda: self._all(self.set_vars, False))

    def _fill_sets(self, fragments):
        """Every set a name is known for, 4-piece first then 2-piece,
        alphabetical within each, as the Memory Fragments tab lists
        them, each with how many fragments are listed for it. Rebuilt
        only when a name or a count changes; the ticks survive it."""
        counts = {}
        for fragment in fragments:
            counts[fragment.set_name] = counts.get(fragment.set_name, 0) + 1
        pieces = {set_name_of(sid): set_pieces(sid) for sid in named_sets()}
        names = sorted(pieces, key=lambda n: (-(pieces[n] or 0), n.lower()))
        names += sorted(n for n in counts if n not in pieces)
        drawn = tuple((n, counts.get(n, 0)) for n in names)
        if drawn == self._sets_drawn:
            return
        self._sets_drawn = drawn
        ticked = {n: v.get() for n, v in self.set_vars.items()}
        for widget in self.sets_inner.winfo_children():
            widget.destroy()
        self.set_vars.clear()
        four = [n for n in names if pieces.get(n) == 4]
        rest = [n for n in names if pieces.get(n) != 4]
        rows = (len(four) + SET_COLUMNS - 1) // SET_COLUMNS
        cells = [(n, i // SET_COLUMNS, i % SET_COLUMNS, 0 if i < SET_COLUMNS
                  else 3) for i, n in enumerate(four)]
        # The 2-piece sets start a row of their own, a small division
        # above their first, as on the Memory Fragments tab.
        cells += [(n, rows + j // SET_COLUMNS, j % SET_COLUMNS,
                   9 if j < SET_COLUMNS else 3) for j, n in enumerate(rest)]
        for name, row, col, top in cells:
            var = tk.BooleanVar(value=ticked.get(name, True))
            self.set_vars[name] = var
            elements = (SETS.get(set_named(name)) or {}).get("elements") \
                or []
            colour = ATTRIBUTE_COLORS.get(elements[0] if elements else None,
                                          self.colors["fg"])
            # The first column's leading pad and the last's trailing one
            # are the panel's insets, with the checkbox's own; between
            # columns, the leading pad and both insets.
            # spacing: border edge -> first non-button element -- panel, checkbox ↔
            # spacing: checkbox row -> checkbox row (small division) -- checkbox, checkbox ↕
            make_checkbox(self.sets_inner, self.colors,
                          text="%s (%d)" % (name, counts.get(name, 0)),
                          variable=var, command=self._filtered,
                          fg=colour).grid(
                row=row, column=col, sticky=tk.W,
                padx=px((2 if col == 0 else 3,
                         2 if col == SET_COLUMNS - 1 else 0)),
                pady=px((top, 0)))

    def _measured(self, tree, columns, sort=None):
        """Each column as wide as its heading or widest sample, in the
        list's own fonts -- measured, so the fonts carry the scale and
        only the inset takes `px`. None stretches: a stretched column
        keeps its width when the Weights list takes room beside it, and
        pushes the columns after it out of view. A heading's click calls
        `sort` with its column, `_sort_by` by default."""
        sort = sort or self._sort_by
        from tkinter import font as tkfont
        cell = tkfont.nametofont("TkDefaultFont")
        head = tkfont.nametofont("TkHeadingFont")
        for col, title, samples, anchor in columns:
            width = max([head.measure(title)]
                        + [cell.measure(s) for s in samples]) \
                + px(2 * TEXT_INSET)
            tree.heading(col, text=title, anchor=anchor,
                         command=lambda c=col: sort(c))
            tree.column(col, width=width, minwidth=width, anchor=anchor,
                        stretch=False)

    def _build_list(self, parent):
        ids = [c[0] for c in COLUMNS]
        self.tree = ttk.Treeview(parent, columns=ids, show="headings",
                                 height=LIST_ROWS, selectmode="browse")
        self._measured(self.tree, COLUMNS)
        bar = ttk.Scrollbar(parent, orient=tk.VERTICAL,
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        # The scrollbar first (`docs/ui_runtime.md`): a list packed
        # before it takes its room wherever it is too wide.
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _build_deal(self, parent):
        """The verdict and the two versions' substats over a list of
        every combatant's reading of the deal."""
        # The negative top padding takes back what the borderless panel
        # leaves under its title, which pack's pady cannot.
        # spacing: title above, element below -- title, label ↕
        self.deal_label = ttk.Label(parent, text=NO_DEAL, justify=tk.LEFT,
                                    padding=px((-2, -5, -2, 0)))
        self.deal_label.pack(anchor=tk.W, pady=(0, px(5)))
        holder = ttk.Frame(parent)
        holder.pack(fill=tk.BOTH, expand=True)
        self.deal_tree = ttk.Treeview(
            holder, columns=[c[0] for c in DEAL_COLUMNS], show="headings",
            height=DEAL_ROWS, selectmode="none")
        self._measured(self.deal_tree, DEAL_COLUMNS, sort=lambda _c: None)
        bar = ttk.Scrollbar(holder, orient=tk.VERTICAL,
                            command=self.deal_tree.yview)
        self.deal_tree.configure(yscrollcommand=bar.set)
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        self.deal_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._deal_gs = (None, {})

    def _head_tip(self, tree, event):
        """The meaning of the heading under the pointer, after the
        tooltip's delay. A heading is not a widget, so the column under
        the pointer drives the tip (as on the Memory Fragments tab)."""
        if tree.identify_region(event.x, event.y) != "heading":
            if self._tip_at is not None:
                self._tips.hide()
                self._tip_at = None
            return
        column = tree.identify_column(event.x)
        if (tree, column) == self._tip_at:
            return
        self._tip_at = (tree, column)
        self._tips.hide()
        try:
            shown = list(tree["displaycolumns"])
            if shown in (["#all"], ("#all",)):
                shown = list(tree["columns"])
            col = shown[int(column[1:]) - 1]
        except (ValueError, IndexError):
            return
        text = HEAD_TIPS.get(col)
        if text:
            self._tips.schedule(tree, text)

    def _gs_of(self, name, versions):
        """(Before's, After's) Gear Score under `name`'s preset, kept
        for the deal in hand."""
        from optimizer.run_settings import weights_for
        token = self.work.deal["token"]
        held_token, held = self._deal_gs
        if held_token != token:
            held = {}
            self._deal_gs = (token, held)
        if name not in held:
            valuer = rj.GearValuer(weights_for(
                getattr(self.context, "character_preset_manager", None),
                getattr(self.context, "preset_manager", None), name) or {})
            held[name] = tuple(valuer.bind(v).reference(v)[0]
                               for v in versions)
        return held[name]

    def _show_deal(self):
        """The Before / After panel from the work's reading of the deal
        in hand, its rows by how much they change, the largest first."""
        work = self.work
        tree = self.deal_tree
        tree.delete(*tree.get_children())
        deal = work.deal
        if deal is None:
            self.deal_label.configure(text=NO_DEAL)
            return
        weights = work.weights()
        versions = (deal["before"], deal["after"])
        rows = [(n, r) for n, r in work.deal_rows.items() if r is not None]

        def gap(r):
            if r["before"] is None or r["after"] is None:
                return 0.0
            return r["after"] - r["before"]

        rows.sort(key=lambda i: (-abs(i[1]["change"]), -gap(i[1]), i[0]))
        for name, r in rows:
            weight = weights.get(name, 0)
            gs = self._gs_of(name, versions)
            tree.insert("", tk.END, values=(
                name, weight, "%+.2f%%" % r["change"],
                "%+.2f%%" % (r["change"] * weight),
                "" if r["before"] is None else "%+.2f%%" % r["before"],
                "" if r["after"] is None else "%+.2f%%" % r["after"],
                "%.1f" % gs[0], "%.1f" % gs[1], r["in_top"]))
        self.deal_label.configure(text="\n".join((
            deal_verdict(work.deal_rows, self._combatants(),
                         len(work.names())),
            "Before:  " + substat_words(deal["before"]),
            "After:   " + substat_words(deal["after"]))))

    def _build_weights(self, parent):
        holder = ttk.Frame(parent)
        holder.pack(fill=tk.BOTH, expand=True)
        columns = (("name", "Combatant", ("Heidemarie",), tk.W),
                   ("weight", "Weight", ("10",), tk.E))
        self.weight_tree = ttk.Treeview(
            holder, columns=[c[0] for c in columns], show="headings",
            height=WEIGHT_ROWS, selectmode="extended")
        self._measured(self.weight_tree, columns, sort=self._sort_weights)
        bar = ttk.Scrollbar(holder, orient=tk.VERTICAL,
                            command=self.weight_tree.yview)
        self.weight_tree.configure(yscrollcommand=bar.set)
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        self.weight_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.weight_tree.tag_configure(
            "off", foreground=self.colors["fg_dim"])
        self.weight_tree.bind("<<TreeviewSelect>>", self._on_pick_weight)

    def _build_weight_spin(self, row):
        """`Set weight:` and its spinbox, for the combatant picked in the
        Weights list. Shown with that list only (`_show_mode`)."""
        ttk.Label(row, text="Set weight:").pack(side=tk.LEFT)
        self.weight_var = tk.IntVar(value=0)
        self.weight_spin = tk.Spinbox(
            row, from_=0, to=WEIGHT_MAX, increment=1, width=4,
            textvariable=self.weight_var,
            bg=self.colors["bg_light"], fg=self.colors["fg"],
            buttonbackground=self.colors["bg_lighter"],
            insertbackground=self.colors["fg"],
            selectbackground=self.colors["select"],
            selectforeground=self.colors["fg"],
            relief=tk.FLAT, bd=px(1),
            command=self._on_weight)
        # spacing: label ↔ its element -- label, spinbox ↔
        self.weight_spin.pack(side=tk.LEFT, padx=px((5, 0)))
        # A tk.Spinbox's from_/to bound its buttons and its wheel, never
        # its text: without this a typed 99 reaches the weights.
        clamp_on_commit(self.weight_spin, self.weight_var, self.colors,
                        self.root)
        step_on_wheel(self.weight_spin)
        self.weight_spin.bind("<Return>", lambda _e: self._on_weight(),
                              add="+")
        self.weight_spin.bind("<FocusOut>", lambda _e: self._on_weight(),
                              add="+")

    def _rewrap(self, event):
        """The note wrapped to the width its row leaves it. Only a
        change is written: a new wraplength moves the label's requested
        width, and a handler writing every time can bounce the row."""
        # Less the label's own inset at the left; the right one is
        # taken back (`setup_ui`), so a full line ends at the box's edge.
        width = max(px(200), event.width - px(2))
        try:
            if int(str(self.note_label.cget("wraplength"))) == width:
                return
        except (ValueError, tk.TclError):
            pass
        self.note_label.configure(wraplength=width)

    # --------------------------------------------------------- settings

    def _settings(self):
        manager = getattr(self.context, "settings_manager", None)
        if manager is None:
            return {}
        return {key: manager.get(key) for key in (
            MEASURE_KEY, MODE_KEY, COMBATANT_KEY, WEIGHTS_KEY, OWNER_KEY)
            if manager.get(key) is not None}

    def _save(self, key, value):
        manager = getattr(self.context, "settings_manager", None)
        if manager is not None:
            manager.set(key, value)

    def _weights(self):
        manager = getattr(self.context, "settings_manager", None)
        stored = manager.get(WEIGHTS_KEY) if manager is not None else None
        return dict(stored) if isinstance(stored, dict) else {}

    def measure(self):
        return _value(MEASURES, self.measure_var.get())

    def mode(self):
        return _value(MODES, self.mode_var.get())

    # ----------------------------------------------------------- events

    def _changed(self):
        self._save(MEASURE_KEY, self.measure())
        self._save(MODE_KEY, self.mode())
        self._save(COMBATANT_KEY, self.combatant_var.get())
        self._save(OWNER_KEY, _value(OWNERS, self.owner_var.get()))
        self._show_mode()
        self.refresh_readjust()

    def _filtered(self):
        """A Slot or a Set ticked: the same answers, drawn again."""
        self._show_work()

    def _on_background(self):
        self._save(BACKGROUND_KEY, bool(self.background_var.get()))
        self.work.refresh()

    def _full_speed(self):
        self.work.full_speed()

    def _background_speed(self):
        self.work.background_speed()

    def _hidden(self):
        self.work.visible = False

    def _all(self, variables, value):
        for var in variables.values():
            var.set(value)
        self._filtered()

    def _show_mode(self):
        weighted = self.mode() == "weighted"
        if weighted:
            self.weights_frame.grid()
            self.weight_row.grid()
            self.combatant_box.grid_remove()
        else:
            self.weights_frame.grid_remove()
            self.weight_row.grid_remove()
            self.combatant_box.grid()
        shown = [c[0] for c in COLUMNS
                 if weighted or c[0] not in WEIGHTED_ONLY]
        self.tree.configure(displaycolumns=shown)
        self.note_label.configure(text=NOTES[self.measure()])

    def _on_pick_weight(self, _event=None):
        """The spinbox shows the weight of the row last clicked, of
        those picked (Shift and Ctrl pick several)."""
        tree = self.weight_tree
        picked = tree.selection()
        if picked:
            shown = tree.focus() if tree.focus() in picked else picked[0]
            self.weight_var.set(self._weights().get(shown, 0))

    def _on_weight(self):
        """The spinbox's weight given to every combatant picked."""
        picked = self.weight_tree.selection()
        if not picked:
            return
        try:
            weight = max(0, min(WEIGHT_MAX, int(self.weight_var.get())))
        except (tk.TclError, ValueError):
            return
        weights = self._weights()
        if all(weights.get(name, 0) == weight for name in picked):
            return
        for name in picked:
            if weight:
                weights[name] = weight
            else:
                weights.pop(name, None)
        self._save(WEIGHTS_KEY, weights)
        self._fill_weights()
        if self._settle is not None:
            self.frame.after_cancel(self._settle)
        self._settle = self.frame.after(SETTLE_MS, self.refresh_readjust)

    def _sort_by(self, column):
        key, down = self._sort
        self._sort = (column, not down if key == column else True)
        self._draw(self._shown)

    # ------------------------------------------------------------- data

    def _names(self):
        optimizer = self.optimizer
        if optimizer is None:
            return []
        return sorted(set(optimizer.characters)
                      | set(optimizer.character_info))

    def _weights_sort(self):
        """(column, descending) the Weights list is sorted by, as kept."""
        manager = getattr(self.context, "settings_manager", None)
        kept = manager.get(WEIGHTS_SORT_KEY) if manager is not None else None
        if isinstance(kept, list) and len(kept) == 2 \
                and kept[0] in ("name", "weight"):
            return kept[0], bool(kept[1])
        return "name", False

    def _sort_weights(self, column):
        """A heading clicked: that column, the other way round where it
        is the column already; a new one starts heaviest or A first."""
        key, down = self._weights_sort()
        down = not down if key == column else column == "weight"
        self._save(WEIGHTS_SORT_KEY, [column, down])
        self._fill_weights()

    def _fill_weights(self):
        weights = self._weights()
        tree = self.weight_tree
        picked, focus = tree.selection(), tree.focus()
        tree.delete(*tree.get_children())
        key, down = self._weights_sort()
        names = sorted(self._names(), key=str.lower)
        if key == "weight":
            # Ties by name, A first whichever way the weights run.
            names.sort(key=lambda n: weights.get(n, 0), reverse=down)
        elif down:
            names.reverse()
        for name in names:
            weight = weights.get(name, 0)
            tree.insert("", tk.END, iid=name, values=(name, weight),
                        tags=() if weight else ("off",))
        kept = [name for name in picked if tree.exists(name)]
        if kept:
            tree.selection_set(kept)
        # The focus is the row a Shift-click picks a range from, and the
        # one the spinbox shows; a refill clears it.
        if focus and tree.exists(focus):
            tree.focus(focus)

    def _combatants(self):
        """{combatant: weight} the list is read for."""
        if self.mode() == "weighted":
            return self.work.weights()
        name = self.work.chosen()
        return {name: 1.0} if name else {}

    def _readjustable(self):
        optimizer = self.optimizer
        return sorted((f for f in optimizer.fragments if rj.readjustable(f)),
                      key=lambda f: f.id)

    def refresh_readjust(self):
        """Read the controls and the loaded data again and have the work
        plan with them; it tells `_show_work` what it has."""
        self._settle = None
        names = self._names()
        self.combatant_box.configure(values=names)
        if names and self.combatant_var.get() not in names:
            self.combatant_var.set(names[0])
        self._fill_weights()
        self._show_mode()
        self.work.visible = bool(self.frame.winfo_ismapped())
        self.work.refresh()

    def _show_work(self):
        """Draw what the work has: the list once every combatant it is
        read for is worked out, and the progress under the counts.
        Drawn only while the tab shows; `<Map>` catches it up."""
        if not self.frame.winfo_ismapped():
            return
        self._show_deal()
        optimizer = self.optimizer
        if optimizer is None or not optimizer.fragments:
            # Every set at 0: the panel keeps the height it has with
            # data, which the list's title is set under.
            self._fill_sets([])
            self._show_status(None)
            self.progress_label.configure(text=NO_PROGRESS)
            self.full_button.state(["disabled"])
            self.slow_button.state(["disabled"])
            self._draw([], NO_DATA)
            return
        fragments = self._readjustable()
        self._fill_sets(fragments)
        self._show_progress()
        work = self.work
        if work.error is not None:
            error, work.error = work.error, None
            self._show_status(None)
            self._draw([], FAILED % error)
            return
        combatants = self._combatants()
        if not combatants:
            self._show_status(None)
            self._draw([], NOBODY)
            return
        statuses = {n: work.statuses.get(n) for n in combatants}
        if any(s is None or not s.complete for s in statuses.values()):
            self._show_status(None)
            self._draw(None, LOADING)
            return
        readable = {n: s for n, s in statuses.items() if s.reason is None}
        if not readable:
            self._show_status(None)
            words = NO_PRESET if self.measure() == rj.GEAR else NO_BUILD
            self._draw([], words % ", ".join(sorted(statuses)))
            return
        shown = best_readings(self._passing(fragments),
                              {n: s.readings for n, s in readable.items()},
                              {n: combatants[n] for n in readable})
        self._draw(shown)
        self._show_status(len(shown))

    def _show_progress(self):
        work = self.work
        self.progress_label.configure(text="\n".join(progress_lines(
            work.groups(), work.statuses, work.speed)))
        # Speed means nothing once all is in, or without the background.
        idle = all(s.complete for s in work.statuses.values()) \
            or not work.background()
        for button, speed in ((self.full_button, rj.FULL),
                              (self.slow_button, rj.BACKGROUND)):
            button.state(["disabled"] if idle or work.speed == speed
                         else ["!disabled"])


    def _passing(self, fragments):
        """The fragments the Slots, Sets and MFs filters let
        through."""
        owner = _value(OWNERS, self.owner_var.get())
        theirs = set(self._combatants())
        out = []
        for f in fragments:
            if not self.slot_vars.get(f.slot_num, tk.BooleanVar(
                    value=True)).get():
                continue
            var = self.set_vars.get(f.set_name)
            if var is not None and not var.get():
                continue
            if owner == "unequipped" and f.equipped_to:
                continue
            if owner == "theirs" and f.equipped_to not in theirs:
                continue
            out.append(f)
        return out

    def _show_status(self, count):
        held = item_amounts.held(getattr(self.optimizer, "raw_data", None)
                                 ).get(rj.QUARTZ, 0) or 0
        self.held_label.configure(text=HELD % held,
                                  foreground=self.colors[held_colour(held)])
        self.count_label.configure(
            text=COUNT % count if count is not None else "")

    def _draw(self, readings, words=None):
        """Fill the list: `readings`, sorted as its heading says, or
        one row saying `words` -- `Loading...` while the workers are
        busy, else why there is nothing. None keeps what is drawn
        behind the words."""
        tree = self.tree
        if words is not None:
            if readings is not None:
                self._shown = readings
            self.count_label.configure(text="")
            # Written once: the poll asks again every few hundredths of
            # a second while the workers are busy.
            if self._words == words:
                return
            self._words = words
            tree.delete(*tree.get_children())
            cells = [""] * len(COLUMNS)
            # In the widest column, which shows the words whole.
            cells[[c[0] for c in COLUMNS].index("subs")] = words
            tree.insert("", tk.END, values=cells)
            return
        self._words = None
        tree.delete(*tree.get_children())
        self._shown = readings
        measure = self.measure()
        key, down = self._sort
        ids = [c[0] for c in COLUMNS]
        rows = [(reading, row_values(reading, measure))
                for reading in readings or []]
        numbers = {
            "weighted": lambda r: r.value,
            "per": lambda r: r.best.per_quartz,
            "now": lambda r: r.now, "avg": lambda r: r.plain.avg,
            "gain": lambda r: r.plain.mean,
            "chance": lambda r: r.plain.chance,
            "xgain": lambda r: r.exclude.mean,
            "xchance": lambda r: r.exclude.chance,
            "best": lambda r: max(r.plain.best, r.exclude.best)}
        if key in numbers:
            rows.sort(key=lambda r: numbers[key](r[0]), reverse=down)
        else:
            at = ids.index(key)
            rows.sort(key=lambda r: str(r[1][at]), reverse=not down)
        for _reading, values in rows:
            tree.insert("", tk.END, values=values)
