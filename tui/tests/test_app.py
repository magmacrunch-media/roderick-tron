"""The screens, driven headlessly.

These cover what the simulation suites cannot: that the rules are wired to the
screen correctly, and that the title and a run hand off to each other. They
need the engine and its terminal extra, and are skipped without them so the
simulation tests still run on a bare checkout.

Textual's ``run_test`` pilot gives a real app with a real event loop and a real
size, so key handling, the frame loop and resize are exercised as they are in
play — no mocking of the parts most likely to break.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("textual", reason='needs: pip install -e ".[dev]"')

from magmacrunch.engine import scores as score_mod  # noqa: E402
from magmacrunch.engine.arcade import ArcadeGame  # noqa: E402
from magmacrunch.engine.core.tui_host import TuiHost  # noqa: E402

from tron import config as C  # noqa: E402
from tron import theme
from tron.app import TronApp  # noqa: E402
from tron.arcade import GAME  # noqa: E402
from tron.scenes import TitleScene  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_scores(tmp_path, monkeypatch):
    """No test may touch a real player's score file."""
    monkeypatch.setenv(score_mod.DATA_DIR_ENV, str(tmp_path))


def buffer_text(app: TronApp) -> str:
    return app.host.game.surface.buffer.to_text()


def settle(app: TronApp) -> None:
    app.host.stack.update(0.0)


def hosted(seed: int = 7) -> TronApp:
    host = TuiHost(title=GAME.info.title, fps=GAME.info.fps,
                   hold_ms=GAME.info.hold_ms)
    app = TronApp(host, seed=seed)
    host.push_scene(app.root_scene)
    settle(app)
    return app


def playing(seed: int = 7):
    app = hosted(seed)
    app.start_run()
    settle(app)
    return app, app.host.scene


async def _piloted(app: TronApp, size=(80, 24)):
    from magmacrunch.engine.core.tui_game import _GameApp

    textual_app = _GameApp(app.host.game, app.host.game.surface)
    app.host.game._app = textual_app
    return textual_app.run_test(size=size)


def run(coro):
    return asyncio.run(coro)


def tap(app: TronApp, key: str) -> None:
    """A keypress the way the host delivers one."""
    app.host.input.press(key)
    for pressed in app.host.input.drain():
        app.host.stack.dispatch_key(pressed)


# ── The declaration ─────────────────────────────────────────────────


def test_the_game_is_a_valid_arcade_cabinet():
    assert isinstance(GAME, ArcadeGame)
    assert GAME.info.key == "roderick-tron"


def test_it_runs_at_sixty_and_says_why():
    """The only cabinet here above 30fps.

    A jump is 33 frames of arc quantised to five cell rows. Sampled at 30 the
    eye gets half the distinct positions, and a platformer is judged on
    whether an arc can be read well enough to land on a tile.
    """
    assert GAME.info.fps == 60


def test_the_input_latch_is_the_short_side_of_the_bind():
    """hold_ms under the repeat delay, deliberately.

    Over the delay a real release leaves nearly six tiles of coasting, which
    over a pit is fatal; under it there is a gap in the middle of a held key,
    which is merely ugly. The gap is survivable only because the earned-speed
    ramp rides it out — see CHARGE_GRACE_FRAMES.
    """
    assert GAME.info.hold_ms == 260
    assert GAME.info.hold_ms / 1000 * 60 < C.CHARGE_GRACE_FRAMES, (
        "the charge must outlast the movement latch, or the gap eats the run"
    )


def test_the_floor_is_the_web_viewport():
    """Sixty columns: thirty tiles, two cells each, so a tile is square."""
    assert GAME.info.min_cols == 60
    assert theme.MIN_COLS == 60


def test_start_returns_a_scene_without_pushing_it():
    host = TuiHost(title="t", fps=GAME.info.fps, hold_ms=GAME.info.hold_ms)
    scene = GAME.start(host)
    assert isinstance(scene, TitleScene)
    assert len(host.stack) == 0


