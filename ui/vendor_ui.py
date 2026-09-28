"""Vendor window: buy with left-click, sell from bags with right-click."""
from __future__ import annotations

import math
from typing import Any

from ursina import color, window

from core.events import events
from items import item as I
from settings import INTERACT_RANGE
from ui.icons import item_icon
from ui.widgets import DIM, GOLD, IconSlot, Panel, label


class VendorWindow(Panel):
    ROWS = 6

    def __init__(self, game) -> None:
        super().__init__(position=(-window.aspect_ratio / 2 + 0.36, 0.02), size=(0.64, 0.56), title="Vendor",
                         on_close=self.close, z=-0.55)
        self.game = game
        self.npc: Any = None
        self.cells: list[tuple[IconSlot, Any, Any]] = []
        for i in range(self.ROWS * 2):
            col, row = i // self.ROWS, i % self.ROWS
            x = self.left + 0.045 + col * 0.31
            y = self.top - 0.09 - row * 0.068
            slot = IconSlot(self, (x, y), 0.055, on_click=lambda s, i=i: self.buy(i),
                            tooltip=lambda s: self._tooltip(s))
            name = label(self, "", (x + 0.035, y + 0.016), 0.78)
            price = label(self, "", (x + 0.035, y - 0.006), 0.72, GOLD)
            self.cells.append((slot, name, price))
        self.gold = label(self, "", (self.left + 0.03, -self.size[1] / 2 + 0.03), 1.0, GOLD, origin=(-0.5, 0))
        self.hint = label(self, "Left-click to buy  |  right-click bag items to sell",
                          (0, -self.size[1] / 2 + 0.065), 0.72, DIM, origin=(0, 0))
        self.enabled = False
        events.on("gold_changed", lambda **_: self._gold())

    def _tooltip(self, s: IconSlot) -> list | None:
        if not s.data:
            return None
        p = self.game.player
        it = I.get(s.data)
        cmp = p.equipment.get(it["slot"]) if it["slot"] in I.EQUIP_SLOTS else None
        lines = I.tooltip_lines(s.data, p, cmp)
        lines = [l for l in lines if not l[0].startswith("Sells for")]
        lines.append((f"Price: {I.buy_price(s.data)} gold", (1, 0.85, 0.3)))
        return lines

    def open(self, npc: Any) -> None:
        self.npc = npc
        self.title_text.text = f"{npc.name} - Goods"
        self.enabled = True
        for i, (slot, name, price) in enumerate(self.cells):
            if i < len(npc.vendor_items):
                iid = npc.vendor_items[i]
                slot.enabled = name.enabled = price.enabled = True
                slot.data = iid
                slot.set_icon(item_icon(iid), I.color_of(iid))
                name.text = I.name(iid)
                name.color = color.rgb(*I.color_of(iid))
                price.text = f"{I.buy_price(iid)} gold"
            else:
                slot.enabled = name.enabled = price.enabled = False
                slot.data = None
        self._gold()
        events.emit("vendor_opened")
        self.game.hud.bags.open()

    def close(self) -> None:
        if self.enabled:
            self.enabled = False
            self.npc = None
            events.emit("vendor_closed")

    def _gold(self) -> None:
        if self.game.player:
            self.gold.text = f"You have {self.game.player.inventory.gold} gold"

    def buy(self, i: int) -> None:
        slot = self.cells[i][0]
        iid = slot.data
        if not iid:
            return
        p = self.game.player
        price = I.buy_price(iid)
        if p.inventory.gold < price:
            events.emit("message", text="You don't have enough gold.")
            events.emit("sound", name="error")
            return
        if not p.inventory.can_add(iid, 1):
            events.emit("message", text="Your bags are full.")
            return
        p.inventory.add_gold(-price)
        p.inventory.add(iid, 1)
        events.emit("sound", name="coin")

    def sell_from_bag(self, index: int) -> None:
        p = self.game.player
        e = p.inventory.slots[index]
        if not e:
            return
        price = I.sell_price(e["id"])
        if price <= 0:
            events.emit("message", text="The vendor has no interest in that.")
            return
        p.inventory.take_slot(index)
        p.inventory.add_gold(price * e["count"])
        events.emit("sound", name="coin")

    def update(self) -> None:
        if self.npc is None:
            return
        p = self.game.player
        if p is None or math.hypot(self.npc.x - p.x, self.npc.z - p.z) > INTERACT_RANGE + 4:
            self.close()
