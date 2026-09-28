"""Scripted smoke tests: drive the game for a few seconds, take screenshots, log checks, quit.

Run with ``python main.py --autotest m1`` (see SCRIPTS below). Screenshots go to screenshots/autotest.
"""
from __future__ import annotations

import json
import traceback
from typing import Any, Callable

from panda3d.core import Filename
from ursina import application, held_keys

from settings import SCREENSHOT_DIR

Step = tuple


class AutoTest:
    """Executes a list of timed steps against the running game."""

    def __init__(self, game, name: str) -> None:
        self.game = game
        self.name = name
        self.steps: list[Step] = list(SCRIPTS[name](game))
        self.t = 0.0
        self.next_at = 0.0
        self.log: list[str] = []
        self.out = SCREENSHOT_DIR / "autotest"
        self.out.mkdir(parents=True, exist_ok=True)
        self.released: list[tuple[float, str]] = []
        self.failures = 0

    def say(self, msg: str) -> None:
        print(f"[autotest] {msg}", flush=True)
        self.log.append(msg)

    def update(self, dt: float) -> None:
        self.t += dt
        for at, key in list(self.released):
            if self.t >= at:
                held_keys[key] = 0
                self.released.remove((at, key))
        while self.steps and self.t >= self.next_at:
            step = self.steps.pop(0)
            try:
                self._run(step)
            except Exception:
                self.failures += 1
                self.say("STEP FAILED " + repr(step[:1]) + "\n" + traceback.format_exc())

    def _run(self, step: Step) -> None:
        g = self.game
        op = step[0]
        if op == "wait":
            self.next_at = self.t + step[1]
        elif op == "until":
            # ("until", predicate, timeout): re-check every 0.25s until true or timed out
            pred, timeout = step[1], step[2]
            start = getattr(self, "_until_start", None)
            if start is None:
                self._until_start = self.t
                start = self.t
            if not pred(g) and self.t - start < timeout:
                self.steps.insert(0, step)
                self.next_at = self.t + 0.25
            else:
                self._until_start = None
        elif op == "time":
            g.world.env.hour = float(step[1])
        elif op == "tp":
            x, z = step[1], step[2]
            yaw = step[3] if len(step) > 3 else g.player.yaw
            g.player.teleport(x, z, yaw)
            g.cam.yaw = yaw
            if len(step) > 4:
                g.cam.pitch = step[4]
            if len(step) > 5:
                g.cam.target_distance = g.cam.distance = g.cam.current_distance = step[5]
        elif op == "cam":
            g.cam.yaw, g.cam.pitch = step[1], step[2]
            if len(step) > 3:
                g.cam.target_distance = g.cam.distance = g.cam.current_distance = step[3]
        elif op == "shot":
            path = self.out / f"{step[1]}.png"
            application.base.win.saveScreenshot(Filename.fromOsSpecific(str(path)))
            self.say(f"screenshot {path.name}")
        elif op == "hold":
            held_keys[step[1]] = 1
            self.released.append((self.t + step[2], step[1]))
        elif op == "press":
            from ursina.main import keyboard_keys
            key = step[1]
            if len(key) == 1 and key in keyboard_keys:
                g.app.input(key, is_raw=True)
            else:
                g.app.input(key)
        elif op == "call":
            result = step[1](g)
            if result is not None:
                self.say(f"{step[2] if len(step) > 2 else 'call'}: {result}")
        elif op == "check":
            ok = bool(step[1](g))
            if not ok:
                self.failures += 1
            self.say(f"CHECK {'OK ' if ok else 'FAIL'} {step[2]}")
        elif op == "fps":
            self.say(f"avg fps: {g.average_fps():.1f}")
        elif op == "quit":
            self.say(f"finished with {self.failures} failure(s)")
            (self.out / f"{self.name}_log.json").write_text(json.dumps(self.log, indent=1), encoding="utf-8")
            application.quit()
        else:
            raise ValueError(f"unknown step {op}")


def _perf(g) -> list[Step]:
    return [("wait", 2.0), ("tp", -10, -80, 0, 18, 12), ("time", 12.0), ("wait", 6.0), ("fps",), ("quit",)]


def _perfdead(g) -> list[Step]:
    return [("wait", 2.0), ("tp", 0, 318, 0, 12, 18), ("wait", 3.0), ("call", lambda g: (g.player.dead, g.state), "state"),
            ("wait", 5.0), ("fps",), ("shot", "perf_dead"), ("quit",)]


def _dbg(g) -> list[Step]:
    def dump(g):
        out = []
        for pl in g.hud.nameplates.plates:
            if pl.enabled and pl.unit is None:
                pass
        for i, pl in enumerate(g.hud.nameplates.plates):
            if pl.enabled:
                out.append((pl.name_text.text, repr(pl.title_text.text), repr(pl.marker.text), pl.title_text.use_tags,
                            [tn.node().getText() for tn in pl.marker.text_nodes], [tn.node().getText() for tn in pl.title_text.text_nodes]))
        return out
    return [("wait", 1.5), ("tp", -186, -268, 220, 16, 10), ("wait", 0.5), ("call", dump, "plates"), ("quit",)]


def _m1(g) -> list[Step]:
    return [
        ("wait", 1.5),
        ("time", 9.5), ("cam", 40, 16, 11), ("wait", 0.6), ("shot", "m1_01_ashfang_start"),
        ("call", lambda g: (round(g.player.x, 1), round(g.player.y, 2), round(g.player.z, 1)), "player pos"),
        ("hold", "w", 2.0), ("wait", 2.2),
        ("call", lambda g: (round(g.player.x, 1), round(g.player.z, 1), round(g.player.motor.last_speed, 2)), "after walking"),
        ("check", lambda g: abs(g.player.x - (-168)) + abs(g.player.z - (-250)) > 5, "player moved with W"),
        ("press", "space"), ("wait", 0.25),
        ("check", lambda g: not g.player.motor.grounded, "player airborne after jump"),
        ("wait", 1.0), ("check", lambda g: g.player.motor.grounded, "player landed"),
        ("tp", -20, -110, 10, 14, 13), ("time", 13), ("wait", 0.8), ("shot", "m1_02_redtusk_noon"),
        ("tp", 205, -258, 80, 12, 14), ("wait", 0.8), ("shot", "m1_03_saltroot_sandbar"),
        ("tp", 190, -252, 90, 10, 12), ("wait", 0.5), ("hold", "w", 3.0), ("wait", 3.2),
        ("call", lambda g: (round(g.player.x, 1), round(g.player.y, 2), g.player.motor.swimming), "wade/swim"),
        ("tp", 175, 60, 70, 8, 12), ("time", 18.6), ("wait", 0.8), ("shot", "m1_04_coast_dusk"),
        ("tp", -10, -96, 0, 12, 12), ("time", 23.0), ("wait", 0.8), ("shot", "m1_05_redtusk_night"),
        ("tp", 0, 280, 0, 8, 16), ("time", 10.5), ("wait", 0.8), ("shot", "m1_06_ironmaw_gate"),
        ("tp", -90, 158, 300, 14, 12), ("time", 15.0), ("wait", 0.8), ("shot", "m1_07_scorchspine_pass"),
        ("tp", -200, 214, 300, 10, 10), ("wait", 0.8), ("shot", "m1_08_mine_entrance"),
        ("tp", 60, -40, 0, 55, 32), ("wait", 0.8), ("shot", "m1_09_overview"),
        ("tp", -60, -150, 45, 18, 12), ("time", 7.0), ("wait", 2.0), ("fps",), ("shot", "m1_10_morning_plains"),
        ("tp", -160, -250, 200, 35, 5), ("time", 12.0), ("wait", 0.5), ("shot", "m1_11_player_closeup"),
        ("quit",),
    ]


