"""Escort quests: an NPC walks a path, ambushes spawn, the quest fails if the NPC dies."""
from __future__ import annotations

import math
from typing import Any

from core.events import events


class EscortController:
    """Drives at most one escort at a time."""

    def __init__(self, game) -> None:
        self.game = game
        self.qid: str | None = None
        self.obj: dict[str, Any] | None = None
        self.npc = None
        self.index = 0
        self.spawned: list[Any] = []
        self.triggered: set[int] = set()
        self.wait = 0.0
        events.on("unit_died", self._on_died)

    @property
    def active(self) -> bool:
        return self.qid is not None

    def start(self, qid: str, obj: dict[str, Any]) -> None:
        npc = self.game.npcs.get(obj["npc"])
        if npc is None:
            return
        npc.reset()
        npc.targetable = True
        npc.faction = "friendly"
        npc.rig.revive()
        npc.rig.action = None
        npc.walk_speed = 4.0
        self.qid, self.obj, self.npc = qid, obj, npc
        self.index = 0
        self.triggered.clear()
        self.spawned.clear()
        self.wait = 2.0
        events.emit("chat", text=f"<rgb(0.4,1,0.4)>{npc.name} says: Stay close. If they come, they'll come fast.")

    def stop(self) -> None:
        if self.npc is not None:
            self.npc.reset()
        for e in self.spawned:
            if not e.dead:
                e.evade()
        self.qid = self.obj = self.npc = None

    def _on_died(self, unit: Any, killer: Any = None, **_: Any) -> None:
        if self.npc is not None and unit is self.npc and self.qid:
            qid = self.qid
            self.game.quests.fail(qid, f"{unit.name} has fallen.")
            npc = self.npc
            self.qid = self.obj = self.npc = None
            self.game.pending(6.0, npc.reset)

    def update(self, dt: float) -> None:
        if not self.active:
            return
        npc = self.npc
        p = self.game.player
        path = self.obj["path"]
        if self.wait > 0:
            self.wait -= dt
            return
        # hold position while enemies are attacking
        fighting = any(not e.dead and e.state == "combat" for e in self.spawned)
        far = math.hypot(p.x - npc.x, p.z - npc.z) > 22
        if fighting or far or p.dead:
            npc.walk_target = None
            return
        if npc.walk_target is None:
            if self.index >= len(path):
                self._finish()
                return
            for amb_i, amb in enumerate(self.obj.get("ambushes", [])):
                if amb["at"] == self.index and amb_i not in self.triggered:
                    self.triggered.add(amb_i)
                    self._ambush(amb)
                    return
            tx, tz = path[self.index]
            npc.walk_target = (float(tx), float(tz))
            self.index += 1

    def _ambush(self, amb: dict[str, Any]) -> None:
        npc = self.npc
        ox, oz = amb.get("offset", [12, 0])
        events.emit("chat", text="<rgb(1,0.5,0.3)>Dustfang Raider yells: There she is! Finish the job!")
        for k, (etype, lvl) in enumerate(amb["enemies"]):
            x = npc.x + ox + k * 2.5
            z = npc.z + oz - k * 2.0
            e = self.game.enemies.spawn(etype, int(lvl), x, z, {"temporary": True, "wander": 0})
            e.engage(npc, social=False)
            e.add_threat(npc, 50)
            self.spawned.append(e)
        self.wait = 1.0

    def _finish(self) -> None:
        qid = self.qid
        q = self.game.quests
        defs = q.defs[qid]
        for i, obj in enumerate(defs["objectives"]):
            if obj["type"] == "escort":
                q._advance(qid, i)
        npc = self.npc
        npc.targetable = False
        events.emit("chat", text=f"<rgb(0.4,1,0.4)>{npc.name} says: Redtusk... I made it. Thank you. Speak to the Overseer.")
        # Durgha stays at the post until the player turns the quest in, then returns home
        self.qid = self.obj = None
        self.npc = None
