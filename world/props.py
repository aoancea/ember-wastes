"""Low-poly prop library (nature and buildings) and the per-chunk static batcher."""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from panda3d.core import NodePath

from core.meshgen import MeshBuilder, rotation_matrix, shade
from settings import WORLD_MIN_X, WORLD_MIN_Z
from world.collision import Platform
from world.sky import PointLight

Col = tuple[float, float, float, float]

BARK: Col = (0.36, 0.25, 0.18, 1)
DEAD_BARK: Col = (0.52, 0.46, 0.40, 1)
CANOPY: Col = (0.44, 0.46, 0.20, 1)
CANOPY_DARK: Col = (0.31, 0.36, 0.16, 1)
ROCK: Col = (0.58, 0.32, 0.22, 1)
ROCK_DARK: Col = (0.42, 0.24, 0.18, 1)
HIDE: Col = (0.74, 0.57, 0.39, 1)
HIDE_DARK: Col = (0.58, 0.40, 0.26, 1)
WOOD: Col = (0.50, 0.34, 0.20, 1)
WOOD_DARK: Col = (0.33, 0.22, 0.14, 1)
THATCH: Col = (0.74, 0.62, 0.36, 1)
BONE: Col = (0.90, 0.85, 0.72, 1)
RED_CLOTH: Col = (0.64, 0.16, 0.12, 1)
STONE: Col = (0.55, 0.50, 0.46, 1)
STONE_DARK: Col = (0.38, 0.35, 0.33, 1)
IRON: Col = (0.30, 0.29, 0.31, 1)
FIRE: Col = (1.0, 0.55, 0.12, 1)
FIRE_CORE: Col = (1.0, 0.85, 0.35, 1)
PALM: Col = (0.30, 0.52, 0.20, 1)
DARK_WOOD_C: Col = (0.2, 0.13, 0.08, 1)


@dataclass
class PropModel:
    """Geometry plus gameplay data for one placed prop (in local space, origin on the ground)."""

    lit: MeshBuilder = field(default_factory=MeshBuilder)
    glow: MeshBuilder | None = None
    colliders: list[tuple] = field(default_factory=list)   # ("circle", x, z, r, top) | ("box", x, z, hx, hz, yaw, top)
    lights: list[tuple] = field(default_factory=list)      # (x, y, z, radius, (r, g, b), intensity, flicker)
    platforms: list[tuple] = field(default_factory=list)   # (x, z, hx, hz, yaw, y0, y1)

    def glow_mb(self) -> MeshBuilder:
        if self.glow is None:
            self.glow = MeshBuilder()
        return self.glow


def _fire(pm: PropModel, x: float, y: float, z: float, size: float = 1.0, light: bool = True) -> None:
    g = pm.glow_mb()
    g.cone((x, y, z), 0.45 * size, 1.1 * size, FIRE, segments=5, jitter=0.1)
    g.cone((x + 0.12 * size, y, z - 0.1 * size), 0.25 * size, 0.8 * size, FIRE_CORE, segments=4)
    g.cone((x - 0.15 * size, y, z + 0.12 * size), 0.22 * size, 0.65 * size, FIRE_CORE, segments=4)
    if light:
        pm.lights.append((x, y + 1.2 * size, z, 14.0 * size, (1.0, 0.55, 0.22), 1.1, 0.18))


# ----------------------------------------------------------------------------- nature
def thorn_tree(rng: random.Random) -> PropModel:
    pm = PropModel()
    mb = pm.lit
    h = rng.uniform(3.2, 5.6)
    lean = rng.uniform(-12, 12)
    pts = [(0.0, 0.0, 0.0)]
    x = z = 0.0
    for i in range(3):
        x += math.sin(math.radians(lean)) * h / 3 + rng.uniform(-0.3, 0.3)
        z += rng.uniform(-0.3, 0.3)
        pts.append((x, h * (i + 1) / 3, z))
    rads = [0.28, 0.2, 0.14, 0.1]
    for i in range(3):
        mb.beam(pts[i], pts[i + 1], rads[i], BARK, segments=5, radius_b=rads[i + 1])
    top = pts[-1]
    canopy_col = CANOPY if rng.random() < 0.75 else CANOPY_DARK
    for k in range(rng.randint(3, 5)):
        ang = rng.uniform(0, math.tau)
        L = rng.uniform(1.2, 2.4)
        end = (top[0] + math.cos(ang) * L, top[1] + rng.uniform(0.2, 0.9), top[2] + math.sin(ang) * L)
        start = pts[rng.randint(2, 3)]
        mb.beam(start, end, 0.09, BARK, segments=4, radius_b=0.05)
        for _ in range(3):
            t = rng.uniform(0.3, 0.9)
            p = tuple(start[i] + (end[i] - start[i]) * t for i in range(3))
            mb.cone(p, 0.03, 0.3, DEAD_BARK, segments=3, rot=(rng.uniform(-90, 90), rng.uniform(0, 360), rng.uniform(-90, 90)))
        if rng.random() < 0.85:
            mb.sphere((end[0], end[1] + 0.15, end[2]), (rng.uniform(0.9, 1.5), 0.32, rng.uniform(0.9, 1.5)),
                      shade(canopy_col, rng.uniform(0.85, 1.1)), detail=1, jitter=0.1)
    pm.colliders.append(("circle", 0.0, 0.0, 0.45, 6))
    return pm


def dead_tree(rng: random.Random) -> PropModel:
    pm = PropModel()
    mb = pm.lit
    h = rng.uniform(2.5, 4.5)
    mb.beam((0, 0, 0), (rng.uniform(-0.4, 0.4), h, rng.uniform(-0.4, 0.4)), 0.22, DEAD_BARK, segments=5, radius_b=0.08)
    for _ in range(rng.randint(2, 4)):
        y = rng.uniform(h * 0.4, h * 0.9)
        ang = rng.uniform(0, math.tau)
        L = rng.uniform(0.8, 1.8)
        mb.beam((0, y, 0), (math.cos(ang) * L, y + rng.uniform(0.3, 1.0), math.sin(ang) * L), 0.08, DEAD_BARK,
                segments=4, radius_b=0.03)
    pm.colliders.append(("circle", 0.0, 0.0, 0.35, 5))
    return pm