def _approach(g, dist: float = 2.2) -> None:
    t = g.targeting.target
    p = g.player
    import math as _m
    dx, dz = p.x - t.x, p.z - t.z
    d = _m.hypot(dx, dz) or 1.0
    p.teleport(t.x + dx / d * (t.radius + dist), t.z + dz / d * (t.radius + dist))
    p.face_towards(t.x, t.z)
    g.cam.yaw = p.yaw


def _m2(g) -> list[Step]:
    state: dict = {}

    def kill_check(g):
        t = state.get("boar")
        return t is not None and t.dead

    return [
        ("wait", 1.5), ("time", 10.0),
        ("tp", -163, -228, 0, 18, 12), ("wait", 0.5),
        ("press", "tab"), ("wait", 0.2),
        ("check", lambda g: g.targeting.target is not None and g.targeting.target.type_id == "desert_boar", "tab targets a boar"),
        ("call", lambda g: state.update(boar=g.targeting.target, xp0=g.player.xp.xp) or g.targeting.target.name, "target"),
        ("call", lambda g: _approach(g)), ("call", lambda g: setattr(g.player, "auto_attacking", True)),
        ("wait", 1.6), ("shot", "m2_01_fighting"),
        ("call", lambda g: (g.player.hp, g.player.max_hp, round(state["boar"].hp), state["boar"].max_hp), "hp player/boar"),
        ("wait", 12.0),
        ("check", kill_check, "boar killed by auto-attack"),
        ("check", lambda g: g.player.xp.xp > state["xp0"], "xp gained from kill"),
        ("call", lambda g: (g.player.xp.xp, g.player.level), "xp/level"),
        ("call", lambda g: g.interact_with(state["boar"])), ("wait", 0.4), ("shot", "m2_02_loot_window"),
        ("call", lambda g: state["boar"].loot, "loot"),
        ("call", lambda g: g.hud.loot.take_all()), ("wait", 0.2),
        ("call", lambda g: (g.player.inventory.gold, [s for s in g.player.inventory.slots if s]), "bags"),
        ("call", lambda g: setattr(state["boar"], "corpse_timer", 0.01)), ("wait", 0.3),
        ("call", lambda g: setattr(state["boar"], "respawn_timer", 0.3)), ("wait", 0.8),
        ("check", lambda g: state["boar"].state in ("idle", "combat") and not state["boar"].dead, "boar respawned"),
        # aggro + leash
        ("tp", -84, -146, 45, 25, 16), ("wait", 1.5),
        ("call", lambda g: [e.name for e in g.enemies.enemies_near(g.player.x, g.player.z, 40) if e.state == "combat"], "aggroed"),
        ("shot", "m2_03_aggro"),
        ("tp", -10, -80, 0, 18, 12), ("wait", 14.0),
        ("check", lambda g: all(e.state != "combat" for e in g.enemies.enemies_near(-84, -146, 60)), "enemies leashed after running away"),
        # player death + release
        ("call", lambda g: g.player.take_damage(99999, None, kind="true")), ("wait", 2.0), ("shot", "m2_04_dead"),
        ("check", lambda g: g.player.dead and g.hud.death.enabled, "death screen shown"),
        ("call", lambda g: g.hud.death.release()), ("wait", 0.5),
        ("check", lambda g: not g.player.dead and g.state == "playing", "player revived"),
        ("call", lambda g: (round(g.player.x), round(g.player.z), round(g.player.hp)), "respawned at"),
        ("tp", -155, -240, 250, 14, 9), ("time", 17.5), ("wait", 0.2), ("press", "tab"), ("wait", 0.2),
        ("call", lambda g: _approach(g, 1.8)), ("call", lambda g: setattr(g.player, "auto_attacking", True)),
        ("wait", 3.0), ("shot", "m2_05_dummy"),
        ("fps",), ("quit",),
    ]


def _m3(g) -> list[Step]:
    st: dict = {}

    def learn_all(g):
        for aid in g.abilities.order:
            g.abilities.learn(aid, 1)

    def show_tooltip(g):
        from ui.widgets import Tooltip
        from items import item as I
        p = g.player
        lines = I.tooltip_lines("hollowforged_cleaver", p, p.equipment.get("weapon"))
        Tooltip.get().show(lines)
        Tooltip.get().position = (0.05, 0.1, -5)

    return [
        ("wait", 1.5), ("time", 11.0), ("call", learn_all),
        ("tp", -115, -175, 20, 16, 11), ("wait", 0.3), ("press", "tab"), ("wait", 0.2),
        ("call", lambda g: _approach(g, 1.6)),
        ("call", lambda g: st.update(r0=g.player.resource) or g.player.resource, "rage before"),
        ("call", lambda g: setattr(g.player, "resource", 50.0)),
        ("press", "1"), ("wait", 0.6),
        ("check", lambda g: g.abilities.cooldowns.get("brutal_strike", 0) > 0, "Savage Chop went on cooldown"),
        ("check", lambda g: g.targeting.target.hp < g.targeting.target.max_hp or g.hud.floating.live, "Savage Chop hit (or missed visibly)"),
        ("shot", "m3_01_brutal_strike"),
        ("call", lambda g: st.update(str0=g.player.stats.strength, sta0=g.player.stats.stamina, hp0=g.player.max_hp) or
         (g.player.stats.strength, g.player.stats.stamina, g.player.max_hp), "stats L1"),
        ("call", lambda g: g.player.gain_xp(400, "test")), ("wait", 0.5), ("shot", "m3_02_level_up"),
        ("check", lambda g: g.player.level == 2, "reached level 2"),
        ("check", lambda g: g.player.stats.strength == st["str0"] + 3 and g.player.stats.stamina == st["sta0"] + 3,
         "warrior gained +3 str/+3 sta"),
        ("check", lambda g: g.player.max_hp > st["hp0"] and g.player.hp >= g.player.max_hp * 0.9, "max HP up and full heal"),
        ("call", lambda g: g.player.inventory.add("hollowforged_cleaver")),
        ("call", lambda g: g.player.inventory.add("tattered_leather_cap")),
        ("call", lambda g: g.player.inventory.add("minor_healing_draught", 3)),
        ("press", "b"), ("press", "c"), ("wait", 0.3), ("call", show_tooltip), ("wait", 0.3),
        ("shot", "m3_03_bags_character_tooltip"),
        ("call", lambda g: st.update(arm0=g.player.armor) or g.player.armor, "armor before helm"),
        ("call", lambda g: g.player.use_bag_item(next(i for i, s in enumerate(g.player.inventory.slots) if s and s["id"] == "tattered_leather_cap"))),
        ("check", lambda g: g.player.equipment.get("head") == "tattered_leather_cap" and g.player.armor > st["arm0"], "cap equipped, armor up"),
        ("call", lambda g: g.player.use_bag_item(next(i for i, s in enumerate(g.player.inventory.slots) if s and s["id"] == "hollowforged_cleaver"))),
        ("check", lambda g: g.player.equipment.get("weapon") == "hollowforged_cleaver", "cleaver equipped"),
        ("check", lambda g: any(s and s["id"] == "worn_hand_axe" for s in g.player.inventory.slots), "old axe back in bags"),
        ("call", lambda g: __import__("ui.widgets", fromlist=["Tooltip"]).Tooltip.get().hide()),
        ("wait", 0.3), ("shot", "m3_04_equipped"),
        ("press", "b"), ("press", "c"),
        ("call", lambda g: g.player.gain_xp(4000, "test")), ("wait", 0.3),
        ("call", lambda g: (g.player.level, int(g.player.max_hp), g.player.stats.strength), "level/hp/str after xp"),
        ("tp", 30, -40, 0, 18, 13), ("wait", 0.3), ("press", "tab"), ("wait", 0.2),
        ("call", lambda g: (g.targeting.target.name, round(g.player.distance_to(g.targeting.target), 1)) if g.targeting.target else None, "rush target"),
        ("call", lambda g: _approach(g, 12.0)), ("wait", 0.1),
        ("call", lambda g: setattr(g.player, "combat_timer", 0.0)),
        ("press", "2"), ("wait", 0.6),
        ("check", lambda g: g.targeting.target is not None and g.player.distance_to(g.targeting.target) < 5, "Tusk Rush closed distance"),
        ("check", lambda g: g.targeting.target.has_aura("stun"), "target stunned"),
        ("call", lambda g: setattr(g.player, "resource", 100.0)),
        ("wait", 0.6), ("press", "3"), ("wait", 1.1), ("check", lambda g: g.targeting.target.has_aura("bleed") or g.targeting.target.dead, "bleed applied"),
        ("press", "4"), ("wait", 0.25), ("shot", "m3_05_quake_stomp"),
        ("check", lambda g: g.targeting.target.dead or g.targeting.target.has_aura("slow"), "stomp slowed"),
        ("call", lambda g: setattr(g.player, "hp", g.player.max_hp * 0.4)),
        ("wait", 1.2), ("press", "5"), ("wait", 0.3),
        ("check", lambda g: g.player.has_aura("undying"), "undying roar buff"),
        ("wait", 0.8), ("shot", "m3_06_hotbar_cooldowns"),
        ("fps",), ("quit",),
    ]


