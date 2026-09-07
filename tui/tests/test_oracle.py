"""Hold the port to the shipped JavaScript, frame by frame.

``tools/js_oracle.mjs`` loads the real browser modules into a node vm, drives
them from a seeded input script and emits every frame. This replays the
identical script against the Python port and compares. Nothing here
reimplements game logic -- a test that did could pass while both versions were
wrong in the same way.

Regenerated on every run rather than committed, so the trace cannot go stale
against a web build that has moved on. That costs about a second and buys the
guarantee the whole file exists for.

**Two rules are deliberately held out of the comparison**, because the port
changed them on purpose and a comparison that included them would be red
whether or not anything was broken:

* the jump is fixed height here, so the oracle holds JUMP down throughout and
  the browser's ``JUMP_CUT`` never fires;
* the run modifier became earned speed, so the oracle holds RUN down and this
  side pins the cap with :class:`PinnedRun`.

Both are asserted from the other direction in ``test_physics.py``. Everything
else is in scope, which is most of the game.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tron import config as C
from tron.entities import Entities
from tron.levels import LEVELS
from tron.player import Intent, Player
from tron.tilemap import Box, Tilemap

TUI = Path(__file__).resolve().parents[1]
WEB_JS = TUI.parent / "web" / "js"

#: The browser and the port both use IEEE-754 doubles and perform the same
#: operations in the same order, so the traces agree far more tightly than this.
#: The tolerance is here to keep a last-place difference from being a failure,
#: not to paper over a divergence -- anything real is orders of magnitude
#: larger. ``test_the_tolerance_is_not_carrying_anything`` proves it is slack.
TOL = 1e-9

#: The ``trace`` fixture in conftest.py skips on its own when node or web/ is
#: missing, so nothing here needs a guard of its own.


class PinnedRun(Player):
    """The port, with its earned-speed ramp pinned to the top.

    The oracle holds the browser's RUN modifier down for the whole run, which
    fixes its cap at ``RUN_MAX``. This is the same statement on this side: it
    replaces exactly the one method that differs and leaves everything else --
    acceleration, friction, the turn boost, the overspeed bleed -- untouched.
    """

    def max_speed(self) -> float:
        return C.ROLL_MAX if self.rolling else C.RUN_MAX


def intents(script):
    for f in script:
        yield Intent(
            left=f["left"], right=f["right"], down=f["down"],
            jump=f["jump"], roll=f["roll"],
        )


# ── The constants ───────────────────────────────────────────────────


def test_the_constants_agree(trace):
    """Read out of the running browser, not out of the file this time."""
    shared = {k: v for k, v in trace["config"].items() if hasattr(C, k)}
    assert len(shared) > 40, "almost nothing matched by name"
    bad = {
        k: (v, getattr(C, k))
        for k, v in shared.items()
        if abs(v - float(getattr(C, k))) > TOL
    }
    assert not bad, f"diverged from the running game: {bad}"


# ── Collision ───────────────────────────────────────────────────────


@pytest.mark.parametrize("index", range(3))
def test_collision_matches_probe_for_probe(trace, index):
    """The part that has to be identical to the pixel.

    Random bodies and deltas, including deltas well past a tile, so the
    stepped movers' anti-tunnelling path is covered rather than assumed.
    """
    level = trace["levels"][index]
    m = Tilemap(LEVELS[index])
    bad = []
    for i, probe in enumerate(level["collision"]):
        a, want = probe["in"], probe["out"]
        box = Box(a["x"], a["y"], a["w"], a["h"])
        hit = m.move_x(box, a["dx"])
        land = m.move_y(box, a["dy"], a["dropping"])
        got = (box.x, box.y, hit, land.ground, land.ceiling, land.platform)
        exp = (
            want["x"], want["y"], want["hit"],
            want["ground"], want["ceiling"], want["platform"],
        )
        moved = abs(got[0] - exp[0]) > TOL or abs(got[1] - exp[1]) > TOL
        if moved or got[2:] != exp[2:]:
            bad.append((i, a, exp, got))
    assert not bad, (
        f"{len(bad)} of {len(level['collision'])} probes differ; first: {bad[0]}"
    )


# ── The player ──────────────────────────────────────────────────────

FIELDS = [
    "box.x", "box.y", "box.w", "box.h",
    "vx", "vy", "grounded", "rolling",
    "facing", "coyote", "jump_buffer", "roll_timer",
]


def player_state(p: Player) -> list[float]:
    return [
        p.box.x, p.box.y, p.box.w, p.box.h,
        p.vx, p.vy,
        1 if p.grounded else 0, 1 if p.rolling else 0,
        p.facing, p.coyote, p.jump_buffer, p.roll_timer,
    ]


@pytest.mark.parametrize("index", range(3))
def test_the_player_matches_frame_for_frame(trace, index):
    """Three hundred frames of scripted play, compared every frame.

    Covers collision, coyote time, the jump buffer, roll commitment and the
    roll-jump momentum rule, updraft lift and drift, friction, the overspeed
    bleed, and the drop-through the browser only gained once this oracle found
    it was reading a consumed key edge.
    """
    level = trace["levels"][index]
    m = Tilemap(LEVELS[index])
    p = PinnedRun(m)

    pairs = zip(intents(level["script"]), level["player"], strict=True)
    for frame, (intent, want) in enumerate(pairs):
        p.update(intent, 1.0)
        got = player_state(p)
        for name, g, w in zip(FIELDS, got, want, strict=True):
            assert abs(g - w) <= TOL, (
                f"level {index}, frame {frame}, {name}: port {g!r} vs browser {w!r}"
            )


# ── Entities ────────────────────────────────────────────────────────


@pytest.mark.parametrize("index", range(3))
def test_the_entities_match_frame_for_frame(trace, index):
    """Enemies, bells and trolleys, beside the same player.

    Gargoyle ledge-turning is the piece worth the trouble: it is the one bit of
    enemy logic with geometry in it, and a port that got the footing probe's
    offset wrong would walk them off the roof within seconds while still
    looking plausible on its own.
    """
    level = trace["levels"][index]
    m = Tilemap(LEVELS[index])
    p = PinnedRun(m)
    e = Entities(m)

    pairs = zip(intents(level["script"]), level["entities"], strict=True)
    for frame, (intent, want) in enumerate(pairs):
        p.update(intent, 1.0)
        e.update(p, intent, 1.0)

        got_enemies = [[x.kind, x.x, x.y, x.dir, x.hp] for x in e.enemies]
        assert len(got_enemies) == len(want["enemies"]), (
            f"level {index}, frame {frame}: {len(got_enemies)} enemies vs "
            f"{len(want['enemies'])}"
        )
        for a, b in zip(got_enemies, want["enemies"], strict=True):
            assert a[0] == b[0], f"level {index}, frame {frame}: kind {a[0]} vs {b[0]}"
            assert abs(a[1] - b[1]) <= TOL, f"lvl {index} frame {frame}: enemy x"
            assert abs(a[2] - b[2]) <= TOL, f"lvl {index} frame {frame}: enemy y"
            assert a[3] == b[3], f"level {index}, frame {frame}: enemy dir"
            assert a[4] == b[4], f"level {index}, frame {frame}: enemy hp"

        for a, b in zip(e.bells, want["bells"], strict=True):
            assert abs(a.angle - b[0]) <= TOL, f"lvl {index} frame {frame}: bell"
            assert abs(a.cooldown - b[1]) <= TOL, f"lvl {index} frame {frame}: cooldown"

        for a, b in zip(e.trolleys, want["trolleys"], strict=True):
            assert abs(a.x - b[0]) <= TOL, f"level {index}, frame {frame}: trolley x"
            assert abs(a.y - b[1]) <= TOL, f"level {index}, frame {frame}: trolley y"
            assert abs(a.vx - b[2]) <= TOL, f"level {index}, frame {frame}: trolley vx"
            assert (1 if a.riding else 0) == b[3], f"lvl {index} frame {frame}: riding"
            assert (1 if a.spent else 0) == b[4], f"lvl {index} frame {frame}: spent"

        taken = sum(1 for n in m.notes if n.taken)
        assert taken == want["notesTaken"], f"level {index}, frame {frame}: notes taken"
        letters = sum(1 for x in m.letters if x.taken)
        assert letters == want["lettersTaken"], f"level {index}, frame {frame}: letters"


# ── Dropping through one-way platforms ──────────────────────────────


@pytest.mark.parametrize("index", range(3))
def test_dropping_through_platforms_matches(trace, index):
    """The mechanic the browser only gained when this oracle was being built.

    ``Input.jump()`` is ``wasPressed``, so player.js's second call always saw a
    consumed edge and ``dropping`` was permanently false. The port read its
    edge from a plain field and had been doing the intended thing all along,
    so the divergence would have looked like the port being wrong.

    It has its own trace because a mutation run showed the scripted play never
    reached it: disabling drop-through here left every other comparison in this
    file green. Both halves are traced -- holding down and not holding it --
    so a port that dropped through unconditionally would fail too.
    """
    level = trace["levels"][index]
    m = Tilemap(LEVELS[index])
    assert level["drops"], f"level {index} has no one-way platforms to test"

    for run in level["drops"]:
        p = PinnedRun(m)
        p.reset(m.spawn)
        p.box.x = run["tx"] * C.TILE
        p.box.y = run["ty"] * C.TILE - p.box.h - 10
        p.vx, p.vy = 0.0, 2.0
        p.grounded = False
        p.coyote = 0.0

        intent = Intent(down=run["holdDown"], jump=True)
        for frame, want in enumerate(run["frames"]):
            p.update(intent, 1.0)
            got = [p.box.x, p.box.y, p.vy, 1 if p.grounded else 0]
            names = ["x", "y", "vy", "grounded"]
            for name, g, w in zip(names, got, want, strict=True):
                assert abs(g - w) <= TOL, (
                    f"level {index}, platform {run['tx']},{run['ty']}, "
                    f"down={run['holdDown']}, frame {frame}, {name}: {g!r} vs {w!r}"
                )


def test_holding_down_is_what_makes_the_difference(trace):
    """The trace is only worth having if its two halves actually diverge.

    If holding down changed nothing, the test above would compare two identical
    runs and pass no matter what drop-through did.
    """
    differed = 0
    for level in trace["levels"]:
        by_spot: dict[tuple[int, int], dict[bool, list]] = {}
        for run in level["drops"]:
            spot = by_spot.setdefault((run["tx"], run["ty"]), {})
            spot[run["holdDown"]] = run["frames"]
        for pair in by_spot.values():
            if len(pair) == 2 and pair[True] != pair[False]:
                differed += 1
    assert differed, "holding down changed nothing anywhere -- drop-through is inert"


# ── The tolerance ───────────────────────────────────────────────────


def test_the_tolerance_is_not_carrying_anything(trace):
    """The traces agree far more tightly than TOL, so it is slack, not glue.

    A tolerance quietly absorbing a real difference is the way a comparison
    test rots into a formality. Measuring the largest disagreement and
    asserting it is far below the threshold keeps that visible.
    """
    worst = 0.0
    for index in range(3):
        level = trace["levels"][index]
        m = Tilemap(LEVELS[index])
        p = PinnedRun(m)
        for intent, want in zip(intents(level["script"]), level["player"], strict=True):
            p.update(intent, 1.0)
            for g, w in zip(player_state(p), want, strict=True):
                worst = max(worst, abs(g - w))
    assert worst < TOL / 1000, (
        f"largest disagreement is {worst!r}, close enough to the {TOL!r} "
        "tolerance that the tolerance is doing real work"
    )
    print(f"\n  largest player disagreement across 900 frames: {worst!r}")
