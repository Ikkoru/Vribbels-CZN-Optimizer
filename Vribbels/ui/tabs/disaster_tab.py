"""The Galactic Disaster tab: what is left on the live season's
challenge pages.

A column per page of the game's Challenge Mission screen, Weekly
Progress aside: its title and a `done/total` count, then the
requirements still to meet, one block of wrapped words each, and a line
per batch of achievements still locked. An achievement for finishing
others is counted and never written out. One collecting a list carries
the items still to find as its tip.

**A page with nothing left moves.** Its heading goes green into a column
of its own at the tab's right, absent while no page is finished, and the
pages still open share the width it leaves. A page with a reward waiting
to be claimed has its count in orange, blinking once the page has moved.

`disaster_challenges.board` reads the snapshot; this only draws it.
`docs/disaster_challenges.md` has both.
"""

import time
import tkinter as tk
from tkinter import ttk

import disaster_challenges

from ..base_tab import BaseTab
from ..utils.tab_header import make_heading
from ..utils.tooltip import Tooltip
from ui.scaling import px
from .checklist_tab import (BLINK_MS, BLOCK_PAD, COLUMNS_PADX, COLUMNS_PADY,
                            HEADING_COUNTDOWN_DROP, HEADING_COUNTDOWN_FONT,
                            HEADING_COUNTDOWN_GAP, HEADING_GAP, ROW_FONT,
                            ROW_PITCH, WARN_BLINK_COLOURS)

# Two columns side by side: the end of one column's words against the
# next column's. Each is a block of text, so the two read as separate
# answers at the Checklist's Expiring Items distance, not a frame's 4.
COLUMN_GAP = 16         # spacing: control group ↔ control group -- run, run ↔

# One requirement against the next. Each is a block of wrapped lines, so
# they part at the Checklist's block division rather than at its row
# pitch: at a row's distance the space between two requirements reads as
# the space inside one.
REQUIREMENT_PITCH = ROW_PITCH + BLOCK_PAD

# A finished page's heading under the one before it, in the column at
# the right: the Checklist's row pitch, 12 from one heading's baseline
# to the next one's capitals, a heading being one row there.
FINISHED_PITCH = 1

# What each line's `spacing1` comes from: a column's first line sits
# under the heading at the Checklist's heading gap, every line after it
# a requirement's pitch below the last. One tag per line, as on the
# Checklist: two tags setting one option resolve by priority, not sum.
FIRST_TAG = "first"
ROW_TAG = "requirement"
LINE_PITCH = {FIRST_TAG: ROW_PITCH, ROW_TAG: REQUIREMENT_PITCH}
# A locked batch's line, and a tip's range, plus the row's id.
LOCKED_TAG = "locked"
TIP_PREFIX = "tip:"

# The colours: a finished page's heading; a count with a reward waiting,
# steady on an open page and blinking on a finished one.
FINISHED_COLOUR = "green"
UNCLAIMED_COLOUR = "orange"

# How often the tab rereads the clock while it is showing: a locked
# batch's countdown, and a gate opening, move with nothing else.
TICK_MS = 60 * 1000

# What a finished page's count's two halves each give back of a
# label's inset, on the side where they meet: the label's own 2.
COUNT_JOIN = 2
# What `_drawn` keeps the split of open and finished pages under.
_LAYOUT = "layout"


