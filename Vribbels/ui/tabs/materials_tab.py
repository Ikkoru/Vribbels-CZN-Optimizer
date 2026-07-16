"""Materials tab for displaying growth stones and items."""

import tkinter as tk
from tkinter import ttk
from pathlib import Path
from game_data import GROWTH_STONES, ATTRIBUTE_COLORS
from ..base_tab import BaseTab
from ..utils.image_utils import create_icon_with_quantity


class MaterialsTab(BaseTab):
    """
    Materials tab displays growth stones organized by attribute and quality.

    Updates automatically when data is loaded via refresh_materials().
    """

    def __init__(self, parent, context):
        super().__init__(parent, context)
        self.material_icons = {}  # res_id -> Label widget mapping
        self.setup_ui()
        # Render the stone icons immediately (quantity 0) so the tab
        # isn't a wall of text placeholders before the first capture --
        # the images are static assets, only the counts need data.
        self._render_icons({})

    def setup_ui(self):
        """Setup the Materials tab UI."""
        container = ttk.Frame(self.frame)
        container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Title
        title_label = ttk.Label(container, text="Growth Stones",
                                font=("Segoe UI", 14, "bold"))
        title_label.pack(anchor=tk.W, pady=(0, 15))

        # Growth stones frame
        stones_frame = ttk.Frame(container)
        stones_frame.pack(fill=tk.BOTH, expand=True)

        # Organize by attribute
        attributes = ["Passion", "Instinct", "Void", "Order", "Justice"]
        qualities = ["Premium", "Great", "Common"]

        for row, attribute in enumerate(attributes):
            # Attribute label with color
            attr_label = ttk.Label(
                stones_frame,
                text=attribute,
                font=("Segoe UI", 12, "bold"),
                foreground=ATTRIBUTE_COLORS.get(attribute, "#FFFFFF")
            )
            attr_label.grid(row=row, column=0, sticky=tk.W, padx=(0, 20), pady=10)

            # Create icon placeholder for each quality level
            for col, quality in enumerate(qualities, start=1):
                # Find the res_id for this attribute/quality combo
                res_id = None
                for rid, (attr, qual, icon_file) in GROWTH_STONES.items():
                    if attr == attribute and qual == quality:
                        res_id = rid
                        break

                if res_id:
                    # Placeholder label - will be updated when data loads
                    placeholder_label = tk.Label(
                        stones_frame,
                        text=f"{quality}\n0",
                        bg=self.colors["bg"],
                        fg=self.colors["fg"],
                        font=("Segoe UI", 11)
                    )
                    placeholder_label.grid(row=row, column=col, padx=5, pady=5)

                    # Store reference with res_id for later updates
                    self.material_icons[res_id] = placeholder_label

    def refresh_materials(self):
        """
        Update materials display with current inventory data.

        Called automatically after data loads.
        """
        if not self.optimizer.raw_data:
            return

        # Get items from inventory
        inventory = self.optimizer.raw_data.get("inventory", {})
        items = inventory.get("items", [])

        # Create dictionary of res_id -> amount
        item_quantities = {}
        for item in items:
            res_id = item.get("res_id")
            amount = item.get("amount", 0)
            if res_id:
                item_quantities[res_id] = amount

        self._render_icons(item_quantities)

    def _render_icons(self, item_quantities: dict):
        """(Re)draw every growth-stone label: icon + quantity overlay when
        the image asset exists, text fallback otherwise. `item_quantities`
        maps res_id -> owned amount; missing entries render as 0, which is
        also how the tab looks BEFORE any snapshot is loaded (the images
        are static assets -- only the counts need captured data).
        """
        # Get the path to images folder
        script_dir = Path(__file__).parent.parent.parent
        images_dir = script_dir / "images"

        # Update each growth stone icon
        for res_id, label_widget in self.material_icons.items():
            if res_id not in GROWTH_STONES:
                continue
            attribute, quality, icon_filename = GROWTH_STONES[res_id]
            quantity = item_quantities.get(res_id, 0)
            icon_path = images_dir / icon_filename

            if icon_path.exists():
                # Create icon with quantity overlay
                photo = create_icon_with_quantity(str(icon_path), quantity)
                if photo:
                    label_widget.config(image=photo, text="")
                    label_widget.image = photo  # Keep reference to prevent GC
                    continue
            # Icon file not found (or failed to build) -- text fallback.
            label_widget.config(text=f"{quality}\n{quantity}", image="")
