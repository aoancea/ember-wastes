"""Loot window for defeated enemies."""
from __future__ import annotations

import math
from typing import Any

from ursina import window

from core.events import events
from items import item as I
from settings import LOOT_RANGE
from ui.icons import item_icon, simple_icon
from ui.widgets import GOLD, IconSlot, Panel, label, make_button, rgb


class LootWindow(Panel):
    """Shows a corpse's gold and items; click to take, or Take All."""

    ROWS = 6

    def __init__(self, game) -> None:
        super().__init__(position=(-window.aspect_ratio / 2 + 0.3, 0.05), size=(0.3, 0.46), title="Loot",
                         on_close=self.close, z=-0.5)
        self.game = game
        self.enemy: Any = None
        self.rows: list[tuple[IconSlot, Any]] = []
        for i in range(self.ROWS):
            y = self.top - 0.08 - i * 0.058
            slot = IconSlot(self, (self.left + 0.045, y), 0.048, on_click=lambda s, i=i: self.take(i),
                            tooltip=lambda s: I.tooltip_lines(s.data["id"], self.game.player) if s.data and s.data.get("id") else None)
            name = label(self, "", (self.left + 0.078, y + 0.012), 0.85)
            self.rows.append((slot, name))
        self.take_all_btn = make_button(self, "Take All", (0, -self.size[1] / 2 + 0.035), (0.14, 0.04), self.take_all)
        self.enabled = False

    def open(self, enemy: Any) -> None:
        self.enemy = enemy
        self.enabled = True
        self.refresh()
        events.emit("sound", name="loot")

    def close(self) -> None:
        self.enabled = False
        self.enemy = None

    def _entries(self) -> list[dict[str, Any]]:
        loot = self.enemy.loot if self.enemy is not None and self.enemy.loot else None
        if not loot:
            return []
        out: list[dict[str, Any]] = []
        if loot.get("gold", 0) > 0:
            out.append({"gold": loot["gold"]})
        out.extend(loot.get("items", []))
        return out

    def refresh(self) -> None:
        entries = self._entries()
        if not entries:
            self.close()
            return
        for i, (slot, name) in enumerate(self.rows):
            if i < len(entries):
                e = entries[i]
                slot.enabled = True
                name.enabled = True
                slot.data = e
                if "gold" in e:
                    slot.set_icon(simple_icon("coin", (0.35, 0.28, 0.1)), (0.9, 0.75, 0.3))
                    name.text = f"{e['gold']} Gold"
                    name.color = GOLD
                else:
                    iid = e["id"]
                    slot.set_icon(item_icon(iid), I.color_of(iid), e.get("count", 1))
                    name.text = I.name(iid)
                    name.color = rgb(I.color_of(iid))
            else:
                slot.enabled = False
                name.enabled = False
                slot.data = None

    def take(self, index: int) -> None:
        entries = self._entries()
        if index >= len(entries) or self.enemy is None:
            return
        e = entries[index]
        loot = self.enemy.loot
        p = self.game.player
        if "gold" in e:
            p.inventory.add_gold(loot["gold"])
            loot["gold"] = 0
            events.emit("sound", name="coin")
        else:
            if p.inventory.add(e["id"], e.get("count", 1)):
                loot["items"].remove(e)
                events.emit("sound", name="loot")
                events.emit("item_looted", item_id=e["id"])
            else:
                return
        self.refresh()

    def take_all(self) -> None:
        for _ in range(12):
            if not self.enabled or not self._entries():
                break
            before = len(self._entries())
            self.take(0)
            if self.enabled and len(self._entries()) == before:
                break

    def update(self) -> None:
        if self.enemy is None:
            return
        p = self.game.player
        if p is None or math.hypot(self.enemy.x - p.x, self.enemy.z - p.z) > LOOT_RANGE + 3 or not self.enemy.dead:
            self.close()
