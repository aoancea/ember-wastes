"""Creature models (original designs) with procedural animation."""
from __future__ import annotations

import math
from typing import Any

from panda3d.core import NodePath

from core.meshgen import MeshBuilder, shade
from core.rig import Rig, copy_part, swing
from core.util import set_rot
from npcs.models import build_humanoid

IVORY = (0.92, 0.87, 0.72, 1.0)
DARK = (0.08, 0.06, 0.05, 1.0)
EYE_RED = (0.9, 0.15, 0.05, 1.0)


def _c(v: Any, a: float = 1.0) -> tuple[float, float, float, float]:
    return (float(v[0]), float(v[1]), float(v[2]), a)


# ------------------------------------------------------------------ quadrupeds
class QuadrupedRig(Rig):
    """Four-legged beast: body, head, four legs and a tail."""

    def __init__(self, kind: str, color: Any, accent: Any = None) -> None:
        super().__init__()
        self.kind = kind
        self.col = _c(color)
        self.accent = _c(accent) if accent is not None else shade(self.col, 0.6)
        spec = {
            "boar": dict(hip=0.72, len=1.5, width=0.9, leg=0.62, head_z=0.95, head_y=0.1, tail_z=-0.8, height=1.45, radius=0.8),
            "lizard": dict(hip=0.42, len=1.8, width=0.7, leg=0.38, head_z=1.0, head_y=0.05, tail_z=-0.9, height=0.9, radius=0.8),
            "hyena": dict(hip=0.8, len=1.4, width=0.6, leg=0.75, head_z=0.85, head_y=0.25, tail_z=-0.72, height=1.5, radius=0.6),
        }[kind]
        self.spec = spec
        self.height = spec["height"]
        self.radius = spec["radius"]
        self.torso = self.body.attachNewNode("torso")
        self.torso.setY(spec["hip"])
        self.head = self.torso.attachNewNode("head")
        self.head.setPos(0, spec["head_y"], spec["head_z"])
        self.tail = self.torso.attachNewNode("tail")
        self.tail.setPos(0, 0.05, spec["tail_z"])
        L, W = spec["len"], spec["width"]
        self.legs: list[NodePath] = []
        for sx, sz in ((-1, 1), (1, 1), (-1, -1), (1, -1)):
            leg = self.torso.attachNewNode("leg")
            leg.setPos(sx * W * 0.36, -0.05, sz * L * 0.33)
            self.legs.append(leg)
        key = (kind, tuple(round(c, 3) for c in self.col), tuple(round(c, 3) for c in self.accent))
        copy_part(key + ("body",), lambda: self._body(), self.torso)
        copy_part(key + ("head",), lambda: self._head(), self.head)
        copy_part(key + ("tail",), lambda: self._tail(), self.tail)
        for i, leg in enumerate(self.legs):
            copy_part(key + ("leg",), lambda: self._leg(), leg)
            if kind == "lizard":
                set_rot(leg, 0, 0, (-1 if i % 2 == 0 else 1) * 35)

    def _body(self) -> MeshBuilder:
        mb = MeshBuilder()
        s = self.spec
        c, a = self.col, self.accent
        if self.kind == "boar":
            mb.box((0, 0.05, 0), (s["width"], 0.78, s["len"]), c, taper=0.85)
            mb.box((0, 0.15, 0.45), (s["width"] * 1.08, 0.85, 0.6), shade(c, 0.9))
            for i in range(7):
                z = 0.6 - i * 0.2
                mb.cone((0, 0.45, z), 0.09, 0.28 + 0.1 * math.sin(i), a, segments=4, rot=(-20, 0, 0))
        elif self.kind == "lizard":
            mb.box((0, 0.0, 0), (s["width"], 0.4, s["len"]), c, taper=0.8)
            mb.box((0, -0.12, 0), (s["width"] * 0.8, 0.12, s["len"] * 0.85), shade(c, 1.35))
            for i in range(6):
                mb.cone((0, 0.18, 0.7 - i * 0.28), 0.07, 0.2, a, segments=3)
        else:  # hyena
            mb.box((0, 0.05, 0.1), (s["width"], 0.6, s["len"]), c, taper=0.85, rot=(-8, 0, 0))
            mb.box((0, 0.4, 0.35), (0.14, 0.2, 0.9), a, rot=(-12, 0, 0))
            for i in range(5):
                mb.box((0.16 * (1 if i % 2 else -1), 0.12, 0.4 - i * 0.22), (0.12, 0.16, 0.12), shade(a, 1.2))
        return mb

    def _head(self) -> MeshBuilder:
        mb = MeshBuilder()
        c, a = self.col, self.accent
        if self.kind == "boar":
            mb.box((0, 0, 0.18), (0.62, 0.55, 0.55), c)
            mb.box((0, -0.08, 0.52), (0.36, 0.3, 0.3), shade(c, 1.1))
            mb.box((0, -0.08, 0.68), (0.3, 0.22, 0.05), (0.35, 0.2, 0.18, 1))
            for sx in (-1, 1):
                mb.cone((sx * 0.17, -0.18, 0.55), 0.05, 0.36, IVORY, rot=(-60, 0, sx * -20))
                mb.box((sx * 0.22, 0.28, 0.02), (0.14, 0.24, 0.06), shade(c, 0.8), rot=(0, 0, sx * -30))
                mb.box((sx * 0.17, 0.1, 0.46), (0.06, 0.06, 0.04), DARK)
        elif self.kind == "lizard":
            mb.box((0, 0, 0.25), (0.42, 0.28, 0.6), c, taper=0.7)
            mb.box((0, -0.1, 0.35), (0.36, 0.08, 0.5), shade(c, 1.3))
            for sx in (-1, 1):
                mb.box((sx * 0.16, 0.1, 0.35), (0.08, 0.08, 0.06), (1.0, 0.8, 0.1, 1))
                mb.triangle((sx * 0.2, 0.05, 0.0), (sx * 0.55, 0.35, -0.15), (sx * 0.5, -0.2, -0.1), a, double=True)
        else:
            mb.box((0, 0, 0.12), (0.4, 0.38, 0.42), c)
            mb.box((0, -0.06, 0.42), (0.24, 0.22, 0.32), shade(c, 0.8))
            mb.box((0, -0.06, 0.59), (0.12, 0.1, 0.04), DARK)
            for sx in (-1, 1):
                mb.cone((sx * 0.14, 0.18, 0.02), 0.08, 0.26, a, segments=4)
                mb.box((sx * 0.12, 0.08, 0.34), (0.06, 0.05, 0.04), (0.95, 0.75, 0.1, 1))
        return mb

    def _tail(self) -> MeshBuilder:
        mb = MeshBuilder()
        if self.kind == "lizard":
            mb.beam((0, 0, 0), (0, -0.1, -1.6), 0.18, self.col, segments=5, radius_b=0.04)
        elif self.kind == "boar":
            mb.beam((0, 0.1, 0), (0, -0.2, -0.35), 0.04, self.accent, segments=3)
        else:
            mb.beam((0, 0.1, 0), (0, -0.2, -0.55), 0.06, self.accent, segments=3)
        return mb

    def _leg(self) -> MeshBuilder:
        mb = MeshBuilder()
        L = self.spec["leg"]
        c = shade(self.col, 0.85)
        mb.box((0, -L * 0.45, 0), (0.18, L * 0.9, 0.2), c)
        mb.box((0, -L * 0.95, 0.04), (0.2, 0.1, 0.24), shade(c, 0.6))
        return mb

    def _pose(self, dt: float, speed: float, grounded: bool, swimming: bool) -> None:
        mbl = self.move_blend
        ph = self.phase * 1.3
        amp = 38 * mbl
        for i, leg in enumerate(self.legs):
            off = 0.0 if i in (0, 3) else math.pi
            base_roll = 0.0
            if self.kind == "lizard":
                base_roll = (-1 if i % 2 == 0 else 1) * 35
            set_rot(leg, swing(ph + off, amp), 0, base_roll)
        bob = abs(math.sin(ph)) * 0.05 * mbl + math.sin(self.idle_t * 2.0) * 0.01
        self.torso.setY(self.spec["hip"] + bob)
        head_x = math.sin(self.idle_t * 1.3) * 4
        tail_y = math.sin(self.idle_t * 3.0 + ph) * (20 if self.kind == "lizard" else 30)
        torso_x = 0.0
        act, t = self.action, self.action_progress()
        if act == "attack":
            k = math.sin(t * math.pi)
            head_x = 25 * k if t > 0.3 else -20 * math.sin(t / 0.3 * math.pi)
            self.torso.setZ(0.35 * k)
        elif act == "charge":
            torso_x = 8
            head_x = 20
        elif act == "hit":
            torso_x = -6 * math.sin(t * math.pi)
        elif act == "roar":
            head_x = -35 * math.sin(t * math.pi)
        else:
            self.torso.setZ(0)
        set_rot(self.head, head_x, 0, 0)
        set_rot(self.tail, 0, tail_y, 0)
        set_rot(self.torso, torso_x, 0, 0)

    def _pose_death(self, t: float) -> None:
        e = 1 - (1 - t) ** 3
        set_rot(self.body, 0, 0, 90 * e)
        self.body.setY(0.2 * e * self.spec["hip"])
        for i, leg in enumerate(self.legs):
            set_rot(leg, (-30 if i < 2 else 30) * e, 0, 0)


