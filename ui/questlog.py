"""Quest log (L) and the on-screen quest tracker."""
from __future__ import annotations


from ursina import Button, Entity, Text, camera, color, window

from core.events import events
from ui.widgets import DIM, GOLD, TEXT, Panel, label, make_button

WRAP = 44


class QuestLog(Panel):
    def __init__(self, game) -> None:
        super().__init__(position=(0, 0.03), size=(0.9, 0.62), title="Quest Log", on_close=self.close, z=-0.5)
        self.game = game
        self.selected: str | None = None
        self.list_bg = Entity(parent=self, model="quad", origin=(-0.5, 0.5), position=(self.left + 0.015, self.top - 0.05, -0.001),
                              scale=(0.33, self.size[1] - 0.11), color=color.rgba(0, 0, 0, 0.25))
        self.buttons: list[Button] = []
        for i in range(12):
            b = Button(parent=self, position=(self.left + 0.18, self.top - 0.075 - i * 0.038, -0.02), scale=(0.32, 0.034),
                       color=color.rgba(0, 0, 0, 0), highlight_color=color.rgba(0.5, 0.35, 0.15, 0.45),
                       on_click=lambda i=i: self._select(i))
            b.lbl = Text(parent=b, text="", origin=(-0.5, 0), x=-0.47, z=-0.01)
            b.lbl.scale = (0.85 * 0.034 / 0.32 / 0.034, 0.85 / 0.034)
            b.lbl.scale_x = b.lbl.scale_y * 0.034 / 0.32
            self.buttons.append(b)
        rx = self.left + 0.37
        self.d_title = label(self, "", (rx, self.top - 0.07), 1.15, GOLD)
        self.d_obj = Text(parent=self, text="", origin=(-0.5, 0.5), position=(rx, self.top - 0.11, -0.02), scale=0.85, color=TEXT)
        self.d_desc_title = label(self, "", (rx, 0), 0.95, GOLD)
        self.d_desc = Text(parent=self, text="", origin=(-0.5, 0.5), position=(rx, 0, -0.02), scale=0.78, color=color.rgb(0.85, 0.82, 0.75))
        self.abandon = make_button(self, "Abandon", (self.size[0] / 2 - 0.1, -self.size[1] / 2 + 0.04), (0.14, 0.04), self._abandon)
        self.empty = label(self, "", (rx, self.top - 0.1), 0.9, DIM)
        self._ids: list[str] = []
        self.enabled = False
        events.on("quest_changed", lambda **_: self.refresh())

    def open(self) -> None:
        self.enabled = True
        self.refresh()
        events.emit("sound", name="open")

    def close(self) -> None:
        self.enabled = False

    def toggle(self) -> None:
        self.close() if self.enabled else self.open()

    def _select(self, i: int) -> None:
        if i < len(self._ids):
            self.selected = self._ids[i]
            self.refresh()

    def _abandon(self) -> None:
        if self.selected:
            self.game.quests.abandon(self.selected)
            self.selected = None
            self.refresh()

    def refresh(self) -> None:
        if not self.enabled:
            return
        q = self.game.quests
        self._ids = list(q.active.keys())
        if self.selected not in self._ids:
            self.selected = self._ids[0] if self._ids else None
        for i, b in enumerate(self.buttons):
            if i < len(self._ids):
                qid = self._ids[i]
                st = q.active[qid]
                b.enabled = True
                tag = " (Complete)" if st["state"] == "complete" else (" (Failed)" if st["state"] == "failed" else "")
                lvl = q.defs[qid].get("level", 1)
                b.lbl.text = f"[{lvl}] {q.title(qid)}{tag}"
                b.lbl.color = GOLD if qid == self.selected else (color.rgb(0.4, 1, 0.4) if st["state"] == "complete" else TEXT)
            else:
                b.enabled = False
        if not self.selected:
            self.d_title.text = ""
            self.d_obj.text = ""
            self.d_desc.text = ""
            self.d_desc_title.text = ""
            self.empty.text = "No active quests. Look for NPCs with a yellow !"
            self.abandon.enabled = False
            return
        self.empty.text = ""
        self.abandon.enabled = True
        qid = self.selected
        d = q.defs[qid]
        self.d_title.text = d["title"]
        obj = d.get("objectives_text", "")
        prog = "\n".join(("  [x] " if done else "  [ ] ") + t for t, done in q.objective_lines(qid))
        self.d_obj.text = obj
        self.d_obj.wordwrap = WRAP
        self.d_obj.text = self.d_obj.text.rstrip() + "\n\n" + prog
        lines = self.d_obj.text.count("\n") + 1
        y = self.top - 0.11 - lines * 0.024 - 0.03
        self.d_desc_title.text = "Description"
        self.d_desc_title.y = y
        self.d_desc.text = d["text"]
        self.d_desc.wordwrap = WRAP + 8
        self.d_desc.y = y - 0.03


class QuestTracker(Entity):
    """Compact list of active quests and their progress, on the right side of the screen."""

    def __init__(self, game) -> None:
        super().__init__(parent=camera.ui, position=(window.aspect_ratio / 2 - 0.3, 0.12, -0.5))
        self.game = game
        self.bg = Entity(parent=self, model="quad", origin=(-0.5, 0.5), position=(-0.008, 0.008, 0.01), scale=(0.3, 0.1),
                         color=color.rgba(0, 0, 0, 0.35), enabled=False)
        self.text = Text(parent=self, text="", origin=(-0.5, 0.5), scale=0.78, color=TEXT)
        events.on("quest_changed", lambda **_: self.refresh())
        events.on("quest_accepted", lambda **_: self.refresh())

    def refresh(self) -> None:
        q = self.game.quests
        if q is None:
            return
        parts = []
        for qid in list(q.active.keys())[:5]:
            st = q.active[qid]
            head = "<rgb(0.4,1,0.4)>" if st["state"] == "complete" else ("<rgb(1,0.4,0.3)>" if st["state"] == "failed" else "<rgb(1,0.82,0.3)>")
            parts.append(f"{head}{q.title(qid)}")
            if st["state"] == "complete":
                npc = q.turn_in_npc(qid)
                from core import data
                parts.append(f"<rgb(0.8,0.8,0.8)>  - Return to {data.npcs().get(npc, {}).get('name', '?')}")
            else:
                for t, done in q.objective_lines(qid):
                    parts.append(("<rgb(0.55,0.55,0.55)>" if done else "<rgb(0.95,0.95,0.95)>") + f"  - {t}")
        self.text.text = "\n".join(parts)
        self.bg.enabled = bool(parts)
        if parts:
            self.bg.scale = (0.3, len(parts) * 0.0205 + 0.016)
