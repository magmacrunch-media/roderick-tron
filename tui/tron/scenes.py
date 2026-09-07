"""The screens, as scenes.

Modality is the stack, not a flag — the engine's own rule. :class:`TitleScene`
sits at the bottom; starting a run pushes a :class:`GameScene` on top of it,
and Esc pops back.

── Where the input actually lands ──

``TuiInput``'s docstring draws the line this cabinet lives on: decay semantics
suit a *held direction*, and edges suit a control whose exact moment of
pressing is the game. A platformer needs both at once, and it needs them to
not fight.

Walking is the held one, and reads through ``is_pressed``. Jumping, rolling
and firing are edges, collected in :meth:`GameScene.handle_key` and spent on
the next update — one press, one action.

The trap is that the two requirements disagree about ``hold_ms``. A keyboard
goes silent for its repeat delay after the first press, so a short latch
leaves a gap in the middle of a held key and a long one leaves a tail after a
real release. This cabinet takes the short latch, because over a pit a tail is
fatal and a stutter is only ugly, and pays for it in
:data:`tron.config.CHARGE_GRACE_FRAMES` — the earned-speed ramp rides out the
gap even though the movement does not. That split is the whole reason the
constant exists, and it is argued in full there.
"""

from __future__ import annotations

import textwrap
from dataclasses import replace

from magmacrunch.engine.ui import bigtext
from magmacrunch.engine.ui.menu import Menu
from magmacrunch.engine.ui.theme import DEFAULT_THEME

from tron import cells, theme
from tron import config as C
from tron.entities import Entities
from tron.levels import LEVELS
from tron.player import Intent, Player
from tron.tilemap import Tilemap

MENU_HELP = "↑↓ choose    Enter select    Q quit"
ARCADE_HELP = "Esc  back to the arcade"
#: Two spaces between hints where other lines use four: seven hints do not fit
#: the 60-column floor otherwise, and ``_fit`` truncates from the right without
#: saying so — the hint that goes missing would be how to get out.
GAME_HELP = "←→ walk  SPACE jump  X roll  Z note  P pause  Esc title"
PAUSE_HELP = "P resume    R restart    Esc title    Q quit"
RULES_HELP = "↑↓ scroll    any other key goes back"
INITIALS_HELP = "Enter confirms    Backspace fixes"
SCORES_HELP = "any key goes back"

#: What the ported constants are measured in.
#:
#: **The one unit conversion in the game, and it belongs at exactly one line.**
#: Every rate in :mod:`tron.config` is "units per 60fps frame" and is
#: multiplied by dt at the point of use — the web build's convention, and what
#: makes the simulation frame-rate independent and comparable against the
#: shipped JavaScript. The engine's loop measures dt in *seconds*, so handing
#: it straight to the simulation runs the game about sixty times too slow.
#: Jovian shipped that bug and fixed it with this same line.
FRAMES_PER_SECOND = C.FRAMES_PER_SECOND

RULES = (
    ("THE ROOFTOPS", (
        "Roderick Tron is a clockwork gentleman crossing the rooftops of an "
        "1810s Dutch city. Reach the door at the far end of each of three "
        "levels.",
        "Falling off the bottom costs a life, and so does walking into "
        "anything with teeth. The canal is fatal outright.",
    )),
    ("MOVING", (
        "Hold a direction and he builds speed. A walk clears three tiles, a "
        "run nearly six — but the run has to be earned, so a long gap needs a "
        "run-up rather than a decision.",
        "Rolling is the skill move. It carries more speed than a run, it "
        "tucks him into a one-tile gap, and it kills anything soft it touches "
        "— but it commits, so you have to mean it. The widest gap in the game "
        "is seven tiles, and only a roll crosses it.",
        "Every jump is full height. A chimney draught is how a level reaches "
        "upward, and a bell cannon fires you along whatever angle it is "
        "pointing when you press jump.",
    )),
    ("THE ROOFTOP MENAGERIE", (
        "Gargoyles walk and can be stomped. Flyers bob. Statues are too heavy "
        "to flatten — a stomp bounces off one, and it takes three notes.",
        "Notes are ammunition and points both, so exploring for them and "
        "fighting are the same activity. A hundred buys a life.",
        "The clockwork bird is one free hit. Losing it is visible and "
        "recoverable; losing a life is neither.",
    )),
    ("THE COAL RUN", (
        "Board a trolley and it takes over. It rolls at a fixed speed and "
        "jump is the only thing you still control, which is the point: a cart "
        "you could slow down is a cart you could wait out.",
    )),
)


