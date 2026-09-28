"""Menus: main menu, character creation, load, settings, pause, death and victory screens."""
from __future__ import annotations

import math
from typing import Any

from ursina import Button, Entity, InputField, Slider, Text, camera, color, window

import save as savefile
from core import data
from core.events import events
from settings import GAME_TITLE, RESOLUTIONS, VERSION, user_settings
from ui.widgets import DIM, GOLD, TEXT, Panel, label, make_button

TITLE_RED = color.rgb(0.95, 0.42, 0.18)


class DeathPanel(Entity):
    """'You have died' overlay with a Release Spirit button."""

    def __init__(self, game) -> None:
        super().__init__(parent=camera.ui, z=-2, enabled=False)
        self.game = game
        self.shade = Entity(parent=self, model="quad", scale=(4, 2), color=color.rgba(0.25, 0.0, 0.0, 0.35), z=0.1)
        self.panel = Panel(self, (0, 0.12), (0.46, 0.2))
        self.title = label(self.panel, "You have died.", (0, 0.045), 1.8, color.rgb(1, 0.3, 0.25), origin=(0, 0))
        self.btn = make_button(self.panel, "Release Spirit", (0, -0.045), (0.22, 0.05), self.release)
        events.on("player_died", self._on_died)
        events.on("player_revived", lambda **_: setattr(self, "enabled", False))
        self._t = 0.0

    def _on_died(self, **_: Any) -> None:
        self._t = 0.0
        self.enabled = True
        self.btn.enabled = False

    def release(self) -> None:
        self.game.release_spirit()
        self.enabled = False

    def update(self) -> None:
        from ursina import time
        self._t += time.dt
        if self._t > 1.5 and not self.btn.enabled:
            self.btn.enabled = True


class MenuScreen(Entity):
    """Base for full-screen menus: dimmed background + centred column of buttons."""

    def __init__(self, game, dim: float = 0.35) -> None:
        super().__init__(parent=camera.ui, z=-8, enabled=False)
        self.game = game
        self.shade = Entity(parent=self, model="quad", scale=(4, 2), color=color.rgba(0, 0, 0, dim), z=0.2)

    def show(self) -> None:
        self.enabled = True

    def hide(self) -> None:
        self.enabled = False


class MainMenu(MenuScreen):
    def __init__(self, game, ui) -> None:
        super().__init__(game, 0.25)
        self.ui = ui
        self.title = Text(parent=self, text=GAME_TITLE.upper(), origin=(0, 0), y=0.3, scale=4.2, color=TITLE_RED)
        self.subtitle = Text(parent=self, text="A tale of the orc clans and the tide-born tribe", origin=(0, 0), y=0.225,
                             scale=1.2, color=color.rgb(1, 0.9, 0.7))
        self.version = Text(parent=self, text=f"v{VERSION}", origin=(0.5, -0.5), position=(window.aspect_ratio / 2 - 0.02, -0.485),
                            scale=0.8, color=DIM)
        self.panel = Panel(self, (0, -0.06), (0.4, 0.44))
        self.buttons: list[Button] = []
        items = [("New Game", ui.open_creation), ("Continue", self._continue), ("Load Game", ui.open_load),
                 ("Settings", lambda: ui.open_settings(self)), ("Quit", self._quit)]
        for i, (txt, fn) in enumerate(items):
            b = make_button(self.panel, txt, (0, 0.16 - i * 0.075), (0.28, 0.055), fn, text_scale=1.2)
            self.buttons.append(b)
        self.hint = Text(parent=self, text="WASD move  -  Right mouse: look  -  1-5 abilities  -  Tab: target  -  F / right-click: interact",
                         origin=(0, 0), y=-0.45, scale=0.85, color=color.rgb(0.9, 0.85, 0.75))

    def show(self) -> None:
        super().show()
        has = savefile.latest() is not None
        for b in (self.buttons[1], self.buttons[2]):
            b.ignore_input = not has
            b.collision = has
            if b.text_entity:
                b.text_entity.color = GOLD if has else color.rgb(0.45, 0.42, 0.38)

    def _continue(self) -> None:
        latest = savefile.latest()
        if latest:
            self.game.load_game(latest[1])

    def _quit(self) -> None:
        from ursina import application
        application.quit()