def rock(rng: random.Random, size: float | None = None) -> PropModel:
    pm = PropModel()
    s = size if size is not None else rng.uniform(0.6, 2.2)
    col = ROCK if rng.random() < 0.6 else ROCK_DARK
    pm.lit.sphere((0, s * 0.35, 0), (s * rng.uniform(0.9, 1.3), s * rng.uniform(0.6, 0.9), s * rng.uniform(0.8, 1.2)),
                  col, detail=1, noise=0.22, seed=rng.randint(0, 10 ** 6), rot=(0, rng.uniform(0, 360), 0), jitter=0.08)
    for _ in range(rng.randint(0, 2)):
        a = rng.uniform(0, math.tau)
        ss = s * rng.uniform(0.3, 0.55)
        pm.lit.sphere((math.cos(a) * s * 1.1, ss * 0.3, math.sin(a) * s * 1.1), (ss, ss * 0.7, ss), shade(col, 1.1),
                      detail=0, noise=0.25, seed=rng.randint(0, 10 ** 6), jitter=0.08)
    if s > 0.7:
        pm.colliders.append(("circle", 0.0, 0.0, s * 0.95, s * 1.1))
    return pm


def boulder(rng: random.Random) -> PropModel:
    return rock(rng, rng.uniform(2.5, 4.5))


def hoodoo(rng: random.Random) -> PropModel:
    """Tall wind-carved rock spire."""
    pm = PropModel()
    y = 0.0
    r = rng.uniform(1.6, 2.4)
    for i in range(rng.randint(3, 5)):
        hh = rng.uniform(1.5, 3.0)
        col = ROCK if i % 2 == 0 else shade(ROCK_DARK, 1.15)
        pm.lit.cylinder((rng.uniform(-0.2, 0.2), y, rng.uniform(-0.2, 0.2)), r, hh, col, radius_top=r * rng.uniform(0.7, 1.05),
                        segments=6, rot=(0, rng.uniform(0, 60), 0), jitter=0.08)
        y += hh
        r *= rng.uniform(0.75, 1.05)
    pm.lit.sphere((0, y, 0), (r * 1.4, r * 0.6, r * 1.3), ROCK_DARK, detail=0, noise=0.2, seed=rng.randint(0, 999))
    pm.colliders.append(("circle", 0.0, 0.0, 2.2, 14))
    return pm


def dry_bush(rng: random.Random) -> PropModel:
    pm = PropModel()
    col = (0.55, 0.47, 0.25, 1) if rng.random() < 0.7 else (0.45, 0.35, 0.22, 1)
    for _ in range(rng.randint(5, 9)):
        pm.lit.cone((rng.uniform(-0.3, 0.3), 0, rng.uniform(-0.3, 0.3)), 0.06, rng.uniform(0.5, 1.1), col,
                    segments=3, rot=(rng.uniform(-40, 40), rng.uniform(0, 360), rng.uniform(-40, 40)), jitter=0.15)
    return pm


def bones(rng: random.Random) -> PropModel:
    """Bleached ribcage and skull of some huge beast."""
    pm = PropModel()
    mb = pm.lit
    L = rng.uniform(5, 8)
    mb.beam((0, 0.3, -L / 2), (0, 0.5, L / 2), 0.18, BONE, segments=5)
    n = int(L / 0.9)
    for i in range(n):
        z = -L / 2 + (i + 0.5) * L / n
        hgt = 2.2 * math.sin(math.pi * (i + 0.5) / n) + 0.6
        for sx in (-1, 1):
            mb.beam((0, 0.5, z), (sx * 1.2, hgt, z + 0.2), 0.09, BONE, segments=4)
            mb.beam((sx * 1.2, hgt, z + 0.2), (sx * 1.5, 0.0, z + 0.4), 0.08, BONE, segments=4)
    mb.box((0, 0.6, L / 2 + 0.9), (1.2, 1.0, 1.6), BONE, taper=0.8)
    for sx in (-1, 1):
        mb.cone((sx * 0.5, 1.0, L / 2 + 1.2), 0.18, 1.3, BONE, rot=(-60, 0, sx * 25))
    pm.colliders.append(("box", 0.0, 0.0, 1.4, L / 2 + 1.2, 0.0, 2.5))
    return pm


def palm_tree(rng: random.Random) -> PropModel:
    pm = PropModel()
    mb = pm.lit
    h = rng.uniform(4.5, 7.0)
    bend = rng.uniform(0.6, 1.8)
    ang = rng.uniform(0, math.tau)
    pts = []
    for i in range(5):
        t = i / 4
        pts.append((math.cos(ang) * bend * t * t, h * t, math.sin(ang) * bend * t * t))
    for i in range(4):
        mb.beam(pts[i], pts[i + 1], 0.22 - i * 0.03, (0.52, 0.40, 0.26, 1), segments=5, radius_b=0.19 - i * 0.03)
    top = pts[-1]
    for k in range(7):
        a = k / 7 * math.tau + rng.uniform(-0.2, 0.2)
        L = rng.uniform(2.2, 3.0)
        mid = (top[0] + math.cos(a) * L * 0.5, top[1] + 0.5, top[2] + math.sin(a) * L * 0.5)
        end = (top[0] + math.cos(a) * L, top[1] - 0.6, top[2] + math.sin(a) * L)
        w = 0.45
        px, pz = -math.sin(a) * w, math.cos(a) * w
        col = shade(PALM, rng.uniform(0.85, 1.15))
        mb.quad(top, (mid[0] + px, mid[1], mid[2] + pz), mid, (mid[0] - px, mid[1], mid[2] - pz), col, facing=(0, 1, 0), double=True)
        mb.quad(mid, (mid[0] + px, mid[1], mid[2] + pz), end, (mid[0] - px, mid[1], mid[2] - pz), col, facing=(0, 1, 0), double=True)
    for _ in range(3):
        mb.sphere((top[0] + rng.uniform(-0.2, 0.2), top[1] - 0.25, top[2] + rng.uniform(-0.2, 0.2)), 0.16, (0.45, 0.3, 0.15, 1), detail=0)
    pm.colliders.append(("circle", 0.0, 0.0, 0.35, 7))
    return pm


def driftwood(rng: random.Random) -> PropModel:
    pm = PropModel()
    a = rng.uniform(0, 180)
    L = rng.uniform(1.8, 3.2)
    dx, dz = math.cos(math.radians(a)) * L / 2, math.sin(math.radians(a)) * L / 2
    pm.lit.beam((-dx, 0.15, -dz), (dx, 0.2, dz), 0.16, DEAD_BARK, segments=5, radius_b=0.1)
    return pm


