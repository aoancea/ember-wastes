"""Class trainer window: learn abilities (unlock levels 1/2/4/6/8) and buy higher ranks."""
from __future__ import annotations

import math
from typing import Any

from ursina import color, window

from core.events import events
from settings import INTERACT_RANGE
from ui.icons import ability_icon
from ui.widgets import DIM, GOLD, TEXT, IconSlot, Panel, label, make_button


class TrainerWindow(Panel):
    def __init__(self, game) -> None:
        super().__init__(position=(-window.aspect_ratio / 2 + 0.36, 0.02), size=(0.66, 0.58), title="Trainer",
                         on_close=self.close, z=-0.55)
        self.game = game
        self.npc: Any = None
        self.rows = []
        for i in range(5):
            y = self.top - 0.1 - i * 0.088
            slot = IconSlot(self, (self.left + 0.05, y), 0.06, tooltip=lambda s: self._tooltip(s))
            name = label(self, "", (self.left + 0.09, y + 0.022), 0.92, TEXT)
            info = label(self, "", (self.left + 0.09, y - 0.004), 0.75, DIM)
            btn = make_button(self, "Learn", (-self.left - 0.09, y), (0.13, 0.04), lambda i=i: self.learn(i), text_scale=0.9)
            self.rows.append((slot, name, info, btn))
        self.gold = label(self, "", (self.left + 0.03, -self.size[1] / 2 + 0.03), 1.0, GOLD, origin=(-0.5, 0))
        self.enabled = False
        events.on("gold_changed", lambda **_: self.refresh())
        events.on("level_up", lambda **_: self.refresh())

    def _tooltip(self, s: IconSlot) -> list | None:
        if not s.data:
            return None
        aid, rank = s.data
        return self.game.abilities.tooltip(aid, rank)

    def open(self, npc: Any) -> None:
        self.npc = npc
        self.title_text.text = f"{npc.name} - {npc.title}"
        self.enabled = True
        self.refresh()

    def close(self) -> None:
        self.enabled = False
        self.npc = None

    def _next_rank(self, aid: str) -> tuple[int, dict[str, Any]] | None:
        ab = self.game.abilities
        cur = ab.known.get(aid, 0)
        ranks = ab.ranks(aid)
        if cur >= len(ranks):
            return None
        return cur + 1, ranks[cur]

    def refresh(self) -> None:
        if not self.enabled:
            return
        ab = self.game.abilities
        p = self.game.player
        for i, (slot, name, info, btn) in enumerate(self.rows):
            aid = ab.order[i]
            d = ab.defs[aid]
            nxt = self._next_rank(aid)
            slot.set_icon(ability_icon(aid), (0.7, 0.55, 0.3))
            cur = ab.known.get(aid, 0)
            if nxt is None:
                slot.data = (aid, cur)
                name.text = f"{d['name']}  (Rank {cur})"
                info.text = "Fully trained"
                info.color = color.rgb(0.4, 0.9, 0.4)
                btn.enabled = False
                continue
            rank, rd = nxt
            slot.data = (aid, rank)
            name.text = f"{d['name']}  Rank {rank}" if cur else f"{d['name']}"
            price = rd.get("price", 0)
            if p.level < rd["level"]:
                info.text = f"Requires level {rd['level']}   -   {price} gold"
                info.color = color.rgb(1, 0.4, 0.3)
                btn.enabled = False
            else:
                info.text = f"{'Upgrade' if cur else 'Learn'} for {price} gold" + ("" if p.inventory.gold >= price else "  (not enough gold)")
                info.color = GOLD if p.inventory.gold >= price else color.rgb(1, 0.4, 0.3)
                btn.enabled = True
                btn.text = "Upgrade" if cur else "Learn"
        self.gold.text = f"You have {p.inventory.gold} gold"

    def learn(self, i: int) -> None:
        ab = self.game.abilities
        p = self.game.player
        aid = ab.order[i]
        nxt = self._next_rank(aid)
        if nxt is None:
            return
        rank, rd = nxt
        if p.level < rd["level"]:
            return
        price = int(rd.get("price", 0))
        if p.inventory.gold < price:
            events.emit("message", text="You don't have enough gold.")
            events.emit("sound", name="error")
            return
        p.inventory.add_gold(-price)
        ab.learn(aid, rank)
        events.emit("sound", name="level_up" if rank == 1 else "quest_accept")
        events.emit("message", text=f"You have learned {ab.defs[aid]['name']}" + (f" (Rank {rank})" if rank > 1 else "") + ".",
                    color=(1, 0.85, 0.3))
        self.refresh()

    def update(self) -> None:
        if self.npc is None:
            return
        p = self.game.player
        if p is None or math.hypot(self.npc.x - p.x, self.npc.z - p.z) > INTERACT_RANGE + 4:
            self.close()
