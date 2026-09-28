"""Hollowfang Mine: a tile-based underground dungeon placed far away from the overworld."""
from __future__ import annotations

import math
import random

import numpy as np

from core.events import events
from core.meshgen import MeshBuilder, shade
from settings import DUNGEON_ORIGIN
from world.sky import PointLight

TILE = 4.0
WALL_H = 7.5

# '#' rock, '.' floor, 'E' entrance/exit, 'T' torch spot, 'C' crystal, 'R' rails+cart, 'B' boss, 'S' start
LAYOUT = """
##############################################
##############################################
####################...........###############
##################....T.....C....#############
#################......................#######
#################..C.......B..........C..#####
################..........................####
################...T....................T.####
################..........................####
#################.......C..........C.....#####
###################.....................######
#####################......T.......##########
#########################.......#############
##########################.....##############
##########################..T..##############
##########################.....##############
##########...#############.....##############
########.......####......C.....C..###########
#######....C.....##.......................####
######...........##.T...................C.####
######..T....C.......................T....####
######....................................####
#######...........##......C.......C......#####
#########.......####.....................#####
###########...#######....#########...#########
###########...######################.#########
###########.R.######################.#########
###########.R.######################..########
##########..R..######################.########
#########...R...#####################.########
########....R....####################.########
########...R.....T##########.........#########
#########...R.......................##########
##########...R....T.......###################
###########..R......#########################
############.......##########################
############..T..############################
############.....############################
############..S..############################
############.....############################
#############.E.#############################
##############################################
""".strip("\n").splitlines()

ROCK = (0.36, 0.28, 0.24, 1)
ROCK_DARK = (0.22, 0.17, 0.15, 1)
FLOOR = (0.40, 0.32, 0.26, 1)
WOOD = (0.42, 0.28, 0.16, 1)
IRON = (0.3, 0.29, 0.31, 1)