# ------------------------------------------------------------------ scorpion
class ScorpionRig(Rig):
    def __init__(self, color: Any, accent: Any = None) -> None:
        super().__init__()
        self.col = _c(color)
        self.accent = _c(accent) if accent is not None else shade(self.col, 0.7)
        self.height = 1.6
        self.radius = 0.8
        key = ("scorpion", tuple(round(c, 3) for c in self.col))
        self.torso = self.body.attachNewNode("torso")
        self.torso.setY(0.42)
        copy_part(key + ("body",), self._body, self.torso)
        self.legs: list[NodePath] = []
        for side in (-1, 1):
            for i in range(4):
                leg = self.torso.attachNewNode("leg")
                leg.setPos(side * 0.32, 0, 0.35 - i * 0.26)
                copy_part(key + ("leg", side), lambda side=side: self._leg(side), leg)
                self.legs.append(leg)
        self.claws: list[NodePath] = []
        for side in (-1, 1):
            claw = self.torso.attachNewNode("claw")
            claw.setPos(side * 0.3, 0.05, 0.55)
            copy_part(key + ("claw", side), lambda side=side: self._claw(side), claw)
            self.claws.append(claw)
        self.tail_segs: list[NodePath] = []
        parent = self.torso
        pos = (0, 0.05, -0.55)
        for i in range(5):
            seg = parent.attachNewNode("tail")
            seg.setPos(*pos)
            copy_part(key + ("tail", i), lambda i=i: self._tail_seg(i), seg)
            self.tail_segs.append(seg)
            parent = seg
            pos = (0, 0, -0.3 + i * 0.02)

    def _body(self) -> MeshBuilder:
        mb = MeshBuilder()
        c = self.col
        mb.box((0, 0, 0.1), (0.7, 0.28, 1.1), c, taper=0.8)
        for i in range(4):
            mb.box((0, 0.13, 0.4 - i * 0.26), (0.62 - i * 0.05, 0.08, 0.2), shade(c, 0.85))
        mb.box((0, 0.02, 0.62), (0.44, 0.2, 0.25), shade(c, 1.1))
        for sx in (-1, 1):
            mb.box((sx * 0.1, 0.14, 0.66), (0.06, 0.06, 0.05), DARK)
        return mb

    def _leg(self, side: int) -> MeshBuilder:
        mb = MeshBuilder()
        c = shade(self.col, 0.9)
        mb.beam((0, 0, 0), (side * 0.45, 0.22, 0), 0.05, c, segments=4)
        mb.beam((side * 0.45, 0.22, 0), (side * 0.7, -0.42, 0.04), 0.04, c, segments=4)
        return mb

    def _claw(self, side: int) -> MeshBuilder:
        mb = MeshBuilder()
        c = self.col
        mb.beam((0, 0, 0), (side * 0.25, 0.05, 0.45), 0.08, c, segments=4)
        mb.box((side * 0.28, 0.05, 0.62), (0.26, 0.16, 0.3), shade(c, 1.05))
        mb.box((side * 0.2, 0.05, 0.86), (0.08, 0.1, 0.22), shade(c, 0.9))
        mb.box((side * 0.36, 0.05, 0.84), (0.1, 0.12, 0.2), shade(c, 0.9))
        return mb

    def _tail_seg(self, i: int) -> MeshBuilder:
        mb = MeshBuilder()
        r = 0.16 - i * 0.02
        mb.sphere((0, 0, -0.14), (r * 1.1, r, 0.2), shade(self.col, 1.0 - i * 0.05), detail=0)
        if i == 4:
            mb.sphere((0, 0, -0.3), 0.12, self.accent, detail=0)
            mb.cone((0, -0.05, -0.36), 0.05, 0.3, DARK, rot=(120, 0, 0))
        return mb

    def _pose(self, dt: float, speed: float, grounded: bool, swimming: bool) -> None:
        ph = self.phase * 1.8
        amp = 22 * self.move_blend
        for i, leg in enumerate(self.legs):
            side = -1 if i < 4 else 1
            idx = i % 4
            set_rot(leg, 0, swing(ph + idx * 1.6 + (0 if side < 0 else math.pi), amp), swing(ph + idx, 6 * self.move_blend))
        curl = [48, 40, 38, 32, 20]
        act, t = self.action, self.action_progress()
        strike = 0.0
        snap = 0.0
        if act == "attack":
            strike = math.sin(t * math.pi)
            snap = math.sin(t * math.pi * 2)
        for i, seg in enumerate(self.tail_segs):
            k = curl[i] + strike * (12 + i * 4)
            set_rot(seg, k + math.sin(self.idle_t * 2 + i) * 3, 0, 0)
        for j, claw in enumerate(self.claws):
            side = -1 if j == 0 else 1
            set_rot(claw, -10 + math.sin(self.idle_t * 1.5 + j) * 5, side * (10 + 20 * snap), 0)
        self.torso.setY(0.42 + math.sin(self.idle_t * 2.5) * 0.01)

    def _pose_death(self, t: float) -> None:
        e = 1 - (1 - t) ** 3
        set_rot(self.body, 0, 0, 180 * e)
        self.body.setY(0.7 * e)