# ----------------------------------------------------------------------------- buildings
def orc_hut(rng: random.Random, color: Col | None = None) -> PropModel:
    pm = PropModel()
    mb = pm.lit
    r = rng.uniform(3.0, 3.8)
    hide = color or (HIDE if rng.random() < 0.6 else HIDE_DARK)
    mb.cylinder((0, 0, 0), r, 2.0, hide, radius_top=r * 0.92, segments=9, jitter=0.06)
    mb.cone((0, 2.0, 0), r * 1.12, 2.8, shade(hide, 0.85), segments=9, jitter=0.08)
    for k in range(9):
        a = k / 9 * math.tau
        base = (math.cos(a) * r * 1.05, 1.7, math.sin(a) * r * 1.05)
        tip = (math.cos(a) * r * 0.2, 5.8, math.sin(a) * r * 0.2)
        mb.beam(base, tip, 0.08, WOOD_DARK, segments=4)
        if k % 2 == 0:
            mb.cone((math.cos(a) * r * 1.05, 0.2, math.sin(a) * r * 1.05), 0.12, 1.1, BONE,
                    rot=(0, 0, 0), segments=4)
    # doorway facing +z
    mb.box((0, 0.9, r * 0.95), (1.3, 1.8, 0.3), (0.12, 0.08, 0.06, 1))
    mb.beam((-0.8, 0, r + 0.1), (-0.8, 2.2, r + 0.1), 0.1, WOOD, segments=4)
    mb.beam((0.8, 0, r + 0.1), (0.8, 2.2, r + 0.1), 0.1, WOOD, segments=4)
    mb.beam((-1.0, 2.2, r + 0.1), (1.0, 2.2, r + 0.1), 0.1, WOOD, segments=4)
    mb.box((0, 2.5, r + 0.15), (0.5, 0.4, 0.1), RED_CLOTH)
    pm.colliders.append(("circle", 0.0, 0.0, r + 0.1, 6.5))
    return pm


def troll_hut(rng: random.Random) -> PropModel:
    pm = PropModel()
    mb = pm.lit
    r = rng.uniform(2.6, 3.2)
    floor = 1.2
    for k in range(6):
        a = k / 6 * math.tau
        mb.beam((math.cos(a) * r * 0.9, -0.5, math.sin(a) * r * 0.9), (math.cos(a) * r * 0.9, floor, math.sin(a) * r * 0.9), 0.14, WOOD_DARK, segments=4)
    mb.cylinder((0, floor, 0), r * 1.05, 0.2, WOOD, segments=8)
    mb.cylinder((0, floor + 0.2, 0), r * 0.9, 1.9, (0.62, 0.52, 0.32, 1), radius_top=r * 0.85, segments=8, jitter=0.08)
    mb.cone((0, floor + 2.0, 0), r * 1.35, 2.6, THATCH, segments=8, jitter=0.1)
    mb.box((0, floor + 1.0, r * 0.85), (1.1, 1.5, 0.3), (0.1, 0.07, 0.05, 1))
    # ladder
    for i in range(4):
        mb.box((0, 0.1 + i * 0.3, r * 1.25 + 0.2 - i * 0.12), (0.9, 0.06, 0.12), WOOD)
    for sx in (-1, 1):
        mb.beam((sx * 0.45, 0.0, r * 1.35 + 0.2), (sx * 0.45, floor + 0.2, r * 1.0), 0.06, WOOD, segments=4)
    mask = (0.85, 0.45, 0.2, 1)
    mb.box((0, floor + 2.3, r * 0.95), (0.6, 0.7, 0.12), mask)
    mb.box((0, floor + 2.3, r * 1.0), (0.4, 0.12, 0.06), (0.1, 0.1, 0.1, 1))
    pm.colliders.append(("circle", 0.0, 0.0, r + 0.1, 6))
    return pm


def palisade(rng: random.Random, length: float = 10.0) -> PropModel:
    pm = PropModel()
    n = max(2, int(length / 0.55))
    for i in range(n):
        x = -length / 2 + (i + 0.5) * length / n
        h = rng.uniform(3.0, 3.8)
        pm.lit.cylinder((x, 0, 0), 0.26, h, shade(WOOD, rng.uniform(0.85, 1.1)), segments=5)
        pm.lit.cone((x, h, 0), 0.26, 0.6, WOOD_DARK, segments=5)
    pm.lit.box((0, 1.2, -0.3), (length, 0.2, 0.15), WOOD_DARK)
    pm.lit.box((0, 2.4, -0.3), (length, 0.2, 0.15), WOOD_DARK)
    pm.colliders.append(("box", 0.0, 0.0, length / 2, 0.35, 0.0, 4))
    return pm


def watchtower(rng: random.Random) -> PropModel:
    pm = PropModel()
    mb = pm.lit
    h = 7.0
    for sx in (-1, 1):
        for sz in (-1, 1):
            mb.beam((sx * 1.6, 0, sz * 1.6), (sx * 1.2, h, sz * 1.2), 0.18, WOOD_DARK, segments=5)
    for y in (2.5, 5.0):
        for sx, sz, ex, ez in ((-1.4, -1.4, 1.4, 1.4), (1.4, -1.4, -1.4, 1.4)):
            mb.beam((sx, y - 1.2, sz), (ex, y + 1.2, ez), 0.07, WOOD, segments=4)
    mb.box((0, h, 0), (3.4, 0.25, 3.4), WOOD)
    for sx in (-1, 1):
        mb.box((sx * 1.6, h + 0.6, 0), (0.15, 1.0, 3.4), WOOD_DARK)
        mb.box((0, h + 0.6, sx * 1.6), (3.4, 1.0, 0.15), WOOD_DARK)
    for sx in (-1, 1):
        for sz in (-1, 1):
            mb.beam((sx * 1.5, h, sz * 1.5), (sx * 1.5, h + 2.4, sz * 1.5), 0.1, WOOD_DARK, segments=4)
    mb.cone((0, h + 2.3, 0), 2.9, 1.8, HIDE_DARK, segments=4, rot=(0, 45, 0))
    mb.box((0, h + 1.4, 1.75), (1.4, 0.8, 0.05), RED_CLOTH)
    pm.colliders.append(("box", 0.0, 0.0, 1.8, 1.8, 0.0, 10))
    _fire(pm, 0.0, h + 0.15, 0.0, 0.45)
    return pm


