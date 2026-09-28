"""Character attributes and the derived combat numbers they produce."""
from __future__ import annotations

from typing import Any

from core import data

PRIMARY_STATS = ("strength", "agility", "intellect", "stamina")
STAT_LABELS = {
    "strength": "Strength", "agility": "Agility", "intellect": "Intellect", "stamina": "Stamina",
    "armor": "Armor", "spell_power": "Spell Power", "attack_power": "Attack Power",
}


class CharacterStats:
    """Base attributes (grow with level) + gear bonuses + aura modifiers -> derived values."""

    def __init__(self, cls_id: str) -> None:
        self.cls_id = cls_id
        self.cls: dict[str, Any] = data.classes()[cls_id]
        self.base: dict[str, float] = {k: float(v) for k, v in self.cls["base_stats"].items()}
        self.base_hp = float(self.cls["base_hp"])
        self.base_resource = float(self.cls["base_resource"])
        self.gear: dict[str, float] = {}
        self.aura_source = None  # a Unit whose auras may modify stats

    # ---------------------------------------------------------------- totals
    def total(self, stat: str) -> float:
        v = self.base.get(stat, 0.0) + self.gear.get(stat, 0.0)
        if self.aura_source is not None:
            v += self.aura_source.mod(stat)
        return v

    def set_gear(self, bonuses: dict[str, float]) -> None:
        self.gear = dict(bonuses)

    # ---------------------------------------------------------------- derived
    @property
    def strength(self) -> float:
        return self.total("strength")

    @property
    def agility(self) -> float:
        return self.total("agility")

    @property
    def intellect(self) -> float:
        return self.total("intellect")

    @property
    def stamina(self) -> float:
        return self.total("stamina")

    def max_hp(self) -> float:
        return self.base_hp + self.stamina * float(self.cls["hp_per_stamina"])

    def max_resource(self) -> float:
        if self.cls["resource"] == "rage":
            return 100.0
        return self.base_resource + self.intellect * float(self.cls["resource_per_int"])

    def attack_power(self) -> float:
        c = self.cls
        return (self.strength * c["ap_per_strength"] + self.agility * c["ap_per_agility"]
                + self.gear.get("attack_power", 0.0))

    def ranged_attack_power(self) -> float:
        c = self.cls
        return self.agility * c["ranged_ap_per_agility"] + self.strength * 0.5 + self.gear.get("attack_power", 0.0)

    def spell_power(self) -> float:
        return self.intellect * float(self.cls["spell_power_per_intellect"]) + self.gear.get("spell_power", 0.0)

    def crit_chance(self) -> float:
        return 0.05 + self.agility * float(self.cls["crit_per_agility"]) / 100.0

    def spell_crit_chance(self) -> float:
        return 0.05 + self.intellect * float(self.cls["spell_crit_per_intellect"]) / 100.0

    def armor(self) -> float:
        return self.gear.get("armor", 0.0) + self.agility * 2.0

    def level_up(self, growth: dict[str, float]) -> dict[str, float]:
        """Apply one level of growth; returns what changed (for the level-up message)."""
        gained: dict[str, float] = {}
        for stat in PRIMARY_STATS:
            g = float(growth.get(stat, 0))
            if g:
                self.base[stat] = self.base.get(stat, 0.0) + g
                gained[stat] = g
        self.base_hp += float(growth.get("hp", 0))
        self.base_resource += float(growth.get("resource", 0))
        return gained

    def to_dict(self) -> dict[str, Any]:
        return {"base": self.base, "base_hp": self.base_hp, "base_resource": self.base_resource}

    def load_dict(self, d: dict[str, Any]) -> None:
        self.base = {k: float(v) for k, v in d.get("base", self.base).items()}
        self.base_hp = float(d.get("base_hp", self.base_hp))
        self.base_resource = float(d.get("base_resource", self.base_resource))