class Dungeon:
    """Builds the mine interior, its collision and lights, and handles entering/leaving."""

    def __init__(self, game) -> None:
        self.game = game
        self.ox, self.oy, self.oz = DUNGEON_ORIGIN
        self.grid = [row.ljust(len(LAYOUT[0]), "#") for row in LAYOUT]
        self.h = len(self.grid)
        self.w = len(self.grid[0])
        self.root = game.world.root.attachNewNode("dungeon")
        self.inside = False
        self.cooldown = 0.0
        self.lights: list[PointLight] = []
        self.spawn_points: dict[str, list[tuple[float, float]]] = {}
        self._build()
        self.root.hide()
        game.world.collision.ground_override = self._ground
        self.bounds = (self.ox - 2, self.ox + self.w * TILE + 2, self.oz - self.h * TILE - 2, self.oz + 2)

    # ------------------------------------------------------------------ geometry
    def tile_center(self, col: int, row: int) -> tuple[float, float]:
        """World (x, z) of a grid cell; row 0 is the north edge."""
        return self.ox + (col + 0.5) * TILE, self.oz - (row + 0.5) * TILE

    def cell_at(self, x: float, z: float) -> tuple[int, int]:
        return int(math.floor((x - self.ox) / TILE)), int(math.floor((self.oz - z) / TILE))

    def is_floor(self, col: int, row: int) -> bool:
        if 0 <= row < self.h and 0 <= col < self.w:
            return self.grid[row][col] != "#"
        return False

    def contains(self, x: float, z: float) -> bool:
        return self.bounds[0] <= x <= self.bounds[1] and self.bounds[2] <= z <= self.bounds[3]

    def _ground(self, x: float, z: float, feet_y: float) -> float | None:
        if not self.contains(x, z):
            return None
        return self.oy

    def _build(self) -> None:
        rng = random.Random(77)
        lit = MeshBuilder()
        glow = MeshBuilder()
        col_world = self.game.world.collision
        for r in range(self.h):
            for c in range(self.w):
                ch = self.grid[r][c]
                cx, cz = self.tile_center(c, r)
                if ch == "#":
                    # only walls that touch a floor tile need geometry/collision
                    touching = any(self.is_floor(c + dc, r + dr) for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1),
                                                                                (1, 1), (-1, -1), (1, -1), (-1, 1)))
                    if touching:
                        col_world.add_box(cx, cz, TILE / 2, TILE / 2, 0.0, top=self.oy + WALL_H, tag="dungeon")
                        for k in range(2):
                            s = rng.uniform(TILE * 0.55, TILE * 0.85)
                            lit.sphere((cx + rng.uniform(-1, 1), self.oy + rng.uniform(1.5, WALL_H - 1.0), cz + rng.uniform(-1, 1)),
                                       (s, rng.uniform(2.5, 4.0), s), shade(ROCK, rng.uniform(0.75, 1.15)), detail=1,
                                       noise=0.25, seed=rng.randint(0, 99999), jitter=0.1)
                        lit.box((cx, self.oy + WALL_H / 2, cz), (TILE, WALL_H, TILE), ROCK_DARK, jitter=0.1)
                    continue
                # floor tile
                lit.box((cx, self.oy - 0.5, cz), (TILE, 1.0, TILE), shade(FLOOR, rng.uniform(0.85, 1.1)), jitter=0.06)
                if rng.random() < 0.25:
                    lit.sphere((cx + rng.uniform(-1.5, 1.5), self.oy, cz + rng.uniform(-1.5, 1.5)), rng.uniform(0.2, 0.45),
                               ROCK, detail=0, noise=0.3, seed=rng.randint(0, 9999))
                # ceiling
                lit.box((cx, self.oy + WALL_H + 0.5, cz), (TILE, 1.0, TILE), ROCK_DARK, jitter=0.08)
                if rng.random() < 0.3:
                    lit.cone((cx + rng.uniform(-1, 1), self.oy + WALL_H, cz + rng.uniform(-1, 1)), rng.uniform(0.2, 0.4),
                             rng.uniform(0.8, 2.0), ROCK, rot=(180, 0, 0), segments=5)
                if ch == "T":
                    self._torch(lit, glow, c, r)
                elif ch == "C":
                    self._crystals(lit, glow, cx, cz, rng)
                elif ch == "R":
                    lit.box((cx - 0.5, self.oy + 0.05, cz), (0.1, 0.1, TILE), IRON)
                    lit.box((cx + 0.5, self.oy + 0.05, cz), (0.1, 0.1, TILE), IRON)
                    for k in range(4):
                        lit.box((cx, self.oy + 0.02, cz - TILE / 2 + (k + 0.5) * TILE / 4), (1.5, 0.06, 0.25), WOOD)
                    if rng.random() < 0.3:
                        lit.box((cx, self.oy + 0.7, cz), (1.3, 0.8, 1.8), IRON, taper=1.2)
                        col_world.add_box(cx, cz, 0.7, 0.9, 0.0, top=self.oy + 1.2, tag="dungeon")
                elif ch == "S":
                    self.start = (cx, cz)
                elif ch == "E":
                    self.exit_pos = (cx, cz)
                    glow.box((cx, self.oy + 2.4, cz - 1.6), (3.2, 4.8, 0.2), (1.0, 0.85, 0.55, 1))
                    self.lights.append(PointLight((cx, self.oy + 2.5, cz + 1.0), 10.0, (1.0, 0.85, 0.6), 1.4, 0.0))
                elif ch == "B":
                    self.boss_spot = (cx, cz)
                # support beams across narrow corridors
                if self.is_floor(c, r - 1) and self.is_floor(c, r + 1) and not self.is_floor(c - 1, r) \
                        and not self.is_floor(c + 1, r) and (r % 3 == 0):
                    self._beam(lit, cx, cz, horizontal=True)
                elif self.is_floor(c - 1, r) and self.is_floor(c + 1, r) and not self.is_floor(c, r - 1) \
                        and not self.is_floor(c, r + 1) and (c % 3 == 0):
                    self._beam(lit, cx, cz, horizontal=False)
        node = lit.build("dungeon_lit")
        node.reparentTo(self.root)
        gnode = glow.build("dungeon_glow")
        gnode.reparentTo(self.root)
        gnode.setShaderInput("u_emissive", 1.35)
        gnode.setShaderInput("u_flame", 0.6)
        self._build_boss_room_details()

    def _torch(self, lit: MeshBuilder, glow: MeshBuilder, c: int, r: int) -> None:
        cx, cz = self.tile_center(c, r)
        # hang the torch on the nearest wall
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if not self.is_floor(c + dc, r + dr):
                wx = cx + dc * (TILE / 2 - 0.3)
                wz = cz - dr * (TILE / 2 - 0.3)
                break
        else:
            wx, wz = cx, cz
        lit.beam((wx, self.oy + 2.4, wz), ((wx + cx) / 2, self.oy + 3.0, (wz + cz) / 2), 0.07, WOOD, segments=4)
        glow.cone(((wx + cx) / 2, self.oy + 3.0, (wz + cz) / 2), 0.2, 0.55, (1.0, 0.6, 0.15, 1), segments=5)
        self.lights.append(PointLight(((wx + cx) / 2, self.oy + 3.4, (wz + cz) / 2), 13.0, (1.0, 0.55, 0.2), 1.4, 0.2))

    def _crystals(self, lit: MeshBuilder, glow: MeshBuilder, cx: float, cz: float, rng: random.Random) -> None:
        col = (0.35, 0.65, 1.0, 1) if rng.random() < 0.6 else (0.75, 0.35, 1.0, 1)
        for _ in range(rng.randint(3, 6)):
            h = rng.uniform(0.8, 2.4)
            glow.cone((cx + rng.uniform(-1.2, 1.2), self.oy - 0.1, cz + rng.uniform(-1.2, 1.2)), rng.uniform(0.15, 0.35), h,
                      col, rot=(rng.uniform(-25, 25), rng.uniform(0, 360), rng.uniform(-25, 25)), segments=5)
        self.lights.append(PointLight((cx, self.oy + 1.5, cz), 11.0, (col[0], col[1], col[2]), 1.1, 0.05))
        self.game.world.collision.add_circle(cx, cz, 1.2, top=self.oy + 1.5, tag="dungeon")

    def _beam(self, lit: MeshBuilder, cx: float, cz: float, horizontal: bool) -> None:
        half = TILE / 2
        if horizontal:
            a, b = (cx - half, cz), (cx + half, cz)
        else:
            a, b = (cx, cz - half), (cx, cz + half)
        for p in (a, b):
            lit.beam((p[0], self.oy, p[1]), (p[0], self.oy + WALL_H - 1.2, p[1]), 0.18, WOOD, segments=5)
        lit.beam((a[0], self.oy + WALL_H - 1.3, a[1]), (b[0], self.oy + WALL_H - 1.3, b[1]), 0.2, WOOD, segments=5)

    def _build_boss_room_details(self) -> None:
        mb = MeshBuilder()
        glow = MeshBuilder()
        bx, bz = self.boss_spot
        rng = random.Random(5)
        for _ in range(14):
            a = rng.uniform(0, math.tau)
            d = rng.uniform(6, 22)
            x, z = bx + math.cos(a) * d, bz + math.sin(a) * d
            c, r = self.cell_at(x, z)
            if self.is_floor(c, r):
                mb.beam((x, self.oy + 0.1, z), (x + rng.uniform(-1, 1), self.oy + 0.2, z + rng.uniform(-1, 1)), 0.1,
                        (0.9, 0.86, 0.75, 1), segments=4)
        # glowing fissures in the floor
        for k in range(8):
            a = k / 8 * math.tau + rng.uniform(-0.2, 0.2)
            L = rng.uniform(5, 12)
            glow.beam((bx + math.cos(a) * 3, self.oy + 0.02, bz + math.sin(a) * 3),
                      (bx + math.cos(a) * L, self.oy + 0.02, bz + math.sin(a) * L), (0.35, 0.05), (1.0, 0.35, 0.05, 1))
        self.lights.append(PointLight((bx, self.oy + 1.0, bz), 26.0, (1.0, 0.35, 0.08), 1.2, 0.1))
        n = mb.build("boss_bones")
        n.reparentTo(self.root)
        g = glow.build("boss_glow")
        g.reparentTo(self.root)
        g.setShaderInput("u_emissive", 1.4)

    # ------------------------------------------------------------------ enter / exit
    def enter(self) -> None:
        if self.inside or self.cooldown > 0:
            return
        g = self.game
        self.cooldown = 2.0
        g.hud.fade(lambda: self._do_enter())

    def _do_enter(self) -> None:
        g = self.game
        self.inside = True
        g.world.set_underground(True)
        self.root.show()
        for l in self.lights:
            g.world.env.add_light(l)
        x, z = self.start
        g.player.motor.dungeon_bounds = self.bounds
        g.player.teleport(x, z, 0.0)
        g.cam.yaw = 0.0
        g.cam.pitch = 20.0
        if g.companions:
            g.companions.clear()
        events.emit("region_changed", region={"id": "mine_interior", "name": "Hollowfang Mine", "levels": [7, 10]})
        events.emit("entered_dungeon")

    def exit(self, silent: bool = False) -> None:
        if not self.inside:
            return
        if silent:
            self._do_exit()
        else:
            self.game.hud.fade(self._do_exit)

    def _do_exit(self) -> None:
        g = self.game
        self.inside = False
        self.cooldown = 3.0
        g.world.set_underground(False)
        self.root.hide()
        for l in self.lights:
            g.world.env.remove_light(l)
        g.player.motor.dungeon_bounds = None
        if not g.player.dead:
            g.player.teleport(-222.0, 216.0, 120.0)
            g.cam.yaw = 120.0
        if g.companions:
            g.companions.clear()
        events.emit("left_dungeon")

    def update(self, dt: float) -> None:
        self.cooldown = max(0.0, self.cooldown - dt)
        if not self.inside or self.cooldown > 0:
            return
        p = self.game.player
        ex, ez = self.exit_pos
        if not p.dead and math.hypot(p.x - ex, p.z - ez) < 1.8:
            self.exit()

    # ------------------------------------------------------------------ enemies
    def spawn_enemies(self, manager) -> None:
        """Goblins in every chamber and Grakk in the deepest cavern."""
        rng = random.Random(9)
        groups = [
            ("tunnel_goblin", (7, 8), [(12, 27), (13, 30), (11, 31), (14, 33), (9, 21), (12, 19)]),
            ("goblin_geomancer", (8, 8), [(7, 18), (13, 21)]),
            ("tunnel_goblin", (8, 8), [(22, 32), (24, 32), (37, 27)]),
            ("tunnel_goblin", (8, 9), [(24, 19), (28, 20), (33, 18), (37, 21)]),
            ("goblin_geomancer", (8, 9), [(30, 22), (38, 18), (25, 22)]),
            ("tunnel_goblin", (9, 9), [(28, 13), (29, 15)]),
            ("goblin_geomancer", (9, 9), [(28, 11)]),
        ]
        for tid, (lo, hi), cells in groups:
            for (c, r) in cells:
                if not self.is_floor(c, r):
                    continue
                x, z = self.tile_center(c, r)
                manager.spawn(tid, rng.randint(lo, hi), x, z, {"wander": 2.0, "dungeon": True}, yaw=rng.uniform(0, 360))
        bx, bz = self.boss_spot
        self.boss = manager.spawn("grakk", 10, bx, bz, {"wander": 0.0, "dungeon": True}, yaw=180.0)

    def map_image(self, px: int = 8) -> np.ndarray:
        img = np.zeros((self.h * px, self.w * px, 3), np.uint8)
        img[:] = (22, 16, 14)
        for r in range(self.h):
            for c in range(self.w):
                if self.grid[r][c] != "#":
                    col = (120, 96, 78)
                    if self.grid[r][c] == "C":
                        col = (90, 130, 190)
                    elif self.grid[r][c] == "B":
                        col = (170, 70, 40)
                    img[r * px:(r + 1) * px, c * px:(c + 1) * px] = col
        return img