def test_listing_this_game_does_not_drag_in_its_screens():
    """A menu loads one arcade module per installed game just to draw a row."""
    import subprocess
    import sys

    code = (
        "import sys, tron.arcade; "
        "print([m for m in ('tron.scenes', 'tron.app', 'tron.entities', "
        "'textual') if m in sys.modules])"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, check=True)
    assert out.stdout.strip() == "[]", out.stdout


# ── The stack ───────────────────────────────────────────────────────


def test_the_title_is_the_bottom_of_the_stack():
    app = hosted()
    assert isinstance(app.host.scene, TitleScene)
    assert not app.in_game


def test_starting_a_run_pushes_it_over_the_title():
    app, _ = playing()
    assert app.in_game
    assert len(app.host.stack) == 2
    assert isinstance(app.host.stack.scenes[0], TitleScene)


def test_escape_pops_back_to_the_title():
    app, scene = playing()
    scene.handle_key("escape")
    settle(app)
    assert isinstance(app.host.scene, TitleScene)


# ── The two halves of the input seam ────────────────────────────────


def test_walking_reads_held_state():
    """The decay half: holding right moves him right."""
    app, scene = playing()
    start = scene.player.box.x
    app.host.input.press("right")
    for _ in range(20):
        app.host.stack.update(1 / 60)
    assert scene.player.box.x > start


def test_jumping_is_an_edge_and_never_held_state():
    """The other half. Held state cannot produce a jump at all, because a
    terminal cannot tell a held jump from a released one — which is the same
    reason the port has no variable jump height."""
    app, scene = playing()
    app.host.input.press("space")
    for _ in range(10):
        app.host.stack.update(1 / 60)
    assert scene.player.vy >= 0, "held state should never launch a jump"


def test_a_press_jumps_exactly_once():
    app, scene = playing()
    # A few frames first. A freshly built Player has not been updated yet, so
    # it has not landed on anything and coyote is zero; the spawn also sits
    # flush with the floor, and it takes two steps for the body to sink far
    # enough that tile_range's bottom-1 row reaches the tile holding it up.
    for _ in range(4):
        app.host.stack.update(1 / 60)
    assert scene.player.grounded or scene.player.coyote > 0
    tap(app, "space")
    app.host.stack.update(1 / 60)
    assert scene.player.vy < 0, "the press did not become a jump"


def test_a_press_rolls():
    app, scene = playing()
    for _ in range(5):
        app.host.stack.update(1 / 60)
    tap(app, "x")
    app.host.stack.update(1 / 60)
    assert scene.player.rolling


def test_firing_spends_a_note():
    app, scene = playing()
    ammo = scene.player.ammo
    tap(app, "z")
    app.host.stack.update(1 / 60)
    assert len(scene.entities.shots) == 1
    assert scene.player.ammo == ammo - 1


# ── Pause ───────────────────────────────────────────────────────────


def test_p_stops_the_clock():
    app, scene = playing()
    for _ in range(5):
        app.host.stack.update(1 / 60)
    scene.handle_key("p")
    frozen = (scene.player.box.x, scene.player.box.y)
    app.host.input.press("right")
    for _ in range(20):
        app.host.stack.update(1 / 60)
    assert scene.paused
    assert (scene.player.box.x, scene.player.box.y) == frozen


def test_a_pause_cannot_be_used_to_keep_firing():
    app, scene = playing()
    scene.handle_key("p")
    tap(app, "z")
    app.host.stack.update(1 / 60)
    assert scene.entities.shots == []


# ── The unit conversion ─────────────────────────────────────────────


def test_a_second_of_wall_clock_is_sixty_frames_of_game():
    """The engine measures dt in seconds; every ported constant is per 60fps
    frame. Handed straight through, the game runs about sixty times too slow —
    which looks like sluggishness rather than like a bug, and is the mistake
    Jovian shipped before fixing it with the same one-line conversion.

    A free fall is the cleanest probe: distance is 0.5*g*t^2 in frames, and no
    input is involved.
    """
    app, scene = playing()
    scene.player.grounded = False
    scene.player.coyote = 0
    scene.player.box.y = 0
    scene.player.vy = 0
    for _ in range(6):                      # a tenth of a second
        app.host.stack.update(1 / 60)
    frames = 6
    expected = 0.5 * C.GRAVITY * frames * frames
    assert scene.player.box.y == pytest.approx(expected, rel=0.3), (
        "a tenth of a second of wall clock should be six frames of gravity"
    )


