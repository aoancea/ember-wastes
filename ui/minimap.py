"""Circular minimap (top-right) and the full world map window (M)."""
from __future__ import annotations

import math

import numpy as np
from PIL import Image
from ursina import Entity, Mesh, Text, Texture, camera, color, window

from core import data, shaders
from core.events import events
from settings import WORLD_MAX_X, WORLD_MAX_Z, WORLD_MIN_X, WORLD_MIN_Z
from ui.widgets import GOLD, TEXT, Panel, label, make_button, rgb

YELLOW = (1.0, 0.85, 0.1)


def _arrow_mesh() -> Mesh:
    return Mesh(vertices=[(0, 0.6, 0), (-0.4, -0.45, 0), (0, -0.2, 0), (0.4, -0.45, 0)],
                triangles=[(0, 1, 2), (0, 2, 3)], mode="triangle")


def np_texture(img: np.ndarray) -> Texture:
    t = Texture(Image.fromarray(img, "RGB"))
    t.filtering = "bilinear"
    return t


class MapSource:
    """Knows how to turn world coordinates into map UVs for the overworld or the mine."""

    def __init__(self, game) -> None:
        self.game = game
        world = game.world
        self.world_tex = np_texture(world.terrain.map_image(2))
        self.world_rect = (WORLD_MIN_X, WORLD_MIN_Z, WORLD_MAX_X - WORLD_MIN_X, WORLD_MAX_Z - WORLD_MIN_Z)
        self.dungeon_tex = None
        self.dungeon_rect = None

    def set_dungeon(self, dungeon) -> None:
        self.dungeon_tex = np_texture(dungeon.map_image(8))
        from world.dungeon import TILE
        self.dungeon_rect = (dungeon.ox, dungeon.oz - dungeon.h * TILE, dungeon.w * TILE, dungeon.h * TILE)

    def current(self) -> tuple[Texture, tuple[float, float, float, float]]:
        if self.game.world.underground and self.dungeon_tex is not None:
            return self.dungeon_tex, self.dungeon_rect
        return self.world_tex, self.world_rect


