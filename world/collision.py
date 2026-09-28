"""2.5D collision: circles and oriented boxes on the ground plane, plus walkable platforms."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterator


@dataclass(eq=False)
class Obstacle:
    """Vertical blocker. ``kind`` is 'circle' or 'box' (oriented rectangle)."""

    kind: str
    x: float
    z: float
    r: float = 0.0          # circle radius
    hx: float = 0.0         # box half extents (local x/z)
    hz: float = 0.0
    yaw: float = 0.0        # degrees, Ursina convention
    top: float = 1e9        # obstacles lower than the feet can be walked over
    tag: str = ""
    cos: float = field(default=1.0, init=False)
    sin: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        a = math.radians(self.yaw)
        self.cos, self.sin = math.cos(a), math.sin(a)

    def bound_radius(self) -> float:
        return self.r if self.kind == "circle" else math.hypot(self.hx, self.hz)


@dataclass(eq=False)
class Platform:
    """Walkable oriented rectangle (piers, bridges, floors). Height may ramp along local z."""

    x: float
    z: float
    hx: float
    hz: float
    yaw: float
    y0: float
    y1: float | None = None

    def __post_init__(self) -> None:
        a = math.radians(self.yaw)
        self.cos, self.sin = math.cos(a), math.sin(a)

    def height(self, x: float, z: float) -> float | None:
        dx, dz = x - self.x, z - self.z
        lx = dx * self.cos - dz * self.sin
        lz = dx * self.sin + dz * self.cos
        if abs(lx) > self.hx or abs(lz) > self.hz:
            return None
        if self.y1 is None:
            return self.y0
        t = (lz + self.hz) / (2 * self.hz)
        return self.y0 + (self.y1 - self.y0) * t


class CollisionWorld:
    """Spatial hash of static obstacles and platforms."""

    CELL = 8.0

    def __init__(self, terrain_height: Callable[[float, float], float]) -> None:
        self.terrain_height = terrain_height
        self._cells: dict[tuple[int, int], list[Obstacle]] = {}
        self._pcells: dict[tuple[int, int], list[Platform]] = {}
        self.obstacles: list[Obstacle] = []
        self.platforms: list[Platform] = []
        self.ground_override: Callable[[float, float, float], float | None] | None = None

    def _cells_for(self, x: float, z: float, r: float) -> Iterator[tuple[int, int]]:
        c = self.CELL
        for i in range(int(math.floor((x - r) / c)), int(math.floor((x + r) / c)) + 1):
            for j in range(int(math.floor((z - r) / c)), int(math.floor((z + r) / c)) + 1):
                yield (i, j)

    def add(self, ob: Obstacle) -> Obstacle:
        self.obstacles.append(ob)
        for key in self._cells_for(ob.x, ob.z, ob.bound_radius()):
            self._cells.setdefault(key, []).append(ob)
        return ob

    def add_circle(self, x: float, z: float, r: float, top: float = 1e9, tag: str = "") -> Obstacle:
        return self.add(Obstacle("circle", x, z, r=r, top=top, tag=tag))

    def add_box(self, x: float, z: float, hx: float, hz: float, yaw: float = 0.0, top: float = 1e9,
                tag: str = "") -> Obstacle:
        return self.add(Obstacle("box", x, z, hx=hx, hz=hz, yaw=yaw, top=top, tag=tag))

    def remove(self, ob: Obstacle) -> None:
        if ob in self.obstacles:
            self.obstacles.remove(ob)
        for key in self._cells_for(ob.x, ob.z, ob.bound_radius()):
            lst = self._cells.get(key)
            if lst and ob in lst:
                lst.remove(ob)

    def add_platform(self, p: Platform) -> Platform:
        self.platforms.append(p)
        for key in self._cells_for(p.x, p.z, math.hypot(p.hx, p.hz)):
            self._pcells.setdefault(key, []).append(p)
        return p

    def nearby(self, x: float, z: float, r: float) -> set[Obstacle]:
        out: set[Obstacle] = set()
        for key in self._cells_for(x, z, r):
            lst = self._cells.get(key)
            if lst:
                out.update(lst)
        return out

    # ------------------------------------------------------------------ queries
    def ground_height(self, x: float, z: float, feet_y: float | None = None, step: float = 0.9) -> float:
        """Highest walkable surface under (x, z) that is not above ``feet_y + step``."""
        if self.ground_override is not None:
            g = self.ground_override(x, z, feet_y if feet_y is not None else 1e9)
            if g is not None:
                return g
        h = self.terrain_height(x, z)
        key = (int(math.floor(x / self.CELL)), int(math.floor(z / self.CELL)))
        plats = self._pcells.get(key)
        if plats:
            for p in plats:
                ph = p.height(x, z)
                if ph is not None and ph > h and (feet_y is None or ph <= feet_y + step):
                    h = ph
        return h

    def resolve(self, x: float, z: float, radius: float, feet_y: float = -1e9) -> tuple[float, float, bool]:
        """Push a circle of ``radius`` out of all obstacles. Returns (x, z, collided)."""
        hit = False
        for _ in range(2):
            moved = False
            for ob in self.nearby(x, z, radius + 1.0):
                if feet_y >= ob.top - 0.35:
                    continue
                if ob.kind == "circle":
                    dx, dz = x - ob.x, z - ob.z
                    d2 = dx * dx + dz * dz
                    rr = ob.r + radius
                    if d2 < rr * rr:
                        d = math.sqrt(d2) or 1e-4
                        push = rr - d
                        x += dx / d * push
                        z += dz / d * push
                        moved = hit = True
                else:
                    dx, dz = x - ob.x, z - ob.z
                    # rotate into box space (inverse of yaw)
                    lx = dx * ob.cos - dz * ob.sin
                    lz = dx * ob.sin + dz * ob.cos
                    cx = max(-ob.hx, min(ob.hx, lx))
                    cz = max(-ob.hz, min(ob.hz, lz))
                    ex, ez = lx - cx, lz - cz
                    d2 = ex * ex + ez * ez
                    if d2 < radius * radius:
                        if d2 > 1e-8:
                            d = math.sqrt(d2)
                            nlx = lx + ex / d * (radius - d)
                            nlz = lz + ez / d * (radius - d)
                        else:
                            px = ob.hx - abs(lx)
                            pz = ob.hz - abs(lz)
                            if px < pz:
                                nlx = math.copysign(ob.hx + radius, lx)
                                nlz = lz
                            else:
                                nlx = lx
                                nlz = math.copysign(ob.hz + radius, lz)
                        # back to world space
                        x = ob.x + nlx * ob.cos + nlz * ob.sin
                        z = ob.z - nlx * ob.sin + nlz * ob.cos
                        moved = hit = True
            if not moved:
                break
        return x, z, hit

    def point_inside(self, x: float, z: float, y: float, pad: float = 0.3) -> bool:
        """True if (x, y, z) is inside a solid obstacle (used to keep the camera out of props)."""
        for ob in self.nearby(x, z, pad + 0.5):
            if y > ob.top + 0.2:
                continue
            if ob.kind == "circle":
                if (x - ob.x) ** 2 + (z - ob.z) ** 2 < (ob.r + pad) ** 2:
                    return True
            else:
                dx, dz = x - ob.x, z - ob.z
                lx = dx * ob.cos - dz * ob.sin
                lz = dx * ob.sin + dz * ob.cos
                if abs(lx) < ob.hx + pad and abs(lz) < ob.hz + pad:
                    return True
        return False

    def blocked_line(self, ax: float, az: float, bx: float, bz: float, radius: float = 0.3) -> bool:
        """True if the straight segment a->b passes through a tall obstacle (line of sight)."""
        dist = math.hypot(bx - ax, bz - az)
        steps = max(2, int(dist / 1.5))
        for i in range(1, steps):
            t = i / steps
            x = ax + (bx - ax) * t
            z = az + (bz - az) * t
            for ob in self.nearby(x, z, radius):
                if ob.top < 3.0:
                    continue
                if ob.kind == "circle":
                    if (x - ob.x) ** 2 + (z - ob.z) ** 2 < (ob.r + radius) ** 2:
                        return True
                else:
                    dx, dz = x - ob.x, z - ob.z
                    lx = dx * ob.cos - dz * ob.sin
                    lz = dx * ob.sin + dz * ob.cos
                    if abs(lx) < ob.hx + radius and abs(lz) < ob.hz + radius:
                        return True
        return False
