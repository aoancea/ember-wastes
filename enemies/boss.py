"""Scripted boss encounters: Grakk the Tunnelmaw (mine) and Warlord Rukhar Cinderjaw (gate)."""
from __future__ import annotations

import math
import random

from combat.unit import Aura
from core.events import events
from enemies.enemy import Enemy


class GrakkBoss(Enemy):
    """Phase 1: fist smashes + telegraphed Ground Slam.
    Phase 2 (below 50%): summons tunnelers, attacks faster and burrows to erupt under the player."""

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.phase = 1
        self.slam_cd = 8.0
        self.burrow_cd = 6.0
        self.burrowing = 0.0
        self.adds: list[Enemy] = []

    def engage(self, target, social: bool = True) -> None:
        was = self.state != "combat"
        super().engage(target, social=False)
        if was and self.state == "combat":
            self.rig.play("roar", 1.2)
            events.emit("chat", text="<rgb(1,0.45,0.3)>Grakk the Tunnelmaw roars: FRESH MEAT FOR THE MAW!")
            events.emit("sound", name="roar")
            events.emit("boss_engaged", boss=self)

    def evade(self) -> None:
        super().evade()
        self.phase = 1
        self.burrowing = 0.0
        self.rig.burrow = 0.0
        self.targetable = True
        for a in self.adds:
            if not a.dead:
                a.evade()
        self.adds.clear()

    def take_damage(self, amount, source, school="physical", crit=False, kind="melee", ability=None) -> int:
        if getattr(self, "burrowing", 0.0) > 0:
            return 0
        return super().take_damage(amount, source, school, crit, kind, ability)

    def _combat(self, dt: float) -> float:
        tgt = self.pick_target()
        if tgt is None or math.hypot(self.x - self.home[0], self.z - self.home[1]) > 55:
            self.evade()
            return 0.0
        self.target = tgt
        self.slam_cd -= dt
        if self.phase == 1 and self.hp < self.max_hp * 0.5:
            self._enter_phase2()
        if self.burrowing > 0:
            return self._update_burrow(dt, tgt)
        if self.phase == 2:
            self.burrow_cd -= dt
            if self.burrow_cd <= 0 and self.casting is None and not self.pending:
                self._start_burrow(tgt)
                return 0.0
        if self.slam_cd <= 0 and self.distance_to(tgt) < 10 and not self.pending:
            self.slam_cd = 11.0 if self.phase == 1 else 9.0
            r = 9.0
            self.game.fx.telegraph_circle(self.x, self.z, r, 1.8)
            self.rig.play("slam", 2.2)
            events.emit("chat", text="<rgb(1,0.6,0.3)>Grakk raises his fists high! Get clear!")
            self.pending.append((1.8, lambda: self._slam(r)))
            self.attack_timer = 2.4
            return 0.0
        if self.pending:
            return 0.0
        return super()._combat(dt)

    def _slam(self, r: float) -> None:
        if self.dead:
            return
        for u in self.game.friendly_units():
            if math.hypot(u.x - self.x, u.z - self.z) <= r + u.radius * 0.5:
                u.take_damage(random.uniform(self.dmin, self.dmax) * 2.2, self, kind="melee", ability="Ground Slam")
        self.game.fx.shockwave(self.x, self.motor.y, self.z, r, (1.0, 0.55, 0.25, 0.9))
        events.emit("sound", name="stomp")

    def _enter_phase2(self) -> None:
        self.phase = 2
        self.burrow_cd = 5.0
        self.add_aura(Aura("enrage", "Tunnel Fury", 9999, self, debuff=False, mods={"haste": 0.25}))
        self.rig.play("roar", 1.4)
        events.emit("chat", text="<rgb(1,0.45,0.3)>Grakk the Tunnelmaw bellows: DIGGERS! TO ME!")
        events.emit("sound", name="roar")
        for k in range(2):
            a = math.radians(self.yaw + (k * 2 - 1) * 70)
            x, z = self.x + math.sin(a) * 9, self.z + math.cos(a) * 9
            e = self.manager.spawn("tunnel_goblin", 8, x, z, {"temporary": True, "wander": 0.0})
            if self.target is not None:
                e.engage(self.target, social=False)
            self.adds.append(e)
            self.game.fx.dust_puff(x, self.motor.y, z, 14)

    def _start_burrow(self, tgt) -> None:
        self.burrowing = 3.2
        self.burrow_cd = 13.0
        self.targetable = False
        self.burrow_target = (tgt.x, tgt.z)
        events.emit("chat", text="<rgb(1,0.6,0.3)>Grakk burrows into the ground! The floor trembles beneath you...")
        self.game.fx.dust_puff(self.x, self.motor.y, self.z, 16)
        events.emit("sound", name="stomp", volume=0.6)

    def _update_burrow(self, dt: float, tgt) -> float:
        t_prev = self.burrowing
        self.burrowing -= dt
        elapsed = 3.2 - self.burrowing
        if elapsed < 0.8:
            self.rig.burrow = min(1.0, elapsed / 0.8)
        elif t_prev > 1.6 >= self.burrowing:
            # lock the eruption point on the target and warn
            self.burrow_target = (tgt.x, tgt.z)
            self.game.fx.telegraph_circle(tgt.x, tgt.z, 4.5, 1.5)
        elif elapsed >= 0.8 and self.burrowing > 1.6:
            pass
        if self.burrowing <= 0:
            bx, bz = self.burrow_target
            self.motor.teleport(bx, bz)
            self.burrowing = 0.0
            self.rig.burrow = 0.0
            self.targetable = True
            self.rig.play("roar", 0.8)
            for u in self.game.friendly_units():
                if math.hypot(u.x - bx, u.z - bz) <= 4.5 + u.radius * 0.5:
                    u.take_damage(random.uniform(self.dmin, self.dmax) * 2.4, self, kind="melee", ability="Tunnel Burst")
            self.game.fx.shockwave(bx, self.motor.y, bz, 4.5, (0.9, 0.6, 0.35, 0.9))
            events.emit("sound", name="stomp")
        return 0.0

    def sync(self, dt: float, speed: float = 0.0) -> None:
        super().sync(dt, speed)
        if getattr(self, "burrowing", 0.0) > 0:
            self.shadow.hide()
        elif not self.dead:
            self.shadow.show()