# ------------------------------------------------------------------ crab
class CrabRig(Rig):
    def __init__(self, color: Any) -> None:
        super().__init__()
        self.col = _c(color)
        self.height = 1.3
        self.radius = 0.9
        key = ("crab", tuple(round(c, 3) for c in self.col))
        self.torso = self.body.attachNewNode("torso")
        self.torso.setY(0.55)
        copy_part(key + ("body",), self._body, self.torso)
        self.legs: list[NodePath] = []
        for side in (-1, 1):
            for i in range(3):
                leg = self.torso.attachNewNode("leg")
                leg.setPos(side * 0.5, 0, 0.25 - i * 0.28)
                copy_part(key + ("leg", side), lambda side=side: self._leg(side), leg)
                self.legs.append(leg)
        self.claws: list[NodePath] = []
        for side in (-1, 1):
            claw = self.torso.attachNewNode("claw")
            claw.setPos(side * 0.45, 0.1, 0.45)
            copy_part(key + ("claw", side), lambda side=side: self._claw(side), claw)
            self.claws.append(claw)

    def _body(self) -> MeshBuilder:
        mb = MeshBuilder()
        c = self.col
        mb.sphere((0, 0, 0), (0.75, 0.32, 0.6), c, detail=1)
        mb.sphere((0, -0.12, 0), (0.7, 0.18, 0.55), shade(c, 1.3), detail=0)
        for sx in (-1, 1):
            mb.beam((sx * 0.15, 0.2, 0.45), (sx * 0.2, 0.45, 0.55), 0.03, shade(c, 0.9), segments=3)
            mb.sphere((sx * 0.2, 0.48, 0.56), 0.06, DARK, detail=0)
        for i in range(5):
            mb.cone((-0.5 + i * 0.25, 0.25, 0.1 - abs(i - 2) * 0.08), 0.05, 0.12, shade(c, 0.8), segments=3)
        return mb

    def _leg(self, side: int) -> MeshBuilder:
        mb = MeshBuilder()
        c = shade(self.col, 0.85)
        mb.beam((0, 0, 0), (side * 0.45, 0.2, 0), 0.05, c, segments=4)
        mb.beam((side * 0.45, 0.2, 0), (side * 0.65, -0.55, 0), 0.04, c, segments=4)
        return mb

    def _claw(self, side: int) -> MeshBuilder:
        mb = MeshBuilder()
        c = self.col
        mb.beam((0, 0, 0), (side * 0.3, 0.2, 0.4), 0.08, c, segments=4)
        mb.sphere((side * 0.35, 0.28, 0.62), (0.22, 0.2, 0.3), shade(c, 1.1), detail=0)
        mb.box((side * 0.28, 0.35, 0.9), (0.08, 0.12, 0.3), shade(c, 0.8))
        mb.box((side * 0.42, 0.2, 0.86), (0.08, 0.1, 0.26), shade(c, 0.8))
        return mb

    def _pose(self, dt: float, speed: float, grounded: bool, swimming: bool) -> None:
        ph = self.phase * 2.0
        amp = 25 * self.move_blend
        for i, leg in enumerate(self.legs):
            set_rot(leg, swing(ph + i * 1.3, amp * 0.5), 0, swing(ph + i * 2.1, amp))
        act, t = self.action, self.action_progress()
        snap = math.sin(t * math.pi) if act == "attack" else 0.0
        for j, claw in enumerate(self.claws):
            side = -1 if j == 0 else 1
            set_rot(claw, -15 - 35 * snap + math.sin(self.idle_t * 2 + j) * 6, side * -10, 0)
        self.torso.setY(0.55 + math.sin(self.idle_t * 3.0) * 0.015)

    def _pose_death(self, t: float) -> None:
        e = 1 - (1 - t) ** 3
        set_rot(self.body, 0, 0, 180 * e)
        self.body.setY(1.0 * e)


