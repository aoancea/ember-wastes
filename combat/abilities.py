"""Player abilities: data-driven definitions from abilities.json executed by type."""
from __future__ import annotations

import random
from typing import Any

from combat.combat import roll_attack, roll_spell
from combat.unit import Aura, Unit
from core import data
from core.events import events
from settings import GLOBAL_COOLDOWN

GREEN = (0.25, 1.0, 0.25)
WHITE = (1.0, 1.0, 1.0)
GREY = (0.7, 0.7, 0.7)
YELLOW = (1.0, 0.85, 0.3)
RED = (1.0, 0.3, 0.25)


class AbilitySystem:
    """Known abilities, ranks, cooldowns, the global cooldown and cast bars for the player."""

    def __init__(self, game, player) -> None:
        self.game = game
        self.p = player
        player.abilities = self
        self.defs: dict[str, Any] = data.abilities()
        self.order: list[str] = list(player.cls_def["abilities"])
        self.known: dict[str, int] = {}
        self.cooldowns: dict[str, float] = {}
        self.gcd = 0.0
        self.casting: dict[str, Any] | None = None

    # ----------------------------------------------------------------- data
    def rank_data(self, aid: str, rank: int | None = None) -> dict[str, Any]:
        d = dict(self.defs[aid])
        ranks = d.pop("ranks")
        r = rank if rank is not None else self.known.get(aid, 1)
        r = max(1, min(r, len(ranks)))
        d.update(ranks[r - 1])
        d["id"] = aid
        d["max_rank"] = len(ranks)
        return d

    def ranks(self, aid: str) -> list[dict[str, Any]]:
        return self.defs[aid]["ranks"]

    def learn(self, aid: str, rank: int) -> None:
        self.known[aid] = rank
        events.emit("ability_learned", ability=aid, rank=rank)

    def hotbar(self) -> list[str | None]:
        return [aid if aid in self.known else None for aid in self.order]

    def cooldown_left(self, aid: str) -> tuple[float, float]:
        """(remaining, total) of the longest of the ability cooldown and the GCD."""
        d = self.defs[aid]
        cd = self.cooldowns.get(aid, 0.0)
        total = float(d.get("cooldown", 0))
        if not d.get("off_gcd") and self.gcd > cd:
            return self.gcd, GLOBAL_COOLDOWN
        return cd, max(total, 0.01)

    def cost_text(self, aid: str) -> str:
        d = self.defs[aid]
        c = d.get("cost", 0)
        if not c:
            return ""
        return f"{c} {'Rage' if self.p.resource_type == 'rage' else 'Mana'}"

    def describe(self, aid: str, rank: int | None = None) -> str:
        d = self.rank_data(aid, rank)
        text = d["description"]
        fmt = {k: v for k, v in d.items() if isinstance(v, (int, float))}
        try:
            return text.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return text

    def tooltip(self, aid: str, rank: int | None = None) -> list[tuple[str, tuple]]:
        d = self.rank_data(aid, rank)
        r = rank if rank is not None else self.known.get(aid, 1)
        lines: list[tuple[str, tuple]] = [(d["name"], WHITE), (f"Rank {r}", GREY)]
        cost = self.cost_text(aid)
        rng = d.get("range")
        rng_t = "Melee range" if rng == "melee" else (f"{rng} yd range" if rng else "")
        if cost or rng_t:
            lines.append((f"{cost}    {rng_t}".strip(), WHITE))
        ct = d.get("cast_time", 0)
        cd = d.get("cooldown", 0)
        lines.append((f"{'Instant' if not ct else f'{ct:.1f} sec cast'}    {f'{cd:g} sec cooldown' if cd else ''}".strip(), WHITE))
        lines.append((self.describe(aid, rank), YELLOW))
        return lines

    # ----------------------------------------------------------------- checks
    def _target(self) -> Unit | None:
        t = self.p.target
        if t is None or not hasattr(t, "take_damage"):
            return None
        return t

    def can_use(self, aid: str) -> tuple[bool, str]:
        p = self.p
        if aid not in self.known:
            return False, "You haven't learned that yet."
        if p.dead:
            return False, "You are dead."
        if p.is_stunned():
            return False, "You are stunned."
        d = self.rank_data(aid)
        if self.casting:
            return False, "You are already casting."
        if self.cooldowns.get(aid, 0) > 0:
            return False, "That isn't ready yet."
        if not d.get("off_gcd") and self.gcd > 0:
            return False, ""
        cost = d.get("cost", 0)
        if cost and p.resource < cost:
            return False, f"Not enough {'rage' if p.resource_type == 'rage' else 'mana'}."
        needs_target = d["type"] in ("weapon_strike", "charge", "bleed", "ranged_shot", "dot_shot", "slow_shot",
                                     "ground_barrage", "spell_bolt", "spell_dot", "chain")
        if needs_target:
            t = self._target()
            if t is None:
                return False, "You have no target."
            if t.dead or not p.is_hostile_to(t):
                return False, "Invalid target."
            dist = p.distance_to(t)
            rng = d.get("range")
            if rng == "melee":
                if dist > p.melee_reach(t):
                    return False, "Out of range."
            elif isinstance(rng, (int, float)) and rng > 0 and dist > rng:
                return False, "Out of range."
            if d.get("min_range") and dist < d["min_range"]:
                return False, "Too close."
            if d["type"] == "charge" and p.in_combat and not d.get("usable_in_combat", True):
                return False, "Can't do that while in combat."
        return True, ""

    # ----------------------------------------------------------------- use
    def use_slot(self, index: int) -> None:
        hb = self.hotbar()
        if 0 <= index < len(hb) and hb[index]:
            self.use(hb[index])
        elif 0 <= index < len(self.order):
            aid = self.order[index]
            lvl = self.defs[aid]["level"]
            if self.p.level < lvl:
                events.emit("message", text=f"{self.defs[aid]['name']} is learned at level {lvl}.", color=RED)
            else:
                events.emit("message", text=f"Visit the class trainer in Redtusk Post to learn {self.defs[aid]['name']}.",
                            color=YELLOW)

    def use(self, aid: str) -> bool:
        ok, why = self.can_use(aid)
        if not ok:
            if why:
                events.emit("message", text=why, color=RED)
                events.emit("sound", name="error")
            return False
        d = self.rank_data(aid)
        p = self.p
        t = self._target()
        if t is not None and d.get("range") not in (0, None):
            p.face_towards(t.x, t.z)
        if d.get("cast_time", 0) > 0:
            self.casting = {"id": aid, "t": 0.0, "dur": float(d["cast_time"]), "target": t, "data": d}
            p.rig.play("channel", 99)
            events.emit("cast_start", ability=aid, duration=d["cast_time"], name=d["name"])
            events.emit("sound", name="cast")
            if not d.get("off_gcd"):
                self.gcd = GLOBAL_COOLDOWN
            return True
        if not p.spend(d.get("cost", 0)):
            return False
        self._execute(d, t)
        self._after_use(d)
        return True

    def _after_use(self, d: dict[str, Any]) -> None:
        if d.get("cooldown"):
            self.cooldowns[d["id"]] = float(d["cooldown"])
        if not d.get("off_gcd"):
            self.gcd = max(self.gcd, GLOBAL_COOLDOWN)
        t = self._target()
        if t is not None and not t.dead and self.p.is_hostile_to(t):
            self.p.auto_attacking = True

    def cancel_cast(self, reason: str = "") -> None:
        if self.casting:
            self.casting = None
            self.p.rig.play("release", 0.2)
            events.emit("cast_stop", reason=reason)
            if reason:
                events.emit("message", text=reason, color=RED)

    def pushback(self) -> None:
        if self.casting:
            self.casting["t"] = max(0.0, self.casting["t"] - 0.35)

    def update(self, dt: float) -> None:
        for k in list(self.cooldowns):
            self.cooldowns[k] -= dt
            if self.cooldowns[k] <= 0:
                del self.cooldowns[k]
        self.gcd = max(0.0, self.gcd - dt)
        c = self.casting
        if c:
            c["t"] += dt
            t = c["target"]
            if t is not None and (t.dead and c["data"]["type"] != "heal"):
                self.cancel_cast("Target died")
                return
            if c["t"] >= c["dur"]:
                d = c["data"]
                self.casting = None
                events.emit("cast_stop", reason="")
                p = self.p
                if t is not None and d.get("range") and isinstance(d["range"], (int, float)) and \
                        p.distance_to(t) > d["range"] + 3:
                    events.emit("message", text="Out of range.", color=RED)
                    p.rig.play("release", 0.2)
                    return
                if not p.spend(d.get("cost", 0)):
                    events.emit("message", text="Not enough mana.", color=RED)
                    return
                p.rig.play("release", 0.35)
                self._execute(d, t)
                if d.get("cooldown"):
                    self.cooldowns[d["id"]] = float(d["cooldown"])
                if t is not None and not t.dead and p.is_hostile_to(t):
                    p.auto_attacking = True

    # ----------------------------------------------------------------- effects
    def _spell_damage(self, d: dict[str, Any], mult: float = 1.0) -> tuple[float, bool]:
        base = random.uniform(d.get("min", 0), d.get("max", 0)) + self.p.spell_power() * d.get("coef", 0.0)
        res = roll_spell(self.p.level, self.p.target.level if self.p.target else self.p.level,
                         self.p.stats.spell_crit_chance())
        crit = res == "crit"
        return base * mult * (1.5 if crit else 1.0), crit

    def _execute(self, d: dict[str, Any], t: Unit | None) -> None:
        p = self.p
        g = self.game
        kind = d["type"]
        events.emit("ability_used", ability=d["id"])
        if kind == "weapon_strike":
            p.rig.play("attack", 0.45)
            res = roll_attack(p.level, t.level, p.crit_chance())
            dmg = p.weapon_damage(normalized=True) + d.get("bonus", 0)
            events.emit("sound", name="swing")
            g.pending(0.15, lambda: self._strike(t, dmg, res, d["name"]))
        elif kind == "charge":
            def arrive(t=t, d=d) -> None:
                if t.dead:
                    return
                t.add_aura(Aura("stun", "Stunned", d.get("stun", 1.0), p, mods={"stun": 1}, icon="stun"))
                p.gain_rage(d.get("rage_gain", 12))
                if hasattr(t, "add_threat"):
                    t.add_threat(p, 30)
                g.fx.dust_puff(t.x, t.y, t.z, 10)
                events.emit("sound", name="hit")
                p.auto_attacking = True
                p.swing_timer = 0.0
            p.charge = {"target": t, "time": 0.0, "on_arrive": arrive}
            events.emit("sound", name="charge")
        elif kind == "bleed":
            p.rig.play("attack2", 0.4)
            dur = float(d.get("duration", 12))
            ticks = dur / 3.0
            t.add_aura(Aura("bleed", d["name"], dur, p, tick=3.0, tick_damage=d["total"] / ticks,
                            school="physical", icon="claw"))
            if hasattr(t, "add_threat"):
                t.add_threat(p, 20)
            g.fx.hit(t, False, "blood")
            events.emit("sound", name="hit")
        elif kind == "stomp":
            p.rig.play("stomp", 0.5)
            r = float(d.get("radius", 8))
            g.fx.shockwave(p.x, p.y, p.z, r)
            events.emit("sound", name="stomp")
            for e in g.enemies.living_near(p.x, p.z, r + 1.0):
                if e.passive and e.type_id != "training_dummy":
                    continue
                dmg = random.uniform(d["min"], d["max"]) + p.attack_power() * 0.1
                e.take_damage(dmg, p, kind="melee", ability=d["name"])
                e.add_aura(Aura("slow", "Quaked", d.get("slow_time", 6), p, mods={"slow": d.get("slow_pct", 40) / 100}, icon="slow"))
        elif kind == "self_buff_heal":
            p.rig.play("roar", 0.8)
            p.heal(p.max_hp * d.get("heal_pct", 25) / 100.0, p)
            p.add_aura(Aura("undying", d["name"], d.get("duration", 10), p, debuff=False,
                            mods={"dr": d.get("dr_pct", 20) / 100.0}, icon="roar"))
            g.fx.heal(p)
            g.fx.shockwave(p.x, p.y, p.z, 5.0, (1.0, 0.8, 0.3, 0.8))
            events.emit("sound", name="roar")
        elif kind in ("ranged_shot", "dot_shot", "slow_shot"):
            p.rig.play("shoot", 0.5)
            events.emit("sound", name="bow")
            proj = "venom" if kind == "dot_shot" else "arrow"
            res = roll_attack(p.level, t.level, p.crit_chance(), can_dodge=False)
            dmg = (p.weapon_damage(normalized=True) + d.get("bonus", 0)) if kind != "dot_shot" else 0.0
            g.fx.projectile(p, t, proj, lambda: self._shot_hit(t, d, dmg, res))
        elif kind == "ground_barrage":
            p.rig.play("shoot", 0.6)
            cx, cz = t.x, t.z
            r = float(d.get("radius", 7))
            events.emit("sound", name="bow")
            for w in range(int(d.get("waves", 3))):
                g.pending(0.35 + w * 0.8, lambda cx=cx, cz=cz, r=r: self._barrage_wave(cx, cz, r, d))
        elif kind == "summon":
            p.rig.play("roar", 0.8)
            g.companions.summon_hyena(p, d)
            events.emit("sound", name="summon")
        elif kind == "spell_bolt":
            dmg, crit = self._spell_damage(d)
            g.fx.lightning(p, t)
            events.emit("sound", name="lightning")
            t.take_damage(dmg, p, school=d.get("school", "nature"), crit=crit, kind="spell", ability=d["name"])
        elif kind == "spell_dot":
            p.rig.play("cast", 0.4)
            events.emit("sound", name="fire")

            def hit(t=t, d=d) -> None:
                if t.dead:
                    return
                dmg, crit = self._spell_damage({"min": d["hit"], "max": d["hit"] * 1.15, "coef": d.get("coef", 0.4)})
                t.take_damage(dmg, p, school="fire", crit=crit, kind="spell", ability=d["name"])
                if not t.dead:
                    dur = float(d.get("duration", 12))
                    t.add_aura(Aura("brand", d["name"], dur, p, tick=3.0, tick_damage=d["total"] / (dur / 3.0) + p.spell_power() * 0.05,
                                    school="fire", icon="flame"))
            g.fx.projectile(p, t, "ember", hit)
        elif kind == "heal":
            amt, crit = self._spell_damage(d)
            p.heal(amt, p, crit=crit)
            g.fx.heal(p)
            events.emit("sound", name="heal")
        elif kind == "totem":
            g.companions.plant_totem(p, d)
            events.emit("sound", name="summon")
        elif kind == "chain":
            events.emit("sound", name="lightning")
            dmg, crit = self._spell_damage(d)
            hit_list = [t]
            src: Unit = p
            cur = t
            mult = 1.0
            for j in range(int(d.get("jumps", 2)) + 1):
                g.fx.lightning(src, cur)
                cur.take_damage(dmg * mult, p, school="nature", crit=crit, kind="spell", ability=d["name"])
                mult *= 0.7
                nxt = None
                best = 12.0
                for e in g.enemies.living_near(cur.x, cur.z, 12.0):
                    if e in hit_list or e.passive:
                        continue
                    dd = e.distance_to(cur)
                    if dd < best:
                        best, nxt = dd, e
                if nxt is None:
                    break
                hit_list.append(nxt)
                src, cur = cur, nxt

    def _strike(self, t: Unit, dmg: float, res: str, name: str) -> None:
        p = self.p
        if t.dead or p.dead:
            return
        if res in ("miss", "dodge"):
            t.notify_miss(p, res)
            return
        crit = res == "crit"
        t.take_damage(dmg * (2.0 if crit else 1.0), p, crit=crit, kind="melee", ability=name)
        if hasattr(t, "add_threat"):
            t.add_threat(p, 15)
        self.game.fx.hit(t, crit, "blood")
        events.emit("sound", name="crit" if crit else "hit")

    def _shot_hit(self, t: Unit, d: dict[str, Any], dmg: float, res: str) -> None:
        p = self.p
        if t.dead:
            return
        if res == "miss":
            t.notify_miss(p, "miss")
            return
        crit = res == "crit"
        if d["type"] == "dot_shot":
            dur = float(d.get("duration", 12))
            t.add_aura(Aura("venom_arrow", d["name"], dur, p, tick=3.0,
                            tick_damage=d["total"] / (dur / 3.0) + p.attack_power() * 0.02, school="nature", icon="venom"))
            if hasattr(t, "add_threat"):
                t.add_threat(p, 10)
            return
        t.take_damage(dmg * (2.0 if crit else 1.0), p, crit=crit, kind="ranged", ability=d["name"])
        if d["type"] == "slow_shot" and not t.dead:
            t.add_aura(Aura("slow", "Crippled", d.get("slow_time", 8), p, mods={"slow": d.get("slow_pct", 50) / 100}, icon="slow"))
        self.game.fx.hit(t, crit, "spark")

    def _barrage_wave(self, cx: float, cz: float, r: float, d: dict[str, Any]) -> None:
        g = self.game
        p = self.p
        g.fx.arrow_rain(cx, cz, r)
        for e in g.enemies.living_near(cx, cz, r + 0.5):
            if e.passive and e.type_id != "training_dummy":
                continue
            dmg = random.uniform(d["min"], d["max"]) + p.attack_power() * 0.05
            e.take_damage(dmg, p, kind="ranged", ability=d["name"])

    # ----------------------------------------------------------------- save
    def to_dict(self) -> dict[str, Any]:
        return {"known": dict(self.known)}

    def load_dict(self, d: dict[str, Any]) -> None:
        self.known = {k: int(v) for k, v in d.get("known", {}).items() if k in self.defs}
