"""Temporary allies: the hunter's hyena and the shaman's Ember Totem."""
from __future__ import annotations

import math
import random
from typing import Any

from combat.combat import roll_attack
from combat.unit import Unit
from core import data
from core.events import events
from core.meshgen import MeshBuilder
from core.rig import blob_shadow, copy_part
from core.util import damp_angle, set_yaw, yaw_to
from enemies.models import build_enemy_rig
from player.controller import CharacterMotor


class Hyena(Unit):
    """Fights the owner's target; enemies may turn on it."""

    faction = "player"

    def __init__(self, game, owner, d: dict[str, Any]) -> None:
        super().__init__("Spirit Hyena", owner.level)
        self.game = game
        self.owner = owner
        t = data.enemies()["types"]["hyena"]
        self.rig = build_enemy_rig(t)
        self.rig.root.reparentTo(game.world.actors)
        self.rig.root.setShaderInput("u_rim", 0.5)
        self.radius = self.rig.radius
        self.height = self.rig.height
        self.shadow = blob_shadow(game.world.fx, 0.8)
        a = math.radians(owner.yaw + 120)
        self.motor = CharacterMotor(game.world, owner.x + math.sin(a) * 2, owner.z + math.cos(a) * 2, radius=0.5)
        self.max_hp = float(int(t["hp"] * (1 + 0.4 * (owner.level - 1))))
        self.hp = self.max_hp
        self.base_armor = t["armor"] * (1 + 0.3 * (owner.level - 1))
        self.dmin, self.dmax = float(d["min"]), float(d["max"])
        self.life = float(d["duration"])
        self.yaw = owner.yaw
        self.attack_timer = 0.5
        self.targetable = True
        self.taunted = False
        game.fx.dust_puff(self.x, self.y, self.z, 12)

    @property
    def x(self) -> float:
        return self.motor.x

    @property
    def z(self) -> float:
        return self.motor.z

    @property
    def y(self) -> float:
        return self.motor.y

    def update(self, dt: float) -> bool:
        self.life -= dt
        if self.dead or self.life <= 0 or self.owner.dead:
            return False
        self.update_auras(dt)
        self.attack_timer -= dt
        tgt = self.owner.target if (self.owner.target is not None and self.owner.is_hostile_to(self.owner.target)
                                    and not self.owner.target.dead) else None
        if tgt is None and self.owner.last_attacker is not None and not self.owner.last_attacker.dead \
                and self.owner.in_combat:
            tgt = self.owner.last_attacker
        speed = 0.0
        if tgt is not None and self.distance_to(self.owner) < 45:
            dx, dz = tgt.x - self.x, tgt.z - self.z
            d = math.hypot(dx, dz)
            reach = self.radius + tgt.radius + 0.9
            if d > reach:
                self.yaw = damp_angle(self.yaw, yaw_to(dx, dz), 10, dt)
                speed = self.motor.move(dt, dx, dz, 8.5)
            else:
                self.yaw = damp_angle(self.yaw, yaw_to(dx, dz), 12, dt)
                if self.attack_timer <= 0:
                    self.attack_timer = 1.6
                    self.rig.play("attack", 0.4)
                    res = roll_attack(self.level, tgt.level, 0.08)
                    if res in ("miss", "dodge"):
                        tgt.notify_miss(self, res)
                    else:
                        dmg = random.uniform(self.dmin, self.dmax) * (1.5 if res == "crit" else 1.0)
                        tgt.take_damage(dmg, self, crit=res == "crit")
                        if hasattr(tgt, "add_threat"):
                            tgt.add_threat(self, dmg * 4.0 + (120.0 if not self.taunted else 0.0))
                            self.taunted = True
        else:
            dx, dz = self.owner.x - self.x, self.owner.z - self.z
            d = math.hypot(dx, dz)
            if d > 40:
                self.motor.teleport(self.owner.x + 1.5, self.owner.z - 1.5)
            elif d > 3.0:
                self.yaw = damp_angle(self.yaw, yaw_to(dx, dz), 8, dt)
                speed = self.motor.move(dt, dx, dz, min(9.0, 3 + d))
        m = self.motor
        self.rig.root.setPos(m.x, m.y, m.z)
        set_yaw(self.rig.root, self.yaw)
        self.rig.update(dt, speed, True, m.swimming)
        self.shadow.setPos(m.x, m.y + 0.06, m.z)
        return True

    def destroy(self) -> None:
        self.game.fx.dust_puff(self.x, self.y, self.z, 10)
        self.rig.destroy()
        self.shadow.removeNode()