def _kill(g, type_ids, n: int, loot: bool = True) -> int:
    """Kill the n nearest living enemies of the given types as the player (quest credit + loot)."""
    p = g.player
    if isinstance(type_ids, str):
        type_ids = [type_ids]
    cands = [e for e in g.enemies.enemies if e.type_id in type_ids and not e.dead and e.state != "respawning"]
    cands.sort(key=lambda e: (e.x - p.x) ** 2 + (e.z - p.z) ** 2)
    k = 0
    for e in cands[:n]:
        e.tagged_by_player = True
        e.take_damage(e.hp + 10, p, kind="true")
        if loot and e.loot:
            for it in list(e.loot["items"]):
                p.inventory.add(it["id"], it.get("count", 1))
            p.inventory.add_gold(e.loot.get("gold", 0))
            e.loot = {"gold": 0, "items": []}
        k += 1
    return k


def _talk(g, npc_id: str) -> None:
    n = g.npcs.get(npc_id)
    g.player.teleport(n.x + 2.0, n.z + 2.0)
    g.player.face_towards(n.x, n.z)
    g.cam.yaw = g.player.yaw
    n.interact(g)


def _dlg_option(g, text_part: str) -> None:
    d = g.hud.dialogue
    for i, o in enumerate(d.options):
        if o.enabled and text_part in o.label.text:
            d._option(i)
            return
    raise RuntimeError(f"option {text_part!r} not found in " + str([o.label.text for o in d.options if o.enabled]))


def _m4(g) -> list[Step]:
    Q = lambda g: g.quests
    return [
        ("wait", 1.5), ("time", 10.5),
        ("check", lambda g: g.npcs.get("chieftain_brakka").quest_marker() and g.npcs.get("chieftain_brakka").quest_marker()[0] == "!",
         "Chieftain shows ! marker"),
        ("tp", -186, -268, 220, 16, 10), ("wait", 0.5), ("shot", "m4_01_markers_ashfang"),
        ("call", lambda g: _talk(g, "chieftain_brakka")), ("wait", 0.3),
        ("call", lambda g: _dlg_option(g, "Rite of the Hollow")), ("wait", 0.3), ("shot", "m4_02_quest_offer"),
        ("call", lambda g: g.hud.dialogue._button("a")), ("wait", 0.2),
        ("check", lambda g: "o1" in Q(g).active, "o1 accepted"),
        ("call", lambda g: _talk(g, "drillmaster_gorza")), ("wait", 0.3),
        ("call", lambda g: _dlg_option(g, "Rite of the Hollow")), ("wait", 0.3), ("shot", "m4_03_quest_complete"),
        ("call", lambda g: g.hud.dialogue._button("a")), ("wait", 0.2),
        ("check", lambda g: "o1" in Q(g).done, "o1 turned in"),
        ("check", lambda g: g.hud.dialogue.mode == "offer" and g.hud.dialogue.qid == "o2", "o2 offered next"),
        ("call", lambda g: g.hud.dialogue._button("a")), ("call", lambda g: g.hud.dialogue.close()),
        ("call", lambda g: _kill(g, "desert_boar", 6), "boars killed"), ("wait", 0.3),
        ("check", lambda g: Q(g).is_complete("o2"), "o2 objectives complete"),
        ("call", lambda g: _talk(g, "mother_ruska")), ("call", lambda g: _dlg_option(g, "Stinger Venom")),
        ("call", lambda g: g.hud.dialogue._button("a")), ("call", lambda g: g.hud.dialogue.close()),
        ("press", "l"), ("wait", 0.3), ("shot", "m4_04_questlog_tracker"), ("press", "l"),
        ("call", lambda g: _kill(g, "sand_scorpion", 7), "scorpions killed"),
        ("call", lambda g: [_kill(g, "sand_scorpion", 3) for _ in range(3)] and None),
        ("call", lambda g: g.player.inventory.count("venom_sac"), "venom sacs"),
        ("check", lambda g: Q(g).is_complete("o3"), "o3 objectives complete"),
        ("call", lambda g: _talk(g, "drillmaster_gorza")), ("call", lambda g: _dlg_option(g, "Tusks and Hide")),
        ("call", lambda g: g.hud.dialogue._button("a")), ("call", lambda g: g.hud.dialogue.close()),
        ("check", lambda g: g.player.inventory.count("hollowforged_cleaver") == 1, "o2 reward received"),
        ("call", lambda g: _talk(g, "mother_ruska")), ("call", lambda g: _dlg_option(g, "Stinger Venom")),
        ("call", lambda g: g.hud.dialogue._button("a")), ("call", lambda g: g.hud.dialogue.close()),
        ("call", lambda g: _talk(g, "chieftain_brakka")), ("call", lambda g: _dlg_option(g, "Word to Redtusk")),
        ("call", lambda g: g.hud.dialogue._button("a")), ("call", lambda g: g.hud.dialogue.close()),
        ("check", lambda g: g.player.inventory.count("clan_message") == 1, "message item given"),
        ("call", lambda g: (g.player.level, g.player.xp.xp), "level/xp after start zone"),
        ("tp", -10, -92, 0, 14, 14), ("wait", 0.8), ("shot", "m4_05_redtusk_markers"),
        ("call", lambda g: _talk(g, "overseer_kazreth")), ("call", lambda g: _dlg_option(g, "Word to Redtusk")),
        ("call", lambda g: g.hud.dialogue._button("a")), ("wait", 0.3),
        ("check", lambda g: "o4" in Q(g).done and g.player.inventory.count("clan_message") == 0, "o4 delivered"),
        ("call", lambda g: g.hud.dialogue.show_greeting()), ("wait", 0.2), ("shot", "m4_06_kazreth_offers"),
        ("call", lambda g: _dlg_option(g, "The Trainer's Call")), ("call", lambda g: g.hud.dialogue._button("a")),
        ("call", lambda g: _dlg_option(g, "Wings of Ill Omen")), ("call", lambda g: g.hud.dialogue._button("a")),
        ("call", lambda g: g.hud.dialogue.close()),
        ("call", lambda g: g.player.inventory.add_gold(40)),
        ("call", lambda g: _talk(g, "warmaster_drogan")), ("call", lambda g: _dlg_option(g, "Trainer's Call")),
        ("call", lambda g: g.hud.dialogue._button("a")), ("call", lambda g: _dlg_option(g, "Train me")), ("wait", 0.3),
        ("check", lambda g: "r0" in Q(g).done, "trainer quest done"),
        ("shot", "m4_07_trainer"),
        ("call", lambda g: g.hud.trainer.learn(1)), ("wait", 0.2),
        ("check", lambda g: "tusk_rush" in g.abilities.known, "learned Tusk Rush at trainer"),
        ("call", lambda g: g.hud.trainer.close()),
        ("call", lambda g: _talk(g, "quartermaster_hesk")), ("call", lambda g: _dlg_option(g, "browse")), ("wait", 0.3),
        ("call", lambda g: st_gold.update(g=g.player.inventory.gold)),
        ("call", lambda g: g.hud.vendor.buy(7)), ("wait", 0.2),
        ("check", lambda g: g.player.inventory.gold < st_gold["g"], "bought an item"),
        ("call", lambda g: g.hud.vendor.sell_from_bag(next(i for i, s in enumerate(g.player.inventory.slots) if s and s["id"] == "worn_hand_axe")) if any(s and s["id"] == "worn_hand_axe" for s in g.player.inventory.slots) else None),
        ("wait", 0.3), ("shot", "m4_08_vendor"),
        ("call", lambda g: g.hud.vendor.close()), ("call", lambda g: g.hud.bags.close()),
        ("call", lambda g: _talk(g, "innkeeper_oshra")), ("wait", 0.4), ("shot", "m4_09_inn"),
        ("call", lambda g: g.hud.dialogue.close()),
        ("fps",), ("quit",),
    ]


