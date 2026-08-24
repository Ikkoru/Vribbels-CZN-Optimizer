"""Capture tab for intercepting game data."""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
from capture import check_prerequisites, CaptureError
from capture.constants import SERVERS
from game_data.characters import CHARACTERS, ATTRIBUTE_COLORS
from ..base_tab import BaseTab
from ..utils.checkbox import make_checkbox
from ..utils.scrolled_text import make_scrolled_text


# Width of the tab's fixed left column, in pixels. The right column
# takes whatever is left of the tab, so this is the only lever on the
# Upgrade Log Settings panel's width.
LEFT_COLUMN_PX = 583

# Log Preset checkboxes per row, filled left-to-right then down.
LOG_PRESET_COLUMNS = 5

# Gap between those columns, in pixels.
LOG_PRESET_COLUMN_GAP = 6

# What the Region readout says before a capture has seen a connection.
REGION_UNKNOWN = "not detected yet"
# ...and when two games on different servers are running at once.
REGION_CONFLICT = (
    "two servers at once -- close one game and capture again"
)


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
        # spacing: content frame -> content frame
        # The sides and bottom absorb the notebook's removed client inset
        # so this tab sits where it did (see Flush.TNotebook in
        # czn_optimizer_gui). The top is 0 instead -- see top_columns
        # below for the nesting level that pays for it.
        main_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))

        # Everything above the Capture Log sits in a two-column grid:
        # column 1 = the capture controls at a fixed 610px, column 2 =
        # the Upgrade Log settings taking whatever is left. weight=0 +
        # minsize pins the left column; an equal-weight `uniform` pair
        # would force a 50/50 split and ignore left_col's width request.
        top_columns = ttk.Frame(main_frame)
        # spacing: tab list -> first element
        # pady top is 0, not 2: this tab has an extra nesting level that
        # the other tabs don't (main_frame -> top_columns -> left_col),
        # so a value here would stack on top of one the other tabs never
        # pay and drop the heading below theirs.
        top_columns.pack(fill=tk.X, pady=(0, 2))
        # Column 0 is fixed and column 1 takes the rest, so this width is
        # what sets the Upgrade Log Settings panel's: every pixel taken
        # off here is one the panel gains.
        top_columns.grid_columnconfigure(0, weight=0, minsize=LEFT_COLUMN_PX)
        top_columns.grid_columnconfigure(1, weight=1)

        left_col = ttk.Frame(top_columns)
        # spacing: content frame -> content frame
        # The widest lever on this tab: everything down the left side is
        # a child of this frame, so its padx positions the heading,
        # Status, Server Region, Requirements and the button row at once.
        left_col.grid(row=0, column=0, sticky="nsew", padx=2)
        # grid_propagate(False) caps the frame at the requested width;
        # without it a wide child (the button row) would push the column
        # past minsize.
        left_col.configure(width=LEFT_COLUMN_PX)
        left_col.grid_propagate(False)

        # spacing: frame edge -> first non-button element
        # The frame's own padding is NOT the lever for the left inset --
        # the explanation label below carries that, for the reason given
        # there.
        right_col = ttk.LabelFrame(top_columns, text="Upgrade Log Settings",
                                   padding=(3, 1, 4, 3))
        # spacing: TBD -- panel title -> heading in the adjacent column
        # The pady top lands this LabelFrame's title on the same line as
        # the left column's heading: a LabelFrame title has no internal
        # leading above it, where the 14pt heading beside it keeps a
        # little after its negative padding.
        right_col.grid(row=0, column=1, sticky="nsew", padx=2, pady=(3, 0))

        # spacing: frame edge -> first non-button element
        # spacing: explanation text -> the controls it explains
        # Corrected on this LABEL rather than on the panel's padding: the
        # checkboxes below are already on target, and a frame-level shift
        # would move them off it to bring this one on.
        ttk.Label(
            right_col,
            text="Assigned presets compared in the Upgraded log lines' "
                 "Highest Potential.\nChecking or unchecking a preset "
                 "excludes it (and re-writes the last Upgraded line).",
            foreground=self.colors["fg_dim"], justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=(1, 0), pady=(0, 0))

        # Mismatch filters, bottom-left, two columns. Packed BEFORE the
        # checklist so the checklist's expand=True doesn't swallow the
        # cavity these need. Global (settings.json), all on by default;
        # toggling one re-writes the last Upgraded line, as a preset
        # toggle does.
        options_frame = ttk.Frame(right_col)
        # spacing: checkboxes -> unrelated checkboxes
        # (from the Log Presets checklist above. No audit entry covers
        # this rule anywhere yet.)
        options_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        options_frame.grid_columnconfigure(1, weight=1)

        sm = self.context.settings_manager

        def _filter_checkbox(text, key, row, column):
            var = tk.BooleanVar(
                value=(bool(sm.get(key, True)) if sm is not None else True)
            )
            # spacing: element and its label ↔ element and its label
            make_checkbox(
                options_frame, self.colors, text=text, variable=var,
                command=lambda: self._on_log_filter_toggle(key, var),
            ).grid(row=row, column=column, sticky=tk.W,
                   padx=(0, 10) if column == 0 else 0)
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

        # Title and subtitle share one line, bottom-aligned (as on the
        # Gear Score tab).
        title_frame = ttk.Frame(left_col)
        # spacing: content frame -> content frame
        title_frame.pack(fill=tk.X, pady=(0, 2))

        # spacing: header subtext
        # The vertical padding corrects the font's internal offsets, not
        # layout -- see docs/ui_spacing.md "The rules". The LEFT
        # component is a different job: this tab nests one level deeper
        # than the other headers (main_frame -> top_columns -> left_col),
        # so the accumulated container padding sits the heading right of
        # theirs; this pulls it back, and takes one more. The subtitle
        # follows automatically -- pack places it after this label's (now
        # narrower) box.
        ttk.Label(title_frame, text="Data Capture", padding=(-3, -3, 0, -2),
                  font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT, anchor=tk.S)
        ttk.Label(title_frame, text="Capture game data by intercepting API traffic",
                  foreground=self.colors["fg_dim"],
                  padding=(0, 0, 0, -4)).pack(
                      side=tk.LEFT, anchor=tk.S, padx=(10, 0), pady=(0, 0))

        # spacing: exception -- frame edge -> first non-button element
        # The LEFT inset deliberately does not meet it, and the panel is
        # left out of the audit for that; see docs/ui_spacing.md.
        status_frame = ttk.LabelFrame(left_col, text="Status", padding=(5, 1, 5, 3))
        # spacing: content frame -> content frame
        status_frame.pack(fill=tk.X, pady=2)

        # spacing: header subtext
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
        self.capture_info_label.pack(side=tk.LEFT, anchor=tk.S,
                                     padx=(10, 0), pady=(0, 2))

        # spacing: frame edge -> first non-button element
        region_frame = ttk.LabelFrame(left_col, text="Server Region", padding=(4, 6, 5, 5))
        # spacing: content frame -> content frame
        region_frame.pack(fill=tk.X, padx=0, pady=2)

        region_inner = ttk.Frame(region_frame)
        region_inner.pack(fill=tk.X)

        # A READOUT, not a choice. Both regions are redirected during a
        # capture and the addon forwards each connection to its own
        # server, so which one the game uses is the game's business --
        # there is nothing for the user to get wrong, and nothing to
        # select. This reports what was observed.
        # spacing: label ↔ its element
        ttk.Label(region_inner, text="Region:").pack(side=tk.LEFT, padx=(0, 10))

        self.region_var = tk.StringVar(value=REGION_UNKNOWN)
        # spacing: label ↔ its element
        self.detected_label = ttk.Label(
            region_inner,
            textvariable=self.region_var,
            foreground=self.colors["fg_dim"],
        )
        self.detected_label.pack(side=tk.LEFT)

        # spacing: button -> button
        # The trailing padx on each button below is the lever. The row
        # sits in a borderless ttk.Frame, so there is no frame edge for
        # the button rule's left and bottom to measure against; only the
        # gap between the buttons themselves applies here.
        btn_frame = ttk.Frame(left_col)
        # spacing: content frame -> content frame
        btn_frame.pack(fill=tk.X, pady=2)

        self.capture_start_btn = ttk.Button(btn_frame, text="Start Capture",
                                             command=self.start_capture, width=18)
        self.capture_start_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.capture_stop_btn = ttk.Button(btn_frame, text="Stop Capture",
                                            command=self.stop_capture,
                                            width=18, state=tk.DISABLED)
        self.capture_stop_btn.pack(side=tk.LEFT, padx=(0, 4))

        ttk.Button(btn_frame, text="Open Snapshots",
                   command=self.open_snapshots_folder, width=15).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Load Latest",
                   command=self.load_latest_capture, width=12).pack(side=tk.LEFT)

        self.debug_var = tk.BooleanVar(value=False)
        # wraplength keeps the label narrow inside the fixed-width left
        # column instead of pushing the button row wider.
        self.debug_checkbox = make_checkbox(
            btn_frame, self.colors, text="Debug WebSocket traffic",
            variable=self.debug_var, wraplength=100,
        )
        # Enable to log every WebSocket message to a websocket_debug_*.jsonl
        # file in the snapshots folder — useful when adding support for new
        # packet types (e.g., fragment create/delete).
        # spacing: TBD -- button row -> a checkbox beside it
        self.debug_checkbox.pack(side=tk.LEFT, padx=(6, 0))

        # spacing: frame edge -> first non-button element
        # The right edge carries slack, not a target: the frame is
        # stretched wider than its text.
        req_frame = ttk.LabelFrame(left_col, text="Requirements", padding=(4, 2, 5, 4))
        # spacing: content frame -> content frame
        req_frame.pack(fill=tk.X, pady=2)

        requirements_text = """- Run as Administrator (required for hosts file modification)
- Certificate installed (see Setup tab)
- Game must be closed before starting capture
- After starting capture, launch the game and load into the main menu
- Data loads automatically, keep capture running to see live updates as you make changes
- If you stop the capture, close the game before starting a new capture"""

        ttk.Label(req_frame, text=requirements_text, justify=tk.LEFT).pack(anchor=tk.W)

        # spacing: content frame -> content frame
        # This padx and main_frame's own sum to the gap from the window
        # edge, matching every other bordered panel.
        #
        # No frame padding: the text inset lives on the Text's own
        # padx/pady, so its lighter background reaches the frame border.
        log_frame = ttk.LabelFrame(main_frame, text="Capture Log", padding=0)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # spacing: frame edge -> first non-button element
        # The panel's inset sits here rather than on the LabelFrame,
        # inside the text widget's own lighter background. The pady has
        # the line box's leading above the first glyph netted out of it,
        # which is why it differs between text panels in different fonts.
        # The helper carries the dark palette, zeroes Tk's default border
        # and focus ring, and darkens the wrapping frame and scrollbar
        # that the ScrolledText builds for itself -- none of which the
        # constructor can reach. See ui/utils/scrolled_text.py.
        self.capture_log = make_scrolled_text(
            log_frame, self.colors, height=15, wrap=tk.WORD,
        )
        self.capture_log.pack(fill=tk.BOTH, expand=True)

        self.capture_log.tag_configure("success", foreground=self.colors["green"])
        self.capture_log.tag_configure("error", foreground=self.colors["red"])
        self.capture_log.tag_configure("warning", foreground=self.colors["yellow"])
        self.capture_log.tag_configure("info", foreground=self.colors["accent"])

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
        self.capture_log.insert(tk.END, f"{msg}\n", tag)
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
        t.insert(tk.END, f"{msg}\n", tag)
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
            t.insert("upg_start", f"{msg}\n", tag)
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

        columns = LOG_PRESET_COLUMNS
        # Every column but the LAST absorbs the leftover width. Sizing
        # them all alike instead (weight + uniform) makes the last column
        # as wide as the widest label in the whole grid, and the distance
        # from its own label to the panel edge is then that difference
        # rather than the frame-edge rule's gap.
        for c in range(columns - 1):
            frame.grid_columnconfigure(c, weight=1)
        frame.grid_columnconfigure(columns - 1, weight=0)
        for idx, name in enumerate(sorted(preset_to_ids)):
            ids = preset_to_ids[name]
            checked = (any(lpm.is_selected(r) for r in ids)
                       if lpm is not None else True)
            var = tk.BooleanVar(value=checked)
            cb = make_checkbox(
                frame, self.colors, text=name, variable=var,
                fg=self._preset_element_colour(ids),
                command=lambda n=name, v=var: self._on_log_preset_toggle(n, v),
            )
            column = idx % columns
            # spacing: element and its label ↔ element and its label
            # Leading pad, so the last column ends at its own label and
            # the panel's frame-edge padding is the only gap after it.
            cb.grid(row=idx // columns, column=column,
                    sticky=tk.W,
                    padx=(0 if column == 0 else LOG_PRESET_COLUMN_GAP, 0))
            self._log_preset_vars[name] = var

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
                text="Launch the game and load into the main menu. Keep running for live updates."
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