def _totem_mesh() -> MeshBuilder:
    mb = MeshBuilder()
    wood = (0.45, 0.28, 0.16, 1)
    mb.cylinder((0, 0, 0), 0.22, 1.6, wood, radius_top=0.16, segments=6)
    mb.box((0, 1.1, 0.12), (0.4, 0.45, 0.28), (0.7, 0.2, 0.12, 1))
    mb.box((0, 1.15, 0.27), (0.28, 0.08, 0.04), (0.95, 0.9, 0.8, 1))
    for sx in (-1, 1):
        mb.beam((0, 1.5, 0), (sx * 0.45, 1.75, 0), 0.04, wood, segments=4)
    mb.cylinder((0, 1.6, 0), 0.25, 0.12, (0.3, 0.3, 0.32, 1), radius_top=0.32, segments=6)
    return mb


def _flame_mesh() -> MeshBuilder:
    mb = MeshBuilder()
    mb.cone((0, 0, 0), 0.22, 0.55, (1.0, 0.5, 0.1, 1), segments=5)
    mb.cone((0.05, 0, 0.03), 0.12, 0.4, (1.0, 0.85, 0.3, 1), segments=4)
    return mb


class EmberTotem(Unit):
    faction = "player"

    def __init__(self, game, owner, d: dict[str, Any]) -> None:
        super().__init__("Ember Totem", owner.level)
        self.game = game
        self.owner = owner
        self.targetable = False
        yaw = math.radians(owner.yaw)
        self._x = owner.x + math.sin(yaw) * 1.5
        self._z = owner.z + math.cos(yaw) * 1.5
        self._y = game.world.ground(self._x, self._z)
        self.root = game.world.actors.attachNewNode("totem")
        copy_part(("ember_totem",), _totem_mesh, self.root)
        flame = copy_part(("ember_flame",), _flame_mesh, self.root)
        flame.setPos(0, 1.72, 0)
        flame.setShaderInput("u_emissive", 1.3)
        flame.setShaderInput("u_flame", 1.0)
        self.root.setPos(self._x, self._y, self._z)
        self.height = 1.8
        self.radius = 0.3
        self.max_hp = self.hp = 50.0
        self.life = float(d["duration"])
        self.d = d
        self.timer = 0.5
        from world.sky import PointLight
        self.light = game.world.env.add_light(PointLight((self._x, self._y + 2.0, self._z), 9.0, (1.0, 0.5, 0.2), 1.2, 0.2))
        game.fx.dust_puff(self._x, self._y, self._z, 8)

    @property
    def x(self) -> float:
        return self._x

    @property
    def z(self) -> float:
        return self._z

    @property
    def y(self) -> float:
        return self._y

    def update(self, dt: float) -> bool:
        self.life -= dt
        if self.life <= 0 or self.owner.dead:
            return False
        self.timer -= dt
        if self.timer <= 0:
            self.timer = 2.0
            best, bd = None, 20.0
            for e in self.game.enemies.living_near(self._x, self._z, 20.0):
                if e.passive and e.type_id != "training_dummy":
                    continue
                if e.state == "combat" or e is self.owner.target:
                    dd = math.hypot(e.x - self._x, e.z - self._z)
                    if dd < bd:
                        best, bd = e, dd
            if best is not None:
                d = self.d
                dmg = random.uniform(d["min"], d["max"]) + self.owner.spell_power() * d.get("coef", 0.25)
                tgt = best
                self.game.fx.projectile(self, tgt, "ember",
                                        lambda: (not tgt.dead) and tgt.take_damage(dmg, self.owner, school="fire", kind="spell",
                                                                                   ability="Ember Totem"))
        return True

    def destroy(self) -> None:
        self.game.world.env.remove_light(self.light)
        self.game.fx.dust_puff(self._x, self._y, self._z, 6)
        self.root.removeNode()


class CompanionManager:
    def __init__(self, game) -> None:
        self.game = game
        self.units: list[Unit] = []

    def summon_hyena(self, owner, d: dict[str, Any]) -> None:
        for u in list(self.units):
            if isinstance(u, Hyena):
                self._remove(u)
        self.units.append(Hyena(self.game, owner, d))
        events.emit("message", text="A spirit hyena answers your call!", color=(0.9, 0.8, 0.4))

    def plant_totem(self, owner, d: dict[str, Any]) -> None:
        for u in list(self.units):
            if isinstance(u, EmberTotem):
                self._remove(u)
        self.units.append(EmberTotem(self.game, owner, d))

    def _remove(self, u: Unit) -> None:
        if u in self.units:
            self.units.remove(u)
        u.destroy()

    def update(self, dt: float) -> None:
        for u in list(self.units):
            if not u.update(dt):
                self._remove(u)

    def clear(self) -> None:
        for u in list(self.units):
            self._remove(u)
