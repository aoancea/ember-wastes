"""Visual combat effects: projectiles, beams, sparks, telegraphs, shockwaves and glows."""
from __future__ import annotations

import math
import random
from typing import Callable

import numpy as np
from panda3d.core import NodePath, TransparencyAttrib, Vec3

from core.meshgen import MeshBuilder, make_geom_node
from core.textures import radial_texture, ring_texture, telegraph_texture
from core.util import set_rot

_protos: dict[str, NodePath] = {}


def _proto(name: str, build: Callable[[], MeshBuilder]) -> NodePath:
    if name not in _protos:
        _protos[name] = build().build(name)
    return _protos[name]


def _arrow() -> MeshBuilder:
    mb = MeshBuilder()
    mb.beam((0, 0, -0.45), (0, 0, 0.45), 0.025, (0.55, 0.4, 0.25, 1), segments=3)
    mb.cone((0, 0, 0.45), 0.05, 0.14, (0.7, 0.7, 0.72, 1), rot=(90, 0, 0), segments=4)
    mb.box((0, 0, -0.42), (0.14, 0.01, 0.12), (0.9, 0.9, 0.85, 1))
    return mb


def _bolt() -> MeshBuilder:
    mb = MeshBuilder()
    mb.beam((0, 0, -0.3), (0, 0, 0.3), 0.03, (0.3, 0.25, 0.2, 1), segments=3)
    mb.cone((0, 0, 0.3), 0.05, 0.12, (0.4, 0.4, 0.42, 1), rot=(90, 0, 0), segments=4)
    return mb


def _orb(color: tuple) -> Callable[[], MeshBuilder]:
    def b() -> MeshBuilder:
        mb = MeshBuilder()
        mb.sphere((0, 0, 0), 0.28, color, detail=1)
        mb.sphere((0, 0, 0), 0.16, (1.0, 0.95, 0.7, 1), detail=0)
        return mb
    return b


def _cube(color: tuple) -> Callable[[], MeshBuilder]:
    def b() -> MeshBuilder:
        mb = MeshBuilder()
        mb.box((0, 0, 0), (1, 1, 1), color, jitter=0)
        return mb
    return b


class Effect:
    """Base class: ``update`` returns False when finished."""

    def __init__(self, node: NodePath, life: float) -> None:
        self.node = node
        self.life = life
        self.t = 0.0

    def update(self, dt: float) -> bool:
        self.t += dt
        return self.t < self.life

    def destroy(self) -> None:
        self.node.removeNode()


class Projectile(Effect):
    def __init__(self, node: NodePath, source, target, speed: float, on_hit: Callable[[], None] | None,
                 arc: float, fx: "EffectsManager", impact: str) -> None:
        super().__init__(node, 6.0)
        self.target = target
        self.speed = speed
        self.on_hit = on_hit
        self.arc = arc
        self.fx = fx
        self.impact = impact
        self.pos = Vec3(source.x, source.y + source.height * 0.65, source.z)
        self.start = Vec3(self.pos)
        self.total = max(0.1, self._target_pos().__sub__(self.pos).length())
        node.setPos(self.pos)

    def _target_pos(self) -> Vec3:
        t = self.target
        return Vec3(t.x, t.y + t.height * 0.55, t.z)

    def update(self, dt: float) -> bool:
        self.t += dt
        tp = self._target_pos()
        d = tp - self.pos
        dist = d.length()
        step = self.speed * dt
        if dist <= step or self.t > self.life:
            if self.on_hit:
                self.on_hit()
            self.fx.impact(tp, self.impact)
            return False
        d.normalize()
        self.pos += d * step
        done = 1.0 - dist / self.total
        lift = math.sin(max(0.0, min(done, 1.0)) * math.pi) * self.arc
        p = Vec3(self.pos.x, self.pos.y + lift, self.pos.z)
        self.node.setPos(p)
        self.node.lookAt(tp, Vec3(0, 1, 0))
        return True


