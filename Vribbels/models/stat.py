"""
Stat-related data models for CZN.
Contains SubstatRoll and Stat classes for representing equipment statistics.
"""

from dataclasses import dataclass, field


@dataclass
class SubstatRoll:
    """Represents a single roll of a substat"""
    value: float
    stat_type: int
    is_min_roll: bool = False
    is_max_roll: bool = False


@dataclass
class Stat:
    name: str
    raw_name: str
    value: float
    is_percentage: bool
    is_main: bool = False
    roll_count: int = 1
    rolls: list = field(default_factory=list)
    base_value: float = 0.0
    upgrade_values: list = field(default_factory=list)

    def format_value(self) -> str:
        if self.is_percentage:
            return f"{self.value:.1f}%"
        return str(int(self.value) if self.value == int(self.value) else f"{self.value:.1f}")

    def get_roll_quality_pct(self) -> float:
        """How close this substat rolled to its maximum, as 0-100.

        100 means every roll landed at the top of its range. Independent
        of any scoring preset -- this is roll luck, NOT a share of the
        fragment's Gear Score, which weights each stat.
        """
        from game_data import STATS
        stat_info = STATS.get(self.raw_name, (self.name, self.name, self.is_percentage, 1.0, 0.5))
        max_roll = stat_info[3]
        if max_roll > 0 and self.roll_count > 0:
            return self.value / (max_roll * self.roll_count) * 100
        return 0.0
