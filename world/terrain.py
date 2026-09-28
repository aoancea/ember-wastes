"""Procedural heightmap terrain for the Ember Wastes, built as flat-shaded chunks.

The heightmap is composed from authored features in ``data/zones.json`` (coast, mesas,
canyon basin, mountain block, roads, riverbeds, islands) layered on value noise.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from panda3d.core import NodePath, SamplerState

from core.meshgen import make_geom_node
from core.noise import fbm, polyline_distance, ridged, smoothstep
from core.textures import np_to_texture
from settings import (CHUNK_CELLS, SEA_LEVEL, TERRAIN_CELL, WORLD_MAX_X, WORLD_MAX_Z, WORLD_MIN_X,
                      WORLD_MIN_Z)


def _lerp(a: np.ndarray, b: np.ndarray | float, t: np.ndarray | float) -> np.ndarray:
    return a + (b - a) * t


def _box_blur(a: np.ndarray, k: int) -> np.ndarray:
    """Uniform (2k+1)^2 box blur with edge padding."""
    p = np.pad(a, k, mode="edge").astype(np.float64)
    c = np.cumsum(np.cumsum(p, axis=0), axis=1)
    c = np.pad(c, ((1, 0), (1, 0)))
    n = 2 * k + 1
    s = c[n:, n:] - c[:-n, n:] - c[n:, :-n] + c[:-n, :-n]
    return (s / (n * n)).astype(np.float32)


@dataclass
class Chunk:
    node: NodePath
    cx: float
    cz: float
    visible: bool = True


class Terrain:
    """Heightmap, height queries, chunk meshes, and derived map textures."""

    def __init__(self, zone_data: dict) -> None:
        self.cfg = zone_data["terrain"]
        self.nx = int(round((WORLD_MAX_X - WORLD_MIN_X) / TERRAIN_CELL))
        self.nz = int(round((WORLD_MAX_Z - WORLD_MIN_Z) / TERRAIN_CELL))
        xs = WORLD_MIN_X + np.arange(self.nx + 1, dtype=np.float32) * TERRAIN_CELL
        zs = WORLD_MIN_Z + np.arange(self.nz + 1, dtype=np.float32) * TERRAIN_CELL
        self.X, self.Z = np.meshgrid(xs, zs)
        self.masks: dict[str, np.ndarray] = {}
        self.heights = self._generate()
        self._h: list[list[float]] = self.heights.tolist()
        self.chunks: list[Chunk] = []
        self.root: NodePath | None = None
        self._tri_colors: np.ndarray | None = None

    # ------------------------------------------------------------------ generation
    def coast_x(self, z: np.ndarray | float) -> np.ndarray | float:
        c = self.cfg["coast"]
        v = c["base"]
        for amp, freq, phase in c["waves"]:
            v = v + amp * np.sin(np.asarray(z) * freq + phase)
        return v

    def _generate(self) -> np.ndarray:
        cfg = self.cfg
        X, Z = self.X, self.Z
        seed = int(cfg["seed"])
        base = float(cfg["plains_height"])

        # 1. rolling red-sand plains with rocky hills and low escarpments
        dunes = fbm(X, Z, 70.0, 4, seed)
        hills = ridged(X, Z, 85.0, 3, seed + 5)
        h = base + (dunes - 0.5) * 6.5 + np.maximum(hills - 0.52, 0.0) * 18.0
        h += (fbm(X, Z, 13.0, 2, seed + 9) - 0.5) * 1.3
        steps = fbm(X, Z, 120.0, 3, seed + 7)
        h += smoothstep(0.55, 0.60, steps) * 3.5 + smoothstep(0.66, 0.70, steps) * 3.0

        # 2. boundary mountains (west, south, north with a notch for the gate)
        e = cfg["edges"]
        mnoise = ridged(X, Z, 55.0, 4, seed + 21)
        wobble = (fbm(X, Z, 70.0, 3, seed + 22) - 0.5) * 170.0
        mheight = base + e["height"] * (0.65 + 0.7 * mnoise)
        west = smoothstep(e["west"], e["west"] - 30.0, X + wobble)
        south = smoothstep(e["south"], e["south"] - 30.0, Z + wobble)
        north = smoothstep(e["north"], e["north"] + 26.0, Z + wobble * 0.5)
        n = cfg["gate_notch"]
        notch = smoothstep(n["half_width"], n["half_width"] - 10.0, np.abs(X - n["x"])) * smoothstep(370.0, 360.0, Z)
        edge = np.maximum(np.maximum(west, south), north * (1.0 - notch))
        h = _lerp(h, np.maximum(h, mheight), edge)

        # 3. mountain massifs (the Scorchspine block and a few outliers)
        mass_mask = np.zeros_like(h)
        mrid = ridged(X, Z, 48.0, 4, seed + 33)
        for m in cfg["massifs"]:
            cx, cz = m["center"]
            r = np.sqrt((X - cx) ** 2 + (Z - cz) ** 2) + (fbm(X, Z, 30.0, 3, seed + 31) - 0.5) * 40.0
            mm = smoothstep(m["radius"], m["radius"] * 0.62, r)
            mh = base + m["height"] * (0.6 + 0.75 * mrid) * (0.55 + 0.45 * smoothstep(m["radius"], m["radius"] * 0.3, r))
            h = _lerp(h, np.maximum(h, mh), mm)
            mass_mask = np.maximum(mass_mask, mm)
        self.masks["scorch"] = (mass_mask * smoothstep(60.0, 110.0, Z) * smoothstep(-40.0, -90.0, X)).astype(np.float32)

        # 4. walled canyon basins (Ashfang Hollow)
        basin_mask = np.zeros_like(h)
        for b in cfg["basins"]:
            cx, cz = b["center"]
            r = np.sqrt((X - cx) ** 2 + (Z - cz) ** 2)
            r = r + (fbm(X, Z, 22.0, 2, seed + 44) - 0.5) * 16.0
            ring = smoothstep(b["inner"], b["inner"] + 7.0, r) * smoothstep(b["outer"] + 26.0, b["outer"], r)
            crest = ridged(X, Z, 20.0, 3, seed + 45)
            wall = b["floor"] + b["wall"] * ring * (0.8 + 0.35 * crest)
            h = np.maximum(h, wall)
            inside = smoothstep(b["inner"] + 1.0, b["inner"] - 6.0, r)
            floor = b["floor"] + (fbm(X, Z, 18.0, 2, seed + 46) - 0.5) * 1.6
            h = _lerp(h, floor, inside)
            basin_mask = np.maximum(basin_mask, smoothstep(b["outer"], b["inner"], r))
        self.masks["basin"] = basin_mask

        # 5. flat-topped mesas with steep cliffs
        mesa_mask = np.zeros_like(h)
        for m in cfg["mesas"]:
            cx, cz = m["center"]
            r = np.sqrt((X - cx) ** 2 + (Z - cz) ** 2) + (fbm(X, Z, 11.0, 2, seed + 51) - 0.5) * 9.0
            cliff = smoothstep(m["radius"] + 3.0, m["radius"] - 3.0, r)
            talus = smoothstep(m["radius"] + 18.0, m["radius"], r)
            top = base + m["height"] + (fbm(X, Z, 9.0, 2, seed + 52) - 0.5) * 1.5
            mh = _lerp(h, top, cliff * 0.86 + talus * 0.14)
            h = np.maximum(h, mh)
            mesa_mask = np.maximum(mesa_mask, cliff)
        self.masks["mesa"] = mesa_mask

        # 6. dry riverbeds
        river_mask = np.zeros_like(h)
        for rb in cfg["riverbeds"]:
            d, _ = polyline_distance(X, Z, rb["points"])
            d = d + (fbm(X, Z, 9.0, 2, seed + 61) - 0.5) * 3.0
            half = rb["width"] * 0.5
            m = smoothstep(half + 4.0, half - 2.0, d)
            h = h - rb["depth"] * m
            river_mask = np.maximum(river_mask, smoothstep(half + 1.0, half - 2.5, d))
        self.masks["river"] = river_mask

        # 7. coast line, beaches, sea floor and islands
        cx = self.coast_x(Z) + (fbm(X * 0.0, Z, 30.0, 2, seed + 71) - 0.5) * 10.0
        d = X - cx
        beach = np.where(d < 0, -d * 0.085, -d * 0.085 - smoothstep(6.0, 60.0, d) * 8.0)
        beach = np.maximum(beach, -13.0) + 0.05
        s = smoothstep(-50.0, -12.0, d)
        h = _lerp(h, beach, s)
        island_mask = np.zeros_like(h)
        for isl in cfg["islands"]:
            ix, iz = isl["center"]
            r = np.sqrt((X - ix) ** 2 + (Z - iz) ** 2) + (fbm(X, Z, 10.0, 2, seed + 81) - 0.5) * 7.0
            R = isl["radius"]
            prof = (isl["height"] + 3.5) * smoothstep(R * 1.35, R * 0.35, r) - 3.5
            prof = prof + (fbm(X, Z, 7.0, 2, seed + 82) - 0.5) * 0.8 * smoothstep(R, R * 0.5, r)
            h = np.maximum(h, np.where(r < R * 1.35, prof, -99.0))
            island_mask = np.maximum(island_mask, smoothstep(R * 1.1, R * 0.6, r))
        self.masks["island"] = island_mask
        self.masks["coast_d"] = d.astype(np.float32)

        # 8. carved paths (canyon exits, mountain pass, sandbar) and roads
        road_mask = np.zeros_like(h)
        for p in cfg["paths"]:
            dist, ph = polyline_distance(X, Z, p["points"])
            if p.get("carve_width", 0) > 0:
                half = p["carve_width"] * 0.5
                m = smoothstep(half, half - 6.0, dist + (fbm(X, Z, 8.0, 2, seed + 91) - 0.5) * 4.0)
                valid = ~np.isnan(ph)
                target = np.where(valid, ph + (fbm(X, Z, 6.0, 2, seed + 92) - 0.5) * 0.6, h)
                h = np.where(valid, _lerp(h, target, m), h)
            if p.get("road_width", 0) > 0:
                half = p["road_width"] * 0.5
                rm = smoothstep(half + 1.5, half - 1.0, dist + (fbm(X, Z, 5.0, 2, seed + 93) - 0.5) * 1.2)
                road_mask = np.maximum(road_mask, rm)
        self.masks["road"] = road_mask

        # 9. flattened pads (towns, camps, plazas)
        for pad in cfg["pads"]:
            px, pz = pad["center"]
            r = np.sqrt((X - px) ** 2 + (Z - pz) ** 2)
            m = smoothstep(pad["radius"] + pad["edge"], pad["radius"], r)
            if pad.get("height") is None:
                j = int(round((pz - WORLD_MIN_Z) / TERRAIN_CELL))
                i = int(round((px - WORLD_MIN_X) / TERRAIN_CELL))
                target = float(h[j, i])
            else:
                target = float(pad["height"])
            h = _lerp(h, target + (fbm(X, Z, 12.0, 2, seed + 95) - 0.5) * 0.5, m)

        # 10. smooth roads so they read as travelled paths
        blur = _box_blur(h, 2)
        h = _lerp(h, blur, road_mask * 0.75)
        h = np.clip(h, -14.0, 140.0)
        return h.astype(np.float32)

    # --------------------------------------------------------------------- queries
    def height_at(self, x: float, z: float) -> float:
        """Exact height of the rendered (triangulated) surface."""
        fx = (x - WORLD_MIN_X) / TERRAIN_CELL
        fz = (z - WORLD_MIN_Z) / TERRAIN_CELL
        i = int(fx)
        j = int(fz)
        if i < 0:
            i, fx = 0, 0.0
        elif i >= self.nx:
            i, fx = self.nx - 1, float(self.nx)
        if j < 0:
            j, fz = 0, 0.0
        elif j >= self.nz:
            j, fz = self.nz - 1, float(self.nz)
        tx = fx - i
        tz = fz - j
        r0 = self._h[j]
        r1 = self._h[j + 1]
        h00 = r0[i]
        h10 = r0[i + 1]
        h01 = r1[i]
        h11 = r1[i + 1]
        if tx >= tz:
            return h00 + tx * (h10 - h00) + tz * (h11 - h10)
        return h00 + tz * (h01 - h00) + tx * (h11 - h01)

    def normal_at(self, x: float, z: float) -> tuple[float, float, float]:
        """Surface normal of the triangle under (x, z)."""
        fx = min(max((x - WORLD_MIN_X) / TERRAIN_CELL, 0.0), self.nx - 1e-4)
        fz = min(max((z - WORLD_MIN_Z) / TERRAIN_CELL, 0.0), self.nz - 1e-4)
        i, j = int(fx), int(fz)
        tx, tz = fx - i, fz - j
        r0, r1 = self._h[j], self._h[j + 1]
        if tx >= tz:
            dx = r0[i + 1] - r0[i]
            dz = r1[i + 1] - r0[i + 1]
        else:
            dx = r1[i + 1] - r1[i]
            dz = r1[i] - r0[i]
        nx, ny, nz = -dx / TERRAIN_CELL, 1.0, -dz / TERRAIN_CELL
        ln = math.sqrt(nx * nx + ny * ny + nz * nz)
        return nx / ln, ny / ln, nz / ln

    def mask_at(self, name: str, x: float, z: float) -> float:
        m = self.masks[name]
        i = int(round((x - WORLD_MIN_X) / TERRAIN_CELL))
        j = int(round((z - WORLD_MIN_Z) / TERRAIN_CELL))
        i = min(max(i, 0), self.nx)
        j = min(max(j, 0), self.nz)
        return float(m[j, i])

    def water_depth(self, x: float, z: float) -> float:
        return SEA_LEVEL - self.height_at(x, z)

    # --------------------------------------------------------------------- meshes
    def _triangles(self) -> np.ndarray:
        P = np.stack([self.X, self.heights, self.Z], axis=-1)
        p00 = P[:-1, :-1]
        p10 = P[:-1, 1:]
        p11 = P[1:, 1:]
        p01 = P[1:, :-1]
        A = np.stack([p00, p10, p11], axis=2)
        B = np.stack([p00, p11, p01], axis=2)
        return np.stack([A, B], axis=2).astype(np.float32)  # (nz, nx, 2, 3, 3)

    def _colors(self, tris: np.ndarray) -> np.ndarray:
        """Per-triangle RGBA colours from height, slope and region masks."""
        a, b, c = tris[..., 0, :], tris[..., 1, :], tris[..., 2, :]
        nrm = np.cross(c - a, b - a)
        nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True) + 1e-9
        ny = nrm[..., 1]
        cent = tris.mean(axis=-2)
        h = cent[..., 1]
        cx, cz = cent[..., 0], cent[..., 2]
        seed = int(self.cfg["seed"])

        def tri_mask(name: str) -> np.ndarray:
            m = self.masks[name]
            v = (m[:-1, :-1] + m[1:, 1:]) * 0.5
            return np.repeat(v[:, :, None], 2, axis=2)

        n1 = fbm(cx, cz, 25.0, 3, seed + 101)
        n2 = fbm(cx, cz, 6.0, 2, seed + 102)
        sand_a = np.array([0.80, 0.44, 0.26], np.float32)
        sand_b = np.array([0.88, 0.58, 0.36], np.float32)
        col = sand_a + (sand_b - sand_a) * (n1 * 0.8 + n2 * 0.2)[..., None]
        big = fbm(cx, cz, 140.0, 3, seed + 104)
        col = _lerp(col, np.array([0.70, 0.33, 0.21], np.float32), smoothstep(0.45, 0.65, big)[..., None] * 0.55)
        col = _lerp(col, np.array([0.90, 0.66, 0.44], np.float32), smoothstep(0.45, 0.30, big)[..., None] * 0.45)

        # dry grass tufts on flat ground
        grass = smoothstep(0.56, 0.78, fbm(cx, cz, 16.0, 4, seed + 103)) * smoothstep(0.93, 0.98, ny)
        grass *= (1 - tri_mask("road")) * (1 - tri_mask("river")) * smoothstep(1.2, 2.5, h)
        col = _lerp(col, np.array([0.66, 0.55, 0.30], np.float32), (grass * 0.45)[..., None])

        # canyon basin floor: darker, ashy
        basin = tri_mask("basin")
        ash = np.array([0.62, 0.38, 0.28], np.float32) + (n2[..., None] - 0.5) * 0.08
        col = _lerp(col, ash, (basin * 0.55)[..., None])

        # scorched mountains
        scorch = tri_mask("scorch")
        col = _lerp(col, np.array([0.46, 0.26, 0.20], np.float32), (scorch * 0.6)[..., None])

        # steep rock with horizontal strata
        slope = 1.0 - ny
        rock_t = smoothstep(0.16, 0.34, slope)
        strata = 0.5 + 0.5 * np.sin(h * 0.85 + n1 * 3.0)
        rock_dark = np.array([0.50, 0.23, 0.15], np.float32)
        rock_light = np.array([0.70, 0.38, 0.24], np.float32)
        rock = rock_dark + (rock_light - rock_dark) * strata[..., None]
        rock = _lerp(rock, np.array([0.30, 0.18, 0.15], np.float32), (scorch * 0.55)[..., None])
        col = _lerp(col, rock, rock_t[..., None])

        # high peaks a bit darker and duller
        peak = smoothstep(30.0, 60.0, h)
        col = _lerp(col, np.array([0.42, 0.25, 0.20], np.float32), (peak * 0.5)[..., None])

        # riverbed cracked clay
        river = tri_mask("river") * (1 - rock_t)
        clay = np.array([0.70, 0.52, 0.40], np.float32) + (n2[..., None] - 0.5) * 0.1
        col = _lerp(col, clay, (river * 0.85)[..., None])

        # roads
        road = tri_mask("road") * (1 - rock_t * 0.5)
        col = _lerp(col, np.array([0.60, 0.42, 0.30], np.float32), (road * 0.8)[..., None])

        # islands: greener tropical ground
        isl_all = tri_mask("island")
        col = _lerp(col, np.array([0.88, 0.72, 0.50], np.float32), (smoothstep(0.0, 0.5, isl_all) * 0.8)[..., None])
        isl = isl_all * smoothstep(1.6, 2.8, h) * (1 - rock_t)
        green = np.array([0.40, 0.55, 0.24], np.float32) + (n2[..., None] - 0.5) * 0.12
        col = _lerp(col, green, (isl * 0.75)[..., None])

        # beaches and wet sand under water
        beach = smoothstep(2.0, 0.7, h) * (1 - rock_t)
        col = _lerp(col, np.array([0.90, 0.76, 0.55], np.float32), (beach * 0.85)[..., None])
        wet = smoothstep(0.2, -1.5, h)
        col = _lerp(col, np.array([0.55, 0.50, 0.40], np.float32), wet[..., None] * 0.7)

        col = np.clip(col, 0.0, 1.0)
        rgba = np.concatenate([col, np.ones(col.shape[:-1] + (1,), np.float32)], axis=-1)
        return rgba.astype(np.float32)

    def build(self, parent: NodePath) -> NodePath:
        """Create chunk meshes under ``parent``."""
        tris = self._triangles()
        cols = self._colors(tris)
        self._tri_colors = cols
        a, b, c = tris[..., 0, :], tris[..., 1, :], tris[..., 2, :]
        nrm = np.cross(c - a, b - a)
        nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True) + 1e-9
        self.root = parent.attachNewNode("terrain")
        self.root.setShaderInput("u_detail", 1.0)
        cc = CHUNK_CELLS
        for cj in range(0, self.nz, cc):
            for ci in range(0, self.nx, cc):
                t = tris[cj:cj + cc, ci:ci + cc].reshape(-1, 3, 3)
                k = cols[cj:cj + cc, ci:ci + cc].reshape(-1, 4)
                nn = nrm[cj:cj + cc, ci:ci + cc].reshape(-1, 3)
                node = make_geom_node(t.reshape(-1, 3), np.repeat(nn, 3, axis=0), np.repeat(k, 3, axis=0),
                                      name=f"chunk_{ci}_{cj}")
                node.reparentTo(self.root)
                cx = WORLD_MIN_X + (ci + cc * 0.5) * TERRAIN_CELL
                cz = WORLD_MIN_Z + (cj + cc * 0.5) * TERRAIN_CELL
                self.chunks.append(Chunk(node, cx, cz))
        return self.root

    def update_visibility(self, cam_x: float, cam_z: float, view_dist: float) -> None:
        """Hide chunks beyond the view distance (the fog hides the seam)."""
        limit = view_dist + CHUNK_CELLS * TERRAIN_CELL * 0.75
        lim2 = limit * limit
        for ch in self.chunks:
            dx = ch.cx - cam_x
            dz = ch.cz - cam_z
            vis = dx * dx + dz * dz < lim2
            if vis != ch.visible:
                ch.visible = vis
                if vis:
                    ch.node.show()
                else:
                    ch.node.hide()

    # ----------------------------------------------------------------- 2D products
    def map_image(self, px_per_cell: int = 2) -> np.ndarray:
        """Top-down shaded colour map (row 0 = north) used for the minimap and world map."""
        if self._tri_colors is None:
            self._tri_colors = self._colors(self._triangles())
        col = self._tri_colors[..., 0, :3].copy()  # (nz, nx, 3)
        h = self.heights
        gx = (h[:-1, 1:] - h[:-1, :-1]) / TERRAIN_CELL
        gz = (h[1:, :-1] - h[:-1, :-1]) / TERRAIN_CELL
        shade = np.clip(1.0 + (-gx * 0.55 + gz * 0.55) * 0.35, 0.55, 1.35)
        col = col * shade[..., None]
        depth = np.clip(-(h[:-1, :-1] + h[1:, 1:]) * 0.5, 0, 12)
        water = np.clip(depth / 2.0, 0, 1)[..., None]
        wcol = np.array([0.20, 0.55, 0.62]) * (1 - np.clip(depth / 12, 0, 1))[..., None] + \
            np.array([0.05, 0.22, 0.38]) * np.clip(depth / 12, 0, 1)[..., None]
        col = col * (1 - water * 0.9) + wcol * water * 0.9
        road = ((self.masks["road"][:-1, :-1]) > 0.5)[..., None]
        col = np.where(road, col * 0.78, col)
        img = np.clip(col * 255, 0, 255).astype(np.uint8)[::-1]
        if px_per_cell > 1:
            img = np.repeat(np.repeat(img, px_per_cell, axis=0), px_per_cell, axis=1)
        return img

    def water_depth_texture(self):
        """Texture of sea depth (0..12 units -> 0..1) covering the heightmap."""
        depth = np.clip((SEA_LEVEL - self.heights) / 12.0, 0.0, 1.0)
        img = (depth * 255).astype(np.uint8)[::-1]
        tex = np_to_texture(img, "water_depth", mipmap=False, repeat=False)
        tex.setWrapU(SamplerState.WM_border_color)
        tex.setWrapV(SamplerState.WM_border_color)
        tex.setBorderColor((1, 1, 1, 1))
        rect = (WORLD_MIN_X, WORLD_MIN_Z, WORLD_MAX_X - WORLD_MIN_X, WORLD_MAX_Z - WORLD_MIN_Z)
        return tex, rect
