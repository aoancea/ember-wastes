"""Heads-up display: frames, bars, hotbar, tracker, minimap and messages (grows per milestone)."""
from __future__ import annotations

from typing import Any

from ursina import Entity, Text, camera, color, window

from core.events import events
from ui.character_ui import CharacterWindow
from ui.dialogue import DialogueWindow
from ui.questlog import QuestLog, QuestTracker
from ui.trainer_ui import TrainerWindow
from ui.vendor_ui import VendorWindow
from ui.frames import CastBar, FloatingText, Nameplates, PlayerFrame, TargetFrame
from ui.hotbar import Hotbar, MicroMenu, XPBar
from ui.inventory_ui import BagsWindow
from ui.loot_ui import LootWindow
from ui.menus import DeathPanel
from ui.messages import Messages
from ui.minimap import MapSource, Minimap, WorldMap
from ui.widgets import Tooltip


class HUD:
    """Top-level in-game UI. ``input`` returns True when it consumed a key."""

    def __init__(self, game) -> None:
        self.game = game
        self.fps_text = Text(parent=camera.ui, text="", position=(window.aspect_ratio / 2 - 0.01, -0.485), scale=0.7,
                             origin=(0.5, -0.5), color=color.rgba(1, 1, 1, 0.7))
        self.region_text = Text(parent=camera.ui, text="", origin=(0, 0), y=0.40, scale=1.6,
                                color=color.rgb(1, 0.85, 0.5))
        self.region_sub = Text(parent=camera.ui, text="", origin=(0, 0), y=0.365, scale=0.9,
                               color=color.rgb(0.95, 0.9, 0.8))
        self.player_frame = PlayerFrame(game)
        self.target_frame = TargetFrame(game)
        self.cast_bar = CastBar(game)
        self.nameplates = Nameplates(game)
        self.floating = FloatingText(game)
        self.messages = Messages(game)
        self.loot = LootWindow(game)
        self.death = DeathPanel(game)
        self.hotbar = Hotbar(game)
        self.xpbar = XPBar(game)
        self.micro = MicroMenu(self)
        self.bags = BagsWindow(game)
        self.character = CharacterWindow(game)
        self.dialogue = DialogueWindow(game)
        self.vendor = VendorWindow(game)
        self.trainer = TrainerWindow(game)
        self.questlog = QuestLog(game)
        self.tracker = QuestTracker(game)
        self.map_source = MapSource(game)
        if game.dungeon is not None:
            self.map_source.set_dungeon(game.dungeon)
        self.minimap = Minimap(game, self.map_source)
        self.worldmap = WorldMap(game, self.map_source)
        self.fader = Entity(parent=camera.ui, model="quad", scale=(4, 2), color=color.rgba(0, 0, 0, 0), z=-20, enabled=False)
        self._fade: list = []
        Tooltip.get()
        self.windows: list[Any] = [self.character, self.bags, self.questlog, self.worldmap, self.loot, self.dialogue, self.vendor,
                                   self.trainer]
        self._fps_t = 0.0
        self._region = None
        self._region_fade = 0.0
        events.on("region_changed", self._on_region)

    def fade(self, callback, duration: float = 0.35) -> None:
        """Fade to black, run ``callback``, fade back in."""
        self._fade = [0.0, duration, callback, "out"]
        self.fader.enabled = True

    def _update_fade(self, dt: float) -> None:
        if not self._fade:
            return
        f = self._fade
        f[0] += dt
        k = min(1.0, f[0] / f[1])
        if f[3] == "out":
            self.fader.color = color.rgba(0, 0, 0, k)
            if k >= 1.0:
                cb = f[2]
                self._fade = [0.0, f[1], None, "in"]
                cb()
        else:
            self.fader.color = color.rgba(0, 0, 0, 1 - k)
            if k >= 1.0:
                self._fade = []
                self.fader.enabled = False

    def open_loot(self, enemy: Any) -> None:
        self.loot.open(enemy)

    def open_dialogue(self, npc: Any) -> None:
        self.vendor.close()
        self.trainer.close()
        self.dialogue.open(npc)

    def open_vendor(self, npc: Any) -> None:
        self.vendor.open(npc)

    def open_trainer(self, npc: Any) -> None:
        self.trainer.open(npc)

    def _on_region(self, region: dict, **_: Any) -> None:
        self.region_text.text = region["name"]
        lv = region.get("levels")
        self.region_sub.text = f"Levels {lv[0]}-{lv[1]}" if lv else ""
        self._region_fade = 4.0

    def update(self, dt: float) -> None:
        g = self.game
        self._fps_t -= dt
        if self._fps_t <= 0:
            self._fps_t = 0.5
            if g.settings.show_fps and g.player:
                p = g.player
                self.fps_text.text = f"{g.average_fps():.0f} fps  |  {g.world.env.clock_text}  |  ({p.x:.0f}, {p.z:.0f})"
            else:
                self.fps_text.text = ""
        if g.player and getattr(self, "visible", True):
            r = g.world.zones.region_at(g.player.x, g.player.z) if not g.world.underground else \
                {"id": "mine_interior", "name": "Hollowfang Mine", "levels": [7, 10]}
            if self._region is None or r["id"] != self._region["id"]:
                self._region = r
                events.emit("region_changed", region=r)
            self.nameplates.update(dt)
            self.floating.update(dt)
        self.messages.update(dt)
        self._update_fade(dt)
        if self.worldmap.enabled and int(g.time * 4) % 4 == 0:
            self.worldmap.refresh()
        if self._region_fade > 0:
            self._region_fade -= dt
            a = min(1.0, self._region_fade)
            self.region_text.color = color.rgba(1, 0.85, 0.5, a)
            self.region_sub.color = color.rgba(0.95, 0.9, 0.8, a)

    def set_visible(self, v: bool) -> None:
        for e in (self.fps_text, self.region_text, self.region_sub, self.player_frame, self.hotbar, self.xpbar, self.micro,
                  self.minimap, self.tracker, self.messages.log_root, self.messages.error, self.messages.banner,
                  self.messages.sub):
            e.enabled = v
        if not v:
            self.target_frame.enabled = False
            self.cast_bar.enabled = False
            for w in self.windows:
                if w.enabled:
                    w.close() if hasattr(w, "close") else setattr(w, "enabled", False)
            for pl in self.nameplates.plates:
                pl.enabled = False
            for t in self.floating.pool:
                t.enabled = False
            self.floating.live.clear()
            self.death.enabled = False
        self.visible = v

    def any_window_open(self) -> bool:
        return any(w.enabled for w in self.windows)

    def toggle(self, name: str) -> None:
        w = {"bags": self.bags, "character": self.character, "questlog": self.questlog, "map": self.worldmap}.get(name)
        if w is not None:
            w.toggle()
        elif name == "menu":
            if not self.close_top_window():
                events.emit("toggle_menu")
        else:
            events.emit("toggle_window", name=name)

    def close_top_window(self) -> bool:
        for w in reversed(self.windows):
            if w.enabled:
                if hasattr(w, "close"):
                    w.close()
                else:
                    w.enabled = False
                return True
        return False

    def input(self, key: str) -> bool:
        if self.game.ui_capture_keys:
            return False
        if key == "b":
            self.toggle("bags")
            return True
        if key == "c":
            self.toggle("character")
            return True
        if key == "l":
            self.toggle("questlog")
            return True
        if key == "m":
            self.toggle("map")
            return True
        if key == "escape":
            if self.close_top_window():
                return True
            if self.game.targeting and self.game.targeting.target is not None:
                self.game.targeting.clear()
                return True
        return False
