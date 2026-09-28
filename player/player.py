"""The player character: model, movement, stats, equipment, auto-attack, leveling and death."""
from __future__ import annotations

import math
import random
from typing import Any

from panda3d.core import Vec3

from combat.combat import roll_attack
from combat.unit import Unit
from core import data
from core.events import events
from core.rig import blob_shadow
from core.util import angle_diff, damp_angle, set_yaw, yaw_to
from items import item as I
from items.inventory import Equipment, Inventory
from npcs.models import HumanoidRig, build_humanoid
from player.controller import CharacterMotor
from progression.leveling import Experience
from progression.stats import CharacterStats

RUN_SPEED = 7.0
WALK_SPEED = 2.6
BACK_SPEED = 4.5
HUNTER_RANGE = 32.0

RACE_LOOKS: dict[str, dict[str, Any]] = {
    "orc": {"race": "orc", "pants": (0.32, 0.24, 0.17), "boots": (0.26, 0.17, 0.10), "bracers": (0.35, 0.22, 0.13)},
    "troll": {"race": "troll", "pants": (0.28, 0.34, 0.42), "boots": None, "bracers": (0.55, 0.40, 0.20),
              "belt": (0.5, 0.3, 0.15)},
}

WEAPON_MODEL = {"axe": "axe", "sword": "sword", "cutlass": "cutlass", "mace": "mace", "club": "club", "staff": "staff",
                "spear": "spear", "bow": "bow", "greataxe": "greataxe", "dagger": "dagger"}


