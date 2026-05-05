#!/usr/bin/env python3
"""
Vribbels - CZN Memory Fragment Tool
A Fribbels-inspired gear management and optimization tool for Chaos Zero Nightmare
Includes integrated data capture and setup functionality.
"""

import json
import os
import sys
import itertools
import socket
import subprocess
import shutil
import ctypes
import re
import webbrowser
from dataclasses import dataclass, field
from typing import Optional, Callable
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import queue
from datetime import datetime
from PIL import Image, ImageTk, ImageDraw, ImageFont

# === GAME DATA IMPORTS ===
from game_data import *
from models import *
from capture import *
from optimizer import GearOptimizer
from update_checker import UpdateChecker
from config import load_config, save_config, AppConfig
from ui import AppContext, MaterialsTab, SetupTab, CaptureTab, InventoryTab, OptimizerTab, HeroesTab, ScoringTab, AboutTab


class MultiSelectListbox(tk.Frame):
    """A frame containing a listbox with multi-select capability"""
    def __init__(self, parent, items, height=4, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.listbox = tk.Listbox(self, selectmode=tk.MULTIPLE, height=height,
                                  exportselection=False, bg="#363650", fg="#cdd6f4",
                                  selectbackground="#3b6ea5", selectforeground="#cdd6f4",
                                  highlightthickness=0)
        self.listbox.pack(fill=tk.BOTH, expand=True)
        
        for item in items:
            self.listbox.insert(tk.END, item)
    
    def get_selected(self) -> list[str]:
        indices = self.listbox.curselection()
        return [self.listbox.get(i) for i in indices]
    
    def select_items(self, items: list[str]):
        self.listbox.selection_clear(0, tk.END)
        for i in range(self.listbox.size()):
            if self.listbox.get(i) in items:
                self.listbox.selection_set(i)


class OptimizerGUI:
    def __init__(self):
        # Load configuration
        self.config = load_config()

        self.root = tk.Tk()
        self.root.title("Vribbels - CZN Memory Fragment Optimizer")
        self.root.geometry("1550x1000")
        self.root.minsize(1300, 800)

        self.colors = {
            "bg": "#1e1e2e", "bg_light": "#2a2a3e", "bg_lighter": "#363650",
            "fg": "#cdd6f4", "fg_dim": "#6c7086", "accent": "#89b4fa",
            "green": "#a6e3a1", "red": "#f38ba8", "yellow": "#f9e2af", "purple": "#cba6f7",
            "orange": "#FF8C00", "select": "#3b6ea5",
        }

        self.root.configure(bg=self.colors["bg"])
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.configure_styles()

        self.optimizer = GearOptimizer()

        # Initialize update checker
        self.update_checker = UpdateChecker()

        # Update check state
        self.update_check_queue = queue.Queue()
        self.update_check_done = False

        # Initialize capture manager
        self.capture_manager = CaptureManager(
            output_folder=OUTPUT_DIR,
            log_callback=lambda msg, tag=None: self.capture_tab_instance.capture_log_msg(msg, tag) if hasattr(self, 'capture_tab_instance') else None,
            status_callback=lambda status: self.capture_tab_instance.capture_status_label.config(text=status) if hasattr(self, 'capture_tab_instance') else None,
            live_update_callback=lambda: self.root.after(0, self._handle_live_update)
        )

        # Create AppContext for UI tabs
        self.app_context = AppContext(
            root=self.root,
            notebook=None,  # Set after notebook created in setup_ui
            optimizer=self.optimizer,
            capture_manager=self.capture_manager,
            update_checker=self.update_checker,
            colors=self.colors,
            style=self.style,
            load_file_callback=self.load_file,
            load_data_callback=self.load_data,
            switch_tab_callback=self._switch_to_tab,
            config=self.config
        )

        self.setup_ui()

        # Check for updates if needed (non-blocking)
        if self.update_checker.should_check_now():
            self._check_for_updates_at_startup()
            self.root.after(100, self._check_update_queue)
        else:
            # Re-notify from cached info if a known update exists and isn't skipped
            self._notify_cached_update()

        self.auto_load()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def configure_styles(self):
        self.style.configure(".", background=self.colors["bg"], foreground=self.colors["fg"])
        self.style.configure("TFrame", background=self.colors["bg"])
        self.style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["fg"])
        self.style.configure("TButton", background=self.colors["bg_light"], foreground=self.colors["fg"], padding=5)
        self.style.map("TButton", background=[("active", self.colors["bg_lighter"])])
        self.style.configure("TCombobox", fieldbackground=self.colors["bg_lighter"], background=self.colors["bg_lighter"],
                             foreground=self.colors["fg"], selectbackground=self.colors["select"],
                             selectforeground=self.colors["fg"])
        self.style.map("TCombobox", fieldbackground=[("readonly", self.colors["bg_lighter"])], 
                       foreground=[("readonly", self.colors["fg"])])
        self.style.configure("TCheckbutton", background=self.colors["bg"], foreground=self.colors["fg"])
        self.style.map("TCheckbutton", background=[("active", self.colors["bg_lighter"])],
                       foreground=[("active", self.colors["fg"])])
        self.style.configure("TLabelframe", background=self.colors["bg"])
        self.style.configure("TLabelframe.Label", background=self.colors["bg"], foreground=self.colors["accent"])
        self.style.configure("TScale", background=self.colors["bg"], troughcolor=self.colors["bg_light"])
        self.style.configure("TNotebook", background=self.colors["bg"])
        self.style.configure("TNotebook.Tab", background=self.colors["bg_light"], foreground=self.colors["fg"], padding=[10, 5])
        self.style.map("TNotebook.Tab", background=[("selected", self.colors["bg_lighter"])])
        self.style.configure("Treeview", background=self.colors["bg_light"], foreground=self.colors["fg"],
                             fieldbackground=self.colors["bg_light"], rowheight=24)
        self.style.configure("Treeview.Heading", background=self.colors["bg_lighter"], foreground=self.colors["fg"])
        self.style.map("Treeview.Heading", background=[("active", self.colors["select"])],
                       foreground=[("active", self.colors["fg"])])
        self.style.map("Treeview", background=[("selected", self.colors["select"])],
                       foreground=[("selected", self.colors["fg"])])

    def setup_ui(self):
        top_bar = ttk.Frame(self.root)
        top_bar.pack(fill=tk.X, padx=5, pady=(5, 0))
        
        kofi_btn = tk.Button(top_bar, text="Support on Ko-Fi", 
                            command=lambda: webbrowser.open("https://ko-fi.com/H2H21PHYKW"),
                            bg="#72a4f2", fg="white", font=("Segoe UI", 9, "bold"),
                            relief=tk.FLAT, padx=10, pady=3, cursor="hand2")
        kofi_btn.pack(side=tk.RIGHT, padx=5)
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Update AppContext with notebook reference
        self.app_context.notebook = self.notebook

        # Create OptimizerTab instance
        self.optimizer_tab_instance = OptimizerTab(self.notebook, self.app_context)
        self.optimizer_tab = self.optimizer_tab_instance.get_frame()
        self.notebook.add(self.optimizer_tab, text="Optimizer")

        # Inventory tab - using UI module
        self.inventory_tab_instance = InventoryTab(self.notebook, self.app_context)
        self.inventory_tab = self.inventory_tab_instance.get_frame()
        self.notebook.add(self.inventory_tab, text="Memory Fragments")

        # Materials tab - using UI module
        self.materials_tab_instance = MaterialsTab(self.notebook, self.app_context)
        self.materials_tab = self.materials_tab_instance.get_frame()
        self.notebook.add(self.materials_tab, text="Materials")

        # Heroes tab - using UI module
        self.heroes_tab_instance = HeroesTab(self.notebook, self.app_context)
        self.heroes_tab = self.heroes_tab_instance.get_frame()
        self.notebook.add(self.heroes_tab, text="Combatants")

        # Capture tab - using UI module
        self.capture_tab_instance = CaptureTab(self.notebook, self.app_context)
        self.capture_tab = self.capture_tab_instance.get_frame()
        self.notebook.add(self.capture_tab, text="Capture")
        
        # Setup tab - using UI module
        self.setup_tab_instance = SetupTab(self.notebook, self.app_context)
        self.setup_tab = self.setup_tab_instance.get_frame()
        self.notebook.add(self.setup_tab, text="Setup")

        # Set tab instance references for cross-tab refresh
        self.app_context.inventory_tab = self.inventory_tab_instance
        self.app_context.heroes_tab = self.heroes_tab_instance

        # Scoring tab - using UI module
        self.scoring_tab_instance = ScoringTab(self.notebook, self.app_context)
        self.scoring_tab = self.scoring_tab_instance.get_frame()
        self.notebook.add(self.scoring_tab, text="Scoring")

        # About tab
        self.about_tab_instance = AboutTab(self.notebook, self.app_context)
        self.about_tab = self.about_tab_instance.get_frame()
        self.notebook.add(self.about_tab, text="About")

        # Set update_checker reference in about tab
        self.about_tab_instance.update_checker = self.update_checker

    def _switch_to_tab(self, tab_frame: tk.Widget):
        """Switch notebook to the specified tab frame."""
        self.notebook.select(tab_frame)

    def _check_update_queue(self):
        """Check for update check results from startup background thread."""
        try:
            update_info = self.update_check_queue.get_nowait()
            self._handle_update_check_result(update_info)
        except queue.Empty:
            if not self.update_check_done:
                self.root.after(100, self._check_update_queue)

    def _handle_update_check_result(self, update_info):
        """Handle update check result and show dialog if needed."""
        self.update_check_done = True

        if not update_info or update_info.error or not update_info.update_available:
            return

        # Check if version is skipped
        if self.update_checker.is_version_skipped(update_info.latest_version):
            return

        # Show update dialog
        from update_checker import UpdateDialog
        UpdateDialog(
            self.root,
            self.update_checker,
            update_info.latest_version,
            self.colors
        )

    def _check_for_updates_at_startup(self):
        """Check for updates in background thread (non-blocking)."""
        def do_check():
            try:
                update_info = self.update_checker.check_for_updates()
                self.update_check_queue.put(update_info)
            except Exception as e:
                print(f"Error checking for updates: {e}")
                self.update_check_queue.put(None)

        thread = threading.Thread(target=do_check, daemon=True)
        thread.start()

    def _notify_cached_update(self):
        """Show update dialog from cached metadata if a known update exists and isn't skipped."""
        from packaging import version as pkg_version
        metadata = self.update_checker._read_metadata()
        cached_latest = metadata.get("last_known_latest")
        if not cached_latest:
            return
        try:
            if pkg_version.parse(cached_latest) > pkg_version.parse(self.update_checker.current_version):
                if not self.update_checker.is_version_skipped(cached_latest):
                    from update_checker import UpdateDialog
                    UpdateDialog(self.root, self.update_checker, cached_latest, self.colors)
        except Exception:
            pass

    def on_close(self):
        """Handle window close event."""
        if self.capture_manager.is_capturing():
            if messagebox.askyesno("Confirm Exit", "Capture is still running. Stop and exit?"):
                self.capture_tab_instance.stop_capture()
            else:
                return
        self.root.destroy()

    # New — uses the same logic as the Load Latest button
    def auto_load(self):
        latest = self.capture_manager.get_latest_capture()
        if latest:
            self.load_data(str(latest))

    def load_file(self):
        filepath = filedialog.askopenfilename(
            title="Select Memory Fragment Snapshot",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir="snapshots"
        )
        if filepath:
            self.load_data(filepath)

    def load_data(self, filepath: str):
        try:
            self.optimizer.load_data(filepath)

            # Update optimizer tab UI
            self.optimizer_tab_instance.refresh_after_load()

            # Update other tabs
            self.inventory_tab_instance.populate_set_filters()
            self.inventory_tab_instance.refresh_inventory()
            self.heroes_tab_instance.refresh_heroes()
            self.materials_tab_instance.refresh_materials()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load: {e}")
            import traceback
            traceback.print_exc()

    def _handle_live_update(self):
        """Handle live update from capture — reload latest snapshot and refresh UI."""
        latest = self.capture_manager.get_latest_capture()
        if latest:
            try:
                self.optimizer.load_data(str(latest))
                self.inventory_tab_instance.populate_set_filters()
                self.scoring_tab_instance.apply_custom_weights()  # re-scores and refreshes inventory + heroes
                self.materials_tab_instance.refresh_materials()
            except Exception:
                pass  # Silently ignore reload errors during live monitoring


    def run(self):
        self.root.mainloop()


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_as_admin():
    if sys.platform != "win32":
        return False
    
    try:
        if getattr(sys, 'frozen', False):
            script = sys.executable
            params = " ".join(sys.argv[1:])
        else:
            script = sys.executable
            params = f'"{sys.argv[0]}"'
            if len(sys.argv) > 1:
                params += " " + " ".join(sys.argv[1:])
        
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", script, params, None, 1)
        return ret > 32
    except Exception as e:
        print(f"Failed to elevate: {e}")
        return False


def main():
    if sys.platform == "win32" and not is_admin():
        temp_root = tk.Tk()
        temp_root.withdraw()
        
        response = messagebox.askyesno(
            "Administrator Required",
            "This application needs Administrator privileges for the capture feature.\n\n"
            "Do you want to restart with elevated permissions?\n\n"
            "(Click 'No' to continue without capture functionality)"
        )
        
        temp_root.destroy()
        
        if response:
            if run_as_admin():
                sys.exit(0)
            else:
                temp_root2 = tk.Tk()
                temp_root2.withdraw()
                messagebox.showwarning("Elevation Failed", "Could not get administrator privileges.")
                temp_root2.destroy()
    
    app = OptimizerGUI()
    app.run()


if __name__ == "__main__":
    main()