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
whose weighted gain is highest.

The work runs on a worker thread (`docs/ui_runtime.md`): the build
score samples the real score for the fragments ranked highest, which
takes seconds. `docs/readjust.md` has the model.
"""

import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

import item_amounts
import readjust as rj
from game_data.constants import EQUIPMENT_SLOTS

from ..base_tab import BaseTab
from ..scaling import px, px_after
from ..utils.combobox_nav import bind_combobox_nav
from ..utils.spinbox_clamp import clamp_on_commit, step_on_wheel

# The dropdowns' words, each beside what it stands for.
MEASURES = (("Gear Score", rj.GEAR), ("Build Score", rj.BUILD))
MODES = (("One combatant", "one"), ("Several, weighted", "weighted"))
OWNERS = (("All", "all"), ("Worn by them", "theirs"),
          ("Unequipped", "unequipped"))
SLOTS = (("All", 0),) + tuple(
    (name.split()[0], number) for number, name in sorted(
        EQUIPMENT_SLOTS.items()))

# The settings each control is kept under (`settings_manager.LAYOUT`).
MEASURE_KEY = "readjust_measure"
MODE_KEY = "readjust_mode"
COMBATANT_KEY = "readjust_combatant"
WEIGHTS_KEY = "readjust_weights"
OWNER_KEY = "readjust_owner"
SLOT_KEY = "readjust_slot"

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

# The note under the lists, by measure.
NOTES = {
    rj.GEAR: (
        "Readjustment keeps each substat and its starting value and deals "
        "the upgrades out again; the game lets you keep Before or After, "
        "so it only gains. Reroll: 1 Quartz. Exclude: 2 Quartz, the "
        "substat left out back at its starting value. Gain: the "
        "expected rise in Gear Score, under the combatant's assigned "
        "preset. Chance: of any rise. Best: the most it can rise. Per "
        "Quartz: the better of the two, per Quartz spent."),
    rj.BUILD: (
        "Readjustment keeps each substat and its starting value and deals "
        "the upgrades out again; the game lets you keep Before or After, "
        "so it only gains. Reroll: 1 Quartz. Exclude: 2 Quartz, the "
        "substat left out back at its starting value. Gain: the "
        "expected rise in the Optimizer's score of the combatant's "
        "equipped build with this fragment in its slot, over that build "
        "as worn or with the fragment as it stands, whichever is better. "
        "Now: the build with the fragment as it stands. The top %d are "
        "sampled off the real score." % rj.REFINE_TOP),
}
WORKING = "Working out..."
NO_DATA = "No capture loaded: log in with the capture running."
NOBODY = "Give a combatant a weight above 0."
NO_PRESET = "%s has no Gear Score preset: assign one on the Combatants tab."
HELD = "Shuffling Quartz held: %d"
COUNT = "%d fragments"

POLL_MS = 50
# How long the weight spinbox has to hold still before a new reading.
SETTLE_MS = 400


def _words(pairs, value):
    return next((word for word, v in pairs if v == value), pairs[0][0])


def _value(pairs, word):
    return next((v for w, v in pairs if w == word), pairs[0][1])


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


class ReadjustTab(BaseTab):
    """Fully upgraded Legendaries, ranked by what a readjustment of each
    is expected to gain per Shuffling Quartz."""

    def __init__(self, parent, context):
        super().__init__(parent, context)
        self._generation = 0
        self._result = None
        self._readings = []
        self._sort = ("weighted", True)
        self._settle = None
        self.setup_ui()
        self.refresh_readjust()
        # **NOT redundant with the load paths:** a preset or an
        # Optimizer setting changed on another tab is read here.
        self.when_shown(self.refresh_readjust)

    # ------------------------------------------------------------ build

    def setup_ui(self):
        content = ttk.Frame(self.frame)
        toolbar = ttk.Frame(content)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        toolbar.pack(fill=tk.X, padx=(px_after(2, 2), px_after(2, 2)),
                     pady=px((0, 0)))
        controls = ttk.Frame(toolbar)
        # spacing: tab list -> first element -- tab, dropdown ↕
        # spacing: panel ↕ unrelated label -- dropdown, title ↕
        controls.pack(side=tk.LEFT, anchor=tk.N,
                      pady=(px_after(1, 5), px(5)))
        settings = self._settings()
        self.measure_var = tk.StringVar(value=_words(
            MEASURES, settings.get(MEASURE_KEY, rj.GEAR)))
        self.mode_var = tk.StringVar(value=_words(
            MODES, settings.get(MODE_KEY, "one")))
        self.combatant_var = tk.StringVar(
            value=settings.get(COMBATANT_KEY, "") or "")
        self.owner_var = tk.StringVar(value=_words(
            OWNERS, settings.get(OWNER_KEY, "all")))
        self.slot_var = tk.StringVar(value=_words(
            SLOTS, settings.get(SLOT_KEY, 0)))
        self._dropdown(controls, "Score:", self.measure_var,
                       [w for w, _v in MEASURES], first=True)
        self._dropdown(controls, "For:", self.mode_var,
                       [w for w, _v in MODES])
        self.combatant_box = ttk.Combobox(
            controls, textvariable=self.combatant_var, state="readonly",
            width=14)
        # spacing: label ↔ its element -- dropdown, dropdown ↔
        self.combatant_box.pack(side=tk.LEFT, padx=px((5, 0)))
        self.combatant_box.bind("<<ComboboxSelected>>",
                                lambda _e: self._changed())
        bind_combobox_nav(self.combatant_box)
        self._dropdown(controls, "Slot:", self.slot_var,
                       [w for w, _v in SLOTS])
        self._dropdown(controls, "Fragments:", self.owner_var,
                       [w for w, _v in OWNERS])

        self.status_label = ttk.Label(toolbar, text="",
                                      foreground=self.colors["fg_dim"])
        # spacing: tab list -> first element -- tab, label ↕
        self.status_label.pack(side=tk.RIGHT, anchor=tk.N,
                               pady=(px_after(1, 7), 0))

        body = ttk.Frame(content)
        body.pack(fill=tk.BOTH, expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self.weights_frame = ttk.LabelFrame(
            body, text="Weights", padding=px(0),
            style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- label, title ↕
        self.weights_frame.grid(row=0, column=0, sticky="ns",
                                padx=(px_after(2, 2), px(2)),
                                pady=(px_after(5, 2), px(2)))
        self._build_weights(self.weights_frame)

        lists = ttk.LabelFrame(body, text="Fragments", padding=px(0),
                               style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- label, title ↕
        lists.grid(row=0, column=1, sticky="nsew",
                   padx=(px_after(2, 2), px_after(2, 2)),
                   pady=(px_after(5, 2), px(2)))
        self._build_list(lists)

        self.note_label = ttk.Label(content, text="", justify=tk.LEFT,
                                    foreground=self.colors["fg_dim"])
        # spacing: panel ↕ unrelated label -- panel, label ↕
        # spacing: content frame -> content frame -- label, frame ↔↕
        self.note_label.pack(fill=tk.X, padx=px_after(2, 2),
                             pady=(px_after(2, 3), px_after(2, 2)))
        self.note_label.bind(
            "<Configure>", lambda e: self.note_label.configure(
                wraplength=max(1, e.width)))

        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        content.pack(fill=tk.BOTH, expand=True, padx=px(2),
                     pady=px((1, 2)))
        self._show_mode()

    def _dropdown(self, parent, words, var, values, first=False):
        holder = ttk.Frame(parent)
        # spacing: control group ↔ control group -- dropdown, label ↔
        holder.pack(side=tk.LEFT, anchor=tk.N,
                    padx=px((0 if first else 13, 0)))
        ttk.Label(holder, text=words).pack(side=tk.LEFT)
        box = ttk.Combobox(holder, textvariable=var, state="readonly",
                           values=values,
                           width=max(len(v) for v in values) + 1)
        # spacing: label ↔ its element -- label, dropdown ↔
        box.pack(side=tk.LEFT, padx=px((2, 0)))
        box.bind("<<ComboboxSelected>>", lambda _e: self._changed())
        bind_combobox_nav(box)
        return box

    def _measured(self, tree, columns):
        """Each column as wide as its heading or widest sample, in the
        list's own fonts -- measured, so the fonts carry the scale and
        only the inset takes `px`."""
        cell = tkfont.nametofont("TkDefaultFont")
        head = tkfont.nametofont("TkHeadingFont")
        for col, title, samples, anchor in columns:
            width = max([head.measure(title)]
                        + [cell.measure(s) for s in samples]) \
                + px(2 * TEXT_INSET)
            tree.heading(col, text=title, anchor=anchor,
                         command=lambda c=col: self._sort_by(c))
            # None stretches: a stretched column keeps its width when
            # the Weights list takes room beside it, and pushes the
            # columns after it out of view.
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
        self._measured(self.weight_tree, columns)
        for col, _t, _s, _a in columns:
            self.weight_tree.heading(col, command="")
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

    # --------------------------------------------------------- settings

    def _settings(self):
        manager = getattr(self.context, "settings_manager", None)
        if manager is None:
            return {}
        return {key: manager.get(key) for key in (
            MEASURE_KEY, MODE_KEY, COMBATANT_KEY, WEIGHTS_KEY, OWNER_KEY,
            SLOT_KEY) if manager.get(key) is not None}

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
        self._save(SLOT_KEY, _value(SLOTS, self.slot_var.get()))
        self._show_mode()
        self.refresh_readjust()

    def _show_mode(self):
        weighted = self.mode() == "weighted"
        if weighted:
            self.weights_frame.grid()
            self.combatant_box.pack_forget()
        else:
            self.weights_frame.grid_remove()
            if not self.combatant_box.winfo_manager():
                self.combatant_box.pack(
                    side=tk.LEFT, padx=px((5, 0)),
                    after=self.combatant_box.master.winfo_children()[1])
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
        self._fill_list()

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

    def request(self):
        """The `readjust.Request` the controls stand for, and why there
        is nothing to ask where there is not (None, words)."""
        names = self._names()
        if self.mode() == "weighted":
            combatants = {name: weight for name, weight
                          in self._weights().items()
                          if name in names and weight > 0}
        else:
            name = self.combatant_var.get()
            combatants = {name: 1.0} if name in names else {}
        if not combatants:
            return None, NOBODY
        measure = self.measure()
        presets, settings = {}, {}
        context = self.context
        for name in combatants:
            if measure == rj.GEAR:
                assigned = context.character_preset_manager.get_preset_for(
                    name) if context.character_preset_manager else None
                weights = context.preset_manager.get_preset(assigned) \
                    if assigned and context.preset_manager else None
                if weights is not None:
                    presets[name] = weights
            else:
                info = self.optimizer.character_info.get(name)
                manager = context.optimizer_settings_manager
                if manager is not None:
                    settings[name] = manager.get_character_data(
                        info.res_id if info is not None else 0)
        if measure == rj.GEAR and not presets:
            return None, NO_PRESET % ", ".join(sorted(combatants))
        return rj.Request(measure, combatants, presets=presets,
                          settings=settings,
                          owner=_value(OWNERS, self.owner_var.get()),
                          slot=_value(SLOTS, self.slot_var.get())), ""

    def refresh_readjust(self):
        """Read the controls and the loaded data again, and rank on a
        worker thread; `_poll` draws the answer."""
        self._settle = None
        names = self._names()
        self.combatant_box.configure(values=names)
        if names and self.combatant_var.get() not in names:
            self.combatant_var.set(names[0])
        self._fill_weights()
        self._show_mode()
        self._generation += 1
        optimizer = self.optimizer
        if optimizer is None or not optimizer.fragments:
            self._readings = []
            self._fill_list()
            self.status_label.configure(text=NO_DATA)
            return
        request, why = self.request()
        if request is None:
            self._readings = []
            self._fill_list()
            self.status_label.configure(text=why)
            return
        self.status_label.configure(text=WORKING)
        generation = self._generation
        self._result = None

        def work():
            try:
                out = rj.rank(optimizer, request,
                              lambda: generation != self._generation)
            except Exception as e:             # shown, not raised
                out = e
            self._result = (generation, request.measure, out)

        threading.Thread(target=work, daemon=True).start()
        self.frame.after(POLL_MS, self._poll, generation)

    def _poll(self, generation):
        if generation != self._generation:
            return
        result = self._result
        if result is None or result[0] != generation:
            self.frame.after(POLL_MS, self._poll, generation)
            return
        _gen, measure, out = result
        if isinstance(out, Exception):
            self._readings = []
            self._fill_list()
            self.status_label.configure(
                text="Could not work it out: %s" % out)
            return
        if out is None:
            return
        self._readings = out
        self._measure_shown = measure
        self._fill_list()
        held = item_amounts.held(self.optimizer.raw_data).get(rj.QUARTZ, 0)
        self.status_label.configure(
            text="%s    %s" % (COUNT % len(out), HELD % held))

    def _fill_list(self):
        tree = self.tree
        tree.delete(*tree.get_children())
        measure = getattr(self, "_measure_shown", self.measure())
        key, down = self._sort
        ids = [c[0] for c in COLUMNS]
        rows = [(reading, row_values(reading, measure))
                for reading in self._readings]
        if key in ("weighted", "per"):
            rows.sort(key=lambda r: r[0].value, reverse=down)
        elif key in ("now", "gain", "chance", "xgain", "xchance", "best"):
            number = {
                "now": lambda r: r.now, "gain": lambda r: r.plain.mean,
                "chance": lambda r: r.plain.chance,
                "xgain": lambda r: r.exclude.mean,
                "xchance": lambda r: r.exclude.chance,
                "best": lambda r: max(r.plain.best, r.exclude.best)}[key]
            rows.sort(key=lambda r: number(r[0]), reverse=down)
        else:
            at = ids.index(key)
            rows.sort(key=lambda r: str(r[1][at]), reverse=not down)
        for _reading, values in rows:
            tree.insert("", tk.END, values=values)
