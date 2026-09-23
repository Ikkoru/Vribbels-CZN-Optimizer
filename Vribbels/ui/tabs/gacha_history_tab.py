"""Gacha History tab: every pull the game has listed, and how lucky it
was.

`gacha_history.py` does the reading and the arithmetic; this draws it.
Two lists: one row per banner family with its luck, and the pulls of
whichever family is selected, newest first.

**Nothing is read until the tab is first shown.** The luck figures are
an exact convolution over every 5-star the history holds, which is a
few tenths of a second the first time -- spent at startup, that would
be on every launch whether or not anyone opens the tab.
"""

import json
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

import gacha_history as gh
from capture.constants import OUTPUT_DIR
from game_data.constants import RARITY_COLORS
from ui.scaling import px
from ..base_tab import BaseTab
from ..utils.button_width import BUTTON_W_MEDIUM

# The instructions under the tab strip, in the Optimizer's explanation
# style. `HELP_WRAPLENGTH` is where the text starts wrapped: wider than
# its longest line, so the default window shows the three lines whole
# and the first rewrap moves nothing. A narrower window rewraps.
HELP_WRAPLENGTH = 900
HELP_TEXT = (
    "Records your pulls long after the game stops. Important! The game "
    "erases records that are older than about half a year!\n"
    "To use: Start a capture. In game open each banner's Probability "
    "Info > Rescue Records. Page through to the last page! Do this for "
    "each banner; they are separate!\n"
    "Import JSON also reads hub-czn's Export JSON. Luckier than: the "
    "share of players who needed more pulls for as many 5★s."
)

# (label, the rarities it shows). None shows everything.
FILTERS = (("All pulls", None), ("4★ and 5★", {4, 5}),
           ("5★ only", {5}))

# (id, heading, width, anchor). The LAST column of each list stretches.
SUMMARY_COLUMNS = (
    ("banner", "Banner", 200, tk.W),
    ("pulls", "Pulls", 52, tk.E),
    ("fives", "5★", 36, tk.E),
    ("avg", "Avg 5★ pull", 84, tk.E),
    ("game", "Game avg", 68, tk.E),
    ("luck", "Luckier than", 88, tk.E),
    ("fifty", "50/50 won", 72, tk.E),
    ("fours", "4★", 40, tk.E),
    ("four_avg", "Avg 4★ pull", 84, tk.E),
    ("pity", "Pity now", 66, tk.E),
    ("read", "Last read from the game", 220, tk.W),
)
PULL_COLUMNS = (
    ("number", "#", 50, tk.E),
    ("unit", "Unit", 150, tk.W),
    ("stars", "Rarity", 56, tk.CENTER),
    ("pull", "Pull", 44, tk.E),
    ("featured", "Rate-up", 150, tk.W),
    ("outcome", "50/50", 96, tk.W),
    ("time", "Time", 160, tk.W),
)

# Row colours by rarity. A unit's stars index the rarity table
# directly -- 5 Mythic, 4 Legendary, 3 Rare. A unit neither the game's
# rate lists nor the tables know is drawn loudly, in a colour no
# rarity has: its pity, and every pity after it, rest on nobody
# knowing whether it was a 5-star.
STAR_COLOURS = {stars: RARITY_COLORS[stars] for stars in (5, 4, 3)}
UNKNOWN_COLOUR = "red"

NO_VALUE = "-"


def _stars(stars):
    return "%d★" % stars if stars else "?"


def _number(value, digits=1):
    return NO_VALUE if value is None else "%.*f" % (digits, value)


def _when(epoch):
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")


