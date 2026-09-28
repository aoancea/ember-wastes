"""Unit frames (player/target), cast bar, nameplates and floating combat text."""
from __future__ import annotations

import math
from typing import Any

from panda3d.core import Point3
from ursina import Entity, Text, camera, color, window

from combat.combat import difficulty_color
from core.events import events
from ui.widgets import GOLD, TEXT, Bar, label, quad, rgb, world_to_ui

HP_GREEN = color.rgb(0.15, 0.72, 0.18)
RAGE_RED = color.rgb(0.78, 0.12, 0.10)
MANA_BLUE = color.rgb(0.15, 0.35, 0.85)
CAST_YELLOW = color.rgb(0.95, 0.7, 0.15)


class UnitFrame(Entity):
    """Name, level, health bar and resource bar for one unit."""

    def __init__(self, position: tuple, width: float = 0.34, show_resource: bool = True) -> None:
        super().__init__(parent=camera.ui, position=(position[0], position[1], 0))
        self.w = width
        h = 0.105
        self.bg = quad(self, (width / 2, -h / 2), (width, h), color.rgba(0.06, 0.05, 0.04, 0.8), z=0.01)
        self.border = quad(self, (width / 2, -h / 2), (width + 0.005, h + 0.005), color.rgba(0.55, 0.42, 0.22, 0.95), z=0.02)
        self.name_text = label(self, "", (0.012, -0.008), 1.0, TEXT)
        self.level_text = label(self, "", (width - 0.012, -0.008), 0.9, GOLD, origin=(0.5, 0.5))
        self.hp = Bar(self, (0.012, -0.05), (width - 0.024, 0.03), HP_GREEN, text_scale=0.8)
        self.res = Bar(self, (0.012, -0.083), (width - 0.024, 0.02), MANA_BLUE, text_scale=0.65) if show_resource else None
        self.unit: Any = None
        self._name_key: tuple = ()

    def set_unit(self, unit: Any) -> None:
        self.unit = unit
        self._name_key = ()
        self.enabled = unit is not None

    def refresh_name(self, name: str, col: Any, level_str: str) -> None:
        key = (name, tuple(col), level_str)
        if key != self._name_key:
            self._name_key = key
            self.name_text.text = name
            self.name_text.color = rgb(col)
            self.level_text.text = level_str
            # shrink long names so they never run into the level text
            avail = self.w - 0.03 - len(level_str) * 0.0105
            self.name_text.scale = 1.0
            wdt = self.name_text.width
            if wdt > avail:
                self.name_text.scale = max(0.6, avail / wdt)


class PlayerFrame(UnitFrame):
    def __init__(self, game) -> None:
        super().__init__((-window.aspect_ratio / 2 + 0.02, 0.485))
        self.game = game
        self.combat_icon = label(self, "", (self.w - 0.07, -0.008), 0.9, color.rgb(1, 0.3, 0.2), origin=(0.5, 0.5))

    def update(self) -> None:
        p = self.game.player
        if p is None:
            return
        self.refresh_name(p.name, (1, 0.95, 0.85), f"Lv {p.level}")
        self.hp.set(p.hp, p.max_hp)
        if p.resource_type == "rage":
            self.res.set_color(RAGE_RED)
        else:
            self.res.set_color(MANA_BLUE)
        self.res.set(p.resource, p.max_resource)
        t = "In Combat" if p.in_combat else ""
        if self.combat_icon.text != t:
            self.combat_icon.text = t


class TargetFrame(UnitFrame):
    def __init__(self, game) -> None:
        super().__init__((-window.aspect_ratio / 2 + 0.39, 0.485))
        self.game = game
        self.cast = Bar(self, (0.012, -0.122), (self.w - 0.024, 0.018), CAST_YELLOW, text_scale=0.6)
        self.aura_text = label(self, "", (0.012, -0.14), 0.7, color.rgb(1, 0.6, 0.5))
        self.set_unit(None)
        events.on("target_changed", lambda target, **_: self.set_unit(target))
        self._cast_seen = False

    def update(self) -> None:
        u = self.unit
        if u is None:
            return
        p = self.game.player
        if hasattr(u, "take_damage"):
            lvl = u.level
            if getattr(u, "faction", "") == "hostile" and p is not None:
                col = difficulty_color(p.level, lvl)
            elif getattr(u, "faction", "") in ("friendly", "player"):
                col = (0.3, 1.0, 0.35)
            else:
                col = (1.0, 0.9, 0.3)
            tag_ = " Elite" if getattr(u, "elite", False) else ""
            lvl_s = ("Boss" if getattr(u, "boss", False) else f"Lv {lvl}") + tag_
            self.refresh_name(u.name, col, lvl_s)
            if u.dead:
                self.hp.set(0, max(u.max_hp, 1), "Dead")
            else:
                self.hp.set(u.hp, u.max_hp)
            if self.res is not None:
                if getattr(u, "max_resource", 0) > 0:
                    if not self.res.enabled:
                        self.res.enabled = True
                    self.res.set(u.resource, u.max_resource)
                elif self.res.enabled:
                    self.res.enabled = False
            c = getattr(u, "casting", None)
            if c:
                if not self.cast.enabled:
                    self.cast.enabled = True
                self.cast.set(c["t"], c["dur"], c.get("name", "Casting"))
            elif self.cast.enabled:
                self.cast.enabled = False
            auras = [a.name for a in u.auras if a.debuff][:3]
            txt = ", ".join(auras)
            if self.aura_text.text != txt:
                self.aura_text.text = txt
        else:
            self.refresh_name(getattr(u, "name", "?"), (0.3, 1.0, 0.35), getattr(u, "title_short", ""))
            self.hp.set(1, 1, getattr(u, "subtitle", "") or " ")
            if self.res is not None:
                self.res.enabled = False
            self.cast.enabled = False
            if self.aura_text.text:
                self.aura_text.text = ""


