"""Checklist tab: what resets, and how often.

Four headed columns, one per reset period, each listing the things that
come back on it. Most rows are LABELS ONLY: what they are waiting for
is completion status, and the capture carries the first pieces of it --
`point_entity` for the daily and weekly activity totals,
`mission_entities` for a per-mission `complete_time`, and
`season_pass_entity` for the Arkhianon Supply's rank. See
`docs/capture_pipeline.md`.

One row reads a value: the day's activity total, out of a hundred, in
the alert colour where the day is not finished.

The columns are built the way the Materials tab's are: content in the
EVEN grid columns with an empty expanding one between each pair, so the
block spans the window and the gaps across it stay equal. A row is one
Text per column rather than a Label per line -- a tab switch re-runs
the geometry managers over every widget on the page, and forty labels
is forty of them.
"""

import tkinter as tk
from tkinter import ttk
from tkinter import font as tkfont

from ..base_tab import BaseTab
from ..utils.scrolled_text import make_scrolled_text
from ..utils.tab_header import make_heading
from ui.scaling import px


# Each column's heading and its rows, left to right. Read off the
# game: the wording is the game's own where it has one, and `$hop`
# marks a shop tab rather than a currency.
#
# **A column's rows are its own.** `Arkhianon Supply` appears under
# three headings because it resets three ways -- a daily set of
# missions, a weekly set, and the pass itself -- and they are three
# different things to check rather than one row repeated.
COLUMNS = (
    ("Daily", (
        "Coffee",
        "Activity (Dailies)",
        "Arkhianon Supply",
        "Dates",
        "Delegation",
        "Other Events",
    )),
    ("Weekly", (
        "Nono's Shop",
        "$hop - Memory Archive - Traveler",
        "Arkhianon Supply",
        "Simulation Challenges",
        "Chaos & Sortie Currency",
        "Seasonal Event(s)",
        "Seasonal Shop",
        "Seasonal Accumulated Score",
    )),
    ("Monthly", (
        "Nono's Shop",
        "$hop - Memory Archive - Traveler",
        "$hop - Zeronium Shop",
        "$hop - Blackhorn Trade",
        "$hop - Exchange Shop - Prism Module",
    )),
    ("Other", (
        "Basin of Hyperspace (21 days)",
        "Zero System Chaos Matrix (84? days)",
        "Arkhianon Supply (42? days)",
        "Seasonal Event (21 + 21 + 21 days)",
        "Sortie (21 days)",
        "Other Events",
    )),
)

# The rows' face. The headings use the shared helper's own.
ROW_FONT = ("Segoe UI", 9)

# The one row that reads a value so far, and what it is read against.
# `point_entity.day_point` is the day's ACTIVITY total and a hundred is
# a full day; anything short is drawn in the alert colour, which is the
# whole of what the row says today.
ACTIVITY_ROW = "Activity (Dailies)"
ACTIVITY_FULL = 100
POINT_FIELD = "point_entity"

# What a value reads before any snapshot has reached the tab. NOT `0`,
# which is what an untouched day reads: nothing claimed and nothing
# recorded are different answers.
NO_DATA = "-"

# What separates one row from the next, as `spacing1` on every line
# after the first. A lever a rendered distance short of the rule: a
# Text line's own box already carries part of the pitch, and unlike a
# padding this cannot go negative.
ROW_PITCH = 4           # spacing: label row -> label row -- run, run ↕

# A row's words against its value, which is a left TAB STOP. A lever
# short of the rule, the words stopping inside their own advance.
LABEL_TO_VALUE = 6      # spacing: label ↔ its element -- run, run ↔

# The heading of a column against the first row under it. The gap runs
# from the heading's BASELINE to the row's CAPITAL, with the heading's
# box below its baseline and the row's box above its capital both
# inside it -- which is why the lever is at its floor.
HEADING_GAP = 0         # spacing: panel ↕ unrelated label -- heading, frame ↕

# What a Text puts around its own content, both sides together. Its
# `width` is in CHARACTERS and this block is sized in pixels, so the
# holder is fixed and the Text fills it.
TEXT_INSET = 2

# ---- the mission listing, TEMPORARY --------------------------------
#
# Every mission the capture carries, with what it reports, so the ids
# can be read off the screen and written into `docs/missions_id.tsv`.
# **Delete this block and its four constants once the missions are
# identified**; the rows above are what the tab is for.
DEBUG_MISSIONS = True
DEBUG_TITLE = "Mission ids (temporary)"
DEBUG_ROWS = 12         # visible lines; the rest scroll
DEBUG_COLS = 40         # characters, which is the widest line plus room
DEBUG_FONT = ("Consolas", 9)