# ------------------------------------------------------------------ vulture
class VultureRig(Rig):
    def __init__(self, color: Any) -> None:
        super().__init__()
        self.col = _c(color)
        self.height = 1.4
        self.radius = 0.9
        self.flying = True
        key = ("vulture", tuple(round(c, 3) for c in self.col))
        self.torso = self.body.attachNewNode("torso")
        self.torso.setY(0.8)
        copy_part(key + ("body",), self._body, self.torso)
        self.neck = self.torso.attachNewNode("neck")
        self.neck.setPos(0, 0.25, 0.45)
        copy_part(key + ("head",), self._head, self.neck)
        self.wings: list[NodePath] = []
        for side in (-1, 1):
            w = self.torso.attachNewNode("wing")
            w.setPos(side * 0.28, 0.2, 0.05)
            copy_part(key + ("wing", side), lambda side=side: self._wing(side), w)
            self.wings.append(w)
        self.hover = 0.0

    def _body(self) -> MeshBuilder:
        mb = MeshBuilder()
        c = self.col
        mb.sphere((0, 0, 0), (0.38, 0.36, 0.62), c, detail=1)
        mb.box((0, 0.1, -0.7), (0.5, 0.06, 0.5), shade(c, 0.8), taper=1.0)
        mb.box((0, 0.3, 0.3), (0.5, 0.2, 0.3), (0.85, 0.82, 0.75, 1))
        for sx in (-1, 1):
            mb.beam((sx * 0.12, -0.3, 0.05), (sx * 0.14, -0.7, 0.1), 0.04, (0.55, 0.5, 0.4, 1), segments=3)
        return mb

    def _head(self) -> MeshBuilder:
        mb = MeshBuilder()
        pink = (0.78, 0.45, 0.42, 1)
        mb.beam((0, 0, 0), (0, 0.25, 0.3), 0.07, pink, segments=4)
        mb.sphere((0, 0.3, 0.36), (0.14, 0.13, 0.18), pink, detail=0)
        mb.cone((0, 0.26, 0.5), 0.06, 0.2, (0.9, 0.85, 0.6, 1), rot=(100, 0, 0), segments=4)
        for sx in (-1, 1):
            mb.box((sx * 0.08, 0.34, 0.42), (0.04, 0.04, 0.03), DARK)
        return mb

    def _wing(self, side: int) -> MeshBuilder:
        mb = MeshBuilder()
        c = self.col
        mb.quad((0, 0, 0.25), (side * 1.4, 0.05, 0.1), (side * 1.3, 0.0, -0.4), (0, 0, -0.35), c, facing=(0, 1, 0), double=True)
        mb.quad((side * 1.4, 0.05, 0.1), (side * 2.1, 0.0, -0.1), (side * 1.9, -0.02, -0.55), (side * 1.3, 0.0, -0.4),
                shade(c, 0.75), facing=(0, 1, 0), double=True)
        return mb

    def _pose(self, dt: float, speed: float, grounded: bool, swimming: bool) -> None:
        t = self.idle_t
        flap_speed = 8.0 if self.action in ("attack",) else 5.0
        glide = self.hover > 0.5
        flap = math.sin(t * flap_speed) * (18 if glide else 38)
        for j, w in enumerate(self.wings):
            side = -1 if j == 0 else 1
            set_rot(w, 0, 0, side * (flap + 5))
        neck_x = 10 + math.sin(t * 1.7) * 6
        act, p = self.action, self.action_progress()
        if act == "attack":
            neck_x = 10 + 50 * math.sin(p * math.pi)
        set_rot(self.neck, neck_x, 0, 0)
        self.torso.setY(0.8 + math.sin(t * flap_speed) * 0.08)

    def _pose_death(self, t: float) -> None:
        e = 1 - (1 - t) ** 3
        set_rot(self.body, 0, 0, 100 * e)
        for j, w in enumerate(self.wings):
            set_rot(w, 0, 0, (-1 if j == 0 else 1) * -20 * e)


