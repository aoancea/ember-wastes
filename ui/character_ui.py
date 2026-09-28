"""Character window (C): equipped gear and every stat."""
from __future__ import annotations

from typing import Any

from ursina import color, window

from combat.combat import armor_mitigation
from core.events import events
from items import item as I
from ui.icons import item_icon, simple_icon
from ui.widgets import DIM, GOLD, TEXT, IconSlot, Panel, label


class CharacterWindow(Panel):
    SLOTS = [("head", "Head", "head"), ("chest", "Chest", "chest"), ("legs", "Legs", "legs"), ("boots", "Feet", "boots"),
             ("weapon", "Weapon", "sword")]

    def __init__(self, game) -> None:
        super().__init__(position=(-window.aspect_ratio / 2 + 0.3, 0.02), size=(0.6, 0.56), title="Character",
                         on_close=self.close, z=-0.45)
        self.game = game
        self.header = label(self, "", (0, self.top - 0.065), 0.95, TEXT, origin=(0, 0))
        self.slot_widgets: dict[str, IconSlot] = {}
        self.slot_names: dict[str, Any] = {}
        for i, (slot, title, glyph) in enumerate(self.SLOTS):
            y = self.top - 0.13 - i * 0.075
            s = IconSlot(self, (self.left + 0.05, y), 0.062, on_right_click=lambda s, sl=slot: self._unequip(sl),
                         tooltip=lambda s, sl=slot: self._tooltip(sl))
            self.slot_widgets[slot] = s
            self.slot_names[slot] = label(self, title, (self.left + 0.09, y + 0.012), 0.75, DIM)
            self.slot_names[slot + "_item"] = label(self, "", (self.left + 0.09, y - 0.008), 0.72, TEXT)
        self.stat_lines = [label(self, "", (0.0, self.top - 0.11 - i * 0.027), 0.8, TEXT) for i in range(15)]
        self.hint = label(self, "Right-click gear to unequip", (0, -self.size[1] / 2 + 0.025), 0.7, DIM, origin=(0, 0))
        self.enabled = False
        events.on("stats_changed", lambda **_: self.refresh())
        events.on("equipment_changed", lambda **_: self.refresh())
        events.on("level_up", lambda **_: self.refresh())

    def open(self) -> None:
        self.enabled = True
        self.refresh()
        events.emit("sound", name="open")

    def close(self) -> None:
        self.enabled = False

    def toggle(self) -> None:
        self.close() if self.enabled else self.open()

    def _tooltip(self, slot: str) -> list | None:
        iid = self.game.player.equipment.get(slot)
        if not iid:
            return [(dict((s, t) for s, t, _ in self.SLOTS)[slot], (0.8, 0.8, 0.8)), ("Empty", (0.6, 0.6, 0.6))]
        return I.tooltip_lines(iid, self.game.player)

    def _unequip(self, slot: str) -> None:
        self.game.player.unequip(slot)
        self.refresh()

    def refresh(self) -> None:
        if not self.enabled:
            return
        p = self.game.player
        self.header.text = f"{p.name}   Level {p.level} {p.race.title()} {p.cls_def['name']}"
        for slot, title, glyph in self.SLOTS:
            iid = p.equipment.get(slot)
            w = self.slot_widgets[slot]
            if iid:
                w.set_icon(item_icon(iid), I.color_of(iid))
                self.slot_names[slot + "_item"].text = I.name(iid)
                self.slot_names[slot + "_item"].color = color.rgb(*I.color_of(iid))
            else:
                w.set_icon(simple_icon(glyph, (0.12, 0.1, 0.08)), None)
                w.icon.color = color.rgba(1, 1, 1, 0.25)
                self.slot_names[slot + "_item"].text = "Empty"
                self.slot_names[slot + "_item"].color = DIM
            if iid:
                w.icon.color = color.white
        st = p.stats
        lo, hi = p.damage_range()
        _, _, speed = p.weapon_info()
        dr = armor_mitigation(p.armor, p.level) * 100
        res_name = "Rage" if p.resource_type == "rage" else "Mana"

        def gear(stat: str) -> str:
            g = st.gear.get(stat, 0)
            return f"  (+{int(g)})" if g else ""
        lines = [
            (f"Health            {int(p.hp)} / {int(p.max_hp)}", (0.4, 1, 0.4)),
            (f"{res_name:<18}{int(p.resource)} / {int(p.max_resource)}", (0.5, 0.7, 1) if res_name == "Mana" else (1, 0.45, 0.4)),
            ("", TEXT),
            (f"Strength          {int(st.strength)}{gear('strength')}", TEXT),
            (f"Agility            {int(st.agility)}{gear('agility')}", TEXT),
            (f"Intellect         {int(st.intellect)}{gear('intellect')}", TEXT),
            (f"Stamina           {int(st.stamina)}{gear('stamina')}", TEXT),
            (f"Armor              {int(p.armor)}  (-{dr:.0f}% dmg)", TEXT),
            ("", TEXT),
            (f"Damage            {lo} - {hi}   ({speed:.1f}s)", GOLD),
            (f"DPS                 {(lo + hi) / 2 / speed:.1f}", GOLD),
            (f"Attack Power    {int(p.attack_power())}", GOLD),
            (f"Crit Chance      {p.crit_chance() * 100:.1f}%", GOLD),
            (f"Spell Power     {int(p.spell_power())}", GOLD),
            (f"Spell Crit        {st.spell_crit_chance() * 100:.1f}%", GOLD),
        ]
        for t, (txt, col) in zip(self.stat_lines, lines):
            t.text = txt
            t.color = col if isinstance(col, color.Color) else color.rgb(*col)
