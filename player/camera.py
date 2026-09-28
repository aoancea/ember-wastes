"""Third-person orbit camera with terrain collision and right-mouse mouselook."""
from __future__ import annotations

import math

from panda3d.core import Vec3, WindowProperties

from core.util import clamp, damp


class MouseLook:
    """Captures relative mouse movement while a button is held, keeping the cursor in place."""

    def __init__(self, base) -> None:
        self.base = base
        self.active = False
        self.anchor = (0, 0)
        self.dx = 0.0
        self.dy = 0.0
        self.moved = 0.0

    def begin(self) -> None:
        win = self.base.win
        if not win or self.active:
            return
        p = win.getPointer(0)
        self.anchor = (int(p.getX()), int(p.getY()))
        props = WindowProperties()
        props.setCursorHidden(True)
        win.requestProperties(props)
        self.active = True
        self.moved = 0.0

    def end(self) -> None:
        if not self.active:
            return
        win = self.base.win
        props = WindowProperties()
        props.setCursorHidden(False)
        win.requestProperties(props)
        win.movePointer(0, self.anchor[0], self.anchor[1])
        self.active = False

    def poll(self) -> tuple[float, float]:
        if not self.active or not self.base.win:
            return 0.0, 0.0
        p = self.base.win.getPointer(0)
        dx = p.getX() - self.anchor[0]
        dy = p.getY() - self.anchor[1]
        if dx or dy:
            self.base.win.movePointer(0, self.anchor[0], self.anchor[1])
        self.moved += abs(dx) + abs(dy)
        return float(dx), float(dy)


class ThirdPersonCamera:
    """Orbits a focus point; yaw/pitch in degrees (pitch > 0 looks down)."""

    def __init__(self, camera, world) -> None:
        self.camera = camera
        self.world = world
        self.yaw = 0.0
        self.pitch = 18.0
        self.distance = 10.0
        self.target_distance = 10.0
        self.min_distance = 2.2
        self.max_distance = 32.0
        self.focus = Vec3(0, 0, 0)
        self.current_distance = 10.0
        self.shake_t = 0.0
        self.shake_amp = 0.0
        self.ceiling: float | None = None

    def zoom(self, amount: float) -> None:
        self.target_distance = clamp(self.target_distance * (1.0 + amount), self.min_distance, self.max_distance)

    def rotate(self, dyaw: float, dpitch: float) -> None:
        self.yaw = (self.yaw + dyaw) % 360.0
        self.pitch = clamp(self.pitch + dpitch, -25.0, 80.0)

    def shake(self, amp: float = 0.25, dur: float = 0.25) -> None:
        self.shake_amp = max(self.shake_amp, amp)
        self.shake_t = max(self.shake_t, dur)

    def forward_xz(self) -> tuple[float, float]:
        r = math.radians(self.yaw)
        return math.sin(r), math.cos(r)

    def update(self, dt: float, focus: Vec3) -> None:
        self.focus = focus
        self.distance = damp(self.distance, self.target_distance, 10.0, dt)
        yr, pr = math.radians(self.yaw), math.radians(self.pitch)
        back = Vec3(-math.sin(yr) * math.cos(pr), math.sin(pr), -math.cos(yr) * math.cos(pr))
        # pull in if terrain/ground blocks the view
        d = self.distance
        steps = 10
        col = self.world.collision
        for i in range(1, steps + 1):
            t = d * i / steps
            p = focus + back * t
            g = self.world.ground(p.x, p.z, p.y) + 0.45
            if p.y < g or (t > 1.5 and col.point_inside(p.x, p.z, p.y, 0.35)):
                d = max(self.min_distance * 0.5, t - d / steps)
                break
        # ease back out, snap in fast
        if d < self.current_distance:
            self.current_distance = d
        else:
            self.current_distance = damp(self.current_distance, d, 4.0, dt)
        pos = focus + back * self.current_distance
        g = self.world.ground(pos.x, pos.z, pos.y) + 0.35
        if pos.y < g:
            pos.y = g
        if self.world.underground and self.ceiling is not None:
            pos.y = min(pos.y, self.ceiling - 0.7)
        if self.shake_t > 0:
            self.shake_t -= dt
            k = self.shake_amp * max(self.shake_t, 0) * 4
            pos += Vec3(math.sin(self.shake_t * 91) * k, math.sin(self.shake_t * 73) * k, 0)
        self.camera.setPos(pos)
        self.camera.lookAt(focus, Vec3(0, 1, 0))