# The field the missions arrive under, and what a row says when it has
# been finished. A `content_*` row never carries `complete_time` at
# all, so the two readings are not "done" and "not done" -- they are
# "reported done" and "said nothing".
MISSION_FIELD = "mission_entities"
DONE = "done"
NOT_DONE = "-"


class ChecklistTab(BaseTab):
    """The recurring-task columns."""

    def __init__(self, parent, context):
        super().__init__(parent, context)
        # (Text, rows) per column heading, for the refresh to rewrite.
        self.column_texts = {}
        # The temporary mission listing, or None while it is switched off.
        self.mission_text = None
        self.setup_ui()
        # Drawn once with nothing, so the tab is its rows rather than a
        # blank before the first capture.
        self.refresh_checklist()

    # ------------------------------------------------------------ build

    def setup_ui(self):
        """Build the Checklist tab UI."""
        # **Created before anything else on the tab.** The audit reaches
        # the columns through the tab's FIRST CHILD, and `winfo_children`
        # is in creation order -- so a block built ahead of this one
        # takes that position and every Checklist entry skips, silently.
        # `checks/check_tabs_build.py` holds it there.
        columns = ttk.Frame(self.frame)

        # Packed before the columns, which is a separate order: pack
        # hands each widget its requested size in turn and only then
        # gives the leftover to whatever expands.
        if DEBUG_MISSIONS:
            self._build_mission_list()

        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        columns.pack(fill=tk.BOTH, expand=True, padx=px(2), pady=px((0, 2)))

        # Content in the EVEN grid columns, an empty expanding one
        # between each pair. Given to spacers of one uniform group the
        # leftover width lands as equal gaps with the block flush
        # against both edges; shared out inside the content cells it
        # lands unequally, the widest column keeping the least.
        for index in range(len(COLUMNS) + 1):
            columns.grid_columnconfigure(2 * index, weight=0)
        for index in range(len(COLUMNS)):
            # spacing: content frame -> content frame -- frame, frame ↔
            # NOT TRACKED: the distance is whatever the tab has spare
            # divided four ways, so it moves with the window. What is
            # fixed is that the four are equal.
            columns.grid_columnconfigure(2 * index + 1, weight=1,
                                         uniform="checklist")
        columns.grid_rowconfigure(0, weight=1)

        for index, (title, rows) in enumerate(COLUMNS):
            column = ttk.Frame(columns)
            column.grid(row=0, column=2 * index, sticky="nsew")
            self._build_column(column, title, rows)

    def _build_column(self, parent, title, rows):
        """One heading and the rows under it."""
        make_heading(parent, title).pack(anchor=tk.CENTER)

        font = tkfont.Font(font=ROW_FONT)
        # The words, plus a column reserved for the widest reading any
        # row can show. RESERVED rather than fitted: a column that
        # sized to its content would move every row's words the moment
        # a figure gained a digit.
        labels = max(font.measure(row) for row in rows) + TEXT_INSET
        stop = labels + LABEL_TO_VALUE
        holder = tk.Frame(parent, width=stop + font.measure(_widest_value()),
                          height=self._block_height(len(rows)),
                          bg=self.colors["bg"])
        holder.pack_propagate(False)
        # spacing: panel ↕ unrelated label -- heading, frame ↕
        holder.pack(anchor=tk.N, pady=px((HEADING_GAP, 0)))

        text = tk.Text(
            holder, wrap=tk.NONE, bd=0, highlightthickness=px(0),
            padx=px(0), pady=px(0),
            bg=self.colors["bg"], fg=self.colors["fg"], font=ROW_FONT,
            # Selectable but never focusable, and no insertion cursor:
            # the rows can be copied, and nothing about them invites
            # typing.
            takefocus=0, insertwidth=px(0), cursor="arrow",
            # A LEFT stop: a row's reading sits beside its own words
            # rather than at the block's far edge, where it would read
            # as belonging to the column instead of to the row.
            tabs=(stop,),
        )
        text.pack(fill=tk.BOTH, expand=True)
        # spacing: label row -> label row -- run, run ↕
        text.tag_configure("row", spacing1=px(ROW_PITCH))
        # The colour is the whole of what a short reading says.
        text.tag_configure("alert", foreground=self.colors["red"])
        self.column_texts[title] = (text, rows)

    def _build_mission_list(self):
        """The temporary mission listing, bottom left. See DEBUG_MISSIONS."""
        # spacing: out of scope -- a temporary listing of mission ids, deleted once they are identified
        block = ttk.Frame(self.frame)
        block.pack(side=tk.BOTTOM, anchor=tk.W, padx=px(4), pady=px((0, 4)))
        ttk.Label(block, text=DEBUG_TITLE,
                  foreground=self.colors["fg_dim"]).pack(anchor=tk.W)
        self.mission_text = make_scrolled_text(
            block, self.colors, width=DEBUG_COLS, height=DEBUG_ROWS,
            wrap=tk.NONE, font=DEBUG_FONT, takefocus=0)
        self.mission_text.pack(anchor=tk.W)

    @staticmethod
    def _block_height(rows):
        """A column's height: its rows and the pitch between them.

        Measured off the face rather than multiplied by a guess -- a
        Text sizes in LINES and this block is pinned in pixels, so the
        two have to be reconciled somewhere.
        """
        return (rows * tkfont.Font(font=ROW_FONT).metrics("linespace")
                + (rows - 1) * px(ROW_PITCH))

    # ----------------------------------------------------------- update

    def refresh_checklist(self):
        """Redraw every reading from the loaded snapshot.

        Called automatically after data loads. A snapshot with no
        `point_entity` -- one taken before the capture kept it -- reads
        `-`: nothing claimed and nothing recorded are different answers
        and a zero would say the first.
        """
        if not self.column_texts:
            return
        raw = getattr(self.optimizer, "raw_data", None) or {}
        point = raw.get(POINT_FIELD)
        day = point.get("day_point") if isinstance(point, dict) else None
        if isinstance(day, int) and not isinstance(day, bool):
            reading = ("%d/%d" % (day, ACTIVITY_FULL), day != ACTIVITY_FULL)
        else:
            reading = ("%s/%d" % (NO_DATA, ACTIVITY_FULL), False)
        for text, rows in self.column_texts.values():
            self._fill(text, rows,
                       {ACTIVITY_ROW: reading} if ACTIVITY_ROW in rows else {})
        if self.mission_text is not None:
            self._fill_missions(raw.get(MISSION_FIELD))

    def _fill_missions(self, missions):
        """Rewrite the temporary mission listing. See DEBUG_MISSIONS.

        Takes either shape the field comes in: the addon's cache, keyed
        by res_id, or a bare list off the wire.
        """
        rows = missions.values() if isinstance(missions, dict) else missions
        lines = []
        for row in rows or ():
            if not isinstance(row, dict) or not row.get("res_id"):
                continue
            res_id = str(row["res_id"])
            lines.append((_family(res_id), res_id,
                          "%-24s %8s  %s" % (
                              res_id, row.get("score", ""),
                              DONE if row.get("complete_time") else NOT_DONE)))
        lines.sort()
        body = (LINE_SEP.join(line for _, _, line in lines) if lines
                else "no missions in this snapshot")
        self.mission_text.config(state=tk.NORMAL)
        self.mission_text.delete("1.0", tk.END)
        self.mission_text.insert(tk.END, body)
        self.mission_text.config(state=tk.DISABLED)

    @staticmethod
    def _fill(text, rows, readings):
        """Rewrite one column: its rows, and any reading beside one.

        `readings` maps a row's words to (value, alert). Written whole
        rather than patched line by line -- a Text has no per-line
        assignment, and the block is small.
        """
        text.config(state=tk.NORMAL)
        text.delete("1.0", tk.END)
        for index, row in enumerate(rows):
            value, alert = readings.get(row, (None, False))
            text.insert(tk.END, (LINE_SEP if index else "") + row, "row")
            if value is not None:
                text.insert(tk.END, COLUMN_SEP + value,
                            ("row", "alert") if alert else "row")
        text.config(state=tk.DISABLED)


# What separates one row from the next, and a row from its value.
# Named because a Text's columns ARE its tabs and its rows ARE its
# newlines -- so these two characters are structure rather than
# punctuation.
LINE_SEP = "\n"
COLUMN_SEP = "\t"


def _family(res_id):
    """The id's leading words, which is the set it belongs to.

    Groups the listing the way `docs/missions_id_dump.py` groups the
    file it is read into. Split at the first NUMBERED segment: the
    numbers are the mission within its set, and how many of them an id
    carries varies between sets.
    """
    parts = []
    for part in res_id.split("_"):
        if part.isdigit():
            break
        parts.append(part)
    return "_".join(parts) or res_id


def _widest_value():
    """The widest reading any row can show.

    Stated rather than derived: the only value so far is an activity
    total out of a hundred, and a column reserved for the widest form
    it can take does not move when the figure does.
    """
    return "%d/%d" % (ACTIVITY_FULL, ACTIVITY_FULL)