class Particles(Effect):
    """A handful of small cubes flying out from a point with gravity, fading out."""

    def __init__(self, parent: NodePath, pos: Vec3, color: tuple, count: int, speed: float,
                 life: float, size: float, gravity: float = 9.0, up: float = 1.0) -> None:
        node = parent.attachNewNode("particles")
        super().__init__(node, life)
        proto = _proto(f"cube{color}", _cube(color))
        self.parts: list[tuple[NodePath, Vec3]] = []
        for _ in range(count):
            p = proto.copyTo(node)
            p.setPos(pos)
            s = size * random.uniform(0.6, 1.3)
            p.setScale(s)
            v = Vec3(random.uniform(-1, 1), random.uniform(0.2, 1.0) * up, random.uniform(-1, 1))
            v.normalize()
            self.parts.append((p, v * speed * random.uniform(0.5, 1.0)))
        self.gravity = gravity
        node.setShaderInput("u_emissive", 1.0)
        node.setTransparency(TransparencyAttrib.M_alpha)

    def update(self, dt: float) -> bool:
        self.t += dt
        k = max(0.0, 1.0 - self.t / self.life)
        for i, (p, v) in enumerate(self.parts):
            v.y -= self.gravity * dt
            p.setPos(p.getPos() + v * dt)
            p.setScale(p.getScale() * (0.97 if k < 0.5 else 1.0))
        self.node.setAlphaScale(k)
        return self.t < self.life


class Decal(Effect):
    """Ground-draped textured quad (telegraphs, rings)."""

    def __init__(self, fx: "EffectsManager", x: float, z: float, radius: float, tex, color: tuple,
                 life: float, grow: bool = False, follow=None, lift: float = 0.12) -> None:
        node = fx.draped(x, z, radius, lift)
        node.reparentTo(fx.root)
        node.setTexture(tex, 1)
        node.setTransparency(TransparencyAttrib.M_alpha)
        node.setDepthWrite(False)
        node.setBin("transparent", 5)
        node.setShaderInput("u_emissive", 1.0)
        node.setColorScale(*color)
        node.setTwoSided(True)
        super().__init__(node, life)
        self.grow = grow
        self.follow = follow
        self.color = color
        self.base = (x, z)

    def update(self, dt: float) -> bool:
        self.t += dt
        k = self.t / self.life
        pulse = 0.75 + 0.25 * math.sin(self.t * 14)
        a = self.color[3] * (min(1.0, self.t * 6) if k < 0.85 else (1 - k) / 0.15)
        self.node.setColorScale(self.color[0], self.color[1], self.color[2], max(0.0, a * pulse))
        return self.t < self.life


class Ring(Effect):
    """Expanding flat ring (shockwaves, level-up)."""

    def __init__(self, fx: "EffectsManager", pos: Vec3, radius: float, color: tuple, life: float) -> None:
        node = fx.flat_quad("ring", fx.ring_tex)
        node.reparentTo(fx.root)
        node.setPos(pos.x, pos.y + 0.2, pos.z)
        node.setColorScale(*color)
        super().__init__(node, life)
        self.radius = radius
        self.color = color

    def update(self, dt: float) -> bool:
        self.t += dt
        k = min(self.t / self.life, 1.0)
        r = 0.3 + self.radius * (1 - (1 - k) ** 2)
        self.node.setScale(r)
        self.node.setColorScale(self.color[0], self.color[1], self.color[2], self.color[3] * (1 - k))
        return self.t < self.life


class Beam(Effect):
    """Jagged lightning beam between two points."""

    def __init__(self, fx: "EffectsManager", a: Vec3, b: Vec3, color: tuple, life: float = 0.25) -> None:
        mb = MeshBuilder()
        pts = [a]
        n = 7
        for i in range(1, n):
            t = i / n
            p = a + (b - a) * t
            p += Vec3(random.uniform(-0.5, 0.5), random.uniform(-0.5, 0.5), random.uniform(-0.5, 0.5))
            pts.append(p)
        pts.append(b)
        for p0, p1 in zip(pts[:-1], pts[1:]):
            mb.beam(tuple(p0), tuple(p1), 0.07, color, segments=3)
            mb.beam(tuple(p0), tuple(p1), 0.03, (1, 1, 1, 1), segments=3)
        node = mb.build("beam")
        node.reparentTo(fx.root)
        node.setShaderInput("u_emissive", 1.6)
        node.setTransparency(TransparencyAttrib.M_alpha)
        super().__init__(node, life)

    def update(self, dt: float) -> bool:
        self.t += dt
        self.node.setAlphaScale(max(0.0, 1 - self.t / self.life))
        return self.t < self.life


class Column(Effect):
    """Rising column of light (level up) that follows a unit."""

    def __init__(self, fx: "EffectsManager", unit, color: tuple, life: float = 2.2) -> None:
        mb = MeshBuilder()
        mb.cylinder((0, 0, 0), 1.1, 7.0, color, radius_top=0.6, segments=12, caps=False, jitter=0)
        node = mb.build("column")
        node.reparentTo(fx.root)
        node.setShaderInput("u_emissive", 1.6)
        node.setTransparency(TransparencyAttrib.M_alpha)
        node.setDepthWrite(False)
        node.setTwoSided(True)
        node.setBin("transparent", 30)
        super().__init__(node, life)
        self.unit = unit

    def update(self, dt: float) -> bool:
        self.t += dt
        k = self.t / self.life
        self.node.setPos(self.unit.x, self.unit.y, self.unit.z)
        self.node.setScale(1.0, 0.2 + min(1.0, self.t * 3), 1.0)
        self.node.setH(self.t * 90)
        self.node.setAlphaScale(max(0.0, 0.55 * (1 - k)))
        return self.t < self.life


