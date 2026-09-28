"""Bags (slot-based inventory with stacking), gold and equipped gear."""
from __future__ import annotations

from typing import Any

from core.events import events
from items import item as I

BAG_SIZE = 24


class Inventory:
    """A fixed number of bag slots; each slot holds {'id', 'count'} or None."""

    def __init__(self, size: int = BAG_SIZE) -> None:
        self.slots: list[dict[str, Any] | None] = [None] * size
        self.gold = 0

    def add(self, item_id: str, count: int = 1, silent: bool = False) -> int:
        """Add items, stacking where possible. Returns how many were added."""
        if not I.exists(item_id) or count <= 0:
            return 0
        stack = I.stack_size(item_id)
        left = count
        for s in self.slots:
            if left <= 0:
                break
            if s and s["id"] == item_id and s["count"] < stack:
                n = min(stack - s["count"], left)
                s["count"] += n
                left -= n
        for i, s in enumerate(self.slots):
            if left <= 0:
                break
            if s is None:
                n = min(stack, left)
                self.slots[i] = {"id": item_id, "count": n}
                left -= n
        added = count - left
        if added:
            events.emit("inventory_changed")
            if not silent:
                events.emit("item_received", item_id=item_id, count=added)
        if left > 0:
            events.emit("message", text="Your bags are full.", color=(1, 0.3, 0.3))
        return added

    def can_add(self, item_id: str, count: int = 1) -> bool:
        stack = I.stack_size(item_id)
        room = 0
        for s in self.slots:
            if s is None:
                room += stack
            elif s["id"] == item_id:
                room += stack - s["count"]
        return room >= count

    def count(self, item_id: str) -> int:
        return sum(s["count"] for s in self.slots if s and s["id"] == item_id)

    def remove(self, item_id: str, count: int = 1) -> bool:
        if self.count(item_id) < count:
            return False
        left = count
        for i in range(len(self.slots) - 1, -1, -1):
            s = self.slots[i]
            if s and s["id"] == item_id and left > 0:
                n = min(s["count"], left)
                s["count"] -= n
                left -= n
                if s["count"] <= 0:
                    self.slots[i] = None
        events.emit("inventory_changed")
        return True

    def take_slot(self, index: int) -> dict[str, Any] | None:
        s = self.slots[index]
        self.slots[index] = None
        if s:
            events.emit("inventory_changed")
        return s

    def put_slot(self, index: int, entry: dict[str, Any] | None) -> None:
        self.slots[index] = entry
        events.emit("inventory_changed")

    def free_slots(self) -> int:
        return sum(1 for s in self.slots if s is None)

    def add_gold(self, amount: int) -> None:
        if amount:
            self.gold = max(0, self.gold + amount)
            events.emit("gold_changed", gold=self.gold, delta=amount)

    def to_list(self) -> list[Any]:
        return [dict(s) if s else None for s in self.slots]

    def load_list(self, lst: list[Any]) -> None:
        self.slots = [None] * max(BAG_SIZE, len(lst))
        for i, s in enumerate(lst):
            if s and I.exists(s["id"]):
                self.slots[i] = {"id": s["id"], "count": int(s.get("count", 1))}
        events.emit("inventory_changed")


class Equipment:
    """Item ids worn in each equipment slot."""

    def __init__(self) -> None:
        self.slots: dict[str, str | None] = {s: None for s in I.EQUIP_SLOTS}

    def get(self, slot: str) -> str | None:
        return self.slots.get(slot)

    def set(self, slot: str, item_id: str | None) -> str | None:
        old = self.slots.get(slot)
        self.slots[slot] = item_id
        events.emit("equipment_changed", slot=slot)
        return old

    def total_stats(self) -> dict[str, float]:
        total: dict[str, float] = {}
        for iid in self.slots.values():
            if iid:
                for k, v in I.stats(iid).items():
                    total[k] = total.get(k, 0.0) + float(v)
        return total

    def weapon(self) -> dict[str, Any] | None:
        iid = self.slots.get("weapon")
        return I.get(iid) if iid else None