def campfire(rng: random.Random) -> PropModel:
    pm = PropModel()
    for k in range(8):
        a = k / 8 * math.tau
        pm.lit.sphere((math.cos(a) * 0.9, 0.12, math.sin(a) * 0.9), 0.24, STONE_DARK, detail=0, noise=0.2, seed=k)
    for k in range(4):
        a = k / 4 * math.pi + 0.3
        pm.lit.beam((math.cos(a) * 0.6, 0.1, math.sin(a) * 0.6), (-math.cos(a) * 0.6, 0.25, -math.sin(a) * 0.6), 0.09, WOOD_DARK, segments=4)
    _fire(pm, 0.0, 0.1, 0.0, 0.9)
    pm.colliders.append(("circle", 0.0, 0.0, 1.0, 0.5))
    return pm


def bonfire(rng: random.Random) -> PropModel:
    pm = PropModel()
    for k in range(10):
        a = k / 10 * math.tau
        pm.lit.sphere((math.cos(a) * 1.8, 0.2, math.sin(a) * 1.8), 0.42, STONE_DARK, detail=0, noise=0.2, seed=k)
    for k in range(6):
        a = k / 6 * math.tau
        pm.lit.beam((math.cos(a) * 1.3, 0.0, math.sin(a) * 1.3), (0, 2.0, 0), 0.13, WOOD_DARK, segments=4)
    _fire(pm, 0.0, 0.2, 0.0, 1.8)
    pm.lights[-1] = (0.0, 2.5, 0.0, 22.0, (1.0, 0.55, 0.22), 1.4, 0.18)
    pm.colliders.append(("circle", 0.0, 0.0, 2.2, 3))
    return pm


def brazier(rng: random.Random) -> PropModel:
    pm = PropModel()
    for k in range(3):
        a = k / 3 * math.tau
        pm.lit.beam((math.cos(a) * 0.45, 0, math.sin(a) * 0.45), (math.cos(a) * 0.2, 1.1, math.sin(a) * 0.2), 0.05, IRON, segments=4)
    pm.lit.cylinder((0, 1.0, 0), 0.35, 0.35, IRON, radius_top=0.55, segments=7)
    _fire(pm, 0.0, 1.3, 0.0, 0.55)
    pm.colliders.append(("circle", 0.0, 0.0, 0.5, 1.6))
    return pm


def crate(rng: random.Random) -> PropModel:
    pm = PropModel()
    s = rng.uniform(0.8, 1.1)
    pm.lit.box((0, s / 2, 0), (s, s, s), WOOD, rot=(0, rng.uniform(0, 30), 0))
    pm.lit.box((0, s / 2, 0), (s * 1.02, s * 0.15, s * 1.02), WOOD_DARK, rot=(0, rng.uniform(0, 30), 0))
    pm.colliders.append(("circle", 0.0, 0.0, s * 0.6, s))
    return pm


def barrel(rng: random.Random) -> PropModel:
    pm = PropModel()
    pm.lit.cylinder((0, 0, 0), 0.42, 1.1, WOOD, radius_top=0.42, segments=8)
    pm.lit.cylinder((0, 0.25, 0), 0.45, 0.08, IRON, segments=8)
    pm.lit.cylinder((0, 0.8, 0), 0.45, 0.08, IRON, segments=8)
    pm.colliders.append(("circle", 0.0, 0.0, 0.5, 1.1))
    return pm


def totem(rng: random.Random) -> PropModel:
    pm = PropModel()
    mb = pm.lit
    h = rng.uniform(4.5, 6.0)
    mb.cylinder((0, 0, 0), 0.35, h, WOOD, radius_top=0.3, segments=6)
    for i, y in enumerate((1.3, 2.7, 4.0)):
        if y > h - 0.5:
            break
        c = (0.7, 0.2, 0.15, 1) if i % 2 == 0 else (0.2, 0.45, 0.6, 1)
        mb.box((0, y, 0.25), (0.6, 0.7, 0.35), c)
        mb.box((0, y + 0.1, 0.44), (0.4, 0.12, 0.05), (0.95, 0.9, 0.8, 1))
        mb.cone((0, y - 0.2, 0.44), 0.08, 0.25, BONE, rot=(90, 0, 0))
    mb.beam((-1.2, h - 0.5, 0), (1.2, h - 0.2, 0), 0.08, WOOD_DARK, segments=4)
    mb.quad((-1.1, h - 0.45, 0.05), (1.1, h - 0.2, 0.05), (1.0, h - 2.3, 0.05), (-1.0, h - 2.4, 0.05), RED_CLOTH,
            facing=(0, 0, 1), double=True)
    pm.colliders.append(("circle", 0.0, 0.0, 0.45, 6))
    return pm


def banner(rng: random.Random, color: Col = RED_CLOTH) -> PropModel:
    pm = PropModel()
    mb = pm.lit
    mb.cylinder((0, 0, 0), 0.12, 5.5, WOOD_DARK, segments=5)
    mb.beam((0, 5.2, 0), (1.4, 5.2, 0), 0.07, WOOD_DARK, segments=4)
    mb.quad((0.05, 5.1, 0.02), (1.35, 5.1, 0.02), (1.3, 2.8, 0.02), (0.1, 2.6, 0.02), color, facing=(0, 0, 1), double=True)
    mb.box((0.7, 4.1, 0.03), (0.5, 0.5, 0.02), (0.1, 0.08, 0.06, 1))
    pm.colliders.append(("circle", 0.0, 0.0, 0.2, 6))
    return pm


def weapon_rack(rng: random.Random) -> PropModel:
    pm = PropModel()
    mb = pm.lit
    for sx in (-1, 1):
        mb.beam((sx * 1.0, 0, 0), (sx * 1.0, 1.6, 0), 0.07, WOOD_DARK, segments=4)
    mb.beam((-1.1, 1.4, 0), (1.1, 1.4, 0), 0.06, WOOD_DARK, segments=4)
    for i in range(4):
        x = -0.7 + i * 0.45
        mb.beam((x, 0.1, 0.15), (x, 1.7, -0.05), 0.04, WOOD, segments=4)
        mb.box((x, 1.6, -0.03), (0.05, 0.3, 0.2), (0.62, 0.62, 0.66, 1))
    pm.colliders.append(("box", 0.0, 0.0, 1.1, 0.3, 0.0, 1.7))
    return pm