class CharacterCreation(MenuScreen):
    """Race + class selection with a live 3D preview and a name field."""

    def __init__(self, game, ui) -> None:
        super().__init__(game, 0.0)
        self.ui = ui
        self.race = "orc"
        self.cls = "warrior"
        ar = window.aspect_ratio
        self.lpanel = Panel(self, (-ar / 2 + 0.3, 0.0), (0.52, 0.86), title="Create your hero")
        lp = self.lpanel
        label(lp, "Race", (lp.left + 0.03, lp.top - 0.07), 1.1, GOLD)
        self.race_btns = {}
        for i, (rid, name) in enumerate((("orc", "Orc"), ("troll", "Troll"))):
            b = make_button(lp, name, (lp.left + 0.1 + i * 0.16, lp.top - 0.12), (0.14, 0.045), lambda r=rid: self.set_race(r))
            self.race_btns[rid] = b
        self.race_text = Text(parent=lp, text="", origin=(-0.5, 0.5), position=(lp.left + 0.03, lp.top - 0.16, -0.02),
                              scale=0.8, color=TEXT)
        label(lp, "Class", (lp.left + 0.03, lp.top - 0.33), 1.1, GOLD)
        self.cls_btns = {}
        for i, cid in enumerate(("warrior", "hunter", "shaman")):
            b = make_button(lp, data.classes()[cid]["name"], (lp.left + 0.09 + i * 0.155, lp.top - 0.38), (0.14, 0.045),
                            lambda c=cid: self.set_class(c))
            self.cls_btns[cid] = b
        self.cls_text = Text(parent=lp, text="", origin=(-0.5, 0.5), position=(lp.left + 0.03, lp.top - 0.42, -0.02),
                             scale=0.8, color=TEXT)
        label(lp, "Name", (lp.left + 0.03, -lp.size[1] / 2 + 0.17), 1.1, GOLD)
        self.name_field = InputField(parent=lp, default_value="", max_lines=1, character_limit=16,
                                     position=(0, -lp.size[1] / 2 + 0.115, -0.02), scale=(0.42, 0.045))
        self.create_btn = make_button(lp, "Create", (0.1, -lp.size[1] / 2 + 0.045), (0.18, 0.05), self._create, text_scale=1.1)
        self.back_btn = make_button(lp, "Back", (-0.12, -lp.size[1] / 2 + 0.045), (0.14, 0.05), self._back)
        self.preview = None
        self._spin = 0.0

    def show(self) -> None:
        super().show()
        self.set_race(self.race)
        self.set_class(self.cls)
        self.game.ui_capture_keys = True

    def hide(self) -> None:
        super().hide()
        self.game.ui_capture_keys = False
        if self.preview is not None:
            self.preview.destroy()
            self.preview = None
        self.game.cam_override = None

    def _highlight(self) -> None:
        for rid, b in self.race_btns.items():
            b.color = color.rgba(0.6, 0.32, 0.1, 1) if rid == self.race else color.rgba(0.32, 0.18, 0.08, 1)
        for cid, b in self.cls_btns.items():
            b.color = color.rgba(0.6, 0.32, 0.1, 1) if cid == self.cls else color.rgba(0.32, 0.18, 0.08, 1)

    def set_race(self, r: str) -> None:
        self.race = r
        txt = {
            "orc": "Orcs of the Ashfang clan are born in a walled canyon and tested young. Broad, tusked and stubborn, they "
                   "start in Ashfang Hollow.",
            "troll": "The tide-born Saltroot tribe crossed the grey sea in hollow boats. Tall, blue-skinned and spirit-wise, "
                     "they start on the Saltroot Isles.",
        }[r]
        self.race_text.text = txt
        self.race_text.wordwrap = 44
        if not self.name_field.text:
            self.name_field.text = {"orc": "Urzag", "troll": "Zanwe"}[r]
        self._highlight()
        self._rebuild_preview()

    def set_class(self, c: str) -> None:
        self.cls = c
        d = data.classes()[c]
        res = "Rage" if d["resource"] == "rage" else "Mana"
        self.cls_text.text = f"{d['description']}\nResource: {res}.  Primary stats: " + {
            "warrior": "Strength and Stamina.", "hunter": "Agility.", "shaman": "Intellect and Stamina."}[c]
        self.cls_text.wordwrap = 44
        self._highlight()
        self._rebuild_preview()

    def _rebuild_preview(self) -> None:
        from items import item as I
        from npcs.models import build_humanoid
        from player.player import RACE_LOOKS, WEAPON_MODEL
        if self.preview is not None:
            self.preview.destroy()
        look = dict(RACE_LOOKS[self.race])
        cd = data.classes()[self.cls]
        look.update(cd.get("look", {}))
        gear = cd["starting_gear"]
        ch = I.get(gear["chest"])
        look["chest_style"] = ch.get("style", "vest")
        look["shirt"] = tuple(ch["color"])
        look["pants"] = tuple(I.get(gear["legs"])["color"])
        look["boots"] = tuple(I.get(gear["boots"])["color"])
        w = I.get(gear["weapon"])
        look["weapon"] = WEAPON_MODEL.get(w["weapon_type"])
        look["weapon_color"] = tuple(w["color"])
        self.preview = build_humanoid(look)
        self.preview.root.reparentTo(self.game.world.actors)
        self.preview.root.setShaderInput("u_rim", 0.5)
        self._place()

    def _place(self) -> None:
        from panda3d.core import Vec3
        g = self.game
        x, z = -6.0, -90.0
        y = g.world.ground(x, z)
        self.preview.root.setPos(x, y, z)
        h = self.preview.height
        cam = Vec3(x + 1.6, y + h * 0.62, z + 6.2)
        g.cam_override = (cam, Vec3(x + 1.6, y + h * 0.48, z))

    def update(self) -> None:
        if self.preview is None:
            return
        from ursina import time
        from core.util import set_yaw
        self._spin += time.dt * 25
        set_yaw(self.preview.root, math.sin(self._spin * 0.03) * 35)
        self.preview.update(time.dt, 0.0)
        if self.game.cam_override is None:
            self._place()
        from ursina import camera as cam
        cam.setPos(self.game.cam_override[0])
        from panda3d.core import Vec3
        cam.lookAt(self.game.cam_override[1], Vec3(0, 1, 0))

    def _create(self) -> None:
        name = (self.name_field.text or "").strip() or {"orc": "Urzag", "troll": "Zanwe"}[self.race]
        name = "".join(ch for ch in name if ch.isalnum() or ch in " -'")[:16].strip() or "Hero"
        self.hide()
        self.game.new_game(self.race, self.cls, name.title())

    def _back(self) -> None:
        self.hide()
        self.ui.main.show()


