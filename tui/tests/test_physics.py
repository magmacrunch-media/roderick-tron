"""The rules, with nothing but pytest on the machine.

Nothing here imports the engine, and ``test_rules_layer_is_standalone`` is what
proves it rather than leaving it to habit. Several of these tests are
measurements from the port's design notes kept executable, so that a fourth
level or a retuned constant breaks a test instead of quietly invalidating an
argument nobody re-runs.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

from tron import cells
from tron import config as C
from tron.levels import LEVELS
from tron.player import Intent, Player
from tron.tilemap import Box, Tilemap

WEB_CONFIG = pathlib.Path(__file__).resolve().parents[2] / "web" / "js" / "config.js"


def maps():
    return [Tilemap(level) for level in LEVELS]


def run(player, intent, frames, dt=1.0):
    for _ in range(frames):
        player.update(intent, dt)


# ── The port is a port ──────────────────────────────────────────────


@pytest.mark.skipif(
    not WEB_CONFIG.exists(), reason="web/ not present (installed wheel)"
)
def test_constants_match_the_web_build():
    """Every constant this module shares with config.js has the same value.

    The web build stays the source of truth for tuning, so the failure mode
    worth catching is a number changed there and not here. Only scalars are
    compared: the JS getters and the colour table have no counterpart.
    """
    with open(WEB_CONFIG, encoding="utf-8", newline="") as fh:
        src = fh.read()
    found = dict(
        re.findall(r"^\s{4}([A-Z][A-Z0-9_]*):\s*(-?\d+(?:\.\d+)?),", src, re.M)
    )
    assert len(found) > 40, f"parsed only {len(found)} constants — did config.js move?"

    shared = {k: v for k, v in found.items() if hasattr(C, k)}
    assert len(shared) > 40, "almost nothing matched by name; check the port"

    mismatched = {
        k: (float(v), getattr(C, k))
        for k, v in shared.items()
        if abs(float(v) - float(getattr(C, k))) > 1e-9
    }
    assert not mismatched, f"diverged from config.js: {mismatched}"


def test_rules_layer_is_standalone():
    """The rules import nothing outside the standard library.

    Run in a subprocess: importing them in-process here would pass whether or
    not pytest had already dragged the engine in.
    """
    code = (
        "import sys;"
        "import tron.config, tron.tilemap, tron.player, tron.entities, tron.cells;"
        "bad=[m for m in sys.modules if m.split('.')[0] in "
        "{'magmacrunch','textual','rich'}];"
        "print(bad)"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert out.stdout.strip() == "[]", f"rules pulled in {out.stdout.strip()}"


def test_absent_constants_are_absent_on_purpose():
    """JUMP_CUT and the run modifier have no counterpart here.

    Both read input a terminal cannot deliver. Keeping them as dead constants
    would suggest they were merely unused rather than deliberately dropped.
    """
    assert not hasattr(C, "JUMP_CUT")
    assert hasattr(C, "RUN_CHARGE_FRAMES"), "the replacement for the SHIFT modifier"


# ── Levels ──────────────────────────────────────────────────────────


def test_every_level_parses_with_a_spawn_and_an_exit():
    for m in maps():
        assert m.cols == 96, m.name
        assert m.exit is not None, f"{m.name} has no exit"
        assert m.spawn.x > 0, f"{m.name} kept the default spawn"


def test_entity_characters_are_lifted_out_of_the_grid():
    """Collision never has to know what a gargoyle is."""
    for m in maps():
        flat = "".join("".join(row) for row in m.grid)
        assert not (set(flat) & set("SEoTRONgfsbc")), m.name
        assert set(flat) <= set(".#=~^-"), sorted(set(flat))


def test_the_letters_spell_tron_once_per_level():
    for m in maps():
        assert sorted(letter.ch for letter in m.letters) == ["N", "O", "R", "T"], m.name


# ── The jump ────────────────────────────────────────────────────────


def test_a_full_jump_reaches_its_configured_height():
    m = Tilemap(LEVELS[0])
    p = Player(m)
    p.grounded = True
    p.coyote = C.COYOTE_FRAMES
    top = p.box.y
    run(p, Intent(jump=True), 1)
    for _ in range(120):
        p.update(Intent(), 1.0)
        top = min(top, p.box.y)
        if p.grounded:
            break
    rise = m.spawn.y - top
    assert rise == pytest.approx(C.JUMP_HEIGHT, abs=6), rise


def test_the_jump_is_fixed_height():
    """Releasing early cannot clip it, because there is no release to read.

    The web build's JUMP_CUT would make these two arcs differ. Holding nothing
    after the press must reach the same apex as pressing every frame.
    """
    apexes = []
    for keep_pressing in (False, True):
        m = Tilemap(LEVELS[0])
        p = Player(m)
        p.grounded = True
        p.coyote = C.COYOTE_FRAMES
        p.update(Intent(jump=True), 1.0)
        top = p.box.y
        for _ in range(120):
            p.update(Intent(jump=keep_pressing), 1.0)
            top = min(top, p.box.y)
            if p.grounded:
                break
        apexes.append(top)
    assert apexes[0] == pytest.approx(apexes[1], abs=0.001)


def test_no_level_needs_a_clipped_jump():
    """The measurement that justifies dropping JUMP_CUT, kept executable.

    Walk every tile a body could stand on and check the headroom above it. If
    a level ever puts a ceiling inside jump height, a fixed-height jump can
    brain him on it and the argument in config.py stops holding.
    """
    tight = []
    for m in maps():
        for tx in range(m.cols):
            for ty in range(m.rows - 1):
                if m.tile_at(tx, ty + 1) not in "#=":
                    continue  # nothing to stand on
                if m.tile_at(tx, ty) != ".":
                    continue  # not standable itself
                head = 0
                y = ty
                while y >= 0 and m.tile_at(tx, y) != "#":
                    head += 1
                    y -= 1
                if head * C.TILE < C.JUMP_HEIGHT:
                    tight.append((m.name, tx, ty, head))
    assert not tight, f"a full jump would hit a ceiling at {tight[:5]}"


def test_coyote_time_allows_a_jump_just_after_the_ledge():
    m = Tilemap(LEVELS[0])
    p = Player(m)
    p.grounded = True
    p.coyote = C.COYOTE_FRAMES
    p.update(Intent(), 1.0)  # steps off; coyote is now counting down
    p.grounded = False
    p.update(Intent(jump=True), 1.0)
    assert p.vy < 0, "a jump inside the coyote window was refused"


def test_the_jump_buffer_survives_the_repeat_delay_argument():
    """Airtime outlasts a keyboard's repeat delay, which is why edges suffice.

    Not a behavioural test so much as a pinned number: the plan leans on a
    550ms arc against a ~500ms repeat delay, and a retune of GRAVITY or
    JUMP_FORCE that broke it would go unnoticed otherwise.
    """
    airtime_ms = C.JUMP_AIRTIME / 60.0 * 1000.0
    assert airtime_ms > 500, f"airtime fell to {airtime_ms:.0f}ms"


# ── Earned speed ────────────────────────────────────────────────────


def test_speed_starts_at_a_walk_and_ramps_to_a_run():
    m = Tilemap(LEVELS[0])
    p = Player(m)
    p.grounded = True
    assert p.max_speed() == pytest.approx(C.WALK_MAX)
    run(p, Intent(right=True), C.RUN_CHARGE_FRAMES + 5)
    assert p.max_speed() == pytest.approx(C.RUN_MAX)


def test_turning_spends_the_charge():
    """A run-up is a commitment; reversing is how you give it up."""
    m = Tilemap(LEVELS[0])
    p = Player(m)
    p.grounded = True
    run(p, Intent(right=True), C.RUN_CHARGE_FRAMES + 5)
    p.update(Intent(left=True), 1.0)
    assert p.max_speed() == pytest.approx(C.WALK_MAX)


def test_earned_speed_fits_the_tightest_runup():
    """Full speed must arrive before the level runs out of ground.

    The tightest run-up in any level is the nine tiles before ROOFTOP
    REQUIEM's seven-tile gap. Reaching RUN_MAX later than that would make the
    gap uncrossable, which is the failure this whole design has to avoid.
    """
    m = Tilemap(LEVELS[0])
    p = Player(m)
    p.grounded = True
    start = p.box.x
    for _ in range(400):
        p.update(Intent(right=True), 1.0)
        p.grounded = True  # flat ground; this test is about the ramp alone
        if p.charge >= C.RUN_CHARGE_FRAMES:
            break
    tiles = (p.box.x - start) / C.TILE
    assert tiles < 9, f"took {tiles:.1f} tiles to reach full speed"


def test_a_roll_still_beats_a_run():
    """The three distances the levels are designed against stay ordered."""
    assert C.WALK_MAX < C.RUN_MAX < C.ROLL_MAX
    reach = lambda v: v * C.JUMP_AIRTIME / C.TILE  # noqa: E731
    assert reach(C.WALK_MAX) < 4 < reach(C.RUN_MAX) < 7 < reach(C.ROLL_MAX)


# ── Collision ───────────────────────────────────────────────────────


def test_one_way_platforms_are_passable_from_below():
    m = Tilemap(LEVELS[0])
    box = Box(0, 0, C.PLAYER_W, C.PLAYER_H)
    # A platform row from the real level: find one and sit just under it.
    ty, tx = next(
        (y, x)
        for y in range(m.rows)
        for x in range(m.cols)
        if m.tile_at(x, y) == "="
    )
    box.x = tx * C.TILE
    box.y = ty * C.TILE + C.TILE  # below it
    rising = m.move_y(box, -6.0)
    assert not rising.ground, "a one-way platform blocked an upward move"


def test_one_way_platforms_catch_a_body_falling_onto_them():
    m = Tilemap(LEVELS[0])
    ty, tx = next(
        (y, x)
        for y in range(m.rows)
        for x in range(m.cols)
        if m.tile_at(x, y) == "="
    )
    box = Box(tx * C.TILE, ty * C.TILE - C.PLAYER_H - 4, C.PLAYER_W, C.PLAYER_H)
    land = m.move_y(box, 6.0)
    assert land.ground and land.platform
    assert box.y + box.h == pytest.approx(ty * C.TILE)


def test_a_body_resting_on_a_platform_does_not_sink():
    """The bug the bottom_row scan in platform_top exists to stop."""
    m = Tilemap(LEVELS[0])
    ty, tx = next(
        (y, x)
        for y in range(m.rows)
        for x in range(m.cols)
        if m.tile_at(x, y) == "="
    )
    box = Box(tx * C.TILE, ty * C.TILE - C.PLAYER_H, C.PLAYER_W, C.PLAYER_H)
    for _ in range(30):
        land = m.move_y(box, C.GRAVITY)
        assert land.ground, "fell through a platform it was resting on"
    assert box.y + box.h == pytest.approx(ty * C.TILE)


def test_nothing_tunnels_through_a_wall_at_speed():
    """Stepped movement, tested at more than a tile per frame."""
    m = Tilemap(LEVELS[0])
    # A wall with at least three tiles of air to its left, so the run-up is
    # inside the level: off the left edge reads as solid and would stop the
    # body before it ever reached the wall under test.
    ty, tx = next(
        (y, x)
        for y in range(m.rows)
        for x in range(3, m.cols)
        if m.tile_at(x, y) == "#"
        and all(m.tile_at(x - k, y) == "." for k in (1, 2, 3))
    )
    box = Box((tx - 3) * C.TILE, ty * C.TILE, C.PLAYER_W, C.PLAYER_H)
    m.move_x(box, 200.0)
    assert not m.overlaps_solid(box.x, box.y, box.w, box.h)
    assert box.x + box.w <= tx * C.TILE + 0.001


def test_the_level_is_walled_but_open_below():
    m = Tilemap(LEVELS[0])
    assert m.tile_at(-1, 5) == "#"
    assert m.tile_at(m.cols, 5) == "#"
    assert m.tile_at(5, m.rows) == "."  # falling out of the bottom kills


def test_a_roll_fits_where_a_stand_does_not():
    assert C.ROLL_H <= C.TILE < C.PLAYER_H


# ── dt ──────────────────────────────────────────────────────────────


def test_the_simulation_is_frame_rate_independent():
    """The same arc, stepped at four different rates, lands in the same place.

    Not to the pixel, and it cannot be: this is semi-implicit Euler, so the
    step size shifts the result slightly and the web build has exactly the same
    spread. Measured across dt 0.25 to 2.0 it is 3.1px horizontally and 7.5px
    vertically over a 21-frame jump.

    The tolerance is set above that and well below what the bug it guards
    would produce. Dropping dt from a position step -- the mistake the runner
    shipped, which ran at double speed on a 120Hz display -- puts x at 121px
    against a baseline of 60. Eight pixels catches that with sixty to spare.
    """
    def fall(dt, frames):
        m = Tilemap(LEVELS[0])
        p = Player(m)
        p.grounded = True
        p.coyote = C.COYOTE_FRAMES
        p.update(Intent(jump=True, right=True), dt)
        for _ in range(frames):
            p.update(Intent(right=True), dt)
        return p.box.x, p.box.y

    base = fall(1.0, 20)
    for dt, frames in ((0.5, 40), (0.25, 80), (2.0, 10)):
        got = fall(dt, frames)
        assert got[0] == pytest.approx(base[0], abs=8.0), f"x at dt={dt}"
        assert got[1] == pytest.approx(base[1], abs=8.0), f"y at dt={dt}"


def test_frames_per_second_is_the_only_conversion():
    """The engine hands out seconds; the constants are per 60fps frame."""
    assert C.FRAMES_PER_SECOND == 60.0
    assert pytest.approx(0.53, abs=0.02) == C.JUMP_AIRTIME / C.FRAMES_PER_SECOND


# ── Cells ───────────────────────────────────────────────────────────


def test_a_tile_is_square_at_a_terminals_aspect():
    assert cells.CELLS_PER_TILE == 2
    assert cells.CELL_W * 2 == cells.CELL_H


def test_the_web_viewport_is_sixty_columns():
    assert cells.min_cols_for() == 60
    assert cells.min_cols_for() < 80, "must fit the terminal that always exists"


def test_the_camera_never_shows_past_the_level():
    m = Tilemap(LEVELS[0])
    p = Player(m)
    view_w, view_h = cells.playfield_size(60, 17)
    cam = cells.Camera(m, view_w, view_h)
    for x in (-500, 0, m.w * 2):
        p.box.x = x
        cam.snap_to(p)
        assert 0 <= cam.x <= m.w - view_w
        assert 0 <= cam.y <= max(0, m.h - view_h)


def test_a_level_shorter_than_the_window_pins_to_the_origin():
    m = Tilemap(LEVELS[0])
    p = Player(m)
    cam = cells.Camera(m, m.w * 2, m.h * 2)
    cam.snap_to(p)
    assert (cam.x, cam.y) == (0.0, 0.0)


def test_the_tile_window_covers_the_visible_columns():
    m = Tilemap(LEVELS[0])
    cam = cells.Camera(m, *cells.playfield_size(60, 17))
    cam.x, cam.y = 320.0, 0.0
    tx0, ty0, tx1, ty1 = cam.tile_window(60, 17)
    assert tx0 <= 320 // C.TILE
    assert tx1 >= (320 + 60 * cells.CELL_W) // C.TILE - 1
    assert 0 <= ty0 <= ty1 <= m.rows - 1
