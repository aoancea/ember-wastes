"""NPC dialogue window: greeting, quest offers, progress, turn-in with rewards, vendor/trainer links."""
from __future__ import annotations

import math
from typing import Any, Callable

from ursina import Button, Entity, Text, color, window

from core.events import events
from items import item as I
from settings import INTERACT_RANGE
from ui.icons import item_icon
from ui.widgets import GOLD, TEXT, IconSlot, Panel, label, make_button, rgb

WRAP = 58


class OptionButton(Button):
    def __init__(self, parent: Entity, position: tuple, width: float, on_click: Callable[[], None]) -> None:
        super().__init__(parent=parent, position=(position[0], position[1], -0.02), scale=(width, 0.036),
                         color=color.rgba(0.2, 0.15, 0.1, 0.0), highlight_color=color.rgba(0.5, 0.35, 0.15, 0.45),
                         pressed_color=color.rgba(0.6, 0.4, 0.15, 0.6), on_click=on_click)
        sy = 0.9 / 0.036
        self.label = Text(parent=self, text="", origin=(-0.5, 0), x=-0.47, z=-0.01)
        self.label.scale = (sy * 0.036 / width, sy)

    def set(self, text: str, col: Any = TEXT) -> None:
        self.label.text = text
        self.label.color = col if isinstance(col, color.Color) else rgb(col)