def anvil(rng: random.Random) -> PropModel:
    pm = PropModel()
    pm.lit.cylinder((0, 0, 0), 0.4, 0.6, WOOD_DARK, segments=6)
    pm.lit.box((0, 0.75, 0), (0.9, 0.3, 0.4), IRON, taper=1.2)
    pm.lit.cone((0.5, 0.8, 0), 0.12, 0.35, IRON, rot=(0, 0, -90), segments=4)
    pm.colliders.append(("circle", 0.0, 0.0, 0.55, 1.0))
    return pm


def forge(rng: random.Random) -> PropModel:
    pm = PropModel()
    pm.lit.box((0, 0.6, 0), (2.2, 1.2, 1.6), STONE_DARK)
    pm.lit.box((0, 1.25, 0), (2.4, 0.15, 1.8), STONE)
    pm.lit.cylinder((0.6, 1.3, -0.4), 0.3, 2.6, STONE_DARK, radius_top=0.22, segments=6)
    pm.glow_mb().box((-0.2, 1.36, 0.1), (1.3, 0.1, 1.0), (1.0, 0.45, 0.1, 1))
    pm.lights.append((0.0, 2.0, 0.0, 10.0, (1.0, 0.45, 0.15), 1.0, 0.1))
    pm.colliders.append(("box", 0.0, 0.0, 1.2, 0.9, 0.0, 3))
    return pm


def drying_rack(rng: random.Random) -> PropModel:
    pm = PropModel()
    for sx in (-1, 1):
        pm.lit.beam((sx * 1.2, 0, 0), (sx * 1.2, 2.0, 0), 0.07, WOOD_DARK, segments=4)
    pm.lit.beam((-1.3, 1.9, 0), (1.3, 1.9, 0), 0.06, WOOD_DARK, segments=4)
    for i in range(3):
        x = -0.75 + i * 0.75
        pm.lit.quad((x - 0.3, 1.85, 0.02), (x + 0.3, 1.85, 0.02), (x + 0.25, 0.8, 0.02), (x - 0.25, 0.9, 0.02),
                    shade(HIDE, 0.9 + 0.1 * i), facing=(0, 0, 1), double=True)
    pm.colliders.append(("box", 0.0, 0.0, 1.3, 0.2, 0.0, 2.0))
    return pm


def cook_pot(rng: random.Random) -> PropModel:
    pm = PropModel()
    for k in range(3):
        a = k / 3 * math.tau
        pm.lit.beam((math.cos(a) * 0.9, 0, math.sin(a) * 0.9), (0, 1.8, 0), 0.06, WOOD_DARK, segments=4)
    pm.lit.cylinder((0, 0.35, 0), 0.5, 0.55, IRON, radius_top=0.55, segments=8)
    _fire(pm, 0.0, 0.0, 0.0, 0.5)
    pm.colliders.append(("circle", 0.0, 0.0, 0.7, 1.0))
    return pm


def tent(rng: random.Random, color: Col = (0.55, 0.50, 0.40, 1)) -> PropModel:
    pm = PropModel()
    w, L, h = 3.0, 4.0, 2.4
    mb = pm.lit
    for sx in (-1, 1):
        mb.quad((0, h, -L / 2), (0, h, L / 2), (sx * w / 2, 0, L / 2), (sx * w / 2, 0, -L / 2), color,
                facing=(sx, 0.6, 0), double=True, jitter=0.05)
    mb.triangle((0, h, -L / 2), (-w / 2, 0, -L / 2), (w / 2, 0, -L / 2), shade(color, 0.85), facing=(0, 0, -1))
    mb.beam((0, 0, L / 2 + 0.1), (0, h + 0.3, L / 2 + 0.1), 0.06, WOOD_DARK, segments=4)
    mb.beam((0, h, -L / 2), (0, h, L / 2 + 0.1), 0.05, WOOD_DARK, segments=4)
    pm.colliders.append(("box", 0.0, 0.0, w / 2, L / 2, 0.0, 3))
    return pm


def wagon(rng: random.Random, burned: bool = False) -> PropModel:
    pm = PropModel()
    mb = pm.lit
    wood = (0.18, 0.14, 0.12, 1) if burned else WOOD
    mb.box((0, 1.0, 0), (1.8, 0.2, 3.4), wood)
    for sx in (-1, 1):
        mb.box((sx * 0.9, 1.35, 0), (0.1, 0.5, 3.4), shade(wood, 0.9))
    mb.box((0, 1.35, -1.7), (1.8, 0.5, 0.1), shade(wood, 0.9))
    for sx in (-1, 1):
        for sz in (-1, 1):
            mb.cylinder((sx * 1.0, 0.55, sz * 1.1), 0.55, 0.12, shade(wood, 0.8), segments=8, rot=(0, 0, 90))
    mb.beam((0, 0.8, 1.7), (0, 0.5, 3.4), 0.07, wood, segments=4)
    if burned:
        mb.box((0.3, 1.2, 0.3), (0.9, 0.3, 1.0), (0.1, 0.09, 0.09, 1), rot=(0, 20, 8))
        mb.sphere((0.2, 1.5, -0.8), (0.5, 0.35, 0.5), (0.3, 0.25, 0.22, 1), detail=0)
        mb.cylinder((-0.3, 1.1, 0.6), 0.35, 0.8, (0.15, 0.12, 0.1, 1), segments=6, rot=(80, 0, 10))
    else:
        mb.cylinder((0, 1.2, 0.4), 0.4, 0.9, WOOD, segments=7, rot=(90, 0, 0))
    pm.colliders.append(("box", 0.0, 0.0, 1.2, 1.9, 0.0, 2.5))
    return pm


def well(rng: random.Random) -> PropModel:
    pm = PropModel()
    mb = pm.lit
    mb.cylinder((0, 0, 0), 1.2, 0.9, STONE, segments=9)
    mb.cylinder((0, 0.85, 0), 1.0, 0.08, (0.2, 0.35, 0.45, 1), segments=9)
    for sx in (-1, 1):
        mb.beam((sx * 1.1, 0.8, 0), (sx * 1.1, 2.6, 0), 0.09, WOOD_DARK, segments=4)
    mb.beam((-1.3, 2.5, 0), (1.3, 2.5, 0), 0.07, WOOD_DARK, segments=4)
    mb.cone((0, 2.55, 0), 1.7, 1.0, HIDE_DARK, segments=4, rot=(0, 45, 0))
    pm.colliders.append(("circle", 0.0, 0.0, 1.3, 3))
    return pm


