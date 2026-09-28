"""Quest state machine: availability, objectives (kill/collect/talk/deliver/explore/escort), rewards."""
from __future__ import annotations

import math
import random
from typing import Any

from core import data
from core.events import events
from items import item as I

YELLOW = (1.0, 0.85, 0.1)
GREY = (0.65, 0.65, 0.65)


class QuestManager:
    """Tracks the player's quests and reacts to game events to advance objectives."""

    def __init__(self, game) -> None:
        self.game = game
        self.defs: dict[str, Any] = data.quests()["quests"]
        self.active: dict[str, dict[str, Any]] = {}     # qid -> {"progress": [..], "state": "active"|"complete"|"failed"}
        self.done: set[str] = set()
        self._explore_t = 0.0
        events.on("unit_died", self._on_unit_died)
        events.on("inventory_changed", self._on_inventory)
        events.on("npc_talked", self._on_talk)

    # ------------------------------------------------------------------ queries
    def title(self, qid: str) -> str:
        return self.defs[qid]["title"]

    def is_available(self, qid: str) -> bool:
        q = self.defs[qid]
        p = self.game.player
        if qid in self.done or qid in self.active or p is None:
            return False
        if q.get("race") and q["race"] != p.race:
            return False
        if q.get("class") and q["class"] != p.cls:
            return False
        if any(r not in self.done for r in q.get("requires", [])):
            return False
        if q.get("requires_any") and not any(r in self.done for r in q["requires_any"]):
            return False
        if p.level < q.get("min_level", q.get("level", 1)) - 2:
            return False
        return True

    def turn_in_npc(self, qid: str) -> str:
        t = self.defs[qid]["turn_in"]
        if t == "@trainer":
            return {"warrior": "warmaster_drogan", "hunter": "huntmaster_sika", "shaman": "seer_umbala"}[self.game.player.cls]
        return t

    def offers_for(self, npc_id: str) -> list[str]:
        return [qid for qid, q in self.defs.items() if q["giver"] == npc_id and self.is_available(qid)]

    def turn_ins_for(self, npc_id: str) -> list[str]:
        return [qid for qid in self.active if self.turn_in_npc(qid) == npc_id]

    def is_complete(self, qid: str) -> bool:
        st = self.active.get(qid)
        return st is not None and st["state"] == "complete"

    def marker_for(self, npc) -> tuple[str, tuple] | str:
        for qid in self.turn_ins_for(npc.id):
            if self.is_complete(qid):
                return ("?", YELLOW)
        if self.offers_for(npc.id):
            return ("!", YELLOW)
        if self.turn_ins_for(npc.id):
            return ("?", GREY)
        return ""

    def objective_lines(self, qid: str) -> list[tuple[str, bool]]:
        """(text, done) for each objective, for the log and tracker."""
        q = self.defs[qid]
        st = self.active.get(qid)
        out: list[tuple[str, bool]] = []
        if not q["objectives"]:
            npc = data.npcs().get(self.turn_in_npc(qid), {})
            out.append((f"Speak with {npc.get('name', '?')}", False))
            return out
        for i, obj in enumerate(q["objectives"]):
            cur = self.progress(qid, i)
            need = obj.get("count", 1)
            label = obj.get("label") or self._default_label(obj)
            if obj["type"] in ("kill", "collect"):
                out.append((f"{label}: {min(cur, need)}/{need}", cur >= need))
            else:
                out.append((label, cur >= need))
        if st and st["state"] == "failed":
            out.append(("Failed - speak to the quest giver to retry", False))
        return out

    def _default_label(self, obj: dict[str, Any]) -> str:
        if obj["type"] == "collect":
            return I.name(obj["item"])
        if obj["type"] == "explore":
            return "Explore the area"
        return obj["type"].title()

    def progress(self, qid: str, i: int) -> int:
        st = self.active.get(qid)
        if st is None:
            return 0
        obj = self.defs[qid]["objectives"][i]
        if obj["type"] == "collect":
            return self.game.player.inventory.count(obj["item"])
        return st["progress"][i]

    # ------------------------------------------------------------------ actions
    def accept(self, qid: str) -> None:
        q = self.defs[qid]
        self.active[qid] = {"progress": [0] * len(q["objectives"]), "state": "active"}
        for iid in q.get("start_items", []):
            self.game.player.inventory.add(iid, 1)
        events.emit("sound", name="quest_accept")
        events.emit("quest_accepted", qid=qid)
        events.emit("chat", text=f"<rgb(1,0.85,0.3)>Quest accepted: {q['title']}")
        for obj in q["objectives"]:
            if obj["type"] == "escort":
                self.game.escort.start(qid, obj)
        self._check_complete(qid)

    def abandon(self, qid: str) -> None:
        if qid not in self.active:
            return
        q = self.defs[qid]
        del self.active[qid]
        for obj in q["objectives"]:
            if obj["type"] == "collect" and I.get(obj["item"])["slot"] == "quest":
                self.game.player.inventory.remove(obj["item"], self.game.player.inventory.count(obj["item"]))
            if obj["type"] == "escort":
                self.game.escort.stop()
        for iid in q.get("start_items", []):
            self.game.player.inventory.remove(iid, 1)
        events.emit("quest_changed", qid=qid)
        events.emit("chat", text=f"<rgb(1,0.5,0.4)>Quest abandoned: {q['title']}")

    def can_turn_in(self, qid: str) -> bool:
        st = self.active.get(qid)
        if st is None:
            return False
        if not self.defs[qid]["objectives"]:
            return True
        return st["state"] == "complete"

    def reward_items(self, qid: str) -> list[str]:
        r = self.defs[qid].get("rewards", {}).get("items", {})
        cls = self.game.player.cls
        out: list[str] = []
        for key in ("all", cls):
            v = r.get(key)
            if isinstance(v, str):
                out.append(v)
            elif isinstance(v, list):
                out.extend(v)
        return out

    def turn_in(self, qid: str) -> bool:
        if not self.can_turn_in(qid):
            return False
        q = self.defs[qid]
        p = self.game.player
        items = self.reward_items(qid)
        if p.inventory.free_slots() < len(set(items)):
            events.emit("message", text="Your bags are too full to accept the reward.")
            return False
        for obj in q["objectives"]:
            if obj["type"] == "collect" and obj["item"] not in q.get("keep_items", []):
                p.inventory.remove(obj["item"], obj.get("count", 1))
        for iid in q.get("remove_items", []):
            p.inventory.remove(iid, p.inventory.count(iid))
        del self.active[qid]
        self.done.add(qid)
        rw = q.get("rewards", {})
        if rw.get("gold"):
            p.inventory.add_gold(int(rw["gold"]))
        for iid in items:
            p.inventory.add(iid, 1)
        events.emit("sound", name="quest_complete")
        events.emit("chat", text=f"<rgb(1,0.85,0.3)>Quest completed: {q['title']}")
        if rw.get("xp"):
            p.gain_xp(int(rw["xp"]), q["title"])
        events.emit("quest_turned_in", qid=qid)
        events.emit("quest_changed", qid=qid)
        if q.get("final"):
            events.emit("game_won")
        return True

    # ------------------------------------------------------------------ progress
    def _advance(self, qid: str, i: int, amount: int = 1) -> None:
        st = self.active[qid]
        obj = self.defs[qid]["objectives"][i]
        need = obj.get("count", 1)
        if st["progress"][i] >= need:
            return
        st["progress"][i] = min(need, st["progress"][i] + amount)
        label = obj.get("label") or self._default_label(obj)
        if obj["type"] == "kill":
            events.emit("message", text=f"{label}: {st['progress'][i]}/{need}", color=(1, 0.85, 0.3))
        events.emit("quest_changed", qid=qid)
        self._check_complete(qid)

    def _check_complete(self, qid: str) -> None:
        st = self.active.get(qid)
        if st is None or st["state"] == "failed":
            return
        q = self.defs[qid]
        if not q["objectives"]:
            return
        done = all(self.progress(qid, i) >= obj.get("count", 1) for i, obj in enumerate(q["objectives"]))
        was = st["state"]
        st["state"] = "complete" if done else "active"
        if st["state"] != was:
            if done:
                events.emit("message", text=f"{q['title']} completed!", color=(1, 0.85, 0.3))
                events.emit("sound", name="quest_accept")
            events.emit("quest_changed", qid=qid)

    def fail(self, qid: str, reason: str = "") -> None:
        st = self.active.get(qid)
        if st is None:
            return
        st["state"] = "failed"
        events.emit("message", text=f"{self.defs[qid]['title']} failed. {reason}".strip(), color=(1, 0.3, 0.25))
        events.emit("quest_changed", qid=qid)

    def retry(self, qid: str) -> None:
        q = self.defs[qid]
        self.active[qid] = {"progress": [0] * len(q["objectives"]), "state": "active"}
        for obj in q["objectives"]:
            if obj["type"] == "escort":
                self.game.escort.start(qid, obj)
        events.emit("quest_changed", qid=qid)

    def _on_unit_died(self, unit: Any, killer: Any = None, **_: Any) -> None:
        p = self.game.player
        if p is None or getattr(unit, "faction", "") != "hostile":
            return
        credited = killer is p or getattr(killer, "owner", None) is p or getattr(unit, "tagged_by_player", False)
        if not credited:
            return
        for qid in list(self.active):
            st = self.active[qid]
            if st["state"] == "failed":
                continue
            for i, obj in enumerate(self.defs[qid]["objectives"]):
                if obj["type"] == "kill" and unit.type_id in obj["enemy"]:
                    self._advance(qid, i)

    def _on_inventory(self, **_: Any) -> None:
        for qid in list(self.active):
            if any(o["type"] == "collect" for o in self.defs[qid]["objectives"]):
                self._check_complete(qid)
                events.emit("quest_changed", qid=qid)

    def _on_talk(self, npc: Any, **_: Any) -> None:
        pass

    def quest_drops(self, enemy: Any) -> list[str]:
        """Quest items that this enemy should drop right now (only while needed)."""
        out = []
        p = self.game.player
        for qid, st in self.active.items():
            if st["state"] == "failed":
                continue
            for obj in self.defs[qid]["objectives"]:
                if obj["type"] == "collect" and enemy.type_id in obj.get("drop_from", []):
                    if p.inventory.count(obj["item"]) < obj.get("count", 1) and random.random() < obj.get("chance", 0.5):
                        out.append(obj["item"])
        return out

    def needs_item(self, item_id: str) -> bool:
        p = self.game.player
        for qid, st in self.active.items():
            for obj in self.defs[qid]["objectives"]:
                if obj["type"] == "collect" and obj["item"] == item_id and p.inventory.count(item_id) < obj.get("count", 1):
                    return True
        return False

    def update(self, dt: float) -> None:
        self._explore_t -= dt
        if self._explore_t > 0:
            return
        self._explore_t = 0.5
        p = self.game.player
        if p is None or p.dead:
            return
        zones = self.game.world.zones
        for qid in list(self.active):
            st = self.active[qid]
            for i, obj in enumerate(self.defs[qid]["objectives"]):
                if obj["type"] == "explore" and st["progress"][i] < 1:
                    lm = next((l for l in zones.landmarks if l["id"] == obj["landmark"]), None)
                    if lm and math.hypot(p.x - lm["pos"][0], p.z - lm["pos"][1]) <= lm["radius"]:
                        events.emit("announce", title=f"Discovered: {lm['name']}", subtitle=self.defs[qid]["title"])
                        self._advance(qid, i)

    # ------------------------------------------------------------------ save
    def to_dict(self) -> dict[str, Any]:
        return {"active": self.active, "done": sorted(self.done)}

    def load_dict(self, d: dict[str, Any]) -> None:
        self.active = {k: v for k, v in d.get("active", {}).items() if k in self.defs}
        self.done = {q for q in d.get("done", []) if q in self.defs}
        for qid, st in self.active.items():
            for obj in self.defs[qid]["objectives"]:
                if obj["type"] == "escort" and st["state"] == "active":
                    st["state"] = "failed"
        events.emit("quest_changed", qid="")
