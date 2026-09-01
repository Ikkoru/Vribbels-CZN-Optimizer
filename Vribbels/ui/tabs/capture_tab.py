"""Capture tab for intercepting game data."""

import re
import tkinter as tk
from tkinter import ttk, messagebox
import threading
from capture import check_prerequisites, CaptureError
from capture.constants import SERVERS
from game_data.characters import CHARACTERS, ATTRIBUTE_COLORS
from ..base_tab import BaseTab
from ..utils.button_width import BUTTON_W_MEDIUM
from ..utils.checkbox import make_checkbox
from ..utils.scrolled_text import make_scrolled_text
from ..utils.tab_header import make_tab_header


# Log Preset checkboxes per row when the checklist's width is not
# knowable -- before the frame is realized, and in a headless build. The
# count is DERIVED from the width everywhere else; see
# `_log_preset_columns`.
LOG_PRESET_COLUMNS_FALLBACK = 6

# Gap between those columns, in pixels. A FLOOR, not a distance: the
# columns size to the preset names in them and the names are the user's,
# so what renders is 8 only where a column holds its widest possible
# name and more everywhere else. NOT TRACKED for that reason -- the
# audit compares against a number, and there is no number here.
#
# 8 is the point below which names would start to run together, which is
# what makes it the constraint the column count is solved against. It is
# a floor the count RESPECTS rather than one the grid enforces: the
# solver never returns a count the panel cannot hold, so the last column
# clips against the panel edge before any two names close up.
LOG_PRESET_COLUMN_GAP = 8


def _log_preset_grid_width(widths, columns):
    """What `columns` columns of these labels take, gaps included.

    Placement is row-major, so column `c` holds `widths[c::columns]` and
    the grid gives that column its OWN widest member. Summing per column
    is the whole of it: `max(widths) * columns` reserves room for as
    many copies of the longest preset name as there are columns, and the
    names differ by a factor of four -- enough to refuse a layout that
    fits with a hundred pixels to spare.
    """
    per = [max(widths[c::columns]) for c in range(columns)
           if widths[c::columns]]
    return sum(per) + max(0, len(per) - 1) * LOG_PRESET_COLUMN_GAP

# What the Region readout says before a capture has seen a connection.
REGION_UNKNOWN = "not detected yet"
# ...and when two games on different servers are running at once.
REGION_CONFLICT = (
    "two servers at once -- close one game and capture again"
)

# At or below this, a fragment's ceiling is not worth reading and is
# drawn in warning yellow rather than green. A JUDGEMENT, not a
# threshold anything computes: 40 is where the maintainer stops
# caring, on a 0-100 Gear Score.
LOG_VALUE_POOR = 40

# One value in a `Highest ...` list: `21-80` or, where the fragment
# has no upgrades left, `80`. Anchored on the separator that starts
# every part, so the digits in a preset NAME are never matched.
LOG_VALUE_RE = re.compile(r"(?:: |, )(\d+)(?:-(\d+))?")

# The word that says what happened, and how to read it. `Created` is
# neither good nor bad -- a fragment arriving is news.
LOG_EVENT_TAGS = {
    "Upgraded": "event_good",
    "Deleted": "event_bad",
    "Created": "event_new",
}


