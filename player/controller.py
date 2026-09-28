"""Kinematic character movement over terrain: slopes, jumping, swimming, obstacles, bounds."""
from __future__ import annotations

import math

from settings import (PLAYABLE_MAX_X, SEA_LEVEL, SWIM_DEPTH, WORLD_MAX_X, WORLD_MAX_Z, WORLD_MIN_X,
                      WORLD_MIN_Z)

GRAVITY = 26.0
JUMP_SPEED = 9.0
MAX_CLIMB = 1.35        # rise / run that can still be walked up (~53 degrees)
STEP_DOWN = 0.8         # stay glued to the ground when walking down within this drop
SLIDE_NY = 0.55         # slopes steeper than this make you slide


class CharacterMotor:
    """Moves a vertical capsule (x, y = feet, z) through the world."""

    def __init__(self, world, x: float, z: float, radius: float = 0.5, bounded: bool = True) -> None:
        self.world = world
        self.radius = radius
        self.x = x
        self.z = z
        self.y = world.ground(x, z)
        self.vy = 0.0
        self.grounded = True
        self.swimming = False
        self.bounded = bounded
        self.last_speed = 0.0
        self.blocked = False
        self.fall_start_y = self.y
        self.landed_fall = 0.0
        self.sea_blocked = False
        self.dungeon_bounds: tuple[float, float, float, float] | None = None

    def teleport(self, x: float, z: float, y: float | None = None) -> None:
        self.x, self.z = x, z
        self.y = self.world.ground(x, z) if y is None else y
        self.vy = 0.0
        self.grounded = True

    def _walkable(self, cur_ground: float, nx: float, nz: float, dist: float) -> bool:
        g = self.world.ground(nx, nz, self.y)
        if not self.grounded or self.swimming:
            return g <= self.y + 0.6
        rise = g - cur_ground
        if rise <= 0.25:
            return True
        return rise / max(dist, 1e-4) <= MAX_CLIMB

    def move(self, dt: float, wish_x: float, wish_z: float, speed: float, jump: bool = False) -> float:
        """Advance one frame. ``wish`` is a (not necessarily unit) world direction. Returns speed moved."""
        world = self.world
        ox, oz = self.x, self.z
        cur_ground = world.ground(self.x, self.z, self.y)
        depth = SEA_LEVEL - cur_ground
        self.swimming = depth > SWIM_DEPTH and self.y <= SEA_LEVEL - SWIM_DEPTH + 0.35 and not world.underground
        if self.swimming:
            speed *= 0.62

        ln = math.hypot(wish_x, wish_z)
        self.blocked = False
        if ln > 1e-4:
            wx, wz = wish_x / ln, wish_z / ln
            step = speed * dt * min(ln, 1.0)
            nx, nz = self.x + wx * step, self.z + wz * step
            if self._walkable(cur_ground, nx, nz, step):
                self.x, self.z = nx, nz
            else:
                self.blocked = True
                # try sliding along either axis
                if abs(wx) > 0.1 and self._walkable(cur_ground, self.x + wx * step, self.z, abs(wx * step)):
                    self.x += wx * step
                elif abs(wz) > 0.1 and self._walkable(cur_ground, self.x, self.z + wz * step, abs(wz * step)):
                    self.z += wz * step

        # static obstacles
        self.x, self.z, hit = world.collision.resolve(self.x, self.z, self.radius, self.y)
        if hit:
            self.blocked = True

        # world bounds
        self.sea_blocked = False
        if self.bounded and not world.underground:
            if self.x > PLAYABLE_MAX_X:
                self.x = PLAYABLE_MAX_X
                self.sea_blocked = True
            self.x = max(WORLD_MIN_X + 12.0, self.x)
            self.z = min(max(WORLD_MIN_Z + 12.0, self.z), WORLD_MAX_Z - 12.0)
            self.x = min(self.x, WORLD_MAX_X - 12.0)
        if self.dungeon_bounds is not None:
            x0, x1, z0, z1 = self.dungeon_bounds
            self.x = min(max(self.x, x0), x1)
            self.z = min(max(self.z, z0), z1)

        # vertical
        ground = world.ground(self.x, self.z, self.y)
        self.landed_fall = 0.0
        water_y = SEA_LEVEL - SWIM_DEPTH + 0.2
        if not world.underground and SEA_LEVEL - ground > SWIM_DEPTH and self.y <= water_y + 0.3 and self.vy <= 0:
            # floating
            self.swimming = True
            self.y += (water_y - self.y) * min(dt * 6.0, 1.0)
            self.vy = 0.0
            self.grounded = False
        elif self.grounded:
            if jump:
                self.vy = JUMP_SPEED
                self.grounded = False
                self.fall_start_y = self.y
                self.y += self.vy * dt
            elif ground >= self.y - STEP_DOWN:
                self.y = ground
                self.vy = 0.0
            else:
                self.grounded = False
                self.fall_start_y = self.y
        else:
            if self.swimming and jump:
                pass
            self.vy -= GRAVITY * dt
            self.y += self.vy * dt
            if self.y <= ground:
                self.landed_fall = self.fall_start_y - ground
                self.y = ground
                self.vy = 0.0
                self.grounded = True
            if self.vy > 0:
                self.fall_start_y = max(self.fall_start_y, self.y)

        # slide off very steep ground
        if self.grounded and not self.swimming:
            nx_, ny_, nz_ = world.terrain.normal_at(self.x, self.z) if not world.underground else (0.0, 1.0, 0.0)
            if ny_ < SLIDE_NY and ground >= world.terrain.height_at(self.x, self.z) - 0.01:
                self.x += nx_ * 7.0 * dt
                self.z += nz_ * 7.0 * dt
                self.y = world.ground(self.x, self.z, self.y)

        moved = math.hypot(self.x - ox, self.z - oz)
        self.last_speed = moved / dt if dt > 0 else 0.0
        return self.last_speed