class LoadMenu(MenuScreen):
    ROWS = 8

    def __init__(self, game, ui) -> None:
        super().__init__(game, 0.35)
        self.ui = ui
        self.panel = Panel(self, (0, 0.0), (0.9, 0.7), title="Load Game", on_close=self._back)
        self.rows: list[tuple[Button, Button]] = []
        for i in range(self.ROWS):
            y = self.panel.top - 0.1 - i * 0.065
            b = make_button(self.panel, "", (-0.07, y), (0.68, 0.052), lambda i=i: self._load(i), text_scale=0.9)
            d = make_button(self.panel, "Delete", (0.37, y), (0.1, 0.045), lambda i=i: self._delete(i),
                            col=color.rgba(0.35, 0.1, 0.08, 1), text_scale=0.8)
            self.rows.append((b, d))
        self.back_btn = make_button(self.panel, "Back", (0, -self.panel.size[1] / 2 + 0.045), (0.16, 0.05), self._back)
        self.saves: list = []
        self.return_to: Any = None

    def show(self, return_to: Any = None) -> None:
        super().show()
        self.return_to = return_to
        self.saves = savefile.list_saves()
        for i, (b, d) in enumerate(self.rows):
            if i < len(self.saves):
                b.enabled = d.enabled = True
                b.text = savefile.describe(self.saves[i][1])
            else:
                b.enabled = d.enabled = False

    def _load(self, i: int) -> None:
        if i < len(self.saves):
            self.hide()
            self.ui.pause.hide()
            self.game.load_game(self.saves[i][1])

    def _delete(self, i: int) -> None:
        if i < len(self.saves):
            savefile.delete(self.saves[i][0])
            self.show(self.return_to)

    def _back(self) -> None:
        self.hide()
        (self.return_to or self.ui.main).show()


