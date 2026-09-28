"""Regions of the Ember Wastes, settlement layouts and natural prop scattering."""
from __future__ import annotations

import math
import random
import zlib
from typing import Any

import numpy as np

from core.util import yaw_to
from settings import WORLD_MAX_X, WORLD_MAX_Z, WORLD_MIN_X, WORLD_MIN_Z
from world import props as P
from world.props import PropBatcher, PropModel


class ZoneMap:
    """Answers 'which region / landmark is this point in?'."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.regions = sorted(data["regions"], key=lambda r: -r["priority"])
        self.by_id = {r["id"]: r for r in data["regions"]}
        self.landmarks = data.get("landmarks", [])
        self.settlements = data.get("settlements", [])
        self.gate_pos: tuple[float, float, float] | None = None

    def region_at(self, x: float, z: float) -> dict[str, Any]:
        for r in self.regions:
            cx, cz = r["center"]
            if (x - cx) ** 2 + (z - cz) ** 2 <= r["radius"] ** 2:
                return r
        return self.regions[-1]

    def landmark_at(self, x: float, z: float) -> dict[str, Any] | None:
        for lm in self.landmarks:
            lx, lz = lm["pos"]
            if (x - lx) ** 2 + (z - lz) ** 2 <= lm["radius"] ** 2:
                return lm
        return None

    def in_settlement(self, x: float, z: float, margin: float = 0.0) -> bool:
        for s in self.settlements:
            cx, cz = s["center"]
            if (x - cx) ** 2 + (z - cz) ** 2 <= (s["radius"] + margin) ** 2:
                return True
        return False


_variant_cache: dict[tuple, list[PropModel]] = {}


def variants(kind: str, n: int = 6, **kwargs: Any) -> list[PropModel]:
    key = (kind, n, tuple(sorted(kwargs.items())))
    if key not in _variant_cache:
        builder = P.PROPS[kind]
        _variant_cache[key] = [builder(random.Random(zlib.crc32(kind.encode()) % 10000 + i * 7919), **kwargs) for i in range(n)]
    return _variant_cache[key]


def place_structures(zmap: ZoneMap, terrain, batcher: PropBatcher) -> None:
    """Place all authored buildings/props listed under ``structures`` in zones.json."""
    for i, s in enumerate(zmap.data.get("structures", [])):
        kind = s["type"]
        x, z = s["pos"]
        rng = random.Random(1000 + i)
        if kind == "palisade_ring":
            _palisade_ring(terrain, batcher, x, z, s["radius"], s.get("gaps", []), s.get("gap_width", 12))
            continue
        kwargs: dict[str, Any] = {}
        for k in ("length", "burned", "color"):
            if k in s:
                kwargs[k] = tuple(s[k]) if isinstance(s[k], list) else s[k]
        if kind == "ironmaw_gate":
            kwargs["doors"] = False
        pm = P.PROPS[kind](rng, **kwargs)
        if "face" in s:
            yaw = yaw_to(s["face"][0] - x, s["face"][1] - z)
        else:
            yaw = float(s.get("yaw", 0.0))
        y = _foot_height(terrain, x, z, 1.5 * s.get("scale", 1.0))
        if kind == "dock":
            y = 0.0
        if kind == "ironmaw_gate":
            zmap.gate_pos = (x, y, z)
        batcher.place(pm, x, y, z, yaw, float(s.get("scale", 1.0)))


def _palisade_ring(terrain, batcher: PropBatcher, cx: float, cz: float, radius: float,
                   gaps: list[float], gap_width: float) -> None:
    seg_len = 7.5
    n = int(2 * math.pi * radius / seg_len)
    for k in range(n):
        ang = k / n * 360.0
        if any(abs((ang - g + 180) % 360 - 180) < gap_width for g in gaps):
            continue
        a = math.radians(ang)
        x = cx + math.sin(a) * radius
        z = cz + math.cos(a) * radius
        pm = variants("palisade", 3)[k % 3]
        yaw = ang + 90.0
        batcher.place(pm, x, _foot_height(terrain, x, z, 3.0) - 0.2, z, yaw, 1.0)


def _foot_height(terrain, x: float, z: float, r: float) -> float:
    hs = [terrain.height_at(x + dx, z + dz) for dx, dz in ((0, 0), (r, 0), (-r, 0), (0, r), (0, -r))]
    return min(hs) - 0.05


def scatter_nature(zmap: ZoneMap, terrain, batcher: PropBatcher, seed: int = 99) -> None:
    """Deterministically sprinkle trees, rocks, bushes, bones and palms over the zone."""
    rng = random.Random(seed)
    step = 8.0
    xs = np.arange(WORLD_MIN_X + 6, WORLD_MAX_X - 6, step)
    zs = np.arange(WORLD_MIN_Z + 6, WORLD_MAX_Z - 6, step)
    for z0 in zs:
        for x0 in xs:
            x = float(x0 + rng.uniform(-step * 0.45, step * 0.45))
            z = float(z0 + rng.uniform(-step * 0.45, step * 0.45))
            h = terrain.height_at(x, z)
            nx, ny, nz = terrain.normal_at(x, z)
            road = terrain.mask_at("road", x, z)
            river = terrain.mask_at("river", x, z)
            island = terrain.mask_at("island", x, z)
            scorch = terrain.mask_at("scorch", x, z)
            coast_d = terrain.mask_at("coast_d", x, z)
            if road > 0.15 or zmap.in_settlement(x, z, 4.0):
                continue
            roll = rng.random()
            yaw = rng.uniform(0, 360)
            if h < 0.25:
                continue
            beach = h < 2.2 and coast_d > -40
            kind: str | None = None
            scale = 1.0
            if island > 0.3 and h > 1.0:
                if roll < 0.30:
                    kind = "palm_tree"
                elif roll < 0.40:
                    kind = "rock"
                    scale = 0.7
                elif roll < 0.55:
                    kind = "dry_bush"
            elif beach:
                if z < -120 and roll < 0.07:
                    kind = "palm_tree"
                elif roll < 0.12:
                    kind = "driftwood"
                elif roll < 0.18:
                    kind = "rock"
                    scale = 0.6
            elif ny < 0.72:
                if roll < 0.10:
                    kind = "rock"
                    scale = rng.uniform(1.0, 1.8)
            elif scorch > 0.4:
                if roll < 0.08:
                    kind = "dead_tree"
                elif roll < 0.20:
                    kind = "rock"
                elif roll < 0.23:
                    kind = "boulder"
                elif roll < 0.235:
                    kind = "bones"
            else:
                near_river = river > 0.05 or (0.0 < terrain.mask_at("river", x + 8, z) + terrain.mask_at("river", x - 8, z))
                tree_p = 0.16 if near_river else 0.055
                if roll < tree_p:
                    kind = "thorn_tree" if rng.random() < 0.85 else "dead_tree"
                elif roll < tree_p + 0.08:
                    kind = "rock"
                elif roll < tree_p + 0.10:
                    kind = "boulder"
                elif roll < tree_p + 0.108:
                    kind = "hoodoo"
                elif roll < tree_p + 0.112:
                    kind = "bones"
                elif roll < tree_p + 0.30:
                    kind = "dry_bush"
            if kind is None:
                continue
            if kind in ("hoodoo", "bones") and zmap.in_settlement(x, z, 25.0):
                continue
            pm = rng.choice(variants(kind, 8 if kind in ("rock", "thorn_tree", "dry_bush") else 5))
            y = h - 0.15 if kind not in ("rock", "boulder") else h - 0.35
            batcher.place(pm, x, y, z, yaw, scale * rng.uniform(0.85, 1.15))