st_gold: dict = {}


def _level_to(g, lvl: int) -> None:
    from progression.leveling import xp_to_next
    p = g.player
    while p.level < lvl:
        p.gain_xp(xp_to_next(p.level) - p.xp.xp, "test")


def _learn_all(g) -> None:
    for aid in g.abilities.order:
        g.abilities.learn(aid, len(g.abilities.ranks(aid)) if g.player.level >= 10 else 1)


def _near_enemy(g, type_id: str, dist: float = 14.0, pitch: float = 16, cam_d: float = 9) -> Any:
    p = g.player
    cands = [e for e in g.enemies.enemies if e.type_id == type_id and not e.dead and e.state != "respawning"]
    cands.sort(key=lambda e: (e.x - p.x) ** 2 + (e.z - p.z) ** 2)
    e = cands[0]
    import math as _m
    a = _m.radians(e.home_yaw + 180 if not e.flying else 30)
    x, z = e.x + _m.sin(a) * dist, e.z + _m.cos(a) * dist
    p.teleport(x, z)
    p.face_towards(e.x, e.z)
    g.cam.yaw, g.cam.pitch = p.yaw, pitch
    g.cam.target_distance = g.cam.distance = g.cam.current_distance = cam_d
    g.targeting.set_target(e)
    return e


def _portrait(g, type_id: str, dist: float) -> str:
    """Point the camera at the nearest enemy of a type (front view), with the player hidden."""
    from panda3d.core import Vec3 as _V
    import math as _m
    p = g.player
    cands = [e for e in g.enemies.enemies if e.type_id == type_id and not e.dead and e.state != "respawning"]
    cands.sort(key=lambda e: (e.x - p.x) ** 2 + (e.z - p.z) ** 2)
    e = cands[0]
    p.teleport(e.x + 60, e.z + 60)
    e.state = "idle"
    e.wander_target = None
    e.wander_timer = 99
    a = _m.radians(e.yaw + 25)
    h = e.height
    cy = e.y + h * 0.55
    cam = _V(e.x + _m.sin(a) * dist, cy + dist * 0.3, e.z + _m.cos(a) * dist)
    g.cam_override = (cam, _V(e.x, cy, e.z))
    g.player.rig.root.hide()
    return f"{e.name} L{e.level} hp={int(e.max_hp)}"


def _gallery(g) -> list[Step]:
    steps: list[Step] = [("wait", 1.5), ("time", 12.0), ("call", lambda g: setattr(g.player, "targetable", False))]
    for tid, d in [("desert_boar", 4.5), ("sand_scorpion", 4.5), ("cliff_lizard", 4.5), ("brinepincer_crab", 4.5),
                   ("smuggler_cutthroat", 4.0), ("smuggler_sharpshooter", 4.0), ("captain_saltjaw", 4.5), ("ridge_scorpion", 5.5),
                   ("ridge_lizard", 5.5), ("dustfang_raider", 4.0), ("tunnel_goblin", 3.5), ("warlord_rukhar", 6.0),
                   ("dune_vulture", 8.0), ("training_dummy", 4.0)]:
        steps += [("call", lambda g, tid=tid, d=d: _portrait(g, tid, d)), ("wait", 0.5), ("shot", f"m5_gallery_{tid}")]
    steps += [("call", lambda g: setattr(g, "cam_override", None)), ("quit",)]
    return steps


def _hunter(g) -> list[Step]:
    return [
        ("wait", 1.0), ("call", lambda g: g.spawn_player("troll", "hunter", "Zenji")), ("wait", 0.5), ("time", 11.0),
        ("call", lambda g: _level_to(g, 10)), ("call", _learn_all),
        ("call", lambda g: _near_enemy(g, "desert_boar", 22).name, "target"),
        ("call", lambda g: setattr(g.player, "auto_attacking", True)), ("wait", 2.8), ("shot", "m5_hunter_01_autoshot"),
        ("check", lambda g: g.targeting.target.hp < g.targeting.target.max_hp, "auto-shot hits at range"),
        ("press", "1"), ("wait", 1.2), ("press", "2"), ("wait", 1.2), ("press", "3"), ("wait", 0.8),
        ("check", lambda g: g.targeting.target.dead or g.targeting.target.has_aura("slow"), "crippling shot slowed"),
        ("call", lambda g: _near_enemy(g, "dune_vulture", 18).name, "target"), ("wait", 1.2),
        ("press", "4"), ("wait", 0.5), ("shot", "m5_hunter_02_arrow_storm"), ("wait", 2.0),
        ("press", "5"), ("wait", 1.5), ("shot", "m5_hunter_03_hyena"),
        ("check", lambda g: len(g.companions.units) == 1, "hyena summoned"),
        ("wait", 5.0), ("fps",), ("quit",),
    ]


