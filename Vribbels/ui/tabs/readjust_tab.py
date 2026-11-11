"""The Substat Readjustment tab: which fully upgraded Legendary Memory
Fragments a Shuffling Quartz does most for.

A readjustment deals a fragment's upgrades out again and the player
keeps Before or After, so it can only gain; `readjust` works out what
it is expected to, plainly (1 Quartz) and with the best substat
excluded (2 Quartz), and the list ranks every fragment by the better
of the two per Quartz.

**Score** picks the measure: Gear Score, under the combatant's assigned
preset, or Build Score, the Optimizer's score of the combatant's
equipped build with the fragment in its slot. **For** picks whose: one
combatant, or several, each weighted, every fragment read for the one
whose weighted gain is highest. **Slots**, **Sets** and **Fragments**
narrow the list without working anything out again.

**The work runs in worker processes** (`readjust.submit`), a job a
chunk of fragments for one combatant and measure, and every answer is
kept until the data or that combatant's preset or settings change: a
measure or a combatant gone back to draws at once, and one still being
worked out shows `Loading...` meanwhile, the window free to use. A
change of mind drops the jobs not started yet. `docs/readjust.md` has
the model.
"""

import json
import tkinter as tk
from tkinter import ttk

import item_amounts
import readjust as rj
from game_data import EQUIPMENT_SLOTS, SETS
from game_data.characters import ATTRIBUTE_COLORS
from game_data.sets import named_sets, set_named, set_pieces
from game_data.sets import set_name as set_name_of

from ..base_tab import BaseTab
from ..scaling import px, px_after
from ..utils.all_none_row import make_all_none_row
from ..utils.checkbox import make_checkbox
from ..utils.combobox_nav import bind_combobox_nav
from ..utils.spinbox_clamp import clamp_on_commit, step_on_wheel

# The dropdowns' words, each beside what it stands for.
MEASURES = (("Gear Score", rj.GEAR), ("Build Score", rj.BUILD))
MODES = (("One combatant", "one"), ("Several, weighted", "weighted"))
OWNERS = (("All", "all"), ("Worn by them", "theirs"),
          ("Unequipped", "unequipped"))

# The settings each control is kept under (`settings_manager.LAYOUT`).
MEASURE_KEY = "readjust_measure"
MODE_KEY = "readjust_mode"
COMBATANT_KEY = "readjust_combatant"
WEIGHTS_KEY = "readjust_weights"
OWNER_KEY = "readjust_owner"

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
# The Sets panel's columns: one fewer than the Memory Fragments tab's,
# which leaves the note beside it room to read.
SET_COLUMNS = 4

# The note beside the filters, by measure.
_KEEPS = ("Readjustment keeps each substat's starting value and performs "
          "its 4 upgrades again; you keep Before or After, so it only "
          "gains. Reroll costs 1 Quartz, Exclude 2. ")
NOTES = {
    rj.GEAR: _KEEPS + (
        "Gain: the expected rise in Gear Score under the combatant's "
        "preset. Chance: of any rise. Best: the most it can rise. Use and "
        "Per Quartz: the option with the larger gain per Quartz."),
    rj.BUILD: _KEEPS + (
        "Gain: the expected rise in the Optimizer's score of the "
        "combatant's equipped build with this fragment in its slot, over "
        "Now (that build with the fragment as it stands) or the build as "
        "worn, whichever is higher. The top %d are sampled off the real "
        "score. Use and Per Quartz: the option with the larger gain per "
        "Quartz." % rj.REFINE_TOP),
}
LOADING = "Loading..."
NO_DATA = "No capture loaded: log in with the capture running."
NOBODY = "Give a combatant a weight above 0."
NO_PRESET = "%s has no Gear Score preset: assign one on the Combatants tab."
FAILED = "Could not work it out: %s"
HELD = "%d Shuffling Quartz"
COUNT = "%d Memory Fragments"
# The Quartz count's colour by how many readjustments it pays for: the
# palette's, red at none up to green past an exclusion's two.
HELD_COLOURS = ((0, "red"), (1, "orange"), (2, "yellow"))
HELD_PLENTY = "green"

