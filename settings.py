"""Global constants and persistent user settings for Ember Wastes."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def base_dir() -> Path:
    """Folder that holds writable files (saves, settings, cache)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_dir() -> Path:
    """Folder that holds bundled read-only resources (data/*.json)."""
    return Path(getattr(sys, "_MEIPASS", base_dir()))


ROOT = base_dir()
DATA_DIR = resource_dir() / "data"
SAVE_DIR = ROOT / "saves"
CACHE_DIR = ROOT / "cache"
SCREENSHOT_DIR = ROOT / "screenshots"
SETTINGS_FILE = ROOT / "settings.json"

GAME_TITLE = "Ember Wastes"
VERSION = "1.0.0"

# --- World layout -----------------------------------------------------------
WORLD_MIN_X, WORLD_MAX_X = -320.0, 320.0
WORLD_MIN_Z, WORLD_MAX_Z = -384.0, 384.0
TERRAIN_CELL = 2.0          # world units per heightmap cell
CHUNK_CELLS = 32            # cells per terrain chunk side
SEA_LEVEL = 0.0
SWIM_DEPTH = 1.35           # water deeper than this makes the player swim
PLAYABLE_MAX_X = 300.0      # invisible sea boundary

# Dungeon interior lives far away from the overworld
DUNGEON_ORIGIN = (2000.0, 0.0, 0.0)

# --- Time ---------------------------------------------------------------------
DAY_LENGTH_SECONDS = 1200.0  # one full in-game day in real seconds
START_HOUR = 9.0

# --- Gameplay -------------------------------------------------------------------
MAX_LEVEL = 10
GLOBAL_COOLDOWN = 1.0
MELEE_RANGE = 3.2
INTERACT_RANGE = 5.0
LOOT_RANGE = 5.0
CORPSE_TIME = 90.0

RESOLUTIONS: list[tuple[int, int]] = [
    (1280, 720), (1600, 900), (1920, 1080), (2560, 1440), (3840, 2160),
]


@dataclass
class UserSettings:
    """Options the player can change from the settings menu."""

    mouse_sensitivity: float = 1.0
    master_volume: float = 0.8
    sfx_volume: float = 0.9
    ambient_volume: float = 0.6
    resolution: list[int] = field(default_factory=lambda: [1600, 900])
    fullscreen: bool = False
    view_distance: float = 260.0
    heat_haze: bool = True
    show_fps: bool = True
    invert_y: bool = False

    @classmethod
    def load(cls) -> "UserSettings":
        """Load settings from disk, falling back to defaults on any problem."""
        s = cls()
        try:
            raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            for key, value in raw.items():
                if hasattr(s, key):
                    setattr(s, key, value)
        except (OSError, ValueError):
            pass
        return s

    def save(self) -> None:
        """Write settings to disk (errors are ignored)."""
        try:
            SETTINGS_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except OSError:
            pass


user_settings = UserSettings.load()