def _shaman(g) -> list[Step]:
    return [
        ("wait", 1.0), ("call", lambda g: g.spawn_player("orc", "shaman", "Ogra")), ("wait", 0.5), ("time", 16.0),
        ("call", lambda g: _level_to(g, 10)), ("call", _learn_all),
        ("call", lambda g: _near_enemy(g, "sand_scorpion", 18).name, "target"),
        ("press", "1"), ("wait", 0.8), ("shot", "m5_shaman_01_casting"),
        ("check", lambda g: g.abilities.casting is not None, "lightning lash is casting"),
        ("wait", 1.4), ("check", lambda g: g.targeting.target.dead or g.targeting.target.hp < g.targeting.target.max_hp, "lightning hit"),
        ("call", lambda g: _near_enemy(g, "sand_scorpion", 18).name, "target"),
        ("press", "2"), ("wait", 1.0),
        ("check", lambda g: g.targeting.target.dead or g.targeting.target.has_aura("brand"), "searing brand dot"),
        ("press", "4"), ("wait", 0.3),
        ("check", lambda g: len(g.companions.units) == 1, "ember totem placed"),
        ("wait", 2.5), ("shot", "m5_shaman_02_totem"),
        ("call", lambda g: setattr(g.player, "hp", g.player.max_hp * 0.4)), ("call", lambda g: st5.update(hp=g.player.hp)),
        ("press", "3"), ("wait", 2.6),
        ("check", lambda g: g.player.hp > st5["hp"] + 30, "tidal mend healed"),
        ("call", lambda g: _near_enemy(g, "desert_boar", 20).name, "chain target"),
        ("press", "5"), ("wait", 2.0), ("shot", "m5_shaman_03_chain"),
        ("fps",), ("quit",),
    ]


st5: dict = {}


def _troll(g) -> list[Step]:
    def collect_driftwood(g):
        n = 0
        for o in g.interactables.objects:
            if getattr(o, "id", "") == "driftwood" and o.available and n < 5:
                g.player.teleport(o.x + 1.2, o.z + 1.2)
                o.interact(g)
                n += 1
        return n
    return [
        ("wait", 1.0), ("call", lambda g: g.spawn_player("troll", "warrior", "Tzaka")), ("wait", 0.5), ("time", 9.0),
        ("cam", 300, 14, 11), ("wait", 0.8), ("shot", "m5_troll_01_start"),
        ("call", lambda g: _talk(g, "elder_wazuko")), ("call", lambda g: _dlg_option(g, "Tide-Touched")),
        ("call", lambda g: g.hud.dialogue._button("a")), ("call", lambda g: g.hud.dialogue.close()),
        ("call", lambda g: _talk(g, "spearmaster_koru")), ("call", lambda g: _dlg_option(g, "Tide-Touched")),
        ("call", lambda g: g.hud.dialogue._button("a")), ("call", lambda g: g.hud.dialogue._button("a")),
        ("call", lambda g: g.hud.dialogue.close()),
        ("call", lambda g: _talk(g, "tidecaller_nyassa")), ("call", lambda g: _dlg_option(g, "Driftwood")),
        ("call", lambda g: g.hud.dialogue._button("a")), ("call", lambda g: g.hud.dialogue.close()),
        ("check", lambda g: "t2" in g.quests.active and "t3" in g.quests.active, "t2 and t3 accepted"),
        ("call", lambda g: _near_obj(g)), ("wait", 0.6), ("shot", "m5_troll_02_driftwood"),
        ("call", collect_driftwood, "driftwood picked"),
        ("check", lambda g: g.quests.is_complete("t3"), "driftwood quest complete"),
        ("call", lambda g: _kill(g, "brinepincer_crab", 6), "crabs"),
        ("check", lambda g: g.quests.is_complete("t2"), "crab quest complete"),
        ("call", lambda g: _talk(g, "spearmaster_koru")), ("call", lambda g: _dlg_option(g, "Pincers")),
        ("call", lambda g: g.hud.dialogue._button("a")), ("call", lambda g: g.hud.dialogue.close()),
        ("call", lambda g: _talk(g, "tidecaller_nyassa")), ("call", lambda g: _dlg_option(g, "Driftwood")),
        ("call", lambda g: g.hud.dialogue._button("a")), ("call", lambda g: g.hud.dialogue.close()),
        ("call", lambda g: _talk(g, "elder_wazuko")), ("call", lambda g: _dlg_option(g, "Across the Shallows")),
        ("call", lambda g: g.hud.dialogue._button("a")), ("call", lambda g: g.hud.dialogue.close()),
        ("check", lambda g: g.player.inventory.count("pearl_offering") == 1, "pearl offering received"),
        ("tp", 176, -246, 250, 12, 10), ("wait", 0.8), ("shot", "m5_troll_03_sandbar"),
        ("call", lambda g: (g.player.level, g.player.xp.xp), "level after troll start"),
        ("quit",),
    ]


def _near_obj(g):
    o = next(o for o in g.interactables.objects if getattr(o, "id", "") == "driftwood" and o.available)
    g.player.teleport(o.x + 3.0, o.z + 3.0)
    g.player.face_towards(o.x, o.z)
    g.cam.yaw = g.player.yaw
    g.targeting.set_target(o)


def _durza(g):
    return g.npcs.get("durza")


def _escort(g) -> list[Step]:
    def setup(g):
        _level_to(g, 6)
        _learn_all(g)
        g.quests.done.update({"o1", "o2", "o3", "o4", "r3"})

    def follow(g):
        d = _durza(g)
        g.player.teleport(d.x + 3, d.z + 3)

    return [
        ("wait", 1.0), ("call", setup), ("time", 14.0),
        ("call", lambda g: _talk(g, "durza")), ("call", lambda g: _dlg_option(g, "Survivor")),
        ("call", lambda g: g.hud.dialogue._button("a")), ("call", lambda g: g.hud.dialogue.close()),
        ("check", lambda g: g.escort.active, "escort started"),
        ("wait", 5.0), ("shot", "m5_escort_01_walking"),
        ("call", lambda g: [(e.name, e.state, round(e.distance_to(_durza(g)), 1)) for e in g.escort.spawned], "ambushers"),
        ("call", lambda g: _kill(g, "dustfang_raider", 3, loot=False)), ("call", follow), ("wait", 8.0),
        ("call", lambda g: _kill(g, "dustfang_raider", 3, loot=False)), ("call", follow), ("wait", 8.0),
        ("call", lambda g: _kill(g, "dustfang_raider", 3, loot=False)), ("call", follow), ("wait", 8.0),
        ("call", lambda g: (round(_durza(g).x), round(_durza(g).z), g.escort.index, g.quests.active.get("r4")), "durza"),
        ("call", lambda g: _kill(g, "dustfang_raider", 3, loot=False)), ("call", follow), ("wait", 8.0),
        ("call", lambda g: _kill(g, "dustfang_raider", 3, loot=False)), ("call", follow), ("wait", 8.0),
        ("call", follow), ("wait", 10.0), ("call", follow), ("wait", 10.0), ("call", follow), ("wait", 10.0),
        ("call", lambda g: (round(_durza(g).x), round(_durza(g).z), g.quests.active.get("r4")), "durza end"),
        ("check", lambda g: g.quests.is_complete("r4"), "escort completed"),
        ("shot", "m5_escort_02_done"),
        ("quit",),
    ]