class SettingsMenu(MenuScreen):
    def __init__(self, game, ui) -> None:
        super().__init__(game, 0.35)
        self.ui = ui
        self.panel = Panel(self, (0, 0.0), (0.7, 0.8), title="Settings", on_close=self._back)
        p = self.panel
        s = user_settings
        self.return_to: Any = None
        y0 = p.top - 0.1
        self.sliders: dict[str, Slider] = {}
        specs = [("mouse_sensitivity", "Mouse sensitivity", 0.2, 3.0, 0.05), ("master_volume", "Master volume", 0.0, 1.0, 0.05),
                 ("sfx_volume", "Effects volume", 0.0, 1.0, 0.05), ("ambient_volume", "Ambience volume", 0.0, 1.0, 0.05),
                 ("view_distance", "View distance", 140.0, 380.0, 10.0)]
        for i, (key, text, lo, hi, step) in enumerate(specs):
            y = y0 - i * 0.07
            label(p, text, (p.left + 0.04, y + 0.012), 0.9, TEXT)
            sl = Slider(lo, hi, default=getattr(s, key), step=step, parent=p, x=-0.02, y=y, z=-0.02, scale=0.55,
                        dynamic=True)
            sl.on_value_changed = lambda k=key, sl=sl: self._set(k, sl.value)
            self.sliders[key] = sl
        y = y0 - len(specs) * 0.07 - 0.02
        self.toggles: dict[str, Button] = {}
        for i, (key, text) in enumerate((("fullscreen", "Fullscreen"), ("heat_haze", "Heat haze"), ("show_fps", "Show FPS"),
                                         ("invert_y", "Invert mouse Y"))):
            yy = y - i * 0.055
            label(p, text, (p.left + 0.04, yy + 0.012), 0.9, TEXT)
            b = make_button(p, "", (0.12, yy), (0.14, 0.042), lambda k=key: self._toggle(k), text_scale=0.9)
            self.toggles[key] = b
        yy = y - 4 * 0.055
        label(p, "Resolution", (p.left + 0.04, yy + 0.012), 0.9, TEXT)
        self.res_btn = make_button(p, "", (0.12, yy), (0.2, 0.042), self._cycle_res, text_scale=0.9)
        self.done = make_button(p, "Done", (0, -p.size[1] / 2 + 0.045), (0.16, 0.05), self._back)
        self.note = label(p, "Settings are saved automatically.", (0, -p.size[1] / 2 + 0.095), 0.75, DIM, origin=(0, 0))

    def show(self, return_to: Any = None) -> None:
        super().show()
        self.return_to = return_to
        s = user_settings
        for k, sl in self.sliders.items():
            sl.value = getattr(s, k)
        self._refresh()

    def _refresh(self) -> None:
        s = user_settings
        for k, b in self.toggles.items():
            b.text = "On" if getattr(s, k) else "Off"
        self.res_btn.text = f"{s.resolution[0]} x {s.resolution[1]}"

    def _set(self, key: str, value: float) -> None:
        setattr(user_settings, key, float(value))
        if key == "view_distance":
            self.game.apply_view_distance()
        user_settings.save()

    def _toggle(self, key: str) -> None:
        setattr(user_settings, key, not getattr(user_settings, key))
        self.game.apply_settings(key)
        user_settings.save()
        self._refresh()

    def _cycle_res(self) -> None:
        cur = tuple(user_settings.resolution)
        opts = list(RESOLUTIONS)
        i = opts.index(cur) if cur in opts else 0
        user_settings.resolution = list(opts[(i + 1) % len(opts)])
        self.game.apply_settings("resolution")
        user_settings.save()
        self._refresh()

    def _back(self) -> None:
        self.hide()
        user_settings.save()
        if self.return_to is not None:
            self.return_to.show()