def longhouse(rng: random.Random, w: float = 10.0, L: float = 16.0) -> PropModel:
    """Open-sided pavilion (the inn): roof on posts, walkable interior."""
    pm = PropModel()
    mb = pm.lit
    h = 3.6
    ridge = 6.4
    nx = int(L / 4) + 1
    for i in range(nx):
        z = -L / 2 + i * L / (nx - 1)
        for sx in (-1, 1):
            mb.beam((sx * w / 2, 0, z), (sx * w / 2, h + 0.2, z), 0.22, WOOD_DARK, segments=5)
            pm.colliders.append(("circle", sx * w / 2, z, 0.35, 7))
    for sx in (-1, 1):
        mb.quad((0, ridge, -L / 2 - 0.8), (0, ridge, L / 2 + 0.8), (sx * (w / 2 + 1.2), h - 0.3, L / 2 + 0.8),
                (sx * (w / 2 + 1.2), h - 0.3, -L / 2 - 0.8), HIDE, facing=(sx, 1, 0), double=True, jitter=0.05)
        mb.beam((sx * w / 2, h, -L / 2), (sx * w / 2, h, L / 2), 0.14, WOOD_DARK, segments=4)
    mb.beam((0, ridge, -L / 2 - 0.9), (0, ridge, L / 2 + 0.9), 0.16, WOOD_DARK, segments=4)
    for sz in (-1, 1):
        mb.triangle((0, ridge, sz * L / 2), (-w / 2, h, sz * L / 2), (w / 2, h, sz * L / 2), shade(HIDE, 0.8),
                    facing=(0, 0, sz), double=True)
        for sx in (-1, 1):
            mb.cone((sx * 0.4, ridge + 0.2, sz * (L / 2 + 0.9)), 0.12, 1.3, BONE, rot=(sz * 50, 0, sx * 30), segments=4)
    mb.box((0, 0.05, 0), (w - 0.6, 0.1, L - 0.6), shade(WOOD, 0.8))
    pm.platforms.append((0.0, 0.0, (w - 0.6) / 2, (L - 0.6) / 2, 0.0, 0.1, None))
    # bar counter and tables
    mb.box((-w / 2 + 1.4, 0.6, -L / 2 + 3.5), (1.0, 1.1, 5.0), WOOD_DARK)
    pm.colliders.append(("box", -w / 2 + 1.4, -L / 2 + 3.5, 0.55, 2.5, 0.0, 7))
    for tz in (-1.5, 3.0):
        mb.box((1.2, 0.75, tz), (2.2, 0.12, 1.2), WOOD)
        for sx in (-1, 1):
            for sz in (-1, 1):
                mb.beam((1.2 + sx * 0.9, 0, tz + sz * 0.45), (1.2 + sx * 0.9, 0.72, tz + sz * 0.45), 0.05, WOOD_DARK, segments=4)
        for sx in (-1, 1):
            mb.box((1.2, 0.4, tz + sx * 1.0), (2.0, 0.1, 0.4), WOOD)
        pm.colliders.append(("box", 1.2, tz, 1.1, 0.7, 0.0, 0.8))
    for k, (x, z) in enumerate(((-w / 2 + 1.4, -L / 2 + 1.0), (-w / 2 + 1.0, L / 2 - 1.5), (w / 2 - 1.0, L / 2 - 1.2))):
        mb.cylinder((x, 0.1, z), 0.42, 1.1, WOOD, segments=8)
    # hanging lanterns
    for z in (-L / 4, L / 4):
        pm.glow_mb().box((0, h - 0.4, z), (0.3, 0.4, 0.3), (1.0, 0.8, 0.4, 1))
        pm.lights.append((0.0, h - 0.6, z, 12.0, (1.0, 0.65, 0.3), 0.9, 0.08))
    return pm


def mine_entrance(rng: random.Random) -> PropModel:
    pm = PropModel()
    mb = pm.lit
    w, h, d = 5.0, 4.6, 5.0
    mb.box((0, h / 2, -d / 2), (w - 0.4, h, d), (0.02, 0.015, 0.01, 1))
    for z in (0.0, -2.0):
        for sx in (-1, 1):
            mb.beam((sx * w / 2, 0, z), (sx * w / 2, h, z), 0.26, WOOD_DARK, segments=5)
        mb.box((0, h, z), (w + 0.8, 0.5, 0.5), WOOD_DARK)
    mb.box((0, h + 0.8, 0.3), (2.6, 0.7, 0.12), WOOD)
    for sx in (-1, 1):
        mb.box((sx * 0.5, 0.05, 2.5), (0.1, 0.1, 6.0), IRON)
    for i in range(6):
        mb.box((0, 0.02, 0.2 + i * 0.9), (1.4, 0.06, 0.25), WOOD_DARK)
    mb.box((0.0, 0.7, 3.4), (1.3, 0.8, 1.8), IRON, taper=1.2)
    for sx in (-1, 1):
        for sz in (-1, 1):
            mb.cylinder((sx * 0.55, 0.2, 3.4 + sz * 0.6), 0.2, 0.1, DARK_WOOD_C, segments=6, rot=(0, 0, 90))
    for sx in (-1, 1):
        pm.glow_mb().box((sx * (w / 2 + 0.2), 3.2, 0.3), (0.3, 0.4, 0.3), (1.0, 0.75, 0.35, 1))
        pm.lights.append((sx * (w / 2 + 0.2), 3.0, 0.8, 10.0, (1.0, 0.6, 0.25), 1.0, 0.1))
    pm.colliders.append(("box", -w / 2 - 0.3, -d / 2, 0.4, d / 2, 0.0, 6))
    pm.colliders.append(("box", w / 2 + 0.3, -d / 2, 0.4, d / 2, 0.0, 6))
    pm.colliders.append(("box", 0.0, 3.4, 0.8, 1.0, 0.0, 1.4))
    return pm



