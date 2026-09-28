"""Loads the editable JSON game data from the /data folder."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from settings import DATA_DIR


@lru_cache(maxsize=None)
def load(name: str) -> Any:
    """Return the parsed contents of ``data/<name>.json`` (cached)."""
    path = DATA_DIR / f"{name}.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def reload_all() -> None:
    load.cache_clear()


def classes() -> dict[str, Any]:
    return load("classes")


def abilities() -> dict[str, Any]:
    return load("abilities")


def enemies() -> dict[str, Any]:
    return load("enemies")


def items() -> dict[str, Any]:
    return load("items")


def npcs() -> dict[str, Any]:
    return load("npcs")


def quests() -> dict[str, Any]:
    return load("quests")


def zones() -> dict[str, Any]:
    return load("zones")


def levels() -> dict[str, Any]:
    return load("levels")