class Minimap(Entity):
    SIZE = 0.24
    MARKERS = 26

    def __init__(self, game, source: MapSource) -> None:
        super().__init__(parent=camera.ui, position=(window.aspect_ratio / 2 - self.SIZE / 2 - 0.02, 0.5 - self.SIZE / 2 - 0.05, 0))
        self.game = game
        self.src = source
        self.radius_world = 70.0
        self.map = Entity(parent=self, model="quad", scale=self.SIZE, texture=source.world_tex, z=0.01)
        # set the shader on the NodePath directly: Ursina swaps custom shaders on UI entities for its unlit one
        self.map.setShader(shaders.minimap_shader())
        self.map.setShaderInput("u_dark", 0.0)
        self.map.setShaderInput("u_center", (0.5, 0.5))
        self.map.setShaderInput("u_zoom", (0.2, 0.2))
        self.frame = Entity(parent=self, model="circle", scale=self.SIZE + 0.012, color=color.rgba(0.3, 0.22, 0.1, 1), z=0.02)
        self.arrow = Entity(parent=self, model=_arrow_mesh(), scale=0.016, color=color.rgb(1, 0.95, 0.4), z=-0.02)
        self.markers = [Text(parent=self, text="", origin=(0, 0), scale=1.0, z=-0.01, enabled=False) for _ in range(self.MARKERS)]
        self.dots = [Entity(parent=self, model="circle", scale=0.007, color=color.red, z=-0.01, enabled=False,
                            add_to_scene_entities=False) for _ in range(self.MARKERS)]
        self.zone_text = Text(parent=self, text="", origin=(0, 0), y=self.SIZE / 2 + 0.022, scale=0.85, color=GOLD)
        self.clock_text = Text(parent=self, text="", origin=(0, 0), y=-self.SIZE / 2 - 0.018, scale=0.75, color=TEXT)
        self.btn_in = make_button(self, "+", (self.SIZE / 2 - 0.005, -self.SIZE / 2 + 0.02), (0.028, 0.028), lambda: self.zoom(0.75), text_scale=0.9)
        self.btn_out = make_button(self, "-", (self.SIZE / 2 - 0.005, -self.SIZE / 2 - 0.012), (0.028, 0.028), lambda: self.zoom(1.33), text_scale=0.9)
        self.north = Text(parent=self, text="N", origin=(0, 0), y=self.SIZE / 2 - 0.01, scale=0.7, color=color.rgb(1, 0.9, 0.6), z=-0.03)
        self._t = 0.0
        events.on("region_changed", lambda region, **_: setattr(self.zone_text, "text", region["name"]))

    def zoom(self, k: float) -> None:
        self.radius_world = max(30.0, min(160.0, self.radius_world * k))

    def _to_ui(self, dx: float, dz: float) -> tuple[float, float]:
        s = self.SIZE / (2 * self.radius_world)
        return dx * s, dz * s

    def update(self) -> None:
        g = self.game
        p = g.player
        if p is None:
            return
        tex, rect = self.src.current()
        if self.map.texture is not tex:
            self.map.texture = tex
        u = (p.x - rect[0]) / rect[2]
        v = (p.z - rect[1]) / rect[3]
        r = self.radius_world * (0.5 if g.world.underground else 1.0)
        self.map.setShaderInput("u_center", (u, v))
        self.map.setShaderInput("u_zoom", (2 * r / rect[2], 2 * r / rect[3]))
        self._r = r
        self.arrow.rotation_z = p.yaw
        self._t -= 1 / 60
        if self._t > 0:
            return
        self._t = 0.1
        ct = f"{g.world.env.clock_text}"
        if self.clock_text.text != ct:
            self.clock_text.text = ct
        self._place_markers(r)

    def _place_markers(self, r: float) -> None:
        g = self.game
        p = g.player
        s = self.SIZE / (2 * r)
        lim = self.SIZE / 2 * 0.9
        mi = 0
        di = 0
        # NPC quest markers (clamped to the edge so you can navigate to them)
        if g.npcs and not g.world.underground:
            for n in g.npcs.npcs.values():
                mk = n.quest_marker()
                dx, dz = (n.x - p.x) * s, (n.z - p.z) * s
                d = math.hypot(dx, dz)
                if mk:
                    if d > lim:
                        dx, dz = dx / d * lim, dz / d * lim
                    if mi < self.MARKERS:
                        t = self.markers[mi]
                        mi += 1
                        t.enabled = True
                        t.text = mk[0]
                        t.color = rgb(mk[1])
                        t.position = (dx, dz, -0.01)
                elif d < lim and di < self.MARKERS:
                    dot = self.dots[di]
                    di += 1
                    dot.enabled = True
                    dot.color = color.rgb(0.3, 1, 0.35)
                    dot.position = (dx, dz, -0.01)
        # quest objects
        if g.interactables:
            for o in g.interactables.objects:
                if getattr(o, "available", False) and hasattr(o, "wanted") and o.wanted():
                    dx, dz = (o.x - p.x) * s, (o.z - p.z) * s
                    if math.hypot(dx, dz) < lim and di < self.MARKERS:
                        dot = self.dots[di]
                        di += 1
                        dot.enabled = True
                        dot.color = color.rgb(1, 0.85, 0.2)
                        dot.position = (dx, dz, -0.01)
        # hostile units nearby
        for e in g.enemies.enemies_near(p.x, p.z, r):
            if e.dead or e.state == "respawning" or e.passive or di >= self.MARKERS:
                continue
            dx, dz = (e.x - p.x) * s, (e.z - p.z) * s
            if math.hypot(dx, dz) < lim:
                dot = self.dots[di]
                di += 1
                dot.enabled = True
                dot.color = color.rgb(1, 0.2, 0.15) if e.state == "combat" else color.rgb(0.85, 0.3, 0.2)
                dot.position = (dx, dz, -0.01)
        for t in self.markers[mi:]:
            if t.enabled:
                t.enabled = False
        for d in self.dots[di:]:
            if d.enabled:
                d.enabled = False


