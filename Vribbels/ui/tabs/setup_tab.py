"""Setup tab for first-time configuration and prerequisite checking.

Round 11 adds a "Restore Defaults" panel to the right of "Setup Status",
plus modal dialogs (`Restore Default Presets`, `Restore Default Combatant
Presets`, `Restore Default Combatant Settings`) for restoring missing
defaults and replacing changed defaults at the per-entry granularity.
See `_open_restore_dialog` and the helpers it calls
(`_compute_diffs`, `_apply_restore_changes`).

The three "kinds" of restore share a generalized dialog (grid-laid-out
rows with stable column positions) and differ only in:
  - which file under `default_settings/` is the source of truth
  - how missing / changed is computed (key choice + diff function)
  - how a restoration is applied (which manager call to make)
  - whether the right frame shows a Rename column (only kind=="presets")
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import json
import copy
import subprocess
import ctypes
from pathlib import Path
import sys
from capture import setup_certificate, open_certificate, find_mitmdump
from ..base_tab import BaseTab
from defaults_sync import resolve_defaults_dir


_RENAME_PLACEHOLDER = "Rename current preset to..."


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

    Round 11: also hosts the "Restore Defaults" panel with three buttons,
    one per defaultable file.
    """

    def __init__(self, parent, context):
        super().__init__(parent, context)

        # Status label widgets
        self.python_status = None
        self.mitmproxy_status = None
        self.cert_status = None
        self.admin_status = None

        self.setup_ui()

        # Auto-check status after UI setup
        self.root.after(1000, self.check_status)

    # ====================================================================
    # UI construction
    # ====================================================================

    def setup_ui(self):
        """Setup the Setup tab UI."""
        main_frame = ttk.Frame(self.frame)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Title
        ttk.Label(main_frame, text="First-Time Setup",
                  font=("Segoe UI", 14, "bold")).pack(anchor=tk.W)
        ttk.Label(main_frame,
                  text="Complete these steps before using the capture feature",
                  foreground=self.colors["fg_dim"]).pack(anchor=tk.W, pady=(0, 10))

        # Round 11: top row holds Setup Status (left) and Restore Defaults
        # (right) side-by-side in equal-width columns.
        top_row = ttk.Frame(main_frame)
        top_row.pack(fill=tk.X, pady=(0, 10))
        top_row.grid_columnconfigure(0, weight=1, uniform="halves")
        top_row.grid_columnconfigure(1, weight=1, uniform="halves")

        status_frame = ttk.LabelFrame(top_row, text="Setup Status", padding=10)
        status_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        self.python_status = ttk.Label(status_frame, text="Checking Python...",
                                        font=("Segoe UI", 10))
        self.python_status.pack(anchor=tk.W, pady=2)

        self.mitmproxy_status = ttk.Label(status_frame, text="Checking mitmproxy...",
                                           font=("Segoe UI", 10))
        self.mitmproxy_status.pack(anchor=tk.W, pady=2)

        self.cert_status = ttk.Label(status_frame, text="Checking certificate...",
                                      font=("Segoe UI", 10))
        self.cert_status.pack(anchor=tk.W, pady=2)

        self.admin_status = ttk.Label(status_frame, text="Checking admin rights...",
                                       font=("Segoe UI", 10))
        self.admin_status.pack(anchor=tk.W, pady=2)

        # Restore Defaults panel: three [button + explanation] rows.
        restore_frame = ttk.LabelFrame(top_row, text="Restore Defaults", padding=10)
        restore_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        button_specs = [
            (
                "Presets",
                "Restores default Gear Score presets. Does NOT delete user presets.",
                "presets",
            ),
            (
                "Combatant Presets",
                "Restores default per-Combatant preset assignments. "
                "Does NOT delete user assignments.",
                "character_preset",
            ),
            (
                "Combatant Settings",
                "Restores default Optimizer tab settings per Combatant. "
                "Does NOT delete user settings.",
                "optimizer_settings",
            ),
        ]
        for label, explanation, kind in button_specs:
            row = ttk.Frame(restore_frame)
            row.pack(fill=tk.X, anchor=tk.NW, pady=(0, 4))
            ttk.Button(
                row, text=label, width=20,
                command=lambda k=kind: self._open_restore_dialog(k),
            ).pack(side=tk.LEFT, anchor=tk.NW)
            ttk.Label(
                row, text=explanation,
                foreground=self.colors["fg_dim"],
                wraplength=240, justify=tk.LEFT,
            ).pack(side=tk.LEFT, padx=(8, 0), anchor=tk.NW)

        # Button frame
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(btn_frame, text="Check Status",
                   command=self.check_status, width=15).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Generate & Install Cert",
                   command=self.setup_cert, width=22).pack(side=tk.LEFT, padx=5)

        # Instructions frame
        instr_frame = ttk.LabelFrame(main_frame, text="Setup Instructions", padding=10)
        instr_frame.pack(fill=tk.BOTH, expand=True)

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

        instr_text = scrolledtext.ScrolledText(
            instr_frame, height=18, wrap=tk.WORD,
            bg=self.colors["bg_light"], fg=self.colors["fg"]
        )
        # Match the Gear Score tab's white-flash fix: force the wrapping
        # frame + scrollbar to dark so we never see a white paint on
        # first show.
        try:
            instr_text.frame.configure(bg=self.colors["bg_light"])
        except (AttributeError, tk.TclError):
            pass
        try:
            instr_text.vbar.configure(
                bg=self.colors["bg_light"],
                troughcolor=self.colors["bg"],
                activebackground=self.colors["bg_lighter"],
            )
        except (AttributeError, tk.TclError):
            pass
        instr_text.insert("1.0", instructions)
        instr_text.config(state=tk.DISABLED)
        instr_text.pack(fill=tk.BOTH, expand=True)

    def check_status(self):
        """Check status of all prerequisites."""
        # Check Python
        try:
            result = subprocess.run(["python", "--version"],
                                     capture_output=True, text=True)
            if result.returncode == 0:
                version = result.stdout.strip() or result.stderr.strip()
                self.python_status.config(text=f"[OK] {version}",
                                           foreground=self.colors["green"])
            else:
                raise FileNotFoundError()
        except:
            self.python_status.config(text="[X] Python not found",
                                       foreground=self.colors["red"])

        # Check mitmproxy
        mitmdump_path = find_mitmdump()
        if mitmdump_path:
            try:
                result = subprocess.run([mitmdump_path, "--version"],
                                         capture_output=True, text=True)
                if result.returncode == 0:
                    version = result.stdout.split()[1] if result.stdout else "installed"
                    self.mitmproxy_status.config(text=f"[OK] mitmproxy {version}",
                                                  foreground=self.colors["green"])
                else:
                    raise FileNotFoundError()
            except:
                self.mitmproxy_status.config(text="[X] mitmproxy not working",
                                              foreground=self.colors["red"])
        else:
            self.mitmproxy_status.config(text="[X] mitmproxy not found",
                                          foreground=self.colors["red"])

        # Check certificate
        cert_path = Path.home() / ".mitmproxy" / "mitmproxy-ca-cert.cer"
        if cert_path.exists():
            self.cert_status.config(text=f"[OK] Certificate exists",
                                     foreground=self.colors["green"])
        else:
            self.cert_status.config(text="[X] Certificate not generated",
                                     foreground=self.colors["red"])

        # Check admin rights
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
            if is_admin:
                self.admin_status.config(text="[OK] Running as Administrator",
                                          foreground=self.colors["green"])
            else:
                self.admin_status.config(text="[!] Not running as Administrator",
                                          foreground=self.colors["yellow"])
        except:
            self.admin_status.config(text="? Could not check admin status",
                                      foreground=self.colors["yellow"])

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
    # Restore Defaults dialog (Round 11)
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
            bottom, text="Cancel", width=10,
            command=dlg.destroy,
        ).pack(side=tk.RIGHT)
        ttk.Button(
            bottom, text="Restore", width=10,
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
                ttk.Checkbutton(rows, variable=var).grid(
                    row=grid_row, column=0, sticky="w", padx=(0, 16), pady=1,
                )
                ttk.Label(rows, text=display).grid(
                    row=grid_row, column=1, sticky="w", pady=1,
                )

        buttons = ttk.Frame(left)
        buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(
            buttons, text="All", width=6,
            command=lambda: self._toggle_all(missing_data, "restore", True),
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            buttons, text="None", width=6,
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
        x-position whether the entry is shown or hidden -- fixes the
        round-11-followup ask where checking Rename made the checkbox
        and the column-header label jump leftward as the entry appeared.

        changed is a list of (key, display_name). changed_data is filled
        with key -> {"replace": BooleanVar, "display": str, plus
        optionally "rename" / "rename_text" / "entry" when show_rename}.
        """
        right = ttk.LabelFrame(parent, text="Replace Changed", padding=8)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        rows = ttk.Frame(right)
        rows.pack(fill=tk.BOTH, expand=True)

        # Round 11 follow-up: reserve a fixed minimum width for column 3
        # (the rename text entry). Without this, the column has zero size
        # when no rows have the entry visible, and the dialog visibly
        # RESIZES the first time the user checks any Rename checkbox
        # (the entry's natural width pushing both panels wider). With
        # minsize set, the entry's slot is always allocated whether the
        # entry is present or not, so toggling Rename just paints in /
        # out of an already-sized cell. 220px fits the 26-char Entry
        # plus a touch of breathing room.
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
            buttons, text="All", width=6,
            command=lambda: self._toggle_all(changed_data, "replace", True),
        ).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(
            buttons, text="None", width=6,
            command=lambda: self._toggle_all(changed_data, "replace", False),
        ).pack(side=tk.LEFT)

    def _build_changed_row_simple(
        self, parent_grid, grid_row, key, display, changed_data: dict,
    ) -> None:
        """Simple per-row builder (no Rename) for character_preset and
        optimizer_settings restores."""
        replace_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(parent_grid, variable=replace_var).grid(
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

        ttk.Checkbutton(parent_grid, variable=replace_var).grid(
            row=grid_row, column=0, sticky="w", padx=(0, 16), pady=1,
        )
        ttk.Label(parent_grid, text=display).grid(
            row=grid_row, column=1, sticky="w", padx=(0, 16), pady=1,
        )
        rename_cb = ttk.Checkbutton(parent_grid, variable=rename_var)
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
        # Hide initially but PRESERVE the grid cell so re-show via
        # grid() places it back in the exact same spot. This is the
        # key alignment-fix: previously the row used pack + before=
        # which let the entry's appearance shift the rename_cb's x.
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

        Round 11 follow-up: treat `None` (no preset assigned, i.e. the
        "Default Preset" UI state) as a non-opinion on BOTH sides.
        Bucket rules:
          - defaults' value is None   -> skip (defaults have no
                                          recommendation to offer for
                                          this character)
          - user's value is None or missing AND defaults' value is
            non-null                  -> Missing (user has no preset of
                                          their own; defaults recommend
                                          something concrete)
          - both non-null and differ  -> Changed (two real opinions in
                                          conflict)
          - both non-null and match   -> skip

        Previously the diff treated user=None vs default="Amir" as
        "Changed", which surprised the user when they'd just reset an
        assignment to Default Preset and saw it pop up in the Replace
        Changed list.

        Both files are normalized to v2 first so we can compare apples
        to apples even if either side is on disk in v1.
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
            re-renders the Preset column; AND the scoring_tab listbox's
            assignment markers refresh via whichever method the tab
            exposes (a couple of method names tried, since the API
            isn't standardized).
          - optimizer_settings -> optimizer_tab.refresh_after_load()
            re-reads the selected combatant's per-char settings into
            the sliders / dropdowns.
        """
        if kind in ("presets", "character_preset"):
            self._safe_call(
                getattr(self.context, "heroes_tab", None),
                "refresh_heroes",
            )
            # scoring_tab listbox markers: try a few candidate method
            # names since the ScoringTab API isn't standardized for
            # this specific refresh. First one that exists wins.
            scoring = getattr(self.context, "scoring_tab", None)
            for name in (
                "refresh_preset_assignments",
                "refresh_preset_list",
                "refresh_preset_listbox",
                "_refresh_preset_listbox",
            ):
                if self._safe_call(scoring, name):
                    break
        if kind == "optimizer_settings":
            self._safe_call(
                getattr(self.context, "optimizer_tab", None),
                "refresh_after_load",
            )

    @staticmethod
    def _safe_call(obj, method_name) -> bool:
        """Call obj.method_name() if obj is non-None and method exists.
        Returns True if the call succeeded (so the caller can stop
        trying alternate method names)."""
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
