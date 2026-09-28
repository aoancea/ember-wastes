"""Central game object: owns the world, the player and every gameplay system, and runs the loop."""
from __future__ import annotations

import math
from typing import Any, Callable

from panda3d.core import Vec3
from ursina import Entity, application, camera, held_keys, mouse, time

from core.events import events
from player.camera import MouseLook, ThirdPersonCamera
from settings import INTERACT_RANGE, LOOT_RANGE, user_settings
from world.effects import PostProcess
from world.world import World

RESPAWN_POINTS: list[tuple[str, float, float]] = [
    ("Ashfang Hollow", -170.0, -252.0),
    ("Saltroot Isles", 229.0, -257.0),
    ("Redtusk Post", -6.0, -86.0),
    ("Scorchspine Outrider Camp", -62.0, 138.0),
    ("Northern Road", 6.0, 250.0),
    ("Brineclaw Road", 118.0, 112.0),
]


class Game:
    """Holds references to all systems. A single instance lives in ``core.game.game``."""

    def __init__(self, app) -> None:
        self.app = app
        self.base = application.base
        self.settings = user_settings
        self.state = "loading"      # loading | menu | playing | dead
        self.paused = False
        self.world: World | None = None
        self.player = None
        self.cam: ThirdPersonCamera | None = None
        self.mouselook = MouseLook(self.base)
        self.post: PostProcess | None = None
        self.hud = None
        self.audio = None
        self.enemies = None
        self.targeting = None
        self.fx = None
        self.loot = None
        self.quests = None
        self.npcs = None
        self.interactables = None
        self.companions = None
        self.dungeon = None
        self.systems: list[Any] = []
        self.jump_request = False
        self._lmb_down = False
        self._lmb_drag = 0.0
        self._rmb_down = False
        self._rmb_drag = 0.0
        self.time = 0.0
        self.frame_times: list[float] = []
        self.on_update: list[Callable[[float], None]] = []
        self.ui_capture_keys = False
        self._pending: list[list[Any]] = []
        self._amb_timer = 0.0
        self.cam_override: tuple[Vec3, Vec3] | None = None
        self.menus = None
        self.play_time = 0.0
        self.victory = False
        self._menu_t = 0.0
        self.gate_doors = None

    # ---------------------------------------------------------------- setup
    def build_world(self) -> None:
        vd = float(self.settings.view_distance)
        self.world = World(self.base.render, vd)
        camera.fov = 78
        camera.clip_plane_near = 0.15
        camera.clip_plane_far = max(vd + 160.0, 480.0)
        mouse.traverse_target = None  # we do our own world picking
        self.cam = ThirdPersonCamera(camera, self.world)
        self.gate_doors = self.world.gate_doors
        self.post = PostProcess(self.base, 0.15, camera.clip_plane_far)
        self.post.enable()
        self.post.haze_enabled = bool(self.settings.heat_haze)
        from combat.companions import CompanionManager
        from combat.effects import EffectsManager
        from combat.targeting import Targeting
        from core.audio import AudioSystem
        from enemies.spawner import EnemyManager
        from items.loot import LootSystem
        self.audio = AudioSystem()
        self.fx = EffectsManager(self)
        self.loot = LootSystem(self)
        self.enemies = EnemyManager(self)
        self.companions = CompanionManager(self)
        self.targeting = Targeting(self)
        from world.dungeon import WALL_H, Dungeon
        self.dungeon = Dungeon(self)
        self.cam.ceiling = self.dungeon.oy + WALL_H
        self.enemies.spawn_all()
        self.dungeon.spawn_enemies(self.enemies)
        from npcs.npc import NPCManager
        from quests.escort import EscortController
        from quests.objects import InteractableManager, MineEntrance
        from quests.quest_manager import QuestManager
        self.npcs = NPCManager(self)
        self.quests = QuestManager(self)
        self.escort = EscortController(self)
        self.interactables = InteractableManager(self)
        self.interactables.add(MineEntrance(self, -236.0, 225.8))
        self.systems = [self.npcs, self.quests, self.escort, self.interactables, self.dungeon]
        events.on("unit_died", self._on_unit_died)
        events.on("level_up", self._on_level_up)
        events.on("game_won", self._on_game_won)

    def spawn_player(self, race: str, cls: str, name: str, save: dict | None = None) -> None:
        from combat.abilities import AbilitySystem
        from player.player import Player
        spawn = {"orc": (-168.0, -250.0, 227.0), "troll": (228.0, -256.0, 144.0)}.get(race, (-168.0, -250.0, 0.0))
        if self.player:
            self.player.destroy()
        self.player = Player(self, race, cls, name, spawn[0], spawn[1], spawn[2])
        self.abilities = AbilitySystem(self, self.player)
        if save is None:
            self.player.give_starting_kit()
            first = self.player.cls_def["abilities"][0]
            self.abilities.learn(first, 1)
        self.cam.yaw = spawn[2]
        self.state = "playing"
        events.emit("player_spawned", player=self.player)

    # ---------------------------------------------------------------- helpers
    def pending(self, delay: float, fn: Callable[[], Any]) -> None:
        self._pending.append([delay, fn])

    def friendly_units(self) -> list[Any]:
        out = []
        if self.player is not None and not self.player.dead:
            out.append(self.player)
        if self.companions:
            out.extend(u for u in self.companions.units if getattr(u, "targetable", False) and not u.dead)
        return out

    def interact_with(self, obj: Any) -> None:
        p = self.player
        if p is None or p.dead or obj is None:
            return
        d = math.hypot(obj.x - p.x, obj.z - p.z)
        if hasattr(obj, "take_damage") and getattr(obj, "faction", "") == "hostile":
            if obj.dead:
                if getattr(obj, "lootable", False):
                    if d > LOOT_RANGE + obj.radius:
                        events.emit("message", text="You are too far away.")
                        return
                    if self.hud:
                        self.hud.open_loot(obj)
                return
            p.auto_attacking = True
            return
        if hasattr(obj, "interact"):
            if d > INTERACT_RANGE + getattr(obj, "radius", 0.5):
                events.emit("message", text="You are too far away.")
                return
            obj.interact(self)

    def interact_nearest(self) -> None:
        """F key: loot/talk/use whatever is closest (or the current target)."""
        p = self.player
        t = self.targeting.target
        if t is not None and math.hypot(t.x - p.x, t.z - p.z) <= INTERACT_RANGE + 1.5 and \
                (getattr(t, "lootable", False) or hasattr(t, "interact")):
            self.interact_with(t)
            return
        best, bd = None, INTERACT_RANGE + 1.0
        cands: list[Any] = [e for e in self.enemies.enemies_near(p.x, p.z, 8) if e.lootable]
        if self.npcs:
            cands += self.npcs.near(p.x, p.z, 8)
        if self.interactables:
            cands += self.interactables.near(p.x, p.z, 8)
        for c in cands:
            dd = math.hypot(c.x - p.x, c.z - p.z)
            if dd < bd:
                best, bd = c, dd
        if best is not None:
            self.targeting.set_target(best)
            self.interact_with(best)

    def _on_unit_died(self, unit: Any, killer: Any = None, **_: Any) -> None:
        p = self.player
        if unit is p:
            self.state = "dead"
            self.enemies.reset_all()
            if self.companions:
                self.companions.clear()
            events.emit("sound", name="death")
            events.emit("player_died")
            return
        if p is None:
            return
        if getattr(unit, "faction", "") == "hostile":
            by_player = killer is p or getattr(killer, "owner", None) is p or getattr(unit, "tagged_by_player", False)
            if by_player and not unit.t.get("no_xp"):
                from combat.combat import kill_xp
                xp = kill_xp(p.level, unit.level, unit.elite)
                if xp:
                    p.gain_xp(xp, unit.name)
            if self.targeting.target is unit:
                p.auto_attacking = False
            events.emit("sound", name="squeal" if unit.t.get("model") in ("boar", "hyena") else "grunt", volume=0.6)

    def _on_level_up(self, level: int, **_: Any) -> None:
        if self.player:
            self.fx.level_up(self.player)
            if self.post:
                self.post.trigger_flash((1.0, 0.9, 0.5), 0.35)
        events.emit("sound", name="level_up")

    # ---------------------------------------------------------------- lifecycle
    def reset_world_state(self) -> None:
        """Put enemies, NPCs, quests and objects back to a fresh state (new game / load)."""
        if self.dungeon is not None and self.dungeon.inside:
            self.dungeon.exit(silent=True)
        if self.companions:
            self.companions.clear()
        if self.fx:
            self.fx.clear()
        self._pending.clear()
        if self.escort is not None:
            self.escort.qid = self.escort.obj = self.escort.npc = None
        for e in list(self.enemies.enemies):
            if e.spawn.get("temporary"):
                self.enemies.remove(e)
                continue
            if e.state == "combat":
                e.evade()
            if e.dead or e.state == "respawning":
                e.respawn()
            e.hp = e.max_hp
            e.state = "idle"
            e.motor.teleport(*e.home)
        for n in self.npcs.npcs.values():
            n.reset()
        for o in self.interactables.objects:
            if hasattr(o, "respawn_t"):
                o.available = True
                o.root.show()
        self.quests.active.clear()
        self.quests.done.clear()
        self.targeting.clear()
        self.victory = False
        self.play_time = 0.0
        self.set_gate_open(False, instant=True)
        events.emit("quest_changed", qid="")

    def _enter_play(self) -> None:
        self.state = "playing"
        self.paused = False
        self.cam_override = None
        if self.menus:
            for m in (self.menus.main, self.menus.creation, self.menus.load, self.menus.settings, self.menus.pause):
                m.enabled = False
            self.ui_capture_keys = False
        if self.hud:
            self.hud.set_visible(True)

    def new_game(self, race: str, cls: str, name: str) -> None:
        self.reset_world_state()
        self.world.env.hour = 8.5
        self.spawn_player(race, cls, name)
        self._enter_play()
        start = "Ashfang Hollow" if race == "orc" else "the Saltroot Isles"
        giver = "Chieftain Ghorvash" if race == "orc" else "Elder Wazuko"
        events.emit("announce", title=f"Welcome to the Ember Wastes, {name}",
                    subtitle=f"Speak with {giver} (yellow marker) in {start}.")
        self.save()

    def load_game(self, d: dict) -> None:
        p = d["player"]
        self.reset_world_state()
        self.spawn_player(p["race"], p["cls"], p["name"], save=d)
        self.player.load_dict(p)
        self.abilities.load_dict(d.get("abilities", {}))
        if not self.abilities.known:
            self.abilities.learn(self.player.cls_def["abilities"][0], 1)
        self.quests.load_dict(d.get("quests", {}))
        self.world.env.hour = float(d.get("world", {}).get("hour", 10.0))
        self.victory = bool(d.get("victory", False))
        self.play_time = float(d.get("play_time", 0.0))
        if self.victory:
            self.set_gate_open(True, instant=True)
        self.cam.yaw = self.player.yaw
        self._enter_play()
        events.emit("announce", title=f"Welcome back, {self.player.name}", subtitle="")

    def save(self):
        if self.player is None:
            return None
        import save as savefile
        try:
            path = savefile.save_game(self)
            events.emit("chat", text=f"<rgb(0.7,0.9,0.7)>Game saved ({path.name}).")
            return path
        except OSError as exc:
            events.emit("message", text=f"Save failed: {exc}")
            return None

    def return_to_menu(self) -> None:
        if self.dungeon is not None and self.dungeon.inside:
            self.dungeon.exit(silent=True)
        if self.companions:
            self.companions.clear()
        if self.player is not None:
            self.player.destroy()
            self.player = None
        self.targeting.clear()
        self.state = "menu"
        self.paused = False
        self.mouselook.end()
        if self.hud:
            self.hud.set_visible(False)
        if self.menus:
            self.menus.main.show()

    def _on_game_won(self, **_: Any) -> None:
        self.victory = True
        self.set_gate_open(True)
        events.emit("sound", name="level_up")
        self.pending(4.0, lambda: self.menus.victory.show_victory() if self.menus else None)
        self.save()

    def set_gate_open(self, value: bool, instant: bool = False) -> None:
        if self.gate_doors is not None:
            self.gate_doors.set_open(value, instant)

    def apply_view_distance(self) -> None:
        vd = float(self.settings.view_distance)
        self.world.set_view_distance(vd)
        camera.clip_plane_far = max(vd + 160.0, 480.0)
        if self.post:
            self.post.set_clip(0.15, camera.clip_plane_far)

    def apply_settings(self, key: str) -> None:
        from ursina import window
        s = self.settings
        if key == "fullscreen":
            window.fullscreen = bool(s.fullscreen)
        elif key == "resolution" and not s.fullscreen:
            window.size = (int(s.resolution[0]), int(s.resolution[1]))
            window.center_on_screen()
        elif key == "heat_haze" and self.post:
            self.post.haze_enabled = bool(s.heat_haze)

    def release_spirit(self) -> None:
        p = self.player
        if p is None or not p.dead:
            return
        name, x, z = min(RESPAWN_POINTS, key=lambda r: (r[1] - p.x) ** 2 + (r[2] - p.z) ** 2)
        if self.dungeon is not None and self.dungeon.inside:
            self.dungeon.exit(silent=True)
            name, x, z = "Scorchspine Outrider Camp", -224.0, 216.0
        p.revive(x, z, 0.6)
        self.state = "playing"
        events.emit("message", text=f"You return to life at {name}.", color=(1, 0.85, 0.4))

    # ---------------------------------------------------------------- loop
    def update(self) -> None:
        dt = min(time.dt, 0.1)
        self.time += dt
        self.frame_times.append(time.dt)
        if len(self.frame_times) > 240:
            self.frame_times.pop(0)
        if self.world is None:
            return
        active = self.state in ("playing", "dead") and not self.paused
        if active and self.player is not None:
            self.play_time += dt
            self._update_play(dt)
        elif self.state == "menu":
            self._update_menu_camera(dt)
        if self.gate_doors is not None:
            self.gate_doors.update(dt)
        for fn in list(self.on_update):
            fn(dt)
        cam_pos = camera.world_position
        if not self.paused:
            self.world.update(dt, Vec3(cam_pos.x, cam_pos.y, cam_pos.z))
            if self.fx:
                self.fx.update(dt)
        fog = self.world.env.fog_color
        self.base.setBackgroundColor(fog[0], fog[1], fog[2], 1)
        if self.post and self.post.enabled:
            self.post.update(dt, 0.0 if self.world.underground else (1.0 - self.world.env.night) * 0.9)
        if self.hud:
            self.hud.update(dt)
        if self.audio:
            self._update_ambience(dt)
            self.audio.update(dt)

    def _update_menu_camera(self, dt: float) -> None:
        if self.menus and self.menus.creation.enabled:
            return
        self._menu_t += dt
        a = self._menu_t * 0.05 + 2.2
        cx, cz = -10.0, -80.0
        cy = self.world.ground(cx, cz)
        pos = Vec3(cx + math.sin(a) * 70, cy + 32, cz + math.cos(a) * 70)
        camera.setPos(pos)
        camera.lookAt(Vec3(cx, cy + 4, cz), Vec3(0, 1, 0))

    def _update_ambience(self, dt: float) -> None:
        self._amb_timer -= dt
        if self._amb_timer > 0:
            return
        self._amb_timer = 0.5
        levels: dict[str, float] = {}
        if self.state in ("menu", "loading"):
            levels["theme"] = 0.9
            levels["amb_wind"] = 0.3
        elif self.player is not None:
            p = self.player
            if self.world.underground:
                levels["amb_cave"] = 0.8
            else:
                coast = self.world.terrain.mask_at("coast_d", p.x, p.z)
                ocean = max(0.0, min(1.0, 1.0 - (-coast - 10) / 70.0))
                levels["amb_ocean"] = ocean * 0.8
                levels["amb_wind"] = 0.55 * (1.0 - ocean * 0.5)
                levels["amb_night"] = self.world.env.night * 0.5 * (1.0 - ocean)
        self.audio.set_ambience(levels)

    def _update_play(self, dt: float) -> None:
        p = self.player
        items, self._pending = self._pending, []
        keep = []
        for item in items:
            item[0] -= dt
            if item[0] <= 0:
                item[1]()
            else:
                keep.append(item)
        self._pending = keep + self._pending
        # mouse look / camera orbit
        dx, dy = self.mouselook.poll()
        sens = 0.16 * float(self.settings.mouse_sensitivity)
        inv = -1.0 if self.settings.invert_y else 1.0
        if dx or dy:
            self.cam.rotate(dx * sens, dy * sens * 0.8 * inv)
            if self._lmb_down:
                self._lmb_drag += abs(dx) + abs(dy)
            if self._rmb_down:
                self._rmb_drag += abs(dx) + abs(dy)
        keys = {
            "w": held_keys["w"] or held_keys["up arrow"], "s": held_keys["s"] or held_keys["down arrow"],
            "a": held_keys["a"] or held_keys["left arrow"], "d": held_keys["d"] or held_keys["right arrow"],
            "q": held_keys["q"], "e": held_keys["e"],
            "shift": held_keys["left shift"] or held_keys["right shift"] or held_keys["shift"],
            "jump": self.jump_request,
            "both_mouse": self._lmb_down and self._rmb_down,
        }
        self.jump_request = False
        if self.ui_capture_keys:
            keys = {"jump": False}
        rmb_look = self._rmb_down and self.mouselook.active
        can_move = self.state == "playing" and p.can_move()
        p.update_movement(dt, keys, self.cam.yaw, rmb_look, can_move)
        p.update(dt)
        self.abilities.update(dt)
        self.enemies.update(dt)
        self.companions.update(dt)
        # keep the player "in combat" while anything is fighting them
        for e in self.enemies.enemies_near(p.x, p.z, 60):
            if e.state == "combat" and e.target is p:
                p.enter_combat(1.0)
                break
        for system in self.systems:
            system.update(dt)
        self.targeting.update(dt)
        p.sync_model(dt)
        if self.cam_override is not None:
            camera.setPos(self.cam_override[0])
            camera.lookAt(self.cam_override[1], Vec3(0, 1, 0))
        else:
            self.cam.update(dt, p.focus_point())

    # ---------------------------------------------------------------- input
    def input(self, key: str) -> None:
        if self.world is None:
            return
        if key == "escape" and self.menus is not None:
            if self.state == "menu":
                self.menus.escape()
                return
            if self.menus.any_open():
                self.menus.escape()
                return
            hud_busy = self.hud is not None and self.hud.any_window_open()
            has_target = self.targeting is not None and self.targeting.target is not None
            if not hud_busy and not has_target:
                self.menus.escape()
                return
        if self.state == "menu" or (self.menus is not None and self.menus.any_open()):
            return
        if self.hud and self.hud.input(key):
            return
        if self.state not in ("playing", "dead") or self.paused:
            return
        if key == "scroll up":
            self.cam.zoom(-0.12)
        elif key == "scroll down":
            self.cam.zoom(0.12)
        elif key == "right mouse down":
            if not self._pointer_over_ui():
                self._rmb_down = True
                self._rmb_drag = 0.0
                self.mouselook.begin()
        elif key == "right mouse up":
            was = self._rmb_down
            self._rmb_down = False
            if not self._lmb_down:
                self.mouselook.end()
            if was and self._rmb_drag < 6:
                events.emit("world_right_click")
        elif key == "left mouse down":
            if not self._pointer_over_ui():
                self._lmb_down = True
                self._lmb_drag = 0.0
                self.mouselook.begin()
        elif key == "left mouse up":
            was = self._lmb_down
            self._lmb_down = False
            if not self._rmb_down:
                self.mouselook.end()
            if was and self._lmb_drag < 6:
                events.emit("world_left_click")
        if self.state != "playing" or self.player is None:
            return
        if key == "space":
            self.jump_request = True
        elif key == "tab":
            self.targeting.tab(backwards=bool(held_keys["shift"]))
        elif key in ("1", "2", "3", "4", "5"):
            self.abilities.use_slot(int(key) - 1)
        elif key == "f":
            self.interact_nearest()
        elif key == "r":
            t = self.targeting.target
            if t is not None and hasattr(t, "take_damage") and not t.dead and self.player.is_hostile_to(t):
                self.player.auto_attacking = not self.player.auto_attacking
        events.emit("key", key=key)

    def _pointer_over_ui(self) -> bool:
        he = mouse.hovered_entity
        return he is not None and he.has_ancestor(camera.ui)

    def average_fps(self) -> float:
        if not self.frame_times:
            return 0.0
        return len(self.frame_times) / max(sum(self.frame_times), 1e-6)


game: Game | None = None


class GameLoop(Entity):
    """Ursina entity that forwards update/input to the Game object."""

    def __init__(self, g: Game) -> None:
        super().__init__(ignore_paused=True, eternal=True)
        self.g = g

    def update(self) -> None:
        self.g.update()

    def input(self, key: str) -> None:
        self.g.input(key)