def stone_ruin(rng: random.Random) -> PropModel:
    """Broken round stone watchtower."""
    pm = PropModel()
    mb = pm.lit
    r = 3.2
    segs = 10
    for k in range(segs):
        a0 = k / segs * math.tau
        a1 = (k + 1) / segs * math.tau
        hh = 4.0 + 5.0 * abs(math.sin(k * 1.7)) if k not in (2, 3) else 0.8
        am = (a0 + a1) / 2
        mb.box((math.cos(am) * r, hh / 2, math.sin(am) * r), (2 * r * math.sin(math.pi / segs) + 0.1, hh, 0.9),
               shade(STONE, 0.85 + 0.2 * rng.random()), rot=(0, -math.degrees(am) + 90, 0))
    for _ in range(6):
        a = rng.uniform(0, math.tau)
        d = rng.uniform(r + 1, r + 4)
        mb.box((math.cos(a) * d, 0.3, math.sin(a) * d), (rng.uniform(0.6, 1.2), 0.5, rng.uniform(0.6, 1.0)), STONE_DARK,
               rot=(rng.uniform(-15, 15), rng.uniform(0, 90), rng.uniform(-15, 15)))
    for k in range(segs):
        if k in (2, 3):
            continue
        am = (k + 0.5) / segs * math.tau
        pm.colliders.append(("circle", math.cos(am) * r, math.sin(am) * r, 1.1, 9))
    return pm


def dock(rng: random.Random, length: float = 14.0, height: float = 1.2) -> PropModel:
    pm = PropModel()
    mb = pm.lit
    w = 2.6
    n = int(length / 0.5)
    for i in range(n):
        z = i * 0.5 + 0.25
        mb.box((rng.uniform(-0.05, 0.05), height, z), (w, 0.12, 0.45), shade(WOOD, rng.uniform(0.85, 1.1)))
    for i in range(int(length / 3) + 1):
        z = i * 3.0
        for sx in (-1, 1):
            mb.beam((sx * (w / 2), -4.0, z), (sx * (w / 2), height + 0.6, z), 0.14, WOOD_DARK, segments=5)
    pm.platforms.append((0.0, length / 2, w / 2, length / 2, 0.0, height + 0.06, None))
    return pm


def shipwreck(rng: random.Random) -> PropModel:
    pm = PropModel()
    mb = pm.lit
    L = 16.0
    for i in range(9):
        z = -L / 2 + i * L / 8
        width = 3.2 * math.sin(math.pi * (i + 0.5) / 9) + 0.8
        for sx in (-1, 1):
            if i in (5, 6) and sx == 1:
                continue
            mb.beam((sx * width, 0.0, z), (sx * width * 1.1, 3.2, z + 0.2), 0.14, DEAD_BARK, segments=4)
    for k in range(5):
        y = 0.4 + k * 0.6
        for sx in (-1, 1):
            if sx == 1 and k in (2, 3):
                continue
            mb.box((sx * 3.0, y, 0), (0.12, 0.4, L * (0.95 - k * 0.07)), shade(WOOD_DARK, 1 + 0.05 * k), rot=(0, 0, sx * -12))
    mb.beam((0, 0, -2), (0.8, 9.0, -1.6), 0.25, DEAD_BARK, segments=6)
    mb.beam((-1.8, 7.0, -1.7), (2.6, 7.2, -1.8), 0.1, DEAD_BARK, segments=4)
    mb.quad((-1.4, 6.9, -1.6), (2.0, 7.1, -1.6), (1.6, 4.2, -1.2), (-1.0, 4.5, -1.1), (0.72, 0.68, 0.58, 1), facing=(0, 0, 1), double=True)
    pm.colliders.append(("box", 0.0, 0.0, 3.4, L / 2, 0.0, 9))
    return pm



def ironmaw_gate(rng: random.Random, doors: bool = True) -> PropModel:
    """The huge fortress gate at the north edge of the zone (faces -z, towards the plaza)."""
    pm = PropModel()
    mb = pm.lit
    stone = (0.46, 0.40, 0.37, 1)
    stone_d = (0.33, 0.29, 0.27, 1)
    wall_h = 22.0
    # curtain walls reaching into the cliffs
    for sx in (-1, 1):
        mb.box((sx * 31.0, wall_h / 2, 0), (26.0, wall_h, 7.0), stone, jitter=0.05)
        mb.box((sx * 31.0, wall_h + 0.6, -3.2), (26.0, 1.2, 1.0), stone_d)
        for i in range(9):
            mb.box((sx * (19.5 + i * 2.8), wall_h + 1.6, -3.2), (1.4, 1.2, 1.0), stone_d)
        pm.colliders.append(("box", sx * 31.0, 0.0, 13.0, 3.5, 0.0, 36))
    # twin towers
    for sx in (-1, 1):
        tx = sx * 12.5
        mb.box((tx, 15.0, 0), (10.0, 30.0, 11.0), stone, taper=0.88, jitter=0.05)
        mb.box((tx, 30.6, 0), (10.6, 1.4, 11.6), stone_d)
        for cx in (-4, -1.3, 1.3, 4):
            mb.box((tx + cx, 32.0, -5.4), (1.4, 1.6, 0.9), stone_d)
            mb.box((tx + cx, 32.0, 5.4), (1.4, 1.6, 0.9), stone_d)
        for cz in (-4, 0, 4):
            mb.box((tx + sx * 5.1, 32.0, cz), (0.9, 1.6, 1.4), stone_d)
        mb.cone((tx, 31.3, 0), 6.8, 7.5, (0.28, 0.12, 0.10, 1), segments=4, rot=(0, 45, 0))
        for y in (9.0, 17.0, 24.0):
            mb.box((tx, y, -5.55), (1.2, 2.2, 0.2), (0.05, 0.04, 0.04, 1))
        for k in range(5):
            mb.cone((tx - 4.5 + k * 2.2, 3.0, -5.8), 0.45, 3.2, IRON, rot=(-70, 0, 0), segments=4)
        mb.quad((tx - 2.6, 26.0, -5.62), (tx + 2.6, 26.0, -5.62), (tx + 2.2, 14.0, -5.62), (tx - 2.2, 13.0, -5.62),
                RED_CLOTH, facing=(0, 0, -1))
        mb.box((tx, 21.0, -5.66), (2.2, 2.2, 0.05), (0.08, 0.06, 0.05, 1))
        pm.colliders.append(("box", tx, 0.0, 5.2, 5.6, 0.0, 36))
    # arch + gate doors
    mb.box((0, 21.0, 0), (15.2, 6.0, 9.0), stone_d)
    for i in range(6):
        mb.box((-6.3 + i * 2.52, 24.7, -4.2), (1.3, 1.4, 1.0), stone)
    if doors:
        door = (0.30, 0.20, 0.13, 1)
        for sx in (-1, 1):
            mb.box((sx * 3.6, 9.0, -1.0), (7.0, 18.0, 1.0), door)
            for y in (3.0, 8.0, 13.0, 16.5):
                mb.box((sx * 3.6, y, -1.6), (7.2, 0.6, 0.3), IRON)
        mb.box((0, 9.0, -1.6), (0.3, 18.0, 0.4), IRON)
    mb.box((0, 21.4, -4.6), (4.0, 3.0, 0.4), IRON)
    mb.sphere((0, 21.4, -4.9), (1.2, 1.2, 0.5), (0.55, 0.12, 0.08, 1), detail=0)
    if doors:
        pm.colliders.append(("box", 0.0, 0.0, 7.6, 4.5, 0.0, 36))
    for sx in (-1, 1):
        pm.glow_mb()
        _fire(pm, sx * 8.2, 0.0, -7.5, 1.1)
        mb.cylinder((sx * 8.2, 0.0, -7.5), 0.7, 0.6, IRON, radius_top=1.0, segments=7)
    return pm