class WarlordBoss(Enemy):
    """Warlord Rukhar: heavy axe, telegraphed Cinder Whirl, calls raiders and enrages at 50%."""

    def __init__(self, *a, **kw) -> None:
        super().__init__(*a, **kw)
        self.phase = 1
        self.whirl_cd = 9.0
        self.adds: list[Enemy] = []

    def engage(self, target, social: bool = True) -> None:
        was = self.state != "combat"
        super().engage(target, social=True)
        if was and self.state == "combat":
            self.rig.play("roar", 1.2)
            events.emit("chat", text="<rgb(1,0.45,0.3)>Warlord Rukhar Cinderjaw shouts: The clans grew soft. I will burn the softness out of them - starting with you!")
            events.emit("sound", name="roar")
            events.emit("boss_engaged", boss=self)

    def evade(self) -> None:
        super().evade()
        self.phase = 1
        for a in self.adds:
            if not a.dead:
                a.evade()
        self.adds.clear()

    def _combat(self, dt: float) -> float:
        tgt = self.pick_target()
        if tgt is None or math.hypot(self.x - self.home[0], self.z - self.home[1]) > 60:
            self.evade()
            return 0.0
        self.whirl_cd -= dt
        if self.phase == 1 and self.hp < self.max_hp * 0.5:
            self.phase = 2
            self.add_aura(Aura("enrage", "Cinder Rage", 9999, self, debuff=False, mods={"haste": 0.3}))
            self.rig.play("roar", 1.3)
            events.emit("chat", text="<rgb(1,0.45,0.3)>Warlord Rukhar Cinderjaw roars: DUSTFANG! TO YOUR WARLORD!")
            for k in range(2):
                a = math.radians(self.yaw + 150 + k * 60)
                x, z = self.x + math.sin(a) * 12, self.z + math.cos(a) * 12
                e = self.manager.spawn("dustfang_raider", 9, x, z, {"temporary": True, "wander": 0.0})
                e.engage(tgt, social=False)
                self.adds.append(e)
        if self.whirl_cd <= 0 and self.distance_to(tgt) < 8 and not self.pending:
            self.whirl_cd = 12.0 if self.phase == 1 else 9.0
            r = 7.5
            self.game.fx.telegraph_circle(self.x, self.z, r, 1.6, follow=self)
            self.rig.play("attack2", 2.0)
            events.emit("chat", text="<rgb(1,0.6,0.3)>Rukhar begins to spin his burning axe!")
            self.pending.append((1.6, lambda: self._whirl(r)))
            return 0.0
        if self.pending:
            return 0.0
        return super()._combat(dt)

    def _whirl(self, r: float) -> None:
        if self.dead:
            return
        for u in self.game.friendly_units():
            if math.hypot(u.x - self.x, u.z - self.z) <= r + u.radius * 0.5:
                u.take_damage(random.uniform(self.dmin, self.dmax) * 2.0, self, school="fire", kind="melee", ability="Cinder Whirl")
        self.game.fx.shockwave(self.x, self.motor.y, self.z, r, (1.0, 0.45, 0.1, 0.9))
        events.emit("sound", name="fire")


BOSS_CLASSES = {"grakk": GrakkBoss, "warlord_rukhar": WarlordBoss}
