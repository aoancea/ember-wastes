"""Ember Wastes - a single-player 3D fantasy action RPG built with Ursina.

Usage:
    python main.py                               # main menu
    python main.py --quickstart orc warrior Name # skip the menus and start a new character
    python main.py --autotest m1                 # scripted smoke test (screenshots + checks, then quits)
"""
from __future__ import annotations

import argparse
import sys

from panda3d.core import loadPrcFileData

from settings import GAME_TITLE, user_settings

MENU_TESTS = ("m7", "menu")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=GAME_TITLE)
    ap.add_argument("--autotest", default=None, help="run a scripted smoke test and quit")
    ap.add_argument("--quickstart", nargs="*", default=None, help="race class [name] - skip the menus")
    ap.add_argument("--novsync", action="store_true", help="uncapped frame rate")
    ap.add_argument("--size", default=None, help="window size WxH")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    loadPrcFileData("", "framebuffer-multisample 1\nmultisamples 4\n")
    loadPrcFileData("", "texture-anisotropic-degree 4\n")
    loadPrcFileData("", "window-title " + GAME_TITLE + "\n")
    if args.novsync or args.autotest:
        loadPrcFileData("", "sync-video 0\n")

    from ursina import Ursina

    size = tuple(user_settings.resolution)
    if args.size:
        w, h = args.size.lower().split("x")
        size = (int(w), int(h))
    fullscreen = bool(user_settings.fullscreen) and not args.autotest
    app = Ursina(title=GAME_TITLE, development_mode=False, fullscreen=fullscreen, borderless=False,
                 size=size, vsync=not (args.novsync or args.autotest), show_ursina_splash=False)
    from ursina import window
    if not fullscreen:
        window.center_on_screen()
    window.exit_button.enabled = False

    import core.game as game_module
    from core.game import Game, GameLoop
    from ui.hud import HUD
    from ui.menus import MenuController

    game = Game(app)
    game_module.game = game
    game.build_world()
    game.hud = HUD(game)
    game.menus = MenuController(game)
    GameLoop(game)

    if args.autotest and not args.autotest.startswith(MENU_TESTS):
        game.spawn_player("orc", "warrior", "Tester")
        game.hud.set_visible(True)
    elif args.quickstart is not None:
        q = args.quickstart
        race = q[0] if len(q) > 0 and q[0] in ("orc", "troll") else "orc"
        cls = q[1] if len(q) > 1 and q[1] in ("warrior", "hunter", "shaman") else "warrior"
        name = q[2] if len(q) > 2 else ("Urzag" if race == "orc" else "Zanwe")
        game.new_game(race, cls, name)
    else:
        game.state = "menu"
        game.hud.set_visible(False)
        game.menus.main.show()
        game.world.env.hour = 17.2

    if args.autotest:
        from core.autotest import AutoTest
        tester = AutoTest(game, args.autotest)
        game.on_update.append(tester.update)
    app.run(info=False)


if __name__ == "__main__":
    main()
