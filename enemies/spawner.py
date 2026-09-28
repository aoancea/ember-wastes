"""Creates enemies from the spawn tables in zones.json and updates the ones near the player."""
from __future__ import annotations

import math
import random
from typing import Any

from core import data
from enemies.enemy import Enemy

ACTIVE_RADIUS = 150.0
VISIBLE_RADIUS = 190.0


class EnemyManager:
    """Owns every enemy; only enemies near the player (or in combat) run their AI."""

    def __init__(self, game) -> None:
        self.game = game
        self.enemies: list[Enemy] = []
        self._grid: dict[tuple[int, int], list[Enemy]] = {}
        self._grid_timer = 0.0
        self._vis_timer = 0.0

    # ----------------------------------------------------------------- spawning
    def spawn(self, type_id: str, level: int, x: float, z: float, spawn: dict | None = None,
              yaw: float | None = None) -> Enemy:
        from enemies.boss import BOSS_CLASSES
        cls = BOSS_CLASSES.get(type_id, Enemy)
        e = cls(self, type_id, level, x, z, spawn, yaw)
        self.enemies.append(e)
        self._index(e)
        return e

    def remove(self, e: Enemy) -> None:
        if e in self.enemies:
            self.enemies.remove(e)
        e.destroy()
        self._rebuild_grid()

    def spawn_all(self, spawns: list[dict[str, Any]] | None = None) -> None:
        spawns = spawns if spawns is not None else data.zones().get("spawns", [])
        world = self.game.world
        for gi, grp in enumerate(spawns):
            rng = random.Random(7000 + gi)
            levels = grp.get("levels", [1, 1])
            points = grp.get("points")
            if points:
                for p in points:
                    lvl = rng.randint(levels[0], levels[1])
                    yaw = p[2] if len(p) > 2 else None
                    self.spawn(grp["type"], lvl, float(p[0]), float(p[1]), grp, yaw)
                continue
            cx, cz = grp["center"]
            radius = grp.get("radius", 20)
            placed = 0
            tries = 0
            while placed < grp.get("count", 1) and tries < 400:
                tries += 1
                a = rng.random() * math.tau
                d = math.sqrt(rng.random()) * radius
                x, z = cx + math.cos(a) * d, cz + math.sin(a) * d
                if not self._good_spot(world, x, z, grp):
                    continue
                lvl = rng.randint(levels[0], levels[1])
                self.spawn(grp["type"], lvl, x, z, grp)
                placed += 1

    def _good_spot(self, world, x: float, z: float, grp: dict) -> bool:
        h = world.terrain.height_at(x, z)
        if h < (0.2 if not grp.get("allow_water") else -1.0):
            return False
        nx, ny, nz = world.terrain.normal_at(x, z)
        if ny < 0.85:
            return False
        if not grp.get("allow_settlement") and world.zones.in_settlement(x, z, 2.0):
            return False
        x2, z2, hit = world.collision.resolve(x, z, 1.0)
        return not hit

    # ----------------------------------------------------------------- queries
    def _cell(self, x: float, z: float) -> tuple[int, int]:
        return (int(math.floor(x / 16.0)), int(math.floor(z / 16.0)))

    def _index(self, e: Enemy) -> None:
        self._grid.setdefault(self._cell(e.x, e.z), []).append(e)

    def _rebuild_grid(self) -> None:
        self._grid.clear()
        for e in self.enemies:
            if e.state != "respawning":
                self._index(e)

    def enemies_near(self, x: float, z: float, r: float) -> list[Enemy]:
        out = []
        c = 16.0
        for i in range(int(math.floor((x - r) / c)), int(math.floor((x + r) / c)) + 1):
            for j in range(int(math.floor((z - r) / c)), int(math.floor((z + r) / c)) + 1):
                for e in self._grid.get((i, j), ()):
                    if (e.x - x) ** 2 + (e.z - z) ** 2 <= r * r:
                        out.append(e)
        return out

    def living_near(self, x: float, z: float, r: float) -> list[Enemy]:
        return [e for e in self.enemies_near(x, z, r) if not e.dead and e.state != "respawning"]

    # ----------------------------------------------------------------- update
    def update(self, dt: float) -> None:
        p = self.game.player
        if p is None:
            return
        px, pz = p.x, p.z
        a2 = ACTIVE_RADIUS * ACTIVE_RADIUS
        for e in self.enemies:
            dx, dz = e.x - px, e.z - pz
            d2 = dx * dx + dz * dz
            if d2 < a2 or e.state in ("combat", "evade", "respawning") or e.dead:
                lod = 0 if d2 < 45 * 45 else (1 if d2 < 90 * 90 else 3)
                e.update(dt, lod)
        self._grid_timer -= dt
        if self._grid_timer <= 0:
            self._grid_timer = 0.2
            self._rebuild_grid()
        self._vis_timer -= dt
        if self._vis_timer <= 0:
            self._vis_timer = 0.25
            vr = min(VISIBLE_RADIUS, self.game.world.view_distance)
            v2 = vr * vr
            for e in self.enemies:
                dx, dz = e.x - px, e.z - pz
                e.set_visible(dx * dx + dz * dz < v2)

    def reset_all(self) -> None:
        """Called when the player dies: everyone forgets combat."""
        for e in self.enemies:
            if e.state == "combat":
                e.evade()

    def clear(self) -> None:
        for e in self.enemies:
            e.destroy()
        self.enemies.clear()
        self._grid.clear()
