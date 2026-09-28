"""Bags window (B): 24 slots, gold, right-click to use/equip (or sell at a vendor)."""
from __future__ import annotations

from typing import Any

from ursina import color, window

from core.events import events
from items import item as I
from ui.icons import item_icon
from ui.widgets import GOLD, IconSlot, Panel, label


class BagsWindow(Panel):
    COLS = 6
    ROWS = 4
    SLOT = 0.062

    def __init__(self, game) -> None:
        w = self.COLS * (self.SLOT + 0.008) + 0.03
        h = self.ROWS * (self.SLOT + 0.008) + 0.11
        super().__init__(position=(window.aspect_ratio / 2 - w / 2 - 0.02, -0.12), size=(w, h), title="Bags",
                         on_close=self.close, z=-0.4)
        self.game = game
        self.slots: list[IconSlot] = []
        for r in range(self.ROWS):
            for c in range(self.COLS):
                i = r * self.COLS + c
                x = self.left + 0.015 + self.SLOT / 2 + c * (self.SLOT + 0.008)
                y = self.top - 0.06 - self.SLOT / 2 - r * (self.SLOT + 0.008)
                s = IconSlot(self, (x, y), self.SLOT, on_right_click=lambda s, i=i: self._use(i),
                             on_click=lambda s, i=i: self._click(i), tooltip=lambda s, i=i: self._tooltip(i))
                self.slots.append(s)
        self.gold_text = label(self, "", (self.left + 0.02, -self.size[1] / 2 + 0.03), 1.0, GOLD, origin=(-0.5, 0))
        self.hint = label(self, "Right-click: use / equip", (-self.left - 0.02, -self.size[1] / 2 + 0.03), 0.7,
                          color.rgb(0.6, 0.6, 0.55), origin=(0.5, 0))
        self.enabled = False
        events.on("inventory_changed", self.refresh)
        events.on("gold_changed", lambda **_: self.refresh())
        events.on("vendor_opened", lambda **_: self._hint())
        events.on("vendor_closed", lambda **_: self._hint())

    def _hint(self) -> None:
        v = getattr(self.game.hud, "vendor", None)
        self.hint.text = "Right-click: sell" if (v is not None and v.enabled) else "Right-click: use / equip"

    def open(self) -> None:
        self.enabled = True
        self.refresh()
        self._hint()
        events.emit("sound", name="open")

    def close(self) -> None:
        self.enabled = False

    def toggle(self) -> None:
        self.close() if self.enabled else self.open()

    def refresh(self, **_: Any) -> None:
        p = self.game.player
        if p is None or not self.enabled:
            return
        inv = p.inventory
        for i, s in enumerate(self.slots):
            e = inv.slots[i] if i < len(inv.slots) else None
            s.data = e
            if e:
                s.set_icon(item_icon(e["id"]), I.color_of(e["id"]), e["count"])
            else:
                s.set_icon(None, None)
        self.gold_text.text = f"{inv.gold} gold"

    def _tooltip(self, i: int) -> list | None:
        p = self.game.player
        e = p.inventory.slots[i]
        if not e:
            return None
        iid = e["id"]
        it = I.get(iid)
        cmp = p.equipment.get(it["slot"]) if it["slot"] in I.EQUIP_SLOTS else None
        lines = I.tooltip_lines(iid, p, cmp if cmp != iid else None)
        v = getattr(self.game.hud, "vendor", None)
        if v is not None and v.enabled:
            sp = I.sell_price(iid)
            lines.append((f"Right-click to sell for {sp * e['count']} gold" if sp else "Can't be sold", (1, 0.85, 0.3)))
        return lines

    def _click(self, i: int) -> None:
        pass

    def _use(self, i: int) -> None:
        g = self.game
        v = getattr(g.hud, "vendor", None)
        if v is not None and v.enabled:
            v.sell_from_bag(i)
        else:
            g.player.use_bag_item(i)
        self.refresh()
