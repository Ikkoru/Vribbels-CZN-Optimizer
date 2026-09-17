"""Setup & Settings: first-time configuration, and the app's own switches.

TWO COLUMNS, and the split is what the widths mean. The LEFT is fixed
to what the instructions need to read without wrapping, so `Setup
Status`, the two setup buttons and `Setup Instructions` share one edge
down the column's whole length. Everything left over goes to the RIGHT,
where `Restore Defaults`, `Update Status` and `Settings` stack at one
width and one x. The last row is `Links` and `Application Information`,
one in each column, held to ONE height.

`Setup Instructions` is as tall as its text and no taller: a fixed
block that never grows, so a panel sized to hold it exactly holds all
of it.

The `Settings` panel holds what the program does rather than what the
game holds: the UI scale and the optimizer's worker count. **Both take
effect on the next launch** -- the scale is read before any widget
exists and the worker count when a run starts -- which is why each says
so beside itself.

`Restore Defaults` opens one modal per defaultable file, restoring
missing defaults and replacing changed ones at per-entry granularity.
The three kinds share `_open_restore_dialog` and differ in four things:
which file under `default_settings/` is the source, how missing and
changed are computed, which manager call applies a restoration, and
whether the right frame shows a Rename column (presets only).
"""

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont
import json
import copy
import subprocess
import ctypes
import threading
import webbrowser
from pathlib import Path
import sys
from capture import setup_certificate, open_certificate, find_mitmdump
from ..base_tab import BaseTab
from ..utils.all_none_row import make_all_none_row
from ..utils.button_width import (BUTTON_W_LARGE, BUTTON_W_MEDIUM,
                                 BUTTON_W_SMALL)
from ..utils.checkbox import make_checkbox
from ..utils.escape import close_on_escape
from ..utils.scrolled_text import make_scrolled_text
from ..utils.tab_header import make_tab_header
from defaults_sync import resolve_defaults_dir
from ui.scaling import px
from ui import scaling
from ui.update_check import (
    GITHUB_REPO, RELEASES_HTML_URL, UpdateStatus, current_version)


_RENAME_PLACEHOLDER = "Rename current preset to..."


def _pady_pair(value):
    """A pack `pady` as (leading, trailing), whatever shape it is in.

    Tk hands one back as an int, a two-tuple, or a space-separated
    string depending on how it was set -- and a reader that assumed one
    of those would drop the other half of an asymmetric pad.
    """
    if isinstance(value, (tuple, list)):
        pair = list(value)
    else:
        pair = str(value).split()
    numbers = []
    for part in pair:
        try:
            numbers.append(int(part))
        except (TypeError, ValueError):
            numbers.append(0)
    if not numbers:
        return 0, 0
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return numbers[0], numbers[1]

# Restore Defaults panel geometry.
#
# The explanation beside each button wraps to two lines, and a Label's
# box is taller than the lines it holds. Left alone it is the taller
# child of its row, which puts the row height on the TEXT and makes the
# button gap `row padding + (text height - button height)` -- so the
# button rule could not be applied directly at all. Trimming the box to
# its line boxes hands the row height back to the button.
#
# LEVERS, not rendered distances: neither rule is in the spacing audit
# yet, so measure before trusting them. The button-to-explanation pad
# below IS tracked now, and it is two pixels short of the gap it renders
# -- a lever is what is left after the label's own inset.
RESTORE_ROW_GAP = 4     # spacing: button -> button -- button, button ↕
RESTORE_EDGE_PAD = 3    # spacing: border edge -> button -- panel, button ↔↕
RESTORE_TEXT_TRIM = -2  # spacing: button -> button -- button, button ↕

# The first column of Restore Defaults against the second. The first
# column's own width is its widest explanation, so this is the whole of
# the distance between the two.
RESTORE_COLUMN_GAP = 8  # spacing: control group ↔ control group -- label, button ↔

# The face the instructions are set in, and what a panel adds around a
# text block of that face. The width of the LEFT COLUMN is computed
# from the two -- see `_instructions_width` -- so a wrap in the
# instructions means one of these is short rather than that the text
# needs rewriting.
INSTRUCTIONS_FONT = ("Segoe UI Variable Small", 11)
INSTRUCTIONS_PAD = 4    # spacing: border edge -> first non-button element -- panel, text ↔

# What a LabelFrame, a scrollbar and the Text's own inset cost around
# the widest line. MEASURED once and written down rather than derived:
# a ttk border is the theme's and a scrollbar's width is the theme's
# too, and neither is readable before the widgets exist.
INSTRUCTIONS_CHROME = 23

# The Settings panel. Its rows are a label and a control, and the two
# columns line up under each other.
# (left, top, right, bottom). Levers short of the rule -- see
# `update_check.PANEL_PAD`, which carries the same correction for the
# same reason. **The TOP is measured to the DROPDOWN, not to the label
# beside it**: a combobox is the taller of the pair and the rules run
# to whatever comes nearest the edge.
#
# **NEVER NEGATIVE.** A `ttk.LabelFrame` shrunk past 0 on a side eats
# its own BORDER there rather than the space inside it, so the panel
# loses the edge the rule measures to. The bottom correction goes on
# the last LABEL instead -- `SETTINGS_LAST_TRIM`.
SETTINGS_PAD = (1, 4, 1, 0)  # spacing: border edge -> first non-button element -- panel, dropdown ↔↕
SETTINGS_LABEL_GAP = 2  # spacing: label ↔ its element -- label, dropdown ↔
# The two columns inside the panel, and the two size readings inside the
# right one. Wider than `label ↔ its element`: these separate things
# that answer different questions, where that rule joins a pair.
SETTINGS_COLUMN_GAP = 16  # spacing: unique -- the settings panel's two columns -- dropdown, label ↔
# Two label+value pairs side by side, which is the pair rule at its own
# 8px -- LESS the chrome the reading includes and the padding does not:
# each label's own inset plus the side bearings of the glyphs that end
# and begin them. MEASURED off an audit, like `INSTRUCTIONS_CHROME`.
ARCHIVE_PAIR_CHROME = 5
ARCHIVE_SIZE_GAP = 8 - ARCHIVE_PAIR_CHROME  # spacing: element and its label ↔ element and its label -- label, label ↔

# The Compression dropdown's words, against what the setting stores.
# `Off` is a state of the same control rather than a separate switch:
# it is the same question, answered with "not at all".
ARCHIVE_WORDS = {
    "off": "Off",
    "balanced": "Balanced",
    "strongest": "Strongest",
}
ARCHIVE_NOTE = "Archives old captures. Applies on the next launch."
# The panel's own bottom pad is 0 and `SETTINGS_LAST_TRIM` gives the
# left column's last LABEL its gap back. The button is the lowest thing
# in the panel, so it carries its own rule's distance here.
ARCHIVE_BUTTON_EDGE = 3  # spacing: border edge -> button -- panel, button ↕


def _megabytes(count: int) -> str:
    """A byte count as the reader would say it, never as `0.0 MB`."""
    if count >= 1e9:
        return "%.1f GB" % (count / 1e9)
    if count >= 1e6:
        return "%.1f MB" % (count / 1e6)
    if count:
        return "%.0f KB" % max(1, count / 1e3)
    return "none"

# What the LAST line in the panel gives back to its own bottom gap. A
# `ttk.Label` carries about two pixels of inset below its glyphs, and a
# negative `padding` hands them back by shrinking the box rather than
# by moving the text. This is where the correction has to live: the
# panel's own padding cannot go negative without eating its border.
SETTINGS_LAST_TRIM = -1  # spacing: border edge -> first non-button element -- panel, label ↕
SETTINGS_NOTE_GAP = 2   # spacing: explanation text -> the controls it explains -- dropdown, label ↕
SETTINGS_ROW_GAP = 7    # spacing: config panel row ↕ row -- label, dropdown ↕

# The Links panel's own inset. Its children are flat `tk.Button`s whose
# painted edge is their fill rather than a border, which is why the
# non-button rule is the one that matches.
# (left, top, right, bottom). The sides and the ends need different
# levers: a flat button's painted edge is its FILL, which reaches
# its box on every side, so the horizontal pair is the rule itself
# while the vertical pair is two short -- the buttons' own `pady`
# supplies the rest.
LINKS_PAD = (4, 2, 4, 2)  # spacing: border edge -> first non-button element -- panel, button ↔↕

# The leading pad both bottom panels start from, before either is
# pushed down to meet the other. See `link_bottom_heights`.
BOTTOM_ROW_GAP = 5      # spacing: panel ↕ unrelated label -- panel, title ↕

# Application Information's two numbers. The panel's own inset is a
# FLOOR rather than a distance -- its content is centred in a height
# `Links` decides, so the inset is only what would be left if that
# height ever collapsed onto the block. The line gap is the pitch of the
# centred stack, and it is the same above every line but the first, so
# the block stays symmetric and centring it actually centres it.
# spacing: unique -- the Application Information stack is centred in its panel -- label, label ↕
APP_INFO_FLOOR = 4
APP_INFO_LINE_GAP = 5

# What the scale dropdown is worth, and what a change to it needs.
SCALE_NOTE = "Applies on the next launch."

# The instructions, as a module constant: the LEFT COLUMN's width is
# computed from their widest line before any widget exists, so they
# cannot be built inside the function that lays them out.
INSTRUCTIONS = """STEP 1: Generate and install certificate
  - Click "Generate & Install Cert" button
  - When the certificate dialog opens:
    1. Click "Install Certificate"
    2. Select "Local Machine"
    3. Click Next
    4. Select "Place all certificates in the following store"
    5. Click Browse and select "Trusted Root Certification Authorities"
    6. Click OK, Next, then Finish

STEP 2: Verify setup
  - Click "Check Status" to verify all components are ready
  - All items should show green checkmarks [OK]"""

# The optimizer's worker count. `Auto` is 0 in settings and `Off` is 1
# -- the optimizer takes the sequential path at one worker -- so the
# dropdown's words are mapped rather than parsed.
WORKERS_AUTO = "Auto"
WORKERS_OFF = "Off"
WORKERS_WARNING = (
    "Leave this on Auto unless you know what you are doing.\n"
    "Turning it Off makes the Optimizer MUCH slower."
)