class DisasterTab(BaseTab):
    """The live Galactic Disaster season's challenge pages."""

    def __init__(self, parent, context):
        super().__init__(parent, context)
        self._tips = Tooltip(self.colors)
        # {page: (column frame, heading frame, heading, count, Text)},
        # and {page: (heading frame, heading, count)} in the finished
        # column. Built once and shown or hidden; never rebuilt.
        self._columns = {}
        self._finished = {}
        # What each Text and each count shows, so a refresh that changes
        # nothing touches nothing.
        self._drawn = {}
        # {tag: the tip's words}: read when the pointer stops, so a tip
        # bound when its row was first drawn says what the row says now.
        self._tip_words = {}
        self._blink_phase = 0
        self._blink_after = None
        self._blinking = []
        self._tick_after = None
        self.setup_ui()
        self.refresh_disaster()
        # **NOT redundant with the load paths:** a refresh while another
        # tab is showing reads the data and skips the drawing.
        self.when_shown(self.refresh_disaster)

    # ------------------------------------------------------------ build

    def setup_ui(self):
        """Build the Galactic Disaster tab UI."""
        # **Created first**: the audit reaches the columns through the
        # tab's first child.
        columns = ttk.Frame(self.frame)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        columns.pack(fill=tk.BOTH, expand=True, padx=px(COLUMNS_PADX),
                     pady=px(COLUMNS_PADY))
        columns.grid_rowconfigure(0, weight=1)
        self._holder = columns
        for page in disaster_challenges.PAGES:
            self._columns[page] = self._build_page(columns)
        # The finished pages: a grid of a row per page, its heading flush
        # left, then its count in two halves, the done figure right-aligned
        # and `/total` left-aligned, so every row's slash falls in one
        # column. A row is gridded only while its page is finished.
        finished = ttk.Frame(columns)
        self._finished_frame = finished
        for page in disaster_challenges.PAGES:
            # NOT padding between two elements: the two halves of one
            # count, each giving back its side of a label's own inset so
            # the slash sits against the figure as in one string.
            self._finished[page] = (
                make_heading(finished, ""),
                ttk.Label(finished, text="", font=HEADING_COUNTDOWN_FONT,
                          anchor=tk.E, padding=px((0, 0, -COUNT_JOIN, 0))),
                ttk.Label(finished, text="", font=HEADING_COUNTDOWN_FONT,
                          anchor=tk.W, padding=px((-COUNT_JOIN, 0, 0, 0))))
        # What stands instead of the columns when there are no pages to
        # show, and why.
        self._note = ttk.Label(self.frame, text="", font=ROW_FONT,
                               foreground=self.colors["fg_dim"])

    def _build_page(self, parent):
        """One page's column: its heading and count, and the Text of its
        requirements under them. Not placed: `_lay_out` grids it."""
        column = ttk.Frame(parent)
        # The heading and its count travel together, centred over the
        # column, as on the Checklist.
        head = ttk.Frame(column)
        head.pack(anchor=tk.CENTER)
        heading = make_heading(head, "")
        heading.pack(side=tk.LEFT, anchor=tk.S)
        count = self._count_label(head)
        text = tk.Text(
            column, wrap=tk.WORD, width=1, height=1, bd=0,
            highlightthickness=px(0), padx=px(0), pady=px(0),
            bg=self.colors["bg"], fg=self.colors["fg"], font=ROW_FONT,
            # Selectable but never focusable, and no insertion cursor:
            # the words can be copied, and nothing invites typing.
            takefocus=0, insertwidth=px(0), cursor="arrow")
        # spacing: exception -- panel ↕ unrelated label -- heading, frame ↕
        text.pack(fill=tk.BOTH, expand=True, pady=px((HEADING_GAP, 0)))
        # spacing: exception -- label row -> label row -- run, run ↕
        for tag, pitch in LINE_PITCH.items():
            text.tag_configure(tag, spacing1=px(pitch))
        text.tag_configure(LOCKED_TAG, foreground=self.colors["fg_dim"])
        text.config(state=tk.DISABLED)
        return column, head, heading, count, text

    def _count_label(self, head):
        """A heading's `done/total`, beside it on its baseline."""
        count = ttk.Label(head, text="", font=HEADING_COUNTDOWN_FONT)
        # spacing: heading ↔ element -- heading, label ↔
        # spacing: heading ↔ element -- heading, label ↕
        count.pack(side=tk.LEFT, anchor=tk.S,
                   padx=px((HEADING_COUNTDOWN_GAP, 0)),
                   pady=px((0, HEADING_COUNTDOWN_DROP)))
        return count

    # ----------------------------------------------------------- update

    def refresh_disaster(self):
        """Read the loaded snapshot and draw it. Called after every load,
        after the game client is read, and whenever the tab is shown.
        Nothing here records, so a hidden tab waits to be shown."""
        if self.is_hidden():
            return
        raw = getattr(self.optimizer, "raw_data", None) or {}
        self._draw(disaster_challenges.board(raw, time.time()))
        self._tick_restart()

    def _draw(self, board):
        if board.note:
            self._holder.pack_forget()
            self._note.config(text=board.note)
            # spacing: content frame -> content frame -- frame, frame ↔↕
            self._note.pack(anchor=tk.NW, padx=px(COLUMNS_PADX),
                            pady=px(COLUMNS_PADY))
            self._blinking = []
            self._blink_restart()
            return
        self._note.pack_forget()
        if not self._holder.winfo_manager():
            # spacing: content frame -> content frame -- frame, frame ↔↕
            # spacing: tab list -> first element -- tab, frame ↕
            self._holder.pack(fill=tk.BOTH, expand=True,
                              padx=px(COLUMNS_PADX), pady=px(COLUMNS_PADY))
        pages = {page.page: page for page in board.pages}
        open_pages = [page for page in disaster_challenges.PAGES
                      if page in pages
                      and not disaster_challenges.finished(pages[page])]
        done_pages = [page for page in disaster_challenges.PAGES
                      if page in pages
                      and disaster_challenges.finished(pages[page])]
        for page in open_pages:
            self._fill_page(pages[page])
        self._blinking = []
        for page in done_pages:
            heading, done, total = self._finished[page]
            heading.config(text=pages[page].title,
                           foreground=self.colors[FINISHED_COLOUR])
            done.config(text="%d" % pages[page].done)
            total.config(text="/%d" % pages[page].total)
            if pages[page].unclaimed:
                self._blinking.extend((done, total))
            else:
                for half in (done, total):
                    half.config(foreground=self.colors[FINISHED_COLOUR])
        self._lay_out(open_pages, done_pages)
        self._blink_restart()

    def _count_words(self, page):
        return "%d/%d" % (page.done, page.total)

    def _fill_page(self, page):
        """One open page's heading, count and requirements, each touched
        only where it changed."""
        _column, _head, heading, count, text = self._columns[page.page]
        heading.config(text=page.title)
        count.config(text=self._count_words(page),
                     foreground=self.colors[UNCLAIMED_COLOUR
                                            if page.unclaimed else "fg"])
        lines = tuple((row.text, row.tip, row.id) for row in page.rows) \
            + tuple((words, None, None) for words in page.locked)
        if self._drawn.get(page.page) == lines:
            return
        self._drawn[page.page] = lines
        top = text.yview()[0]
        text.config(state=tk.NORMAL)
        text.delete("1.0", tk.END)
        for index, row in enumerate(page.rows):
            tags = [FIRST_TAG if index == 0 else ROW_TAG]
            if row.tip:
                tag = TIP_PREFIX + row.id
                self._tip_words[tag] = "\n".join(row.tip)
                if tag not in text.tag_names():
                    self._tips.bind_tag(
                        text, tag, lambda t=tag: self._tip_words.get(t))
                tags.append(tag)
            text.insert(tk.END, ("\n" if index else "") + row.text,
                        tuple(tags))
        for index, words in enumerate(page.locked):
            first = not page.rows and index == 0
            text.insert(tk.END, ("" if first else "\n") + words,
                        (FIRST_TAG if first else ROW_TAG, LOCKED_TAG))
        text.config(state=tk.DISABLED)
        # A rewrite keeps where the reader had scrolled to: a long page
        # runs past the window's foot and is read with the wheel.
        text.yview_moveto(top)

    def _lay_out(self, open_pages, done_pages):
        """Grid the open pages left to right, sharing the width, and the
        finished column at the right while any page is finished. Only
        where the split moved: the clock redraws every minute."""
        split = (tuple(open_pages), tuple(done_pages))
        if self._drawn.get(_LAYOUT) == split:
            return
        self._drawn[_LAYOUT] = split
        for page in disaster_challenges.PAGES:
            if page not in open_pages:
                self._columns[page][0].grid_remove()
        self._lay_out_finished(done_pages)
        if not done_pages:
            self._finished_frame.grid_remove()
        laid = [self._columns[page][0] for page in open_pages] + (
            [self._finished_frame] if done_pages else [])
        # Content in the EVEN grid columns, a fixed spacer between each
        # pair. A gap padded inside a cell of the uniform group widens
        # that cell's share by the gap, and its column comes out
        # narrower than the one without it.
        for index in range(2 * len(disaster_challenges.PAGES) + 1):
            self._holder.grid_columnconfigure(index, weight=0, uniform="",
                                              minsize=0)
        for at, widget in enumerate(laid):
            if at:
                # spacing: control group ↔ control group -- run, run ↔
                self._holder.grid_columnconfigure(2 * at - 1,
                                                  minsize=px(COLUMN_GAP))
            if widget is self._finished_frame:
                # Alone, the finished column still keeps to the right.
                self._holder.grid_columnconfigure(
                    2 * at, weight=0 if open_pages else 1)
                widget.grid(row=0, column=2 * at, sticky="ne")
            else:
                self._holder.grid_columnconfigure(2 * at, weight=1,
                                                  uniform="pages")
                widget.grid(row=0, column=2 * at, sticky="nsew")

    def _lay_out_finished(self, done_pages):
        """A row per finished page, in the game's order; none for the
        rest."""
        for row, page in enumerate(disaster_challenges.PAGES):
            heading, done, total = self._finished[page]
            if page not in done_pages:
                for widget in (heading, done, total):
                    widget.grid_remove()
                continue
            above = FINISHED_PITCH if page != done_pages[0] else 0
            # spacing: exception -- label row -> label row -- heading, heading ↕
            heading.grid(row=row, column=0, sticky="sw",
                         pady=px((above, 0)))
            # The count on the heading's baseline, as on an open page.
            # spacing: heading ↔ element -- heading, label ↔
            # spacing: heading ↔ element -- heading, label ↕
            done.grid(row=row, column=1, sticky="se",
                      padx=px((HEADING_COUNTDOWN_GAP, 0)),
                      pady=px((above, HEADING_COUNTDOWN_DROP)))
            total.grid(row=row, column=2, sticky="sw",
                       pady=px((above, HEADING_COUNTDOWN_DROP)))

    # ------------------------------------------------------------ clock

    def _tick_restart(self):
        """Reread the clock every `TICK_MS` while the tab is showing."""
        if self._tick_after is not None:
            try:
                self.frame.after_cancel(self._tick_after)
            except tk.TclError:
                pass
        self._tick_after = self.frame.after(TICK_MS, self._tick)

    def _tick(self):
        self._tick_after = None
        if not self.is_hidden():
            self.refresh_disaster()

    def _blink_restart(self):
        """Blink the finished pages' counts with a reward waiting, from
        the bright step, while the tab shows; stop on the bright step
        while nothing blinks."""
        if self._blink_after is not None:
            try:
                self.frame.after_cancel(self._blink_after)
            except tk.TclError:
                pass
            self._blink_after = None
        self._blink_phase = 0
        self._blink_paint()
        if self._blinking:
            self._blink_after = self.frame.after(BLINK_MS, self._blink_step)

    def _blink_step(self):
        self._blink_after = None
        if self.is_hidden():
            self._blink_phase = 0
            self._blink_paint()
            return
        self._blink_phase = 1 - self._blink_phase
        self._blink_paint()
        self._blink_after = self.frame.after(BLINK_MS, self._blink_step)

    def _blink_paint(self):
        name = WARN_BLINK_COLOURS[self._blink_phase]
        try:
            for count in self._blinking:
                count.config(foreground=self.colors.get(name, name))
        except tk.TclError:
            pass                         # the tab went away mid-blink
