"""Capture tab for intercepting game data."""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from capture import check_prerequisites, CaptureError
from capture.constants import SERVERS
from ..base_tab import BaseTab


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
        # True once log_upgrade_msg has set the upg_start/upg_end marks
        # (rewrite_last_upgrade_line no-ops before the first upgrade).
        self._has_upgrade_marks = False

        self.setup_ui()
        self.refresh_log_presets()
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
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Everything above the Capture Log sits in a two-column grid:
        # column 1 = the capture controls, column 2 = the Log Presets
        # checklist. uniform="capcols" + equal weights = equal widths.
        top_columns = ttk.Frame(main_frame)
        top_columns.pack(fill=tk.X)
        top_columns.grid_columnconfigure(0, weight=1, uniform="capcols")
        top_columns.grid_columnconfigure(1, weight=1, uniform="capcols")

        left_col = ttk.Frame(top_columns)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        right_col = ttk.LabelFrame(top_columns, text="Upgrade Log Presets", padding=10)
        right_col.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        ttk.Label(
            right_col,
            text="Assigned presets compared in the Upgraded log lines' "
                 "Highest Potential.\nChecking or unchecking a preset "
                 "excludes it (and re-writes the last Upgraded line).",
            foreground=self.colors["fg_dim"], justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 5))
        self.log_presets_list_frame = ttk.Frame(right_col)
        self.log_presets_list_frame.pack(fill=tk.BOTH, expand=True)

        title_frame = ttk.Frame(left_col)
        title_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(title_frame, text="Data Capture",
                  font=("Segoe UI", 14, "bold")).pack(anchor=tk.W)
        ttk.Label(title_frame, text="Capture game data by intercepting API traffic",
                  foreground=self.colors["fg_dim"]).pack(anchor=tk.W)

        # Status frame
        status_frame = ttk.LabelFrame(left_col, text="Status", padding=10)
        status_frame.pack(fill=tk.X, pady=(0, 10))

        self.capture_status_label = ttk.Label(status_frame, text="Ready",
                                               font=("Segoe UI", 12))
        self.capture_status_label.pack(anchor=tk.W)

        self.capture_info_label = ttk.Label(status_frame,
                                             text="Click 'Start Capture' to begin",
                                             foreground=self.colors["fg_dim"])
        self.capture_info_label.pack(anchor=tk.W)

        # Server Region Selection Frame
        region_frame = ttk.LabelFrame(left_col, text="Server Region", padding=10)
        region_frame.pack(fill=tk.X, padx=0, pady=(0, 10))

        region_inner = ttk.Frame(region_frame)
        region_inner.pack(fill=tk.X)

        ttk.Label(region_inner, text="Region:").pack(side=tk.LEFT, padx=(0, 10))

        # Dropdown with server options
        self.region_var = tk.StringVar(value=self.context.config.server_region)
        self.region_dropdown = ttk.Combobox(
            region_inner,
            textvariable=self.region_var,
            values=list(SERVERS.keys()),
            state="readonly",
            width=15
        )
        self.region_dropdown.pack(side=tk.LEFT, padx=(0, 10))
        self.region_dropdown.bind("<<ComboboxSelected>>", self._on_region_changed)

        # Display label showing detected region (initially hidden)
        self.detected_label = ttk.Label(
            region_inner,
            text="",
            foreground=self.colors['green']
        )
        self.detected_label.pack(side=tk.LEFT, padx=(10, 0))

        # Button frame
        btn_frame = ttk.Frame(left_col)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.capture_start_btn = ttk.Button(btn_frame, text="Start Capture",
                                             command=self.start_capture, width=18)
        self.capture_start_btn.pack(side=tk.LEFT, padx=(0, 10))

        self.capture_stop_btn = ttk.Button(btn_frame, text="Stop Capture",
                                            command=self.stop_capture,
                                            width=18, state=tk.DISABLED)
        self.capture_stop_btn.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(btn_frame, text="Open Snapshots",
                   command=self.open_snapshots_folder, width=15).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(btn_frame, text="Load Latest",
                   command=self.load_latest_capture, width=12).pack(side=tk.LEFT, padx=(0, 10))

        self.debug_var = tk.BooleanVar(value=False)
        self.debug_checkbox = ttk.Checkbutton(
            btn_frame, text="Debug WebSocket traffic", variable=self.debug_var
        )
        # Enable to log every WebSocket message to a websocket_debug_*.jsonl
        # file in the snapshots folder — useful when adding support for new
        # packet types (e.g., fragment create/delete).
        self.debug_checkbox.pack(side=tk.LEFT, padx=(10, 0))

        # Requirements frame
        req_frame = ttk.LabelFrame(left_col, text="Requirements", padding=10)
        req_frame.pack(fill=tk.X)

        requirements_text = """- Run as Administrator (required for hosts file modification)
- Certificate installed (see Setup tab)
- Game must be closed before starting capture
- After starting capture, launch the game and load into the main menu
- Data loads automatically, keep capture running to see live updates as you make changes
- If you stop the capture, close the game before starting a new capture"""

        ttk.Label(req_frame, text=requirements_text, justify=tk.LEFT).pack(anchor=tk.W)

        # Log frame
        log_frame = ttk.LabelFrame(main_frame, text="Capture Log", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        self.capture_log = scrolledtext.ScrolledText(
            log_frame, height=15, wrap=tk.WORD,
            bg=self.colors["bg_light"], fg=self.colors["fg"],
            insertbackground=self.colors["fg"]
        )
        self.capture_log.pack(fill=tk.BOTH, expand=True)

        self.capture_log.tag_configure("success", foreground=self.colors["green"])
        self.capture_log.tag_configure("error", foreground=self.colors["red"])
        self.capture_log.tag_configure("warning", foreground=self.colors["yellow"])
        self.capture_log.tag_configure("info", foreground=self.colors["accent"])

    def capture_log_msg(self, msg: str, tag: str = None):
        """Add a message to the capture log."""
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

        # Three equal columns, filled left-to-right then down.
        for c in range(3):
            frame.grid_columnconfigure(c, weight=1, uniform="logpresets")
        for idx, name in enumerate(sorted(preset_to_ids)):
            ids = preset_to_ids[name]
            checked = (any(lpm.is_selected(r) for r in ids)
                       if lpm is not None else True)
            var = tk.BooleanVar(value=checked)
            cb = ttk.Checkbutton(
                frame, text=name, variable=var,
                command=lambda n=name, v=var: self._on_log_preset_toggle(n, v),
            )
            cb.grid(row=idx // 3, column=idx % 3, sticky=tk.W, padx=(0, 8))
            self._log_preset_vars[name] = var

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

    def check_capture_prerequisites(self):
        """Check capture prerequisites using capture module."""
        self.capture_log_msg("Checking prerequisites...")

        status = check_prerequisites()

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
        self.context.capture_manager.resolve_game_server()

        if self.context.capture_manager.game_server_ips:
            for host, ip in self.context.capture_manager.game_server_ips.items():
                self.capture_log_msg(f"  {host} -> {ip}")
            self.capture_log_msg("[OK] Ready to capture!", "success")
        else:
            self.capture_log_msg("[X] Could not resolve game servers", "error")
            self.capture_start_btn.config(state=tk.DISABLED)

    def start_capture(self):
        """Start capture using CaptureManager."""
        try:
            # Set region before starting
            selected_region = self.region_var.get()
            self.context.capture_manager.set_region(selected_region)

            # Disable region dropdown and debug checkbox during capture
            self.region_dropdown.config(state="disabled")
            self.debug_checkbox.config(state=tk.DISABLED)

            self.context.capture_manager.start_capture(debug_mode=self.debug_var.get())
            self.capture_start_btn.config(state=tk.DISABLED)
            self.capture_stop_btn.config(state=tk.NORMAL)
            self.capture_info_label.config(
                text="Launch the game and load into the main menu. Keep running for live updates."
            )
        except CaptureError as e:
            messagebox.showerror("Capture Error", str(e))

    def stop_capture(self):
        """Stop capture and handle auto-detection."""
        result = self.context.capture_manager.stop_capture()

        # Re-enable region dropdown and debug checkbox
        self.region_dropdown.config(state="readonly")
        self.debug_checkbox.config(state=tk.NORMAL)

        self.capture_start_btn.config(state=tk.NORMAL)
        self.capture_stop_btn.config(state=tk.DISABLED)
        self.capture_info_label.config(text="Check snapshots folder for your data")

        if result:
            captured_file, detected_region = result

            # Auto-detection logic
            if detected_region and detected_region != self.region_var.get():
                # Auto-switch with notification
                self.region_var.set(detected_region)

                server_name = SERVERS[detected_region].display_name
                self.capture_log_msg(
                    f"✓ Auto-detected {server_name} server, updated selection",
                    "success"
                )
                self.detected_label.config(text=f"✓ Detected: {server_name}")

                # Persist (writes through settings.json)
                self.context.config.server_region = detected_region

            self.capture_log_msg(f"Capture file: {captured_file.name}", "success")

    def _on_region_changed(self, *args):
        """Called when user manually changes region dropdown."""
        new_region = self.region_var.get()

        # Persist (writes through settings.json)
        self.context.config.server_region = new_region

        # Clear detection label (manual selection)
        self.detected_label.config(text="")

        self.capture_log_msg(f"Region changed to: {SERVERS[new_region].display_name}", "info")

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
