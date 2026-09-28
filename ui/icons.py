"""Procedurally drawn 64x64 icons for abilities and items (PIL)."""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from ursina import Texture

from core import data

S = 64
_cache: dict[tuple, Texture] = {}


def _bg(col: tuple[float, float, float]) -> Image.Image:
    y, x = np.mgrid[0:S, 0:S].astype(np.float32)
    dx, dy = (x - S * 0.4) / S, (y - S * 0.35) / S
    k = np.maximum(0.35, 1.15 - np.sqrt(dx * dx + dy * dy) * 1.3)
    n = ((x * 7 + y * 13) % 5) * 0.01
    arr = np.stack([col[0] * k + n, col[1] * k + n, col[2] * k + n, np.ones_like(k)], -1)
    img = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGBA")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, S - 1, S - 1], outline=(20, 14, 10, 255), width=3)
    d.rectangle([3, 3, S - 4, S - 4], outline=(255, 255, 255, 40), width=1)
    return img


def _c(col: tuple, a: int = 255) -> tuple[int, int, int, int]:
    return (int(col[0] * 255), int(col[1] * 255), int(col[2] * 255), a)


LIGHT = (0.95, 0.92, 0.85)
METAL = (0.78, 0.8, 0.84)
WOOD = (0.55, 0.36, 0.2)
DARKW = (0.35, 0.22, 0.12)


