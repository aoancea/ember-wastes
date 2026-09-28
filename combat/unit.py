"""Units (anything that fights) and auras (timed buffs/debuffs)."""
from __future__ import annotations

import math
from typing import Any

from core.events import events

PHYSICAL = "physical"


class Aura:
    """A timed effect on a unit: damage/heal over time and/or stat modifiers."""

    def __init__(self, aura_id: str, name: str, duration: float, source: "Unit | None" = None, *,
                 debuff: bool = True, tick: float = 0.0, tick_damage: float = 0.0, tick_heal: float = 0.0,
                 school: str = PHYSICAL, mods: dict[str, float] | None = None, icon: str = "",
                 stacks: int = 1) -> None:
        self.id = aura_id
        self.name = name
        self.duration = duration
        self.remaining = duration
        self.source = source
        self.debuff = debuff
        self.tick = tick
        self.tick_timer = tick
        self.tick_damage = tick_damage
        self.tick_heal = tick_heal
        self.school = school
        self.mods = mods or {}
        self.icon = icon
        self.stacks = stacks

    def update(self, dt: float, unit: "Unit") -> bool:
        """Advance time; returns False when expired."""
        self.remaining -= dt
        if self.tick > 0:
            self.tick_timer -= dt
            while self.tick_timer <= 0 and not unit.dead:
                self.tick_timer += self.tick
                if self.tick_damage > 0:
                    unit.take_damage(self.tick_damage, self.source, self.school, kind="dot", ability=self.name)
                if self.tick_heal > 0:
                    unit.heal(self.tick_heal, self.source)
        return self.remaining > 0


class Unit:
    """Shared combat state for the player, enemies, companions and totems."""

    faction = "hostile"
    is_player = False

    def __init__(self, name: str, level: int) -> None:
        self.name = name
        self.level = level
        self.hp = 1.0
        self.max_hp = 1.0
        self.resource = 0.0
        self.max_resource = 0.0
        self.resource_type: str | None = None
        self.base_armor = 0.0
        self.dead = False
        self.auras: list[Aura] = []
        self.target: Unit | None = None
        self.combat_timer = 0.0
        self.radius = 0.6
        self.height = 2.0
        self.elite = False
        self.boss = False
        self.last_attacker: Unit | None = None

    # -------------------------------------------------------------- position
    @property
    def x(self) -> float:
        raise NotImplementedError

    @property
    def z(self) -> float:
        raise NotImplementedError

    @property
    def y(self) -> float:
        return 0.0

    def distance_to(self, other: "Unit") -> float:
        return math.hypot(self.x - other.x, self.z - other.z)

    def edge_distance(self, other: "Unit") -> float:
        """Distance between the two units' bounding circles."""
        return max(0.0, self.distance_to(other) - self.radius - other.radius)

    # -------------------------------------------------------------- state
    @property
    def in_combat(self) -> bool:
        return self.combat_timer > 0

    def enter_combat(self, seconds: float = 6.0) -> None:
        self.combat_timer = max(self.combat_timer, seconds)

    def mod(self, key: str, default: float = 0.0) -> float:
        """Sum of an aura modifier across all auras (multiplicative keys use mod_mult)."""
        total = default
        for a in self.auras:
            if key in a.mods:
                total += a.mods[key] * a.stacks
        return total

    def mod_max(self, key: str) -> float:
        best = 0.0
        for a in self.auras:
            v = a.mods.get(key)
            if v is not None and v > best:
                best = v
        return best

    @property
    def armor(self) -> float:
        mult = 1.0
        for a in self.auras:
            if "armor_mult" in a.mods:
                mult *= a.mods["armor_mult"]
        return max(0.0, (self.base_armor + self.mod("armor")) * mult)

    def is_stunned(self) -> bool:
        return any(a.mods.get("stun") for a in self.auras)

    def speed_factor(self) -> float:
        slow = self.mod_max("slow")
        return max(0.2, 1.0 - slow) * (1.0 + self.mod("speed"))

    def haste(self) -> float:
        return 1.0 + self.mod("haste")

    def damage_taken_mult(self) -> float:
        return max(0.1, 1.0 - self.mod("dr"))

    # -------------------------------------------------------------- auras
    def add_aura(self, aura: Aura) -> Aura:
        for existing in self.auras:
            if existing.id == aura.id and existing.source is aura.source:
                self.auras.remove(existing)
                break
        self.auras.append(aura)
        events.emit("aura_added", unit=self, aura=aura)
        return aura

    def remove_aura(self, aura_id: str) -> None:
        self.auras = [a for a in self.auras if a.id != aura_id]

    def has_aura(self, aura_id: str, source: "Unit | None" = None) -> bool:
        return any(a.id == aura_id and (source is None or a.source is source) for a in self.auras)

    def update_auras(self, dt: float) -> None:
        if not self.auras:
            return
        expired = []
        for a in list(self.auras):
            if not a.update(dt, self):
                expired.append(a)
            if self.dead:
                self.auras.clear()
                return
        if expired:
            self.auras = [a for a in self.auras if a not in expired]
            for a in expired:
                events.emit("aura_removed", unit=self, aura=a)

    def clear_auras(self) -> None:
        self.auras.clear()

    # -------------------------------------------------------------- damage
    def take_damage(self, amount: float, source: "Unit | None", school: str = PHYSICAL, crit: bool = False,
                    kind: str = "melee", ability: str | None = None) -> int:
        """Apply mitigated damage; returns the amount actually dealt."""
        if self.dead or amount <= 0:
            return 0
        dmg = amount
        if school == PHYSICAL and kind not in ("dot", "true"):
            from combat.combat import armor_mitigation
            atk_level = source.level if source else self.level
            dmg *= 1.0 - armor_mitigation(self.armor, atk_level)
        dmg *= self.damage_taken_mult()
        dealt = max(1, int(round(dmg)))
        self.hp -= dealt
        self.last_attacker = source
        self.enter_combat()
        if source is not None and not source.dead:
            source.enter_combat()
        self.on_damaged(dealt, source, school, crit, kind)
        events.emit("damage", target=self, source=source, amount=dealt, crit=crit, school=school, kind=kind,
                    ability=ability)
        if self.hp <= 0:
            self.hp = 0
            self.die(source)
        return dealt

    def heal(self, amount: float, source: "Unit | None" = None, crit: bool = False, silent: bool = False) -> int:
        if self.dead or amount <= 0:
            return 0
        before = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        done = int(round(self.hp - before))
        if not silent and done > 0:
            events.emit("heal", target=self, source=source, amount=done, crit=crit)
        return done

    def on_damaged(self, amount: int, source: "Unit | None", school: str, crit: bool, kind: str) -> None:
        pass

    def die(self, killer: "Unit | None") -> None:
        self.dead = True
        self.auras.clear()
        events.emit("unit_died", unit=self, killer=killer)

    def notify_miss(self, source: "Unit", result: str) -> None:
        events.emit("miss", target=self, source=source, result=result)

    def is_hostile_to(self, other: "Unit") -> bool:
        if other is None:
            return False
        a, b = self.faction, other.faction
        if "neutral" in (a, b):
            return False
        return (a == "hostile") != (b == "hostile")

    def debug(self) -> dict[str, Any]:
        return {"name": self.name, "lvl": self.level, "hp": f"{self.hp:.0f}/{self.max_hp:.0f}"}