class CastBar(Entity):
    """Player cast bar above the hotbar."""

    def __init__(self, game) -> None:
        super().__init__(parent=camera.ui, position=(-0.16, -0.30, 0), enabled=False)
        self.game = game
        self.bar = Bar(self, (0, 0), (0.32, 0.024), CAST_YELLOW, text_scale=0.75)
        events.on("cast_start", self._start)
        events.on("cast_stop", self._stop)

    def _start(self, name: str = "", duration: float = 1.0, **_: Any) -> None:
        self.enabled = True
        self.bar.set_color(CAST_YELLOW)

    def _stop(self, reason: str = "", **_: Any) -> None:
        self.enabled = False

    def update(self) -> None:
        ab = self.game.player.abilities if self.game.player else None
        if ab is None or not ab.casting:
            self.enabled = False
            return
        c = ab.casting
        self.bar.set(c["t"], c["dur"], f"{c['data']['name']}  {max(0.0, c['dur'] - c['t']):.1f}")


# ------------------------------------------------------------------ nameplates
class Nameplate(Entity):
    def __init__(self) -> None:
        super().__init__(parent=camera.ui, z=1, enabled=False)
        self.name_text = Text(parent=self, text="", origin=(0, 0), y=0.018, scale=0.75, color=color.white)
        self.title_text = Text(parent=self, text="", origin=(0, 0), y=0.038, scale=0.62, color=color.rgb(0.8, 0.8, 0.8), use_tags=False)
        self.bar = Bar(self, (-0.045, 0), (0.09, 0.009), color.rgb(0.8, 0.15, 0.1), show_text=False)
        self.marker = Text(parent=self, text="", origin=(0, 0), y=0.07, scale=2.4, color=color.rgb(1, 0.85, 0.1))
        self.unit: Any = None
        self._key: tuple = ()


class Nameplates:
    """Screen-space names/health bars over nearby enemies and NPCs, plus quest markers."""

    POOL = 18

    def __init__(self, game) -> None:
        self.game = game
        self.plates = [Nameplate() for _ in range(self.POOL)]
        self._timer = 0.0
        self._assigned: list[Any] = []

    def _pick_units(self) -> list[Any]:
        g = self.game
        p = g.player
        out = []
        tgt = g.targeting.target
        for e in g.enemies.enemies_near(p.x, p.z, 38):
            if not e.visible or e.state == "respawning":
                continue
            if e.dead and not (e is tgt or e.lootable):
                continue
            out.append((e.distance_to(p) - (100 if e is tgt else 0), e))
        if g.npcs:
            for n in g.npcs.near(p.x, p.z, 40):
                out.append((n.distance_to(p) + 5, n))
        if g.companions:
            for c in g.companions.units:
                if getattr(c, "targetable", False) and not c.dead:
                    out.append((c.distance_to(p), c))
        out.sort(key=lambda t: t[0])
        return [u for _, u in out[: self.POOL]]

    def update(self, dt: float) -> None:
        g = self.game
        if g.player is None:
            return
        self._timer -= dt
        if self._timer <= 0:
            self._timer = 0.15
            self._assigned = self._pick_units()
        base = g.base
        p = g.player
        for i, plate in enumerate(self.plates):
            u = self._assigned[i] if i < len(self._assigned) else None
            if u is None:
                if plate.enabled:
                    plate.enabled = False
                continue
            h = getattr(u, "height", 2.0)
            pos = world_to_ui(base, Point3(u.x, u.y + h + 0.45, u.z))
            if pos is None:
                if plate.enabled:
                    plate.enabled = False
                continue
            if not plate.enabled:
                plate.enabled = True
            dist = math.hypot(u.x - p.x, u.z - p.z)
            s = max(0.65, min(1.0, 14.0 / max(dist, 1.0)))
            plate.position = (pos[0], pos[1], 1)
            plate.scale = s
            is_npc = hasattr(u, "vendor_items")
            marker: Any = ""
            if callable(getattr(u, "quest_marker", None)):
                marker = u.quest_marker()
            if not is_npc and hasattr(u, "take_damage"):
                hostile = getattr(u, "faction", "") == "hostile"
                col = difficulty_color(p.level, u.level) if hostile else (0.35, 1.0, 0.4)
                if u.dead:
                    col = (0.6, 0.6, 0.6)
                title = "(loot)" if getattr(u, "lootable", False) else ""
                key = (u.name, tuple(col), title)
                show_bar = hostile and not u.dead and (u.hp < u.max_hp or u.state == "combat" or u is g.targeting.target)
                if plate.bar.enabled != show_bar:
                    plate.bar.enabled = show_bar
                if show_bar:
                    plate.bar.set(u.hp, u.max_hp)
            else:
                col = (0.35, 1.0, 0.4)
                title = getattr(u, "title", "")
                title = f"<{title}>" if title else ""
                key = (u.name, tuple(col), title)
                show_bar = bool(getattr(u, "targetable", False)) and hasattr(u, "hp") and u.hp < getattr(u, "max_hp", 1)
                if plate.bar.enabled != show_bar:
                    plate.bar.enabled = show_bar
                if show_bar:
                    plate.bar.set(u.hp, u.max_hp)
            if key != plate._key:
                plate._key = key
                plate.name_text.text = u.name
                plate.name_text.color = rgb(col)
                plate.title_text.text = title
            mk, mcol = (marker if isinstance(marker, tuple) else (marker, (1, 0.85, 0.1)))
            if plate.marker.text != mk:
                plate.marker.text = mk
                plate.marker.color = rgb(mcol)


