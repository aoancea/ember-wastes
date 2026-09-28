"""The overworld: terrain, props, collision, sky/lighting, water and atmosphere."""
from __future__ import annotations

import time

from panda3d.core import NodePath, Vec3

from core import data, shaders
from world.collision import CollisionWorld
from world.effects import Dust
from world.props import PropBatcher
from world.sky import Environment
from world.terrain import Terrain
from world.water import Water
from world.zones import ZoneMap, place_structures, scatter_nature


class World:
    """Builds and updates every static part of the Ember Wastes."""

    def __init__(self, render: NodePath, view_distance: float) -> None:
        t0 = time.perf_counter()
        zone_data = data.zones()
        self.view_distance = view_distance
        self.zones = ZoneMap(zone_data)
        self.terrain = Terrain(zone_data)
        self.root = render.attachNewNode("world_root")
        self.root.setShader(shaders.world_shader())
        self.env = Environment(render, view_distance)
        self.terrain.build(self.root)
        self.collision = CollisionWorld(self.terrain.height_at)
        depth_tex, rect = self.terrain.water_depth_texture()
        self.water = Water(render, depth_tex, rect)
        self.water.attach_floor(self.root)
        self.props = PropBatcher(self.root, self.collision, self.env)
        place_structures(self.zones, self.terrain, self.props)
        scatter_nature(self.zones, self.terrain, self.props)
        self.props.build()
        self.gate_doors = None
        if self.zones.gate_pos is not None:
            from world.gate import GateDoors
            self.gate_doors = GateDoors(self, *self.zones.gate_pos)
        self.dust = Dust(render)
        self.actors = self.root.attachNewNode("actors")
        self.fx = self.root.attachNewNode("fx")
        self._vis_timer = 0.0
        self.underground = False
        print(f"[world] built in {time.perf_counter() - t0:.2f}s, props={self.props.count}, "
              f"obstacles={len(self.collision.obstacles)}, lights={len(self.env.lights)}")

    def ground(self, x: float, z: float, feet_y: float | None = None) -> float:
        return self.collision.ground_height(x, z, feet_y)

    def set_view_distance(self, d: float) -> None:
        self.view_distance = d
        self.env.view_distance = d
        self._vis_timer = 0.0

    def set_underground(self, value: bool) -> None:
        self.underground = value
        self.env.set_underground(value)
        self.water.set_visible(not value)
        self.dust.set_visible(not value)
        self.terrain.root.show() if not value else self.terrain.root.hide()
        self.props.root.show() if not value else self.props.root.hide()

    def update(self, dt: float, cam_pos: Vec3) -> None:
        self.env.update(dt, cam_pos)
        if not self.underground:
            self.water.update(cam_pos)
            self.dust.update(dt, self.env.light_color, self.env.fog_color)
            self._vis_timer -= dt
            if self._vis_timer <= 0:
                self._vis_timer = 0.3
                self.terrain.update_visibility(cam_pos.x, cam_pos.z, self.view_distance)
                self.props.update_visibility(cam_pos.x, cam_pos.z, min(self.view_distance, 240.0))