# -------- per-kind metadata for the generalized restore dialog --------

_RESTORE_KIND_META = {
    "presets": {
        "dialog_title": "Restore Default Presets",
        "filename": "presets.json",
        "show_rename": True,
        "missing_label": "Restores all checked Gear Score presets to user file.",
    },
    "character_preset": {
        "dialog_title": "Restore Default Combatant Presets",
        "filename": "character_preset.json",
        "show_rename": False,
        "missing_label": "Restores default per-combatant preset assignments.",
    },
    "optimizer_settings": {
        "dialog_title": "Restore Default Combatant Settings",
        "filename": "optimizer_settings.json",
        "show_rename": False,
        "missing_label": "Restores default Optimizer-tab settings per Combatant.",
    },
}


class SetupTab(BaseTab):
    """The Setup & Settings tab. See the module docstring for the layout.

    `Setup Status` reports the four capture prerequisites: Python,
    mitmproxy, the certificate, and administrator privileges.
    """

    def __init__(self, parent, context):
        super().__init__(parent, context)

        # Status label widgets
        self.python_status = None
        self.mitmproxy_status = None
        self.cert_status = None
        self.admin_status = None
        # Guard against overlapping probe threads (auto-check on open +
        # an impatient Check Status click).
        self._checking = False
        # Worker hand-off: set by _probe_prerequisites, consumed by
        # _poll_probe on the UI thread. None = not finished yet.
        self._probe_result = None

        self.setup_ui()

        # Auto-check status after UI setup
        self.root.after(1000, self.check_status)

    # ====================================================================
    # UI construction
    # ====================================================================

    @staticmethod
    def _instructions_width():
        """The pixel width the instructions need to read unwrapped.

        The widest line in the block, plus what a panel puts around a
        text of that face. COMPUTED rather than measured off the built
        widgets: the left column is fixed to this and its children fill
        it, so nothing can be read back until after the size is already
        decided.
        """
        font = tkfont.Font(font=INSTRUCTIONS_FONT)
        widest = max(font.measure(line)
                     for line in INSTRUCTIONS.splitlines() or [""])
        return widest + 2 * INSTRUCTIONS_PAD + INSTRUCTIONS_CHROME

    def setup_ui(self):
        """Build the tab: two columns, and the row that closes them."""
        main_frame = ttk.Frame(self.frame)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        main_frame.pack(fill=tk.BOTH, expand=True, padx=px(2), pady=px((0, 2)))

        make_tab_header(
            main_frame, self.colors, "Setup & Settings",
            "Complete these steps before using the capture feature")

        columns = ttk.Frame(main_frame)
        # spacing: panel ↕ unrelated label -- heading, panel ↕
        # spacing: content frame -> content frame -- frame, frame ↕
        # Asymmetric, because the two sides answer to different rules.
        # ABOVE is the tab heading against Setup Status' title, text over
        # a panel, and this tab spends one nesting level more on that run
        # than the two other headed tabs -- so the leading side gives it
        # back rather than the shared header helper losing a pixel the
        # others need.
        columns.pack(fill=tk.BOTH, expand=True, pady=px((0, 2)))

        # The LEFT column is fixed to what the instructions need; the
        # RIGHT takes everything else. A frame with its propagation off
        # is what pins a pixel width -- children would otherwise size it
        # -- and the whole column is pinned rather than each panel in
        # it, so the three share one edge without three copies of the
        # number.
        left = ttk.Frame(columns, width=px(self._instructions_width()))
        left.pack_propagate(False)
        left.pack(side=tk.LEFT, fill=tk.Y)
        right = ttk.Frame(columns)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_status(left)
        self._build_setup_buttons(left)
        self._build_instructions(left)
        self._build_restore(right)
        # spacing: content frame -> content frame -- frame, frame ↔
        # spacing: panel ↕ unrelated label -- panel, title ↕
        self.update_status = UpdateStatus(
            right, self.colors, self.root, self.context.settings_manager)
        self.update_status.panel.pack(fill=tk.X, padx=px(2), pady=px((5, 2)))
        self._build_settings(right)

        # The last row of each column, and the two are held to ONE
        # height. They carry unrelated content and would otherwise end
        # at whatever their own text reached, which reads as a ragged
        # bottom edge across a row nothing else in the tab has.
        self._build_links(left)
        self._build_app_info(right)
        # ON FIRST MAP, not now and not on idle. Two readings are
        # needed and neither exists yet: a panel's own requested height
        # comes from the geometry manager having been round its
        # children, and its POSITION comes from the notebook page being
        # laid out -- which happens the first time the tab is looked
        # at. On idle, both panels still report a y of 3 and the row
        # never moves.
        self.frame.bind("<Map>", self._on_first_map, add="+")

    def _build_status(self, parent):
        """Setup Status: the four prerequisites, live."""
        # spacing: exception -- border edge -> first non-button element -- panel, label ↔↕
        # Both directions miss the rule, for two different reasons.
        #
        # LEFT misses the rule deliberately: this panel is built to read
        # before anything else on the tab and its left edge is placed
        # for that. Tracked at what it is rather than left out, so a
        # drift from it still shows.
        #
        # TOP is out of reach in any case -- a Segoe UI 11 label's ink
        # starts well below its own box top, so even a padding of 0
        # renders more than the rule asks -- and it is wanted anyway:
        # these four rows read as one block at a single pitch, so the
        # gap above the first row matches the gaps between them.
        #
        # BOTTOM is larger than it looks because the rows carry no
        # pady of their own -- it supplies the whole pitch under the
        # last row where the others split it between two neighbours.
        status_frame = ttk.LabelFrame(parent, text="Setup Status",
                                      padding=px((4, 5, 5, 6)))
        # spacing: content frame -> content frame -- frame, frame ↔↕
        status_frame.pack(fill=tk.X, padx=px(2), pady=px(2))

        # spacing: unique -- Setup Status stands apart on purpose -- label, label ↕
        # This panel is the first thing a new user sees, and the one
        # place a troubleshooter reads whether the four prerequisites
        # are live. So it is deliberately not built to the app's
        # defaults: Segoe UI 11 rather than 9, and a pitch of its own.
        # The larger font is also why its padding values differ from
        # every other panel's while its border-edge TARGET does not --
        # a Segoe UI 11 glyph starts further inside its box than a 9.
        #
        # The rows carry no pady: a Segoe UI 11 label's own line box
        # already contributes 7px above its ink and 4 below, which is
        # the whole pitch. Anything added here lands on top of that.
        for attr, text in (("python_status", "Checking Python..."),
                           ("mitmproxy_status", "Checking mitmproxy..."),
                           ("cert_status", "Checking certificate..."),
                           ("admin_status", "Checking admin rights...")):
            label = ttk.Label(status_frame, text=text,
                              font=("Segoe UI", 11))
            label.pack(anchor=tk.W)
            setattr(self, attr, label)

    def _build_setup_buttons(self, parent):
        """The two actions Setup Status is read against."""
        btn_frame = ttk.Frame(parent)
        # spacing: content frame -> content frame -- frame, frame ↕
        btn_frame.pack(fill=tk.X, pady=px((2, 2)))

        # spacing: button -> button -- button, button ↔
        # Each button's trailing pad meets the next one's leading pad, so
        # the pair sums to the gap between them. The button rule reaches
        # no further here: it is `border edge -> internal button`, and
        # these sit in a plain frame rather than inside a panel, so the
        # leading pad answers to the frame rule and matches main_frame's
        # own.
        ttk.Button(btn_frame, text="Check Status", command=self.check_status,
                   width=BUTTON_W_LARGE).pack(side=tk.LEFT, padx=px((2, 2)))
        ttk.Button(btn_frame, text="Generate & Install Cert",
                   command=self.setup_cert, width=BUTTON_W_LARGE).pack(
                       side=tk.LEFT, padx=px((2, 5)))

    def _build_instructions(self, parent):
        """Setup Instructions, as tall as its text and no taller."""
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # This padx and main_frame's own sum to the gap from the window
        # edge, matching every other bordered panel. The frame itself
        # carries no padding, so the text widget's own background reaches
        # the border; the text inset lives on the Text's padx/pady.
        instr_frame = self._instr_frame = ttk.LabelFrame(
            parent, text="Setup Instructions", padding=px(0))
        # spacing: panel ↕ unrelated label -- button, title ↕
        # The leading side carries the whole run from the button row
        # down to this panel's title.
        instr_frame.pack(fill=tk.X, padx=px(2), pady=px((5, 2)))

        # spacing: border edge -> first non-button element -- panel, text ↔↕
        # The panel's inset sits here rather than on the LabelFrame,
        # inside the text widget's own lighter background. The pady has
        # the line box's leading above the first glyph netted out of it,
        # which is why it differs between text panels in different fonts.
        # spacing: exception -- border edge -> first non-button element -- panel, text ↕
        # The TOP misses the rule and cannot reach it: `pady` is at 0,
        # the LabelFrame carries none, and what is left above the
        # first CAPITAL is this face's own line box. The only lever
        # on it is a smaller face.
        #
        # **`height` is the LINE COUNT, so the panel ends where the
        # text does.** The block is fixed and the column is as wide as
        # its widest line, so nothing wraps and a display line is a
        # logical one.
        instr_text = make_scrolled_text(
            instr_frame, self.colors, height=len(INSTRUCTIONS.splitlines()),
            wrap=tk.WORD, font=INSTRUCTIONS_FONT, pady=0,
        )
        instr_text.insert("1.0", INSTRUCTIONS)
        instr_text.config(state=tk.DISABLED)
        instr_text.pack(fill=tk.BOTH, expand=True)

    def _build_restore(self, parent):
        """Restore Defaults: three [button + explanation] rows."""
        # spacing: border edge -> button -- panel, button ↔↕
        # Every edge whose neighbour is a button carries the button
        # rule -- top, left and bottom. The right is slack, the panel
        # being stretched wider than its text.
        restore_frame = ttk.LabelFrame(
            parent, text="Restore Defaults",
            padding=px((RESTORE_EDGE_PAD, RESTORE_EDGE_PAD, 5,
                        RESTORE_EDGE_PAD)))
        # spacing: content frame -> content frame -- frame, frame ↔↕
        restore_frame.pack(fill=tk.X, padx=px(2), pady=px(2))

        button_specs = [
            (
                "Presets",
                "Restores default Gear Score presets.\nDoes NOT delete user presets.",
                "presets",
            ),
            (
                "Combatant Presets",
                "Restores default per-Combatant preset assignments.\n"
                "Does NOT delete user assignments.",
                "character_preset",
            ),
            (
                "Combatant Settings",
                "Restores default Optimizer tab settings per Combatant.\n"
                "Does NOT delete user settings.",
                "optimizer_settings",
            ),
        ]
        # TWO columns. The first is the [button + explanation] rows; the
        # second starts where the LONGEST explanation ends, so nothing
        # in it can ever overlap the words to its left however they
        # rewrap. Measured off the explanations rather than stated:
        # rewrapping one is what would move the boundary, and a number
        # written down here would not follow it.
        rows = ttk.Frame(restore_frame)
        rows.pack(side=tk.LEFT, anchor=tk.NW)
        second = ttk.Frame(restore_frame)
        # spacing: control group ↔ control group -- label, button ↔
        second.pack(side=tk.LEFT, anchor=tk.NW,
                    padx=px((RESTORE_COLUMN_GAP, 0)))

        # The window's own size is a default like any other, and this
        # is the panel that puts defaults back.
        ttk.Button(second, text="Window Size", width=BUTTON_W_LARGE,
                   command=self._restore_window_size).pack(anchor=tk.NW)

        for index, (label, explanation, kind) in enumerate(button_specs):
            row = ttk.Frame(rows)
            # spacing: button -> button -- button, button ↕
            # The gap goes on the LEADING edge of every row after the
            # first, so the last row adds nothing below itself and the
            # frame's own bottom padding is the only thing between the
            # last button and the edge.
            row.pack(fill=tk.X, anchor=tk.NW,
                     pady=px((0 if index == 0 else RESTORE_ROW_GAP, 0)))
            row.grid_columnconfigure(1, weight=1)

            # grid, not pack: `sticky` is what centres each child in the
            # row, and the same value on both is what keeps their middles
            # level whichever turns out to be taller.
            ttk.Button(
                row, text=label, width=BUTTON_W_LARGE,
                command=lambda k=kind: self._open_restore_dialog(k),
            ).grid(row=0, column=0, sticky="")
            # spacing: label ↔ its element -- button, label ↔
            # The negative vertical padding trims the label's box to its
            # own line boxes: two lines of text sit in a box 4px taller
            # than they need, and that surplus makes the LABEL the taller
            # child of the row. Trimmed, the BUTTON sets the row height,
            # so the row padding above is the button gap exactly.
            ttk.Label(
                row, text=explanation,
                foreground=self.colors["fg_dim"],
                wraplength=px(350), justify=tk.LEFT,
                padding=px((0, RESTORE_TEXT_TRIM, 0, RESTORE_TEXT_TRIM)),
            # This pad answers to the FIRST GLYPH OF EVERY LINE, not just
            # the first line's: the gap is read to the leftmost ink in the
            # whole block. Both lines start on a letter whose leading
            # column of ink is too faint to count, so the pad carries a
            # pixel it would not need if either line began on a solid
            # one. Rewrapping the text can therefore move this value --
            # it did when the explanations gained their line breaks.
            ).grid(row=0, column=1, sticky="w", padx=px((2, 0)))

    def _restore_window_size(self):
        """Put the window back to the size a fresh launch gives it.

        The POSITION is left alone: where the window sits is the user's
        answer and only its size is what this restores. `px` because
        the default is stated at 100% and the window is drawn at the
        active scale -- see `ui/scaling.py`.
        """
        self.root.geometry("%dx%d" % (px(scaling.WINDOW_W),
                                     px(scaling.WINDOW_H)))

    def _build_settings(self, parent):
        """Settings: the program's own switches, both restart-scoped."""
        settings_frame = self._settings_frame = ttk.LabelFrame(
            parent, text="Settings", padding=px(SETTINGS_PAD))
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- panel, title ↕
        settings_frame.pack(fill=tk.X, padx=px(2), pady=px((5, 2)))

        sm = self.context.settings_manager

        # Two columns. The left one is the program's own switches; the
        # right one is the capture archive, which is about the DISK
        # rather than about how the program runs -- a different question
        # from the two beside it, so it is a column and not more rows.
        # **`fill=X` and no `expand`**, like every other row in the
        # panel. A frame that also fills the HEIGHT paints its own
        # background down the whole interior, and the left-edge reading
        # then meets that fill instead of the first label's glyph -- one
        # pixel earlier, for a distance nothing moved.
        columns = ttk.Frame(settings_frame)
        columns.pack(fill=tk.X, anchor=tk.W)
        left = ttk.Frame(columns)
        left.pack(side=tk.LEFT, anchor=tk.NW)
        # spacing: unique -- the settings panel's two columns -- dropdown, label ↔
        right = ttk.Frame(columns)
        right.pack(side=tk.LEFT, anchor=tk.NW, fill=tk.Y,
                   padx=px((SETTINGS_COLUMN_GAP, 0)))
        settings_frame = left

        # ---- UI scale ------------------------------------------------
        scale_row = ttk.Frame(settings_frame)
        scale_row.pack(fill=tk.X, anchor=tk.W)
        ttk.Label(scale_row, text="UI scale:").pack(side=tk.LEFT)
        self.ui_scale_var = tk.StringVar(
            value=(sm.get("ui_scale", scaling.DEFAULT_SCALE)
                   if sm is not None else scaling.DEFAULT_SCALE))
        scale_box = ttk.Combobox(
            scale_row, textvariable=self.ui_scale_var, state="readonly",
            values=list(scaling.SCALE_CHOICES),
            width=max(len(word) for word in scaling.SCALE_CHOICES) + 1)
        # spacing: label ↔ its element -- label, dropdown ↔
        scale_box.pack(side=tk.LEFT, padx=px((SETTINGS_LABEL_GAP, 0)))
        self.ui_scale_var.trace_add(
            "write", lambda *_: self._save_setting("ui_scale",
                                                   self.ui_scale_var.get()))
        # spacing: explanation text -> the controls it explains -- dropdown, label ↕
        ttk.Label(settings_frame, text=SCALE_NOTE,
                  foreground=self.colors["fg_dim"]).pack(
                      anchor=tk.W, pady=px((SETTINGS_NOTE_GAP, 0)))

        # ---- optimizer workers ---------------------------------------
        workers_row = ttk.Frame(settings_frame)
        workers_row.pack(fill=tk.X, anchor=tk.W, pady=px((SETTINGS_ROW_GAP, 0)))
        # RED, and the warning under it too: this is the one setting on
        # the tab that makes the program worse if it is touched without
        # a reason.
        ttk.Label(workers_row, text="Optimizer cores:",
                  foreground=self.colors["red"]).pack(side=tk.LEFT)
        self.workers_var = tk.StringVar(
            value=self._workers_word(sm.get("optimizer_workers", 0)
                                     if sm is not None else 0))
        choices = self._workers_choices()
        workers_box = ttk.Combobox(
            workers_row, textvariable=self.workers_var, state="readonly",
            values=choices, width=max(len(word) for word in choices) + 1)
        # spacing: label ↔ its element -- label, dropdown ↔
        workers_box.pack(side=tk.LEFT, padx=px((SETTINGS_LABEL_GAP, 0)))
        self.workers_var.trace_add("write", lambda *_: self._save_workers())
        # spacing: explanation text -> the controls it explains -- dropdown, label ↕
        ttk.Label(settings_frame, text=WORKERS_WARNING,
                  foreground=self.colors["red"], justify=tk.LEFT,
                  padding=px((0, 0, 0, SETTINGS_LAST_TRIM))).pack(
                      anchor=tk.W, pady=px((SETTINGS_NOTE_GAP, 0)))

        self._build_archive_settings(right)

    def _build_archive_settings(self, parent):
        """The capture archive: how hard to compress, and how big it is.

        `Applies on the next launch` is the literal truth and the reason
        the control does nothing when it is changed: the compaction runs
        once, at startup, off the UI thread. Firing a rebuild from a
        dropdown would put a pass of up to half a minute behind a click
        that does not look like it starts one.
        """
        from capture import archive

        top = ttk.Frame(parent)
        top.pack(fill=tk.X, anchor=tk.W)
        ttk.Label(top, text="Compression:").pack(side=tk.LEFT)
        self.archive_var = tk.StringVar(
            value=self._archive_word(self.context.config.capture_archive))
        choices = list(ARCHIVE_WORDS.values())
        box = ttk.Combobox(top, textvariable=self.archive_var,
                           state="readonly", values=choices,
                           width=max(len(word) for word in choices) + 1)
        # spacing: label ↔ its element -- label, dropdown ↔
        box.pack(side=tk.LEFT, padx=px((SETTINGS_LABEL_GAP, 0)))
        self.archive_var.trace_add("write", lambda *_: self._save_archive())
        # spacing: explanation text -> the controls it explains -- dropdown, label ↕
        ttk.Label(parent, text=ARCHIVE_NOTE,
                  foreground=self.colors["fg_dim"]).pack(
                      anchor=tk.W, pady=px((SETTINGS_NOTE_GAP, 0)))

        sizes = ttk.Frame(parent)
        sizes.pack(fill=tk.X, anchor=tk.W, pady=px((SETTINGS_ROW_GAP, 0)))
        self._archive_size_label = ttk.Label(sizes, text="")
        self._archive_size_label.pack(side=tk.LEFT)
        # spacing: element and its label ↔ element and its label -- label, label ↔
        self._folder_size_label = ttk.Label(sizes, text="")
        self._folder_size_label.pack(side=tk.LEFT,
                                     padx=px((ARCHIVE_SIZE_GAP, 0)))

        # BOTTOM of the column, which is the bottom of the panel: the
        # left column is the taller of the two and sets the height.
        self._delete_archive_button = ttk.Button(
            parent, text="Delete Archive", command=self._delete_archive,
            width=BUTTON_W_MEDIUM)
        # spacing: border edge -> button -- panel, button ↕
        self._delete_archive_button.pack(
            side=tk.BOTTOM, anchor=tk.E, pady=px((0, ARCHIVE_BUTTON_EDGE)))

        self._refresh_archive_sizes()
        self.context.notebook.bind(
            "<<NotebookTabChanged>>", self._on_archive_tab_changed, add="+")

    def _on_archive_tab_changed(self, event):
        """Re-read the two sizes when this tab becomes the selected one.

        On SELECT rather than on a timer: both figures come off a
        directory walk and a tar header scan, and neither changes while
        the user is looking at another tab.
        """
        try:
            if event.widget.nametowidget(event.widget.select()) is self.frame:
                self._refresh_archive_sizes()
        except Exception:
            pass

    @staticmethod
    def _archive_word(value):
        return ARCHIVE_WORDS.get(str(value).lower(), ARCHIVE_WORDS["balanced"])

    def _save_archive(self):
        chosen = self.archive_var.get()
        for key, word in ARCHIVE_WORDS.items():
            if word == chosen:
                self.context.config.capture_archive = key
                return

    def _archive_folder(self):
        manager = getattr(self.context, "capture_manager", None)
        return getattr(manager, "output_folder", None)

    def _refresh_archive_sizes(self):
        """Put the archive's size and the loose folder's beside each other.

        The folder figure EXCLUDES the archive, so the two add up to
        what the folder costs rather than overlapping.
        """
        from capture import archive

        folder = self._archive_folder()
        book = folder / archive.ARCHIVE_NAME if folder else None
        packed = book.stat().st_size if book and book.exists() else 0
        loose = 0
        if folder:
            for path in folder.iterdir():
                if path.is_file() and path != book:
                    try:
                        loose += path.stat().st_size
                    except OSError:
                        pass
        self._archive_size_label.configure(
            text="Archive: %s" % _megabytes(packed))
        self._folder_size_label.configure(
            text="Loose: %s" % _megabytes(loose))
        state = tk.NORMAL if packed else tk.DISABLED
        self._delete_archive_button.configure(state=state)
        if packed:
            held = archive.contents(folder)
            inside = sum(size for _name, size in held)
            self._archive_tip = (len(held), inside)
        else:
            self._archive_tip = (0, 0)

    def _delete_archive(self):
        """Delete the archive, to the Recycle Bin where there is one.

        The one irreversible action here: everything else the archiver
        does keeps a verified copy, and this is the copy. So it names
        what is being lost, and it goes to the bin rather than being
        unlinked, which is the only undo there is.
        """
        from capture import archive
        from ui.utils.recycle import recycle

        folder = self._archive_folder()
        book = folder / archive.ARCHIVE_NAME if folder else None
        if not book or not book.exists():
            return
        count, inside = getattr(self, "_archive_tip", (0, 0))
        if not messagebox.askyesno(
                "Delete Archive",
                "Delete %d archived capture%s (%s of history, %s on disk)?\n\n"
                "This cannot be undone from inside the program."
                % (count, "" if count == 1 else "s", _megabytes(inside),
                   _megabytes(book.stat().st_size)),
                icon="warning", default="cancel"):
            return
        if recycle(book):
            self._refresh_archive_sizes()
        else:
            messagebox.showerror(
                "Delete Archive",
                "%s could not be deleted. It may be open in another "
                "program." % archive.ARCHIVE_NAME)

    def _build_links(self, parent):
        """Links: outward buttons, in the left column's width."""
        # spacing: border edge -> first non-button element -- panel, button ↔↕
        # Every child here is a button, so the panel's own inset is the
        # button rule -- but the vocabulary's `border edge -> button` is
        # 3 and these are `tk.Button`s drawn flat rather than ttk ones
        # with a border, so the edge the eye meets is the fill's. The
        # non-button rule is what matches what is drawn.
        self._links_panel = ttk.LabelFrame(parent, text="Links",
                                           padding=px(LINKS_PAD))
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- panel, title ↕
        # `fill=X`, never `expand`: the height is the one `_link_heights`
        # sets, and an expanding panel would stretch to whatever its own
        # column has left -- which is a different amount on each side.
        self._links_panel.pack(fill=tk.X, padx=px(2),
                               pady=px((BOTTOM_ROW_GAP, 2)))

        for text, url in (
                ("View Releases on GitHub", RELEASES_HTML_URL),
                ("Report an Issue", f"https://github.com/{GITHUB_REPO}/issues"),
                ("Documentation", f"https://github.com/{GITHUB_REPO}#readme")):
            self._link_button(text, lambda u=url: webbrowser.open(u))

        def show_donation_message():
            messagebox.showinfo(
                "Support Development",
                "Currently not accepting donations.\n\n"
                "If you wish to instead donate to the original creator of "
                "this project, feel free to do so at:\n"
                "https://ko-fi.com/H2H21PHYKW"
            )

        self._link_button("Support Development", show_donation_message)

    def _link_button(self, text, command):
        """One flat link button, in the Links panel."""
        # spacing: TBD -- the Links panel's own button styling and pitch
        # A flat `tk.Button` with its own padding, filling the panel's
        # width. Only the panel's inset answers to a rule so far.
        tk.Button(
            self._links_panel, text=text, command=command,
            bg=self.colors["bg_lighter"], fg=self.colors["accent"],
            font=("Segoe UI", 9), relief=tk.FLAT,
            padx=px(10), pady=px(5), cursor="hand2", anchor="w",
        ).pack(fill=tk.X, pady=px(2))

    def _build_app_info(self, parent):
        """Application Information: what this build is, centred.

        Three lines at two faces, sitting in the middle of the panel on
        both axes -- which is why nothing in it answers to an edge rule.
        The panel's height is `Links`' rather than its own content's
        (see `link_bottom_heights`), so the distance from the block to
        any of the four borders is half of whatever that leaves over.
        """
        # spacing: unique -- the Application Information stack is centred in its panel -- panel, label ↔↕
        self._app_info_panel = ttk.LabelFrame(
            parent, text="Application Information",
            padding=px(APP_INFO_FLOOR))
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: panel ↕ unrelated label -- panel, title ↕
        # `fill=X`, never `expand` -- see `_build_links`.
        self._app_info_panel.pack(fill=tk.X, padx=px(2),
                                  pady=px((BOTTOM_ROW_GAP, 2)))

        # The stack, in a frame of its own. `expand` is what centres it:
        # the leftover height goes to the frame's cavity and the frame
        # sits in the middle of it, which a label packed straight into
        # the panel cannot do -- three of them would each take a third
        # of the slack and the block would spread rather than move.
        block = ttk.Frame(self._app_info_panel)
        block.pack(expand=True)

        version = current_version()
        # No leading or trailing pad: a block centred by its cavity is
        # only centred while its own padding is symmetric, and a pad on
        # one end offsets it by that much.
        for text, face, lead in (
                ("Vribbels CZN Optimizer (Ikkoru)", ("Segoe UI", 14, "bold"),
                 0),
                (version if version else "Version Unknown",
                 ("Segoe UI", 14, "bold"), APP_INFO_LINE_GAP),
                ("A fork of a Fribbels-inspired gear management and "
                 "optimization tool", ("Segoe UI", 9), APP_INFO_LINE_GAP)):
            ttk.Label(block, text=text, font=face).pack(pady=px((lead, 0)))

    def _on_first_map(self, _event=None):
        """Link the bottom row, once, the first time the tab is shown."""
        if getattr(self, "_bottom_row_linked", False):
            return
        self._bottom_row_linked = True
        self.align_columns()
        self.link_bottom_heights()

    def align_columns(self):
        """Line the two columns' panel edges up across the tab.

        Three edges are matched, and each is a panel pushed DOWN to
        meet one that already sits lower -- nothing is ever pulled up,
        because a panel's top is its own stack's height and there is
        no room above it:

        * `Setup Instructions` and `Update Status` share a top;
        * `Setup Instructions` and `Settings` share a bottom;
        * `Links` and `Application Information` share both.

        **In ROOT coordinates.** `winfo_y` is relative to a widget's
        own parent and these panels have two different ones, a column
        each, so their `y` values are not on the same scale.

        Idempotent, and public because a check calls it. Does nothing
        useful before the tab has been laid out -- see `_on_first_map`.
        """
        self.frame.update_idletasks()
        pairs = ((self._instr_frame, self.update_status.panel, "top"),
                 (self._instr_frame, self._settings_frame, "bottom"))
        for first, second, edge in pairs:
            self.frame.update_idletasks()
            if edge == "top":
                behind = first.winfo_rooty() - second.winfo_rooty()
                mover, other = (second, first) if behind > 0 else (first, second)
            else:
                behind = ((first.winfo_rooty() + first.winfo_height())
                          - (second.winfo_rooty() + second.winfo_height()))
                mover, other = (second, first) if behind > 0 else (first, second)
            if not behind:
                continue
            pad = mover.pack_info().get("pady")
            lead, trail = _pady_pair(pad)
            mover.pack_configure(pady=(lead + abs(behind), trail))

    def link_bottom_heights(self):
        """Line Links and Application Information up, top and bottom.

        They close the two columns and hold unrelated content, so left
        alone each starts where its own column's stack ends and stops
        where its own text does -- two edges out of four ragged.

        **`Links` decides the HEIGHT** and the lower of the two tops
        decides the Y: the panel that has further to fall is the one
        neither can rise above, and matching it is the only way both
        edges line up without either being clipped.

        **Propagation is turned off AFTER the measurement, not before.**
        A frame with propagation already off reports its `height`
        option as its requested height -- 1, by default -- so measuring
        first gives every panel the same wrong answer.

        Idempotent, and public because a check calls it: a build that
        never reaches an idle callback would otherwise measure the
        panels before they were linked.
        """
        panels = (self._links_panel, self._app_info_panel)
        for panel in panels:
            panel.pack_propagate(True)
            panel.pack_configure(pady=px((BOTTOM_ROW_GAP, 2)))
        self.frame.update_idletasks()

        height = self._links_panel.winfo_reqheight()
        for panel in panels:
            panel.configure(height=height)
            panel.pack_propagate(False)

        # Now the tops. Both start from the same leading pad, so
        # whichever sits lower does so because the stack above it is
        # taller -- and the difference is what the other has to be
        # pushed down by.
        #
        # **Compared in ROOT coordinates.** `winfo_y` is relative to a
        # widget's own parent, and these two have different parents:
        # one column each. Their `y` values are not on the same scale
        # and comparing them puts the row wherever the two stacks
        # happen to differ.
        self.frame.update_idletasks()
        tops = [panel.winfo_rooty() for panel in panels]
        if len(set(tops)) > 1:
            # Equal tops mean the tab has not been laid out yet -- both
            # read the same placeholder -- and there is nothing to
            # align. The heights above are still worth setting, so this
            # half is skipped rather than the whole call.
            lowest = max(tops)
            for panel, top in zip(panels, tops):
                panel.pack_configure(
                    pady=(px(BOTTOM_ROW_GAP) + lowest - top, px(2)))
            self.frame.update_idletasks()

    @staticmethod
    def _workers_choices():
        """`Auto`, `Off`, then every core count worth picking.

        **`1` is not offered**: the optimizer takes its sequential path
        at one worker, which is what `Off` already says, and two words
        for one behaviour is a question a user should not have to
        answer.
        """
        import os
        cores = os.cpu_count() or 1
        return [WORKERS_AUTO, WORKERS_OFF] + [str(n)
                                              for n in range(2, cores + 1)]

    @staticmethod
    def _workers_word(stored):
        """The dropdown word for a stored `optimizer_workers` value."""
        try:
            value = int(stored)
        except (TypeError, ValueError):
            return WORKERS_AUTO
        if value <= 0:
            return WORKERS_AUTO
        if value == 1:
            return WORKERS_OFF
        return str(value)

    def _save_workers(self):
        """Persist the dropdown's word as the number it means."""
        word = self.workers_var.get()
        if word == WORKERS_AUTO:
            self._save_setting("optimizer_workers", 0)
        elif word == WORKERS_OFF:
            self._save_setting("optimizer_workers", 1)
        else:
            try:
                self._save_setting("optimizer_workers", int(word))
            except ValueError:
                return

    def _save_setting(self, key, value):
        """Write one setting, where there is a manager to write to."""
        sm = self.context.settings_manager
        if sm is not None:
            sm.set(key, value)

    def check_status(self):
        """Refresh the Setup Status panel.

        Starts a worker and returns immediately; `_apply_status` paints
        the answers back. The probing MUST NOT run inline: it shells out
        to external programs, and a blocked `after()` callback stops Tk
        processing events at all, so the whole program locks up with a
        painted but dead window. `python --version` can block forever
        (see `_run_version`), and this check is scheduled a second after
        the tab is built -- so probing inline takes the app down on
        every launch that hits it, before the user has touched
        anything.
        """
        if self._checking:
            return
        self._checking = True
        self._probe_result = None
        for label, text in (
            (self.python_status, "Checking Python..."),
            (self.mitmproxy_status, "Checking mitmproxy..."),
            (self.cert_status, "Checking certificate..."),
            (self.admin_status, "Checking admin rights..."),
        ):
            try:
                label.config(text=text, foreground=self.colors["fg_dim"])
            except (AttributeError, tk.TclError):
                pass
        threading.Thread(target=self._probe_prerequisites, daemon=True).start()
        self._poll_probe()

    def _poll_probe(self, attempts: int = 0):
        """Wait for the worker's findings and paint them.

        The worker cannot hand them over itself: `after()` from another
        thread only works while the main thread is inside `mainloop()`,
        and this check is scheduled during startup, so the worker can
        finish while the main thread is still in the reveal's `update()`
        passes -- or after mainloop has exited, if the window is closed
        first. Either way Tk raises "main thread is not in main loop".
        So the worker only assigns a plain attribute, and this poll (a
        main-thread `after` chain) does everything Tk-facing.
        """
        if self._probe_result is None:
            if attempts < 200:
                self.root.after(100, lambda: self._poll_probe(attempts + 1))
            else:
                self._checking = False
            return
        self._apply_status(self._probe_result)

    @staticmethod
    def _run_version(cmd) -> str:
        """Run `cmd` and return its version output, or "" if it can't be
        established.

        Bounded and pipe-safe deliberately. On Windows a bare `python`
        usually resolves to the Microsoft Store's app-execution alias,
        which opens the Store instead of an interpreter and never closes
        the stdout pipe it inherited -- `communicate()` then waits on
        that pipe forever, with no timeout to stop it. So: stdin is
        closed so nothing can block waiting for input, a timeout caps
        the wait, and CREATE_NO_WINDOW keeps a console from flashing
        over the UI. The worker thread is the real backstop, since a
        killed child's grandchildren can still hold the pipe open past
        the timeout.
        """
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5,
                stdin=subprocess.DEVNULL, **kwargs
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        if result.returncode != 0:
            return ""
        # Older Pythons report their version on stderr, not stdout.
        return ((result.stdout or "").strip()
                or (result.stderr or "").strip())

    def _probe_prerequisites(self):
        """Worker body for check_status: gather every status string off
        the UI thread, then publish them for _poll_probe. Touches no
        widgets and makes no Tk calls -- see _poll_probe for why."""
        status = {}

        version = self._run_version(["python", "--version"])
        status["python"] = ((f"[OK] {version}", "green") if version
                            else ("[X] Python not found", "red"))

        mitmdump_path = find_mitmdump()
        if not mitmdump_path:
            status["mitmproxy"] = ("[X] mitmproxy not found", "red")
        else:
            version = self._run_version([mitmdump_path, "--version"])
            parts = version.split()
            if len(parts) >= 2:
                status["mitmproxy"] = (f"[OK] mitmproxy {parts[1]}", "green")
            elif version:
                status["mitmproxy"] = ("[OK] mitmproxy installed", "green")
            else:
                status["mitmproxy"] = ("[X] mitmproxy not working", "red")

        cert_path = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.cer"
        status["cert"] = (("[OK] Certificate exists", "green")
                          if cert_path.exists()
                          else ("[X] Certificate not generated", "red"))

        try:
            if ctypes.windll.shell32.IsUserAnAdmin():
                status["admin"] = ("[OK] Running as Administrator", "green")
            else:
                status["admin"] = ("[!] Not running as Administrator", "yellow")
        except Exception:
            status["admin"] = ("? Could not check admin status", "yellow")

        # Publish for the UI thread's poll. Assignment is atomic enough:
        # _poll_probe only ever tests for None.
        self._probe_result = status

    def _apply_status(self, status: dict):
        """Paint the worker's findings onto the status labels. Runs on
        the UI thread."""
        self._checking = False
        for key, label in (
            ("python", self.python_status),
            ("mitmproxy", self.mitmproxy_status),
            ("cert", self.cert_status),
            ("admin", self.admin_status),
        ):
            text, color = status.get(key, ("? Unknown", "yellow"))
            try:
                label.config(text=text, foreground=self.colors[color])
            except (AttributeError, tk.TclError):
                pass

    def setup_cert(self):
        """Generate and open certificate for installation."""
        try:
            cert_path = setup_certificate()
            messagebox.showinfo(
                "Certificate Generated",
                f"Certificate generated at:\n{cert_path}\n\n"
                "Opening certificate installer..."
            )
            open_certificate(cert_path)
            self.check_status()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate certificate: {e}")

    # ====================================================================
    # Restore Defaults dialog
    # ====================================================================

    def _open_restore_dialog(self, kind: str) -> None:
        """Open the modal Restore Defaults dialog for the given kind.

        kind: one of "presets", "character_preset", "optimizer_settings".
        See `_RESTORE_KIND_META` for per-kind switches.
        """
        meta = _RESTORE_KIND_META.get(kind)
        if meta is None:
            return  # bad kind -- caller bug

        # Resolve the manager up front so we can report problems before
        # building any UI.
        mgr = self._manager_for_kind(kind)
        if mgr is None:
            messagebox.showwarning(
                meta["dialog_title"],
                "The required manager isn't available. Restart the "
                "program and try again.",
            )
            return
        if hasattr(mgr, "is_corrupted") and mgr.is_corrupted():
            messagebox.showwarning(
                meta["dialog_title"],
                "The user settings file for this kind is corrupted. "
                "Quarantine and reset it before restoring defaults.",
            )
            return

        defaults_path = self._defaults_file_path(meta["filename"])
        if defaults_path is None or not defaults_path.exists():
            messagebox.showinfo(
                meta["dialog_title"],
                "No bundled defaults available for this kind.",
            )
            return

        missing, changed = self._compute_diffs(kind, mgr, defaults_path)
        if not missing and not changed:
            messagebox.showinfo(
                meta["dialog_title"],
                "Nothing to restore -- your settings match the bundled "
                "defaults (no missing entries, no value changes).",
            )
            return

        self._build_restore_dialog(kind, mgr, defaults_path, missing,
                                   changed, meta)

    def _build_restore_dialog(self, kind, mgr, defaults_path, missing,
                              changed, meta):
        """Build and show the dialog for a diff that has been computed.

        Split from `_open_restore_dialog` so the window can be opened
        with a stated diff. Everything above the split reports a reason
        it cannot open through `messagebox`, which blocks -- so it is
        the wrong half to call from anywhere but a button.

        Returns the dialog.
        """
        missing_data: dict = {}   # key -> {"restore": BooleanVar, "display": str}
        changed_data: dict = {}   # key -> see _build_changed_row

        dlg = tk.Toplevel(self.frame)
        dlg.title(meta["dialog_title"])
        dlg.transient(self.root)
        dlg.grab_set()
        close_on_escape(dlg)
        try:
            dlg.configure(bg=self.colors["bg"])
        except tk.TclError:
            pass

        # spacing: content frame -> content frame -- frame, frame ↔↕
        # The TOP is smaller than the other three because what it runs
        # to is a LabelFrame TITLE rather than a border: the title's own
        # line box already holds most of the distance, so the same 4
        # here would render as 7.
        outer = ttk.Frame(dlg, padding=px((4, 1, 4, 4)))
        outer.pack(fill=tk.BOTH, expand=True)

        frames_row = ttk.Frame(outer)
        frames_row.pack(fill=tk.BOTH, expand=True)
        frames_row.grid_columnconfigure(0, weight=1, uniform="halves")
        frames_row.grid_columnconfigure(1, weight=1, uniform="halves")
        frames_row.grid_rowconfigure(0, weight=1)

        self._build_missing_frame(frames_row, missing, missing_data)
        self._build_changed_frame(frames_row, changed, changed_data, meta["show_rename"])

        # ----- Restore / Cancel -----
        # spacing: content frame -> content frame -- panel, button ↕
        # A button row under two panels and inside no panel of its own,
        # which is the frame rule rather than the border-edge one.
        bottom = ttk.Frame(outer)
        bottom.pack(fill=tk.X, pady=px((4, 0)))
        # spacing: button -> button -- button, button ↔
        ttk.Button(
            bottom, text="Cancel", width=BUTTON_W_SMALL,
            command=dlg.destroy,
        ).pack(side=tk.RIGHT)
        ttk.Button(
            bottom, text="Restore", width=BUTTON_W_SMALL,
            command=lambda: self._apply_restore_changes(
                kind, mgr, defaults_path, missing_data, changed_data, dlg,
            ),
        ).pack(side=tk.RIGHT, padx=px((0, 4)))

        # Center on the main window AND enforce a minimum dialog width
        # that accounts for the (possibly-hidden) rename entry column.
        # The column-3 reservation above keeps the layout stable across
        # the rename toggle, but the natural-size first pass might still
        # land slightly narrower than the rename entry needs; minsize is
        # a cheap safety net.
        dlg.update_idletasks()
        try:
            natural_w = dlg.winfo_reqwidth()
            natural_h = dlg.winfo_reqheight()
            target_w = max(natural_w, 760)
            dlg.minsize(target_w, natural_h)
            x = self.root.winfo_rootx() + (self.root.winfo_width() - target_w) // 2
            y = self.root.winfo_rooty() + (self.root.winfo_height() - natural_h) // 2
            dlg.geometry(f"{target_w}x{natural_h}+{max(0, x)}+{max(0, y)}")
        except (tk.TclError, AttributeError):
            pass
        return dlg

    # ----- frame builders -----

    def _build_missing_frame(self, parent, missing, missing_data: dict) -> None:
        """Build the "Restore Missing" frame using grid for stable
        column alignment.

        missing is a list of (key, display_name) tuples. missing_data
        is filled by this function: key -> {"restore": BooleanVar,
        "display": str}.
        """
        # spacing: border edge -> first non-button element -- panel, checkbox ↔↕
        # Left and right at 0, the way every panel with an All/None row
        # under it carries them: a LabelFrame's `padding` insets every
        # child alike, so a value here would ride both this rule and
        # `border edge -> button`, which is a different number.
        # spacing: border edge -> button -- panel, button ↕
        left = ttk.LabelFrame(parent, text="Restore Missing",
                              padding=px((0, 0, 0, 3)))
        # spacing: content frame -> content frame -- panel, panel ↔
        left.grid(row=0, column=0, sticky="nsew", padx=px((0, 2)))

        rows = ttk.Frame(left)
        rows.pack(fill=tk.BOTH, expand=True)

        # spacing: explanation text -> the controls it explains -- label, checkbox ↕
        # spacing: element and its label ↔ element and its label -- label, label ↔
        # The trailing `padx` is what sets the COLUMN's width -- the
        # heading is wider than the checkbox under it -- so it is also
        # the gap out to the next heading.
        ttk.Label(
            rows, text="Restore",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=px((2, 4)), pady=px((0, 0)))
        ttk.Label(
            rows, text="Name",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=1, sticky="w", pady=px((0, 0)))

        if not missing:
            ttk.Label(
                rows, text="(none missing)",
                foreground=self.colors["fg_dim"],
            ).grid(row=1, column=0, columnspan=2, sticky="w", padx=px((2, 0)))
        else:
            for i, (key, display) in enumerate(missing):
                grid_row = i + 1
                var = tk.BooleanVar(value=True)
                missing_data[key] = {"restore": var, "display": display}
                # spacing: label ↔ its element -- checkbox, label ↔
                # spacing: checkbox/slider ↕ checkbox/slider rows -- checkbox, checkbox ↕
                # The pitch pad is LEADING only, so the first row's gap
                # upward stays the header's and the last adds nothing
                # above the All/None row.
                #
                # `sticky=e` because the heading is wider than the
                # checkbox and sets the column: left-aligned, the boxes
                # sit under the heading's first letter with a band of
                # empty column to their right.
                make_checkbox(rows, self.colors, variable=var).grid(
                    row=grid_row, column=0, sticky="e", padx=px((2, 4)),
                    pady=px((0 if i == 0 else 3, 0)),
                )
                ttk.Label(rows, text=display).grid(
                    row=grid_row, column=1, sticky="w",
                    pady=px((0 if i == 0 else 3, 0)),
                )

        make_all_none_row(
            left,
            lambda: self._toggle_all(missing_data, "restore", True),
            lambda: self._toggle_all(missing_data, "restore", False),
        )

    def _build_changed_frame(
        self, parent, changed, changed_data: dict, show_rename: bool,
    ) -> None:
        """Build the "Replace Changed" frame.

        Grid layout columns:
            col 0: Replace checkbox
            col 1: Display name
            col 2: Rename checkbox (only when show_rename=True)
            col 3: Rename entry  (only when show_rename=True; initially hidden)

        Using grid + grid_remove() keeps the Rename column at a stable
        x-position whether the entry is shown or hidden, so checking
        Rename doesn't shift the checkbox or the column-header label.

        changed is a list of (key, display_name). changed_data is filled
        with key -> {"replace": BooleanVar, "display": str, plus
        optionally "rename" / "rename_text" / "entry" when show_rename}.
        """
        # spacing: border edge -> first non-button element -- panel, checkbox ↔↕
        # spacing: border edge -> button -- panel, button ↕
        right = ttk.LabelFrame(parent, text="Replace Changed",
                               padding=px((0, 0, 0, 3)))
        # spacing: content frame -> content frame -- panel, panel ↔
        right.grid(row=0, column=1, sticky="nsew", padx=px((2, 0)))

        rows = ttk.Frame(right)
        rows.pack(fill=tk.BOTH, expand=True)

        # Reserve a fixed minimum width for column 3 (the rename text
        # entry). Without this the column has zero size while every
        # entry is hidden, and the dialog visibly RESIZES the first
        # time any Rename checkbox is ticked. 220px fits the 26-char
        # Entry plus breathing room.
        if show_rename:
            rows.grid_columnconfigure(3, minsize=px(220))

        # spacing: explanation text -> the controls it explains -- label, checkbox ↕
        # spacing: element and its label ↔ element and its label -- label, label ↔
        ttk.Label(
            rows, text="Replace",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=px((2, 4)), pady=px((0, 0)))
        ttk.Label(
            rows, text="Name",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=1, sticky="w", padx=px((0, 4)), pady=px((0, 0)))
        if show_rename:
            ttk.Label(
                rows, text="Also Rename and Keep Current",
                font=("Segoe UI", 9, "bold"),
            ).grid(row=0, column=2, columnspan=2, sticky="w", pady=px((0, 0)))

        if not changed:
            ttk.Label(
                rows, text="(no changes)",
                foreground=self.colors["fg_dim"],
            ).grid(
                row=1, column=0,
                columnspan=4 if show_rename else 2,
                sticky="w", padx=px((2, 0)),
            )
        else:
            for i, (key, display) in enumerate(changed):
                grid_row = i + 1
                if show_rename:
                    self._build_changed_row_with_rename(
                        rows, grid_row, key, display, changed_data,
                    )
                else:
                    self._build_changed_row_simple(
                        rows, grid_row, key, display, changed_data,
                    )

        make_all_none_row(
            right,
            lambda: self._toggle_all(changed_data, "replace", True),
            lambda: self._toggle_all(changed_data, "replace", False),
        )

    def _build_changed_row_simple(
        self, parent_grid, grid_row, key, display, changed_data: dict,
    ) -> None:
        """Simple per-row builder (no Rename) for character_preset and
        optimizer_settings restores."""
        replace_var = tk.BooleanVar(value=True)
        # spacing: label ↔ its element -- checkbox, label ↔
        # spacing: checkbox/slider ↕ checkbox/slider rows -- checkbox, checkbox ↕
        # The same shape as the Restore Missing rows opposite, down to
        # the leading-only pitch pad: a `pady` on both sides puts half
        # the pitch above the first row and half below the last, where
        # those two gaps answer to their own rules.
        make_checkbox(parent_grid, self.colors,
                      variable=replace_var).grid(
            row=grid_row, column=0, sticky="e", padx=px((2, 4)),
            pady=px((0 if grid_row == 1 else 3, 0)),
        )
        ttk.Label(parent_grid, text=display).grid(
            row=grid_row, column=1, sticky="w", padx=px((0, 4)),
            pady=px((0 if grid_row == 1 else 3, 0)),
        )
        changed_data[key] = {
            "replace": replace_var,
            "display": display,
        }

    def _build_changed_row_with_rename(
        self, parent_grid, grid_row, key, display, changed_data: dict,
    ) -> None:
        """Per-row builder for the presets kind. Includes the Rename
        checkbox + entry with stable column positions via grid +
        grid_remove (no pack-shuffling on toggle)."""
        replace_var = tk.BooleanVar(value=True)
        rename_var = tk.BooleanVar(value=False)
        rename_text_var = tk.StringVar(value="")
        suppress = [False]  # re-entrancy guard for the two var-traces

        # spacing: label ↔ its element -- checkbox, label ↔
        # spacing: checkbox/slider ↕ checkbox/slider rows -- checkbox, checkbox ↕
        pitch = (0 if grid_row == 1 else 3, 0)
        make_checkbox(parent_grid, self.colors,
                      variable=replace_var).grid(
            row=grid_row, column=0, sticky="e", padx=px((2, 4)), pady=px(pitch),
        )
        ttk.Label(parent_grid, text=display).grid(
            row=grid_row, column=1, sticky="w", padx=px((0, 4)), pady=px(pitch),
        )
        rename_cb = make_checkbox(parent_grid, self.colors,
                                  variable=rename_var)
        # spacing: label ↔ its element -- checkbox, entry ↔
        rename_cb.grid(
            row=grid_row, column=2, sticky="w", padx=px((0, 5)), pady=px(pitch),
        )

        rename_entry = tk.Entry(
            parent_grid,
            textvariable=rename_text_var,
            bg=self.colors["bg_light"],
            fg=self.colors["fg_dim"],
            insertbackground=self.colors["fg"],
            relief=tk.FLAT,
            width=26,
        )
        rename_entry.grid(row=grid_row, column=3, sticky="w", pady=px(pitch))
        rename_text_var.set(_RENAME_PLACEHOLDER)
        # Hide via grid_remove (NOT grid_forget / pack): grid_remove
        # preserves the cell's grid options so a later grid() call
        # re-shows the entry in the exact same spot. Pack-based
        # show/hide shifts the rename checkbox's x-position and makes
        # the row jump.
        rename_entry.grid_remove()

        def on_entry_focus_in(_e):
            if rename_text_var.get() == _RENAME_PLACEHOLDER:
                rename_text_var.set("")
                try:
                    rename_entry.configure(fg=self.colors["fg"])
                except tk.TclError:
                    pass

        def on_entry_focus_out(_e):
            if not rename_text_var.get():
                rename_text_var.set(_RENAME_PLACEHOLDER)
                try:
                    rename_entry.configure(fg=self.colors["fg_dim"])
                except tk.TclError:
                    pass

        rename_entry.bind("<FocusIn>", on_entry_focus_in)
        rename_entry.bind("<FocusOut>", on_entry_focus_out)

        def on_rename_toggle(*_):
            if suppress[0]:
                return
            if rename_var.get():
                if not replace_var.get():
                    suppress[0] = True
                    try:
                        replace_var.set(True)
                    finally:
                        suppress[0] = False
                rename_entry.grid()  # re-show in the same cell
            else:
                rename_entry.grid_remove()

        def on_replace_toggle(*_):
            if suppress[0]:
                return
            if not replace_var.get() and rename_var.get():
                suppress[0] = True
                try:
                    rename_var.set(False)
                finally:
                    suppress[0] = False
                rename_entry.grid_remove()

        rename_var.trace_add("write", on_rename_toggle)
        replace_var.trace_add("write", on_replace_toggle)

        changed_data[key] = {
            "replace": replace_var,
            "rename": rename_var,
            "rename_text": rename_text_var,
            "entry": rename_entry,
            "display": display,
        }

    @staticmethod
    def _toggle_all(data_dict: dict, var_key: str, value: bool) -> None:
        """Set every entry's `var_key` BooleanVar to `value`. Used by
        the All / None buttons. The Replace-untoggle case still fires
        its own rename-cleanup trace, so we don't need to also touch
        rename here."""
        for entry in data_dict.values():
            var = entry.get(var_key)
            if isinstance(var, tk.BooleanVar):
                var.set(value)

    # ----- per-kind data helpers -----

    def _manager_for_kind(self, kind: str):
        """Return the manager instance for this restore kind."""
        if kind == "presets":
            return getattr(self.context, "preset_manager", None)
        if kind == "character_preset":
            return getattr(self.context, "character_preset_manager", None)
        if kind == "optimizer_settings":
            return getattr(self.context, "optimizer_settings_manager", None)
        return None

    def _defaults_file_path(self, filename: str):
        """Resolve `default_settings/<filename>` for the running env.

        Frozen builds read from _MEIPASS via
        defaults_sync.resolve_defaults_dir; dev reads from the source
        tree (the Vribbels/ directory)."""
        if getattr(sys, "frozen", False):
            base = Path(sys.executable).parent
        else:
            # Walk up from this file: ui/tabs/setup_tab.py -> Vribbels/.
            base = Path(__file__).resolve().parent.parent.parent
        defaults_dir = resolve_defaults_dir(base)
        return defaults_dir / filename

    def _compute_diffs(self, kind: str, mgr, defaults_path: Path):
        """Compute (missing, changed) for the given kind. Returns lists
        of (key, display_name) tuples, sorted by display name."""
        if kind == "presets":
            return self._diff_presets(mgr, defaults_path)
        if kind == "character_preset":
            return self._diff_character_preset(mgr, defaults_path)
        if kind == "optimizer_settings":
            return self._diff_optimizer_settings(mgr, defaults_path)
        return [], []

    def _diff_presets(self, preset_mgr, defaults_path):
        """presets.json diff: by NAME. Missing = in defaults, not in user.
        Changed = in both, weights differ.
        Tombstoned defaults ARE included in missing -- this dialog is the
        intended way to bring them back, overriding the tombstone."""
        try:
            with open(defaults_path, "r", encoding="utf-8") as f:
                default_data = json.load(f)
        except Exception:
            return [], []
        default_presets = default_data.get("presets", {})
        if not isinstance(default_presets, dict):
            return [], []

        user_presets = preset_mgr.presets
        missing, changed = [], []
        for name, default_weights in default_presets.items():
            if not isinstance(default_weights, dict):
                continue
            if name not in user_presets:
                missing.append((name, name))
                continue
            if not self._preset_weights_equal(default_weights, user_presets[name]):
                changed.append((name, name))
        missing.sort(key=lambda x: x[1].lower())
        changed.sort(key=lambda x: x[1].lower())
        return missing, changed

    def _diff_character_preset(self, char_preset_mgr, defaults_path):
        """character_preset.json diff: by RES_ID (v2 schema).

        `None` (no preset assigned, i.e. the "Default Preset" UI state)
        is treated as a non-opinion on BOTH sides. Bucket rules:
          - defaults' value is None   -> skip (nothing to offer)
          - user's value is None/missing, defaults' non-null -> Missing
          - both non-null and differ  -> Changed
          - both non-null and match   -> skip

        Do NOT flag user=None vs default=non-null as "Changed": a user
        who resets an assignment to Default Preset would then see that
        character pop up in Replace Changed, which reads as noise.

        Both files are normalized to v2 first so mixed-version files
        compare correctly.
        """
        try:
            with open(defaults_path, "r", encoding="utf-8") as f:
                default_raw = json.load(f)
        except Exception:
            return [], []

        try:
            from character_preset_manager import normalize_to_v2
        except ImportError:
            return [], []
        default_v2 = normalize_to_v2(default_raw)
        default_assignments = default_v2.get("assignments", {})
        default_name_hints = default_v2.get("name_hints", {})

        user_assignments = char_preset_mgr.assignments_by_id
        user_name_hints = char_preset_mgr.name_hints

        missing, changed = [], []
        for rid, default_preset in default_assignments.items():
            # Defaults have nothing meaningful to offer -> never flag.
            if default_preset is None:
                continue
            display = (
                default_name_hints.get(rid)
                or user_name_hints.get(rid)
                or rid
            )
            # .get returns None for absent keys -- the two paths
            # ("key missing" and "key present with None value") collapse
            # into the same Missing bucket below, which matches the user's
            # mental model that "Default Preset assigned" == "no opinion".
            user_preset = user_assignments.get(rid)
            if user_preset is None:
                missing.append((rid, display))
                continue
            if user_preset != default_preset:
                changed.append((rid, display))
        missing.sort(key=lambda x: x[1].lower())
        changed.sort(key=lambda x: x[1].lower())
        return missing, changed

    def _diff_optimizer_settings(self, opt_settings_mgr, defaults_path):
        """optimizer_settings.json diff: by RES_ID.
        Missing = in defaults, not in user. Changed = in both, the
        per-char settings dict differs (name_hint excluded from the
        comparison since it's cosmetic).
        """
        try:
            with open(defaults_path, "r", encoding="utf-8") as f:
                default_raw = json.load(f)
        except Exception:
            return [], []
        default_chars = default_raw.get("characters", {})
        if not isinstance(default_chars, dict):
            return [], []

        user_chars = opt_settings_mgr.data.get("characters", {})
        if not isinstance(user_chars, dict):
            user_chars = {}

        missing, changed = [], []
        for rid, default_entry in default_chars.items():
            if not isinstance(default_entry, dict):
                continue
            display = default_entry.get("name_hint") or rid
            user_entry = user_chars.get(rid)
            if user_entry is None:
                missing.append((rid, display))
                continue
            if not self._dict_equal_excluding_keys(
                default_entry, user_entry, ("name_hint",),
            ):
                changed.append((rid, display))
        missing.sort(key=lambda x: x[1].lower())
        changed.sort(key=lambda x: x[1].lower())
        return missing, changed

    @staticmethod
    def _preset_weights_equal(a: dict, b: dict) -> bool:
        """Compare two preset weight dicts as float maps. Missing keys
        on either side default to 1.0 (PresetManager pad behavior)."""
        from preset_manager import SUPPORTED_STATS
        for stat in SUPPORTED_STATS:
            av = float(a.get(stat, 1.0))
            bv = float(b.get(stat, 1.0))
            if abs(av - bv) > 1e-9:
                return False
        return True

    @staticmethod
    def _dict_equal_excluding_keys(a: dict, b: dict, exclude_keys) -> bool:
        """Deep-equality test excluding given top-level keys (e.g.
        "name_hint" for the optimizer_settings per-char dicts).
        Recurses into nested dicts via Python's `==`."""
        exclude_set = set(exclude_keys)
        a_clean = {k: v for k, v in a.items() if k not in exclude_set}
        b_clean = {k: v for k, v in b.items() if k not in exclude_set}
        return a_clean == b_clean

    # ----- apply -----

    def _apply_restore_changes(
        self, kind, mgr, defaults_path, missing_data, changed_data, dlg,
    ):
        """Dispatch to the kind-specific apply routine after validating
        rename inputs (presets only)."""
        meta = _RESTORE_KIND_META.get(kind)
        if meta is None:
            return

        # Validate rename inputs for the presets kind.
        if meta["show_rename"]:
            err = self._validate_rename_inputs(missing_data, changed_data, mgr)
            if err:
                messagebox.showerror(meta["dialog_title"], err, parent=dlg)
                return

        # Sanity check: anything selected?
        any_missing = any(
            e["restore"].get() for e in missing_data.values()
        )
        any_changed = any(
            e["replace"].get() for e in changed_data.values()
        )
        if not any_missing and not any_changed:
            messagebox.showinfo(
                meta["dialog_title"],
                "No changes selected.",
                parent=dlg,
            )
            return

        # Read defaults' raw data once.
        try:
            with open(defaults_path, "r", encoding="utf-8") as f:
                default_raw = json.load(f)
        except Exception as exc:
            messagebox.showerror(
                meta["dialog_title"],
                f"Could not read bundled defaults:\n{exc}",
                parent=dlg,
            )
            return

        try:
            if kind == "presets":
                summary = self._apply_presets(mgr, default_raw, missing_data, changed_data)
            elif kind == "character_preset":
                summary = self._apply_character_preset(mgr, default_raw, missing_data, changed_data)
            elif kind == "optimizer_settings":
                summary = self._apply_optimizer_settings(mgr, default_raw, missing_data, changed_data)
            else:
                summary = "Done."
        except Exception as exc:
            messagebox.showerror(
                meta["dialog_title"],
                f"Restore failed mid-operation:\n{exc}\n\n"
                f"Your settings file may be partially updated.",
                parent=dlg,
            )
            return

        dlg.destroy()
        messagebox.showinfo(meta["dialog_title"], summary)
        self._refresh_dependent_tabs(kind)

    def _validate_rename_inputs(self, missing_data, changed_data, preset_mgr):
        """Return an error message (str) or None. Checks empty / collision
        on rename targets for the presets kind."""
        rename_targets = {}
        for name, entry in changed_data.items():
            if not entry["replace"].get():
                continue
            if not entry.get("rename") or not entry["rename"].get():
                continue
            new_name = entry["rename_text"].get().strip()
            if new_name == _RENAME_PLACEHOLDER:
                new_name = ""
            if not new_name:
                return (
                    f"Preset '{name}': Rename is checked but the new name "
                    f"is empty. Either fill in a new name or uncheck "
                    f"'Also Rename and Keep Current'."
                )
            rename_targets[name] = new_name

        seen_new = set()
        existing = set(preset_mgr.presets.keys())
        for orig, new_name in rename_targets.items():
            if new_name in existing and new_name != orig:
                return (
                    f"Preset '{orig}': new name '{new_name}' already "
                    f"exists. Pick a different name."
                )
            if new_name in seen_new:
                return (
                    f"Preset '{orig}': new name '{new_name}' is also "
                    f"used by another rename. Names must be unique."
                )
            seen_new.add(new_name)

        for name, entry in missing_data.items():
            if entry["restore"].get() and name in seen_new:
                return (
                    f"Preset '{name}' is being restored AND used as a "
                    f"rename target. Pick a different rename name."
                )
        return None

    def _apply_presets(self, preset_mgr, default_raw, missing_data, changed_data):
        """Apply restore for the Gear Score presets kind."""
        default_presets = default_raw.get("presets", {})
        if not isinstance(default_presets, dict):
            raise ValueError("Bundled defaults file is structurally invalid.")

        rename_targets = {}  # orig -> new_name
        replace_only = []
        restore_missing = []
        for name, entry in changed_data.items():
            if not entry["replace"].get():
                continue
            if entry.get("rename") and entry["rename"].get():
                new_name = entry["rename_text"].get().strip()
                if new_name == _RENAME_PLACEHOLDER:
                    new_name = ""
                if new_name:
                    rename_targets[name] = new_name
                    continue
            replace_only.append(name)
        for name, entry in missing_data.items():
            if entry["restore"].get():
                restore_missing.append(name)

        # 1. Renames: save user's existing weights under the new name
        #    BEFORE we overwrite the orig-name slot.
        for orig, new_name in rename_targets.items():
            user_weights = preset_mgr.presets.get(orig, {})
            preset_mgr.save_preset(new_name, dict(user_weights),
                                   set_selected=False)
        # 2. For each "Replace" (renamed or not), overwrite orig slot
        #    with defaults' weights.
        for orig in list(rename_targets.keys()) + replace_only:
            dw = default_presets.get(orig)
            if not isinstance(dw, dict):
                continue
            preset_mgr.save_preset(orig, dict(dw), set_selected=False)
        # 3. Restore missing.
        for name in restore_missing:
            dw = default_presets.get(name)
            if not isinstance(dw, dict):
                continue
            preset_mgr.save_preset(name, dict(dw), set_selected=False)

        parts = []
        if restore_missing:
            parts.append(f"{len(restore_missing)} restored")
        if rename_targets:
            parts.append(f"{len(rename_targets)} renamed + replaced")
        if replace_only:
            parts.append(f"{len(replace_only)} replaced")
        return ("Done: " + ", ".join(parts) + ".\n\n"
                "The Gear Score tab has been refreshed.")

    def _apply_character_preset(
        self, char_preset_mgr, default_raw, missing_data, changed_data,
    ):
        """Apply restore for the character_preset.json kind."""
        try:
            from character_preset_manager import normalize_to_v2
        except ImportError:
            raise RuntimeError("character_preset_manager not available")
        default_v2 = normalize_to_v2(default_raw)
        default_assignments = default_v2.get("assignments", {})
        default_name_hints = default_v2.get("name_hints", {})

        restored = 0
        replaced = 0
        for rid, entry in missing_data.items():
            if not entry["restore"].get():
                continue
            preset = default_assignments.get(rid)
            hint = default_name_hints.get(rid, "")
            char_preset_mgr.set_preset_by_id(rid, preset, name_hint=hint)
            restored += 1
        for rid, entry in changed_data.items():
            if not entry["replace"].get():
                continue
            preset = default_assignments.get(rid)
            hint = default_name_hints.get(rid, "")
            char_preset_mgr.set_preset_by_id(rid, preset, name_hint=hint)
            replaced += 1

        parts = []
        if restored:
            parts.append(f"{restored} restored")
        if replaced:
            parts.append(f"{replaced} replaced")
        return ("Done: " + ", ".join(parts) + ".\n\n"
                "The Combatants tab has been refreshed.")

    def _apply_optimizer_settings(
        self, opt_settings_mgr, default_raw, missing_data, changed_data,
    ):
        """Apply restore for the optimizer_settings.json kind."""
        default_chars = default_raw.get("characters", {})
        if not isinstance(default_chars, dict):
            raise ValueError("Bundled defaults file is structurally invalid.")

        user_chars = opt_settings_mgr.data.setdefault("characters", {})
        restored = 0
        replaced = 0
        for rid, entry in missing_data.items():
            if not entry["restore"].get():
                continue
            default_entry = default_chars.get(rid)
            if not isinstance(default_entry, dict):
                continue
            # Deep-copy so user mutations don't reach back into the
            # default's dict (which in frozen builds is read-only).
            user_chars[rid] = copy.deepcopy(default_entry)
            restored += 1
        for rid, entry in changed_data.items():
            if not entry["replace"].get():
                continue
            default_entry = default_chars.get(rid)
            if not isinstance(default_entry, dict):
                continue
            user_chars[rid] = copy.deepcopy(default_entry)
            replaced += 1

        # Single write at the end.
        opt_settings_mgr._write()

        parts = []
        if restored:
            parts.append(f"{restored} restored")
        if replaced:
            parts.append(f"{replaced} replaced")
        return ("Done: " + ", ".join(parts) + ".\n\n"
                "The Optimizer tab has been refreshed.")

    def _refresh_dependent_tabs(self, kind: str):
        """Refresh the tabs whose displayed state depends on the file
        that was just modified. Best-effort: each refresh is wrapped in
        try/except so a tab-side error doesn't undo the message dialog
        the user just saw.

        Mapping:
          - presets / character_preset -> heroes_tab.refresh_heroes()
            re-renders the Preset column; AND
            scoring_tab.refresh_presets() redraws the preset list
            (names + assignment markers). refresh_presets is
            ScoringTab's stable public entry point for exactly this.
          - optimizer_settings -> optimizer_tab.refresh_after_load()
            re-reads the selected combatant's per-char settings into
            the sliders / dropdowns.
        """
        if kind in ("presets", "character_preset"):
            self._safe_call(
                getattr(self.context, "heroes_tab", None),
                "refresh_heroes",
            )
            self._safe_call(
                getattr(self.context, "scoring_tab", None),
                "refresh_presets",
            )
        if kind == "optimizer_settings":
            self._safe_call(
                getattr(self.context, "optimizer_tab", None),
                "refresh_after_load",
            )

    @staticmethod
    def _safe_call(obj, method_name) -> bool:
        """Call obj.method_name() if obj is non-None and method exists.
        Returns True if the call succeeded. Best-effort by design: a
        missing tab (standalone tests) or a tab-side refresh error
        shouldn't surface after the user already saw the success
        dialog."""
        if obj is None:
            return False
        fn = getattr(obj, method_name, None)
        if not callable(fn):
            return False
        try:
            fn()
            return True
        except Exception:
            return False
