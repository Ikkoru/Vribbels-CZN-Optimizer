"""Gacha History tab: every pull the game has listed, and how lucky it
was.

`gacha_history.py` does the reading and the arithmetic; this draws it.
Two lists side by side: one row per banner family with its luck on the
left, and the pulls of whichever family is selected, newest first.

**Nothing is read until the tab is first shown.** The luck figures are
an exact convolution over every 5-star the history holds, which is a
few tenths of a second the first time -- spent at startup, that would
be on every launch whether or not anyone opens the tab.
"""

import json
import tkinter as tk
import tkinter.font as tkfont
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
    "Import JSON also reads hub-czn's Export JSON. Luck: where your 5★ "
    "pulls rank among all players who got as many 5★s."
)

# (label, the rarities it shows). None shows everything.
FILTERS = (("All pulls", None), ("4★ and 5★", {4, 5}),
           ("5★ only", {5}))

def _unit_names():
    """Every name a unit column can show, for sizing one."""
    from game_data import CHARACTERS, PARTNERS
    return [unit["name"] for table in (CHARACTERS, PARTNERS)
            for unit in table.values()
            if isinstance(unit, dict) and unit.get("name")] + ["#99999"]


# (id, heading, the widest things it will hold, anchor). **Widths are
# MEASURED** from those, in the list's own fonts, so a column fits its
# text at either scale and nothing here is a pixel count. A callable is
# read when the list is built. The LAST column of each list stretches.
SUMMARY_COLUMNS = (
    ("banner", "Banner", tuple(gh.POOL_LABELS.values()), tk.W),
    ("pulls", "Pulls", ("99,999",), tk.E),
    ("fives", "5★", ("999",), tk.E),
    ("avg", "Avg 5★ pull", ("99.9",), tk.E),
    ("game", "Game avg", ("99.9",), tk.E),
    ("luck", "Luck", ("Bottom 50%", "Bottom 0.1%", "Bottom <0.1%"), tk.E),
    ("fifty", "50/50 won", ("99 of 99",), tk.E),
    ("fours", "4★", ("999",), tk.E),
    ("four_avg", "Avg 4★ pull", ("99.9",), tk.E),
    ("pity", "Pity now", ("99",), tk.E),
    ("read", "Last read", ("0000-00-00 00:00",), tk.CENTER),
)
PULL_COLUMNS = (
    ("number", "#", ("99999",), tk.E),
    ("unit", "Unit", _unit_names, tk.W),
    ("stars", "Rarity", ("5★",), tk.CENTER),
    ("pull", "Pull", ("70",), tk.E),
    ("featured", "Rate-up", _unit_names, tk.W),
    ("outcome", "50/50", (gh.WON, gh.LOST, gh.GUARANTEED, gh.RATE_UP,
                          gh.UNKNOWN), tk.W),
    ("time", "Time", ("0000-00-00 00:00",), tk.CENTER),
)

# This tab's lists, styled apart from every other list in the app. Text
# sits TEXT_INSET in from its column's edges, in a cell and a heading
# alike, so a heading lines up with its cells.
#
# **Between two columns sits an empty one, COLUMN_GAP wide.** Tk's
# padding is one pair of values for every column of a list, so it
# cannot keep the outermost columns close to the list's edges and the
# rest far apart; a spacer can. A column is exactly as wide as its
# widest text plus the inset on both sides, so the tightest two columns'
# text is `2 * TEXT_INSET + COLUMN_GAP` apart. Any column's slack lands
# on the side away from its anchor, and only widens that.
TREE_STYLE = "GachaHistory.Treeview"
TEXT_INSET = 3
COLUMN_GAP = 18
# The heading's height is left as the shared style has it.
HEADING_INSET_V = 3

# Row colours by rarity. A unit's stars index the rarity table
# directly -- 5 Mythic, 4 Legendary, 3 Rare. A unit neither the game's
# rate lists nor the tables know is drawn loudly, in a colour no
# rarity has: its pity, and every pity after it, rest on nobody
# knowing whether it was a 5-star.
STAR_COLOURS = {stars: RARITY_COLORS[stars] for stars in (5, 4, 3)}
UNKNOWN_COLOUR = "red"

NO_VALUE = "-"

# A banner type the game has newer pulls for is drawn orange, and red
# where its records were last read more than `URGENT_AFTER_DAYS` ago --
# the pulls it is missing may be halfway to the game erasing them. A
# line at the toolbar's right end says what each colour means. A
# coloured row rather than words in `Last read`: at this tab's column
# inset, the width those words took was what kept the two lists from
# fitting the default window.
BEHIND_TAG = "behind"
URGENT_TAG = "urgent"
BEHIND_NOTE = "Orange banners have unread pulls"
URGENT_NOTE = ("⚠ Red banners were last read over %d days ago.\n"
               "Read them NOW, before the game erases their history!"
               % gh.URGENT_AFTER_DAYS)
URGENT_FONT = ("Segoe UI", 9, "bold")

