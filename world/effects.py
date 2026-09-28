"""Atmospheric effects: GPU dust particles and the heat-haze post-process."""
from __future__ import annotations

import math

import numpy as np
from direct.filter.FilterManager import FilterManager
from panda3d.core import (FrameBufferProperties, NodePath, OmniBoundingVolume, Texture as PTexture,
                          TransparencyAttrib, Vec3)

from core import shaders
from core.meshgen import make_geom_node


class Dust:
    """Hundreds of drifting dust motes animated entirely in the vertex shader."""

    def __init__(self, render: NodePath, count: int = 700, box: float = 60.0) -> None:
        rng = np.random.default_rng(5)
        seeds = rng.random((count, 3)).astype(np.float32)
        corners = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], np.float32)
        pos = np.repeat(seeds, 4, axis=0)
        uvs = np.tile(corners, (count, 1))
        nrm = np.zeros_like(pos)
        col = np.ones((pos.shape[0], 4), np.float32)
        base = (np.arange(count, dtype=np.uint32) * 4)[:, None]
        idx = (base + np.array([0, 1, 2, 0, 2, 3], np.uint32)[None, :]).ravel()
        self.node = make_geom_node(pos, nrm, col, uvs=uvs, indices=idx, name="dust")
        self.node.reparentTo(render)
        self.node.node().setBounds(OmniBoundingVolume())
        self.node.node().setFinal(True)
        self.node.setShader(shaders.dust_shader())
        self.node.setTransparency(TransparencyAttrib.M_alpha)
        self.node.setDepthWrite(False)
        self.node.setBin("transparent", 20)
        self.node.setTwoSided(True)
        self.node.setShaderInput("u_box", box)
        self.node.setShaderInput("u_wind", Vec3(2.2, 0.0, 0.9))
        self.node.setShaderInput("u_dust_color", Vec3(0.9, 0.7, 0.5))
        self.node.setShaderInput("u_dust_alpha", 0.5)
        self._t = 0.0

    def update(self, dt: float, light_color: tuple[float, float, float], fog: tuple[float, float, float]) -> None:
        self._t += dt
        gust = 0.75 + 0.25 * math.sin(self._t * 0.21) + 0.15 * math.sin(self._t * 0.53)
        self.node.setShaderInput("u_wind", Vec3(2.4 * gust, 0.0, 1.0 * gust))
        c = (fog[0] * 0.55 + light_color[0] * 0.25, fog[1] * 0.5 + light_color[1] * 0.2, fog[2] * 0.45 + light_color[2] * 0.15)
        self.node.setShaderInput("u_dust_color", Vec3(*c))
        self.node.setShaderInput("u_dust_alpha", 0.22 + 0.18 * gust)

    def set_visible(self, visible: bool) -> None:
        if visible:
            self.node.show()
        else:
            self.node.hide()


class PostProcess:
    """Full-screen pass for heat haze, vignette and damage/level-up flashes."""

    def __init__(self, base, near: float, far: float) -> None:
        self.base = base
        self.manager: FilterManager | None = None
        self.quad: NodePath | None = None
        self.near, self.far = near, far
        self.haze = 0.0
        self.haze_enabled = True
        self.flash = 0.0
        self.flash_color = Vec3(1, 1, 1)

    @property
    def enabled(self) -> bool:
        return self.manager is not None

    def enable(self) -> bool:
        if self.manager:
            return True
        try:
            self.manager = FilterManager(self.base.win, self.base.cam)
            color = PTexture()
            depth = PTexture()
            props = FrameBufferProperties()
            props.setRgbColor(True)
            props.setDepthBits(24)
            props.setMultisamples(4)
            quad = self.manager.renderSceneInto(colortex=color, depthtex=depth, fbprops=props)
            if quad is None:
                self.manager.cleanup()
                self.manager = FilterManager(self.base.win, self.base.cam)
                quad = self.manager.renderSceneInto(colortex=color, depthtex=depth)
            if quad is None:
                raise RuntimeError("render-to-texture unavailable")
            self.quad = quad
            quad.setShader(shaders.post_shader())
            quad.setShaderInput("tex", color)
            quad.setShaderInput("dtex", depth)
            self._push()
            return True
        except Exception as exc:  # pragma: no cover - depends on the GPU driver
            print("[post] disabled:", exc)
            if self.manager:
                self.manager.cleanup()
            self.manager = None
            self.quad = None
            return False

    def disable(self) -> None:
        if self.manager:
            self.manager.cleanup()
        self.manager = None
        self.quad = None

    def set_clip(self, near: float, far: float) -> None:
        self.near, self.far = near, far

    def trigger_flash(self, color: tuple[float, float, float], strength: float = 0.35) -> None:
        self.flash_color = Vec3(*color)
        self.flash = max(self.flash, strength)

    def _push(self) -> None:
        if self.quad is None:
            return
        self.quad.setShaderInput("u_haze", self.haze)
        self.quad.setShaderInput("u_clip", (self.near, self.far))
        self.quad.setShaderInput("u_flash", self.flash)
        self.quad.setShaderInput("u_flash_color", self.flash_color)

    def update(self, dt: float, daylight: float) -> None:
        self.haze = daylight if self.haze_enabled else 0.0
        self.flash = max(0.0, self.flash - dt * 1.6)
        self._push()
