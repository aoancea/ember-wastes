"""Save and load the game to local JSON files (one file per character in saves/)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from settings import SAVE_DIR, VERSION

SAVE_FORMAT = 1


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()) or "hero"
    return s[:40]


def save_path(name: str) -> Path:
    return SAVE_DIR / f"{_slug(name)}.json"


def collect(game) -> dict[str, Any]:
    """Gather everything needed to restore the current game."""
    p = game.player
    pdata = p.to_dict()
    if game.dungeon is not None and game.dungeon.inside:
        pdata["pos"] = [-222.0, 216.0]
        pdata["yaw"] = 120.0
    if p.dead:
        pdata["hp"] = p.max_hp * 0.5
    return {
        "format": SAVE_FORMAT,
        "game_version": VERSION,
        "saved_at": time.time(),
        "player": pdata,
        "abilities": game.abilities.to_dict(),
        "quests": game.quests.to_dict(),
        "world": {"hour": game.world.env.hour},
        "victory": bool(getattr(game, "victory", False)),
        "play_time": float(getattr(game, "play_time", 0.0)),
    }


def save_game(game) -> Path:
    """Write the save file for the current character and return its path."""
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
    data = collect(game)
    path = save_path(game.player.name)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(path)
    return path


def read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "player" not in data:
            return None
        return data
    except (OSError, ValueError):
        return None


def list_saves() -> list[tuple[Path, dict[str, Any]]]:
    """All readable saves, newest first."""
    if not SAVE_DIR.exists():
        return []
    out = []
    for f in SAVE_DIR.glob("*.json"):
        d = read(f)
        if d:
            out.append((f, d))
    out.sort(key=lambda t: t[1].get("saved_at", 0), reverse=True)
    return out


def latest() -> tuple[Path, dict[str, Any]] | None:
    saves = list_saves()
    return saves[0] if saves else None


def delete(path: Path) -> None:
    try:
        Path(path).unlink()
    except OSError:
        pass


def describe(d: dict[str, Any]) -> str:
    p = d["player"]
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(d.get("saved_at", 0)))
    return f"{p['name']}  -  Level {p['level']} {p['race'].title()} {p['cls'].title()}  -  {when}"
