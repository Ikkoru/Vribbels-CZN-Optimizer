"""
Character and user info data models for CZN.
Contains CharacterInfo and UserInfo classes.
"""

from dataclasses import dataclass, field


@dataclass
class CharacterInfo:
    res_id: int
    name: str
    exp: int = 0
    level: int = 1
    ascend: int = 0
    max_level: int = 10
    limit_break: int = 0
    friendship_index: int = 1
    friendship_bonus: tuple[int, int, int] = (0, 0, 0)
    partner_id: int = 0
    partner_name: str = ""
    partner_res_id: int = 0
    partner_exp: int = 0
    partner_level: int = 1
    partner_ascend: int = 0
    partner_max_level: int = 10
    partner_limit_break: int = 0
    # Potential node data
    potential_node_ids: list[int] = field(default_factory=list)
    # {wire node number: level} for every node the capture carries.
    # The two below are the STAT nodes, kept as their own fields
    # because the scoring path reads them on every combo and a dict
    # lookup per combo is not what that loop is for.
    potential_nodes: dict[int, int] = field(default_factory=dict)
    potential_50_level: int = 0
    potential_60_level: int = 0


@dataclass
class UserInfo:
    nickname: str = ""
    level: int = 1
    login_total: int = 0
    login_continuous: int = 0
    login_highest_continuous: int = 0