class CaptureTab(BaseTab):
    """
    Capture tab for intercepting and capturing game data via proxy.

    Provides controls for starting/stopping capture, viewing logs,
    and loading captured data.
    """

    def __init__(self, parent, context):
        super().__init__(parent, context)

        # Status label widgets
        self.capture_status_label = None
        self.capture_info_label = None
        self.capture_start_btn = None
        self.capture_stop_btn = None
        self.capture_log = None
        # Log Presets checklist (column 2)
        self.log_presets_list_frame = None
        self._log_preset_vars = {}
        # The column count currently on screen. A <Configure> rebuild
        # happens only when the width would change it.
        self._log_preset_columns_shown = None
        # Upgrade Log mismatch filters (column 2, below the checklist)
        self.ignore_atkdef_var = None
        self.ignore_element_var = None
        self.ignore_dps_hp_var = None
        self.ignore_dps_ego_var = None
        # True once log_upgrade_msg has set the upg_start/upg_end marks
        # (rewrite_last_upgrade_line no-ops before the first upgrade).
        self._has_upgrade_marks = False
        # Worker hand-off for the prerequisite probe: (status, ips) once
        # _probe_capture_prerequisites finishes, None until then.
        self._prereq_result = None
        # Set by that same worker when it finds a hosts-file redirect left
        # behind by an earlier run: (message, tag) for the UI thread to
        # log, or None when the file was clean.
        self._stale_hosts_note = None

        self.setup_ui()
        self.refresh_log_presets()

        # The addon learns the region from the first connection's SNI
        # and reports it up through the proxy reader thread.
        if self.context.capture_manager is not None:
            self.context.capture_manager.region_callback = \
                self.set_detected_region
        # Rebuild the checklist whenever the user switches TO this tab, so
        # preset assignment changes made in other tabs are always reflected
        # without cross-tab notification plumbing.
        self.context.notebook.bind(
            "<<NotebookTabChanged>>", self._on_tab_changed, add="+"
        )

        # Auto-check prerequisites after UI setup
        self.root.after(500, self.check_capture_prerequisites)

    def setup_ui(self):
        """Setup the Capture tab UI."""
        main_frame = ttk.Frame(self.frame)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # The sides and bottom absorb the notebook's removed client inset
        # so this tab sits where it did (see Flush.TNotebook in
        # czn_optimizer_gui). The top is 0 instead -- see top_columns
        # below for the nesting level that pays for it.
        main_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))

        # Everything above the Capture Log sits in a two-column grid:
        # column 1 = the capture controls, column 2 = the Upgrade Log
        # settings taking whatever is left. weight=0 gives the left
        # column exactly what its content asks for; an equal-weight
        # `uniform` pair would force a 50/50 split and ignore that
        # request entirely.
        top_columns = ttk.Frame(main_frame)
        # spacing: tab list -> first element -- tab, frame ↕
        # spacing: panel ↕ unrelated label -- panel, title ↕
        # Two components, two rules. The TRAILING one is the smaller
        # share of the gap down to the Capture Log panel's title, which
        # is text -- the rest is on that panel's own leading pady, which
        # is where corrections go because this one is shared by both
        # columns above it.
        # pady top is 0, not 2: this tab has an extra nesting level that
        # the other tabs don't (main_frame -> top_columns -> left_col),
        # so a value here would stack on top of one the other tabs never
        # pay and drop the heading below theirs.
        top_columns.pack(fill=tk.X, pady=(0, 2))
        # Column 0 takes what its widest child asks and column 1 takes
        # the rest, so that child is what sets the Upgrade Log Settings
        # panel's width: every pixel it gives up is one the panel gains.
        # There is no minsize, and one would have to clear the button
        # row's own request to do anything at all -- below that it never
        # binds, and above it the panel beside this column loses width
        # to a number nothing derives.
        top_columns.grid_columnconfigure(0, weight=0)
        top_columns.grid_columnconfigure(1, weight=1)

        left_col = ttk.Frame(top_columns)
        # spacing: content frame -> content frame -- frame, frame ↔
        # The widest lever on this tab: everything down the left side is
        # a child of this frame, so its padx positions the heading,
        # Status, Server Region, Requirements and the button row at once.
        left_col.grid(row=0, column=0, sticky="nsew", padx=2)
        # There is no width clamp here, and one cannot usefully be added:
        # this frame's children are PACKED, and Tk keeps the propagation
        # flag per geometry manager, so `grid_propagate(False)` on it
        # sets a flag nothing reads while pack propagation stays on. A
        # `configure(width=...)` beside it is overridden the same way.
        # The column is as wide as its widest child asks, full stop.

        # spacing: border edge -> first non-button element -- panel, label ↔↕
        # The label and the checkbox column below it read the same
        # inset, so this padding is the lever for both. The TOP
        # component cannot go below 0 and the rule asks for less than a
        # label's line box gives, so that gap is corrected on the label
        # instead.
        right_col = ttk.LabelFrame(top_columns, text="Upgrade Log Settings",
                                   padding=(2, 0, 2, 3))
        # spacing: tab list -> first element -- tab, panel ↕
        # The pady top lands this LabelFrame's title on the same line as
        # the left column's heading: a LabelFrame title has no internal
        # leading above it, where the 14pt heading beside it keeps a
        # little after its negative padding.
        right_col.grid(row=0, column=1, sticky="nsew", padx=2, pady=(3, 0))

        # spacing: border edge -> first non-button element -- panel, label ↔
        # spacing: explanation text -> the controls it explains -- label, checkbox ↕
        # The negative TOP is the panel's top inset, not this label's own
        # placement: the frame's padding is already 0 there and the rule
        # asks for one pixel less than a label's line box gives, so the
        # last pixel has to come out of the label's inset. The trailing
        # pady is the separate gap down to the checkboxes.
        ttk.Label(
            right_col,
            padding=(0, -1, 0, 0),
            text="Assigned presets compared in the Upgraded log lines' "
                 "Highest Potential. Checking or unchecking a preset "
                 "excludes it (and re-writes the last Upgraded line).",
            foreground=self.colors["fg_dim"], justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=(0, 0), pady=(0, 0))

        # Mismatch filters, bottom-left, two columns. Packed BEFORE the
        # checklist so the checklist's expand=True doesn't swallow the
        # cavity these need. Global (settings.json), all on by default;
        # toggling one re-writes the last Upgraded line, as a preset
        # toggle does.
        options_frame = ttk.Frame(right_col)
        # spacing: checkboxes -> unrelated checkboxes -- checkbox, checkbox ↕
        # NOT TRACKED, and cannot usefully be: `side=tk.BOTTOM` pins this
        # block to the panel's floor, so what sits between it and the
        # checklist above is whatever height is left over. The rule's 20 is a MINIMUM here,
        # and the audit compares against a number rather than a floor.
        options_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(17, 0))
        options_frame.grid_columnconfigure(1, weight=1)

        sm = self.context.settings_manager

        def _filter_checkbox(text, key, row, column):
            var = tk.BooleanVar(
                value=(bool(sm.get(key, True)) if sm is not None else True)
            )
            # spacing: element and its label ↔ element and its label -- checkbox, checkbox ↔
            make_checkbox(
                options_frame, self.colors, text=text, variable=var,
                command=lambda: self._on_log_filter_toggle(key, var),
            # spacing: checkbox/slider ↕ checkbox/slider rows -- checkbox, checkbox ↕
            # These sit below the `checkboxes -> unrelated checkboxes`
            # division, and needed the ordinary pitch of their own -- the
            # division says how far the block starts from what is above
            # it, not how its rows sit among themselves.
            ).grid(row=row, column=column, sticky=tk.W,
                   padx=(0, 4) if column == 0 else 0,
                   pady=(0 if row == 0 else 3, 0))
            return var

        self.ignore_atkdef_var = _filter_checkbox(
            "Don't show presets on ATK/DEF mismatch",
            "upgrade_log_ignore_atkdef_mismatch", 0, 0)
        self.ignore_element_var = _filter_checkbox(
            "Don't show presets on Element mismatch",
            "upgrade_log_ignore_element_mismatch", 1, 0)
        self.ignore_dps_hp_var = _filter_checkbox(
            "Don't show DPS presets for HP% MFs",
            "upgrade_log_ignore_dps_hp", 0, 1)
        self.ignore_dps_ego_var = _filter_checkbox(
            "Don't show DPS presets for Ego MFs",
            "upgrade_log_ignore_dps_ego", 1, 1)

        self.log_presets_list_frame = ttk.Frame(right_col)
        self.log_presets_list_frame.pack(fill=tk.BOTH, expand=True)
        # How many columns of presets fit is solved from this frame's
        # width, so a resize is what changes the answer.
        self.log_presets_list_frame.bind(
            "<Configure>", self._reflow_log_presets, add="+")

        # Title and subtitle share one line, bottom-aligned (as on the
        # Gear Score tab).
        # x_trim, where the other two tabs pass nothing: this tab nests
        # one level deeper (main_frame -> top_columns -> left_col), so
        # the accumulated container padding starts its heading right of
        # theirs and this brings it back level.
        make_tab_header(
            left_col, self.colors, "Data Capture",
            "Capture game data by intercepting API traffic", x_trim=-3)

        # spacing: exception -- border edge -> first non-button element -- panel, label ↔↕
        # The LEFT inset deliberately does not meet it, and the panel is
        # left out of the audit for that; see docs/ui_spacing.md.
        status_frame = ttk.LabelFrame(left_col, text="Status", padding=(4, 1, 5, 2))
        # spacing: content frame -> content frame -- frame, frame ↕
        # The trailing side feeds the gap down to Server Region's title,
        # which answers to `panel ↕ unrelated label` -- the lever for
        # that one is on the panel BELOW, so this stays symmetric.
        status_frame.pack(fill=tk.X, pady=2)

        # spacing: header subtext -- label, label ↔
        # "Ready" and the hint sit on one line, the hint bottom-aligned
        # against the larger status font.
        status_row = ttk.Frame(status_frame)
        status_row.pack(fill=tk.X)

        self.capture_status_label = ttk.Label(status_row, text="Ready",
                                               font=("Segoe UI", 11))
        self.capture_status_label.pack(side=tk.LEFT, anchor=tk.S)

        self.capture_info_label = ttk.Label(status_row,
                                             text="Click 'Start Capture' to begin",
                                             foreground=self.colors["fg_dim"])
        # The pady is what seats the hint on the status line: `anchor=S`
        # aligns the two BOXES, and a Segoe UI 9 box holds less below its
        # baseline than a Segoe UI 11 one, so without a lift the hint
        # sits low. It is one pixel less than it looks like it should be
        # -- 2 put the hint a pixel ABOVE the line rather than on it.
        self.capture_info_label.pack(side=tk.LEFT, anchor=tk.S,
                                     padx=(10, 0), pady=(0, 1))

        # spacing: border edge -> first non-button element -- panel, label ↔↕
        region_frame = ttk.LabelFrame(left_col, text="Server Region", padding=(1, 2, 4, 2))
        # spacing: panel ↕ unrelated label -- panel, title ↕
        # spacing: content frame -> content frame -- frame, frame ↕
        # Asymmetric, because the two sides answer to different rules.
        # ABOVE is the Status panel's border against this panel's own
        # TITLE: text is what sits across that gap, and the nearer
        # element decides. BELOW is an ordinary frame-to-frame gap --
        # the button row under it draws no border to measure to.
        region_frame.pack(fill=tk.X, padx=0, pady=(5, 2))

        region_inner = ttk.Frame(region_frame)
        region_inner.pack(fill=tk.X)

        # A READOUT, not a choice. Both regions are redirected during a
        # capture and the addon forwards each connection to its own
        # server, so which one the game uses is the game's business --
        # there is nothing for the user to get wrong, and nothing to
        # select. This reports what was observed.
        # spacing: heading ↔ element -- label, label ↔
        # A heading with its value beside it, not a label against its
        # element: at this distance the two read as a pair of blocks
        # rather than one naming the other.
        ttk.Label(region_inner, text="Region:").pack(side=tk.LEFT, padx=(0, 8))

        self.region_var = tk.StringVar(value=REGION_UNKNOWN)
        # spacing: heading ↔ element -- label, label ↔
        self.detected_label = ttk.Label(
            region_inner,
            textvariable=self.region_var,
            foreground=self.colors["fg_dim"],
        )
        self.detected_label.pack(side=tk.LEFT)

        # spacing: button -> button -- button, button ↔
        # The trailing padx on each button below is the lever for the gap
        # BETWEEN them. The button rule reaches no further here: it is
        # `border edge -> internal button`, and these sit in a plain
        # frame rather than inside a panel, so their offset from the
        # tab's edge answers to the frame rule on this frame's own pack.
        btn_frame = ttk.Frame(left_col)
        # spacing: content frame -> content frame -- frame, frame ↕
        btn_frame.pack(fill=tk.X, pady=(1, 2))

        self.capture_start_btn = ttk.Button(btn_frame, text="Start Capture",
                                             command=self.start_capture, width=BUTTON_W_MEDIUM)
        self.capture_start_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.capture_stop_btn = ttk.Button(btn_frame, text="Stop Capture",
                                            command=self.stop_capture,
                                            width=BUTTON_W_MEDIUM, state=tk.DISABLED)
        self.capture_stop_btn.pack(side=tk.LEFT, padx=(0, 4))

        ttk.Button(btn_frame, text="Open Snapshots",
                   command=self.open_snapshots_folder, width=BUTTON_W_MEDIUM).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Load Latest",
                   command=self.load_latest_capture, width=BUTTON_W_MEDIUM).pack(side=tk.LEFT)

        self.debug_var = tk.BooleanVar(value=False)
        # wraplength breaks the label over two lines so it does not push
        # the button row wider. The row is usually the widest thing in
        # the left column, and the column's width is what the Upgrade
        # Log Settings panel beside it does not get.
        self.debug_checkbox = make_checkbox(
            btn_frame, self.colors, text="Debug WS",
            variable=self.debug_var, wraplength=35,
        )
        # Enable to log every WebSocket message to a websocket_debug_*.jsonl
        # file in the snapshots folder — useful when adding support for new
        # packet types (e.g., fragment create/delete).
        # spacing: border edge -> first non-button element -- button, checkbox ↔
        # spacing: exception -- border edge -> first non-button element -- checkbox, panel ↔
        # A lone non-button after a run of buttons, which is what this
        # rule is about. Not a second element-and-label pair: there is
        # no pair here, only the one checkbox.
        #
        # Its OTHER side answers to the same rule and misses it by the
        # widget's own inset, unavoidably. This row is the widest thing
        # in `left_col` -- `btn_frame` and `left_col` both request the
        # same width and the row's parts sum to exactly it -- so the
        # checkbox's box right edge IS the column edge, and what follows
        # is 2 + 2 of grid padx out to Upgrade Log Settings' border. That
        # 4 is the rule. The extra 2 is this widget: `padx=1` a side, and
        # a pixel of the final `g`'s right sidebearing.
        #
        # **Neither of those 2 pixels can be spent.** `padx=0` would
        # narrow the checkbox, and with it the column, and with THAT the
        # right border of every panel stacked above -- they all fill X,
        # so `Requirements -> Upgrade Log Settings` would widen by
        # exactly what this gap lost.
        self.debug_checkbox.pack(side=tk.LEFT, padx=(2, 0))

        # spacing: border edge -> first non-button element -- panel, label ↔↕
        # Left and right padding match, and the right one only renders
        # while this text is the widest thing in the column: the frame
        # fills the column, so anything past the longest line is slack
        # that no padding here reaches.
        req_frame = ttk.LabelFrame(left_col, text="Requirements", padding=(2, 0, 2, 0))
        # spacing: panel ↕ unrelated label -- button, title ↕
        # ABOVE is the capture button row against this panel's own TITLE:
        # text is what sits across that gap, so the label rule governs
        # and this side carries the correction, the button row's own
        # trailing pad being shared with the gap up to Server Region.
        #
        # BELOW is 0, and it has to be. This is the last thing packed in
        # left_col, and left_col is the taller of the two columns, so its
        # height IS the grid row's -- a pad here would sit below this
        # border and push the row down, taking the right column's border
        # with it while leaving this one where it is. That is the whole
        # of the distance the two columns end out of level by.
        req_frame.pack(fill=tk.X, pady=(3, 0))

        requirements_text = """- Run as Administrator (required for hosts file modification)
- Certificate installed (see Setup tab)
- Game must be closed before starting capture
- Start capture, then launch the game and load into the main menu
- Keep capture running to see live updates as you make changes
- If you stop the capture, close the game before starting a new capture"""

        # spacing: border edge -> first non-button element -- panel, label ↔↕
        # The panel's padding is 0 top and bottom and has to stay
        # there (see the pack below), so this label's own inset is
        # the only lever left on either gap.
        ttk.Label(req_frame, text=requirements_text, justify=tk.LEFT,
                  padding=(0, -1, 0, -1)).pack(anchor=tk.W)

        # spacing: content frame -> content frame -- frame, frame ↔
        # spacing: panel ↕ unrelated label -- panel, title ↕
        # The padx answers to the frame rule: it and main_frame's own sum
        # to the gap from the window edge, matching every other bordered
        # panel. The pady does not -- above this panel is the bottom
        # border of the ones in top_columns, and below that border sits
        # this panel's own TITLE, so the gap is text-facing.
        #
        # BOTH columns of top_columns end above this title, so this pad
        # sets two gaps at once and they are only one number while the
        # columns end level. Both are registered for that reason: when
        # the two entries disagree, the difference is how far out of
        # level they are, and the pad below Requirements is what puts
        # them there.
        #
        # No frame padding: the text inset lives on the Text's own
        # padx/pady, so its lighter background reaches the frame border.
        log_frame = ttk.LabelFrame(main_frame, text="Capture Log", padding=0)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=(5, 2))

        # spacing: border edge -> first non-button element -- panel, text ↔↕
        # The panel's inset sits here rather than on the LabelFrame,
        # inside the text widget's own lighter background. The pady has
        # the line box's leading above the first glyph netted out of it,
        # which is why it differs between text panels in different fonts.
        # The helper carries the dark palette, zeroes Tk's default border
        # and focus ring, and pairs the Text with a ttk scrollbar in a
        # ttk frame so the theme reaches both. See
        # ui/utils/scrolled_text.py.
        # spacing: exception -- border edge -> first non-button element -- panel, text ↕
        # The TOP misses the rule and cannot reach it: `pady` is at 0,
        # the LabelFrame carries none, and what is left above the
        # first CAPITAL is this face's own line box. The only lever
        # on it is a smaller face.
        # 0, where the helper's default is 3: at this face and size
        # the line box already carries the whole inset above the
        # first glyph. **There is no lever left below 0** -- read the
        # top gap again after any font change here.
        self.capture_log = make_scrolled_text(
            log_frame, self.colors, height=15, wrap=tk.WORD,
            font=("Segoe UI Variable Small", 11), pady=0,
        )
        self.capture_log.pack(fill=tk.BOTH, expand=True)

        self.capture_log.tag_configure("success", foreground=self.colors["green"])
        self.capture_log.tag_configure("error", foreground=self.colors["red"])
        self.capture_log.tag_configure("warning", foreground=self.colors["yellow"])
        self.capture_log.tag_configure("info", foreground=self.colors["accent"])

        # Tags for parts of a line rather than the whole of one, and
        # DELIBERATELY not the four above even where the colour is the
        # same. Tk resolves a conflict between two tags on one range by
        # the order they were CREATED, latest winning -- so a word tag
        # sharing a name with a line tag would be outranked wherever the
        # line's own tag happened to be newer. Created last, these
        # always win inside their own span.
        self.capture_log.tag_configure("event_good",
                                       foreground=self.colors["green"])
        self.capture_log.tag_configure("event_bad",
                                       foreground=self.colors["red"])
        self.capture_log.tag_configure("value_good",
                                       foreground=self.colors["green"])
        self.capture_log.tag_configure("value_poor",
                                       foreground=self.colors["yellow"])
        self.capture_log.tag_configure("value_floor",
                                       foreground=self.colors["yellow_dim"])
        self.capture_log.tag_configure("event_new",
                                       foreground=self.colors["blue_light"])
        self.capture_log.tag_configure("preset_name",
                                       foreground=self.colors["preset"])

    def _colour_log_line(self, start: str, msg: str):
        """Tag the parts of one log line that carry a verdict.

        Which event it was, and how good each number is -- neither of
        which the line's own tag can say, because a tag covers the whole
        insert. See `LOG_VALUE_POOR` for where the yellow starts.

        Values are found by the SEPARATOR in front of them rather than
        by shape: every part of a `Highest ...` list begins with its
        number, right after `": "` or `", "`, so a digit inside a preset
        name is never mistaken for one. A preset named with `, 12` in it
        would still fool this; nothing else would.
        """
        t = self.capture_log

        def span(first, last, tag):
            t.tag_add(tag, f"{start}+{first}c", f"{start}+{last}c")

        for word, tag in LOG_EVENT_TAGS.items():
            at = msg.find(word)
            if at >= 0:
                span(at, at + len(word), tag)

        head = msg.find("Highest ")
        if head < 0:
            return
        found = list(LOG_VALUE_RE.finditer(msg, head))
        for index, m in enumerate(found):
            floor, ceiling = m.group(1), m.group(2)
            if ceiling is None:
                # One number: the fragment has no upgrades left, so this
                # IS the ceiling rather than a range's start.
                span(m.start(1), m.end(1), self._value_tag(floor))
            else:
                span(m.start(1), m.end(1), "value_floor")
                span(m.start(2), m.end(2), self._value_tag(ceiling))
            # The rest of the part is the preset's name. It ends where
            # the NEXT part's separator begins rather than at the next
            # comma, so a name holding one keeps its colour.
            after = m.end() + 1
            until = (found[index + 1].start()
                     if index + 1 < len(found) else len(msg))
            if after < until:
                span(after, until, "preset_name")

    @staticmethod
    def _value_tag(value: str) -> str:
        try:
            return ("value_poor" if int(value) <= LOG_VALUE_POOR
                    else "value_good")
        except ValueError:
            return "value_good"

    def capture_log_msg(self, msg: str, tag: str = None):
        """Add a message to the capture log.

        Safe to call from any thread. Tk is single-threaded, and this is
        reached from the capture manager's proxy-reader thread and the
        prerequisite worker as well as from the UI, so an off-thread call
        is marshalled onto the UI thread rather than touching the widget
        directly.
        """
        if threading.current_thread() is not threading.main_thread():
            try:
                self.root.after(0, lambda: self.capture_log_msg(msg, tag))
            except (RuntimeError, tk.TclError):
                # after() from another thread needs the main thread to be
                # inside mainloop. Outside it (startup, shutdown) there is
                # no log to write into anyway, so drop the line rather
                # than kill the calling thread.
                pass
            return
        start = self.capture_log.index("end-1c")
        self.capture_log.insert(tk.END, f"{msg}\n", tag)
        self._colour_log_line(start, msg)
        self.capture_log.see(tk.END)

    def log_upgrade_msg(self, msg: str, tag: str = None):
        """capture_log_msg for '[LIVE] Upgraded' lines: also remembers the
        line's extent via Tk marks so a Log Presets toggle can rewrite the
        LAST Upgraded line in place (rewrite_last_upgrade_line). LEFT
        gravity on both marks keeps them pinned to this line while later
        messages append after it."""
        t = self.capture_log
        t.mark_set("upg_start", "end-1c")
        t.mark_gravity("upg_start", tk.LEFT)
        start = t.index("end-1c")
        t.insert(tk.END, f"{msg}\n", tag)
        self._colour_log_line(start, msg)
        t.mark_set("upg_end", "end-1c")
        t.mark_gravity("upg_end", tk.LEFT)
        self._has_upgrade_marks = True
        t.see(tk.END)

    def rewrite_last_upgrade_line(self, msg: str, tag: str = None):
        """Replace the last Upgraded line (recorded by log_upgrade_msg)
        with `msg`. The end mark flips to RIGHT gravity for the insert so
        it lands after the new text, then back to LEFT so subsequent
        appends at the log's end don't drag it along."""
        if not self._has_upgrade_marks:
            return
        t = self.capture_log
        try:
            t.mark_gravity("upg_end", tk.RIGHT)
            t.delete("upg_start", "upg_end")
            start = t.index("upg_start")
            t.insert("upg_start", f"{msg}\n", tag)
            self._colour_log_line(start, msg)
            t.mark_gravity("upg_end", tk.LEFT)
        except tk.TclError:
            pass

    def _on_tab_changed(self, event):
        """Rebuild the Log Presets checklist when this tab becomes the
        selected one (cheap; assignment changes happen in other tabs)."""
        try:
            if event.widget.nametowidget(event.widget.select()) is self.frame:
                self.refresh_log_presets()
        except Exception:
            pass

    def refresh_log_presets(self):
        """Rebuild the Log Presets checklist from current assignments.

        One row per DISTINCT preset name assigned to >=1 combatant. A row
        is checked iff ANY of its combatants' flags is selected; toggling
        writes the flag on ALL combatants assigned to that preset. The
        persistence is per-combatant res_id (settings/log_presets.json),
        which survives preset renames and reassignments.
        """
        frame = self.log_presets_list_frame
        if frame is None:
            return
        for w in frame.winfo_children():
            w.destroy()
        self._log_preset_vars = {}

        cpm = self.context.character_preset_manager
        pm = self.context.preset_manager
        lpm = self.context.log_presets_manager
        if cpm is None or pm is None or cpm.is_corrupted():
            return

        preset_to_ids: dict = {}
        for rid, preset in cpm.assignments_by_id.items():
            if preset and pm.has_preset(preset):
                preset_to_ids.setdefault(preset, []).append(rid)

        if not preset_to_ids:
            ttk.Label(frame, text="No presets assigned yet.",
                      foreground=self.colors["fg_dim"]).grid(
                          row=0, column=0, sticky=tk.W)
            return

        # Built before they are placed, because the column count is
        # SOLVED from how wide they turn out to be. A widget's own
        # `winfo_reqwidth()` is the real answer as soon as it exists;
        # estimating from font metrics runs a few pixels small per name
        # and the error is what clips the last column.
        made = []
        for name in sorted(preset_to_ids):
            ids = preset_to_ids[name]
            checked = (any(lpm.is_selected(r) for r in ids)
                       if lpm is not None else True)
            var = tk.BooleanVar(value=checked)
            cb = make_checkbox(
                frame, self.colors, text=name, variable=var,
                fg=self._preset_element_colour(ids),
                command=lambda n=name, v=var: self._on_log_preset_toggle(n, v),
            )
            made.append((name, cb, var))

        columns = self._log_preset_columns(
            frame, [cb.winfo_reqwidth() for _n, cb, _v in made])
        self._log_preset_columns_shown = columns

        # Every column but the LAST absorbs the leftover width. Sizing
        # them all alike instead (weight + uniform) makes the last column
        # as wide as the widest label in the whole grid, and the distance
        # from its own label to the panel edge is then that difference
        # rather than the frame-edge rule's gap.
        for c in range(columns):
            frame.grid_columnconfigure(c, weight=0 if c == columns - 1 else 1)
        # Columns a narrower list no longer uses keep their weight and go
        # on absorbing width, which pulls the visible ones together.
        for c in range(columns, frame.grid_size()[0]):
            frame.grid_columnconfigure(c, weight=0, minsize=0)

        for idx, (name, cb, var) in enumerate(made):
            column = idx % columns
            # spacing: element and its label ↔ element and its label -- checkbox, checkbox ↔
            # Leading pad, so the last column ends at its own label and
            # the panel's frame-edge padding is the only gap after it.
            # spacing: checkbox/slider ↕ checkbox/slider rows -- checkbox, checkbox ↕
            cb.grid(row=idx // columns, column=column,
                    sticky=tk.W,
                    padx=(0 if column == 0 else LOG_PRESET_COLUMN_GAP, 0),
                    pady=(0 if idx < columns else 3, 0))
            self._log_preset_vars[name] = var

    def _log_preset_columns(self, frame, widths):
        """The most columns these labels fit in, gaps included.

        The names in these columns are the USER's presets, so no stated
        count can be right for everyone: six columns of short names
        waste the panel, and six of long ones do not fit in it. What is
        fixed is `LOG_PRESET_COLUMN_GAP`, the point below which two
        names stop reading as two -- so the count is the largest `n`
        whose columns still leave it.

        Every `n` is tried rather than stopping at the first that does
        not fit. What a column costs depends on which names land in it,
        so the requirement is not monotonic in `n`: a count can fit
        where a smaller one did not.

        This does NOT make the rendered gap a number. The columns take
        what is left over, so anything but the widest name in a column
        sits further from its neighbour, which is why nothing tracks it.

        Falls back to a stated count only where the width cannot be had:
        before the frame is realized, and in a headless build.
        """
        width = frame.winfo_width()
        if width <= 1:
            # Draining pending geometry gives the TRUE allocated width,
            # so the count computed here is the final one. Safe only
            # because the main window is invisible for the whole of
            # startup -- the drain paints, and painting a half-built
            # window is what being hidden prevents.
            frame.update_idletasks()
            width = frame.winfo_width()
        if width <= 1:
            return LOG_PRESET_COLUMNS_FALLBACK
        if not widths:
            return 1
        return max((n for n in range(1, len(widths) + 1)
                    if _log_preset_grid_width(widths, n) <= width),
                   default=1)

    def _reflow_log_presets(self, _event=None):
        """Rebuild the checklist when the width would change its shape.

        Guarded on the COUNT rather than on the width: a resize fires a
        burst of <Configure>, and rebuilding on each would destroy and
        recreate every checkbox in the panel several times a drag.
        """
        frame = self.log_presets_list_frame
        if frame is None or not self._log_preset_vars:
            return
        # Creation order is the order they were placed in, so a child's
        # index is what decides its column -- reading the widths in this
        # order is what lets the solver ask what each column costs.
        widths = [w.winfo_reqwidth() for w in frame.winfo_children()]
        if not widths:
            return
        if self._log_preset_columns(frame, widths) != \
                getattr(self, "_log_preset_columns_shown", None):
            self.refresh_log_presets()

    def _preset_element_colour(self, res_ids):
        """The shared Element colour of a preset's combatants, or None.

        A preset assigned to combatants of one Element is drawn in that
        Element's colour; a preset spanning several stays on the default
        foreground, because there is no one colour that would be honest.
        Unknown combatants -- captured but not yet in CHARACTERS -- count
        as a distinct Element for this, so a preset covering one is never
        coloured on incomplete information.
        """
        elements = set()
        for rid in res_ids:
            # assignments_by_id is keyed by str(res_id) (the v2 schema);
            # CHARACTERS is keyed by int. Looking up the string finds
            # nothing and every preset silently reads as "unknown
            # Element", which looks exactly like "no shared Element".
            try:
                entry = CHARACTERS.get(int(rid))
            except (TypeError, ValueError):
                entry = None
            elements.add(entry.get("attribute") if entry else None)
            if len(elements) > 1:
                return None
        if len(elements) != 1:
            return None
        return ATTRIBUTE_COLORS.get(elements.pop())

    def _on_log_preset_toggle(self, preset_name: str, var):
        """Persist a checklist toggle to every combatant assigned to this
        preset, then re-render the last Upgraded line against the new
        selection."""
        cpm = self.context.character_preset_manager
        lpm = self.context.log_presets_manager
        if cpm is None or lpm is None or cpm.is_corrupted():
            return
        ids = [rid for rid, p in cpm.assignments_by_id.items()
               if p == preset_name]
        lpm.set_selected(ids, bool(var.get()))
        recompute = self.context.recompute_upgrade_line_callback
        if recompute is not None:
            recompute()

    def _on_log_filter_toggle(self, key: str, var):
        """Persist one of the Upgrade Log mismatch filters, then re-render
        the last Upgraded line against the new setting."""
        sm = self.context.settings_manager
        if sm is not None:
            sm.set(key, bool(var.get()))
        recompute = self.context.recompute_upgrade_line_callback
        if recompute is not None:
            recompute()

    def check_capture_prerequisites(self):
        """Report capture prerequisites in the log.

        The probing happens on a worker thread: `check_prerequisites()`
        shells out to mitmdump and `resolve_game_server()` does DNS, and
        neither may run on the UI thread. A blocked `after()` callback
        stops Tk processing events at all, which locks up the entire
        program behind a painted, dead window.
        """
        self.capture_log_msg("Checking prerequisites...")
        self._prereq_result = None
        self._stale_hosts_note = None
        threading.Thread(
            target=self._probe_capture_prerequisites, daemon=True
        ).start()
        self._poll_capture_prerequisites()

    def _poll_capture_prerequisites(self, attempts: int = 0):
        """Wait for the worker's findings, then log them.

        The worker can't hand them over itself: `after()` from another
        thread only works while the main thread is inside `mainloop()`,
        and this check is scheduled during startup, so the worker can
        finish while the main thread is still in the reveal's `update()`
        passes -- or after mainloop has exited, if the window is closed
        first. Either way Tk raises "main thread is not in main loop".
        The worker therefore only assigns a plain attribute and this
        main-thread `after` chain does everything Tk-facing.
        """
        if self._prereq_result is None:
            if attempts < 200:
                self.root.after(
                    100, lambda: self._poll_capture_prerequisites(attempts + 1))
            return
        status, ips = self._prereq_result
        self._apply_capture_prerequisites(status, ips)

    def _probe_capture_prerequisites(self):
        """Worker body for check_capture_prerequisites: run the blocking
        calls, then publish the outcome for the UI thread's poll. Touches
        no widgets and makes no Tk calls."""
        # A redirect left in the hosts file by a run that ended without
        # removing it makes every game-server lookup answer with this
        # machine -- including the one start_capture uses to choose the
        # proxy's upstream, which would then be the proxy itself. Clear it
        # before anything resolves anything. It also means the game itself
        # could not have connected, so the removal is worth reporting.
        #
        # Not while a capture is running, though: the redirect is doing its
        # job then, and removing it would cut the session off mid-flight.
        try:
            if (not self.context.capture_manager.is_capturing()
                    and self.context.capture_manager.remove_hosts_redirect()):
                self._stale_hosts_note = (
                    "[!] Removed a leftover capture redirect from the "
                    "hosts file",
                    "warning",
                )
        except CaptureError as e:
            self._stale_hosts_note = (f"[!] {e}", "warning")

        try:
            status = check_prerequisites()
        except Exception:
            status = None

        ips = {}
        # Resolving is pointless without mitmproxy -- the original flow
        # bailed out at that point too.
        if status is not None and status.has_mitmproxy:
            try:
                self.context.capture_manager.resolve_game_server()
                ips = dict(
                    self.context.capture_manager.game_server_ips or {}
                )
            except Exception:
                ips = {}

        self._prereq_result = (status, ips)

    def _apply_capture_prerequisites(self, status, ips: dict):
        """Log the worker's findings and set the Start button state.
        Runs on the UI thread."""
        if self._stale_hosts_note is not None:
            self.capture_log_msg(*self._stale_hosts_note)

        if status is None:
            self.capture_log_msg("[X] Could not check prerequisites", "error")
            self.capture_start_btn.config(state=tk.DISABLED)
            return

        if status.is_admin:
            self.capture_log_msg("[OK] Running as Administrator", "success")
        else:
            self.capture_log_msg("[!] Not running as Administrator", "warning")

        if status.has_mitmproxy:
            self.capture_log_msg(f"[OK] mitmproxy version {status.mitmproxy_version}", "success")
        else:
            self.capture_log_msg("[X] mitmproxy not found!", "error")
            self.capture_log_msg("  See Setup tab", "info")
            self.capture_start_btn.config(state=tk.DISABLED)
            return

        if status.has_certificate:
            self.capture_log_msg("[OK] Certificate found", "success")
        else:
            self.capture_log_msg("[!] Certificate not found - see Setup tab", "warning")

        self.capture_log_msg("Resolving game servers...")
        if ips:
            for host, ip in ips.items():
                self.capture_log_msg(f"  {host} -> {ip}")
            self.capture_log_msg("[OK] Ready to capture!", "success")
        else:
            self.capture_log_msg("[X] Could not resolve game servers", "error")
            self.capture_start_btn.config(state=tk.DISABLED)

    def start_capture(self):
        """Start capture using CaptureManager."""
        try:
            # No region to set: both are redirected and the addon routes
            # each connection to its own server.
            self.region_var.set(REGION_UNKNOWN)
            self.debug_checkbox.config(state=tk.DISABLED)

            self.context.capture_manager.start_capture(debug_mode=self.debug_var.get())
            self.capture_start_btn.config(state=tk.DISABLED)
            self.capture_stop_btn.config(state=tk.NORMAL)
            self.capture_info_label.config(
                text="Keep running for live updates."
            )
        except CaptureError as e:
            # The debug checkbox was disabled for the duration of a
            # capture that never began; hand it back or it stays dead
            # until one does.
            self.debug_checkbox.config(state=tk.NORMAL)
            messagebox.showerror("Capture Error", str(e))

    def stop_capture(self):
        """Stop the capture and report which region it saw."""
        result = self.context.capture_manager.stop_capture()

        self.debug_checkbox.config(state=tk.NORMAL)
        self.capture_start_btn.config(state=tk.NORMAL)
        self.capture_stop_btn.config(state=tk.DISABLED)
        self.capture_info_label.config(text="Check snapshots folder for your data")

        if result:
            captured_file, detected_region = result
            self.set_detected_region(detected_region)
            self.capture_log_msg(f"Capture file: {captured_file.name}",
                                 "success")

    def set_detected_region(self, region_id):
        """Show which server region the capture actually talked to.

        Reached from the proxy reader thread as well as from
        stop_capture, so it only touches a StringVar.
        """
        if region_id in (None, ""):
            self.region_var.set(REGION_UNKNOWN)
            return
        if region_id == "conflict":
            self.region_var.set(REGION_CONFLICT)
            return
        config = SERVERS.get(region_id)
        self.region_var.set(config.display_name if config else str(region_id))
        # Remembered only so the readout can open on the last known
        # answer; nothing about the capture depends on it any more.
        try:
            self.context.config.server_region = region_id
        except Exception:
            pass

    def open_snapshots_folder(self):
        """Open snapshots folder using CaptureManager."""
        self.context.capture_manager.open_snapshots_folder()

    def load_latest_capture(self):
        """Load most recent capture file using CaptureManager."""
        latest = self.context.capture_manager.get_latest_capture()
        if latest:
            self.context.load_data_callback(str(latest))
            self.context.switch_tab_callback(self.context.notebook.nametowidget(
                self.context.notebook.tabs()[0]
            ))
        else:
            messagebox.showinfo("No Captures", "No capture files found.")
