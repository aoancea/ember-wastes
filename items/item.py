"""Item definitions (from items.json) and helpers for names, colours, stats and tooltips."""
from __future__ import annotations

from typing import Any

from core import data

EQUIP_SLOTS = ("weapon", "head", "chest", "legs", "boots")
SLOT_NAMES = {"weapon": "Weapon", "head": "Head", "chest": "Chest", "legs": "Legs", "boots": "Feet"}
STAT_ORDER = ("strength", "agility", "intellect", "stamina", "spell_power", "attack_power")
STAT_NAMES = {"strength": "Strength", "agility": "Agility", "intellect": "Intellect", "stamina": "Stamina",
              "spell_power": "Spell Power", "attack_power": "Attack Power", "armor": "Armor"}


def get(item_id: str) -> dict[str, Any]:
    return data.items()["items"][item_id]


def exists(item_id: str) -> bool:
    return item_id in data.items()["items"]


def name(item_id: str) -> str:
    return get(item_id)["name"]


def rarity_color(rarity: str) -> tuple[float, float, float]:
    return tuple(data.items()["rarity_colors"].get(rarity, (1, 1, 1)))  # type: ignore[return-value]


def color_of(item_id: str) -> tuple[float, float, float]:
    return rarity_color(get(item_id).get("rarity", "common"))


def is_equippable(item_id: str) -> bool:
    return get(item_id)["slot"] in EQUIP_SLOTS


def stack_size(item_id: str) -> int:
    return int(get(item_id).get("stack", 1))


def sell_price(item_id: str) -> int:
    it = get(item_id)
    p = int(it.get("price", 0))
    if p <= 0:
        return 0
    if it["slot"] == "junk":
        return p
    return max(1, p // 4)


def buy_price(item_id: str) -> int:
    return int(get(item_id).get("price", 0))


def stats(item_id: str) -> dict[str, float]:
    return dict(get(item_id).get("stats", {}))


def weapon_dps(item_id: str) -> float:
    it = get(item_id)
    if "damage" not in it:
        return 0.0
    lo, hi = it["damage"]
    return (lo + hi) / 2.0 / it.get("speed", 2.0)


def can_equip(player, item_id: str) -> tuple[bool, str]:
    it = get(item_id)
    if it["slot"] not in EQUIP_SLOTS:
        return False, "That can't be equipped."
    if it.get("level", 1) > player.level:
        return False, f"Requires level {it['level']}."
    classes = it.get("classes")
    if classes and player.cls not in classes:
        return False, "Your class can't use that."
    if it["slot"] == "weapon":
        wt = it.get("weapon_type")
        allowed = data.classes()[player.cls]["weapon_types"]
        if wt == "cutlass":
            wt = "sword"
        if wt not in allowed:
            return False, f"{player.cls.title()}s can't use {it.get('weapon_type')}s."
    return True, ""


def tooltip_lines(item_id: str, player=None, compare_with: str | None = None) -> list[tuple[str, tuple]]:
    """Lines of (text, rgb) describing an item, with green/red deltas vs. ``compare_with``."""
    it = get(item_id)
    white = (1, 1, 1)
    grey = (0.7, 0.7, 0.7)
    green = (0.2, 1.0, 0.2)
    red = (1.0, 0.3, 0.25)
    yellow = (1.0, 0.85, 0.3)
    lines: list[tuple[str, tuple]] = [(it["name"], rarity_color(it.get("rarity", "common")))]
    slot = it["slot"]
    if slot in EQUIP_SLOTS:
        kind = it.get("weapon_type", "").title() if slot == "weapon" else ""
        lines.append((f"{SLOT_NAMES[slot]}   {kind}".rstrip(), white))
        if "damage" in it:
            lo, hi = it["damage"]
            lines.append((f"{lo} - {hi} Damage     Speed {it.get('speed', 2.0):.1f}", white))
            lines.append((f"({weapon_dps(item_id):.1f} damage per second)", white))
        st = it.get("stats", {})
        if st.get("armor"):
            lines.append((f"{int(st['armor'])} Armor", white))
        for k in STAT_ORDER:
            if st.get(k):
                lines.append((f"+{int(st[k])} {STAT_NAMES[k]}", green))
        if compare_with:
            other = get(compare_with)
            deltas: list[tuple[str, float]] = []
            if "damage" in it or "damage" in other:
                d = weapon_dps(item_id) - weapon_dps(compare_with)
                if abs(d) > 0.05:
                    deltas.append(("DPS", round(d, 1)))
            ost = other.get("stats", {})
            for k in ("armor",) + STAT_ORDER:
                d = st.get(k, 0) - ost.get(k, 0)
                if d:
                    deltas.append((STAT_NAMES[k], d))
            lines.append(("", white))
            lines.append((f"Compared to {other['name']}:", grey))
            if not deltas:
                lines.append(("  No change", grey))
            for label, d in deltas:
                sign = "+" if d > 0 else ""
                val = f"{d:.1f}" if isinstance(d, float) and not float(d).is_integer() else f"{int(d)}"
                lines.append((f"  {sign}{val} {label}", green if d > 0 else red))
        req = it.get("level", 1)
        if player is not None and req > 1:
            lines.append((f"Requires Level {req}", red if req > player.level else white))
        if player is not None and slot in EQUIP_SLOTS:
            ok, why = can_equip(player, item_id)
            if not ok and "level" not in why:
                lines.append((why, red))
    elif slot == "consumable":
        lines.append(("Consumable", white))
        if it.get("description"):
            lines.append((it["description"], green))
    elif slot == "quest":
        lines.append(("Quest Item", yellow))
    elif slot == "junk":
        lines.append(("Junk", grey))
    sp = sell_price(item_id)
    if sp:
        lines.append((f"Sells for {sp} gold", yellow))
    return lines
