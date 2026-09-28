"""On-screen text: error line, scrolling chat/loot log and big centre announcements."""
from __future__ import annotations

from typing import Any

from ursina import Entity, Text, camera, color, window

from core.events import events
from items import item as I
from ui.widgets import rgb, tag


class Messages:
    """Listens to game events and prints them in the right place."""

    LOG_LINES = 8

    def __init__(self, game) -> None:
        self.game = game
        self.error = Text(parent=camera.ui, text="", origin=(0, 0), y=0.33, scale=1.15, color=color.rgb(1, 0.3, 0.25))
        self.error_t = 0.0
        self.banner = Text(parent=camera.ui, text="", origin=(0, 0), y=0.22, scale=2.2, color=color.rgb(1, 0.85, 0.4))
        self.sub = Text(parent=camera.ui, text="", origin=(0, 0), y=0.17, scale=1.2, color=color.rgb(1, 0.95, 0.8))
        self.banner_t = 0.0
        self.log_root = Entity(parent=camera.ui, position=(-window.aspect_ratio / 2 + 0.02, -0.2, 0))
        self.log_bg = Entity(parent=self.log_root, model="quad", origin=(-0.5, 0.5), scale=(0.52, 0.2), y=0.01,
                             color=color.rgba(0, 0, 0, 0.12), z=0.01)
        self.log_texts = [Text(parent=self.log_root, text="", origin=(-0.5, 0.5), position=(0.008, -i * 0.024, 0),
                               scale=0.78) for i in range(self.LOG_LINES)]
        self.lines: list[str] = []
        events.on("message", self._on_message)
        events.on("item_received", self._on_item)
        events.on("gold_changed", self._on_gold)
        events.on("xp_gained", self._on_xp)
        events.on("level_up", self._on_level)
        events.on("emote", self._on_emote)
        events.on("chat", self._on_chat)
        events.on("announce", self._on_announce)

    # ---------------------------------------------------------------- handlers
    def _on_message(self, text: str, color: Any = (1, 0.3, 0.25), **_: Any) -> None:
        self.error.text = text
        self.error.color = rgb(color)
        self.error_t = 2.5

    def log(self, text: str) -> None:
        self.lines.append(text)
        self.lines = self.lines[-self.LOG_LINES:]
        for i, t in enumerate(self.log_texts):
            idx = len(self.lines) - self.LOG_LINES + i
            t.text = self.lines[idx] if 0 <= idx < len(self.lines) else ""

    def _on_item(self, item_id: str, count: int = 1, **_: Any) -> None:
        c = I.color_of(item_id)
        extra = f" x{count}" if count > 1 else ""
        self.log(f"<rgb(0.8,0.8,0.8)>You receive: {tag(c)}[{I.name(item_id)}]<rgb(0.8,0.8,0.8)>{extra}")

    def _on_gold(self, gold: int, delta: int, **_: Any) -> None:
        if delta > 0:
            self.log(f"<rgb(1,0.85,0.3)>You receive {delta} gold.")

    def _on_xp(self, amount: int, reason: str = "", **_: Any) -> None:
        if amount > 0:
            why = f" ({reason})" if reason else ""
            self.log(f"<rgb(0.75,0.55,1)>You gain {amount} experience{why}.")

    def _on_level(self, level: int, gained: dict | None = None, hp: int = 0, resource: int = 0, **_: Any) -> None:
        self.announce(f"Level {level}!", "You feel stronger.")
        parts = [f"+{int(v)} {k.title()}" for k, v in (gained or {}).items()]
        self.log(f"<rgb(1,0.85,0.3)>You have reached level {level}! " + ", ".join(parts))

    def _on_emote(self, unit: Any, text: str, **_: Any) -> None:
        self.log(f"<rgb(1,0.55,0.3)>{text}")

    def _on_chat(self, text: str, **_: Any) -> None:
        self.log(text)

    def _on_announce(self, title: str, subtitle: str = "", **_: Any) -> None:
        self.announce(title, subtitle)

    def announce(self, title: str, subtitle: str = "", duration: float = 3.5) -> None:
        self.banner.text = title
        self.sub.text = subtitle
        self.banner_t = duration

    def update(self, dt: float) -> None:
        if self.error_t > 0:
            self.error_t -= dt
            a = min(1.0, self.error_t)
            c = self.error.color
            self.error.color = color.rgba(c[0], c[1], c[2], a)
            if self.error_t <= 0:
                self.error.text = ""
        if self.banner_t > 0:
            self.banner_t -= dt
            a = min(1.0, self.banner_t)
            self.banner.color = color.rgba(1, 0.85, 0.4, a)
            self.sub.color = color.rgba(1, 0.95, 0.8, a)
            if self.banner_t <= 0:
                self.banner.text = ""
                self.sub.text = ""
