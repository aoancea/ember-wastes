"""Clickable quest objects in the world (driftwood bundles, stolen crates) and the mine entrance."""
from __future__ import annotations

import math
from typing import Any

from core import data
from core.events import events
from core.meshgen import MeshBuilder
from core.rig import copy_part
from core.util import set_yaw


def _driftwood() -> MeshBuilder:
    mb = MeshBuilder()
    bark = (0.62, 0.56, 0.48, 1)
    for i, (a, dy) in enumerate(((0, 0.12), (35, 0.3), (-30, 0.46))):
        r = math.radians(a)
        mb.beam((-math.cos(r) * 0.8, dy, -math.sin(r) * 0.8), (math.cos(r) * 0.8, dy + 0.05, math.sin(r) * 0.8), 0.12,
                bark, segments=5)
    mb.beam((0, 0.0, -0.1), (0, 0.6, 0.1), 0.04, (0.45, 0.3, 0.18, 1), segments=3)
    return mb


def _crate() -> MeshBuilder:
    mb = MeshBuilder()
    mb.box((0, 0.45, 0), (0.9, 0.9, 0.9), (0.55, 0.38, 0.22, 1))
    mb.box((0, 0.45, 0.46), (0.5, 0.35, 0.02), (0.75, 0.12, 0.08, 1))
    mb.box((0, 0.45, 0), (0.92, 0.12, 0.92), (0.3, 0.2, 0.1, 1))
    return mb


def _sparkle() -> MeshBuilder:
    mb = MeshBuilder()
    for i in range(3):
        a = i * 2.1
        mb.box((math.cos(a) * 0.35, 0.9 + i * 0.25, math.sin(a) * 0.35), (0.07, 0.07, 0.07), (1.0, 0.95, 0.5, 1), rot=(45, 45, 0))
    return mb


MODELS = {"driftwood_bundle": _driftwood, "supply_crate": _crate}


class QuestObject:
    """A lootable world object that grants a quest item while the quest needs it."""

    def __init__(self, game, obj_id: str, d: dict[str, Any], x: float, z: float) -> None:
        self.game = game
        self.id = obj_id
        self.d = d
        self.name = d["name"]
        self.title = "Quest Object"
        self.radius = 0.8
        self.height = 1.0
        world = game.world
        self._x, self._z = self._land(world, x, z)
        self._y = world.ground(self._x, self._z)
        self.root = world.actors.attachNewNode(obj_id)
        copy_part((d.get("model", obj_id),), MODELS.get(d.get("model"), _crate), self.root)
        self.spark = copy_part(("quest_sparkle",), _sparkle, self.root)
        self.spark.setShaderInput("u_emissive", 1.5)
        self.root.setPos(self._x, self._y, self._z)
        set_yaw(self.root, (x * 37 + z * 11) % 360)
        self.respawn_t = 0.0
        self.available = True
        self._t = 0.0

    @staticmethod
    def _land(world, x: float, z: float) -> tuple[float, float]:
        """Nudge a position onto dry land if it is under water."""
        for _ in range(20):
            if world.terrain.height_at(x, z) > 0.35:
                break
            cx, cz = 232.0, -262.0
            best = None
            for isl in data.zones()["terrain"]["islands"]:
                d = math.hypot(isl["center"][0] - x, isl["center"][1] - z)
                if best is None or d < best[0]:
                    best = (d, isl["center"])
            if best:
                cx, cz = best[1]
            x += (cx - x) * 0.12
            z += (cz - z) * 0.12
        return x, z

    @property
    def x(self) -> float:
        return self._x

    @property
    def z(self) -> float:
        return self._z

    @property
    def y(self) -> float:
        return self._y

    def wanted(self) -> bool:
        q = self.game.quests
        return q is not None and self.d.get("quest") in q.active and q.needs_item(self.d["item"])

    def interact(self, game) -> None:
        if not self.available:
            return
        if not self.wanted():
            events.emit("message", text="You have no use for that right now.", color=(0.9, 0.9, 0.9))
            return
        p = game.player
        p.rig.play("interact", 0.8)
        if p.inventory.add(self.d["item"], 1):
            events.emit("sound", name="loot")
            self.available = False
            self.respawn_t = float(self.d.get("respawn", 25))
            self.root.hide()
            if game.targeting.target is self:
                game.targeting.clear()

    def update(self, dt: float) -> None:
        self._t += dt
        if not self.available:
            self.respawn_t -= dt
            if self.respawn_t <= 0:
                self.available = True
                self.root.show()
            return
        show = self.wanted()
        if show:
            self.spark.show()
            self.spark.setH(self._t * 90)
            self.spark.setY(math.sin(self._t * 2.5) * 0.15)
        else:
            self.spark.hide()


class MineEntrance:
    """Invisible trigger in front of the mine mouth: right-click or walk in to enter the dungeon."""

    def __init__(self, game, x: float, z: float) -> None:
        self.game = game
        self.name = "Hollowfang Mine"
        self.title = "Dungeon Entrance"
        self._x, self._z = x, z
        self._y = game.world.ground(x, z)
        self.radius = 2.0
        self.height = 4.0
        self.available = True

    @property
    def x(self) -> float:
        return self._x

    @property
    def z(self) -> float:
        return self._z

    @property
    def y(self) -> float:
        return self._y

    def interact(self, game) -> None:
        if game.dungeon is not None:
            game.dungeon.enter()

    def update(self, dt: float) -> None:
        g = self.game
        p = g.player
        if p is None or p.dead or g.dungeon is None or g.dungeon.inside or g.dungeon.cooldown > 0:
            return
        if math.hypot(p.x - self._x, p.z - self._z) < 1.6:
            g.dungeon.enter()


class InteractableManager:
    def __init__(self, game) -> None:
        self.game = game
        self.objects: list[Any] = []
        for oid, d in data.quests().get("objects", {}).items():
            for pos in d["positions"]:
                self.objects.append(QuestObject(game, oid, d, float(pos[0]), float(pos[1])))

    def add(self, obj: Any) -> None:
        self.objects.append(obj)

    def near(self, x: float, z: float, r: float) -> list[Any]:
        r2 = r * r
        return [o for o in self.objects if o.available and (o.x - x) ** 2 + (o.z - z) ** 2 < r2 and not isinstance(o, MineEntrance)]

    def update(self, dt: float) -> None:
        p = self.game.player
        for o in self.objects:
            if p is None or (o.x - p.x) ** 2 + (o.z - p.z) ** 2 < 150 ** 2 or not o.available:
                o.update(dt)
