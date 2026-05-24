"""
Optimization configuration and execution tab.

Provides UI for configuring gear optimization parameters and viewing results.
Handles background optimization with progress updates and result display.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading
import queue

from ui.base_tab import BaseTab
from ui.context import AppContext
from game_data import (
    SETS, FOUR_PIECE_SETS, TWO_PIECE_SETS,
    SLOT_MAIN_STATS, RARITY_COLORS, ATTRIBUTE_COLORS,
    get_character_by_name
)


class OptimizerTab(BaseTab):
    """
    Main optimization tab for configuring and running gear optimizations.

    Features:
    - Stat priority configuration (sliders for 11 stats)
    - Main stat filters (slots IV/V/VI checkboxes)
    - Set requirements (4-piece and 2-piece multi-select)
    - Exclude hero filters (checkbox grid)
    - Background optimization with progress updates
    - Results display with sortable columns
    - Build comparison view (current vs new stats)
    """

    def __init__(self, parent: tk.Widget, context: AppContext):
        """Initialize OptimizerTab with parent and app context."""
        super().__init__(parent, context)
        self._init_state()
        self.setup_ui()
        # Start queue checking loop for background optimization
        self.root.after(100, self.check_queue)

    def _init_state(self):
        """Initialize all state variables and widget references."""
        # Character selection
        self.selected_character = tk.StringVar()

        # Priority sliders (11 stats: ATK%, Flat ATK, DEF%, etc.)
        self.priority_vars: dict[str, tk.IntVar] = {}
        self.priority_labels: dict[str, ttk.Label] = {}

        # Main stat filters for slots 4, 5, 6
        self.main_stat_vars: dict[int, dict[str, tk.BooleanVar]] = {}

        # Set filters (multi-select checkboxes)
        self.four_piece_vars: dict[str, tk.BooleanVar] = {}
        self.two_piece_vars: dict[str, tk.BooleanVar] = {}

        # Optimization options
        self.top_percent_var = tk.IntVar(value=50)
        self.include_equipped_var = tk.BooleanVar(value=True)
        self.exclude_hero_vars: dict[str, tk.BooleanVar] = {}

        # Results and threading state
        self.optimization_results: list = []
        self.result_queue = queue.Queue()
        self.cancel_flag = [False]  # Mutable list for thread safety

        # Sorting state
        self.result_sort_col = "score"
        self.result_sort_reverse = False

        # Widget references (set during setup_ui)
        self.hero_combo = None
        self.status_label = None
        self.stats_tree = None
        self.result_tree = None
        self.detail_tree = None
        self.progress_label = None
        self.top_pct_label = None
        self.exclude_heroes_frame = None

    def setup_ui(self):
        """Build the optimization tab UI."""
        # Toolbar with hero selector, Start/Stop/Reset buttons.
        # The Load Data button was removed (data loads automatically on
        # capture / app startup via auto_load + _handle_live_update; manual
        # loads can still be done via the Setup tab if needed).
        toolbar = ttk.Frame(self.frame)
        toolbar.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(toolbar, text="Combatant:").pack(side=tk.LEFT, padx=(0, 5))
        self.hero_combo = ttk.Combobox(toolbar, textvariable=self.selected_character,
                                       width=12, state="readonly")
        self.hero_combo.pack(side=tk.LEFT)
        self.hero_combo.bind("<<ComboboxSelected>>", self.on_hero_select)

        ttk.Button(toolbar, text="Start",
                   command=self.run_optimization).pack(side=tk.LEFT, padx=(15, 2))
        ttk.Button(toolbar, text="Stop",
                   command=self.cancel_optimization).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Reset",
                   command=self.reset_settings).pack(side=tk.LEFT, padx=2)

        self.status_label = ttk.Label(toolbar, text="No data loaded",
                                      foreground=self.colors["fg_dim"])
        self.status_label.pack(side=tk.RIGHT, padx=10)

        # Container for pane + detail using grid to guarantee detail space
        body = ttk.Frame(self.frame)
        body.pack(fill=tk.BOTH, expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=0)

        # Main 3-pane layout: Stats Comparison | Configuration | Results
        main_pane = ttk.PanedWindow(body, orient=tk.HORIZONTAL)
        main_pane.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # Left pane: Stats Comparison
        left_frame = ttk.LabelFrame(main_pane, text="Stats Comparison", padding=5)
        main_pane.add(left_frame, weight=1)

        self.stats_tree = ttk.Treeview(left_frame,
                                       columns=("stat", "current", "new", "diff"),
                                       show="headings", height=22)
        self.stats_tree.column("#0", width=0, stretch=False)
        self.stats_tree.heading("stat", text="Stat")
        self.stats_tree.heading("current", text="Current")
        self.stats_tree.heading("new", text="New")
        self.stats_tree.heading("diff", text="+/-")
        self.stats_tree.column("stat", width=90)
        self.stats_tree.column("current", width=60, anchor=tk.E)
        self.stats_tree.column("new", width=60, anchor=tk.E)
        self.stats_tree.column("diff", width=60, anchor=tk.E)
        self.stats_tree.pack(fill=tk.BOTH, expand=True)

        # Middle pane: Configuration (will be populated in next task)
        middle_frame = ttk.Frame(main_pane)
        main_pane.add(middle_frame, weight=1)

        # Priority sliders configuration
        priority_frame = ttk.LabelFrame(middle_frame, text="Stat Priority (-1 to 3)", padding=5)
        priority_frame.pack(fill=tk.X, pady=(0, 5))

        priority_stats = ["ATK%", "Flat ATK", "DEF%", "Flat DEF", "HP%", "Flat HP",
                          "CRate", "CDmg", "Ego", "Extra DMG%", "DoT%"]

        for i, stat_name in enumerate(priority_stats):
            row = i // 2
            col = i % 2
            frame = ttk.Frame(priority_frame)
            frame.grid(row=row, column=col, sticky=tk.W, padx=3, pady=1)

            ttk.Label(frame, text=f"{stat_name}:", width=10,
                      font=("Segoe UI", 9)).pack(side=tk.LEFT)
            var = tk.IntVar(value=0)
            self.priority_vars[stat_name] = var

            scale = ttk.Scale(frame, from_=-1, to=3, variable=var,
                              orient=tk.HORIZONTAL, length=70,
                              command=lambda v, s=stat_name: self.on_priority_change(s))
            scale.pack(side=tk.LEFT, padx=2)

            label = ttk.Label(frame, text="0", width=2, font=("Segoe UI", 9, "bold"))
            label.pack(side=tk.LEFT)
            self.priority_labels[stat_name] = label

        # Top % filter
        top_frame = ttk.Frame(priority_frame)
        top_frame.grid(row=(len(priority_stats) + 1) // 2, column=0,
                       columnspan=2, pady=(8, 0), sticky=tk.W)
        ttk.Label(top_frame, text="Top % Filter:",
                  font=("Segoe UI", 9)).pack(side=tk.LEFT)
        ttk.Scale(top_frame, from_=10, to=100, variable=self.top_percent_var,
                  orient=tk.HORIZONTAL, length=90).pack(side=tk.LEFT, padx=5)
        self.top_pct_label = ttk.Label(top_frame, text="50%",
                                        font=("Segoe UI", 9, "bold"))
        self.top_pct_label.pack(side=tk.LEFT)
        self.top_percent_var.trace_add("write",
                                        lambda *a: self.top_pct_label.config(
                                            text=f"{self.top_percent_var.get()}%"))

        # Main stat filters for slots IV, V, VI
        main_stat_frame = ttk.LabelFrame(middle_frame, text="Main Stats (Slots IV/V/VI)",
                                         padding=5)
        main_stat_frame.pack(fill=tk.X, pady=(0, 5))

        for slot_num, slot_name in [(4, "IV"), (5, "V"), (6, "VI")]:
            slot_frame = ttk.Frame(main_stat_frame)
            slot_frame.pack(fill=tk.X, pady=1)
            ttk.Label(slot_frame, text=f"{slot_name}:", width=3,
                      font=("Segoe UI", 9)).pack(side=tk.LEFT)

            self.main_stat_vars[slot_num] = {}
            possible_mains = SLOT_MAIN_STATS[slot_num]

            for main in possible_mains[:8]:
                var = tk.BooleanVar(value=False)
                self.main_stat_vars[slot_num][main] = var
                # Truncate display but keep full name in var
                short_name = main.replace("%", "").replace(" DMG", "").replace("Flat ", "F.")[:8]
                ttk.Checkbutton(slot_frame, text=short_name, variable=var,
                                width=8).pack(side=tk.LEFT)

        # Set configuration (4-piece and 2-piece multi-select)
        set_frame = ttk.LabelFrame(middle_frame, text="Set Configuration", padding=5)
        set_frame.pack(fill=tk.X, pady=(0, 5))

        # 4-piece sets with checkboxes
        four_pc_frame = ttk.Frame(set_frame)
        four_pc_frame.pack(fill=tk.X, pady=2)
        ttk.Label(four_pc_frame, text="4-Piece Sets:",
                  font=("Segoe UI", 9, "bold")).pack(anchor=tk.W)

        four_pc_inner = ttk.Frame(four_pc_frame)
        four_pc_inner.pack(fill=tk.X, padx=5)
        for i, sid in enumerate(FOUR_PIECE_SETS):
            name = SETS[sid]["name"]
            var = tk.BooleanVar(value=False)
            self.four_piece_vars[name] = var
            row = i // 4
            col = i % 4
            ttk.Checkbutton(four_pc_inner, text=name, variable=var).grid(
                row=row, column=col, sticky=tk.W, padx=5)

        # 2-piece sets with checkboxes
        two_pc_frame = ttk.Frame(set_frame)
        two_pc_frame.pack(fill=tk.X, pady=(5, 2))
        ttk.Label(two_pc_frame, text="2-Piece Sets:",
                  font=("Segoe UI", 9, "bold")).pack(anchor=tk.W)

        two_pc_inner = ttk.Frame(two_pc_frame)
        two_pc_inner.pack(fill=tk.X, padx=5)
        for i, sid in enumerate(TWO_PIECE_SETS):
            name = SETS[sid]["name"]
            var = tk.BooleanVar(value=False)
            self.two_piece_vars[name] = var
            row = i // 3
            col = i % 3
            ttk.Checkbutton(two_pc_inner, text=name, variable=var).grid(
                row=row, column=col, sticky=tk.W, padx=5)

        # Include equipped checkbox
        opt_frame = ttk.Frame(set_frame)
        opt_frame.pack(fill=tk.X, pady=3)
        ttk.Checkbutton(opt_frame, text="Include Equipped Items",
                        variable=self.include_equipped_var).pack(anchor=tk.W)

        # Exclude heroes configuration
        exclude_frame = ttk.LabelFrame(middle_frame, text="Exclude Combatant's Gear",
                                       padding=5)
        exclude_frame.pack(fill=tk.X, pady=(0, 5))

        self.exclude_heroes_frame = ttk.Frame(exclude_frame)
        self.exclude_heroes_frame.pack(fill=tk.X)

        # Right pane: Results (will be populated in later task)
        right_frame = ttk.LabelFrame(main_pane, text="Results", padding=5)
        main_pane.add(right_frame, weight=2)

        # Progress label
        self.progress_label = ttk.Label(right_frame, text="Ready to optimize",
                                        foreground=self.colors["fg_dim"])
        self.progress_label.pack(anchor=tk.W)

        # Results tree with sortable columns
        result_cols = ("rank", "score", "sets", "atk", "hp", "def", "crate", "cdmg", "extra")
        self.result_tree = ttk.Treeview(right_frame, columns=result_cols,
                                        show="headings", height=12)
        self.result_tree.heading("rank", text="#",
                                 command=lambda: self.sort_results("rank"))
        self.result_tree.heading("score", text="Score",
                                 command=lambda: self.sort_results("score"))
        self.result_tree.heading("sets", text="Sets",
                                 command=lambda: self.sort_results("sets"))
        self.result_tree.heading("atk", text="ATK",
                                 command=lambda: self.sort_results("atk"))
        self.result_tree.heading("hp", text="HP",
                                 command=lambda: self.sort_results("hp"))
        self.result_tree.heading("def", text="DEF",
                                 command=lambda: self.sort_results("def"))
        self.result_tree.heading("crate", text="CRate",
                                 command=lambda: self.sort_results("crate"))
        self.result_tree.heading("cdmg", text="CDmg",
                                 command=lambda: self.sort_results("cdmg"))
        self.result_tree.heading("extra", text="ExDMG",
                                 command=lambda: self.sort_results("extra"))

        self.result_tree.column("rank", width=28, anchor=tk.CENTER, stretch=False)
        self.result_tree.column("score", width=45, anchor=tk.CENTER, stretch=False)
        self.result_tree.column("sets", width=160, stretch=True)
        self.result_tree.column("atk", width=50, anchor=tk.CENTER, stretch=False)
        self.result_tree.column("hp", width=50, anchor=tk.CENTER, stretch=False)
        self.result_tree.column("def", width=50, anchor=tk.CENTER, stretch=False)
        self.result_tree.column("crate", width=50, anchor=tk.CENTER, stretch=False)
        self.result_tree.column("cdmg", width=55, anchor=tk.CENTER, stretch=False)
        self.result_tree.column("extra", width=50, anchor=tk.CENTER, stretch=False)

        result_scroll = ttk.Scrollbar(right_frame, orient=tk.VERTICAL,
                                      command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=result_scroll.set)
        self.result_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        result_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.result_tree.bind("<<TreeviewSelect>>", self.on_result_select)

        # Selected build detail tree
        detail_frame = ttk.LabelFrame(body, text="Selected Build", padding=5)
        detail_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 5))

        detail_cols = ("slot", "set", "main", "sub1", "sub2", "sub3", "sub4",
                       "gs", "potential", "owner")
        self.detail_tree = ttk.Treeview(detail_frame, columns=detail_cols,
                                        show="headings", height=6)
        for col, txt, w in [("slot","Slot",110), ("set","Set",130), ("main","Main",100),
                            ("sub1","Sub1",95), ("sub2","Sub2",95), ("sub3","Sub3",95),
                            ("sub4","Sub4",95), ("gs","GS",40), ("potential","Potential",75),
                            ("owner","Owner",80)]:
            self.detail_tree.heading(col, text=txt)
            anchor = tk.W if col in ["slot","set","main","owner"] else tk.CENTER
            self.detail_tree.column(col, width=w, anchor=anchor)
        self.detail_tree.pack(fill=tk.X)

    # === Public API (called by main GUI) ===

    def refresh_after_load(self):
        """Called after data loads to update UI components."""
        fragment_count = len(self.optimizer.fragments)
        self.status_label.config(
            text=f"Loaded {fragment_count} fragments",
            foreground=self.colors["green"]
        )
        self.refresh_hero_list()
        self.refresh_exclude_heroes()

    def refresh_hero_list(self):
        """Update hero combo dropdown with loaded heroes."""
        all_heroes = set(self.optimizer.characters.keys()) | \
                     set(self.optimizer.character_info.keys())
        self.hero_combo["values"] = sorted(all_heroes)

    def refresh_exclude_heroes(self):
        """Populate exclude hero checkboxes with colored names."""
        # Clear existing checkboxes
        for widget in self.exclude_heroes_frame.winfo_children():
            widget.destroy()
        self.exclude_hero_vars.clear()

        # Repopulate with colored names (6 columns)
        heroes = sorted(self.optimizer.characters.keys())
        for i, hero in enumerate(heroes):
            var = tk.BooleanVar(value=False)
            self.exclude_hero_vars[hero] = var
            row = i // 6
            col = i % 6

            # Get attribute color for this hero
            hero_data = get_character_by_name(hero)
            attribute = hero_data.get("attribute", "Unknown")
            fg_color = ATTRIBUTE_COLORS.get(attribute, self.colors["fg"])

            # Create checkbutton with colored text
            cb = tk.Checkbutton(
                self.exclude_heroes_frame, text=hero, variable=var,
                bg=self.colors["bg"], fg=fg_color,
                selectcolor=self.colors["bg_light"],
                activebackground=self.colors["bg"],
                activeforeground=fg_color,
                font=("Segoe UI", 9), anchor=tk.W, width=9
            )
            cb.grid(row=row, column=col, sticky=tk.W)

    # === Optimization Lifecycle ===

    def run_optimization(self):
        """Start optimization in background thread."""
        char_name = self.selected_character.get()
        if not char_name:
            messagebox.showwarning("Warning", "Please select a hero")
            return

        # Validate at least one main stat selected
        has_any_main_selected = False
        for slot_num in [4, 5, 6]:
            slot_vars = self.main_stat_vars.get(slot_num, {})
            if any(v.get() for v in slot_vars.values()):
                has_any_main_selected = True
                break

        if not has_any_main_selected:
            messagebox.showwarning("Warning",
                                   "Please select at least one main stat option for slots IV, V, or VI")
            return

        self.cancel_flag[0] = False

        # Build settings dictionary
        # Get selected 4-piece sets (multi-select)
        selected_4pc = []
        for name, var in self.four_piece_vars.items():
            if var.get():
                for sid, sinfo in SETS.items():
                    if sinfo["name"] == name:
                        selected_4pc.append(sid)
                        break

        settings = {
            "four_piece_sets": selected_4pc,
            "two_piece_sets": [],
            "main_stat_4": [n for n, v in self.main_stat_vars.get(4, {}).items() if v.get()],
            "main_stat_5": [n for n, v in self.main_stat_vars.get(5, {}).items() if v.get()],
            "main_stat_6": [n for n, v in self.main_stat_vars.get(6, {}).items() if v.get()],
            "top_percent": self.top_percent_var.get(),
            "include_equipped": self.include_equipped_var.get(),
            "excluded_heroes": [h for h, v in self.exclude_hero_vars.items() if v.get()],
            "max_results": 100,
        }

        # Get selected 2-piece sets from checkboxes
        for name, var in self.two_piece_vars.items():
            if var.get():
                for sid, sinfo in SETS.items():
                    if sinfo["name"] == name:
                        settings["two_piece_sets"].append(sid)
                        break

        # Update priorities in optimizer
        for name, var in self.priority_vars.items():
            self.optimizer.priorities[name] = var.get()
        self.optimizer.recalculate_scores()

        self.progress_label.config(text="Starting...")
        self.result_tree.delete(*self.result_tree.get_children())

        def optimize_thread():
            def progress_cb(checked, total, found):
                self.result_queue.put(("progress", checked, total, found))
            results = self.optimizer.optimize(char_name, settings, progress_cb, self.cancel_flag)
            self.result_queue.put(("done", results))

        threading.Thread(target=optimize_thread, daemon=True).start()

    def cancel_optimization(self):
        """Cancel running optimization."""
        self.cancel_flag[0] = True
        self.progress_label.config(text="Cancelling...")

    def check_queue(self):
        """Poll result queue for progress updates and completion."""
        try:
            while True:
                msg = self.result_queue.get_nowait()
                if msg[0] == "progress":
                    _, checked, total, found = msg
                    pct = (checked / total * 100) if total > 0 else 0
                    self.progress_label.config(
                        text=f"Checked {checked:,} ({pct:.1f}%) - Found {found}"
                    )
                elif msg[0] == "done":
                    results = msg[1]
                    self.optimization_results = results
                    self.display_results(results)
                    self.progress_label.config(
                        text=f"Done! {len(results)} builds found"
                    )
        except queue.Empty:
            pass

        # Continue polling every 100ms
        self.root.after(100, self.check_queue)

    # === Display Methods ===

    def display_results(self, results: list):
        """Display optimization results in tree."""
        self.result_tree.delete(*self.result_tree.get_children())
        for i, (gear, score, stats) in enumerate(results[:100]):
            set_counts = {}
            for p in gear:
                set_counts[p.set_name] = set_counts.get(p.set_name, 0) + 1
            sets_str = " + ".join(f"{c}x{n[:10]}" for n, c in set_counts.items() if c >= 2)

            atk = stats.get("ATK", 0)
            hp = stats.get("HP", 0)
            def_stat = stats.get("DEF", 0)
            crit_rate = stats.get("CRate", 0)
            crit_dmg = stats.get("CDmg", 0)
            extra_dmg = stats.get("Extra DMG%", 0)

            self.result_tree.insert("", tk.END, values=(
                i+1, f"{score:.0f}", sets_str,
                f"{atk:.0f}", f"{hp:.0f}", f"{def_stat:.0f}",
                f"{crit_rate:.1f}", f"{crit_dmg:.1f}", f"{extra_dmg:.1f}"
            ), iid=str(i))

    def sort_results(self, col: str):
        """Sort results by column."""
        if not self.optimization_results:
            return

        # Toggle sort direction if same column
        if col == self.result_sort_col:
            self.result_sort_reverse = not self.result_sort_reverse
        else:
            self.result_sort_col = col
            self.result_sort_reverse = False

        # Column key functions
        col_map = {
            "rank": lambda x: x[0],
            "score": lambda x: x[1],
            "sets": lambda x: "",
            "atk": lambda x: x[2].get("ATK", 0),
            "hp": lambda x: x[2].get("HP", 0),
            "def": lambda x: x[2].get("DEF", 0),
            "crate": lambda x: x[2].get("CRate", 0),
            "cdmg": lambda x: x[2].get("CDmg", 0),
            "extra": lambda x: x[2].get("Extra DMG%", 0),
        }

        key_func = col_map.get(col, lambda x: x[1])
        indexed_results = [(i, gear, score, stats)
                           for i, (gear, score, stats) in enumerate(self.optimization_results)]
        indexed_results.sort(key=lambda x: key_func((x[0], x[2], x[3])),
                             reverse=not self.result_sort_reverse)

        # Redisplay sorted results
        self.result_tree.delete(*self.result_tree.get_children())
        for rank, (orig_idx, gear, score, stats) in enumerate(indexed_results[:100]):
            set_counts = {}
            for p in gear:
                set_counts[p.set_name] = set_counts.get(p.set_name, 0) + 1
            sets_str = " + ".join(f"{c}x{n[:10]}" for n, c in set_counts.items() if c >= 2)

            self.result_tree.insert("", tk.END, values=(
                rank+1, f"{score:.0f}", sets_str,
                f"{stats.get('ATK', 0):.0f}", f"{stats.get('HP', 0):.0f}",
                f"{stats.get('DEF', 0):.0f}",
                f"{stats.get('CRate', 0):.1f}", f"{stats.get('CDmg', 0):.1f}",
                f"{stats.get('Extra DMG%', 0):.1f}"
            ), iid=str(orig_idx))

    def on_result_select(self, event):
        """Show selected build details and stats comparison."""
        sel = self.result_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx >= len(self.optimization_results):
            return

        gear, score, new_stats = self.optimization_results[idx]
        char = self.selected_character.get()
        current_gear = self.optimizer.characters.get(char, [])
        current_stats = self.optimizer.calculate_build_stats(current_gear, char)

        # Update stats comparison tree
        self.stats_tree.delete(*self.stats_tree.get_children())

        stat_order = [
            ("- Totals -", None),
            ("ATK", 0), ("DEF", 0), ("HP", 0), ("CRate", 1), ("CDmg", 1),
            ("- Substats -", None),
            ("ATK%", 1), ("DEF%", 1), ("HP%", 1), ("Ego", 0), ("Extra DMG%", 1), ("DoT%", 1),
        ]

        for stat_name, decimals in stat_order:
            if decimals is None:
                self.stats_tree.insert("", tk.END, values=(stat_name, "", "", ""),
                                       tags=("header",))
                continue

            curr = current_stats.get(stat_name, 0)
            new = new_stats.get(stat_name, 0)
            diff = new - curr

            if decimals == 0:
                curr_fmt = f"{curr:.0f}"
                new_fmt = f"{new:.0f}"
                diff_fmt = f"+{diff:.0f}" if diff > 0 else f"{diff:.0f}"
            else:
                curr_fmt = f"{curr:.1f}"
                new_fmt = f"{new:.1f}"
                diff_fmt = f"+{diff:.1f}" if diff > 0 else f"{diff:.1f}"

            if curr == 0 and new == 0:
                continue

            tag = "pos" if diff > 0.1 else "neg" if diff < -0.1 else ""
            self.stats_tree.insert("", tk.END,
                                   values=(stat_name, curr_fmt, new_fmt, diff_fmt),
                                   tags=(tag,))

        self.stats_tree.tag_configure("pos", foreground=self.colors["green"])
        self.stats_tree.tag_configure("neg", foreground=self.colors["red"])
        self.stats_tree.tag_configure("header", foreground=self.colors["fg_dim"])

        # Update detail tree with gear pieces
        self.detail_tree.delete(*self.detail_tree.get_children())
        for p in sorted(gear, key=lambda x: x.slot_num):
            subs = []
            for s in p.substats[:4]:
                subs.append(f"{s.name}:{s.format_value()}")
            while len(subs) < 4:
                subs.append("-")

            main_str = f"{p.main_stat.name}:{p.main_stat.format_value()}" if p.main_stat else "-"
            pot = f"{p.potential_low:.0f}-{p.potential_high:.0f}" if p.potential_low != p.potential_high else "-"
            owner = p.equipped_to or ""

            self.detail_tree.insert("", tk.END, values=(
                f"+{p.level} {p.slot_name}",
                p.set_name, main_str, *subs, f"{p.gear_score:.0f}", pot, owner
            ), tags=(f"r{p.rarity_num}",))

        self.detail_tree.tag_configure("r4", foreground=RARITY_COLORS[4])
        self.detail_tree.tag_configure("r3", foreground=RARITY_COLORS[3])

    def show_current_stats(self, char_name: str):
        """Display current gear stats for character."""
        gear = self.optimizer.characters.get(char_name, [])
        stats = self.optimizer.calculate_build_stats(gear, char_name)
        self.stats_tree.delete(*self.stats_tree.get_children())

        stat_order = [
            ("- Totals -", None),
            ("ATK", 0), ("DEF", 0), ("HP", 0), ("CRate", 1), ("CDmg", 1),
            ("- Substats -", None),
            ("ATK%", 1), ("DEF%", 1), ("HP%", 1), ("Ego", 0), ("Extra DMG%", 1), ("DoT%", 1),
        ]

        for stat_name, decimals in stat_order:
            if decimals is None:
                self.stats_tree.insert("", tk.END, values=(stat_name, "", "", ""),
                                       tags=("header",))
                continue

            val = stats.get(stat_name, 0)
            if val == 0:
                continue
            fmt = f"{val:.0f}" if decimals == 0 else f"{val:.1f}"
            self.stats_tree.insert("", tk.END, values=(stat_name, fmt, "-", "-"))

        self.stats_tree.tag_configure("header", foreground=self.colors["fg_dim"])

    # === UI Event Handlers ===

    def on_hero_select(self, event=None):
        """Handle hero selection from dropdown."""
        char = self.selected_character.get()
        if char in self.optimizer.characters:
            self.show_current_stats(char)

    def on_priority_change(self, stat_name: str):
        """Handle priority slider change."""
        for name, var in self.priority_vars.items():
            self.optimizer.priorities[name] = var.get()
            self.priority_labels[name].config(text=str(var.get()))
        self.optimizer.recalculate_scores()

    def reset_settings(self):
        """Reset all settings to defaults."""
        # Reset priority sliders
        for var in self.priority_vars.values():
            var.set(0)
        for lbl in self.priority_labels.values():
            lbl.config(text="0")

        # Reset set filters
        for var in self.four_piece_vars.values():
            var.set(False)
        for var in self.two_piece_vars.values():
            var.set(False)

        # Reset main stats
        for slot_vars in self.main_stat_vars.values():
            for var in slot_vars.values():
                var.set(False)

        # Reset options
        self.top_percent_var.set(50)
        self.include_equipped_var.set(True)

        # Reset exclude heroes
        for var in self.exclude_hero_vars.values():
            var.set(False)