def _glyph(d: ImageDraw.ImageDraw, g: str, col: tuple = LIGHT, acc: tuple = METAL) -> None:
    c, a = _c(col), _c(acc)
    w = _c(WOOD)
    if g == "axe":
        d.line([(18, 52), (44, 12)], fill=w, width=5)
        d.polygon([(36, 10), (54, 18), (52, 34), (40, 26)], fill=a, outline=(40, 40, 45, 255))
    elif g == "greataxe":
        d.line([(16, 54), (46, 10)], fill=w, width=5)
        d.polygon([(34, 6), (56, 12), (54, 30), (42, 22)], fill=a)
        d.polygon([(40, 18), (22, 10), (26, 30), (36, 26)], fill=a)
    elif g == "sword" or g == "cutlass":
        d.polygon([(46, 8), (52, 12), (26, 40), (22, 36)], fill=a, outline=(60, 60, 70, 255))
        d.line([(16, 34), (30, 48)], fill=_c((0.8, 0.65, 0.2)), width=4)
        d.line([(22, 42), (12, 52)], fill=w, width=5)
    elif g in ("mace", "club"):
        d.line([(16, 52), (38, 24)], fill=w, width=6)
        d.ellipse([30, 8, 54, 32], fill=a if g == "mace" else w, outline=(40, 40, 40, 255))
        if g == "mace":
            for ang in range(0, 360, 60):
                x = 42 + math.cos(math.radians(ang)) * 13
                y = 20 + math.sin(math.radians(ang)) * 13
                d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=a)
    elif g == "staff":
        d.line([(20, 58), (40, 12)], fill=w, width=5)
        d.ellipse([34, 4, 50, 20], fill=_c((0.4, 0.8, 1.0)), outline=(255, 255, 255, 180))
    elif g == "spear":
        d.line([(14, 56), (44, 16)], fill=w, width=4)
        d.polygon([(40, 18), (52, 4), (48, 22)], fill=a)
    elif g == "bow":
        d.arc([12, 6, 44, 58], 290, 70, fill=w, width=5)
        d.line([(37, 9), (37, 55)], fill=c, width=1)
        d.line([(22, 32), (54, 32)], fill=c, width=2)
        d.polygon([(54, 32), (48, 28), (48, 36)], fill=a)
    elif g == "head":
        d.chord([14, 14, 50, 50], 180, 360, fill=a)
        d.rectangle([14, 30, 50, 36], fill=a)
        d.rectangle([28, 30, 36, 46], fill=a)
    elif g == "chest":
        d.polygon([(20, 14), (44, 14), (54, 24), (48, 30), (46, 52), (18, 52), (16, 30), (10, 24)], fill=a,
                  outline=(30, 20, 10, 255))
        d.line([(32, 16), (32, 50)], fill=(30, 20, 10, 200), width=2)
    elif g == "legs":
        d.polygon([(18, 12), (46, 12), (48, 54), (36, 54), (32, 28), (28, 54), (16, 54)], fill=a,
                  outline=(30, 20, 10, 255))
    elif g == "boots":
        d.polygon([(20, 10), (36, 10), (36, 40), (54, 44), (54, 54), (18, 54)], fill=a, outline=(30, 20, 10, 255))
    elif g == "food":
        d.ellipse([20, 12, 50, 40], fill=_c((0.62, 0.32, 0.18)))
        d.line([(24, 36), (12, 52)], fill=_c((0.95, 0.9, 0.8)), width=5)
    elif g == "drink":
        d.rectangle([22, 20, 42, 54], fill=_c((0.35, 0.6, 0.35)), outline=(20, 40, 20, 255))
        d.rectangle([28, 10, 36, 20], fill=_c((0.5, 0.35, 0.2)))
    elif g in ("potion_red", "potion_blue"):
        col2 = (0.85, 0.12, 0.1) if g == "potion_red" else (0.15, 0.35, 0.95)
        d.ellipse([16, 22, 48, 54], fill=_c(col2), outline=(240, 240, 240, 200))
        d.rectangle([27, 10, 37, 24], fill=_c((0.85, 0.85, 0.9)))
        d.ellipse([22, 28, 30, 36], fill=(255, 255, 255, 120))
    elif g == "tusk":
        d.polygon([(14, 50), (22, 30), (40, 14), (50, 12), (36, 26), (26, 46)], fill=c)
    elif g == "hide":
        d.polygon([(12, 16), (30, 10), (52, 16), (50, 36), (54, 52), (30, 48), (10, 54), (16, 34)], fill=_c((0.62, 0.45, 0.3)))
    elif g == "feather":
        d.line([(16, 54), (46, 10)], fill=c, width=2)
        d.polygon([(46, 10), (30, 20), (18, 46), (34, 34)], fill=_c((0.45, 0.4, 0.35)))
    elif g in ("shell", "scale"):
        d.pieslice([12, 12, 52, 52], 180, 360, fill=_c((0.9, 0.45, 0.3) if g == "shell" else (0.7, 0.35, 0.2)))
        for i in range(4):
            d.line([(32, 32), (14 + i * 12, 14)], fill=(60, 30, 20, 255), width=2)
    elif g in ("coin", "trinket"):
        d.ellipse([16, 16, 48, 48], fill=_c((0.85, 0.7, 0.25)), outline=(90, 70, 20, 255), width=3)
        d.text((27, 23), "$" if g == "coin" else "o", fill=(90, 70, 20, 255))
    elif g == "candle":
        d.rectangle([26, 26, 38, 54], fill=_c((0.9, 0.88, 0.75)))
        d.ellipse([28, 12, 36, 26], fill=_c((1.0, 0.7, 0.2)))
    elif g == "gem":
        d.polygon([(32, 10), (50, 26), (32, 54), (14, 26)], fill=_c((0.5, 0.2, 0.8)), outline=(230, 200, 255, 255))
    elif g == "insignia":
        d.polygon([(32, 8), (52, 20), (46, 50), (18, 50), (12, 20)], fill=_c((0.6, 0.15, 0.1)), outline=(30, 10, 5, 255))
        d.line([(24, 22), (40, 40)], fill=c, width=3)
        d.line([(40, 22), (24, 40)], fill=c, width=3)
    elif g in ("scroll", "letter"):
        d.rectangle([14, 16, 50, 48], fill=_c((0.92, 0.85, 0.65)), outline=(90, 70, 40, 255), width=2)
        for i in range(4):
            d.line([(20, 24 + i * 6), (44, 24 + i * 6)], fill=(90, 70, 40, 255), width=1)
        if g == "letter":
            d.ellipse([27, 38, 37, 48], fill=_c((0.7, 0.1, 0.1)))
    elif g in ("crate", "bundle"):
        if g == "crate":
            d.rectangle([12, 16, 52, 52], fill=_c((0.55, 0.38, 0.22)), outline=(40, 25, 10, 255), width=2)
            d.line([(12, 16), (52, 52)], fill=(40, 25, 10, 255), width=2)
            d.line([(52, 16), (12, 52)], fill=(40, 25, 10, 255), width=2)
        else:
            for i in range(4):
                d.line([(12, 22 + i * 7), (52, 18 + i * 7)], fill=_c((0.6, 0.5, 0.42)), width=5)
            d.line([(30, 12), (34, 52)], fill=_c((0.3, 0.2, 0.1)), width=3)
    elif g == "sac":
        d.ellipse([16, 20, 48, 52], fill=_c((0.45, 0.75, 0.25)), outline=(20, 40, 10, 255), width=2)
        d.polygon([(26, 22), (38, 22), (32, 12)], fill=_c((0.35, 0.6, 0.2)))
    elif g == "pearl":
        d.ellipse([18, 18, 46, 46], fill=_c((0.95, 0.95, 1.0)), outline=(160, 170, 200, 255), width=2)
        d.ellipse([24, 22, 32, 30], fill=(255, 255, 255, 255))
    elif g == "brand":
        d.line([(20, 54), (36, 24)], fill=_c((0.3, 0.3, 0.32)), width=6)
        d.ellipse([28, 8, 54, 34], fill=_c((1.0, 0.45, 0.1)), outline=(80, 20, 5, 255), width=3)
    # ---- ability glyphs
    elif g == "charge":
        for off in (0, 16):
            d.polygon([(12 + off, 16), (30 + off, 32), (12 + off, 48)], fill=c)
    elif g == "claw":
        for i in range(3):
            d.line([(16 + i * 11, 12), (26 + i * 11, 52)], fill=_c((1.0, 0.25, 0.2)), width=4)
    elif g == "quake":
        d.line([(8, 44), (56, 44)], fill=c, width=3)
        d.line([(32, 44), (26, 30), (36, 22), (30, 10)], fill=_c((1.0, 0.8, 0.4)), width=3)
        d.arc([10, 30, 54, 58], 180, 360, fill=c, width=2)
    elif g == "roar":
        d.ellipse([12, 20, 36, 44], fill=_c((0.95, 0.8, 0.3)))
        for r in (8, 14, 20):
            d.arc([30 - r, 32 - r, 30 + r + 16, 32 + r], 300, 60, fill=c, width=3)
    elif g == "arrow":
        d.line([(10, 54), (50, 14)], fill=w, width=4)
        d.polygon([(50, 14), (38, 18), (46, 26)], fill=a)
        d.line([(10, 54), (18, 54)], fill=c, width=3)
        d.line([(10, 54), (10, 46)], fill=c, width=3)
    elif g == "venom":
        d.polygon([(32, 8), (48, 36), (32, 54), (16, 36)], fill=_c((0.4, 0.9, 0.2)))
        d.ellipse([22, 30, 42, 50], fill=_c((0.4, 0.9, 0.2)))
    elif g == "chain":
        for i in range(3):
            d.ellipse([10 + i * 14, 22 + (i % 2) * 6, 30 + i * 14, 38 + (i % 2) * 6], outline=a, width=4)
    elif g == "rain":
        for i in range(5):
            x = 10 + i * 10
            d.line([(x, 8 + (i % 2) * 6), (x + 4, 40 + (i % 2) * 6)], fill=w, width=3)
            d.polygon([(x + 4, 46 + (i % 2) * 6), (x, 38 + (i % 2) * 6), (x + 8, 38 + (i % 2) * 6)], fill=a)
    elif g == "paw":
        d.ellipse([20, 30, 44, 52], fill=c)
        for x, y in ((14, 18), (24, 10), (36, 10), (46, 18)):
            d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=c)
    elif g in ("bolt", "chain_bolt"):
        pts = [(38, 6), (20, 34), (32, 34), (24, 58), (46, 26), (34, 26), (42, 6)]
        d.polygon(pts, fill=_c((1.0, 0.95, 0.5)), outline=(255, 255, 255, 255))
        if g == "chain_bolt":
            d.line([(46, 30), (58, 40), (50, 50)], fill=_c((0.7, 0.8, 1.0)), width=3)
    elif g == "flame":
        d.polygon([(32, 6), (46, 30), (44, 50), (32, 58), (20, 50), (18, 30)], fill=_c((1.0, 0.55, 0.1)))
        d.polygon([(32, 26), (40, 42), (32, 54), (24, 42)], fill=_c((1.0, 0.9, 0.3)))
    elif g == "drop":
        d.polygon([(32, 6), (46, 34), (18, 34)], fill=_c((0.4, 0.8, 1.0)))
        d.ellipse([17, 24, 47, 54], fill=_c((0.4, 0.8, 1.0)))
        d.ellipse([24, 32, 30, 40], fill=(255, 255, 255, 200))
    elif g == "totem":
        d.rectangle([26, 14, 38, 58], fill=w)
        d.rectangle([20, 18, 44, 32], fill=_c((0.75, 0.2, 0.15)))
        d.polygon([(26, 14), (32, 2), (38, 14)], fill=_c((1.0, 0.6, 0.15)))
    else:
        d.ellipse([18, 18, 46, 46], fill=c)


