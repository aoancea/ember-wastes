"""Loot generation for defeated enemies (gold, junk, gear by level, quest drops)."""
from __future__ import annotations

import random
from typing import Any

from core import data
from items import item as I


class LootSystem:
    """Rolls loot tables from enemies.json; quest drops are supplied by the quest manager."""

    def __init__(self, game) -> None:
        self.game = game
        self._drop_pool: list[str] | None = None

    def _pool(self) -> list[str]:
        if self._drop_pool is None:
            self._drop_pool = [iid for iid, it in data.items()["items"].items() if it.get("world_drop")]
        return self._drop_pool

    def roll(self, enemy) -> dict[str, Any]:
        t = enemy.t
        table = t.get("loot", {})
        sc = data.enemies()["scaling"]
        items: list[dict[str, Any]] = []
        gmin, gmax = table.get("gold", [0, 0])
        gold = random.randint(gmin, gmax)
        if gold:
            gold = int(round(gold * (1 + sc["gold_growth"] * (enemy.level - 1))))
        for iid, chance in table.get("items", []):
            if random.random() < chance:
                items.append({"id": iid, "count": 1})
        if random.random() < table.get("gear", 0.0):
            gear = self._roll_gear(enemy.level)
            if gear:
                items.append({"id": gear, "count": 1})
        for iid in table.get("guaranteed", []):
            items.append({"id": iid, "count": 1})
        by_class = table.get("guaranteed_class")
        if by_class and self.game.player is not None:
            iid = by_class.get(self.game.player.cls)
            if iid:
                items.append({"id": iid, "count": 1})
        if self.game.quests is not None:
            for iid in self.game.quests.quest_drops(enemy):
                items.append({"id": iid, "count": 1, "quest": True})
        return {"gold": gold, "items": items}

    def _roll_gear(self, level: int) -> str | None:
        cands = []
        for iid in self._pool():
            it = I.get(iid)
            lv = it.get("level", 1)
            if level - 3 <= lv <= level + 1:
                w = {"common": 5.0, "uncommon": 2.0, "rare": 0.35}.get(it.get("rarity", "common"), 1.0)
                cands.append((iid, w))
        if not cands:
            return None
        total = sum(w for _, w in cands)
        r = random.random() * total
        for iid, w in cands:
            r -= w
            if r <= 0:
                return iid
        return cands[-1][0]
