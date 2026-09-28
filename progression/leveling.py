"""Experience and levels 1-10."""
from __future__ import annotations

from core import data
from core.events import events


def max_level() -> int:
    return int(data.levels()["max_level"])


def xp_to_next(level: int) -> int:
    table = data.levels()["xp_to_next"]
    if level >= max_level() or level >= len(table):
        return 0
    return int(table[level])


class Experience:
    """Tracks level/XP for the player and fires level-up events."""

    def __init__(self, owner, level: int = 1, xp: int = 0) -> None:
        self.owner = owner
        self.level = level
        self.xp = xp

    @property
    def needed(self) -> int:
        return xp_to_next(self.level)

    @property
    def fraction(self) -> float:
        n = self.needed
        return 0.0 if n <= 0 else min(1.0, self.xp / n)

    def gain(self, amount: int, reason: str = "") -> int:
        if amount <= 0 or self.level >= max_level():
            return 0
        self.xp += amount
        events.emit("xp_gained", amount=amount, reason=reason)
        while self.level < max_level() and self.xp >= self.needed:
            self.xp -= self.needed
            self.level += 1
            self.owner.on_level_up(self.level)
        if self.level >= max_level():
            self.xp = 0
        return amount