def _tp_cell(g, c: int, r: int, yaw: float = 0.0, pitch: float = 22, dist: float = 10) -> None:
    x, z = g.dungeon.tile_center(c, r)
    g.player.teleport(x, z, yaw)
    g.cam.yaw, g.cam.pitch = yaw, pitch
    g.cam.target_distance = g.cam.distance = g.cam.current_distance = dist


def _m6(g) -> list[Step]:

    def setup(g):
        _level_to(g, 10)
        _learn_all(g)
        g.quests.done.update({"o1", "o2", "o3", "o4", "r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8", "r9", "r10"})
        g.quests.accept("r11")
        for iid in ("tunnelmaw_crusher", "ember_crested_helm", "warlords_hauberk", "ironbound_greaves", "tunnelers_stompers"):
            pass
        g.player.equip("raider_waraxe") if g.player.inventory.add("raider_waraxe") else None
        g.player.inventory.add("healing_draught", 5)

    def boss_to(g, frac):
        b = g.dungeon.boss
        b.hp = b.max_hp * frac
        return round(b.hp)

    return [
        ("wait", 1.0), ("call", setup), ("time", 15.0),
        ("tp", -228, 222, 300, 14, 12), ("wait", 0.6), ("shot", "m6_01_mine_entrance"),
        ("call", lambda g: g.player.teleport(-236.3, 226.2)), ("wait", 1.5),
        ("check", lambda g: g.dungeon.inside, "entered the mine"),
        ("wait", 0.5), ("shot", "m6_02_mine_start"),
        ("call", lambda g: _tp_cell(g, 12, 31, 0, 25, 11)), ("wait", 0.8), ("shot", "m6_03_rails_hall"),
        ("call", lambda g: _tp_cell(g, 30, 21, 90, 22, 12)), ("wait", 0.8), ("shot", "m6_04_crystal_cavern"),
        ("press", "m"), ("wait", 0.4), ("shot", "m6_05_dungeon_map"), ("press", "m"),
        ("call", lambda g: _kill(g, ["tunnel_goblin", "goblin_geomancer"], 30), "goblins killed"),
        ("call", lambda g: _tp_cell(g, 28, 13, 0, 20, 13)), ("wait", 0.6),
        ("call", lambda g: g.targeting.set_target(g.dungeon.boss)),
        ("call", lambda g: _approach(g, 1.2)), ("call", lambda g: setattr(g.player, "auto_attacking", True)),
        ("call", lambda g: setattr(g.dungeon.boss, "slam_cd", 1.0)),
        ("wait", 1.8), ("shot", "m6_06_boss_slam_telegraph"),
        ("call", lambda g: (g.dungeon.boss.state, round(g.dungeon.boss.hp), g.dungeon.boss.max_hp), "boss"),
        ("wait", 2.0), ("call", lambda g: setattr(g.player, "hp", g.player.max_hp)),
        ("call", lambda g: boss_to(g, 0.48), "boss hp set"), ("wait", 1.2),
        ("check", lambda g: g.dungeon.boss.phase == 2, "boss entered phase 2"),
        ("check", lambda g: len(g.dungeon.boss.adds) == 2, "phase 2 adds summoned"),
        ("shot", "m6_07_phase2_adds"),
        ("call", lambda g: setattr(g.dungeon.boss, "burrow_cd", 0.0)), ("wait", 2.2), ("shot", "m6_08_burrow_telegraph"),
        ("call", lambda g: setattr(g.player, "hp", g.player.max_hp)),
        ("wait", 2.0), ("call", lambda g: _kill(g, ["tunnel_goblin"], 2, loot=False)),
        ("call", lambda g: setattr(g.player, "hp", g.player.max_hp)),
        ("call", lambda g: _kill(g, ["grakk"], 1)), ("wait", 0.5),
        ("check", lambda g: g.dungeon.boss.dead, "Grakk defeated"),
        ("check", lambda g: g.quests.is_complete("r11"), "r11 complete (brand looted)"),
        ("call", lambda g: [s["id"] for s in g.player.inventory.slots if s], "bags after boss"),
        ("wait", 0.5), ("shot", "m6_09_boss_dead"),
        ("call", lambda g: g.dungeon.exit(silent=True)), ("wait", 0.5),
        ("check", lambda g: not g.dungeon.inside and not g.world.underground, "left the mine"),
        ("call", lambda g: _talk(g, "outrider_tazh")), ("call", lambda g: _dlg_option(g, "Grakk")),
        ("call", lambda g: g.hud.dialogue._button("a")), ("wait", 0.2),
        ("check", lambda g: "r11" in g.quests.done and g.hud.dialogue.qid == "r12", "r11 done, r12 offered"),
        ("call", lambda g: g.hud.dialogue._button("a")), ("call", lambda g: g.hud.dialogue.close()),
        ("press", "m"), ("wait", 0.4), ("shot", "m6_10_world_map"), ("press", "m"),
        ("tp", 0, 285, 0, 14, 16), ("time", 18.0), ("wait", 0.8), ("shot", "m6_11_gate_approach"),
        ("call", lambda g: _kill(g, ["dustfang_raider"], 9, loot=False)),
        ("call", lambda g: _near_enemy(g, "warlord_rukhar", 6).name), ("call", lambda g: setattr(g.player, "auto_attacking", True)),
        ("wait", 2.5), ("shot", "m6_12_warlord_fight"),
        ("call", lambda g: setattr(g.player, "hp", g.player.max_hp)),
        ("call", lambda g: _kill(g, ["warlord_rukhar"], 1)), ("wait", 0.5),
        ("check", lambda g: g.quests.is_complete("r12"), "warlord defeated (r12 complete)"),
        ("call", lambda g: _kill(g, ["dustfang_raider"], 9, loot=False)),
        ("call", lambda g: _talk(g, "gatewarden_ushka")), ("call", lambda g: _dlg_option(g, "Ironmaw")),
        ("call", lambda g: g.hud.dialogue._button("a")), ("wait", 1.0),
        ("check", lambda g: "r12" in g.quests.done, "final quest turned in"),
        ("wait", 1.5), ("shot", "m6_13_victory"),
        ("fps",), ("quit",),
    ]


