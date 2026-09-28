"""Hostile creatures: stats scaled by level, AI state machine, abilities, death, loot and respawn."""
from __future__ import annotations

import math
import random
from typing import Any

from combat.combat import aggro_radius, roll_attack
from combat.unit import Aura, Unit
from core import data
from core.events import events
from core.rig import blob_shadow
from core.util import angle_diff, damp_angle, set_yaw, yaw_to
from player.controller import CharacterMotor
from settings import CORPSE_TIME
from enemies.models import build_enemy_rig

LEASH_DISTANCE = 48.0
SOCIAL_RADIUS = 11.0


def scaled_stats(t: dict[str, Any], level: int) -> dict[str, float]:
    sc = data.enemies()["scaling"]
    lv = level - 1
    hp = t["hp"] * (1 + sc["hp_growth"] * lv)
    dmin, dmax = t["damage"]
    dm = 1 + sc["dmg_growth"] * lv
    armor = t.get("armor", 0) * (1 + sc["armor_growth"] * lv)
    if t.get("elite"):
        hp *= sc["elite_hp"]
        dm *= sc["elite_dmg"]
    return {"hp": hp, "dmin": dmin * dm, "dmax": dmax * dm, "armor": armor}


class Enemy(Unit):
    """A hostile (or passive) creature controlled by a simple state machine."""

    faction = "hostile"

    def __init__(self, manager, type_id: str, level: int, x: float, z: float, spawn: dict | None = None,
                 yaw: float | None = None) -> None:
        self.t: dict[str, Any] = data.enemies()["types"][type_id]
        super().__init__(self.t["name"], level)
        self.manager = manager
        self.game = manager.game
        self.world = manager.game.world
        self.type_id = type_id
        self.spawn = spawn or {}
        self.elite = bool(self.t.get("elite"))
        self.boss = bool(self.t.get("boss"))
        self.passive = bool(self.t.get("passive"))
        self.flying = bool(self.t.get("flying"))
        self.ranged = bool(self.t.get("ranged"))
        self.caster = bool(self.t.get("caster"))
        self.rig = build_enemy_rig(self.t)
        self.rig.root.reparentTo(self.world.actors)
        self.radius = self.rig.radius
        self.height = self.rig.height
        self.shadow = blob_shadow(self.world.fx, self.radius * 1.15)
        self.motor = CharacterMotor(self.world, x, z, radius=max(0.35, self.radius * 0.75))
        self.home = (x, z)
        self.home_yaw = yaw if yaw is not None else random.uniform(0, 360)
        self.yaw = self.home_yaw
        self.state = "idle"
        self.threat: dict[Unit, float] = {}
        self.attack_timer = random.uniform(0.3, 1.0)
        self.cds: dict[str, float] = {}
        self.flags: set[str] = set()
        self.wander_timer = random.uniform(2, 8)
        self.wander_target: tuple[float, float] | None = None
        self.aggro_timer = random.uniform(0, 0.3)
        self.corpse_timer = 0.0
        self.respawn_timer = 0.0
        self.loot: dict[str, Any] | None = None
        self.charging = False
        self.casting: dict[str, Any] | None = None
        self.pending: list[tuple[float, Any]] = []   # delayed actions (telegraphs, wind-ups)
        self.fly_height = 0.0
        self.circle_angle = random.uniform(0, math.tau)
        self.visible = True
        self.speed = float(self.t.get("speed", 6.0))
        self.next_hit_mult = 1.0
        self.tagged_by_player = False
        self.quest_tag: str | None = None
        self.last_exchange = 0.0
        self.clock = 0.0
        self.anim_accum = 0.0
        self.lod_skip = 0
        self._apply_level_stats()
        self.hp = self.max_hp
        self.sync(0.0)

    # ----------------------------------------------------------------- basics
    @property
    def x(self) -> float:
        return self.motor.x

    @property
    def z(self) -> float:
        return self.motor.z

    @property
    def y(self) -> float:
        return self.motor.y + self.fly_height

    def _apply_level_stats(self) -> None:
        s = scaled_stats(self.t, self.level)
        self.max_hp = float(int(s["hp"]))
        self.dmin, self.dmax = s["dmin"], s["dmax"]
        self.base_armor = s["armor"]
        self.attack_speed = float(self.t.get("attack_speed", 2.0))

    def set_level(self, level: int) -> None:
        self.level = level
        self._apply_level_stats()
        self.hp = self.max_hp

    @property
    def lootable(self) -> bool:
        return self.dead and self.loot is not None and (bool(self.loot.get("items")) or self.loot.get("gold", 0) > 0)

    def reach(self, other: Unit) -> float:
        if self.ranged:
            return float(self.t.get("attack_range", 20.0))
        return self.radius + other.radius + 1.1

    # ----------------------------------------------------------------- engagement
    def engage(self, target: Unit, social: bool = True) -> None:
        if self.dead or self.passive or self.state == "evade":
            return
        if target is None or target.dead:
            return
        was_idle = self.state != "combat"
        if was_idle:
            self.last_exchange = self.clock
        self.threat[target] = self.threat.get(target, 0.0) + 1.0
        self.state = "combat"
        self.target = target
        self.enter_combat(9999)
        if was_idle:
            self.fly_height = min(self.fly_height, 6.0) if self.flying else 0.0
            events.emit("enemy_aggro", enemy=self, target=target)
            if social:
                for other in self.manager.enemies_near(self.x, self.z, SOCIAL_RADIUS):
                    if other is not self and other.state == "idle" and not other.dead and not other.passive and \
                            (other.type_id == self.type_id or (other.t.get("social") and self.t.get("social"))):
                        other.engage(target, social=False)

    def add_threat(self, unit: Unit, amount: float) -> None:
        if self.dead or self.passive:
            return
        if self.state != "combat":
            self.engage(unit)
        self.threat[unit] = self.threat.get(unit, 0.0) + amount

    def pick_target(self) -> Unit | None:
        alive = {u: v for u, v in self.threat.items() if not u.dead and getattr(u, "targetable", True)}
        self.threat = alive
        if not alive:
            return None
        return max(alive.items(), key=lambda kv: kv[1])[0]

    def evade(self) -> None:
        self.state = "evade"
        self.target = None
        self.threat.clear()
        self.casting = None
        self.pending.clear()
        self.charging = False
        self.combat_timer = 0.0
        self.clear_auras()
        self.flags.discard("frenzy")
        self.flags.discard("shell")
        events.emit("enemy_evade", enemy=self)

    # ----------------------------------------------------------------- damage
    def take_damage(self, amount: float, source: Unit | None, school: str = "physical", crit: bool = False,
                    kind: str = "melee", ability: str | None = None) -> int:
        if self.state == "evade" or self.state == "respawning":
            if source is not None and getattr(source, "is_player", False):
                events.emit("miss", target=self, source=source, result="evade")
            return 0
        if self.t.get("unkillable") and amount >= self.hp:
            amount = max(0, self.hp - 1)
        dealt = super().take_damage(amount, source, school, crit, kind, ability)
        if dealt:
            self.last_exchange = self.clock
        if dealt and not self.dead:
            self.rig.flash()
            if self.rig.action is None and not self.boss:
                self.rig.play("hit", 0.25)
        if source is not None and not self.dead:
            owner = getattr(source, "owner", None)
            if getattr(source, "is_player", False) or owner is not None:
                self.tagged_by_player = True
            if not self.passive:
                self.add_threat(source, dealt * (2.0 if getattr(source, "is_player", False) else 1.0))
        return dealt

    def die(self, killer: Unit | None) -> None:
        self.state = "dead"
        self.casting = None
        self.pending.clear()
        self.corpse_timer = CORPSE_TIME
        self.rig.die()
        self.shadow.hide()
        if self.tagged_by_player or (killer is not None and (getattr(killer, "is_player", False) or getattr(killer, "owner", None))):
            self.loot = self.manager.game.loot.roll(self) if self.manager.game.loot else None
        super().die(killer)

    def respawn(self) -> None:
        self.dead = False
        self.state = "idle"
        self.hp = self.max_hp
        self.threat.clear()
        self.target = None
        self.loot = None
        self.tagged_by_player = False
        self.flags.clear()
        self.cds.clear()
        self.auras.clear()
        self.motor.teleport(*self.home)
        self.yaw = self.home_yaw
        self.rig.revive()
        self.rig.root.show()
        self.shadow.show()
        self.visible = True
        events.emit("enemy_respawned", enemy=self)

    def hide_corpse(self) -> None:
        if self.spawn.get("temporary"):
            self.state = "respawning"
            self.respawn_timer = 1e9
            self.rig.root.hide()
            self.shadow.hide()
            self.loot = None
            return
        self.state = "respawning"
        self.respawn_timer = float(self.t.get("respawn", 45)) * self.spawn.get("respawn_mult", 1.0)
        self.rig.root.hide()
        self.shadow.hide()
        self.loot = None

    # ----------------------------------------------------------------- update
    def update(self, dt: float, lod: int = 0) -> None:
        self.clock += dt
        self.lod_skip = lod
        if self.state == "respawning":
            self.respawn_timer -= dt
            if self.respawn_timer <= 0:
                self.respawn()
            return
        if self.dead:
            self.corpse_timer -= dt
            if self.corpse_timer <= 0:
                self.hide_corpse()
                return
            if self.flying and self.fly_height > 0:
                self.fly_height = max(0.0, self.fly_height - dt * 9.0)
            self.sync(dt, 0.0)
            return
        self.update_auras(dt)
        if self.dead:
            return
        for k in list(self.cds):
            self.cds[k] -= dt
        self.attack_timer -= dt * self.haste()
        self._run_pending(dt)
        if self.dead:
            return
        speed_moved = 0.0
        if self.state == "idle":
            speed_moved = self._idle(dt)
        elif self.state == "combat":
            speed_moved = self._combat(dt)
        elif self.state == "evade":
            speed_moved = self._evade(dt)
        if self.passive and self.hp < self.max_hp and not self.in_combat:
            self.hp = min(self.max_hp, self.hp + self.max_hp * 0.2 * dt)
        self.combat_timer = max(0.0, self.combat_timer - dt) if self.state != "combat" else self.combat_timer
        self.sync(dt, speed_moved)

    def _run_pending(self, dt: float) -> None:
        if not self.pending:
            return
        keep = []
        for t, fn in self.pending:
            t -= dt
            if t <= 0:
                fn()
            else:
                keep.append((t, fn))
        self.pending = keep if not self.dead else []

    # ------------------------------------------------------------------ idle
    def _idle(self, dt: float) -> float:
        game = self.game
        player = game.player
        # aggro check
        self.aggro_timer -= dt
        if self.aggro_timer <= 0:
            self.aggro_timer = 0.25
            if player is not None and not player.dead and not self.passive and player.targetable:
                r = aggro_radius(float(self.t.get("aggro_radius", 8)), player.level, self.level)
                if self.flying:
                    r *= 1.1
                dx, dz = player.x - self.x, player.z - self.z
                if dx * dx + dz * dz < r * r and abs(player.y - self.motor.y) < 8.0:
                    self.engage(player)
                    return 0.0
        if self.passive and self.t.get("speed", 0) == 0:
            return 0.0
        if self.flying:
            return self._idle_fly(dt)
        # wander
        self.wander_timer -= dt
        if self.wander_target is None and self.wander_timer <= 0:
            rng = random.random
            wr = float(self.spawn.get("wander", 7.0))
            a = rng() * math.tau
            d = rng() * wr
            self.wander_target = (self.home[0] + math.cos(a) * d, self.home[1] + math.sin(a) * d)
            self.wander_timer = random.uniform(4, 11)
        if self.wander_target is not None:
            tx, tz = self.wander_target
            dx, dz = tx - self.x, tz - self.z
            dist = math.hypot(dx, dz)
            if dist < 0.6:
                self.wander_target = None
                return 0.0
            self.yaw = damp_angle(self.yaw, yaw_to(dx, dz), 6.0, dt)
            sp = self.motor.move(dt, dx, dz, 1.7)
            if self.motor.blocked and sp < 0.3:
                self.wander_target = None
            return sp
        return 0.0

    def _idle_fly(self, dt: float) -> float:
        self.circle_angle += dt * 0.35
        r = 10.0
        tx = self.home[0] + math.cos(self.circle_angle) * r
        tz = self.home[1] + math.sin(self.circle_angle) * r
        dx, dz = tx - self.x, tz - self.z
        self.yaw = damp_angle(self.yaw, yaw_to(dx, dz), 3.0, dt)
        target_h = 11.0 + math.sin(self.circle_angle * 1.7) * 2.0
        self.fly_height += (target_h - self.fly_height) * min(dt * 0.8, 1.0)
        if hasattr(self.rig, "hover"):
            self.rig.hover = 1.0
        self.motor.x += dx * min(dt * 0.8, 1.0)
        self.motor.z += dz * min(dt * 0.8, 1.0)
        self.motor.y = self.world.ground(self.motor.x, self.motor.z)
        return 0.0

    # ------------------------------------------------------------------ combat
    def _combat(self, dt: float) -> float:
        tgt = self.pick_target()
        if tgt is None or (self.clock - self.last_exchange > 12.0 and not self.boss):
            self.evade()
            return 0.0
        self.target = tgt
        hx, hz = self.home
        if not self.t.get("no_leash") and math.hypot(self.x - hx, self.z - hz) > LEASH_DISTANCE:
            self.evade()
            return 0.0
        if self.flying:
            self.fly_height += (1.4 - self.fly_height) * min(dt * 2.5, 1.0)
            if hasattr(self.rig, "hover"):
                self.rig.hover = 0.0
        self._abilities_tick(tgt)
        if self.is_stunned() or self.casting is not None:
            if self.casting is not None:
                self._update_cast(dt, tgt)
            return 0.0
        dx, dz = tgt.x - self.x, tgt.z - self.z
        dist = math.hypot(dx, dz)
        reach = self.reach(tgt)
        speed = self.speed * self.speed_factor()
        if self.charging:
            speed *= 2.8
            if dist <= reach:
                self.charging = False
        moved = 0.0
        if dist > reach * (0.92 if not self.ranged else 0.95):
            self.yaw = damp_angle(self.yaw, yaw_to(dx, dz), 10.0, dt)
            moved = self.motor.move(dt, dx, dz, speed)
            if self.motor.blocked and moved < 0.2:
                self._stuck_time = getattr(self, "_stuck_time", 0.0) + dt
                if self._stuck_time > 3.0:
                    self._stuck_time = 0.0
                    self.evade()
            else:
                self._stuck_time = 0.0
        else:
            self.yaw = damp_angle(self.yaw, yaw_to(dx, dz), 12.0, dt)
            if self.ranged and dist < 4.0 and not self.caster:
                pass
            if self.attack_timer <= 0 and abs(angle_diff(self.yaw, yaw_to(dx, dz))) < 60:
                self._attack(tgt)
        self._separate(dt)
        return moved

    def _separate(self, dt: float) -> None:
        for u in self.game.friendly_units():
            dx, dz = self.x - u.x, self.z - u.z
            d = math.hypot(dx, dz)
            min_d = (self.radius + u.radius) * 0.85
            if 1e-4 < d < min_d:
                self.motor.x += dx / d * (min_d - d)
                self.motor.z += dz / d * (min_d - d)
        for other in self.manager.enemies_near(self.x, self.z, 2.5):
            if other is self or other.dead or other.state == "respawning":
                continue
            dx, dz = self.x - other.x, self.z - other.z
            d = math.hypot(dx, dz)
            min_d = (self.radius + other.radius) * 0.8
            if 1e-4 < d < min_d:
                push = (min_d - d) * 0.5 * min(dt * 8, 1.0)
                self.motor.x += dx / d * push
                self.motor.z += dz / d * push

    def _attack(self, tgt: Unit) -> None:
        self.attack_timer = self.attack_speed
        if self.caster:
            self.casting = {"t": 0.0, "dur": float(self.t.get("cast_time", 2.0)), "name": "Fire Bolt"}
            self.rig.play("cast", self.casting["dur"])
            events.emit("enemy_cast_start", enemy=self, name="Fire Bolt", duration=self.casting["dur"])
            return
        if self.ranged:
            self.rig.play("shoot", 0.5)
            dmg = random.uniform(self.dmin, self.dmax)
            self.game.fx.projectile(self, tgt, self.t.get("projectile", "bolt"),
                                    lambda: self._deal(tgt, dmg, "ranged"))
            return
        self.rig.play("attack", min(0.55, self.attack_speed * 0.5))
        mult = self.next_hit_mult
        self.next_hit_mult = 1.0
        self.pending.append((0.22, lambda: self._melee_hit(tgt, mult)))

    def _melee_hit(self, tgt: Unit, mult: float) -> None:
        if self.dead or tgt.dead:
            return
        if self.distance_to(tgt) > self.reach(tgt) + 1.5:
            return
        self._deal(tgt, random.uniform(self.dmin, self.dmax) * mult, "melee")

    def _deal(self, tgt: Unit, dmg: float, kind: str) -> None:
        if self.dead or tgt.dead:
            return
        self.last_exchange = self.clock
        res = roll_attack(self.level, tgt.level, 0.05, can_dodge=kind == "melee")
        if res in ("miss", "dodge"):
            tgt.notify_miss(self, res)
            return
        if res == "crit":
            dmg *= 1.5
        tgt.take_damage(dmg, self, crit=res == "crit", kind=kind)
        for ab in self.t.get("abilities", []):
            if ab["id"] == "poison" and random.random() < ab.get("chance", 0.3):
                tick = ab.get("tick", 2) * (1 + 0.25 * (self.level - 1))
                tgt.add_aura(Aura("poison", "Venom", ab.get("duration", 8), self, tick=2.0,
                                  tick_damage=tick, school="nature", icon="venom"))

    def _update_cast(self, dt: float, tgt: Unit) -> None:
        c = self.casting
        c["t"] += dt
        self.yaw = damp_angle(self.yaw, yaw_to(tgt.x - self.x, tgt.z - self.z), 10.0, dt)
        if c["t"] >= c["dur"]:
            self.casting = None
            self.rig.play("release", 0.3)
            dmg = random.uniform(self.dmin, self.dmax) * 1.3
            self.game.fx.projectile(self, tgt, self.t.get("projectile", "fireball"),
                                    lambda: self._spell_hit(tgt, dmg))

    def _spell_hit(self, tgt: Unit, dmg: float) -> None:
        if tgt.dead:
            return
        tgt.take_damage(dmg, self, school="fire", kind="spell")

    # ------------------------------------------------------------------ abilities
    def _ready(self, key: str) -> bool:
        return self.cds.get(key, 0.0) <= 0

    def _abilities_tick(self, tgt: Unit) -> None:
        for ab in self.t.get("abilities", []):
            aid = ab["id"]
            if aid == "charge" and self._ready("charge") and not self.charging:
                d = self.distance_to(tgt)
                if ab.get("min_range", 6) <= d <= ab.get("max_range", 16):
                    self.charging = True
                    self.cds["charge"] = ab.get("cooldown", 14)
                    self.next_hit_mult = ab.get("mult", 1.3)
                    self.attack_timer = 0.0
                    self.rig.play("charge", 0.8)
            elif aid == "frenzy" and "frenzy" not in self.flags and self.hp < self.max_hp * ab.get("hp_below", 0.35):
                self.flags.add("frenzy")
                self.add_aura(Aura("frenzy", "Frenzy", 999, self, debuff=False, mods={"haste": ab.get("haste", 0.4)}))
                events.emit("emote", unit=self, text=f"{self.name} becomes frenzied!")
                self.rig.play("roar", 0.6)
            elif aid == "shell" and "shell" not in self.flags and self.hp < self.max_hp * ab.get("hp_below", 0.3):
                self.flags.add("shell")
                self.add_aura(Aura("shell", "Hardened Shell", 10, self, debuff=False, mods={"armor_mult": ab.get("armor_mult", 2.0)}))
                events.emit("emote", unit=self, text=f"{self.name} withdraws into its shell!")
            elif aid in ("dirty_strike", "swoop") and self._ready(aid) and self.edge_distance(tgt) < 2.0:
                self.cds[aid] = ab.get("cooldown", 10)
                self.next_hit_mult = ab.get("mult", 1.5)
            elif aid == "whirl" and self._ready("whirl") and self.edge_distance(tgt) < ab.get("radius", 7) - 1:
                self.cds["whirl"] = ab.get("cooldown", 14)
                radius = ab.get("radius", 7)
                tele = ab.get("telegraph", 1.4)
                self.game.fx.telegraph_circle(self.x, self.z, radius, tele, follow=self)
                self.rig.play("attack2", tele + 0.4)
                mult = ab.get("mult", 1.2)
                self.pending.append((tele, lambda r=radius, m=mult: self._aoe_hit(r, m)))
            elif aid == "fire_breath" and self._ready("fire_breath") and self.distance_to(tgt) < ab.get("range", 7):
                self.cds["fire_breath"] = ab.get("cooldown", 12)
                self.rig.play("roar", 1.0)
                self.game.fx.breath(self, 0.9)
                mult = ab.get("mult", 1.3)
                rng_ = ab.get("range", 7)
                self.pending.append((0.8, lambda m=mult, r=rng_: self._cone_hit(r, m)))

    def _aoe_hit(self, radius: float, mult: float) -> None:
        if self.dead:
            return
        for u in self.game.friendly_units():
            if not u.dead and math.hypot(u.x - self.x, u.z - self.z) <= radius + u.radius * 0.5:
                u.take_damage(random.uniform(self.dmin, self.dmax) * mult, self, kind="melee")
        self.game.fx.shockwave(self.x, self.world.ground(self.x, self.z), self.z, radius)

    def _cone_hit(self, rng_: float, mult: float) -> None:
        if self.dead:
            return
        for u in self.game.friendly_units():
            if u.dead:
                continue
            d = math.hypot(u.x - self.x, u.z - self.z)
            if d <= rng_ + u.radius and abs(angle_diff(self.yaw, yaw_to(u.x - self.x, u.z - self.z))) < 55:
                u.take_damage(random.uniform(self.dmin, self.dmax) * mult, self, school="fire", kind="spell")

    # ------------------------------------------------------------------ evade
    def _evade(self, dt: float) -> float:
        hx, hz = self.home
        dx, dz = hx - self.x, hz - self.z
        d = math.hypot(dx, dz)
        self.hp = min(self.max_hp, self.hp + self.max_hp * dt * 0.5)
        if self.flying:
            self.fly_height += (8.0 - self.fly_height) * min(dt, 1.0)
        if d < 1.0:
            self.state = "idle"
            self.hp = self.max_hp
            self.yaw = self.home_yaw
            self.wander_timer = random.uniform(3, 8)
            return 0.0
        self.yaw = damp_angle(self.yaw, yaw_to(dx, dz), 10.0, dt)
        moved = self.motor.move(dt, dx, dz, self.speed * 1.35)
        if moved < 0.2:
            self.motor.teleport(hx, hz)
        return moved

    # ------------------------------------------------------------------ visuals
    def sync(self, dt: float, speed: float = 0.0) -> None:
        m = self.motor
        root = self.rig.root
        root.setPos(m.x, m.y + self.fly_height, m.z)
        set_yaw(root, self.yaw)
        if self.visible:
            self.anim_accum += dt
            self._frame = getattr(self, "_frame", 0) + 1
            if self.lod_skip <= 0 or self._frame % (self.lod_skip + 1) == 0:
                self.rig.update(self.anim_accum, speed, m.grounded or self.flying, m.swimming)
                self.anim_accum = 0.0
        if not self.dead and not self.flying:
            self.shadow.setPos(m.x, m.y + 0.06, m.z)
        elif self.flying and not self.dead:
            self.shadow.setPos(m.x, self.world.ground(m.x, m.z) + 0.06, m.z)
            self.shadow.setAlphaScale(max(0.15, 1.0 - self.fly_height * 0.08))

    def set_visible(self, v: bool) -> None:
        if v == self.visible or self.state == "respawning":
            return
        self.visible = v
        if v:
            self.rig.root.show()
            if not self.dead:
                self.shadow.show()
        else:
            self.rig.root.hide()
            self.shadow.hide()

    def destroy(self) -> None:
        self.rig.destroy()
        self.shadow.removeNode()