class PauseMenu(MenuScreen):
    def __init__(self, game, ui) -> None:
        super().__init__(game, 0.45)
        self.ui = ui
        self.panel = Panel(self, (0, 0.0), (0.36, 0.52), title="Paused")
        items = [("Resume", self.resume), ("Save Game", self._save), ("Load Game", lambda: self._sub(ui.load)),
                 ("Settings", lambda: self._sub(ui.settings)), ("Main Menu", self._main), ("Quit Game", self._quit)]
        for i, (txt, fn) in enumerate(items):
            make_button(self.panel, txt, (0, 0.15 - i * 0.065), (0.26, 0.05), fn, text_scale=1.05)
        self.status = label(self.panel, "", (0, -self.panel.size[1] / 2 + 0.03), 0.8, GOLD, origin=(0, 0))

    def show(self) -> None:
        super().show()
        self.status.text = ""
        self.game.paused = True

    def hide(self) -> None:
        super().hide()
        self.game.paused = False

    def resume(self) -> None:
        self.hide()

    def _sub(self, menu: Any) -> None:
        super().hide()
        menu.show(return_to=self)

    def _save(self) -> None:
        path = self.game.save()
        self.status.text = f"Saved to saves/{path.name}" if path else "Could not save."

    def _main(self) -> None:
        self.game.save()
        self.hide()
        self.game.return_to_menu()

    def _quit(self) -> None:
        self.game.save()
        from ursina import application
        application.quit()


class VictoryPanel(MenuScreen):
    def __init__(self, game, ui) -> None:
        super().__init__(game, 0.3)
        self.ui = ui
        self.panel = Panel(self, (0, 0.05), (0.76, 0.5))
        self.title = label(self.panel, "Victory!", (0, 0.17), 3.2, GOLD, origin=(0, 0))
        self.text = Text(parent=self.panel, text="", origin=(0, 0.5), y=0.1, z=-0.02, scale=1.0, color=TEXT)
        make_button(self.panel, "Keep exploring", (-0.14, -0.19), (0.24, 0.05), self.hide, text_scale=1.0)
        make_button(self.panel, "Main Menu", (0.14, -0.19), (0.24, 0.05), self._main, text_scale=1.0)

    def show_victory(self) -> None:
        g = self.game
        p = g.player
        mins = int(g.play_time // 60)
        self.text.text = ("Warlord Rukhar Cinderjaw is defeated and the Ironmaw Gate\n"
                          "belongs to the clans once more.\n\n"
                          f"{p.name}, Level {p.level} {p.race.title()} {p.cls_def['name']}\n"
                          f"Quests completed: {len(g.quests.done)}     Gold: {p.inventory.gold}     Time: {mins} min")
        self.show()
        self.game.paused = False

    def _main(self) -> None:
        self.hide()
        self.game.save()
        self.game.return_to_menu()


class MenuController:
    """Owns all menus and routes Esc between them."""

    def __init__(self, game) -> None:
        self.game = game
        self.main = MainMenu(game, self)
        self.creation = CharacterCreation(game, self)
        self.load = LoadMenu(game, self)
        self.settings = SettingsMenu(game, self)
        self.pause = PauseMenu(game, self)
        self.victory = VictoryPanel(game, self)
        events.on("toggle_menu", lambda **_: self.toggle_pause())

    def open_creation(self) -> None:
        self.main.hide()
        self.creation.show()

    def open_load(self) -> None:
        self.main.hide()
        self.load.show(return_to=self.main)

    def open_settings(self, return_to: Any) -> None:
        return_to.hide()
        self.settings.show(return_to=return_to)

    def any_open(self) -> bool:
        return any(m.enabled for m in (self.main, self.creation, self.load, self.settings, self.pause, self.victory))

    def toggle_pause(self) -> None:
        if self.game.state not in ("playing", "dead"):
            return
        if self.settings.enabled:
            self.settings._back()
        elif self.load.enabled:
            self.load._back()
        elif self.pause.enabled:
            self.pause.hide()
        elif self.victory.enabled:
            self.victory.hide()
        else:
            self.pause.show()

    def escape(self) -> bool:
        if self.game.state == "menu":
            if self.settings.enabled:
                self.settings._back()
                return True
            if self.load.enabled:
                self.load._back()
                return True
            if self.creation.enabled:
                self.creation._back()
                return True
            return False
        self.toggle_pause()
        return True