# Where the status lines wrap, so a long one takes height from the
# toolbar rather than width from the help text beside it.
STATUS_WRAPLENGTH = 320


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
        toolbar.pack(fill=tk.X, padx=px(2), pady=px((0, 0)))

        # The buttons and the filter as one group, so its top pad is the
        # whole lever on their distance from the tab list. On the
        # toolbar it would move the help text too, which its own line
        # box already seats where the rule wants it.
        controls = ttk.Frame(toolbar)
        # spacing: tab list -> first element -- tab, button ↕
        # spacing: tab list -> first element -- tab, dropdown ↕
        controls.pack(side=tk.LEFT, anchor=tk.N, pady=px((5, 0)))

        import_btn = ttk.Button(controls, text="Import JSON",
                                command=self._import, width=BUTTON_W_MEDIUM)
        # spacing: button -> button -- button, button ↔
        import_btn.pack(side=tk.LEFT, anchor=tk.N, padx=px((0, 4)))
        ttk.Button(controls, text="Export JSON", command=self._export,
                   width=BUTTON_W_MEDIUM).pack(side=tk.LEFT, anchor=tk.N)

        show = ttk.Frame(controls)
        # spacing: control group ↔ control group -- button, label ↔
        show.pack(side=tk.LEFT, anchor=tk.N, padx=px((14, 0)))
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

        # The status lines, stacked at the toolbar's right end: the two
        # warnings, most severe first, then anything else there is to
        # say. `_show_status` packs only those with something to say.
        status = ttk.Frame(toolbar)
        status.pack(side=tk.RIGHT, anchor=tk.N)
        self.urgent_label = ttk.Label(
            status, text="", font=URGENT_FONT,
            foreground=self.colors["red"],
            wraplength=px(STATUS_WRAPLENGTH))
        self.behind_label = ttk.Label(
            status, text="", foreground=self.colors["orange"],
            wraplength=px(STATUS_WRAPLENGTH))
        self.status_label = ttk.Label(
            status, text="", foreground=self.colors["fg_dim"],
            wraplength=px(STATUS_WRAPLENGTH))

        help_label = ttk.Label(
            toolbar, text=HELP_TEXT, justify=tk.LEFT,
            foreground=self.colors["fg_dim"],
            wraplength=px(HELP_WRAPLENGTH))
        # spacing: control group ↔ control group -- dropdown, label ↔
        help_label.pack(side=tk.LEFT, padx=px((14, 0)), fill=tk.X,
                        expand=True, anchor=tk.N)
        help_label.bind("<Configure>", self._rewrap)

        # The two lists side by side: the banners at their own width on
        # the left, the pulls taking whatever the window has left. The
        # space under the banners is free for later.
        body = ttk.Frame(content)
        body.pack(fill=tk.BOTH, expand=True)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        summary_frame = ttk.LabelFrame(body, text="Banners",
                                       padding=px(0),
                                       style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- label, title ↕
        summary_frame.grid(row=0, column=0, sticky="nw", padx=px(2),
                           pady=px(2))
        self.summary_tree = self._make_tree(summary_frame, SUMMARY_COLUMNS,
                                            height=1)
        self.summary_tree.pack(fill=tk.X)
        self.summary_tree.bind("<<TreeviewSelect>>", self._on_pick)
        self.summary_tree.tag_configure(BEHIND_TAG,
                                        foreground=self.colors["orange"])
        self.summary_tree.tag_configure(URGENT_TAG,
                                        foreground=self.colors["red"])

        self.pulls_frame = ttk.LabelFrame(body, text="Pulls",
                                          padding=px(0),
                                          style="Borderless.TLabelframe")
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- label, title ↕
        self.pulls_frame.grid(row=0, column=1, sticky="nsew", padx=px(2),
                              pady=px(2))
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

    @staticmethod
    def _style_lists():
        """This tab's list style: the shared one, with wider text insets.

        **A layout with no padding element**, because the shared
        style's `padding` is two levers at once -- it insets the tree
        area as well as every cell's text -- and widened on the area it
        pulls the heading row in from both ends, leaving a strip of the
        list's background beside it. Without the element, `padding`
        reaches only the text. Everything else, colours and row height
        included, falls through to `Treeview` and `Treeview.Heading`.

        **An empty foreground map, and NOT a no-op.** A style's state
        map outranks a row's tag colour, and `Treeview` maps `selected`
        to the plain foreground -- so without this a selected row loses
        its rarity or warning colour. The first style in the chain that
        maps an option answers for it alone, so an empty map here stops
        the lookup before it reaches `Treeview`'s. Removing the line
        changes nothing `style.map` can show; the check probes the
        lookup itself.
        """
        style = ttk.Style()
        try:
            style.layout(TREE_STYLE, [
                ("Treeview.treearea", {"sticky": "nswe"})])
        except tk.TclError:
            pass
        style.map(TREE_STYLE, foreground=[])
        # spacing: unique -- Treeview internals, which are style options -- tree, text ↔
        style.configure(TREE_STYLE,
                        padding=px((TEXT_INSET, 0, TEXT_INSET, 0)))
        # spacing: unique -- Treeview internals, which are style options -- tree, text ↔
        style.configure(TREE_STYLE + ".Heading",
                        padding=px((TEXT_INSET, HEADING_INSET_V,
                                    TEXT_INSET, HEADING_INSET_V)))

    def _make_tree(self, parent, columns, height):
        self._style_lists()
        ids = []
        for index, (col, _title, _samples, _anchor) in enumerate(columns):
            if index:
                ids.append(self._spacer(index))
            ids.append(col)
        tree = ttk.Treeview(parent, columns=ids, show="headings",
                            height=height, selectmode="browse",
                            style=TREE_STYLE)
        # Measured, so no `px()` on the text's share -- the fonts already
        # carry the scale. The inset is a distance and takes it.
        cell = tkfont.nametofont("TkDefaultFont")
        head = tkfont.nametofont("TkHeadingFont")
        for index, (col, title, samples, anchor) in enumerate(columns):
            samples = samples() if callable(samples) else samples
            width = max([head.measure(title)]
                        + [cell.measure(text) for text in samples]) \
                + px(2 * TEXT_INSET)
            # A heading takes its column's anchor: left to Tk it centres
            # over a right-aligned number.
            tree.heading(col, text=title, anchor=anchor)
            tree.column(col, width=width, anchor=anchor,
                        stretch=index == len(columns) - 1)
            if index:
                gap = self._spacer(index)
                tree.heading(gap, text="")
                # spacing: unique -- Treeview internals, which are style options -- tree, text ↔
                tree.column(gap, width=px(COLUMN_GAP),
                            minwidth=px(COLUMN_GAP), stretch=False)
        return tree

    @staticmethod
    def _spacer(index):
        return "gap%d" % index

    @staticmethod
    def _spaced(values):
        """A row's values with the empty spacer cells between them."""
        out = []
        for index, value in enumerate(values):
            if index:
                out.append("")
            out.append(value)
        return tuple(out)

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
            self._show_status("The history could not be read: %s" % e,
                              "red")
            self._fill_summary()
            self._fill_pulls()
            return
        notes = self.history.notes
        if notes:
            # Yellow, not red: red is the urgent banners' colour.
            self._show_status("; ".join(notes), "yellow")
        elif any(pool.stats.behind for pool in self._shown_pools()):
            # The pull count gives way to the warnings, which keeps the
            # toolbar within the help text's height.
            self._show_status("", "fg_dim")
        elif self.history.total:
            self._show_status(
                "%s pulls kept" % format(self.history.total, ","),
                "fg_dim")
        else:
            self._show_status("No history yet", "fg_dim")
        self._fill_summary()
        self._fill_pulls()

    def _show_status(self, text, colour):
        """Set the status lines: the warnings the shown banners call
        for, then `text`. A line with nothing to say is not packed, so
        it leaves no blank line behind."""
        pools = self._shown_pools()
        lines = (
            (self.urgent_label, URGENT_NOTE
             if any(p.stats.urgent for p in pools) else ""),
            (self.behind_label, BEHIND_NOTE
             if any(p.stats.behind and not p.stats.urgent for p in pools)
             else ""),
            (self.status_label, text))
        self.status_label.configure(foreground=self.colors[colour])
        for label, line in lines:
            label.pack_forget()
            label.configure(text=line)
        for label, line in lines:
            if line:
                label.pack(side=tk.TOP, anchor=tk.W)

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
                        values=self._spaced(self._summary_row(pool)),
                        tags=self._summary_tags(pool))
        tree.configure(height=max(1, len(pools)))
        keep = self._pool if self._pool in {p.pool for p in pools} else (
            pools[0].pool if pools else None)
        self._pool = keep
        if keep:
            tree.selection_set(keep)

    @staticmethod
    def _summary_tags(pool):
        if pool.stats.urgent:
            return (URGENT_TAG,)
        if pool.stats.behind:
            return (BEHIND_TAG,)
        return ()

    def _summary_row(self, pool):
        s = pool.stats
        fifty = NO_VALUE
        if s.won is not None and (s.won or s.lost):
            fifty = "%d of %d" % (s.won, s.won + s.lost)
        pity = s.game_pity if s.game_pity is not None else s.pity_now
        read = NO_VALUE
        if s.read_at:
            read = s.read_at.replace("T", " ")[:16]
        return (pool.label, format(s.pulls, ","), s.fives,
                _number(s.avg_pity), _number(s.expected_pity),
                gh.luck_rank(s.luckier_than) or NO_VALUE,
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
                        values=self._spaced((
                            pull.number, gh.unit_name(pull.res_id),
                            _stars(pull.stars), pull.pity,
                            gh.unit_name(pull.featured)
                            if pull.featured else "",
                            pull.outcome or "", _when(pull.at))))

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