class Player(Unit):
    """The hero. Owns stats, bags, gear, abilities and the character model."""

    faction = "player"
    is_player = True

    def __init__(self, game, race: str, cls: str, name: str, x: float, z: float, yaw: float = 0.0,
                 level: int = 1) -> None:
        super().__init__(name, level)
        self.game = game
        self.world = game.world
        self.race = race
        self.cls = cls
        self.cls_def = data.classes()[cls]
        self.resource_type = self.cls_def["resource"]
        self.stats = CharacterStats(cls)
        self.stats.aura_source = self
        self.xp = Experience(self, level, 0)
        self.inventory = Inventory()
        self.equipment = Equipment()
        look = dict(RACE_LOOKS.get(race, RACE_LOOKS["orc"]))
        look.update(self.cls_def.get("look", {}))
        self.base_look = look
        self.rig: HumanoidRig = build_humanoid(look)
        self.rig.root.reparentTo(self.world.actors)
        self.rig.root.setShaderInput("u_rim", 0.35)
        self.height = self.rig.height
        self.radius = 0.5
        self.shadow = blob_shadow(self.world.fx, 0.95)
        self.motor = CharacterMotor(self.world, x, z, radius=self.rig.radius)
        self.yaw = yaw
        self.walking = False
        self.move_dir = (0.0, 0.0)
        self.is_moving = False
        self.auto_attacking = False
        self.swing_timer = 0.0
        self.last_spend = -99.0
        self.clock = 0.0
        self.charge: dict[str, Any] | None = None
        self.death_timer = 0.0
        self.potion_cd = 0.0
        self.abilities = None   # set by AbilitySystem
        self.targetable = True
        self.hp = 1.0
        self.resource = 0.0
        self._last_region = None
        events.on("damage", self._on_damage_event)

    # ----------------------------------------------------------------- basics
    @property
    def x(self) -> float:
        return self.motor.x

    @property
    def z(self) -> float:
        return self.motor.z

    @property
    def y(self) -> float:
        return self.motor.y

    @property
    def position(self) -> Vec3:
        return Vec3(self.motor.x, self.motor.y, self.motor.z)

    @property
    def level(self) -> int:
        return self.xp.level if hasattr(self, "xp") else self._level

    @level.setter
    def level(self, v: int) -> None:
        self._level = v
        if hasattr(self, "xp"):
            self.xp.level = v

    def focus_point(self) -> Vec3:
        return Vec3(self.motor.x, self.motor.y + self.rig.height * 0.82, self.motor.z)

    # ----------------------------------------------------------------- stats
    def recalc(self, keep_ratio: bool = True) -> None:
        """Recompute pools/armor from base stats + gear (+auras)."""
        old_hp, old_max = self.hp, self.max_hp
        old_res, old_rmax = self.resource, self.max_resource
        self.stats.set_gear(self.equipment.total_stats())
        self.max_hp = float(int(self.stats.max_hp()))
        self.max_resource = float(int(self.stats.max_resource()))
        self.base_armor = self.stats.armor()
        if keep_ratio and old_max > 1:
            self.hp = min(self.max_hp, max(1.0, old_hp / old_max * self.max_hp)) if not self.dead else 0.0
        if self.resource_type == "mana" and keep_ratio and old_rmax > 1:
            self.resource = min(self.max_resource, old_res / old_rmax * self.max_resource)
        events.emit("stats_changed")

    def weapon_info(self) -> tuple[float, float, float]:
        w = self.equipment.weapon()
        if w and "damage" in w:
            return float(w["damage"][0]), float(w["damage"][1]), float(w.get("speed", 2.0))
        return 1.0, 3.0, 2.0

    def is_ranged(self) -> bool:
        return self.cls_def["attack_type"] == "ranged"

    def attack_power(self) -> float:
        return (self.stats.ranged_attack_power() if self.is_ranged() else self.stats.attack_power()) + self.mod("ap")

    def weapon_damage(self, normalized: bool = False) -> float:
        lo, hi, speed = self.weapon_info()
        base = random.uniform(lo, hi)
        sp = 2.4 if normalized else speed
        return base + self.attack_power() / 14.0 * sp

    def damage_range(self) -> tuple[int, int]:
        lo, hi, speed = self.weapon_info()
        bonus = self.attack_power() / 14.0 * speed
        return int(lo + bonus), int(hi + bonus)

    def spell_power(self) -> float:
        return self.stats.spell_power() + self.mod("spell_power")

    def crit_chance(self) -> float:
        return self.stats.crit_chance() + self.mod("crit")

    def damage_taken_mult(self) -> float:
        return super().damage_taken_mult() * (1.0 - float(self.cls_def.get("damage_reduction", 0.0)))

    def melee_reach(self, target: Unit) -> float:
        return self.radius + target.radius + 1.7

    def in_attack_range(self, target: Unit) -> bool:
        if self.is_ranged():
            return self.distance_to(target) <= HUNTER_RANGE
        return self.distance_to(target) <= self.melee_reach(target)

    # ----------------------------------------------------------------- equipment
    def equip(self, item_id: str, from_bag_index: int | None = None) -> bool:
        ok, why = I.can_equip(self, item_id)
        if not ok:
            events.emit("message", text=why, color=(1, 0.3, 0.3))
            return False
        slot = I.get(item_id)["slot"]
        if from_bag_index is not None:
            self.inventory.take_slot(from_bag_index)
        old = self.equipment.set(slot, item_id)
        if old:
            if from_bag_index is not None and self.inventory.slots[from_bag_index] is None:
                self.inventory.put_slot(from_bag_index, {"id": old, "count": 1})
            else:
                self.inventory.add(old, 1, silent=True)
        self.recalc()
        self.update_look()
        events.emit("sound", name="equip")
        return True

    def unequip(self, slot: str) -> bool:
        iid = self.equipment.get(slot)
        if not iid:
            return False
        if self.inventory.free_slots() == 0:
            events.emit("message", text="Your bags are full.", color=(1, 0.3, 0.3))
            return False
        self.equipment.set(slot, None)
        self.inventory.add(iid, 1, silent=True)
        self.recalc()
        self.update_look()
        return True

    def use_bag_item(self, index: int) -> None:
        """Right-click on a bag slot: equip gear or use a consumable."""
        s = self.inventory.slots[index]
        if not s or self.dead:
            return
        it = I.get(s["id"])
        if it["slot"] in I.EQUIP_SLOTS:
            self.equip(s["id"], index)
        elif it["slot"] == "consumable":
            self.use_consumable(index)
        elif it["slot"] == "quest":
            events.emit("message", text="That is a quest item.", color=(1, 0.85, 0.3))

    def use_consumable(self, index: int) -> bool:
        s = self.inventory.slots[index]
        if not s:
            return False
        it = I.get(s["id"])
        use = it.get("use", {})
        kind = use.get("type")
        if kind in ("food", "drink") and self.in_combat:
            events.emit("message", text="You can't do that while in combat.")
            return False
        if kind == "potion" and self.potion_cd > 0:
            events.emit("message", text=f"Potion not ready ({int(self.potion_cd) + 1}s).")
            return False
        if use.get("mana") and self.resource_type != "mana":
            events.emit("message", text="You have no mana to restore.")
            return False
        if use.get("heal"):
            self.heal(float(use["heal"]), self)
            self.game.fx.heal(self)
        if use.get("mana"):
            self.resource = min(self.max_resource, self.resource + float(use["mana"]))
        if kind == "potion":
            self.potion_cd = 30.0
        self.inventory.remove(s["id"], 1)
        events.emit("sound", name="heal" if use.get("heal") else "cast")
        return True

    def update_look(self) -> None:
        look = dict(self.base_look)
        eq = self.equipment
        chest = eq.get("chest")
        if chest:
            it = I.get(chest)
            look["chest_style"] = it.get("style", "tunic")
            look["shirt"] = tuple(it.get("color", (0.4, 0.3, 0.2)))
            if it.get("rarity") in ("uncommon", "rare") and it.get("style") == "plate":
                look["shoulders"] = tuple(it.get("color"))
        else:
            look["chest_style"] = "bare"
            look["shirt"] = None
        head = eq.get("head")
        if head:
            it = I.get(head)
            look["helmet"] = it.get("style", "cap")
            look["helmet_color"] = tuple(it.get("color", (0.4, 0.4, 0.4)))
            look["headdress"] = None
        legs = eq.get("legs")
        if legs:
            look["pants"] = tuple(I.get(legs).get("color", look["pants"]))
        boots = eq.get("boots")
        look["boots"] = tuple(I.get(boots).get("color")) if boots else None
        w = eq.get("weapon")
        if w:
            it = I.get(w)
            look["weapon"] = WEAPON_MODEL.get(it.get("weapon_type", "axe"), "axe")
            look["weapon_color"] = tuple(it.get("color")) if it.get("color") else None
        else:
            look["weapon"] = None
        self.rig.set_look(**look)

    # ----------------------------------------------------------------- setup
    def give_starting_kit(self) -> None:
        for slot, iid in self.cls_def.get("starting_gear", {}).items():
            self.equipment.set(slot, iid)
        for iid, n in self.cls_def.get("starting_items", []):
            self.inventory.add(iid, n, silent=True)
        self.recalc(keep_ratio=False)
        self.hp = self.max_hp
        self.resource = 0.0 if self.resource_type == "rage" else self.max_resource
        self.update_look()

    # ----------------------------------------------------------------- level
    def on_level_up(self, new_level: int) -> None:
        growth = data.levels()["level_up"][self.cls]
        gained = self.stats.level_up(growth)
        self.recalc(keep_ratio=False)
        self.hp = self.max_hp
        if self.resource_type == "mana":
            self.resource = self.max_resource
        events.emit("level_up", level=new_level, gained=gained, hp=growth.get("hp", 0), resource=growth.get("resource", 0))

    def gain_xp(self, amount: int, reason: str = "") -> None:
        self.xp.gain(amount, reason)

    # ----------------------------------------------------------------- resources
    def spend(self, amount: float) -> bool:
        if amount <= 0:
            return True
        if self.resource < amount:
            return False
        self.resource -= amount
        self.last_spend = self.clock
        return True

    def gain_rage(self, amount: float) -> None:
        if self.resource_type == "rage":
            self.resource = min(self.max_resource, self.resource + amount)

    def _regen(self, dt: float) -> None:
        in_combat = self.in_combat
        if not in_combat and self.hp < self.max_hp:
            self.hp = min(self.max_hp, self.hp + self.max_hp * 0.028 * dt)
        if self.resource_type == "mana":
            rate = 0.035 if self.clock - self.last_spend > 5.0 else 0.006
            if in_combat:
                rate *= 0.6 if self.clock - self.last_spend > 5.0 else 1.0
            self.resource = min(self.max_resource, self.resource + self.max_resource * rate * dt)
        elif self.resource_type == "rage" and not in_combat:
            self.resource = max(0.0, self.resource - 2.0 * dt)

    def _on_damage_event(self, target, source, amount, crit=False, **kw) -> None:
        if target is self and self.resource_type == "rage" and not self.dead:
            self.gain_rage(amount / max(self.max_hp, 1) * 70.0)

    # ----------------------------------------------------------------- combat
    def take_damage(self, amount: float, source: Unit | None, school: str = "physical", crit: bool = False,
                    kind: str = "melee", ability: str | None = None) -> int:
        dealt = super().take_damage(amount, source, school, crit, kind, ability)
        if dealt and not self.dead:
            self.rig.flash(0.1)
            if self.abilities and self.abilities.casting and kind != "dot":
                self.abilities.pushback()
            # auto-select attackers when idle
            if source is not None and self.game.targeting.target is None and not source.dead:
                self.game.targeting.set_target(source)
                self.auto_attacking = True
        return dealt

    def die(self, killer: Unit | None) -> None:
        self.auto_attacking = False
        self.targetable = False
        self.charge = None
        if self.abilities:
            self.abilities.cancel_cast()
        self.rig.die()
        super().die(killer)
        self.death_timer = 0.0

    def revive(self, x: float, z: float, frac: float = 0.6) -> None:
        self.dead = False
        self.targetable = True
        self.hp = self.max_hp * frac
        if self.resource_type == "mana":
            self.resource = self.max_resource * frac
        else:
            self.resource = 0.0
        self.auras.clear()
        self.combat_timer = 0.0
        self.rig.revive()
        self.teleport(x, z)
        events.emit("player_revived")

    def _auto_attack(self, dt: float) -> None:
        self.swing_timer -= dt * self.haste()
        t = self.target
        if not self.auto_attacking or t is None or getattr(t, "dead", True) or not self.is_hostile_to(t):
            if t is not None and getattr(t, "dead", False):
                self.auto_attacking = False
            return
        if self.abilities and self.abilities.casting:
            return
        if not self.in_attack_range(t):
            return
        if self.is_moving and self.is_ranged():
            return
        if self.swing_timer > 0:
            return
        lo, hi, speed = self.weapon_info()
        self.swing_timer = speed
        self.face_towards(t.x, t.z)
        if self.is_ranged():
            self.rig.play("shoot", 0.55)
            dmg = self.weapon_damage()
            res = roll_attack(self.level, t.level, self.crit_chance(), can_dodge=False)
            events.emit("sound", name="bow")
            self.game.fx.projectile(self, t, "arrow", lambda: self._resolve_hit(t, dmg, res, "ranged"))
        else:
            self.rig.play("attack" if random.random() < 0.6 else "attack2", min(0.5, speed * 0.45))
            dmg = self.weapon_damage()
            res = roll_attack(self.level, t.level, self.crit_chance(), can_dodge=True)
            events.emit("sound", name="swing")
            self.game.pending(0.18, lambda: self._resolve_hit(t, dmg, res, "melee"))

    def _resolve_hit(self, t: Unit, dmg: float, res: str, kind: str) -> None:
        if t.dead or self.dead:
            return
        if res in ("miss", "dodge"):
            t.notify_miss(self, res)
            return
        crit = res == "crit"
        if crit:
            dmg *= 2.0
        dealt = t.take_damage(dmg, self, crit=crit, kind=kind)
        if dealt:
            _, _, speed = self.weapon_info()
            self.gain_rage(4.5 * speed * (1.5 if crit else 1.0))
            self.game.fx.hit(t, crit, "blood" if kind == "melee" else "spark")
            events.emit("sound", name="crit" if crit else "hit")

    # ----------------------------------------------------------------- movement
    def can_move(self) -> bool:
        return not self.dead and not self.is_stunned() and self.charge is None

    def update_movement(self, dt: float, keys: dict, cam_yaw: float, mouselook: bool, can_move: bool = True) -> None:
        if self.charge is not None:
            self._update_charge(dt)
            return
        fwd = (1.0 if keys.get("w") else 0.0) - (1.0 if keys.get("s") else 0.0)
        side = (1.0 if keys.get("d") or keys.get("e") else 0.0) - (1.0 if keys.get("a") or keys.get("q") else 0.0)
        if keys.get("both_mouse"):
            fwd = 1.0
        if not can_move:
            fwd = side = 0.0
        self.walking = bool(keys.get("shift"))
        r = math.radians(cam_yaw)
        fx, fz = math.sin(r), math.cos(r)
        rx, rz = math.cos(r), -math.sin(r)
        wx = fx * fwd + rx * side
        wz = fz * fwd + rz * side
        moving = abs(wx) + abs(wz) > 1e-3
        speed = WALK_SPEED if self.walking else RUN_SPEED
        if mouselook and fwd < 0 and side == 0:
            speed = min(speed, BACK_SPEED)
        speed *= self.speed_factor()
        jump = bool(keys.get("jump")) and can_move
        moved = self.motor.move(dt, wx, wz, speed, jump)
        self.is_moving = moving and moved > 0.1
        if self.motor.sea_blocked and moving and self.clock - getattr(self, "_sea_msg_t", -99.0) > 4.0:
            self._sea_msg_t = self.clock
            events.emit("message", text="The currents are too strong to swim any further.", color=(0.6, 0.85, 1.0))
        if self.motor.landed_fall > 9.0:
            fall = self.motor.landed_fall
            self.take_damage(self.max_hp * min(0.9, (fall - 9.0) * 0.06), None, kind="true")
        t = self.target
        engaged = t is not None and self.auto_attacking and not getattr(t, "dead", True)
        if mouselook:
            self.yaw = cam_yaw
        elif moving:
            self.yaw = damp_angle(self.yaw, yaw_to(wx, wz), 14.0, dt)
        elif engaged or (self.abilities and self.abilities.casting and t is not None):
            self.yaw = damp_angle(self.yaw, yaw_to(t.x - self.x, t.z - self.z), 12.0, dt)
        self.move_dir = (wx, wz)
        if self.is_moving and self.abilities and self.abilities.casting:
            self.abilities.cancel_cast("Interrupted")

    def _update_charge(self, dt: float) -> None:
        c = self.charge
        t = c["target"]
        c["time"] += dt
        if t.dead or c["time"] > 1.5:
            self.charge = None
            return
        dx, dz = t.x - self.x, t.z - self.z
        d = math.hypot(dx, dz)
        self.yaw = yaw_to(dx, dz)
        if d <= self.melee_reach(t) * 0.8:
            self.charge = None
            c["on_arrive"]()
            return
        self.motor.move(dt, dx, dz, 30.0)
        self.is_moving = True
        if random.random() < dt * 20:
            self.game.fx.dust_puff(self.x, self.y, self.z, 3)

    def face_towards(self, x: float, z: float) -> None:
        self.yaw = yaw_to(x - self.x, z - self.z)

    def facing_error(self, x: float, z: float) -> float:
        return abs(angle_diff(self.yaw, yaw_to(x - self.x, z - self.z)))

    # ----------------------------------------------------------------- per frame
    def update(self, dt: float) -> None:
        self.clock += dt
        self.potion_cd = max(0.0, self.potion_cd - dt)
        if self.dead:
            self.death_timer += dt
            return
        self.update_auras(dt)
        if self.dead:
            return
        self.combat_timer = max(0.0, self.combat_timer - dt)
        self._regen(dt)
        self._auto_attack(dt)

    def sync_model(self, dt: float) -> None:
        m = self.motor
        self.rig.root.setPos(m.x, m.y, m.z)
        set_yaw(self.rig.root, self.yaw)
        self.rig.update(dt, m.last_speed if self.is_moving else 0.0, m.grounded, m.swimming)
        g = self.world.ground(m.x, m.z, m.y + 0.1)
        self.shadow.setPos(m.x, g + 0.06, m.z)
        k = max(0.0, 1.0 - (m.y - g) * 0.25)
        self.shadow.setScale(0.6 + 0.4 * k)
        self.shadow.setAlphaScale(k)
        if m.swimming or self.dead:
            self.shadow.hide()
        else:
            self.shadow.show()

    def teleport(self, x: float, z: float, yaw: float | None = None) -> None:
        self.motor.teleport(x, z)
        if yaw is not None:
            self.yaw = yaw
        self.sync_model(0.0)

    def destroy(self) -> None:
        events.off("damage", self._on_damage_event)
        self.rig.destroy()
        self.shadow.removeNode()

    # ----------------------------------------------------------------- save
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "race": self.race, "cls": self.cls, "level": self.level, "xp": self.xp.xp,
            "pos": [self.x, self.z], "yaw": self.yaw, "hp": self.hp, "resource": self.resource,
            "stats": self.stats.to_dict(), "gold": self.inventory.gold, "bags": self.inventory.to_list(),
            "equipment": dict(self.equipment.slots),
        }

    def load_dict(self, d: dict[str, Any]) -> None:
        self.xp.level = int(d.get("level", 1))
        self.xp.xp = int(d.get("xp", 0))
        self.stats.load_dict(d.get("stats", {}))
        self.inventory.load_list(d.get("bags", []))
        self.inventory.gold = int(d.get("gold", 0))
        for slot, iid in d.get("equipment", {}).items():
            self.equipment.slots[slot] = iid if iid and I.exists(iid) else None
        self.recalc(keep_ratio=False)
        self.hp = min(self.max_hp, float(d.get("hp", self.max_hp)))
        self.resource = min(self.max_resource, float(d.get("resource", 0)))
        self.update_look()
        pos = d.get("pos")
        if pos:
            self.teleport(float(pos[0]), float(pos[1]), float(d.get("yaw", 0)))