# ------------------------------------------------------------------ training dummy
class DummyRig(Rig):
    def __init__(self) -> None:
        super().__init__()
        self.height = 2.2
        self.radius = 0.6
        self.pivot = self.body.attachNewNode("pivot")
        copy_part(("dummy",), self._mesh, self.pivot)

    def _mesh(self) -> MeshBuilder:
        mb = MeshBuilder()
        wood = (0.42, 0.28, 0.16, 1)
        straw = (0.85, 0.72, 0.38, 1)
        mb.cylinder((0, 0, 0), 0.1, 2.2, wood, segments=5)
        mb.cylinder((0, 0.9, 0), 0.34, 0.9, straw, radius_top=0.3, segments=7, jitter=0.1)
        mb.sphere((0, 2.05, 0), (0.24, 0.26, 0.24), (0.78, 0.66, 0.44, 1), detail=0)
        mb.beam((-0.7, 1.55, 0), (0.7, 1.55, 0), 0.07, wood, segments=4)
        mb.box((0, 1.3, 0.3), (0.3, 0.3, 0.05), (0.7, 0.15, 0.1, 1))
        for sx in (-1, 1):
            mb.box((sx * 0.08, 2.08, 0.22), (0.05, 0.05, 0.03), DARK)
        return mb

    def _pose(self, dt: float, speed: float, grounded: bool, swimming: bool) -> None:
        if self.action == "hit":
            k = math.sin(self.action_progress() * math.pi * 3) * (1 - self.action_progress())
            set_rot(self.pivot, -12 * k, 0, 5 * k)
        else:
            set_rot(self.pivot, 0, 0, 0)

    def _pose_death(self, t: float) -> None:
        pass


