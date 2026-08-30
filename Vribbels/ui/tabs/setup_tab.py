"""Setup tab for first-time configuration and prerequisite checking.

Also hosts the "Restore Defaults" panel (right of "Setup Status") and
its modal dialogs (`Restore Default Presets`, `Restore Default Combatant
Presets`, `Restore Default Combatant Settings`) for restoring missing
defaults and replacing changed defaults at per-entry granularity. See
`_open_restore_dialog` and the helpers it calls (`_compute_diffs`,
`_apply_restore_changes`).

The three "kinds" of restore share a generalized dialog (grid-laid-out
rows with stable column positions) and differ only in:
  - which file under `default_settings/` is the source of truth
  - how missing / changed is computed (key choice + diff function)
  - how a restoration is applied (which manager call to make)
  - whether the right frame shows a Rename column (only kind=="presets")
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import copy
import subprocess
import ctypes
import threading
from pathlib import Path
import sys
from capture import setup_certificate, open_certificate, find_mitmdump
from ..base_tab import BaseTab
from ..utils.button_width import (
    BUTTON_W_LARGE, BUTTON_W_SMALL, BUTTON_W_TINY)
from ..utils.checkbox import make_checkbox
from ..utils.scrolled_text import make_scrolled_text
from ..utils.tab_header import make_tab_header
from defaults_sync import resolve_defaults_dir


_RENAME_PLACEHOLDER = "Rename current preset to..."

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
    """
    Setup tab for configuring prerequisites before using capture feature.

    Displays status of:
    - Python installation
    - mitmproxy installation
    - Certificate generation
    - Administrator privileges

    Also hosts the "Restore Defaults" panel with three buttons, one per
    defaultable file.
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

    def setup_ui(self):
        """Setup the Setup tab UI."""
        main_frame = ttk.Frame(self.frame)
        # spacing: content frame -> content frame -- frame, frame ↔↕
        # spacing: tab list -> first element -- tab, frame ↕
        main_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=(0, 2))

        make_tab_header(
            main_frame, self.colors, "First-Time Setup",
            "Complete these steps before using the capture feature")

        # Top row: Setup Status (left) and Restore Defaults (right)
        # side-by-side in equal-width columns.
        top_row = ttk.Frame(main_frame)
        # spacing: panel ↕ unrelated label -- heading, panel ↕
        # spacing: content frame -> content frame -- frame, frame ↕
        # Asymmetric, because the two sides answer to different rules.
        # ABOVE is the tab heading against Setup Status' title, text over
        # a panel, and this tab spends one nesting level more on that run
        # than the two other headed tabs -- so the leading side gives it
        # back rather than the shared header helper losing a pixel the
        # others need.
        top_row.pack(fill=tk.X, pady=(0, 2))
        top_row.grid_columnconfigure(0, weight=1, uniform="halves")
        top_row.grid_columnconfigure(1, weight=1, uniform="halves")

        # spacing: exception -- border edge -> first non-button element -- panel, label ↔↕
        # Both directions miss the rule, for two different reasons.
        #
        # LEFT renders 7 where the rule asks 5, deliberately: this panel
        # is built to read before anything else on the tab and its left
        # edge is placed for that. The audit tracks it at 7 rather than
        # leaving it out, so a drift from 7 still shows.
        #
        # TOP is out of reach in any case -- a Segoe UI 11 label's ink
        # starts 7px below its own box top, so even a padding of 0
        # renders 7 -- and it is wanted anyway: these four rows read as
        # one block at a single pitch, so the gap above the first row
        # matches the gaps between them.
        #
        # BOTTOM is larger than it looks because the rows carry no
        # pady of their own -- it supplies the whole pitch under the
        # last row where the others split it between two neighbours.
        status_frame = ttk.LabelFrame(top_row, text="Setup Status",
                                      padding=(4, 4, 5, 7))
        # spacing: content frame -> content frame -- frame, frame ↔↕
        status_frame.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)

        # spacing: unique -- Setup Status stands apart on purpose -- label, label ↕
        # This panel is the first thing a new user sees, and the one
        # place a troubleshooter reads whether the four prerequisites
        # are live. So it is deliberately not built to the app's
        # defaults: Segoe UI 11 rather than 9, a pitch of its own, and
        # a size that matches Restore Defaults beside it. The larger
        # font is also why its padding values differ from every other
        # panel's while its border-edge TARGET does not -- a Segoe UI
        # 11 glyph starts further inside its box than a 9 does.
        #
        # The rows carry no pady: a Segoe UI 11 label's own line box
        # already contributes 7px above its ink and 4 below, which is
        # the whole pitch. Anything added here lands on top of that.
        # The frame's top and bottom padding make the first and last
        # gaps match; docs/ui_spacing.md records what they read.
        self.python_status = ttk.Label(status_frame, text="Checking Python...",
                                        font=("Segoe UI", 11))
        self.python_status.pack(anchor=tk.W)

        self.mitmproxy_status = ttk.Label(status_frame, text="Checking mitmproxy...",
                                           font=("Segoe UI", 11))
        self.mitmproxy_status.pack(anchor=tk.W)

        self.cert_status = ttk.Label(status_frame, text="Checking certificate...",
                                      font=("Segoe UI", 11))
        self.cert_status.pack(anchor=tk.W)

        self.admin_status = ttk.Label(status_frame, text="Checking admin rights...",
                                       font=("Segoe UI", 11))
        self.admin_status.pack(anchor=tk.W)

        # Restore Defaults panel: three [button + explanation] rows.
        # spacing: border edge -> button -- panel, button ↔↕
        # Every edge whose neighbour is a button carries the button
        # rule -- top, left and bottom. The right is slack, the panel
        # being stretched wider than its text.
        restore_frame = ttk.LabelFrame(
            top_row, text="Restore Defaults",
            padding=(RESTORE_EDGE_PAD, RESTORE_EDGE_PAD, 5,
                     RESTORE_EDGE_PAD))
        # spacing: content frame -> content frame -- frame, frame ↔↕
        restore_frame.grid(row=0, column=1, sticky="nsew", padx=2, pady=2)

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
        for index, (label, explanation, kind) in enumerate(button_specs):
            row = ttk.Frame(restore_frame)
            # spacing: button -> button -- button, button ↕
            # The gap goes on the LEADING edge of every row after the
            # first, so the last row adds nothing below itself and the
            # frame's own bottom padding is the only thing between the
            # last button and the edge.
            row.pack(fill=tk.X, anchor=tk.NW,
                     pady=(0 if index == 0 else RESTORE_ROW_GAP, 0))
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
            # own line boxes -- two lines of text sit in a box 4px taller
            # than they need, and that surplus used to make the label the
            # taller child and push the buttons apart. With it gone the
            # BUTTON sets the row height, so the row padding above is the
            # button gap exactly.
            ttk.Label(
                row, text=explanation,
                foreground=self.colors["fg_dim"],
                wraplength=350, justify=tk.LEFT,
                padding=(0, RESTORE_TEXT_TRIM, 0, RESTORE_TEXT_TRIM),
            # This pad answers to the FIRST GLYPH OF EVERY LINE, not just
            # the first line's: the gap is read to the leftmost ink in the
            # whole block. Both lines start on a letter whose leading
            # column of ink is too faint to count, so the pad carries a
            # pixel it would not need if either line began on a solid
            # one. Rewrapping the text can therefore move this value --
            # it did when the explanations gained their line breaks.
            ).grid(row=0, column=1, sticky="w", padx=(1, 0))

        # Button frame
        btn_frame = ttk.Frame(main_frame)
        # spacing: content frame -> content frame -- frame, frame ↕
        btn_frame.pack(fill=tk.X, pady=(0, 2))

        # spacing: button -> button -- button, button ↔
        # Each button's trailing pad meets the next one's leading pad, so
        # the pair sums to the gap between them. The button rule reaches
        # no further here: it is `border edge -> internal button`, and
        # these sit in a plain frame rather than inside a panel, so the
        # leading pad answers to the frame rule and matches main_frame's
        # own.
        ttk.Button(btn_frame, text="Check Status",
                   command=self.check_status, width=BUTTON_W_LARGE).pack(side=tk.LEFT, padx=(2, 2))
        ttk.Button(btn_frame, text="Generate & Install Cert",
                   command=self.setup_cert, width=BUTTON_W_LARGE).pack(side=tk.LEFT, padx=(2, 5))

        # spacing: content frame -> content frame -- frame, frame ↔↕
        # This padx and main_frame's own sum to the gap from the window
        # edge, matching every other bordered panel. The frame itself
        # carries no padding, so the text widget's own background reaches
        # the border; the text inset lives on the Text's padx/pady.
        instr_frame = ttk.LabelFrame(main_frame, text="Setup Instructions",
                                     padding=0)
        # spacing: panel ↕ unrelated label -- button, title ↕
        # The leading side carries the whole gap from the Check Status
        # button row down to this panel's title: the button row's own
        # trailing pad is shared with the run up to the top row, so the
        # correction lands here where nothing else reads it.
        instr_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=(5, 2))

        instructions = """STEP 1: Generate and install certificate
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

        # spacing: border edge -> first non-button element -- panel, text ↔↕
        # The panel's inset sits here rather than on the LabelFrame,
        # inside the text widget's own lighter background. The pady has
        # the line box's leading above the first glyph netted out of it,
        # which is why it differs between text panels in different fonts.
        instr_text = make_scrolled_text(
            instr_frame, self.colors, height=18, wrap=tk.WORD,
        )
        instr_text.insert("1.0", instructions)
        instr_text.config(state=tk.DISABLED)
        instr_text.pack(fill=tk.BOTH, expand=True)

    def check_status(self):
        """Refresh the Setup Status panel.

        Starts a worker and returns immediately; `_apply_status` paints
        the answers back. The probing MUST NOT run inline: it shells out
        to external programs, and a blocked `after()` callback stops Tk
        processing events at all, so the whole program locks up with a
        painted but dead window. That is exactly what used to happen --
        `python --version` can block forever (see `_run_version`), and
        because this check is scheduled a second after the tab is built,
        it took the app down on every launch that hit it.
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

        # ----- Build the dialog -----
        # spacing: out of scope -- a modal dialog, deferred like the
        # Materials and About tabs. The rules scope to the tabs' own
        # panels, so nothing below here is measured or marked.
        dlg = tk.Toplevel(self.frame)
        dlg.title(meta["dialog_title"])
        dlg.transient(self.root)
        dlg.grab_set()
        try:
            dlg.configure(bg=self.colors["bg"])
        except tk.TclError:
            pass

        outer = ttk.Frame(dlg, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        frames_row = ttk.Frame(outer)
        frames_row.pack(fill=tk.BOTH, expand=True)
        frames_row.grid_columnconfigure(0, weight=1, uniform="halves")
        frames_row.grid_columnconfigure(1, weight=1, uniform="halves")
        frames_row.grid_rowconfigure(0, weight=1)

        missing_data: dict = {}   # key -> {"restore": BooleanVar, "display": str}
        changed_data: dict = {}   # key -> see _build_changed_row

        self._build_missing_frame(frames_row, missing, missing_data)
        self._build_changed_frame(frames_row, changed, changed_data, meta["show_rename"])

        # ----- Restore / Cancel -----
        bottom = ttk.Frame(outer)
        bottom.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(
            bottom, text="Cancel", width=BUTTON_W_SMALL,
            command=dlg.destroy,
        ).pack(side=tk.RIGHT)
        ttk.Button(
            bottom, text="Restore", width=BUTTON_W_SMALL,
            command=lambda: self._apply_restore_changes(
                kind, mgr, defaults_path, missing_data, changed_data, dlg,
            ),
        ).pack(side=tk.RIGHT, padx=(0, 5))

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

    # ----- frame builders -----

    def _build_missing_frame(self, parent, missing, missing_data: dict) -> None:
        """Build the "Restore Missing" frame using grid for stable
        column alignment.

        missing is a list of (key, display_name) tuples. missing_data
        is filled by this function: key -> {"restore": BooleanVar,
        "display": str}.
        """
        left = ttk.LabelFrame(parent, text="Restore Missing", padding=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        rows = ttk.Frame(left)
        rows.pack(fill=tk.BOTH, expand=True)

        # Header row at grid row 0.
        ttk.Label(
            rows, text="Restore",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 16), pady=(0, 4))
        ttk.Label(
            rows, text="Name",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=1, sticky="w", pady=(0, 4))

        if not missing:
            ttk.Label(
                rows, text="(none missing)",
                foreground=self.colors["fg_dim"],
            ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        else:
            for i, (key, display) in enumerate(missing):
                grid_row = i + 1
                var = tk.BooleanVar(value=True)
                missing_data[key] = {"restore": var, "display": display}
                make_checkbox(rows, self.colors, variable=var).grid(
                    row=grid_row, column=0, sticky="w", padx=(0, 16), pady=1,
                )
                ttk.Label(rows, text=display).grid(
                    row=grid_row, column=1, sticky="w", pady=1,
                )

        buttons = ttk.Frame(left)
        buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(
            buttons, text="All", width=BUTTON_W_TINY,
            command=lambda: self._toggle_all(missing_data, "restore", True),
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            buttons, text="None", width=BUTTON_W_TINY,
            command=lambda: self._toggle_all(missing_data, "restore", False),
        ).pack(side=tk.LEFT)

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
        right = ttk.LabelFrame(parent, text="Replace Changed", padding=8)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        rows = ttk.Frame(right)
        rows.pack(fill=tk.BOTH, expand=True)

        # Reserve a fixed minimum width for column 3 (the rename text
        # entry). Without this the column has zero size while every
        # entry is hidden, and the dialog visibly RESIZES the first
        # time any Rename checkbox is ticked. 220px fits the 26-char
        # Entry plus breathing room.
        if show_rename:
            rows.grid_columnconfigure(3, minsize=220)

        # Header row.
        ttk.Label(
            rows, text="Replace",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 16), pady=(0, 4))
        ttk.Label(
            rows, text="Name",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=1, sticky="w", padx=(0, 16), pady=(0, 4))
        if show_rename:
            ttk.Label(
                rows, text="Also Rename and Keep Current",
                font=("Segoe UI", 9, "bold"),
            ).grid(row=0, column=2, columnspan=2, sticky="w", pady=(0, 4))

        if not changed:
            ttk.Label(
                rows, text="(no changes)",
                foreground=self.colors["fg_dim"],
            ).grid(
                row=1, column=0,
                columnspan=4 if show_rename else 2,
                sticky="w", pady=(2, 0),
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

        buttons = ttk.Frame(right)
        buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(
            buttons, text="All", width=BUTTON_W_TINY,
            command=lambda: self._toggle_all(changed_data, "replace", True),
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            buttons, text="None", width=BUTTON_W_TINY,
            command=lambda: self._toggle_all(changed_data, "replace", False),
        ).pack(side=tk.LEFT)

    def _build_changed_row_simple(
        self, parent_grid, grid_row, key, display, changed_data: dict,
    ) -> None:
        """Simple per-row builder (no Rename) for character_preset and
        optimizer_settings restores."""
        replace_var = tk.BooleanVar(value=True)
        make_checkbox(parent_grid, self.colors,
                      variable=replace_var).grid(
            row=grid_row, column=0, sticky="w", padx=(0, 16), pady=1,
        )
        ttk.Label(parent_grid, text=display).grid(
            row=grid_row, column=1, sticky="w", padx=(0, 16), pady=1,
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

        make_checkbox(parent_grid, self.colors,
                      variable=replace_var).grid(
            row=grid_row, column=0, sticky="w", padx=(0, 16), pady=1,
        )
        ttk.Label(parent_grid, text=display).grid(
            row=grid_row, column=1, sticky="w", padx=(0, 16), pady=1,
        )
        rename_cb = make_checkbox(parent_grid, self.colors,
                                  variable=rename_var)
        rename_cb.grid(
            row=grid_row, column=2, sticky="w", padx=(0, 6), pady=1,
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
        rename_entry.grid(row=grid_row, column=3, sticky="w", pady=1)
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