def _m7(g) -> list[Step]:
    st: dict = {}

    def create(g):
        c = g.menus.creation
        c.set_race("troll")
        c.set_class("hunter")
        c.name_field.text = "Testhunt"

    def progress(g):
        p = g.player
        _talk(g, "elder_wazuko")
        _dlg_option(g, "Tide-Touched")
        g.hud.dialogue._button("a")
        g.hud.dialogue.close()
        p.inventory.add_gold(37)
        p.gain_xp(120, "test")
        p.teleport(236.0, -250.0, 45.0)
        st.update(pos=(round(p.x, 1), round(p.z, 1)), gold=p.inventory.gold, xp=p.xp.xp, lvl=p.level)
        return st

    def after_load(g):
        p = g.player
        return (round(p.x, 1), round(p.z, 1), p.inventory.gold, p.xp.xp, p.level, sorted(g.quests.active))

    return [
        ("wait", 2.5), ("check", lambda g: g.state == "menu" and g.menus.main.enabled, "main menu shown"),
        ("shot", "m7_01_main_menu"),
        ("call", lambda g: g.menus.open_creation()), ("wait", 0.3), ("call", create), ("wait", 0.8),
        ("shot", "m7_02_character_creation"),
        ("call", lambda g: g.menus.creation._create()), ("wait", 1.0),
        ("check", lambda g: g.state == "playing" and g.player.race == "troll" and g.player.cls == "hunter", "new troll hunter created"),
        ("shot", "m7_03_new_game"),
        ("call", progress, "progress"), ("wait", 0.3),
        ("call", lambda g: str(g.save()), "saved"),
        ("check", lambda g: (__import__("save").save_path("Testhunt")).exists(), "save file written"),
        ("press", "escape"), ("wait", 0.3),
        ("check", lambda g: g.paused and g.menus.pause.enabled, "Esc opens the pause menu"),
        ("shot", "m7_04_pause_menu"),
        ("call", lambda g: g.menus.pause._sub(g.menus.settings)), ("wait", 0.3), ("shot", "m7_05_settings"),
        ("call", lambda g: g.menus.settings._toggle("heat_haze")), ("call", lambda g: g.menus.settings._toggle("heat_haze")),
        ("call", lambda g: g.menus.settings._back()), ("wait", 0.2),
        ("check", lambda g: g.menus.pause.enabled, "back to pause menu"),
        ("call", lambda g: g.menus.pause._main()), ("wait", 1.0),
        ("check", lambda g: g.state == "menu" and g.player is None, "returned to main menu"),
        ("call", lambda g: g.menus.main._continue()), ("wait", 1.0),
        ("call", after_load, "after load"),
        ("check", lambda g: g.player is not None and abs(g.player.x - st["pos"][0]) + abs(g.player.z - st["pos"][1]) < 1.0, "position restored"),
        ("check", lambda g: g.player.inventory.gold == st["gold"] and g.player.xp.xp == st["xp"], "gold and xp restored"),
        ("check", lambda g: "t1" in g.quests.active, "quest state restored"),
        ("call", lambda g: _kill(g, ["dustfang_raider", "warlord_rukhar"], 12, loot=False)),
        ("tp", 0, 318, 0, 12, 18), ("time", 17.5), ("wait", 0.5),
        ("call", lambda g: g._on_game_won()), ("wait", 5.0), ("shot", "m7_06_victory"),
        ("call", lambda g: g.menus.victory.hide()), ("wait", 0.2),
        ("tp", 0, 326, 0, 10, 14), ("wait", 0.5), ("shot", "m7_07_gate_open"),
        ("call", lambda g: (g.gate_doors.amount, g.gate_doors.collider), "gate"),
        ("hold", "w", 3.0), ("wait", 3.2),
        ("call", lambda g: (round(g.player.x, 1), round(g.player.z, 1)), "after walking north"),
        ("check", lambda g: g.player.z > 336, "can walk through the opened gate"),
        ("call", lambda g: __import__("save").delete(__import__("save").save_path("Testhunt"))),
        ("fps",), ("quit",),
    ]


GEAR_BY_LEVEL = {
    "warrior": {1: ["worn_hand_axe"], 3: ["hollowforged_cleaver", "tattered_leather_cap"],
                5: ["redtusk_warblade", "boarhide_helm", "scaled_lizardhide_vest", "boarhide_leggings"],
                7: ["bonecrusher_club", "boarhide_helm", "brawlers_harness", "boarhide_leggings", "crabshell_sabatons"],
                9: ["raider_waraxe", "ember_crested_helm", "brawlers_harness", "ironbound_greaves", "crabshell_sabatons"],
                10: ["tunnelmaw_crusher", "ember_crested_helm", "brawlers_harness", "ironbound_greaves", "tunnelers_stompers"]},
    "hunter": {1: ["frayed_shortbow"], 3: ["sandwood_longbow", "tattered_leather_cap"],
               5: ["vulture_feather_bow", "hawkeye_bandana", "scaled_lizardhide_vest", "sandrunner_pants"],
               7: ["smugglers_recurve", "hawkeye_bandana", "dune_stalker_jerkin", "sandrunner_pants", "crabshell_sabatons"],
               9: ["smugglers_recurve", "smuggler_tricorn", "dune_stalker_jerkin", "sandrunner_pants", "swiftstrider_boots"],
               10: ["ridgestalker_bow", "smuggler_tricorn", "dune_stalker_jerkin", "sandrunner_pants", "tunnelers_stompers"]},
    "shaman": {1: ["knotted_staff"], 3: ["spiritbound_mace", "tattered_leather_cap"],
               5: ["totemwood_staff", "tide_mask", "scaled_lizardhide_vest", "mystic_kilt"],
               7: ["totemwood_staff", "tide_mask", "spiritweave_robe", "mystic_kilt", "crabshell_sabatons"],
               9: ["geomancers_rod", "seers_circlet", "spiritweave_robe", "mystic_kilt", "ashwalker_boots"],
               10: ["tidecallers_scepter", "seers_circlet", "spiritweave_robe", "mystic_kilt", "tunnelers_stompers"]},
}
FOE_BY_LEVEL = {1: "desert_boar", 3: "sand_scorpion", 5: "cliff_lizard", 7: "smuggler_cutthroat", 9: "dustfang_raider"}
PRIORITY = {
    "warrior": ["undying_roar", "tusk_rush", "quake_stomp", "rending_gash", "brutal_strike"],
    "hunter": ["call_of_the_wild", "venom_arrow", "crippling_shot", "piercing_shot", "arrow_storm"],
    "shaman": ["tidal_mend", "ember_totem", "searing_brand", "chain_spark", "lightning_lash"],
}