def _to_texture(img: Image.Image) -> Texture:
    t = Texture(img.filter(ImageFilter.SMOOTH))
    t.filtering = "bilinear"
    return t


def ability_icon(aid: str) -> Texture:
    key = ("ability", aid)
    if key not in _cache:
        d = data.abilities()[aid]
        ic = d.get("icon", {})
        img = _bg(tuple(ic.get("bg", (0.3, 0.3, 0.3))))
        _glyph(ImageDraw.Draw(img), ic.get("glyph", ""))
        _cache[key] = _to_texture(img)
    return _cache[key]


_ITEM_GLYPHS = {
    "broken_tusk": "tusk", "rough_hide": "hide", "scorpion_carapace": "shell", "vulture_feather": "feather",
    "crab_shell_fragment": "shell", "lizard_scale": "scale", "smuggler_trinket": "trinket", "goblin_candle_stub": "candle",
    "bent_coin": "coin", "cracked_gemstone": "gem", "raider_insignia": "insignia", "clan_message": "letter",
    "pearl_offering": "pearl", "venom_sac": "sac", "driftwood_bundle": "bundle", "lizard_hide": "hide",
    "stolen_supplies": "crate", "sealed_orders": "scroll", "warlords_brand": "brand", "roasted_haunch": "food",
    "cactus_water": "drink", "minor_healing_draught": "potion_red", "healing_draught": "potion_red",
    "minor_mana_draught": "potion_blue",
}

