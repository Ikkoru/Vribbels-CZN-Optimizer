"""
UI module for Vribbels CZN Optimizer.

Provides modular tab architecture and shared UI components.
"""

from .base_tab import BaseTab
from .context import AppContext
from .tabs import MaterialsTab, SetupTab, CaptureTab, InventoryTab, OptimizerTab, HeroesTab, ScoringTab, ChecklistTab

__all__ = [
    'BaseTab',
    'AppContext',
    'MaterialsTab',
    'SetupTab',
    'CaptureTab',
    'InventoryTab',
    'OptimizerTab',
    'HeroesTab',
    'ScoringTab',
    'ChecklistTab',
]

__version__ = '1.0.0'