# ------------------------------------------------------------------ Grakk the Tunnelmaw
class GrakkRig(Rig):
    """A hulking tunnel brute with a gaping maw, stone-plated back and huge fists."""

    def __init__(self) -> None:
        super().__init__()
        self.height = 4.6
        self.radius = 1.8
        skin = (0.52, 0.46, 0.38, 1)
        self.skin = skin
        self.hips = self.body.attachNewNode("hips")
        self.hips.setY(1.3)
        self.torso = self.hips.attachNewNode("torso")
        copy_part(("grakk", "torso"), self._torso, self.torso)
        self.jaw = self.torso.attachNewNode("jaw")
        self.jaw.setPos(0, 2.05, 0.95)
        copy_part(("grakk", "jaw"), self._jaw, self.jaw)
        self.arms: list[NodePath] = []
        for side in (-1, 1):
            arm = self.torso.attachNewNode("arm")
            arm.setPos(side * 1.35, 2.4, 0.3)
            copy_part(("grakk", "arm", side), lambda side=side: self._arm(side), arm)
            self.arms.append(arm)
        self.legs: list[NodePath] = []
        for side in (-1, 1):
            leg = self.hips.attachNewNode("leg")
            leg.setPos(side * 0.6, 0, 0)
            copy_part(("grakk", "leg"), self._leg, leg)
            self.legs.append(leg)
        self.burrow = 0.0

    def _torso(self) -> MeshBuilder:
        mb = MeshBuilder()
        s = self.skin
        mb.box((0, 0.3, 0), (1.6, 0.8, 1.2), (0.3, 0.22, 0.16, 1))
        mb.box((0, 1.5, 0.2), (2.5, 2.0, 1.8), s, taper=1.25)
        mb.box((0, 1.4, 0.95), (1.8, 1.4, 0.3), shade(s, 1.15))
        for i, (x, y) in enumerate(((-0.7, 2.4), (0.0, 2.6), (0.7, 2.4), (-0.4, 1.8), (0.4, 1.8), (0.0, 1.2))):
            mb.sphere((x, y, -0.7), (0.55, 0.45, 0.4), (0.38, 0.33, 0.3, 1), detail=0, noise=0.25, seed=i)
            mb.cone((x, y + 0.2, -0.85), 0.14, 0.6, (0.3, 0.26, 0.24, 1), rot=(-40, 0, 0))
        mb.box((0, 2.3, 0.9), (1.0, 0.6, 0.8), s)
        for sx in (-1, 1):
            mb.box((sx * 0.25, 2.45, 1.3), (0.18, 0.1, 0.05), (1.0, 0.55, 0.1, 1))
        mb.box((0, 2.15, 1.35), (0.9, 0.35, 0.1), (0.25, 0.05, 0.04, 1))
        for i in range(6):
            mb.cone((-0.4 + i * 0.16, 2.02, 1.38), 0.05, 0.18, IVORY, rot=(180, 0, 0), segments=3)
        return mb

    def _jaw(self) -> MeshBuilder:
        mb = MeshBuilder()
        mb.box((0, -0.15, 0.25), (1.2, 0.35, 0.9), shade(self.skin, 0.9))
        for i in range(7):
            mb.cone((-0.5 + i * 0.166, 0.02, 0.62), 0.06, 0.26, IVORY, segments=3)
        for sx in (-1, 1):
            mb.cone((sx * 0.55, 0.0, 0.55), 0.1, 0.6, IVORY, rot=(-15, 0, sx * -15))
        return mb

    def _arm(self, side: int) -> MeshBuilder:
        mb = MeshBuilder()
        s = self.skin
        mb.beam((0, 0, 0), (side * 0.3, -1.2, 0.2), 0.42, s, segments=6)
        mb.beam((side * 0.3, -1.2, 0.2), (side * 0.35, -2.3, 0.45), 0.36, shade(s, 0.95), segments=6)
        mb.sphere((side * 0.35, -2.6, 0.5), (0.62, 0.55, 0.62), shade(s, 0.85), detail=1)
        for k in range(3):
            mb.cone((side * (0.2 + 0.15 * k), -2.45, 0.95), 0.08, 0.25, (0.35, 0.3, 0.28, 1), rot=(90, 0, 0), segments=3)
        mb.box((side * 0.1, 0.1, 0), (0.9, 0.5, 0.9), (0.38, 0.33, 0.3, 1))
        return mb

    def _leg(self) -> MeshBuilder:
        mb = MeshBuilder()
        mb.box((0, -0.55, 0), (0.7, 1.1, 0.75), (0.3, 0.22, 0.16, 1))
        mb.box((0, -1.2, 0.2), (0.8, 0.25, 1.1), shade(self.skin, 0.8))
        return mb

    def _pose(self, dt: float, speed: float, grounded: bool, swimming: bool) -> None:
        ph = self.phase * 0.8
        amp = 22 * self.move_blend
        set_rot(self.legs[0], swing(ph, amp), 0, 0)
        set_rot(self.legs[1], swing(ph + math.pi, amp), 0, 0)
        arm_l = [swing(ph + math.pi, amp * 0.6), 0, -12]
        arm_r = [swing(ph, amp * 0.6), 0, 12]
        torso_x = 18 + math.sin(self.idle_t * 1.2) * 2
        jaw = 8 + math.sin(self.idle_t * 1.7) * 6
        act, t = self.action, self.action_progress()
        if act == "attack":
            if t < 0.45:
                k = t / 0.45
                arm_r = [-130 * k, 0, 20]
            else:
                k = (t - 0.45) / 0.55
                arm_r = [-130 + 160 * min(k * 2, 1), 0, 20 * (1 - k)]
            jaw = 25 * math.sin(t * math.pi)
        elif act == "slam":
            if t < 0.6:
                k = t / 0.6
                arm_l = [-150 * k, 0, -15]
                arm_r = [-150 * k, 0, 15]
                torso_x = 18 - 25 * k
            else:
                k = (t - 0.6) / 0.4
                arm_l = [-150 + 190 * min(k * 2.5, 1), 0, -15]
                arm_r = [-150 + 190 * min(k * 2.5, 1), 0, 15]
                torso_x = -7 + 45 * min(k * 2.5, 1)
            jaw = 35 * math.sin(t * math.pi)
        elif act == "roar":
            k = math.sin(t * math.pi)
            arm_l = [-60 * k, 0, -60 * k]
            arm_r = [-60 * k, 0, 60 * k]
            torso_x = 18 - 30 * k
            jaw = 45 * k
        set_rot(self.arms[0], *arm_l)
        set_rot(self.arms[1], *arm_r)
        set_rot(self.torso, torso_x, 0, 0)
        set_rot(self.jaw, jaw, 0, 0)
        self.body.setY(-self.burrow * 5.0)

    def _pose_death(self, t: float) -> None:
        e = 1 - (1 - t) ** 3
        set_rot(self.body, -80 * e, 0, 10 * e)
        self.body.setY(0.3 * e)


# ------------------------------------------------------------------ factory
def build_enemy_rig(etype: dict[str, Any]) -> Rig:
    """Create the right model for an enemy definition from enemies.json."""
    model = etype.get("model", "boar")
    color = etype.get("color", (0.5, 0.4, 0.3))
    accent = etype.get("accent")
    if model in ("boar", "lizard", "hyena"):
        rig: Rig = QuadrupedRig(model, color, accent)
    elif model == "scorpion":
        rig = ScorpionRig(color, accent)
    elif model == "crab":
        rig = CrabRig(color)
    elif model == "vulture":
        rig = VultureRig(color)
    elif model == "dummy":
        rig = DummyRig()
    elif model == "grakk":
        rig = GrakkRig()
    else:
        rig = build_humanoid(etype.get("look"))
    sc = float(etype.get("scale", 1.0))
    if sc != 1.0 and model != "humanoid":
        rig.body.setScale(sc)
        rig.height *= sc
        rig.radius *= sc
        rig.scale = sc
    elif sc != 1.0:
        rig.body.setScale(sc)
        rig.height *= sc
        rig.radius *= sc
        rig.scale = sc
    return rig
