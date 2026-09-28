"""Target selection: tab-targeting, mouse picking and the selection circle."""
from __future__ import annotations

import math
from typing import Any

from panda3d.core import Point2, Point3, Vec3

from core.events import events
from core.textures import ring_texture
from core.util import angle_diff, yaw_to

TAB_RANGE = 42.0


class Targeting:
    """Keeps track of the player's current target and draws the ring under it."""

    def __init__(self, game) -> None:
        self.game = game
        self.target: Any = None
        self._tab_cycle: list[Any] = []
        fx = game.fx
        self.ring = fx.flat_quad("selection", ring_texture(128, 0.14))
        self.ring.reparentTo(game.world.fx)
        self.ring.setBin("transparent", 4)
        self.ring.hide()
        self._spin = 0.0
        events.on("world_left_click", self._on_left_click)
        events.on("world_right_click", self._on_right_click)
        events.on("unit_died", self._on_died)

    # -------------------------------------------------------------- selection
    def set_target(self, unit: Any) -> None:
        if unit is self.target:
            return
        self.target = unit
        p = self.game.player
        if p is not None:
            p.target = unit if unit is not None and hasattr(unit, "take_damage") else None
            p.auto_attacking = False
        events.emit("target_changed", target=unit)

    def clear(self) -> None:
        self.set_target(None)

    def _on_died(self, unit: Any, killer: Any = None, **_: Any) -> None:
        if unit is self.game.player:
            self.clear()

    def candidates(self) -> list[Any]:
        """Everything that can be clicked: enemies (alive or lootable corpses), NPCs, objects."""
        g = self.game
        p = g.player
        out: list[Any] = []
        out.extend(e for e in g.enemies.enemies_near(p.x, p.z, 60)
                   if e.visible and e.state != "respawning" and getattr(e, "targetable", True))
        if g.npcs:
            out.extend(n for n in g.npcs.near(p.x, p.z, 60))
        if g.interactables:
            out.extend(o for o in g.interactables.near(p.x, p.z, 60))
        if g.companions:
            out.extend(c for c in g.companions.units if not c.dead)
        return out

    def tab(self, backwards: bool = False) -> None:
        """Cycle through hostile targets in front of the player, nearest first."""
        g = self.game
        p = g.player
        cam_yaw = g.cam.yaw
        options = []
        for e in g.enemies.living_near(p.x, p.z, TAB_RANGE):
            if e.passive and e.type_id != "training_dummy" or not getattr(e, "targetable", True):
                continue
            dx, dz = e.x - p.x, e.z - p.z
            d = math.hypot(dx, dz)
            ang = abs(angle_diff(cam_yaw, yaw_to(dx, dz)))
            if ang > 75 and d > 8:
                continue
            options.append((d + ang * 0.08, e))
        options.sort(key=lambda t: t[0])
        units = [u for _, u in options]
        if not units:
            return
        if self.target in units:
            i = units.index(self.target)
            i = (i - 1 if backwards else i + 1) % len(units)
            self.set_target(units[i])
        else:
            self.set_target(units[0])

    # -------------------------------------------------------------- picking
    def mouse_ray(self) -> tuple[Vec3, Vec3] | None:
        base = self.game.base
        mw = base.mouseWatcherNode
        if not mw.hasMouse():
            return None
        m = mw.getMouse()
        near, far = Point3(), Point3()
        if not base.camLens.extrude(Point2(m.x, m.y), near, far):
            return None
        rn = base.render.getRelativePoint(base.cam, near)
        rf = base.render.getRelativePoint(base.cam, far)
        d = Vec3(rf - rn)
        d.normalize()
        return Vec3(rn), d

    def pick(self) -> Any:
        ray = self.mouse_ray()
        if ray is None:
            return None
        origin, direction = ray
        best, best_t = None, 1e9
        for c in self.candidates():
            h = getattr(c, "height", 2.0)
            r = max(getattr(c, "radius", 0.6), h * 0.45) * 1.1
            center = Vec3(c.x, c.y + h * 0.5, c.z)
            oc = center - origin
            t = oc.dot(direction)
            if t < 0:
                continue
            closest = origin + direction * t
            if (closest - center).length() <= r and t < best_t:
                best, best_t = c, t
        return best

    def _on_left_click(self, **_: Any) -> None:
        hit = self.pick()
        self.set_target(hit)

    def _on_right_click(self, **_: Any) -> None:
        hit = self.pick()
        if hit is None:
            return
        self.set_target(hit)
        self.game.interact_with(hit)

    # -------------------------------------------------------------- visuals
    def update(self, dt: float) -> None:
        t = self.target
        if t is not None and getattr(t, "state", "") == "respawning":
            self.clear()
            t = None
        if t is None:
            self.ring.hide()
            return
        self.ring.show()
        self._spin += dt * 30
        r = max(0.8, getattr(t, "radius", 0.6) * 1.3)
        g = self.game.world.ground(t.x, t.z, getattr(t, "y", 0) + 0.5)
        self.ring.setPos(t.x, g + 0.1, t.z)
        self.ring.setScale(r)
        self.ring.setH(self._spin)
        p = self.game.player
        if getattr(t, "dead", False):
            col = (0.7, 0.7, 0.7, 0.6)
        elif hasattr(t, "is_hostile_to") and p is not None and t.is_hostile_to(p):
            col = (1.0, 0.2, 0.15, 0.9)
        elif getattr(t, "faction", "") in ("friendly", "player"):
            col = (0.3, 1.0, 0.35, 0.9)
        else:
            col = (1.0, 0.9, 0.2, 0.9)
        self.ring.setColorScale(*col)
