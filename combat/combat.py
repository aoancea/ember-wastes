"""Combat formulas: hit tables, armor, level difference, XP and difficulty colours."""
from __future__ import annotations

import random

from core import data

MISS_BASE = 0.05
DODGE_BASE = 0.04


def armor_mitigation(armor: float, attacker_level: int) -> float:
    """Fraction of physical damage removed by armor (capped at 75%)."""
    if armor <= 0:
        return 0.0
    return min(0.75, armor / (armor + 400.0 + 85.0 * attacker_level))


def roll_attack(attacker_level: int, defender_level: int, crit_chance: float, can_dodge: bool = True,
                rng: random.Random | None = None) -> str:
    """Single-roll hit table: 'miss' | 'dodge' | 'crit' | 'hit'."""
    r = (rng or random).random()
    diff = defender_level - attacker_level
    miss = max(0.0, MISS_BASE + 0.02 * diff)
    dodge = max(0.0, DODGE_BASE + 0.01 * diff) if can_dodge else 0.0
    crit = max(0.0, crit_chance - 0.01 * max(diff, 0))
    if r < miss:
        return "miss"
    r -= miss
    if r < dodge:
        return "dodge"
    r -= dodge
    if r < crit:
        return "crit"
    return "hit"


def roll_spell(attacker_level: int, defender_level: int, crit_chance: float) -> str:
    r = random.random()
    diff = defender_level - attacker_level
    miss = max(0.0, 0.03 + 0.02 * diff)
    if r < miss:
        return "miss"
    if r < miss + crit_chance:
        return "crit"
    return "hit"


def difficulty(player_level: int, mob_level: int) -> str:
    d = mob_level - player_level
    if d >= 5:
        return "red"
    if d >= 3:
        return "orange"
    if d >= -2:
        return "yellow"
    if d >= -4:
        return "green"
    return "grey"


def difficulty_color(player_level: int, mob_level: int) -> tuple[float, float, float]:
    cols = data.levels()["difficulty_colors"]
    return tuple(cols[difficulty(player_level, mob_level)])  # type: ignore[return-value]


def kill_xp(player_level: int, mob_level: int, elite: bool = False) -> int:
    """Experience for killing a mob, zero for grey mobs."""
    cfg = data.levels()["kill_xp"]
    if difficulty(player_level, mob_level) == "grey":
        return 0
    base = cfg["base"] + cfg["per_level"] * mob_level
    d = mob_level - player_level
    if d > 0:
        mult = 1.0 + 0.08 * min(d, 4)
    else:
        mult = max(0.2, 1.0 + d * 0.16)
    xp = base * mult * (2.0 if elite else 1.0)
    return int(round(xp))


def aggro_radius(base: float, player_level: int, mob_level: int) -> float:
    """Higher level mobs notice you from further away; grey ones barely care."""
    if base <= 0:
        return 0.0
    d = mob_level - player_level
    return max(3.5, min(base + d * 1.2, base * 1.9))
