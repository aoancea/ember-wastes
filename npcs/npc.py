"""Friendly NPCs: quest givers, vendors, trainers and escorts."""
from __future__ import annotations

import math
import random
from typing import Any

from combat.unit import Unit
from core import data
from core.events import events
from core.rig import blob_shadow
from core.util import damp_angle, set_yaw, yaw_to
from npcs.models import build_humanoid
from player.controller import CharacterMotor


class NPC(Unit):
    """A friendly character you can talk to. Escort NPCs can also walk and be attacked."""

    faction = "friendly"

    def __init__(self, manager, npc_id: str, d: dict[str, Any]) -> None:
        super().__init__(d["name"], d.get("level", 10))
        self.manager = manager
        self.game = manager.game
        self.id = npc_id
        self.d = d
        self.title = d.get("title", "")
        world = self.game.world
        look = dict(d.get("look", {}))
        self.rig = build_humanoid(look)
        self.rig.root.reparentTo(world.actors)
        self.radius = max(0.5, self.rig.radius)
        self.height = self.rig.height
        x, z = d["pos"]
        self.motor = CharacterMotor(world, float(x), float(z), radius=0.45)
        if "face" in d:
            self.home_yaw = yaw_to(d["face"][0] - x, d["face"][1] - z)
        else:
            self.home_yaw = float(d.get("yaw", 0.0))
        self.yaw = self.home_yaw
        self.home = (float(x), float(z))
        self.shadow = blob_shadow(world.fx, 0.8)
        self.max_hp = self.hp = 400.0
        self.base_armor = 200.0
        self.targetable = False
        self.idle_timer = random.uniform(3, 10)
        self.vendor_items: list[str] = d.get("vendor", [])
        self.trainer: str | None = d.get("trainer")
        self.wounded = bool(d.get("wounded"))
        self.captive = bool(d.get("captive"))
        self.walk_target: tuple[float, float] | None = None
        self.walk_speed = 4.2
        self.following = False
        self.visible_flag = True
        if self.wounded:
            self.rig.play("kneel", 9999)
        self._sync(0.0, 0.0)

    # --------------------------------------------------------------- basics
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
    def title_short(self) -> str:
        return self.title

    @property
    def subtitle(self) -> str:
        return self.title

    def interact(self, game) -> None:
        self.face(game.player.x, game.player.z)
        if game.hud:
            game.hud.open_dialogue(self)
        events.emit("npc_talked", npc=self)

    def face(self, x: float, z: float) -> None:
        self.yaw = yaw_to(x - self.x, z - self.z)

    def quest_marker(self) -> tuple[str, tuple] | str:
        q = self.game.quests
        if q is None:
            return ""
        return q.marker_for(self)

    # --------------------------------------------------------------- combat hooks (escort)
    def take_damage(self, amount: float, source: Unit | None, school: str = "physical", crit: bool = False,
                    kind: str = "melee", ability: str | None = None) -> int:
        if not self.targetable:
            return 0
        dealt = super().take_damage(amount, source, school, crit, kind, ability)
        if dealt:
            self.rig.flash(0.1)
        return dealt

    def die(self, killer: Unit | None) -> None:
        self.rig.die()
        super().die(killer)

    def reset(self) -> None:
        """Back to the spawn point, alive and idle (e.g. after a failed escort)."""
        self.dead = False
        self.hp = self.max_hp
        self.auras.clear()
        self.targetable = False
        self.walk_target = None
        self.rig.revive()
        self.motor.teleport(*self.home)
        self.yaw = self.home_yaw
        if self.wounded:
            self.rig.play("kneel", 9999)

    # --------------------------------------------------------------- update
    def update(self, dt: float) -> None:
        if self.dead:
            self.rig.update(dt, 0.0)
            return
        self.update_auras(dt)
        speed = 0.0
        p = self.game.player
        if self.walk_target is not None:
            tx, tz = self.walk_target
            dx, dz = tx - self.x, tz - self.z
            d = math.hypot(dx, dz)
            if d > 0.5:
                self.yaw = damp_angle(self.yaw, yaw_to(dx, dz), 8.0, dt)
                speed = self.motor.move(dt, dx, dz, self.walk_speed)
            else:
                self.walk_target = None
        elif p is not None and not self.captive:
            d = math.hypot(p.x - self.x, p.z - self.z)
            if d < 9.0 and not p.dead:
                target = yaw_to(p.x - self.x, p.z - self.z)
                diff = (target - self.home_yaw + 180) % 360 - 180
                self.rig.look_yaw = max(-70.0, min(70.0, diff))
                if abs(diff) > 70 and d < 5.0:
                    self.yaw = damp_angle(self.yaw, target, 3.0, dt)
            else:
                self.rig.look_yaw *= 0.95
                self.yaw = damp_angle(self.yaw, self.home_yaw, 2.0, dt)
        self.idle_timer -= dt
        if self.idle_timer <= 0 and not self.wounded and self.walk_target is None:
            self.idle_timer = random.uniform(6, 14)
            self.rig.play(random.choice(["talk", "talk", "interact"]) if not self.captive else "hit", 1.6)
        self._sync(dt, speed)

    def _sync(self, dt: float, speed: float) -> None:
        m = self.motor
        self.rig.root.setPos(m.x, m.y, m.z)
        set_yaw(self.rig.root, self.yaw)
        if self.visible_flag:
            self.rig.update(dt, speed, True, m.swimming)
        self.shadow.setPos(m.x, m.y + 0.06, m.z)

    def set_visible(self, v: bool) -> None:
        if v != self.visible_flag:
            self.visible_flag = v
            if v:
                self.rig.root.show()
                self.shadow.show()
            else:
                self.rig.root.hide()
                self.shadow.hide()


class NPCManager:
    def __init__(self, game) -> None:
        self.game = game
        self.npcs: dict[str, NPC] = {}
        for nid, d in data.npcs().items():
            self.npcs[nid] = NPC(self, nid, d)
        # NPCs are solid
        for n in self.npcs.values():
            if not n.wounded:
                game.world.collision.add_circle(n.x, n.z, 0.55, top=n.motor.y + 2.2, tag="npc")
        self._vis_t = 0.0

    def get(self, nid: str) -> NPC | None:
        return self.npcs.get(nid)

    def near(self, x: float, z: float, r: float) -> list[NPC]:
        r2 = r * r
        return [n for n in self.npcs.values() if n.visible_flag and (n.x - x) ** 2 + (n.z - z) ** 2 < r2]

    def update(self, dt: float) -> None:
        p = self.game.player
        if p is None:
            return
        self._vis_t -= dt
        do_vis = self._vis_t <= 0
        if do_vis:
            self._vis_t = 0.3
        for n in self.npcs.values():
            d2 = (n.x - p.x) ** 2 + (n.z - p.z) ** 2
            if do_vis:
                n.set_visible(d2 < 170 ** 2 and not self.game.world.underground)
            if d2 < 120 ** 2 or n.walk_target is not None or n.targetable:
                n.update(dt)