class DialogueWindow(Panel):
    """One window, several pages."""

    MAX_OPTIONS = 7

    def __init__(self, game) -> None:
        super().__init__(position=(-window.aspect_ratio / 2 + 0.36, 0.02), size=(0.64, 0.66), title=" ",
                         on_close=self.close, z=-0.6)
        self.game = game
        self.npc: Any = None
        self.qid: str | None = None
        self.mode = "greet"
        self.sub = label(self, "", (0, self.top - 0.06), 0.8, color.rgb(0.75, 0.75, 0.7), origin=(0, 0), use_tags=False)
        self.body = Text(parent=self, text="", origin=(-0.5, 0.5), position=(self.left + 0.03, self.top - 0.09, -0.02),
                         scale=0.88, color=TEXT)
        self.obj_title = label(self, "", (self.left + 0.03, 0), 0.95, GOLD)
        self.obj_text = Text(parent=self, text="", origin=(-0.5, 0.5), position=(self.left + 0.03, 0, -0.02), scale=0.82,
                             color=TEXT)
        self.options: list[OptionButton] = []
        for i in range(self.MAX_OPTIONS):
            self.options.append(OptionButton(self, (0, 0), self.size[0] - 0.06, lambda i=i: self._option(i)))
        self._option_actions: list[Callable[[], None]] = []
        self.reward_title = label(self, "", (self.left + 0.03, 0), 0.95, GOLD)
        self.reward_text = label(self, "", (self.left + 0.03, 0), 0.82, TEXT)
        self.reward_slots = [IconSlot(self, (self.left + 0.055 + i * 0.07, 0), 0.055,
                                      tooltip=lambda s: I.tooltip_lines(s.data, self.game.player, self._cmp(s.data)) if s.data else None)
                             for i in range(4)]
        self.btn_a = make_button(self, "Accept", (-0.12, -self.size[1] / 2 + 0.04), (0.18, 0.045), lambda: self._button("a"))
        self.btn_b = make_button(self, "Decline", (0.12, -self.size[1] / 2 + 0.04), (0.18, 0.045), lambda: self._button("b"))
        self.enabled = False

    def _cmp(self, iid: str | None) -> str | None:
        if not iid:
            return None
        it = I.get(iid)
        if it["slot"] in I.EQUIP_SLOTS:
            return self.game.player.equipment.get(it["slot"])
        return None

    # ------------------------------------------------------------------ open/close
    def open(self, npc: Any) -> None:
        self.npc = npc
        self.enabled = True
        self.title_text.text = npc.name
        self.sub.text = f"<{npc.title}>" if npc.title else ""
        self.show_greeting()
        events.emit("sound", name="open")

    def close(self) -> None:
        self.enabled = False
        self.npc = None

    def _clear(self) -> None:
        for o in self.options:
            o.enabled = False
        for s in self.reward_slots:
            s.enabled = False
        self.obj_title.text = ""
        self.obj_text.text = ""
        self.reward_title.text = ""
        self.reward_text.text = ""
        self.btn_a.enabled = False
        self.btn_b.enabled = False
        self._option_actions = []

    def _set_body(self, text: str) -> float:
        self.body.text = text
        self.body.wordwrap = WRAP
        lines = self.body.text.count("\n") + 1
        return self.top - 0.09 - lines * 0.025

    # ------------------------------------------------------------------ pages
    def show_greeting(self) -> None:
        self._clear()
        self.mode = "greet"
        npc = self.npc
        q = self.game.quests
        y = self._set_body(npc.d.get("greeting", "")) - 0.03
        entries: list[tuple[str, Any, Callable[[], None]]] = []
        for qid in q.turn_ins_for(npc.id):
            col = (1, 0.85, 0.1) if q.can_turn_in(qid) else (0.7, 0.7, 0.7)
            entries.append((f"?  {q.title(qid)}", col, lambda qid=qid: self.show_turn_in(qid)))
        for qid in q.offers_for(npc.id):
            entries.append((f"!  {q.title(qid)}", (1, 0.85, 0.1), lambda qid=qid: self.show_offer(qid)))
        for qid, st in q.active.items():
            if st["state"] == "failed" and q.defs[qid]["giver"] == npc.id:
                entries.append((f"!  {q.title(qid)} (retry)", (1, 0.6, 0.3), lambda qid=qid: self._retry(qid)))
        if npc.vendor_items:
            entries.append(("$  Let me browse your goods.", (0.9, 0.9, 0.9), self._open_vendor))
        if npc.trainer:
            if npc.trainer == self.game.player.cls:
                entries.append(("*  Train me.", (0.9, 0.9, 0.9), self._open_trainer))
            else:
                entries.append((f"*  (Only trains {npc.trainer.title()}s)", (0.55, 0.55, 0.55), lambda: None))
        entries.append(("Goodbye.", (0.8, 0.8, 0.8), self.close))
        for i, (txt, col, fn) in enumerate(entries[: self.MAX_OPTIONS]):
            o = self.options[i]
            o.enabled = True
            o.position = (0, y - i * 0.042, -0.02)
            o.set(txt, col)
            self._option_actions.append(fn)

    def _rewards(self, qid: str, y: float) -> None:
        q = self.game.quests
        rw = q.defs[qid].get("rewards", {})
        self.reward_title.text = "Rewards"
        self.reward_title.y = y
        parts = []
        if rw.get("xp"):
            parts.append(f"{rw['xp']} XP")
        if rw.get("gold"):
            parts.append(f"{rw['gold']} gold")
        self.reward_text.text = "    ".join(parts)
        self.reward_text.y = y - 0.03
        items = q.reward_items(qid)
        uniq: list[str] = []
        for iid in items:
            if iid not in uniq:
                uniq.append(iid)
        for i, s in enumerate(self.reward_slots):
            if i < len(uniq):
                s.enabled = True
                s.data = uniq[i]
                s.y = y - 0.09
                s.set_icon(item_icon(uniq[i]), I.color_of(uniq[i]), items.count(uniq[i]))
            else:
                s.enabled = False

    def show_offer(self, qid: str) -> None:
        self._clear()
        self.mode = "offer"
        self.qid = qid
        d = self.game.quests.defs[qid]
        y = self._set_body(d["text"]) - 0.02
        self.obj_title.text = "Objectives"
        self.obj_title.y = y
        self.obj_text.text = d.get("objectives_text", "")
        self.obj_text.wordwrap = WRAP
        self.obj_text.y = y - 0.03
        self._rewards(qid, y - 0.1)
        self.btn_a.enabled = True
        self.btn_a.text = "Accept"
        self.btn_b.enabled = True
        self.btn_b.text = "Decline"

    def show_turn_in(self, qid: str) -> None:
        self._clear()
        q = self.game.quests
        d = q.defs[qid]
        self.qid = qid
        if q.can_turn_in(qid):
            self.mode = "complete"
            y = self._set_body(d.get("complete_text", "Well done.")) - 0.03
            self._rewards(qid, y)
            self.btn_a.enabled = True
            self.btn_a.text = "Complete"
            self.btn_b.enabled = True
            self.btn_b.text = "Back"
        else:
            self.mode = "progress"
            y = self._set_body(d.get("progress_text", "Is it done?")) - 0.03
            lines = q.objective_lines(qid)
            self.obj_title.text = "Progress"
            self.obj_title.y = y
            self.obj_text.text = "\n".join(("[x] " if done else "[ ] ") + t for t, done in lines)
            self.obj_text.y = y - 0.03
            self.btn_b.enabled = True
            self.btn_b.text = "Back"

    def _retry(self, qid: str) -> None:
        self.game.quests.retry(qid)
        self.close()

    def _open_vendor(self) -> None:
        npc = self.npc
        self.close()
        self.game.hud.open_vendor(npc)

    def _open_trainer(self) -> None:
        npc = self.npc
        self.close()
        self.game.hud.open_trainer(npc)
        q = self.game.quests
        if "r0" in q.active:
            q.turn_in("r0")

    # ------------------------------------------------------------------ actions
    def _option(self, i: int) -> None:
        if i < len(self._option_actions):
            events.emit("sound", name="click")
            self._option_actions[i]()

    def _button(self, which: str) -> None:
        q = self.game.quests
        events.emit("sound", name="click")
        if self.mode == "offer":
            if which == "a":
                q.accept(self.qid)
                # immediately complete talk-quests whose turn-in is this same npc
                self.show_greeting()
                if not q.offers_for(self.npc.id) and not q.turn_ins_for(self.npc.id):
                    self.close()
            else:
                self.show_greeting()
        elif self.mode == "complete":
            if which == "a":
                if q.turn_in(self.qid):
                    npc = self.npc
                    self.show_greeting()
                    nxt = q.offers_for(npc.id)
                    if nxt:
                        self.show_offer(nxt[0])
            else:
                self.show_greeting()
        else:
            self.show_greeting()

    def update(self) -> None:
        if self.npc is None:
            return
        p = self.game.player
        if p is None or math.hypot(self.npc.x - p.x, self.npc.z - p.z) > INTERACT_RANGE + 4 or p.dead:
            self.close()