# A job's fragments, and a refinement's: small enough that a change of
# mind waits on little.
CHUNK = 40
REFINE_CHUNK = 5
POLL_MS = 50
# How long the weight spinbox has to hold still before a new reading.
SETTLE_MS = 400
# Answers kept past this many are dropped, the ones not on show first.
KEEP_PARTS = 400

# Between the stacked dropdowns' rows.
DROPDOWN_ROW_GAP = 3   # spacing: TBD -- the Substat Readjustment tab's stacked dropdowns


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


def best_readings(fragments, readings, weights):
    """[Reading], best first: each fragment read for the combatant whose
    weighted gain per Quartz is highest. `readings` {combatant: {id:
    (now, plain, exclude, sampled)}}, `weights` {combatant: weight}."""
    out = []
    for fragment in fragments:
        best = None
        for name, weight in weights.items():
            got = readings.get(name, {}).get(fragment.id)
            if got is None:
                continue
            now, plain, exclude, sampled = got
            reading = rj.Reading(fragment, name, now, plain, exclude,
                                 sampled=sampled, weight=weight)
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
        # {part key: {id: (now, plain, exclude, sampled)}}: every answer
        # a worker has given, and {part key: Future} for those still
        # being worked out. See `_needed`.
        self._parts = {}
        self._futures = {}
        # {signature: build_inputs}, resolved once a combatant.
        self._inputs = {}
        self._token = None
        self._polling = False
        self._error = None
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

        controls = ttk.Frame(top)
        # spacing: tab list -> first element -- tab, dropdown ↕
        controls.pack(side=tk.LEFT, anchor=tk.N,
                      pady=(px_after(1, 5), 0))
        self._dropdown(controls, 0, "Score:", self.measure_var,
                       [w for w, _v in MEASURES])
        self._dropdown(controls, 1, "For:", self.mode_var,
                       [w for w, _v in MODES])
        self.combatant_box = ttk.Combobox(
            controls, textvariable=self.combatant_var, state="readonly",
            width=max(len(w) for w, _v in MODES) + 1)
        # spacing: label ↔ its element -- label, dropdown ↔
        # spacing: TBD -- the Substat Readjustment tab's stacked dropdowns
        self.combatant_box.grid(row=2, column=1, sticky=tk.W,
                                padx=px((2, 0)),
                                pady=px((DROPDOWN_ROW_GAP, 0)))
        self.combatant_box.bind("<<ComboboxSelected>>",
                                lambda _e: self._changed())
        bind_combobox_nav(self.combatant_box)
        self._dropdown(controls, 3, "Fragments:", self.owner_var,
                       [w for w, _v in OWNERS])

        self._build_slots(top)
        self._build_sets(top)

        # The counts, stacked at the row's right end.
        status = ttk.Frame(top)
        # spacing: tab list -> first element -- tab, label ↕
        status.pack(side=tk.RIGHT, anchor=tk.N, pady=(px_after(1, 3), 0))
        self.held_label = ttk.Label(status, text="")
        self.held_label.pack(anchor=tk.E)
        self.count_label = ttk.Label(status, text="",
                                     foreground=self.colors["fg_dim"])
        self.count_label.pack(anchor=tk.E)

        self.note_label = ttk.Label(top, text="", justify=tk.LEFT,
                                    foreground=self.colors["fg_dim"])
        # spacing: control group ↔ control group -- panel, label ↔
        # spacing: tab list -> first element -- tab, label ↕
        self.note_label.pack(side=tk.LEFT, anchor=tk.N, fill=tk.X,
                             expand=True, padx=px((14, 14)),
                             pady=(px_after(1, 3), 0))
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
        self.weights_frame.grid(row=0, column=0, sticky="ns",
                                padx=(px_after(2, 2), px(2)),
                                pady=(px_after(2, 7), px(2)))
        self._build_weights(self.weights_frame)

        lists = ttk.LabelFrame(body, text="Fragments", padding=px(0),
                               style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- panel, title ↕
        lists.grid(row=0, column=1, sticky="nsew",
                   padx=(px_after(2, 2), px_after(2, 2)),
                   pady=(px_after(2, 7), px_after(2, 2)))
        self._build_list(lists)

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
        box.grid(row=row, column=1, sticky=tk.W, padx=px((2, 0)),
                 pady=px((DROPDOWN_ROW_GAP if row else 0, 0)))
        box.bind("<<ComboboxSelected>>", lambda _e: self._changed())
        bind_combobox_nav(box)
        return box

    def _build_slots(self, parent):
        # spacing: border edge -> first non-button element -- panel, checkbox ↔↕
        frame = ttk.LabelFrame(parent, text="Slots",
                               padding=px((0, 2, 0, 3)))
        # spacing: control group ↔ control group -- dropdown, panel ↔
        frame.pack(side=tk.LEFT, anchor=tk.N, padx=px((16, 2)))
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

    def _build_sets(self, parent):
        # spacing: border edge -> first non-button element -- panel, checkbox ↔↕
        frame = ttk.LabelFrame(parent, text="Sets",
                               padding=px((0, 2, 0, 3)))
        # spacing: content frame -> content frame -- panel, panel ↔
        frame.pack(side=tk.LEFT, anchor=tk.N, padx=px((2, 0)))
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
            # spacing: border edge -> first non-button element -- panel, checkbox ↔
            # spacing: checkbox row -> checkbox row (small division) -- checkbox, checkbox ↕
            make_checkbox(self.sets_inner, self.colors,
                          text="%s (%d)" % (name, counts.get(name, 0)),
                          variable=var, command=self._filtered,
                          fg=colour).grid(
                row=row, column=col, sticky=tk.W, padx=px((3, 0)),
                pady=px((top, 0)))

    def _measured(self, tree, columns, sortable=True):
        """Each column as wide as its heading or widest sample, in the
        list's own fonts -- measured, so the fonts carry the scale and
        only the inset takes `px`. None stretches: a stretched column
        keeps its width when the Weights list takes room beside it, and
        pushes the columns after it out of view."""
        from tkinter import font as tkfont
        cell = tkfont.nametofont("TkDefaultFont")
        head = tkfont.nametofont("TkHeadingFont")
        for col, title, samples, anchor in columns:
            width = max([head.measure(title)]
                        + [cell.measure(s) for s in samples]) \
                + px(2 * TEXT_INSET)
            tree.heading(col, text=title, anchor=anchor,
                         command=(lambda c=col: self._sort_by(c))
                         if sortable else "")
            tree.column(col, width=width, minwidth=width, anchor=anchor,
                        stretch=False)

    def _build_list(self, parent):
        ids = [c[0] for c in COLUMNS]
        self.tree = ttk.Treeview(parent, columns=ids, show="headings",
                                 height=LIST_ROWS, selectmode="browse")
        self._measured(self.tree, COLUMNS)
        bar = ttk.Scrollbar(parent, orient=tk.VERTICAL,
                            command=self.tree.yview)
        across = ttk.Scrollbar(parent, orient=tk.HORIZONTAL,
                               command=self.tree.xview)
        self.tree.configure(yscrollcommand=bar.set,
                            xscrollcommand=across.set)
        # The scrollbars first (`docs/ui_runtime.md`): a list packed
        # before them takes their room wherever it is too wide.
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        across.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _build_weights(self, parent):
        holder = ttk.Frame(parent)
        holder.pack(fill=tk.BOTH, expand=True)
        columns = (("name", "Combatant", ("Heidemarie",), tk.W),
                   ("weight", "Weight", ("10",), tk.E))
        self.weight_tree = ttk.Treeview(
            holder, columns=[c[0] for c in columns], show="headings",
            height=WEIGHT_ROWS, selectmode="browse")
        self._measured(self.weight_tree, columns, sortable=False)
        bar = ttk.Scrollbar(holder, orient=tk.VERTICAL,
                            command=self.weight_tree.yview)
        self.weight_tree.configure(yscrollcommand=bar.set)
        bar.pack(side=tk.RIGHT, fill=tk.Y)
        self.weight_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.weight_tree.tag_configure(
            "off", foreground=self.colors["fg_dim"])
        self.weight_tree.bind("<<TreeviewSelect>>", self._on_pick_weight)

        row = ttk.Frame(parent)
        # spacing: explanation text -> the controls it explains -- tree, label ↕
        row.pack(fill=tk.X, pady=(px(7), 0))
        ttk.Label(row, text="Weight:").pack(side=tk.LEFT)
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
        # Less the label's own inset each side, inside its width.
        width = max(px(200), event.width - px(4))
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
        self.refresh_readjust()

    def _all(self, variables, value):
        for var in variables.values():
            var.set(value)
        self._filtered()

    def _show_mode(self):
        weighted = self.mode() == "weighted"
        if weighted:
            self.weights_frame.grid()
            self.combatant_box.grid_remove()
        else:
            self.weights_frame.grid_remove()
            self.combatant_box.grid()
        shown = [c[0] for c in COLUMNS
                 if weighted or c[0] not in WEIGHTED_ONLY]
        self.tree.configure(displaycolumns=shown)
        self.note_label.configure(text=NOTES[self.measure()])

    def _on_pick_weight(self, _event=None):
        picked = self.weight_tree.selection()
        if picked:
            self.weight_var.set(self._weights().get(picked[0], 0))

    def _on_weight(self):
        picked = self.weight_tree.selection()
        if not picked:
            return
        try:
            weight = max(0, min(WEIGHT_MAX, int(self.weight_var.get())))
        except (tk.TclError, ValueError):
            return
        weights = self._weights()
        if weights.get(picked[0], 0) == weight:
            return
        if weight:
            weights[picked[0]] = weight
        else:
            weights.pop(picked[0], None)
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

    def _fill_weights(self):
        weights = self._weights()
        tree = self.weight_tree
        picked = tree.selection()
        tree.delete(*tree.get_children())
        for name in self._names():
            weight = weights.get(name, 0)
            tree.insert("", tk.END, iid=name, values=(name, weight),
                        tags=() if weight else ("off",))
        if picked and tree.exists(picked[0]):
            tree.selection_set(picked[0])

    def _combatants(self):
        """{combatant: weight} the controls ask for."""
        names = self._names()
        if self.mode() == "weighted":
            return {name: weight for name, weight in self._weights().items()
                    if name in names and weight > 0}
        name = self.combatant_var.get()
        return {name: 1.0} if name in names else {}

    def _readjustable(self):
        optimizer = self.optimizer
        return sorted((f for f in optimizer.fragments if rj.readjustable(f)),
                      key=lambda f: f.id)

    def _signatures(self, combatants):
        """{combatant: (signature, job template)}: what one combatant's
        answers depend on, beyond the fragments -- the measure, the
        preset's weights or the Optimizer settings, the rolls -- and
        what a job for them carries. A combatant with no preset is left
        out, and named in the second value."""
        measure = self.measure()
        stats = rj.stats_snapshot()
        rolls = tuple(sorted((k, tuple(v)) for k, v in stats.items()))
        out, bare = {}, []
        context = self.context
        for name in combatants:
            if measure == rj.GEAR:
                assigned = context.character_preset_manager.get_preset_for(
                    name) if context.character_preset_manager else None
                weights = context.preset_manager.get_preset(assigned) \
                    if assigned and context.preset_manager else None
                if weights is None:
                    bare.append(name)
                    continue
                key = (self._token, rj.GEAR, name,
                       tuple(sorted(weights.items())), rolls)
                out[name] = (key, {"measure": rj.GEAR, "weights": weights,
                                   "stats": stats})
            else:
                info = self.optimizer.character_info.get(name)
                manager = context.optimizer_settings_manager
                settings = manager.get_character_data(
                    info.res_id if info is not None else 0) \
                    if manager is not None else {}
                key = (self._token, rj.BUILD, name,
                       json.dumps(settings, sort_keys=True, default=str),
                       rolls)
                out[name] = (key, {"measure": rj.BUILD, "settings": settings,
                                   "stats": stats})
        return out, bare

    def _needed(self, fragments, signatures):
        """({combatant: {id: answer}}, [(part key, job)] still to ask
        for, whether every answer is in). A combatant's fragments are
        asked for a chunk at a time; under the build score, its top
        `REFINE_TOP` by those answers are then sampled, a smaller
        chunk at a time, and those answers replace theirs."""
        readings, wanted = {}, []
        chunks = [fragments[i:i + CHUNK]
                  for i in range(0, len(fragments), CHUNK)]
        for name, (key, template) in signatures.items():
            got, whole = {}, True
            for chunk in chunks:
                part = (key, "read", tuple(f.id for f in chunk))
                if part in self._parts:
                    got.update(self._parts[part])
                else:
                    whole = False
                    wanted.append((part, template, name, chunk, False))
            if whole and template["measure"] == rj.BUILD:
                def value(fid):
                    _now, plain, exclude, _s = got[fid]
                    return max(plain.per_quartz, exclude.per_quartz)
                top = sorted(got, key=lambda fid: (-value(fid), fid))
                by_id = {f.id: f for f in fragments}
                top = [by_id[fid] for fid in top[:rj.REFINE_TOP]]
                for i in range(0, len(top), REFINE_CHUNK):
                    chunk = top[i:i + REFINE_CHUNK]
                    part = (key, "refine", tuple(f.id for f in chunk))
                    if part in self._parts:
                        got.update(self._parts[part])
                    else:
                        whole = False
                        wanted.append((part, template, name, chunk, True))
            readings[name] = got
        return readings, wanted, not wanted

    def _ask(self, wanted):
        """Hand every part not asked for yet to the workers, and drop
        the jobs not started yet that nothing wants now."""
        keys = {part for part, *_rest in wanted}
        for part, future in list(self._futures.items()):
            if part not in keys and future.cancel():
                del self._futures[part]
        for part, template, name, chunk, refine in wanted:
            if part in self._futures:
                continue
            job = {"measure": template["measure"],
                   "stats": template["stats"], "fragments": chunk,
                   "refine": refine}
            if template["measure"] == rj.GEAR:
                job["weights"] = template["weights"]
            else:
                signature = part[0]
                if signature not in self._inputs:
                    self._inputs[signature] = rj.build_inputs(
                        self.optimizer, name, template["settings"])
                job["build"] = self._inputs[signature]
            self._futures[part] = rj.submit(job)
        if self._futures and not self._polling:
            self._polling = True
            self.frame.after(POLL_MS, self._poll)

    def _poll(self):
        """Take in what the workers have answered, ask for what that
        makes wanted, and draw once the list is whole."""
        self._polling = False
        for part, future in list(self._futures.items()):
            if not future.done():
                continue
            del self._futures[part]
            if future.cancelled():
                continue
            try:
                self._parts[part] = future.result()
            except Exception as e:                 # shown, not raised
                self._error = e
        self.refresh_readjust()

    def _forget(self, token):
        """A new snapshot: every answer is of the old one."""
        if token != self._token:
            self._token = token
            self._parts.clear()
            self._inputs.clear()
            for future in self._futures.values():
                future.cancel()
            self._futures.clear()
        elif len(self._parts) > KEEP_PARTS:
            self._parts.clear()

    def refresh_readjust(self):
        """Read the controls and the loaded data again, ask the workers
        for what is not worked out yet, and draw what is."""
        self._settle = None
        names = self._names()
        self.combatant_box.configure(values=names)
        if names and self.combatant_var.get() not in names:
            self.combatant_var.set(names[0])
        self._fill_weights()
        self._show_mode()
        optimizer = self.optimizer
        if optimizer is None or not optimizer.fragments:
            # Every set at 0: the panel keeps the height it has with
            # data, which the list's title is set under.
            self._fill_sets([])
            self._show_status(None)
            self._draw([], NO_DATA)
            return
        fragments = self._readjustable()
        self._fill_sets(fragments)
        self._show_status(None)
        # **Only while showing**: a hidden tab, the checks' own builds
        # among them, starts no worker. `<Map>` catches it up.
        if not self.frame.winfo_ismapped():
            return
        self._forget((id(optimizer.fragments), optimizer.capture_time,
                      len(optimizer.fragments)))
        combatants = self._combatants()
        signatures, bare = self._signatures(combatants)
        if not combatants:
            self._draw([], NOBODY)
            return
        if not signatures:
            self._draw([], NO_PRESET % ", ".join(sorted(bare)))
            return
        readings, wanted, whole = self._needed(fragments, signatures)
        if self._error is not None:
            error, self._error = self._error, None
            self._draw([], FAILED % error)
            return
        if not whole:
            self._ask(wanted)
            self._draw(None, LOADING)
            return
        shown = best_readings(self._passing(fragments), readings,
                              {name: combatants[name]
                               for name in signatures})
        self._draw(shown)
        self._show_status(len(shown))

    def _passing(self, fragments):
        """The fragments the Slots, Sets and Fragments filters let
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
            cells[1] = words
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
            "now": lambda r: r.now, "gain": lambda r: r.plain.mean,
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
