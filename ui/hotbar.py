"""Action bar (abilities 1-5), experience bar and the micro-menu buttons."""
from __future__ import annotations


from ursina import Entity, camera, color

from core import data
from ui.icons import ability_icon
from ui.widgets import Bar, IconSlot, make_button, quad

XP_PURPLE = color.rgb(0.55, 0.25, 0.85)


class Hotbar(Entity):
    """Five ability slots bound to keys 1-5, with cooldown sweep and usability tint."""

    SLOT = 0.072
    GAP = 0.008

    def __init__(self, game) -> None:
        super().__init__(parent=camera.ui, position=(0, -0.425, 0))
        self.game = game
        n = 5
        total = n * self.SLOT + (n - 1) * self.GAP
        self.bg = quad(self, (0, 0), (total + 0.03, self.SLOT + 0.026), color.rgba(0.06, 0.05, 0.04, 0.85), z=0.02)
        self.border = quad(self, (0, 0), (total + 0.036, self.SLOT + 0.032), color.rgba(0.55, 0.42, 0.22, 1), z=0.03)
        self.slots: list[IconSlot] = []
        for i in range(n):
            x = -total / 2 + self.SLOT / 2 + i * (self.SLOT + self.GAP)
            s = IconSlot(self, (x, 0), self.SLOT, on_click=lambda s, i=i: self.game.abilities.use_slot(i),
                         tooltip=lambda s, i=i: self._tooltip(i), key_label=str(i + 1))
            self.slots.append(s)
        self._known_sig: tuple = ()

    def _tooltip(self, i: int) -> list | None:
        ab = self.game.abilities
        if ab is None:
            return None
        aid = ab.order[i]
        if aid in ab.known:
            return ab.tooltip(aid)
        d = data.abilities()[aid]
        return [(d["name"], (0.7, 0.7, 0.7)), (f"Learn at level {d['level']} from the class trainer", (1, 0.4, 0.3)),
                (ab.describe(aid, 1), (1, 0.85, 0.3))]

    def refresh_icons(self) -> None:
        ab = self.game.abilities
        for i, s in enumerate(self.slots):
            aid = ab.order[i]
            if aid in ab.known:
                s.set_icon(ability_icon(aid), (0.75, 0.6, 0.3))
                s.icon.color = color.white
                s._tint = (1, 1, 1, 1)
            else:
                s.set_icon(ability_icon(aid), (0.25, 0.22, 0.2))
                s.icon.color = color.rgba(0.35, 0.35, 0.35, 1)

    def update(self) -> None:
        g = self.game
        ab = getattr(g, "abilities", None)
        if ab is None or g.player is None:
            return
        sig = tuple(sorted(ab.known.items()))
        if sig != self._known_sig:
            self._known_sig = sig
            self.refresh_icons()
        p = g.player
        t = p.target
        for i, s in enumerate(self.slots):
            aid = ab.order[i]
            if aid not in ab.known:
                s.set_cooldown(0, 1)
                s.set_dim(True)
                continue
            rem, tot = ab.cooldown_left(aid)
            s.set_cooldown(rem, tot)
            d = ab.defs[aid]
            unusable = bool(d.get("cost")) and p.resource < d["cost"]
            rng = d.get("range")
            if t is not None and hasattr(t, "take_damage") and not t.dead and rng not in (0, None):
                dist = p.distance_to(t)
                if rng == "melee":
                    unusable = unusable or dist > p.melee_reach(t)
                elif isinstance(rng, (int, float)):
                    unusable = unusable or dist > rng
            want = (1, 0.45, 0.45, 1) if unusable else (1, 1, 1, 1)
            if getattr(s, "_tint", None) != want:
                s._tint = want
                s.icon.color = color.rgba(*want)
            s.set_dim(False)


class XPBar(Entity):
    def __init__(self, game) -> None:
        super().__init__(parent=camera.ui, position=(-0.3, -0.478, 0))
        self.game = game
        self.bar = Bar(self, (0, 0), (0.6, 0.014), XP_PURPLE, text_scale=0.6)
        self.ticks = [quad(self, (0.6 * i / 10, 0), (0.002, 0.014), color.rgba(0, 0, 0, 0.6), z=-0.006) for i in range(1, 10)]

    def update(self) -> None:
        p = self.game.player
        if p is None:
            return
        xp = p.xp
        if xp.needed <= 0:
            self.bar.set(1, 1, "Maximum level")
        else:
            self.bar.set(xp.xp, xp.needed, f"Level {xp.level}   {xp.xp} / {xp.needed} XP")


class MicroMenu(Entity):
    """Small buttons for the main windows (also reachable with hotkeys)."""

    def __init__(self, hud) -> None:
        super().__init__(parent=camera.ui, position=(0.33, -0.425, 0))
        self.hud = hud
        items = [("C", "Character (C)", "character"), ("B", "Bags (B)", "bags"), ("L", "Quest Log (L)", "questlog"),
                 ("M", "World Map (M)", "map"), ("Esc", "Menu (Esc)", "menu")]
        self.buttons = []
        for i, (lbl, tip, key) in enumerate(items):
            b = make_button(self, lbl, (i * 0.048, 0), (0.042, 0.042), lambda k=key: self.hud.toggle(k), text_scale=0.8)
            b.tooltip_text = tip
            self.buttons.append(b)