# ── Lives ───────────────────────────────────────────────────────────


def test_falling_off_the_bottom_costs_a_life():
    """And the count survives the level reload, which it did not at first:
    _load builds a fresh Player at MAX_LIVES, so decrementing the old one and
    then reloading threw the decrement away and the run could never end."""
    app, scene = playing()
    lives = scene.player.lives
    scene.player.box.y = scene.map.h + C.FALL_KILL_MARGIN + 10
    app.host.stack.update(1 / 60)
    assert scene.player.lives == lives - 1


def test_running_out_of_lives_ends_the_run():
    app, scene = playing()
    scene.player.lives = 1
    scene.player.box.y = scene.map.h + C.FALL_KILL_MARGIN + 10
    app.host.stack.update(1 / 60)
    settle(app)
    assert not isinstance(app.host.scene, type(scene))


# ── Drawing ─────────────────────────────────────────────────────────


def test_the_title_screen_says_the_name():
    app = hosted()

    async def go():
        async with await _piloted(app) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.3)
            text = buffer_text(app)
            assert "PLAY" in text
            assert "HOW TO PLAY" in text
            app.host.quit()

    run(go())


def test_a_run_draws_the_rooftops_the_robot_and_the_hud():
    app, scene = playing()

    async def go():
        async with await _piloted(app) as pilot:
            await pilot.pause()
            for _ in range(30):
                app.host.stack.update(1 / 60)
            await asyncio.sleep(0.3)
            text = buffer_text(app)
            assert "SCORE" in text
            assert theme.PLAYER in text, "the robot should be on screen"
            assert theme.SOLID in text, "there should be brick under him"
            assert theme.LIFE in text, "lives should be in the header"
            app.host.quit()

    run(go())


def test_the_level_name_is_in_the_header():
    app, scene = playing()

    async def go():
        async with await _piloted(app) as pilot:
            await pilot.pause()
            app.host.stack.update(1 / 60)
            await asyncio.sleep(0.3)
            assert "ROOFTOP" in buffer_text(app)
            app.host.quit()

    run(go())


def test_a_terminal_below_the_floor_is_told_the_numbers():
    """Naming them matters more here than anywhere: 60 columns is the widest
    floor in the arcade, and "too small" alone does not say it is the width."""
    app, scene = playing()

    async def go():
        async with await _piloted(app, size=(40, 12)) as pilot:
            await pilot.pause()
            await asyncio.sleep(0.3)
            text = buffer_text(app)
            assert "TOO SMALL" in text
            assert "60x16" in text, "the floor should be named"
            assert "SCORE" not in text
            app.host.quit()

    run(go())


def test_a_wider_terminal_shows_more_of_the_level():
    """The camera is sized from the terminal, not from the web canvas.

    Rendered synchronously rather than under a live pilot: the camera chases
    the player between frames, so a test that let the loop run would be racing
    the thing it is measuring.
    """
    def visible_at(cols):
        app, scene = playing()
        app.host.game.surface.buffer.resize(cols, 24)
        scene._resize_camera()
        return scene.camera.view_w

    assert visible_at(100) > visible_at(60)


def test_the_game_help_fits_the_smallest_terminal():
    """``_fit`` truncates from the right and says nothing about it, so a hint
    line that outgrows the floor loses its last key silently — and the last
    key here is how to get out."""
    from tron.scenes import GAME_HELP, PAUSE_HELP

    assert len(GAME_HELP) <= theme.MIN_COLS - 2
    assert len(PAUSE_HELP) <= theme.MIN_COLS - 2