def _fit(text: str, width: int) -> str:
    if width <= 1 or len(text) <= width:
        return text
    return text[: width - 1] + "…"


def _too_small(renderer, cols: int, rows: int) -> bool:
    """Say so rather than drawing a clipped screen.

    Naming the numbers matters more here than in the other cabinets: 60 columns
    is the widest floor in the arcade, and a player told only "too small" has
    no idea it is the width rather than the height.
    """
    if renderer.width >= cols and renderer.height >= rows:
        return False
    renderer.ui_text(1, 1, "TERMINAL TOO SMALL", fill=theme.WARN)
    renderer.ui_text(
        1, 2,
        f"need {cols}x{rows}, have {renderer.width}x{renderer.height}",
        fill=theme.HUD_DIM,
    )
    return True


def _menu_theme():
    return replace(
        DEFAULT_THEME,
        primary=theme.MENU_SELECTED,
        text=theme.HUD_TEXT,
        dim_text=theme.HUD_DIM,
        box_fill=theme.MENU_BOX,
        box_outline=theme.GABLE_STONE,
        outline_width=1,
        selection_fill=theme.MENU_SELECTION_BG,
    )


def _draw_title(renderer, cx: int, box_top: int) -> int:
    """The name, set as large as the window allows. Returns the row below it."""
    budget = box_top - 1
    for big, rest in theme.TITLE_LADDER:
        needed = bigtext.height(big) + (1 if rest else 0)
        if bigtext.width(big) > renderer.width - 2 or needed > budget:
            continue
        y = 1
        for line in bigtext.lines(big):
            renderer.ui_text(cx, y, line, fill=theme.TITLE, anchor="n")
            y += 1
        if rest:
            renderer.ui_text(cx, y, rest, fill=theme.SUBTITLE, anchor="n")
            y += 1
        return y
    renderer.ui_text(cx, 1, theme.BANNER, fill=theme.TITLE, anchor="n")
    return 2


