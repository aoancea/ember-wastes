"""The Ironmaw Gate doors: a separate, animated part of the gate that opens at the end of the story."""
from __future__ import annotations


from core.events import events
from core.meshgen import MeshBuilder
from core.util import set_yaw

DOOR = (0.30, 0.20, 0.13, 1)
IRON = (0.30, 0.29, 0.31, 1)


def _door_mesh(direction: int) -> MeshBuilder:
    """One door leaf built from its hinge (origin) towards +x (direction=1) or -x (direction=-1)."""
    mb = MeshBuilder()
    w = 7.2
    cx = direction * w / 2
    mb.box((cx, 9.0, 0), (w, 18.0, 1.0), DOOR)
    for y in (3.0, 8.0, 13.0, 16.5):
        mb.box((cx, y, -0.6), (w + 0.2, 0.6, 0.3), IRON)
    for y in (5.5, 10.5):
        for k in range(3):
            mb.sphere((direction * (1.2 + k * 2.2), y, -0.7), 0.28, IRON, detail=0)
    mb.box((direction * (w - 0.15), 9.0, -0.6), (0.3, 18.0, 0.4), IRON)
    return mb


class GateDoors:
    def __init__(self, game_world, x: float, y: float, z: float) -> None:
        self.world = game_world
        self.root = game_world.root.attachNewNode("gate_doors")
        self.left = self.root.attachNewNode("left")
        self.right = self.root.attachNewNode("right")
        self.left.setPos(x - 7.2, y, z - 1.0)
        self.right.setPos(x + 7.2, y, z - 1.0)
        _door_mesh(1).build("door_l").reparentTo(self.left)
        _door_mesh(-1).build("door_r").reparentTo(self.right)
        self.x, self.y, self.z = x, y, z
        self.amount = 0.0
        self.target = 0.0
        self.collider = None
        self._add_collider()

    def _add_collider(self) -> None:
        if self.collider is None:
            self.collider = self.world.collision.add_box(self.x, self.z - 1.0, 7.6, 1.2, 0.0, top=self.y + 18.0, tag="gate_door")

    def _remove_collider(self) -> None:
        if self.collider is not None:
            self.world.collision.remove(self.collider)
            self.collider = None

    def set_open(self, value: bool, instant: bool = False) -> None:
        self.target = 1.0 if value else 0.0
        if instant:
            self.amount = self.target
            self._apply()
        if value:
            self._remove_collider()
            if not instant:
                events.emit("sound", name="stomp")
                events.emit("chat", text="<rgb(1,0.85,0.4)>With a groan of iron, the Ironmaw Gate swings open.")
        else:
            self._add_collider()

    def _apply(self) -> None:
        a = self.amount
        e = a * a * (3 - 2 * a)
        set_yaw(self.left, -82 * e)
        set_yaw(self.right, 82 * e)

    def update(self, dt: float) -> None:
        if abs(self.amount - self.target) > 1e-4:
            step = dt * 0.22
            self.amount = min(self.target, self.amount + step) if self.target > self.amount else max(self.target, self.amount - step)
            self._apply()