class GachaHistoryTab(BaseTab):
    """The Gacha History tab."""

    def __init__(self, parent, context):
        super().__init__(parent, context)
        self.history = None
        self._loaded = False
        self._pool = None               # the family the pulls list shows
        self.setup_ui()
        self.frame.bind("<Map>", self._first_show, add="+")

    # ------------------------------------------------------------ layout

    def setup_ui(self):
        # Built inside an unmapped container and packed last, so the tab
        # appears once, settled -- see the Optimizer's setup_ui.
        content = ttk.Frame(self.frame)

        toolbar = ttk.Frame(content)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, button ↕
        toolbar.pack(fill=tk.X, padx=px(2), pady=px((0, 0)))

        import_btn = ttk.Button(toolbar, text="Import JSON",
                                command=self._import, width=BUTTON_W_MEDIUM)
        # spacing: button -> button -- button, button ↔
        import_btn.pack(side=tk.LEFT, anchor=tk.N, padx=px((0, 4)))
        ttk.Button(toolbar, text="Export JSON", command=self._export,
                   width=BUTTON_W_MEDIUM).pack(side=tk.LEFT, anchor=tk.N)

        show = ttk.Frame(toolbar)
        # spacing: control group ↔ control group -- button, label ↔
        show.pack(side=tk.LEFT, anchor=tk.N, padx=px((12, 0)))
        ttk.Label(show, text="Show:").pack(side=tk.LEFT)
        self.filter_var = tk.StringVar(value=FILTERS[0][0])
        filter_box = ttk.Combobox(
            show, textvariable=self.filter_var, state="readonly",
            values=[word for word, _stars in FILTERS],
            width=max(len(word) for word, _stars in FILTERS) + 1)
        # spacing: label ↔ its element -- label, dropdown ↔
        filter_box.pack(side=tk.LEFT, padx=px((2, 0)))
        filter_box.bind("<<ComboboxSelected>>",
                        lambda _e: self._fill_pulls())

        self.status_label = ttk.Label(toolbar, text="",
                                      foreground=self.colors["fg_dim"])
        self.status_label.pack(side=tk.RIGHT, anchor=tk.N)

        help_label = ttk.Label(
            toolbar, text=HELP_TEXT, justify=tk.LEFT,
            foreground=self.colors["fg_dim"],
            wraplength=px(HELP_WRAPLENGTH))
        # spacing: control group ↔ control group -- dropdown, label ↔
        help_label.pack(side=tk.LEFT, padx=px((12, 0)), fill=tk.X,
                        expand=True, anchor=tk.N)
        help_label.bind("<Configure>", self._rewrap)

        summary_frame = ttk.LabelFrame(content, text="Banners",
                                       padding=px(0),
                                       style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔
        # spacing: panel ↕ unrelated label -- label, title ↕
        # spacing: panel ↕ unrelated label -- panel, title ↕
        # The trailing 5 is the whole lever on the gap down to the
        # Pulls title, stacked panels answering to the text rule rather
        # than the frame rule -- the same shape as the Optimizer's
        # Exclude panel above its Results.
        summary_frame.pack(fill=tk.X, padx=px(2), pady=px((2, 5)))
        self.summary_tree = self._make_tree(summary_frame, SUMMARY_COLUMNS,
                                            height=1)
        self.summary_tree.pack(fill=tk.X)
        self.summary_tree.bind("<<TreeviewSelect>>", self._on_pick)

        self.pulls_frame = ttk.LabelFrame(content, text="Pulls",
                                          padding=px(0),
                                          style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔↕
        self.pulls_frame.pack(fill=tk.BOTH, expand=True, padx=px(2),
                              pady=px((0, 2)))
        self.pulls_tree = self._make_tree(self.pulls_frame, PULL_COLUMNS,
                                          height=20)
        scroll = ttk.Scrollbar(self.pulls_frame, orient=tk.VERTICAL,
                               command=self.pulls_tree.yview)
        self.pulls_tree.configure(yscrollcommand=scroll.set)
        self.pulls_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        for stars, colour in STAR_COLOURS.items():
            self.pulls_tree.tag_configure(self._star_tag(stars),
                                          foreground=colour)
        self.pulls_tree.tag_configure(
            self._star_tag(None), foreground=self.colors[UNKNOWN_COLOUR])

        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        content.pack(fill=tk.BOTH, expand=True, padx=px(2), pady=px((1, 2)))

    def _make_tree(self, parent, columns, height):
        tree = ttk.Treeview(parent, columns=[c[0] for c in columns],
                            show="headings", height=height,
                            selectmode="browse")
        for index, (col, title, width, anchor) in enumerate(columns):
            # A heading takes its column's anchor: left to Tk it centres
            # over a right-aligned number.
            tree.heading(col, text=title, anchor=anchor)
            tree.column(col, width=px(width), anchor=anchor,
                        stretch=index == len(columns) - 1)
        return tree

    def _rewrap(self, event):
        """Keep the help text wrapped to the width its row gives it.

        `event.width` is measured, so it is already at the active scale
        and does not go through `px`. Only a CHANGE is written: setting
        `wraplength` moves the label's requested width, and a handler
        that writes every time can bounce the row's layout.
        """
        new = max(px(200), event.width - px(10))
        label = event.widget
        try:
            if int(str(label.cget("wraplength"))) == new:
                return
        except (ValueError, tk.TclError):
            pass
        label.configure(wraplength=new)

    @staticmethod
    def _star_tag(stars):
        return "stars_%s" % (stars if stars else "unknown")

    # ------------------------------------------------------------ reading

    def _folder(self):
        return gh.folder_in(OUTPUT_DIR)

    def _first_show(self, _event):
        if not self._loaded:
            self.refresh()

    def on_capture_update(self):
        """The capture wrote the history file. Only a tab that has
        already been shown re-reads it; one that has not reads it the
        first time it is."""
        if self._loaded:
            self.refresh()

    def refresh(self):
        """Read the history folder again and redraw both lists."""
        self._loaded = True
        try:
            self.history = gh.load(self._folder())
        except Exception as e:                       # noqa: BLE001
            self.history = None
            self.status_label.configure(
                text="The history could not be read: %s" % e,
                foreground=self.colors["red"])
            self._fill_summary()
            self._fill_pulls()
            return
        notes = self.history.notes
        if notes:
            self.status_label.configure(text="; ".join(notes),
                                        foreground=self.colors["red"])
        elif self.history.total:
            self.status_label.configure(
                text="%s pulls kept" % format(self.history.total, ","),
                foreground=self.colors["fg_dim"])
        else:
            self.status_label.configure(text="No history yet",
                                        foreground=self.colors["fg_dim"])
        self._fill_summary()
        self._fill_pulls()

    def _shown_pools(self):
        """Families with pulls, and families whose records have been
        opened -- one never opened and never pulled on is nothing to
        show."""
        if self.history is None:
            return []
        return [pool for pool in self.history.ordered()
                if pool.pulls or pool.stats.read_at]

    def _fill_summary(self):
        tree = self.summary_tree
        tree.delete(*tree.get_children())
        pools = self._shown_pools()
        for pool in pools:
            tree.insert("", tk.END, iid=pool.pool,
                        values=self._summary_row(pool))
        tree.configure(height=max(1, len(pools)))
        keep = self._pool if self._pool in {p.pool for p in pools} else (
            pools[0].pool if pools else None)
        self._pool = keep
        if keep:
            tree.selection_set(keep)

    def _summary_row(self, pool):
        s = pool.stats
        fifty = NO_VALUE
        if s.won is not None and (s.won or s.lost):
            fifty = "%d of %d" % (s.won, s.won + s.lost)
        pity = s.game_pity if s.game_pity is not None else s.pity_now
        read = NO_VALUE
        if s.read_at:
            read = s.read_at.replace("T", " ")[:16]
            if s.behind:
                read += " -- the game has newer pulls"
        return (pool.label, format(s.pulls, ","), s.fives,
                _number(s.avg_pity), _number(s.expected_pity),
                NO_VALUE if s.luckier_than is None
                else "%.0f%%" % (100 * s.luckier_than),
                fifty, s.fours, _number(s.four_avg), pity, read)

    def _on_pick(self, _event):
        chosen = self.summary_tree.selection()
        if chosen and chosen[0] != self._pool:
            self._pool = chosen[0]
            self._fill_pulls()

    def _fill_pulls(self):
        tree = self.pulls_tree
        tree.delete(*tree.get_children())
        pool = (self.history.pools.get(self._pool)
                if self.history is not None and self._pool else None)
        if pool is None:
            self.pulls_frame.configure(text="Pulls")
            return
        self.pulls_frame.configure(text="Pulls: %s" % pool.label)
        wanted = dict(FILTERS).get(self.filter_var.get())
        for pull in reversed(pool.pulls):
            if wanted is not None and pull.stars not in wanted:
                continue
            tree.insert("", tk.END, tags=(self._star_tag(pull.stars),),
                        values=(pull.number, gh.unit_name(pull.res_id),
                                _stars(pull.stars), pull.pity,
                                gh.unit_name(pull.featured)
                                if pull.featured else "",
                                pull.outcome or "", _when(pull.at)))

    # ------------------------------------------------------ import/export

    def _import(self):
        path = filedialog.askopenfilename(
            title="Import JSON", initialdir=str(OUTPUT_DIR),
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        name = Path(path).name
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            batches, skipped = gh.parse_import(data, name)
        except (OSError, ValueError) as e:
            # ImportRejected is a ValueError, and says what it expected.
            messagebox.showerror("Import JSON", "%s: %s" % (name, e))
            return
        before = gh.load(self._folder()).total
        try:
            gh.merge_import(self._folder(), batches)
        except (gh.StoreError, OSError) as e:
            messagebox.showerror("Import JSON", str(e))
            return
        self.refresh()
        after = self.history.total if self.history is not None else before
        read = sum(len(b["reward"]) for b in batches)
        text = "Read %s pulls from %s. %s of them were new to the history." \
            % (format(read, ","), name, format(max(0, after - before), ","))
        if skipped:
            text += "\n\n%s could not be placed in time and were left out." \
                % format(skipped, ",")
        messagebox.showinfo("Import JSON", text)

    def _export(self):
        if self.history is None or not self.history.total:
            messagebox.showinfo("Export JSON", "There is no history to "
                                "export yet.")
            return
        path = filedialog.asksaveasfilename(
            title="Export JSON", defaultextension=".json",
            initialdir=str(OUTPUT_DIR),
            initialfile="gacha_history_%s.json"
            % datetime.now().strftime("%Y%m%d"),
            filetypes=[("JSON files", "*.json")])
        if not path:
            return
        try:
            count = gh.export(self.history, path)
        except OSError as e:
            messagebox.showerror("Export JSON", str(e))
            return
        messagebox.showinfo("Export JSON", "Exported %s pulls to %s."
                            % (format(count, ","), path))