class TitleScene:
    """The bottom of the stack. Everything else is pushed over it."""

    ITEMS = ("PLAY", "HOW TO PLAY", "HIGH SCORES", "QUIT")

    def __init__(self, app):
        self.app = app
        self.menu = Menu(
            app.renderer,
            theme=_menu_theme(),
            menu_width=theme.MENU_W,
            item_height=theme.MENU_ITEM_H,
            title_height=theme.MENU_TITLE_H,
            item_padding=theme.MENU_PAD,
            border_pad=theme.MENU_BORDER,
            selected_color=theme.MENU_SELECTED,
            normal_color=theme.HUD_TEXT,
        )
        self._show()

    def _show(self) -> None:
        self.menu.show(list(self.ITEMS), on_select=self._chose)

    def _chose(self, index: int, label: str) -> None:  # noqa: ARG002
        if index == 0:
            self.app.start_run()
        elif index == 1:
            self.app.show_rules()
        elif index == 2:
            self.app.show_scores()
        else:
            self.app.leave()

    def on_resume(self) -> None:
        self._show()

    def handle_key(self, key: str) -> bool:
        if key in ("up", "k"):
            self.menu.move_up()
        elif key in ("down", "j"):
            self.menu.move_down()
        elif key in ("enter", "space"):
            self.menu.confirm()
        elif key == "q" or key == "escape" and self.app.host.seated:
            self.app.leave()
        else:
            return False
        return True

    def update(self, dt: float) -> None:
        pass

    def render(self) -> None:
        r = self.app.renderer
        r.clear()
        r.draw_rect(0, 0, r.width, r.height, theme.SKY)
        if _too_small(r, theme.MENU_MIN_COLS, theme.MENU_MIN_ROWS):
            r.present()
            return

        cx = r.width // 2
        box_top = self._menu_box_top(r)
        y = _draw_title(r, cx, box_top)
        if y < box_top:
            r.ui_text(cx, y, _fit(theme.TAGLINE, r.width - 2),
                      fill=theme.HUD_DIM, anchor="n")

        self.menu.render()

        if self.app.best:
            r.ui_text(cx, r.height - 3, f"best: {self.app.best}",
                      fill=theme.HUD_DIM, anchor="n")
        r.ui_text(cx, r.height - 2, _fit(MENU_HELP, r.width - 2),
                  fill=theme.HUD_DIM, anchor="n")
        if self.app.host.seated:
            r.ui_text(cx, r.height - 1, _fit(ARCADE_HELP, r.width - 2),
                      fill=theme.HUD_DIM, anchor="n")
        r.present()

    def _menu_box_top(self, renderer) -> int:
        rows = len(self.ITEMS) * theme.MENU_ITEM_H + theme.MENU_PAD * 2
        return max(0, (renderer.height - rows) // 2)


class RulesScene:
    """The rules, scrolling, because they are longer than a terminal is tall."""

    def __init__(self, app):
        self.app = app
        self.offset = 0

    def _lines(self, width: int) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for heading, paragraphs in RULES:
            out.append((heading, theme.TITLE))
            for para in paragraphs:
                for line in textwrap.wrap(para, max(20, width - 4)):
                    out.append((line, theme.HUD_TEXT))
                out.append(("", theme.HUD_TEXT))
        return out

    def _viewport(self) -> int:
        return max(1, self.app.renderer.height - 4)

    def _max_offset(self, width: int) -> int:
        return max(0, len(self._lines(width)) - self._viewport())

    def handle_key(self, key: str) -> bool:
        width = self.app.renderer.width
        if key in ("up", "k"):
            self.offset = max(0, self.offset - 1)
        elif key in ("down", "j"):
            self.offset = min(self._max_offset(width), self.offset + 1)
        else:
            self.app.host.pop_scene()
        return True

    def update(self, dt: float) -> None:
        pass

    def render(self) -> None:
        r = self.app.renderer
        r.clear()
        r.draw_rect(0, 0, r.width, r.height, theme.SKY)
        if _too_small(r, theme.MENU_MIN_COLS, theme.MENU_MIN_ROWS):
            r.present()
            return

        r.ui_text(r.width // 2, 0, "HOW TO PLAY", fill=theme.TITLE, anchor="n")
        lines = self._lines(r.width)
        top = min(self.offset, self._max_offset(r.width))
        for i, (text, fill) in enumerate(lines[top:top + self._viewport()]):
            r.ui_text(2, 2 + i, _fit(text, r.width - 3), fill=fill)

        r.ui_text(r.width // 2, r.height - 1, _fit(RULES_HELP, r.width - 2),
                  fill=theme.HUD_DIM, anchor="n")
        r.present()


class InitialsScene:
    """Three letters, the way an arcade has always asked for them."""

    def __init__(self, app, score: int):
        self.app = app
        self.score = score
        self.letters = list(app.initials)

    def handle_key(self, key: str) -> bool:
        if key == "enter":
            self.app.record(self.score, "".join(self.letters))
            self.app.host.pop_scene()
        elif key == "backspace":
            if self.letters:
                self.letters.pop()
        elif len(key) == 1 and key.isalnum() and len(self.letters) < 3:
            self.letters.append(key.upper())
        else:
            return False
        return True

    def update(self, dt: float) -> None:
        pass

    def render(self) -> None:
        r = self.app.renderer
        r.clear()
        r.draw_rect(0, 0, r.width, r.height, theme.SKY)
        cx, cy = r.width // 2, r.height // 2
        r.ui_text(cx, cy - 3, "A NEW BEST", fill=theme.TITLE, anchor="n")
        r.ui_text(cx, cy - 1, f"{self.score}", fill=theme.HUD_TEXT, anchor="n")
        shown = "".join(self.letters).ljust(3, "_")
        r.ui_text(cx, cy + 1, " ".join(shown), fill=theme.ROBOT_CYAN, anchor="n")
        r.ui_text(cx, r.height - 1, _fit(INITIALS_HELP, r.width - 2),
                  fill=theme.HUD_DIM, anchor="n")
        r.present()


class ScoresScene:
    """The local board."""

    def __init__(self, app):
        self.app = app

    def _viewport(self) -> int:
        return max(1, self.app.renderer.height - 4)

    def handle_key(self, key: str) -> bool:  # noqa: ARG002
        self.app.host.pop_scene()
        return True

    def update(self, dt: float) -> None:
        pass

    def render(self) -> None:
        r = self.app.renderer
        r.clear()
        r.draw_rect(0, 0, r.width, r.height, theme.SKY)
        r.ui_text(r.width // 2, 0, "HIGH SCORES", fill=theme.TITLE, anchor="n")

        entries = self.app.scores.entries()[: self._viewport()]
        if not entries:
            r.ui_text(r.width // 2, 3, "no runs yet", fill=theme.HUD_DIM,
                      anchor="n")
        for i, entry in enumerate(entries):
            rank = f"{i + 1:>2}."
            name = getattr(entry, "initials", getattr(entry, "name", "???"))
            value = getattr(entry, "score", 0)
            fill = (
                theme.MENU_SELECTED
                if self.app.last_rank == i + 1
                else theme.HUD_TEXT
            )
            r.ui_text(2, 2 + i, f"{rank} {name:<4} {value:>8}", fill=fill)

        r.ui_text(r.width // 2, r.height - 1, _fit(SCORES_HELP, r.width - 2),
                  fill=theme.HUD_DIM, anchor="n")
        r.present()


class GameScene:
    """The rooftops."""

    def __init__(self, app):
        self.app = app
        self.level_index = 0
        self.score = 0
        self.paused = False
        self.banner = ""
        self.banner_frames = 0.0
        self._jump = False
        self._roll = False
        self._fire = False
        self._load(0)

    # ── Setting up ──────────────────────────────────────────────────

    def _load(self, index: int) -> None:
        self.level_index = index
        self.map = Tilemap(LEVELS[index])
        self.player = Player(self.map)
        self.entities = Entities(self.map, self.app.rng)
        self.camera = cells.Camera(self.map)
        self._resize_camera()
        self.camera.snap_to(self.player)
        self._say(self.map.name)

    def _resize_camera(self) -> None:
        r = self.app.renderer
        rows = max(1, r.height - theme.HEADER_ROWS - theme.FOOTER_ROWS)
        self.camera.resize(*cells.playfield_size(r.width, rows))

    def restart(self) -> None:
        keep = self.player.lives if hasattr(self, "player") else C.MAX_LIVES
        self._load(self.level_index)
        self.player.lives = keep

    def _say(self, text: str) -> None:
        self.banner = text
        self.banner_frames = 90.0

    def on_enter(self) -> None:
        self.app.host.input.clear()

    # ── Flow ────────────────────────────────────────────────────────

    def _toggle_pause(self) -> None:
        self.paused = not self.paused
        self.app.host.input.clear()

    def _die(self) -> None:
        # Read the count *before* reloading. _load builds a fresh Player, which
        # starts at MAX_LIVES -- so decrementing self.player and then reloading
        # throws the decrement away and the run never ends.
        remaining = self.player.lives - 1
        if remaining <= 0:
            self.player.lives = 0
            self._end()
            return
        self._load(self.level_index)
        self.player.lives = remaining
        self._say("TRY AGAIN")

    def _advance(self) -> None:
        self.score += C.EXIT_POINTS
        if self.level_index + 1 < len(LEVELS):
            lives = self.player.lives
            self._load(self.level_index + 1)
            self.player.lives = lives
        else:
            self._end()

    def _end(self) -> None:
        if self.app.qualifies(self.score):
            self.app.enter_initials(self.score)
        else:
            self.app.record(self.score)
            self.app.to_title()

    # ── Per-frame ───────────────────────────────────────────────────

    def _intent(self) -> Intent:
        """One frame of input, with the edges spent as they are read."""
        source = self.app.host.input
        intent = Intent(
            left=bool(source.is_pressed("left")),
            right=bool(source.is_pressed("right")),
            down=bool(source.is_pressed("down")),
            jump=self._jump,
            roll=self._roll,
            fire=self._fire,
        )
        self._jump = self._roll = self._fire = False
        return intent

    def update(self, dt: float) -> None:
        if self.paused:
            return
        # Seconds to 60fps frames, once, here. See FRAMES_PER_SECOND above.
        step = dt * FRAMES_PER_SECOND
        if self.banner_frames > 0:
            self.banner_frames -= step

        intent = self._intent()
        if intent.fire and self.player.can_shoot():
            self.entities.fire(self.player)
            self.player.spend_shot()

        self.player.update(intent, step)
        self.entities.update(self.player, intent, step)
        self._score_events()

        if self.map.exit is not None and not self.player.exiting:
            e = self.map.exit
            b = self.player.box
            across = b.x < e.x + e.w and b.x + b.w > e.x
            if across and b.y < e.y + e.h and b.y + b.h > e.y:
                self.player.exiting = True
                self._advance()
                return

        fatal = self.player.box.y > self.map.h + C.FALL_KILL_MARGIN
        if not fatal and self.map.overlaps_water(
            self.player.box.x, self.player.box.y,
            self.player.box.w, self.player.box.h,
        ):
            fatal = True
        if fatal:
            self._die()
            return

        self._resize_camera()
        self.camera.update(self.player, step)

    def _score_events(self) -> None:
        for ev in self.entities.events:
            kind = ev["type"]
            if kind == "note":
                self.score += C.NOTE_POINTS
                if self.player.collect(1):
                    self._say("EXTRA LIFE")
            elif kind == "letter":
                self.score += C.LETTER_POINTS
            elif kind == "kill":
                self.score += C.KILL_POINTS
            elif kind == "hurt":
                lost = self.player.hurt(ev["x"])
                if lost == "bird":
                    self._say("THE BIRD IS GONE")
                elif lost == "life" and self.player.lives <= 0:
                    self._end()
                    return

    # ── Input ───────────────────────────────────────────────────────

    def handle_key(self, key: str) -> bool:
        if key == "p":
            self._toggle_pause()
        elif key == "escape":
            self.app.to_title()
        elif key == "q":
            self.app.host.quit()
        elif key == "r":
            self.restart()
        elif self.paused:
            return False
        elif key in ("space", "up", "w"):
            self._jump = True
        elif key == "x":
            self._roll = True
        elif key == "z":
            self._fire = True
        else:
            return False
        return True

    # ── Drawing ─────────────────────────────────────────────────────

    def render(self) -> None:
        r = self.app.renderer
        r.clear()
        r.draw_rect(0, 0, r.width, r.height, theme.SKY)
        if _too_small(r, theme.MIN_COLS, theme.MIN_ROWS):
            r.present()
            return

        top = theme.HEADER_ROWS
        rows = r.height - theme.HEADER_ROWS - theme.FOOTER_ROWS

        self._draw_terrain(r, top, rows)
        self._draw_pickups(r, top, rows)
        self._draw_exit(r, top, rows)
        self._draw_entities(r, top, rows)
        self._draw_player(r, top, rows)
        self._draw_header(r)
        self._draw_footer(r)
        if self.banner_frames > 0:
            self._banner(r, self.banner, theme.TITLE)
        if self.paused:
            self._banner(r, "PAUSED", theme.ROBOT_CYAN)
        r.present()

    def _cell(self, x: float, y: float, top: int, rows: int):
        """A world point as a (col, row) on screen, or None if off it."""
        col, row = self.camera.to_cell(x, y)
        if col < 0 or col >= self.app.renderer.width:
            return None
        if row < 0 or row >= rows:
            return None
        return col, top + row

    def _draw_terrain(self, r, top: int, rows: int) -> None:
        tx0, ty0, tx1, ty1 = self.camera.tile_window(r.width, rows)
        glyphs = {
            "#": (theme.SOLID * cells.CELLS_PER_TILE, theme.BRICK),
            "=": (theme.PLATFORM * cells.CELLS_PER_TILE, theme.ROOF_TILE),
            "-": (theme.RAIL * cells.CELLS_PER_TILE, theme.RAIL_IRON),
            "~": (theme.WATER * cells.CELLS_PER_TILE, theme.CANAL),
            "^": (theme.UPDRAFT_GLYPH * cells.CELLS_PER_TILE, theme.UPDRAFT),
        }
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                ch = self.map.tile_at(tx, ty)
                art = glyphs.get(ch)
                if art is None:
                    continue
                at = self._cell(tx * C.TILE, ty * C.TILE, top, rows)
                if at is None:
                    continue
                r.ui_text(at[0], at[1], art[0], fill=art[1])

    def _draw_pickups(self, r, top: int, rows: int) -> None:
        for n in self.map.notes:
            if n.taken:
                continue
            at = self._cell(n.x, n.y, top, rows)
            if at:
                r.ui_text(at[0], at[1], theme.NOTE, fill=theme.NOTE_WHITE)
        for letter in self.map.letters:
            if letter.taken:
                continue
            at = self._cell(letter.x, letter.y, top, rows)
            if at:
                r.ui_text(at[0], at[1], letter.ch, fill=theme.LETTER_GOLD)

    def _draw_exit(self, r, top: int, rows: int) -> None:
        e = self.map.exit
        if e is None:
            return
        at = self._cell(e.x, e.y, top, rows)
        if at is None:
            return
        r.ui_text(at[0], at[1], theme.EXIT_TOP, fill=theme.EXIT_GLOW)
        if at[1] + 1 < top + rows:
            r.ui_text(at[0], at[1] + 1, theme.EXIT_BOTTOM, fill=theme.EXIT_GLOW)

    def _draw_entities(self, r, top: int, rows: int) -> None:
        marks = {
            "gargoyle": (theme.GARGOYLE, theme.GARGOYLE_STONE),
            "flyer": (theme.FLYER, theme.FLYER_WING),
            "statue": (theme.STATUE, theme.STATUE_STONE),
        }
        for t in self.entities.trolleys:
            if t.spent:
                continue
            at = self._cell(t.x, t.y, top, rows)
            if at:
                r.ui_text(at[0], at[1], theme.TROLLEY_GLYPH,
                          fill=theme.TROLLEY_BODY)
        for b in self.entities.bells:
            at = self._cell(b.x, b.y, top, rows)
            if at:
                r.ui_text(at[0], at[1], theme.BELL, fill=theme.BELL_BRASS)
        for e in self.entities.enemies:
            art = marks.get(e.kind)
            at = self._cell(e.x, e.y, top, rows)
            if art and at:
                fill = theme.GARGOYLE_EYE if e.flash > 0 else art[1]
                r.ui_text(at[0], at[1], art[0], fill=fill)
        for s in self.entities.shots:
            at = self._cell(s.x, s.y, top, rows)
            if at:
                r.ui_text(at[0], at[1], theme.SHOT, fill=theme.NOTE_WHITE)
        if self.entities.bird is not None:
            at = self._cell(self.entities.bird.x, self.entities.bird.y, top, rows)
            if at:
                r.ui_text(at[0], at[1], theme.BIRD, fill=theme.BIRD_BRASS)

    def _draw_player(self, r, top: int, rows: int) -> None:
        p = self.player
        if not p.alive:
            return
        # Invincibility flashes, the way the web build's draw does.
        if p.invincible > 0 and int(p.invincible / 4) % 2 == 0:
            return
        at = self._cell(p.box.x, p.box.y, top, rows)
        if at is None:
            return
        glyph = theme.PLAYER_ROLLING if p.rolling else theme.PLAYER
        r.ui_text(at[0], at[1], glyph, fill=theme.ROBOT_CYAN)

    def _draw_header(self, r) -> None:
        left = f"{self.map.name}"
        mid = f"SCORE {self.score}"
        lives = theme.LIFE * max(0, self.player.lives)
        r.ui_text(0, 0, _fit(left, r.width // 3), fill=theme.HUD_DIM)
        r.ui_text(r.width // 2, 0, mid, fill=theme.HUD_TEXT, anchor="n")
        r.ui_text(r.width - len(lives) - 1, 0, lives, fill=theme.LIFE_HEART)

    def _draw_footer(self, r) -> None:
        hint = PAUSE_HELP if self.paused else GAME_HELP
        r.ui_text(r.width // 2, r.height - 1, _fit(hint, r.width - 2),
                  fill=theme.HUD_DIM, anchor="n")

    def _banner(self, r, text: str, fill: str) -> None:
        r.ui_text(r.width // 2, r.height // 2, _fit(text, r.width - 2),
                  fill=fill, anchor="n")


__all__ = [
    "GameScene", "InitialsScene", "RulesScene", "ScoresScene", "TitleScene",
]