# ------------------------------------------------------------------ floating combat text
class FloatingText:
    """Pooled numbers that float up from where damage/heals happen."""

    POOL = 36

    def __init__(self, game) -> None:
        self.game = game
        self.pool = [Text(parent=camera.ui, text="", origin=(0, 0), z=0.5, enabled=False) for _ in range(self.POOL)]
        self.live: list[dict[str, Any]] = []
        self._next = 0
        events.on("damage", self._on_damage)
        events.on("heal", self._on_heal)
        events.on("miss", self._on_miss)
        events.on("xp_gained", self._on_xp)

    def spawn(self, unit: Any, text: str, col: Any, scale: float = 1.2, life: float = 1.1, rise: float = 1.4,
              offset: float = 0.0) -> None:
        t = self.pool[self._next]
        self._next = (self._next + 1) % self.POOL
        for item in self.live:
            if item["t"] is t:
                self.live.remove(item)
                break
        t.text = text
        t.color = rgb(col)
        t.scale = scale
        t.enabled = True
        import random
        self.live.append({"t": t, "x": unit.x + random.uniform(-0.4, 0.4), "y": unit.y + getattr(unit, "height", 2) * 0.9 + offset,
                          "z": unit.z + random.uniform(-0.4, 0.4), "age": 0.0, "life": life, "rise": rise, "scale": scale,
                          "col": col})

    def _on_damage(self, target, source, amount, crit=False, school="physical", kind="melee", **_: Any) -> None:
        p = self.game.player
        if p is None:
            return
        mine = source is p or getattr(source, "owner", None) is p
        if target is p:
            self.spawn(p, f"-{amount}", (1, 0.25, 0.2), 1.2 if not crit else 1.6, offset=-0.3)
        elif mine:
            col = (1, 1, 1) if school == "physical" else ((1, 0.55, 0.15) if school == "fire" else (0.55, 0.8, 1.0))
            if kind == "dot":
                col = (1, 0.9, 0.3) if school == "physical" else col
            if crit:
                self.spawn(target, f"{amount}!", (1, 0.85, 0.2), 2.1, 1.3, 1.8)
            else:
                self.spawn(target, str(amount), col, 1.35)

    def _on_heal(self, target, amount, crit=False, **_: Any) -> None:
        if target is self.game.player:
            self.spawn(target, f"+{amount}", (0.3, 1, 0.3), 1.4 if not crit else 1.8)

    def _on_miss(self, target, source, result, **_: Any) -> None:
        p = self.game.player
        if source is p or target is p:
            txt = {"miss": "Miss", "dodge": "Dodge", "evade": "Evade"}.get(result, result.title())
            self.spawn(target, txt, (0.85, 0.85, 0.85), 1.1)

    def _on_xp(self, amount: int, reason: str = "", **_: Any) -> None:
        p = self.game.player
        if p is not None and amount > 0:
            self.spawn(p, f"+{amount} XP", (0.75, 0.45, 1.0), 1.0, 1.6, 2.2, offset=0.6)

    def update(self, dt: float) -> None:
        base = self.game.base
        keep = []
        for item in self.live:
            item["age"] += dt
            k = item["age"] / item["life"]
            t = item["t"]
            if k >= 1.0:
                t.enabled = False
                continue
            pos = world_to_ui(base, Point3(item["x"], item["y"] + item["rise"] * k, item["z"]))
            if pos is None:
                if t.enabled:
                    t.enabled = False
                keep.append(item)
                continue
            if not t.enabled:
                t.enabled = True
            pop = 1.0 + max(0.0, 0.25 - item["age"]) * 2.0
            t.position = (pos[0], pos[1], 0.5)
            t.scale = item["scale"] * pop
            c = item["col"]
            t.color = color.rgba(c[0], c[1], c[2], 1.0 if k < 0.6 else 1.0 - (k - 0.6) / 0.4)
            keep.append(item)
        self.live = keep