PropBuilder = Callable[[random.Random], PropModel]

PROPS: dict[str, PropBuilder] = {
    "thorn_tree": thorn_tree, "dead_tree": dead_tree, "rock": rock, "boulder": boulder, "hoodoo": hoodoo,
    "dry_bush": dry_bush, "bones": bones, "palm_tree": palm_tree, "driftwood": driftwood,
    "orc_hut": orc_hut, "troll_hut": troll_hut, "palisade": palisade, "watchtower": watchtower,
    "campfire": campfire, "bonfire": bonfire, "brazier": brazier, "crate": crate, "barrel": barrel,
    "totem": totem, "banner": banner, "weapon_rack": weapon_rack, "anvil": anvil, "forge": forge,
    "drying_rack": drying_rack, "cook_pot": cook_pot, "tent": tent, "wagon": wagon, "well": well,
    "longhouse": longhouse, "mine_entrance": mine_entrance, "stone_ruin": stone_ruin, "dock": dock,
    "shipwreck": shipwreck, "ironmaw_gate": ironmaw_gate,
}


# ---------------------------------------------------------------------------- batcher
class PropBatcher:
    """Collects placed props into per-chunk meshes (one lit + one glowing geom per chunk)."""

    CHUNK = 64.0

    def __init__(self, parent: NodePath, collision, environment) -> None:
        self.root = parent.attachNewNode("props")
        self.collision = collision
        self.env = environment
        self._lit: dict[tuple[int, int], MeshBuilder] = {}
        self._glow: dict[tuple[int, int], MeshBuilder] = {}
        self.chunks: list[tuple[NodePath, float, float, bool]] = []
        self.count = 0

    def _key(self, x: float, z: float) -> tuple[int, int]:
        return (int(math.floor((x - WORLD_MIN_X) / self.CHUNK)), int(math.floor((z - WORLD_MIN_Z) / self.CHUNK)))

    def place(self, pm: PropModel, x: float, y: float, z: float, yaw: float = 0.0, scale: float = 1.0,
              solid: bool = True) -> None:
        key = self._key(x, z)
        rot = (0.0, yaw, 0.0)
        self._lit.setdefault(key, MeshBuilder()).merge(pm.lit, (x, y, z), rot, scale)
        if pm.glow is not None and not pm.glow.is_empty():
            self._glow.setdefault(key, MeshBuilder()).merge(pm.glow, (x, y, z), rot, scale)
        R = rotation_matrix(rot)
        for c in pm.colliders if solid else ():
            lp = R @ np.array([c[1] * scale, 0.0, c[2] * scale], np.float32)
            wx, wz = x + float(lp[0]), z + float(lp[2])
            if c[0] == "circle":
                self.collision.add_circle(wx, wz, c[3] * scale, top=y + c[4] * scale)
            else:
                self.collision.add_box(wx, wz, c[3] * scale, c[4] * scale, yaw + c[5], top=y + c[6] * scale)
        for p in pm.platforms:
            lp = R @ np.array([p[0] * scale, 0.0, p[1] * scale], np.float32)
            y1 = None if p[6] is None else y + p[6] * scale
            self.collision.add_platform(Platform(x + float(lp[0]), z + float(lp[2]), p[2] * scale, p[3] * scale,
                                                 yaw + p[4], y + p[5] * scale, y1))
        for l in pm.lights:
            lp = R @ np.array([l[0] * scale, l[1] * scale, l[2] * scale], np.float32)
            self.env.add_light(PointLight((x + float(lp[0]), y + float(lp[1]), z + float(lp[2])), l[3] * scale, l[4], l[5], l[6]))
        self.count += 1

    def build(self) -> None:
        for key, mb in self._lit.items():
            node = mb.build(f"props_{key[0]}_{key[1]}")
            node.reparentTo(self.root)
            cx = WORLD_MIN_X + (key[0] + 0.5) * self.CHUNK
            cz = WORLD_MIN_Z + (key[1] + 0.5) * self.CHUNK
            self.chunks.append((node, cx, cz, True))
        for key, mb in self._glow.items():
            node = mb.build(f"glow_{key[0]}_{key[1]}")
            node.reparentTo(self.root)
            node.setShaderInput("u_emissive", 1.25)
            node.setShaderInput("u_flame", 1.0)
            cx = WORLD_MIN_X + (key[0] + 0.5) * self.CHUNK
            cz = WORLD_MIN_Z + (key[1] + 0.5) * self.CHUNK
            self.chunks.append((node, cx, cz, True))
        self._lit.clear()
        self._glow.clear()

    def update_visibility(self, cam_x: float, cam_z: float, dist: float) -> None:
        lim2 = (dist + self.CHUNK * 0.7) ** 2
        for i, (node, cx, cz, vis) in enumerate(self.chunks):
            v = (cx - cam_x) ** 2 + (cz - cam_z) ** 2 < lim2
            if v != vis:
                if v:
                    node.show()
                else:
                    node.hide()
                self.chunks[i] = (node, cx, cz, v)