class BalanceBot:
    """Very simple player AI used to measure fight length and damage taken."""

    def __init__(self, g, report: list) -> None:
        self.g = g
        self.report = report
        self.queue: list = []
        self.cur = None
        self.t0 = 0.0
        self.t = 0.0
        self.label = ""
        self.hp_start = 0.0
        self.done = True
        self.potions = 0

    def start(self, label: str, foes: list, potions: int = 0) -> None:
        self.label = label
        self.queue = list(foes)
        self.cur = None
        self.done = False
        self.results = []
        self.hp_start = self.g.player.max_hp
        self.potions = potions
        self.fight_t = 0.0

    def update(self, dt: float) -> None:
        if self.done:
            return
        g = self.g
        p = g.player
        self.t += dt
        if p.dead:
            self.report.append(f"{self.label}: DIED after {len(self.results)} kills {self.results}")
            self.done = True
            return
        if self.cur is None or self.cur.dead:
            if self.cur is not None:
                self.results.append((round(self.fight_t, 1), int(100 * p.hp / p.max_hp)))
            if not self.queue:
                self.report.append(f"{self.label}: {self.results}  (secs, hp% after each)")
                self.done = True
                return
            self.cur = self.queue.pop(0)
            self.cur.engage(p, social=False)
            g.targeting.set_target(self.cur)
            p.auto_attacking = True
            self.fight_t = 0.0
            if p.resource_type == "rage":
                p.resource = 0.0
        self.fight_t += dt
        t = self.cur
        d = p.distance_to(t)
        if not p.is_ranged() and d > p.melee_reach(t) * 0.9 and p.charge is None:
            dx, dz = t.x - p.x, t.z - p.z
            p.motor.move(dt, dx, dz, 7.0)
        if p.hp < p.max_hp * 0.3 and self.potions > 0 and p.potion_cd <= 0:
            self.potions -= 1
            p.heal(160, p)
            p.potion_cd = 30.0
        ab = g.abilities
        if ab.casting or ab.gcd > 0:
            return
        for aid in PRIORITY[p.cls]:
            if aid not in ab.known:
                continue
            if aid == "undying_roar" and p.hp > p.max_hp * 0.4:
                continue
            if aid == "tidal_mend" and p.hp > p.max_hp * 0.45:
                continue
            if aid == "rending_gash" and t.has_aura("bleed"):
                continue
            if aid == "venom_arrow" and t.has_aura("venom_arrow"):
                continue
            if aid == "searing_brand" and t.has_aura("brand"):
                continue
            if aid in ("ember_totem", "call_of_the_wild") and g.companions.units:
                continue
            ok, _ = ab.can_use(aid)
            if ok:
                ab.use(aid)
                break


BAL_ONLY: list[str] = []


def _balboss(g) -> list[Step]:
    BAL_ONLY[:] = ["hunter", "hunter", "warrior"]
    return _balance(g)


def _balance(g) -> list[Step]:
    report: list = []
    bot = BalanceBot(g, report)
    g.on_update.append(bot.update)

    def setup(cls: str, lvl: int):
        def fn(g):
            g.reset_world_state()
            g.spawn_player("orc", cls, "Bot")
            _level_to(g, lvl)
            for aid in g.abilities.order:
                ranks = g.abilities.ranks(aid)
                best = 0
                for i, r in enumerate(ranks):
                    if r["level"] <= lvl:
                        best = i + 1
                if best:
                    g.abilities.learn(aid, best)
            gl = max(k for k in GEAR_BY_LEVEL[cls] if k <= lvl)
            for iid in GEAR_BY_LEVEL[cls][gl]:
                g.player.equipment.set(__import__("items.item", fromlist=["get"]).get(iid)["slot"], iid)
            g.player.recalc(keep_ratio=False)
            g.player.hp = g.player.max_hp
            g.player.resource = 0.0 if g.player.resource_type == "rage" else g.player.max_resource
            g.player.teleport(20.0, 20.0, 0.0)
            g.world.env.hour = 12.0
        return fn

    def spawn_foes(type_id: str, lvl: int, n: int):
        def fn(g):
            p = g.player
            foes = []
            for k in range(n):
                e = g.enemies.spawn(type_id, lvl, p.x + 14 + k * 3, p.z + 4 + k * 5, {"temporary": True, "wander": 0.0})
                foes.append(e)
            bot.start(f"{g.player.cls} L{lvl} vs 3x {type_id} L{lvl}", foes)
        return fn

    def spawn_boss(g):
        p = g.player
        b = g.enemies.spawn("grakk", 10, p.x + 12, p.z + 6, {"temporary": True, "wander": 0.0})
        b.home = (b.x, b.z)
        bot.start(f"{p.cls} L10 vs Grakk (3 potions)", [b], potions=3)

    from ursina import application as _app
    steps: list[Step] = [("wait", 1.0), ("call", lambda g: setattr(_app, "time_scale", 4.0))]
    if BAL_ONLY:
        for cls in BAL_ONLY:
            steps += [("call", setup(cls, 10)), ("wait", 0.3), ("call", spawn_boss), ("until", lambda g: bot.done, 240.0)]
        steps += [("call", lambda g: " | ".join(report), "BALANCE REPORT"), ("quit",)]
        return steps
    for cls in ("warrior", "hunter", "shaman"):
        for lvl in (1, 3, 5, 7, 9):
            steps += [("call", setup(cls, lvl)), ("wait", 0.3), ("call", spawn_foes(FOE_BY_LEVEL[lvl], lvl, 3)),
                      ("until", lambda g: bot.done, 120.0)]
        steps += [("call", setup(cls, 10)), ("wait", 0.3), ("call", spawn_boss), ("until", lambda g: bot.done, 240.0)]
    steps += [("call", lambda g: "\n".join(report), "BALANCE REPORT"), ("quit",)]
    return steps


def _showcase(g) -> list[Step]:
    def clean(g):
        g.hud.messages.log_root.enabled = False
        g.hud.fps_text.enabled = False
        g.hud._region_fade = 0.0
        g.hud.region_text.text = ""
        g.hud.region_sub.text = ""

    def quests(g):
        g.quests.accept("r1")
        g.quests.accept("r2")

    return [
        ("wait", 1.5), ("call", lambda g: _level_to(g, 5)), ("call", _learn_all), ("call", quests),
        ("call", lambda g: g.player.equip("scaled_lizardhide_vest") if g.player.inventory.add("scaled_lizardhide_vest", silent=True) else None),
        ("call", lambda g: g.player.equip("boarhide_helm") if g.player.inventory.add("boarhide_helm", silent=True) else None),
        ("call", lambda g: g.player.equip("redtusk_warblade") if g.player.inventory.add("redtusk_warblade", silent=True) else None),
        ("tp", -2, -104, 330, 13, 13), ("time", 12.5), ("wait", 4.5), ("call", clean), ("wait", 0.3), ("shot", "show_redtusk"),
        ("tp", 186, 118, 60, 9, 12), ("time", 18.4), ("wait", 1.0), ("call", clean), ("shot", "show_coast_dusk"),
        ("tp", -118, 170, 300, 12, 13), ("time", 10.0), ("wait", 1.0), ("call", clean), ("shot", "show_scorchspine"),
        ("tp", -178, -262, 30, 10, 14), ("time", 22.5), ("wait", 1.0), ("call", clean), ("shot", "show_ashfang_night"),
        ("call", lambda g: g.player.teleport(-236.3, 226.2)), ("wait", 1.5),
        ("call", lambda g: _tp_cell(g, 27, 9, 180, 18, 16)), ("wait", 1.0), ("call", clean), ("shot", "show_mine_boss"),
        ("quit",),
    ]


SCRIPTS: dict[str, Callable[[Any], list[Step]]] = {"showcase": _showcase, "balance": _balance, "balboss": _balboss, "m7": _m7, "m6": _m6, "gallery": _gallery, "hunter": _hunter, "shaman": _shaman, "troll": _troll, "escort": _escort, "dbg": _dbg, "m4": _m4, "m1": _m1, "m2": _m2, "m3": _m3, "perf": _perf, "perfdead": _perfdead}