class WorldMap(Panel):
    """Full map with region names, landmarks, the player and quest hints."""

    def __init__(self, game, source: MapSource) -> None:
        h = 0.86
        w = h * 640 / 768
        super().__init__(position=(0, 0.0), size=(w + 0.04, h + 0.08), title="Ember Wastes", on_close=self.close, z=-0.7)
        self.game = game
        self.src = source
        self.mw, self.mh = w, h
        self.map = Entity(parent=self, model="quad", scale=(w, h), y=-0.02, texture=source.world_tex, z=-0.01)
        self.labels: list[Text] = []
        zd = data.zones()
        for r in zd["regions"]:
            if r["id"] == "cinder_flats":
                continue
            x, z = r.get("map_label", r["center"])
            t = Text(parent=self.map, text=r["name"], origin=(0, 0), scale=(0.85 / w, 0.85 / h), z=-0.02,
                     color=color.rgb(1, 0.9, 0.6))
            t.position = (*self._uv(x, z), -0.02)
            self.labels.append(t)
        for lm in zd["landmarks"]:
            x, z = lm["pos"]
            d = Entity(parent=self.map, model="circle", scale=(0.008 / w, 0.008 / h), color=color.rgb(0.95, 0.9, 0.8), z=-0.02)
            d.position = (*self._uv(x, z), -0.02)
            t = Text(parent=self.map, text=lm["name"], origin=(-0.5, 0), scale=(0.6 / w, 0.6 / h), z=-0.02,
                     color=color.rgb(0.9, 0.9, 0.85))
            t.position = (self._uv(x, z)[0] + 0.012, self._uv(x, z)[1], -0.02)
        self.arrow = Entity(parent=self.map, model=_arrow_mesh(), scale=(0.02 / w, 0.02 / h), color=color.rgb(1, 1, 0.3), z=-0.05)
        self.markers = [Text(parent=self.map, text="", origin=(0, 0), scale=(1.4 / w, 1.4 / h), z=-0.04, enabled=False)
                        for _ in range(24)]
        self.hints = [Entity(parent=self.map, model="circle", color=color.rgba(1, 0.85, 0.1, 0.28), z=-0.03, enabled=False)
                      for _ in range(12)]
        self.legend = label(self, "!  new quest      ?  turn in      gold circles  quest areas",
                            (0, self.size[1] / 2 - 0.058), 0.7, color.rgb(0.8, 0.78, 0.7), origin=(0, 0))
        self.enabled = False

    def _uv(self, x: float, z: float) -> tuple[float, float]:
        rect = self.src.world_rect
        return (x - rect[0]) / rect[2] - 0.5, (z - rect[1]) / rect[3] - 0.5

    def open(self) -> None:
        self.enabled = True
        self.refresh()
        events.emit("sound", name="open")

    def close(self) -> None:
        self.enabled = False

    def toggle(self) -> None:
        self.close() if self.enabled else self.open()

    def refresh(self) -> None:
        g = self.game
        under = g.world.underground
        tex, rect = self.src.current()
        self.map.texture = tex
        for t in self.labels:
            t.enabled = not under
        self.title_text.text = "Hollowfang Mine" if under else "Ember Wastes"
        # markers
        mi = 0
        if not under and g.npcs:
            for n in g.npcs.npcs.values():
                mk = n.quest_marker()
                if mk and mi < len(self.markers):
                    t = self.markers[mi]
                    mi += 1
                    t.enabled = True
                    t.text = mk[0]
                    t.color = rgb(mk[1])
                    t.position = (*self._uv(n.x, n.z), -0.04)
        for t in self.markers[mi:]:
            t.enabled = False
        hi = 0
        if not under and g.quests:
            spots = self._quest_spots()
            for (x, z, r) in spots[: len(self.hints)]:
                hnt = self.hints[hi]
                hi += 1
                hnt.enabled = True
                hnt.position = (*self._uv(x, z), -0.03)
                hnt.scale = (2 * r / rect[2], 2 * r / rect[3])
        for hnt in self.hints[hi:]:
            hnt.enabled = False

    def _quest_spots(self) -> list[tuple[float, float, float]]:
        g = self.game
        q = g.quests
        spots: list[tuple[float, float, float]] = []
        zd = data.zones()
        for qid, st in q.active.items():
            if st["state"] != "active":
                continue
            for i, obj in enumerate(q.defs[qid]["objectives"]):
                if q.progress(qid, i) >= obj.get("count", 1):
                    continue
                types = []
                if obj["type"] == "kill":
                    types = obj["enemy"]
                elif obj["type"] == "collect" and obj.get("drop_from"):
                    types = obj["drop_from"]
                for grp in zd.get("spawns", []):
                    if grp["type"] in types:
                        if "center" in grp:
                            spots.append((grp["center"][0], grp["center"][1], grp.get("radius", 20)))
                        elif grp.get("points"):
                            xs = [p[0] for p in grp["points"]]
                            zs = [p[1] for p in grp["points"]]
                            spots.append((sum(xs) / len(xs), sum(zs) / len(zs), 16))
                if types and any(t in ("tunnel_goblin", "goblin_geomancer", "grakk") for t in types):
                    spots.append((-236, 228, 14))
                if obj["type"] == "explore":
                    lm = next((l for l in zd["landmarks"] if l["id"] == obj["landmark"]), None)
                    if lm:
                        spots.append((lm["pos"][0], lm["pos"][1], lm["radius"]))
                if obj["type"] == "collect" and obj.get("object"):
                    od = data.quests()["objects"][obj["object"]]
                    xs = [p[0] for p in od["positions"]]
                    zs = [p[1] for p in od["positions"]]
                    spots.append((sum(xs) / len(xs), sum(zs) / len(zs), 28))
        return spots

    def update(self) -> None:
        g = self.game
        p = g.player
        if p is None:
            return
        tex, rect = self.src.current()
        self.arrow.position = ((p.x - rect[0]) / rect[2] - 0.5, (p.z - rect[1]) / rect[3] - 0.5, -0.05)
        self.arrow.rotation_z = p.yaw