class EffectsManager:
    """Creates and updates short-lived effects."""

    def __init__(self, game) -> None:
        self.game = game
        self.root = game.world.fx.attachNewNode("effects")
        self.effects: list[Effect] = []
        self.ring_tex = ring_texture(128, 0.18)
        self.tele_tex = telegraph_texture(128)
        self.glow_tex = radial_texture(64, 0.0, 1.0, (255, 255, 255), power=1.5)

    # ----------------------------------------------------------------- helpers
    def flat_quad(self, name: str, tex) -> NodePath:
        pos = np.array([[-1, 0, -1], [1, 0, -1], [1, 0, 1], [-1, 0, 1]], np.float32)
        uvs = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], np.float32)
        nrm = np.tile(np.array([0, 1, 0], np.float32), (4, 1))
        col = np.ones((4, 4), np.float32)
        node = make_geom_node(pos, nrm, col, uvs=uvs, indices=np.array([0, 1, 2, 0, 2, 3], np.uint32), name=name)
        node.setTexture(tex, 1)
        node.setTransparency(TransparencyAttrib.M_alpha)
        node.setDepthWrite(False)
        node.setBin("transparent", 6)
        node.setShaderInput("u_emissive", 1.0)
        node.setTwoSided(True)
        return node

    def draped(self, cx: float, cz: float, radius: float, lift: float = 0.12, n: int = 12) -> NodePath:
        """Grid mesh that follows the ground over a square of half-size ``radius``."""
        ground = self.game.world.ground
        xs = np.linspace(-radius, radius, n + 1, dtype=np.float32)
        X, Z = np.meshgrid(xs, xs)
        H = np.array([[ground(cx + float(x), cz + float(z)) for x in xs] for z in xs], np.float32)
        pos = np.stack([X + cx, H + lift, Z + cz], -1).reshape(-1, 3)
        uvs = np.stack([(X / radius + 1) / 2, (Z / radius + 1) / 2], -1).reshape(-1, 2)
        nrm = np.tile(np.array([0, 1, 0], np.float32), (pos.shape[0], 1))
        col = np.ones((pos.shape[0], 4), np.float32)
        from core.meshgen import grid_indices
        return make_geom_node(pos, nrm, col, uvs=uvs, indices=grid_indices(n, n), name="decal")

    def add(self, e: Effect) -> Effect:
        self.effects.append(e)
        return e

    # ----------------------------------------------------------------- effects
    def projectile(self, source, target, kind: str, on_hit: Callable[[], None] | None = None) -> None:
        specs = {
            "arrow": ("arrow", _arrow, 48.0, 0.8, "spark", 1.0),
            "bolt": ("bolt", _bolt, 44.0, 0.3, "spark", 1.0),
            "fireball": ("fireball", _orb((1.0, 0.45, 0.1, 1)), 24.0, 0.4, "fire", 1.4),
            "ember": ("ember", _orb((1.0, 0.55, 0.15, 1)), 26.0, 1.2, "fire", 1.4),
            "venom": ("venom", _orb((0.35, 0.9, 0.2, 1)), 40.0, 0.6, "venom", 1.3),
            "frost": ("frost", _orb((0.5, 0.8, 1.0, 1)), 30.0, 0.4, "spark", 1.3),
        }
        name, build, speed, arc, impact, emissive = specs.get(kind, specs["arrow"])
        node = _proto(name, build).copyTo(self.root)
        if emissive > 1.0:
            node.setShaderInput("u_emissive", emissive)
        self.add(Projectile(node, source, target, speed, on_hit, arc, self, impact))

    def impact(self, pos: Vec3, kind: str = "spark") -> None:
        colors = {"spark": (1.0, 0.85, 0.5, 1), "fire": (1.0, 0.5, 0.1, 1), "venom": (0.4, 0.9, 0.2, 1),
                  "blood": (0.7, 0.08, 0.05, 1), "heal": (0.3, 1.0, 0.5, 1), "nature": (0.5, 0.8, 1.0, 1),
                  "dust": (0.75, 0.55, 0.38, 1)}
        self.add(Particles(self.root, pos, colors.get(kind, colors["spark"]), 7, 5.0, 0.45, 0.09))

    def hit(self, unit, crit: bool = False, kind: str = "blood") -> None:
        pos = Vec3(unit.x, unit.y + unit.height * 0.55, unit.z)
        col = {"blood": (0.75, 0.1, 0.06, 1), "spark": (1.0, 0.85, 0.4, 1), "fire": (1.0, 0.5, 0.1, 1),
               "nature": (0.55, 0.85, 1.0, 1), "venom": (0.4, 0.9, 0.2, 1)}.get(kind, (0.75, 0.1, 0.06, 1))
        self.add(Particles(self.root, pos, col, 10 if crit else 6, 6.0 if crit else 4.0, 0.4, 0.1 if crit else 0.08))

    def lightning(self, a, b) -> None:
        pa = Vec3(a.x, a.y + a.height * 0.7, a.z)
        pb = Vec3(b.x, b.y + b.height * 0.55, b.z)
        self.add(Beam(self, pa, pb, (0.55, 0.75, 1.0, 1), 0.28))
        self.impact(pb, "nature")

    def telegraph_circle(self, x: float, z: float, radius: float, duration: float, follow=None,
                         color: tuple = (1, 1, 1, 0.9)) -> None:
        self.add(Decal(self, x, z, radius, self.tele_tex, color, duration + 0.15, follow=follow))

    def shockwave(self, x: float, y: float, z: float, radius: float, color: tuple = (1.0, 0.7, 0.4, 0.9)) -> None:
        self.add(Ring(self, Vec3(x, y, z), radius, color, 0.45))
        self.add(Particles(self.root, Vec3(x, y + 0.3, z), (0.72, 0.52, 0.36, 1), 14, 7.0, 0.6, 0.14, gravity=12.0))
        self.game.cam.shake(0.25, 0.3)

    def breath(self, unit, duration: float) -> None:
        yaw = math.radians(unit.yaw)
        fx, fz = math.sin(yaw), math.cos(yaw)
        for i in range(3):
            d = 1.5 + i * 2.0
            pos = Vec3(unit.x + fx * d, unit.y + 0.8, unit.z + fz * d)
            self.add(Particles(self.root, pos, (1.0, 0.45 + 0.1 * i, 0.1, 1), 8, 3.0, duration, 0.18, gravity=-2.0))

    def level_up(self, unit) -> None:
        self.add(Column(self, unit, (1.0, 0.85, 0.35, 1), 2.4))
        self.add(Ring(self, Vec3(unit.x, unit.y, unit.z), 5.0, (1.0, 0.85, 0.4, 1), 0.9))
        self.add(Particles(self.root, Vec3(unit.x, unit.y + 1.0, unit.z), (1.0, 0.9, 0.4, 1), 24, 6.0, 1.4, 0.1, gravity=-3.0))

    def heal(self, unit) -> None:
        self.add(Particles(self.root, Vec3(unit.x, unit.y + 0.6, unit.z), (0.4, 1.0, 0.55, 1), 12, 2.5, 1.0, 0.09, gravity=-4.0))

    def dust_puff(self, x: float, y: float, z: float, n: int = 8) -> None:
        self.add(Particles(self.root, Vec3(x, y + 0.2, z), (0.75, 0.55, 0.38, 1), n, 3.0, 0.5, 0.12, gravity=2.0))

    def arrow_rain(self, x: float, z: float, radius: float) -> None:
        y = self.game.world.ground(x, z)
        for _ in range(10):
            a = random.uniform(0, math.tau)
            d = random.uniform(0, radius)
            px, pz = x + math.cos(a) * d, z + math.sin(a) * d
            node = _proto("arrow", _arrow).copyTo(self.root)
            self.add(Falling(node, Vec3(px, y + 14 + random.uniform(0, 4), pz), self.game.world.ground(px, pz)))
        self.add(Ring(self, Vec3(x, y, z), radius, (1.0, 0.95, 0.8, 0.6), 0.35))

    def update(self, dt: float) -> None:
        keep = []
        for e in self.effects:
            if e.update(dt):
                keep.append(e)
            else:
                e.destroy()
        self.effects = keep

    def clear(self) -> None:
        for e in self.effects:
            e.destroy()
        self.effects.clear()


class Falling(Effect):
    def __init__(self, node: NodePath, start: Vec3, ground: float) -> None:
        super().__init__(node, 1.2)
        self.pos = start
        self.ground = ground
        node.setPos(start)
        set_rot(node, 90, 0, 0)

    def update(self, dt: float) -> bool:
        self.t += dt
        if self.pos.y > self.ground + 0.3:
            self.pos.y -= 45 * dt
            self.node.setPos(self.pos)
        return self.t < self.life
