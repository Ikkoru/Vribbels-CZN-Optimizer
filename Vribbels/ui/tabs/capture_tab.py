"""Capture tab for intercepting game data."""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from capture import check_prerequisites, CaptureError
from capture.constants import SERVERS
from config import save_config
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

        self.setup_ui()

        # Auto-check prerequisites after UI setup
        self.root.after(500, self.check_capture_prerequisites)

    def setup_ui(self):
        """Setup the Capture tab UI."""
        main_frame = ttk.Frame(self.frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        title_frame = ttk.Frame(main_frame)
        title_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(title_frame, text="Data Capture",
                  font=("Segoe UI", 14, "bold")).pack(anchor=tk.W)
        ttk.Label(title_frame, text="Capture game data by intercepting API traffic",
                  foreground=self.colors["fg_dim"]).pack(anchor=tk.W)

        # Status frame
        status_frame = ttk.LabelFrame(main_frame, text="Status", padding=10)
        status_frame.pack(fill=tk.X, pady=(0, 10))

        self.capture_status_label = ttk.Label(status_frame, text="Ready",
                                               font=("Segoe UI", 12))
        self.capture_status_label.pack(anchor=tk.W)

        self.capture_info_label = ttk.Label(status_frame,
                                             text="Click 'Start Capture' to begin",
                                             foreground=self.colors["fg_dim"])
        self.capture_info_label.pack(anchor=tk.W)

        # Server Region Selection Frame
        region_frame = ttk.LabelFrame(main_frame, text="Server Region", padding=10)
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
        btn_frame = ttk.Frame(main_frame)
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
        req_frame = ttk.LabelFrame(main_frame, text="Requirements", padding=10)
        req_frame.pack(fill=tk.X, pady=(0, 10))

        requirements_text = """- Run as Administrator (required for hosts file modification)
- Certificate installed (see Setup tab)
- Game must be closed before starting capture
- After starting capture, launch the game and load into the main menu
- Data loads automatically, keep capture running to see live updates as you make changes
- If you stop the capture, close the game before starting a new capture"""

        ttk.Label(req_frame, text=requirements_text, justify=tk.LEFT).pack(anchor=tk.W)

        # Log frame
        log_frame = ttk.LabelFrame(main_frame, text="Capture Log", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True)

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

                # Save to config
                self.context.config.server_region = detected_region
                save_config(self.context.config)

            self.capture_log_msg(f"Capture file: {captured_file.name}", "success")

    def _on_region_changed(self, *args):
        """Called when user manually changes region dropdown."""
        new_region = self.region_var.get()

        # Update config
        self.context.config.server_region = new_region
        save_config(self.context.config)

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