_RARITY_BG = {"poor": (0.25, 0.25, 0.25), "common": (0.3, 0.26, 0.2), "uncommon": (0.14, 0.32, 0.12),
              "rare": (0.1, 0.2, 0.42)}


def item_icon(item_id: str) -> Texture:
    key = ("item", item_id)
    if key not in _cache:
        it: dict[str, Any] = data.items()["items"][item_id]
        slot = it["slot"]
        if slot == "weapon":
            g = it.get("weapon_type", "sword")
        elif slot in ("head", "chest", "legs", "boots"):
            g = slot
        else:
            g = _ITEM_GLYPHS.get(item_id, "gem")
        img = _bg(_RARITY_BG.get(it.get("rarity", "common"), (0.3, 0.26, 0.2)))
        col = tuple(it.get("color", METAL))
        acc = col if slot in ("head", "chest", "legs", "boots") else METAL
        if slot == "weapon":
            acc = (min(1, col[0] * 1.1 + 0.1), min(1, col[1] * 1.1 + 0.1), min(1, col[2] * 1.1 + 0.1))
        _glyph(ImageDraw.Draw(img), g, LIGHT, acc)
        _cache[key] = _to_texture(img)
    return _cache[key]


def simple_icon(glyph: str, bg: tuple = (0.3, 0.3, 0.3)) -> Texture:
    key = ("simple", glyph, bg)
    if key not in _cache:
        img = _bg(bg)
        _glyph(ImageDraw.Draw(img), glyph)
        _cache[key] = _to_texture(img)
    return _cache[key]
